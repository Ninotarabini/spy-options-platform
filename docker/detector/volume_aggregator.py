"""
Volume Aggregator - Agrega volúmenes ATM para detectar tendencias de mercado.
Complementa anomaly_algo.py (individual strikes) con análisis agregado.
"""
from datetime import datetime
from typing import List, Dict, Tuple
import logging
import time

logger = logging.getLogger(__name__)

# COMENTADO: Método antiguo (agregación por rango ATM)
# def calculate_atm_range(spy_price: float, tolerance_pct: float = 2.0) -> Tuple[float, float]:
#     """..."""
#     min_strike = spy_price * (1 - tolerance_pct / 100)
#     max_strike = spy_price * (1 + tolerance_pct / 100)
#     return round(min_strike, 2), round(max_strike, 2)
# 
# def aggregate_atm_volumes(options_data: List[dict], spy_price: float) -> Dict:
#     """..."""
#     min_strike, max_strike = calculate_atm_range(spy_price)
#     
#     calls_volume = 0
#     puts_volume = 0
#     calls_count = 0
#     puts_count = 0
#     
#     for option in options_data:
#         strike = option.get("strike")
#         option_type = option.get("option_type", "").upper()
#         volume = option.get("volume", 0)
#         
#         if not (min_strike <= strike <= max_strike):
#             continue
#         
#         if option_type in ["CALL", "C"]:
#             calls_volume += volume
#             calls_count += 1
#         elif option_type in ["PUT", "P"]:
#             puts_volume += volume
#             puts_count += 1
#     
#     tracker = get_volume_tracker()
#     calls_delta, puts_delta = tracker.calculate_deltas(calls_volume, puts_volume)
#     
#     result = {
#         "timestamp": datetime.utcnow(),
#         "spy_price": round(spy_price, 2),
#         "calls_volume_atm": int(calls_volume),
#         "puts_volume_atm": int(puts_volume),
#         "atm_range": {
#             "min_strike": float(min_strike),
#             "max_strike": float(max_strike)
#         },
#         "strikes_count": {
#             "calls": int(calls_count),
#             "puts": int(puts_count)
#         },
#         "calls_volume_delta": int(calls_delta),
#         "puts_volume_delta": int(puts_delta)
#     }
#     
#     logger.info(f"✅ Agregados ATM: C={calls_volume} (+{calls_delta}), P={puts_volume} (+{puts_delta})")
#     
#     return result

# Instancia global del tracker
_volume_tracker = None

def get_volume_tracker():
    """Obtiene instancia singleton del VolumeTracker."""
    global _volume_tracker
    if _volume_tracker is None:
        from volume_tracker import VolumeTracker
        _volume_tracker = VolumeTracker()
    return _volume_tracker

class FlowAggregator:
    """
    Agrupa signed premium en buckets de 1 segundo para suavizar gráficas.
    """
    def __init__(self):
        self.current_second = int(time.time())
        self.bucket_call = 0.0
        self.bucket_put = 0.0
        
    def add_signed_flow(self, call_flow: float, put_flow: float) -> dict:
        """
        Acumula flows en el bucket actual.
        
        Returns:
            dict con timestamp y flows acumulados cuando cierra el segundo,
            None si aún está en el mismo segundo
        """
        now = int(time.time())
        
        if now != self.current_second:
            # Cerrar bucket anterior
            result = {
                "timestamp": self.current_second,
                "bucket_call": self.bucket_call,
                "bucket_put": self.bucket_put
            }
            
            # Reset para nuevo segundo
            self.bucket_call = 0.0
            self.bucket_put = 0.0
            self.current_second = now
            
            logger.debug(f"Bucket cerrado: {result['timestamp']} | C={result['bucket_call']:.2f} P={result['bucket_put']:.2f}")
            return result
        
        # Seguimos en el mismo segundo, acumular
        self.bucket_call += call_flow
        self.bucket_put += put_flow
        return None


# Instancia global del aggregator
_flow_aggregator = None

def get_flow_aggregator():
    """Obtiene instancia singleton del FlowAggregator."""
    global _flow_aggregator
    if _flow_aggregator is None:
        _flow_aggregator = FlowAggregator()
    return _flow_aggregator