"""IBKR API Client wrapper using ib_insync.
Handles connection, SPY contract, and option chain retrieval.
"""
import logging
import time
import math
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from ib_insync import IB, Stock, Option, Contract, Ticker
from ib_insync.contract import ContractDetails
from config import settings
import os
pod_name = os.getenv('HOSTNAME', 'detector-0')
client_id = abs(hash(pod_name)) % 1000  # 0-999 �nico por pod
logger = logging.getLogger(__name__)

class IBKRClient:
    """Interactive Brokers API client wrapper."""
    
    def __init__(self):
        self.ib = IB()
        self.connected = False
        self.spy_contract: Optional[Stock] = None
        
    def connect(self) -> bool:
        """Connect to IBKR Gateway.
        
        Returns:
            bool: True if connected successfully
        """
        try:
            logger.info(f"Connecting to IBKR at {settings.ibkr_host}:{settings.ibkr_port}")
            self.ib.connect(
                host=settings.ibkr_host,
                port=settings.ibkr_port,
                clientId=settings.ibkr_client_id,
                timeout=90,
                readonly=True
            )
            self.ib.sleep(5)  # Esperar confirmación del servidor
            self.connected = True
            logger.info("Successfully connected to IBKR Gateway")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from IBKR Gateway."""
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IBKR Gateway")
    
    def ensure_connected(self) -> bool:
        """Ensure IBKR connection is active, reconnect if needed.
        
        Returns:
            bool: True if connected (or reconnected successfully)
        """
        if self.ib.isConnected():
            return True
        
        logger.warning("?? IBKR connection lost, attempting reconnection...")
        
        # Try reconnecting with exponential backoff
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            if self.connect():
                logger.info(f"? Reconnected successfully on attempt {attempt}")
                return True
            
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 2, 4, 8 seconds
                logger.warning(f"Retry {attempt}/{max_retries} in {wait_time}s...")
                time.sleep(wait_time)
        
        logger.error("? Failed to reconnect after all retries")
        return False
    
    def get_spy_contract(self) -> Optional[Stock]:
        """Get and qualify SPY stock contract.
        
        Returns:
            Stock: Qualified SPY contract or None
        """
        try:
            spy = Stock('SPY', 'SMART', 'USD')
            self.ib.qualifyContracts(spy)
            self.spy_contract = spy
            logger.info(f"Qualified SPY contract: {spy}")
            return spy
        except Exception as e:
            logger.error(f"Failed to get SPY contract: {e}")
            return None
    
    def get_spy_price(self) -> Optional[float]:
        """Get current SPY market price.
        
        Returns:
            float: Current SPY price or None
        """
        if not self.spy_contract:
            self.get_spy_contract()
        
        if not self.spy_contract:
            return None
        
        try:
            ticker = self.ib.reqMktData(self.spy_contract, '', False, False)
            price = float('nan')
            for attempt in range(10):
                price = ticker.marketPrice()
                if not math.isnan(price):
                    break
                self.ib.sleep(0.5)
            
            # Fallback: last → close → bid-ask promedio
            if math.isnan(price):
                price = ticker.last or ticker.close or \
                        ((ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else float('nan'))
            
            if math.isnan(price):
                raise ValueError("No SPY data available after 5s wait")
            
            logger.info(f"SPY price: ${price:.2f}")
            return price
            
            
                
        except Exception as e:
            logger.error(f"Failed to get SPY price: {e}")
            return None
    
    def get_option_chain_params(self) -> Optional[Dict[str, Any]]:
        """Get option chain parameters for SPY (expirations, strikes).
        
        NOTE: This method may not return 0DTE expirations. Use get_0dte_options() instead.
        
        Returns:
            dict: Option chain parameters or None
        """
        if not self.spy_contract:
            self.get_spy_contract()
        
        if not self.spy_contract:
            return None
        
        try:
            chains = self.ib.reqSecDefOptParams(
                underlyingSymbol=self.spy_contract.symbol,
                futFopExchange='',
                underlyingSecType=self.spy_contract.secType,
                underlyingConId=self.spy_contract.conId
            )
            
            if not chains:
                logger.warning("No option chains found for SPY")
                return None
            
            # Filter for SMART exchange
            smart_chain = next((c for c in chains if c.exchange == 'SMART'), None)
            if not smart_chain:
                logger.warning("No SMART exchange chain found")
                return None
            
            logger.info(f"Found {len(smart_chain.expirations)} expirations for SPY")
            return {
                'expirations': sorted(smart_chain.expirations),
                'strikes': sorted(smart_chain.strikes),
                'exchange': smart_chain.exchange
            }
        except Exception as e:
            logger.error(f"Failed to get option chain params: {e}")
            return None
    
    def get_0dte_options(self, spy_price: float) -> List[Dict[str, Any]]:
        """Get 0DTE options by direct contract construction (bypasses reqSecDefOptParams).
        
        This method constructs option contracts directly instead of querying available expirations,
        which is necessary because reqSecDefOptParams may not return 0DTE expirations.
        
        Args:
            spy_price: Current SPY price to filter strikes
            
        Returns:
            list: Option data with bid/ask/volume
        """
        # Today's expiration in YYYYMMDD format
        today = datetime.now().strftime('%Y%m%d')  # '20260120'
        logger.info(f"Constructing 0DTE contracts for expiration: {today}")
        
        # Calculate strike range (�1% by default from settings)
        strike_range_pct = settings.strikes_range_percent / 100
        min_strike = spy_price * (1 - strike_range_pct)
        max_strike = spy_price * (1 + strike_range_pct)
        
        # Generate strikes in 1 intervals (SPY standard)
        strikes = []
        current = round(min_strike)
        while current <= max_strike:
            strikes.append(current)
            current += 1
        
        logger.info(f"Testing {len(strikes)} strikes for 0DTE ({min_strike:.2f} - {max_strike:.2f})")
        
        # Build and qualify contracts
        options_data = []
        valid_count = 0
        invalid_count = 0
        
        for strike in strikes:
            for right in ['C', 'P']:
                try:
                    # Direct contract construction
                    option = Option('SPY', today, strike, right, 'SMART')
                    
                    # Validate if contract exists
                    qualified = self.ib.qualifyContracts(option)
                    if not qualified:
                        invalid_count += 1
                        continue  # Skip invalid contracts
                    
                    valid_count += 1
                    
                    # Request market data
                    ticker = self.ib.reqMktData(option, '', False, False)
                    self.ib.sleep(0.3)  # Rate limiting (300ms between requests)
                    
                    # Only include if we have valid bid/ask
                    if ticker.bid and ticker.ask and ticker.bid > 0:
                        options_data.append({
                            'strike': strike,
                            'right': right,
                            'expiration': today,
                            'bid': ticker.bid,
                            'ask': ticker.ask,
                            'last': ticker.last if ticker.last else 0,
                            'volume': ticker.volume or 0,
                            'mid': (ticker.bid + ticker.ask) / 2
                        })
                
                except Exception as e:
                    logger.debug(f"Error processing {right} {strike}: {e}")
                    invalid_count += 1
                    continue
        
        logger.info(f"Qualified: {valid_count} contracts, Invalid: {invalid_count}")
        logger.info(f"Retrieved market data for {len(options_data)} options")
        return options_data


# Global client instance
ibkr_client = IBKRClient()
