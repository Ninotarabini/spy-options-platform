# -*- coding: utf-8 -*-
"""SPY Options Anomaly Detector - Main Application.
Continuously scans SPY 0DTE options for pricing anomalies and reports to backend API.
"""
import logging
import sys
import time
from datetime import datetime
from typing import List, Dict, Any
import requests

from config import settings
from ibkr_client import ibkr_client
from anomaly_algo import detect_anomalies


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Main detector application."""
    
    def __init__(self):
        self.running = False
        self.scan_count = 0
        self.anomaly_count = 0
        self.last_scan_time = None
        
    def start(self):
        """Start the detector main loop."""
        logger.info("=" * 60)
        logger.info("SPY Options Anomaly Detector - Starting")
        logger.info("=" * 60)
        logger.info(f"Configuration:")
        logger.info(f"  IBKR Host: {settings.ibkr_host}:{settings.ibkr_port}")
        logger.info(f"  Backend URL: {settings.backend_url}")
        logger.info(f"  Strategy: {settings.strategy_type}")
        logger.info(f"  Anomaly Threshold: {settings.anomaly_threshold}")
        logger.info(f"  Scan Interval: {settings.scan_interval_seconds}s")
        logger.info(f"  Strike Range: +/-{settings.strikes_range_percent}%")
        logger.info("=" * 60)
        
        # Connect to IBKR
        if not ibkr_client.connect():
            logger.error("Failed to connect to IBKR Gateway. Exiting.")
            sys.exit(1)
        
        # Get SPY contract
        if not ibkr_client.get_spy_contract():
            logger.error("Failed to get SPY contract. Exiting.")
            ibkr_client.disconnect()
            sys.exit(1)
        
        logger.info("Initialization complete. Starting scan loop...")
        self.running = True
        
        try:
            self.run_loop()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal. Shutting down...")
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def run_loop(self):
        """Main scanning loop."""
        while self.running:
            try:
                self.scan_and_detect()
                
                # Wait for next scan
                logger.info(f"Waiting {settings.scan_interval_seconds}s until next scan...")
                time.sleep(settings.scan_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in scan cycle: {e}", exc_info=True)
                logger.info("Continuing to next scan...")
                time.sleep(5)  # Brief pause before retry
    
    def scan_and_detect(self):
        """Perform one scan cycle: get data, detect anomalies, report."""
        self.scan_count += 1
        scan_start = time.time()
        
        logger.info("-" * 60)
        logger.info(f"Scan #{self.scan_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Ensure IBKR connection before proceeding
        if not ibkr_client.ensure_connected():
            logger.error("Cannot proceed without IBKR connection. Skipping scan.")
            return
        
        # Get current SPY price
        spy_price = ibkr_client.get_spy_price()
        if not spy_price:
            logger.warning("Could not get SPY price. Skipping scan.")
            return
        
        # Get 0DTE options data
        options_data = ibkr_client.get_0dte_options(spy_price)
        if not options_data:
            logger.warning("No options data retrieved. Skipping scan.")
            return
        
        logger.info(f"Retrieved {len(options_data)} options for analysis")
        
        # Detect anomalies
        anomalies = detect_anomalies(options_data, spy_price)
        
        if anomalies:
            self.anomaly_count += len(anomalies)
            logger.info(f"?? Found {len(anomalies)} anomalies!")
            
            # Report to backend API
            self.report_anomalies(anomalies)
        else:
            logger.info("? No anomalies detected")
        
        scan_duration = time.time() - scan_start
        self.last_scan_time = datetime.now()
        
        logger.info(f"Scan completed in {scan_duration:.2f}s")
        logger.info(f"Total scans: {self.scan_count} | Total anomalies: {self.anomaly_count}")
        logger.info("-" * 60)
    
    from datetime import datetime

    def _adapt_anomaly_for_backend(self, anomaly):
        """
        Adapta el dict crudo de anomaly_algo al schema que espera el backend.
        
        Mapeo de campos:
        - anomaly_algo genera 'deviation_pct' → backend espera 'deviation_percent'
        - anomaly_algo genera 'price' → backend espera 'mid_price'
        - anomaly_algo genera 'right' (C/P) → backend espera 'option_type' (CALL/PUT)
        """
        # Bug #1 FIX: Usar el campo que SÍ existe en anomaly_algo
        deviation = anomaly.get("deviation_pct")
        if deviation is None:
            raise ValueError("Anomaly missing deviation_pct")
        
        # Mapeo de option_type
        option_type = anomaly.get("right")
        if option_type == "C":
            option_type = "CALL"
        elif option_type == "P":
            option_type = "PUT"
        elif option_type not in ("CALL", "PUT"):
            raise ValueError(f"Invalid option_type: {option_type}")
        
        # Bug #3 FIX: Mapear campos correctamente
        return {
            "timestamp": anomaly.get("timestamp"),
            "symbol": "SPY",
            "strike": anomaly.get("strike"),
            "option_type": option_type,
            "bid": anomaly.get("bid"),
            "ask": anomaly.get("ask"),
            "mid_price": anomaly.get("price"),         # FIX: 'price' → 'mid_price'
            "expected_price": None,                     # FIX: No existe en anomaly_algo
            "deviation_percent": deviation,             # Ya mapeado correctamente
            "volume": anomaly.get("volume"),
            "open_interest": anomaly.get("open_interest", 0),
            "severity": anomaly.get("severity")
        }

   
    def _severity_from_deviation(self, d):
        d = abs(d)
        if d > 0.5:
            return "HIGH"
        elif d > 0.25:
            return "MEDIUM"
        return "LOW"


    
    def report_anomalies(self, anomalies: List[Dict[str, Any]]):
        """Report detected anomalies to backend API.
        
        Args:
            anomalies: List of anomaly data dicts
        """
        endpoint = f"{settings.backend_url}/anomalies"
        
        for anomaly in anomalies:
            payload = self._adapt_anomaly_for_backend(anomaly)
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    timeout=5
                )
                
                if response.status_code == 200:
                    logger.info(f"? Reported anomaly: {anomaly['right']} ${anomaly['strike']:.0f}")
                else:
                    logger.warning(f"? Failed to report anomaly: HTTP {response.status_code}")
            except KeyError as e:
                logger.warning(f"⚠️ Skipping malformed anomaly: missing {e}")        
            except requests.exceptions.RequestException as e:
                logger.error(f"? Error reporting anomaly: {e}")
    
    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down detector...")
        self.running = False
        ibkr_client.disconnect()
        logger.info(f"Final stats: {self.scan_count} scans, {self.anomaly_count} anomalies detected")
        logger.info("Detector stopped.")


def main():
    """Application entry point."""
    detector = AnomalyDetector()
    detector.start()


if __name__ == "__main__":
    main()
