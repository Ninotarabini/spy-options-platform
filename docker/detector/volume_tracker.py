"""
Volume Tracker - Calcula deltas de volumen entre scans.
"""
import logging
logger = logging.getLogger(__name__)

class VolumeTracker:
    def __init__(self):
        self.prev_calls_volume = 0
        self.prev_puts_volume = 0
        self.first_scan = True
        
    def calculate_deltas(self, calls_volume: int, puts_volume: int) -> tuple:
        if self.first_scan:
            # En la primera ejecución, el delta es el volumen actual
            calls_delta = 0 
            puts_delta = 0
            self.first_scan = False
        else:
            calls_delta = max(0, calls_volume - self.prev_calls_volume)
            puts_delta = max(0, puts_volume - self.prev_puts_volume)
            
        self.prev_calls_volume = calls_volume
        self.prev_puts_volume = puts_volume
        
        logger.info(f"Deltas calculados: C+{calls_delta} | P+{puts_delta}")
        return calls_delta, puts_delta
