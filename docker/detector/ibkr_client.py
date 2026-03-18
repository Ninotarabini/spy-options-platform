"""IBKR API Client wrapper using ib_insync.
Handles connection, SPY contract, and option chain retrieval.
"""
import asyncio   # ✅ Fix: necesario para asyncio.CancelledError en ensure_connected
import logging
import time
import math
import os

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from ib_async import IB, Stock, Option, Contract, Ticker
from ib_async.contract import ContractDetails
from config import settings

pod_name = os.getenv("HOSTNAME", "detector-0")
client_id = abs(hash(pod_name)) % 1000  # clientId estable y único por pod



class IBKRClient:
    """Interactive Brokers API client wrapper."""
    
    def __init__(self, config=None):
        self.logger = logging.getLogger("ibkr_client")  # ✅ Fix: import logging ya está al tope
        self.ib = IB()
        self.config = config
        self.connected = False
        self.spy_contract: Optional[Stock] = None
        self.active_subscriptions = {}
        self.contract_cache = {}
        self.spy_prev_close = None
        
        # === Event Handlers para Reconexión Automática ===
        self.ib.disconnectedEvent += self._on_disconnect
        self.ib.connectedEvent += self._on_connect
        
        if config:
            self.host = getattr(config, 'ibkr_host', 'ibkr-gateway-service')
            self.port = int(getattr(config, 'ibkr_port', 4001))
        else:
            self.host = 'ibkr-gateway-service'
            self.port = 4001


    def connect(self) -> bool:
        try:
            self.logger.info(f"Connecting to IBKR at {self.host}:{self.port}")

            # ✅ FIX: Usar self.client_id si existe, sino config
            c_id = getattr(self, 'client_id', None) or getattr(self.config, 'ibkr_client_id', 888)
    
            self.logger.info(f"Using clientId: {c_id}")  # ← LOG para verificar
    
            self.ib.connect(
                host=self.host,
                port=self.port,
                clientId=c_id,
                timeout=90,
                readonly=True
            )

            self.ib.reqMarketDataType(1)
            self.logger.info("Market Data Type configurado a 1 (Realtime/OPRA)")

            # --- Test de Permisos ---
            # ✅ Fix: datetime y math ya importados al nivel de módulo
            
            today_str = datetime.now().strftime('%Y%m%d')
            
            # Intentamos obtener el precio actual de SPY para el test ATM
            # Si es el primer arranque, usamos un fallback (ej. 700)
            # Obtener último precio conocido de Azure Storage
            
            # Fallback en cascada
            # Usar config en vez de hardcoded 500
            atm_strike = getattr(self.config, 'spy_fallback_price', 700)

            spy = Stock('SPY', 'SMART', 'USD')
            self.ib.qualifyContracts(spy)
            tickers = self.ib.reqTickers(spy)
            if tickers and tickers[0].marketPrice() > 0:
                atm_strike = round(tickers[0].marketPrice())
                self.logger.info(f"[OK] Precio real-time: ${atm_strike}")

            self.logger.info(f"🛠️ Validando permisos OPRA con: SPY {today_str} {atm_strike}C")
            test_spy_opt = Option('SPY', today_str, atm_strike, 'C', 'SMART')
        
            try:
                self.ib.qualifyContracts(test_spy_opt)
                test_ticker = self.ib.reqMktData(test_spy_opt, '', False, False)
                self.ib.sleep(2) 
            
                if not math.isnan(test_ticker.bid) or test_ticker.last > 0:
                    self.logger.info(f"[OK] OPRA OK - Test bid={test_ticker.bid}, last={test_ticker.last}")
                else:
                    self.logger.warning("⚠️ NO HAY DATOS OPRA - Revisa suscripciones en IBKR")
                
                self.ib.cancelMktData(test_spy_opt)

            except Exception as e:
                self.logger.error(f"[ERROR] Error en test de permisos: {e}")
            
            # --- Finalización ---
            self.connected = True
            self.logger.info("Successfully connected to IBKR Gateway")
            
            # ===== OBTENER PREVIOUS CLOSE =====
            hist_close = self.get_previous_close()
            if hist_close:
                self.spy_prev_close = hist_close
                self.logger.info(f"📊 Previous_close establecido: {self.spy_prev_close}")
            else:
                self.logger.warning("⚠️ No se pudo obtener previous_close")
            # ===================================
            
            return True
        

        except Exception as e:
            # MUY IMPORTANTE: Usar self.logger aquí también
            if hasattr(self, 'logger'):
                self.logger.error(f"Failed to connect to IBKR: {e}")
            else:
                print(f"Critical error (logger not ready): {e}")
            self.connected = False
            return False


    
    def disconnect(self):
        """Disconnect from IBKR Gateway."""
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            self.logger.info("Disconnected from IBKR Gateway")
    
    def ensure_connected(self) -> bool:
        """Verifica la conexión y reintenta persistentemente si se pierde."""
        if self.ib.isConnected():
            return True
        self.logger.warning("🔌 Conexión con IBKR perdida, iniciando reconexión robusta...")
        # Ajuste para mantenimiento nocturno: 
        # 20 intentos cada 30 segundos = 10 minutos de espera total.
        max_retries = 20 
        retry_delay = 30 
        for attempt in range(1, max_retries + 1):
            self.logger.info(f"Intento de reconexión {attempt}/{max_retries}...")
            
            # PASO CRÍTICO: Limpieza. Cerramos cualquier socket zombie antes de re-conectar.
            if self.ib.isConnected():
                self.ib.disconnect()
            
            # Intentamos conectar (Llamando a tu función connect() existente)
            if self.connect():
                self.logger.info(f"✅ Reconectado con éxito en el intento {attempt}")
                self.active_subscriptions.clear() # Limpiamos para evitar datos corruptos
                return True
            
            if attempt < max_retries:
                self.logger.warning(f"Fallo. Esperando {retry_delay}s para el próximo intento...")
                time.sleep(retry_delay)
        self.logger.error("❌ No se pudo reconectar tras 10 minutos de intentos nocturnos.")
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
            self.logger.info(f"Qualified SPY contract: {spy}")
            return spy
        except Exception as e:
            self.logger.error(f"Failed to get SPY contract: {e}")
            return None
        
    def get_previous_close(self) -> Optional[float]: 
        try:
            contract = Stock('SPY', 'SMART', 'USD')
        
            # Solicitar 1 barra diaria (la más reciente)
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',        # Vacío = más reciente
                durationStr='1 D',     # 1 día
                barSizeSetting='1 day', # Barra diaria
                whatToShow='TRADES',   # Datos de negociación
                useRTH=True,           # Solo horario regular
                formatDate=1
            )
        
            if bars and len(bars) > 0:
                close_price = bars[0].close
                self.logger.info(f"✅ Previous close IBKR histórico: ${close_price}")
                return close_price
            
        except Exception as e:
            self.logger.error(f"Error obteniendo previous close: {e}")
    
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
            
            # Guardar cierre anterior para cálculo % diario
            close_val = ticker.close if ticker.close else float('nan')
            if not math.isnan(close_val) and close_val > 0:
                self.spy_prev_close = close_val
            
            self.logger.info(f"SPY price: ${price:.2f}")
            return price           
                            
        except Exception as e:
            self.logger.error(f"Failed to get SPY price: {e}")
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
                self.logger.warning("No option chains found for SPY")
                return None
            
            # Filter for SMART exchange
            smart_chain = next((c for c in chains if c.exchange == 'SMART'), None)
            if not smart_chain:
                self.logger.warning("No SMART exchange chain found")
                return None
            
            self.logger.info(f"Found {len(smart_chain.expirations)} expirations for SPY")
            return {
                'expirations': sorted(smart_chain.expirations),
                'strikes': sorted(smart_chain.strikes),
                'exchange': smart_chain.exchange
            }
        except Exception as e:
            self.logger.error(f"Failed to get option chain params: {e}")
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
        self.logger.info(f"Constructing 0DTE contracts for expiration: {today}")
        
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
        
        self.logger.info(f"Testing {len(strikes)} strikes for 0DTE ({min_strike:.2f} - {max_strike:.2f})")
        
        # Build and qualify contracts
        options_data = []
        valid_count = 0
        invalid_count = 0
        
        for strike in strikes:
            for right in ['C', 'P']:
                try:
                    # Direct contract construction
                    option = Option('SPY', today, strike, right, 'SMART')
                    
                    cache_key = f"{strike}_{right}"

                    if cache_key in self.contract_cache:
                        option = self.contract_cache[cache_key]
                    else:
                        qualified = self.ib.qualifyContracts(option)
                        if not qualified:
                            continue
                        self.contract_cache[cache_key] = option
                                        
                    valid_count += 1
                    
                    # Request market data
                    ticker = self.ib.reqMktData(option, '100,101,106,221,233', False, False) 
                    self.ib.sleep(1)  # Rate limiting (ms between requests)
                    
                    # Determinar volumen según tipo de opción
                    vol = ticker.callVolume if right == "C" else ticker.putVolume
                    volume = int(vol) if (vol and not math.isnan(vol)) else 0
                    
                                         
                    self.logger.info(f"[DEBUG] {right} ${strike}: callVol={ticker.callVolume}, putVol={ticker.putVolume}, vol={ticker.volume}, lastSize={ticker.lastSize}, final_volume={volume}")
    

                    # Only include if we have valid bid/ask
                    
                    if volume > 0:  # Verificar volumen calculado (callVolume/putVolume)    
                        options_data.append({
                            'strike': strike,
                            'option_type': right,
                            'expiration': today,
                            'bid': ticker.bid,
                            'ask': ticker.ask,
                            'last': ticker.last if ticker.last else 0,
                            'volume': volume,
                            'open_interest': (ticker.callOpenInterest if right == 'C' else ticker.putOpenInterest) if right in ['C', 'P'] else 0,
                            'mid': (ticker.bid + ticker.ask) / 2,
                        })
                
                except Exception as e:
                    self.logger.debug(f"Error processing {right} {strike}: {e}")
                    invalid_count += 1
                    continue
        
        self.logger.info(f"Qualified: {valid_count} contracts, Invalid: {invalid_count}")
        self.logger.info(f"Retrieved market data for {len(options_data)} options")
        return options_data
    
    def shutdown(self):
        """Graceful shutdown for Kubernetes SIGTERM."""
        try:
            if self.ib.isConnected():
                self.logger.info("Cerrando sesión IBKR (shutdown)")
                self.ib.disconnect()
        except Exception as e:
            self.logger.warning("Error durante shutdown IBKR: %s", e)
            

    def update_atm_subscriptions(self, spy_price: float) -> List[Dict[str, Any]]:
        """
        Actualiza suscripciones dinámicamente según precio ATM actual.
        Fusiona gestión de strikes dinámica con captura robusta de volumen.
        """
        # ✅ Fix: math, datetime e Option ya importados al nivel de módulo
        
        today = datetime.now().strftime('%Y%m%d')
        
        # 1. Usar rango ATM FIJO (±5 strikes según refactoring Fase 1)
        final_range = getattr(self.config, 'atm_fixed_strikes', 5)

        atm_center = round(spy_price)
        min_strike = atm_center - final_range
        max_strike = atm_center + final_range

        # Definir el set de strikes finales
        current_strikes_set = set(range(int(min_strike), int(max_strike) + 1))
        
        self.logger.info(
            f"🎯 ATM FIJO | SPY: ${spy_price:.2f} | "
            f"Strikes: ±{final_range} ({min_strike} - {max_strike})"
        )

        # 3. Cancelar suscripciones obsoletas
        active_strikes = {int(k.split('_')[0]) for k in self.active_subscriptions.keys()}
        strikes_to_cancel = active_strikes - current_strikes_set
        
        cancel_count = 0
        for strike in strikes_to_cancel:
            for right in ['C', 'P']:
                key = f"{strike}_{right}"
                if key in self.active_subscriptions:
                    ticker = self.active_subscriptions.pop(key)
                    self.ib.cancelMktData(ticker.contract)
                    cancel_count += 1
        
        # 4. Identificar strikes nuevos
        remaining_strikes = {int(k.split('_')[0]) for k in self.active_subscriptions.keys()}
        strikes_to_add = current_strikes_set - remaining_strikes
        
        # 5. Suscribir nuevos strikes (CON TICK 233)
        add_count = 0
        # CREAR TODOS LOS CONTRATOS PRIMERO
        contracts_to_qualify = []
        for strike in strikes_to_add:
            for right in ['C', 'P']:
                option = Option('SPY', today, strike, right, 'SMART')
                contracts_to_qualify.append((option, strike, right))

        # CUALIFICAR TODOS EN BATCH (paralelo)
        if contracts_to_qualify:
            options_list = [c[0] for c in contracts_to_qualify]
            qualified_contracts = self.ib.qualifyContracts(*options_list)
    
            # SUSCRIBIR CUALIFICADOS
            
            for i, (option, strike, right) in enumerate(contracts_to_qualify):
                if i < len(qualified_contracts) and qualified_contracts[i]:
                    try:
                        ticker = self.ib.reqMktData(qualified_contracts[i], '100,101,233', False, False)
                        self.ib.sleep(0.1)
                        key = f"{strike}_{right}"
                        self.active_subscriptions[key] = ticker
                        add_count += 1
                    except Exception as e:
                        self.logger.error(f"Error suscribiendo {strike}_{right}: {e}")
        
        # 6. Pausa de sincronización
        try:
            self.ib.sleep(0.5)  # Reducido de 5s → 0.5s
        except (ConnectionError, ConnectionResetError, asyncio.CancelledError) as e:
            self.logger.error(f"Conexión perdida durante sleep: {e}")
            self.connect()
            return []
        except Exception as e:
            self.logger.error(f"Error inesperado durante sleep: {e}")
            return []
        
        # --- RECOLECCIÓN DE DATOS MEJORADA ---
        options_data = []
        for key, ticker in self.active_subscriptions.items():
            try:
                strike_str, right = key.split('_')
                
                # MEJORA: Lógica de Volumen Robusta (Acumulado Suave)
                vol = ticker.callVolume if right == "C" else ticker.putVolume
                
                # Fallback al volumen total si el específico es 0 o NaN
                if math.isnan(vol) or vol <= 0:
                    vol = ticker.volume

                volume = int(vol) if (not math.isnan(vol) and vol > 0) else 0
                
                # Mid price con seguridad
                bid = ticker.bid if not math.isnan(ticker.bid) and ticker.bid > 0 else 0
                ask = ticker.ask if not math.isnan(ticker.ask) and ticker.ask > 0 else 0
                mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
                
                options_data.append({
                    'strike': float(strike_str),
                    'option_type': right,
                    'expiration': today,
                    'bid': bid,
                    'ask': ask,
                    'last': ticker.last if not math.isnan(ticker.last) else 0,
                    'volume': volume, # <-- Volumen acumulado
                    'open_interest': (ticker.callOpenInterest if right == 'C' else ticker.putOpenInterest) if right in ['C', 'P'] else 0,
                    'mid': mid,
                })
            except Exception as e:
                self.logger.debug(f"Error procesando datos para {key}: {e}")
        
        self.logger.info(
            f"Suscripciones: {len(self.active_subscriptions)} | "
            f"ATM: {len(current_strikes_set)} strikes | "
            f"Limpia: {cancel_count} | "
            f"Nuevas: {add_count}"
        )
        
        return options_data
    
    def _on_disconnect(self):
        """Handler cuando IBKR se desconecta (evento automático ib_async)"""
        self.logger.warning("🔴 IBKR disconnected - esperando reconexión Gateway...")
        self.connected = False
        # NO intentar reconectar aquí (evita loops - ensure_connected lo maneja)
    
    def _on_connect(self):
        """Handler cuando IBKR reconecta (evento automático ib_async)"""
        self.logger.info("🟢 IBKR reconnected - limpiando estado...")
        self.connected = True
        self.active_subscriptions.clear()  # Reset subscriptions tras reconexión
  
# ✅ Fix: instancia global eliminada — IBKRClient se instancia en detector.py.
# Tenerla aqui creaba una segunda instancia fantasma al hacer el import.

