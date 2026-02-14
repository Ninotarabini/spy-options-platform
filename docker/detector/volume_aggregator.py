"""
Volume Aggregator - Agrega volúmenes ATM para detectar tendencias de mercado.
Complementa anomaly_algo.py (individual strikes) con análisis agregado.
"""
from datetime import datetime
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


def calculate_atm_range(spy_price: float, tolerance_pct: float = 2.0) -> Tuple[float, float]:
    """
    Calcula rango ATM ±2% del precio SPY actual.
    
    Args:
        spy_price: Precio actual de SPY
        tolerance_pct: Porcentaje de tolerancia (default 2%)
    
    Returns:
        (min_strike, max_strike)
    
    Ejemplo:
        SPY = 587.23 → ATM range = (575.49, 598.97)
    """
    min_strike = spy_price * (1 - tolerance_pct / 100)
    max_strike = spy_price * (1 + tolerance_pct / 100)
    return round(min_strike, 2), round(max_strike, 2)

def aggregate_atm_volumes(options_data: List[dict], spy_price: float) -> Dict:
    """
    Agrega volúmenes ATM y asegura compatibilidad con VolumeSnapshot model.
    """
    min_strike, max_strike = calculate_atm_range(spy_price)
    
    calls_volume = 0
    puts_volume = 0
    calls_count = 0
    puts_count = 0
    
    for option in options_data:
        strike = option.get("strike")
        # Aseguramos que detecte tanto "C" como "CALL"
        option_type = option.get("option_type", "").upper()
        volume = option.get("volume", 0)
        
        if not (min_strike <= strike <= max_strike):
            continue
        
        if option_type in ["CALL", "C"]:
            calls_volume += volume
            calls_count += 1
        elif option_type in ["PUT", "P"]:
            puts_volume += volume
            puts_count += 1
    
    # 2. Obtener deltas del tracker
    tracker = get_volume_tracker()
    calls_delta, puts_delta = tracker.calculate_deltas(calls_volume, puts_volume)
    
    # 3. Construir el diccionario FINAL (Mapeo exacto a VolumeSnapshot)
    result = {
        "timestamp": datetime.utcnow(), # Pydantic prefiere objeto datetime o string ISO
        "spy_price": round(spy_price, 2),
        "calls_volume_atm": int(calls_volume),
        "puts_volume_atm": int(puts_volume),
        "atm_range": {
            "min_strike": float(min_strike),
            "max_strike": float(max_strike)
        },
        "strikes_count": {
            "calls": int(calls_count),
            "puts": int(puts_count)
        },
        "calls_volume_delta": int(calls_delta),
        "puts_volume_delta": int(puts_delta)
    }
    
    logger.info(f"✅ Agregados ATM: C={calls_volume} (+{calls_delta}), P={puts_volume} (+{puts_delta})")
    
    return result

# Instancia global del tracker
_volume_tracker = None

def get_volume_tracker():
    """Obtiene instancia singleton del VolumeTracker."""
    global _volume_tracker
    if _volume_tracker is None:
        from volume_tracker import VolumeTracker
        _volume_tracker = VolumeTracker()
    return _volume_tracker
