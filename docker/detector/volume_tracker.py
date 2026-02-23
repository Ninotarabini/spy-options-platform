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
        
        # Nuevo: tracking por contrato individual para signed premium
        self.prev_volumes = {}  # {contract_id: volume}
        self.cum_call_flow = 0.0
        self.cum_put_flow = 0.0
        
    # COMENTADO: Método antiguo (agregación ATM total)
    # def calculate_deltas(self, calls_volume: int, puts_volume: int) -> tuple:
    #     if self.first_scan:
    #         calls_delta = 0 
    #         puts_delta = 0
    #         self.first_scan = False
    #     else:
    #         calls_delta = max(0, calls_volume - self.prev_calls_volume)
    #         puts_delta = max(0, puts_volume - self.prev_puts_volume)
    #     
    #     self.prev_calls_volume = calls_volume
    #     self.prev_puts_volume = puts_volume
    #     
    #     logger.info(f"Deltas calculados: C+{calls_delta} | P+{puts_delta}")
    #     return calls_delta, puts_delta
    
    def process_option_tick(self, option_data: dict) -> tuple:
        """
        Calcula signed premium por contrato individual.
        
        Args:
            option_data: Dict con strike, option_type, volume, bid, ask, last
            
        Returns:
            (call_flow, put_flow): Flujo firmado para este tick
        """
        contract_id = f"{option_data['strike']}_{option_data['option_type']}"
        
        current_volume = option_data.get("volume", 0)
        prev_volume = self.prev_volumes.get(contract_id, 0)
        
        delta = current_volume - prev_volume
        if delta <= 0:
            self.prev_volumes[contract_id] = current_volume
            return 0.0, 0.0
        
        self.prev_volumes[contract_id] = current_volume
        
        bid = option_data.get("bid", 0)
        ask = option_data.get("ask", 0)
        last = option_data.get("last", 0)
        
        if not last or not bid or not ask:
            return 0.0, 0.0
        
        # Clasificación de agresión
        if last >= ask:
            sign = 1  # Compra agresiva
        elif last <= bid:
            sign = -1  # Venta agresiva
        else:
            sign = 0  # Neutral (no contar)
        
        # Calcular premium (delta * precio * multiplicador)
        premium = delta * last * 100
        signed_premium = premium * sign
        
        # Acumular en el bucket correspondiente
        if option_data["option_type"] == "C":
            self.cum_call_flow += signed_premium
            return signed_premium, 0.0
        else:
            self.cum_put_flow += signed_premium
            return 0.0, signed_premium