"""
Volume Tracker - Calcula deltas de volumen entre scans.
"""
import logging

logger = logging.getLogger(__name__)

class VolumeTracker:
    """Rastrea volumen entre scans para calcular deltas (incrementos)."""
    
    def __init__(self):
        self.prev_calls_volume = 0
        self.prev_puts_volume = 0
        self.first_scan = True
        
    def calculate_deltas(self, calls_volume: int, puts_volume: int) -> tuple:
        """Calcula la fluctuación (actividad fresca) desde el último scan."""
        if self.first_scan:
            # En el primer scan la fluctuación es 0 hasta tener una referencia
            calls_delta = 0 
            puts_delta = 0
            self.first_scan = False
        else:
            # Usamos max(0, ...) para evitar deltas negativos si el rango ATM cambia
            calls_delta = max(0, calls_volume - self.prev_calls_volume)
            puts_delta = max(0, puts_volume - self.prev_puts_volume)
            
        self.prev_calls_volume = calls_volume
        self.prev_puts_volume = puts_volume
        
        return calls_delta, puts_delta


        if self.first_scan:
            calls_delta = calls_volume
            puts_delta = puts_volume
            self.first_scan = False
            logger.info("First scan: initializing volume tracker")
        else:
            calls_delta = calls_volume - self.prev_calls_volume
            puts_delta = puts_volume - self.prev_puts_volume
            
        # Actualizar para próximo scan
        self.prev_calls_volume = calls_volume
        self.prev_puts_volume = puts_volume
        
        logger.info(f"Volume deltas: CALLS +{calls_delta:,}, PUTS +{puts_delta:,}")
        
        return calls_delta, puts_delta
