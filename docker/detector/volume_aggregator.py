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
    Agrega volúmenes de CALLs y PUTs en rango ATM.
    
    Args:
        options_data: Lista de opciones con estructura:
            [{"strike": 587.5, "option_type": "CALL", "volume": 1250, ...}, ...]
        spy_price: Precio actual de SPY
    
    Returns:
        {
            "timestamp": "2026-02-02T14:30:00Z",
            "spy_price": 587.23,
            "calls_volume_atm": 45000000,
            "puts_volume_atm": -38000000,
            "atm_range": {"min_strike": 575.49, "max_strike": 598.97},
            "strikes_count": {"calls": 12, "puts": 11}
        }
    """
    min_strike, max_strike = calculate_atm_range(spy_price)
    
    calls_volume = 0
    puts_volume = 0
    calls_count = 0
    puts_count = 0
    
    for option in options_data:
        strike = option.get("strike")
        option_type = option.get("option_type", "").upper()
        volume = option.get("volume", 0)
        
        # Filtrar solo strikes en rango ATM
        if not (min_strike <= strike <= max_strike):
            continue
        
        if option_type == "CALL":
            calls_volume += volume
            calls_count += 1
        elif option_type == "PUT":
            puts_volume += volume
            puts_count += 1
    
    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "spy_price": round(spy_price, 2),
        "calls_volume_atm": calls_volume,
        "puts_volume_atm": puts_volume,
        "atm_range": {
            "min_strike": min_strike,
            "max_strike": max_strike
        },
        "strikes_count": {
            "calls": calls_count,
            "puts": puts_count
        }
    }
    tracker = get_volume_tracker()
    calls_delta, puts_delta = tracker.calculate_deltas(calls_volume, puts_volume)
    result["calls_volume_delta"] = calls_delta
    result["puts_volume_delta"] = puts_delta
    
    logger.info(f"Agregados ATM: CALLS={calls_volume:,} ({calls_count} strikes), "
                f"PUTS={puts_volume:,} ({puts_count} strikes), "
                f"SPY={spy_price:.2f}, Range=[{min_strike}-{max_strike}]")
    
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
