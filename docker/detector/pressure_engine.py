"""
Pressure Engine - Motor institucional de presión de mercado SPY 0DTE.

Calcula métricas institucionales basadas en flujo de opciones:
- DPI (Directional Pressure Index): presión direccional -1 a +1
- DRI (Dealer Regime Index): régimen gamma -1 a +1
- MRI (Magnet Risk Index): riesgo de pinning 0 a 1
- Magnetic Strikes: Top 5 strikes con mayor magnetismo

Arquitectura:
    IBKR → detector.py → pressure_engine.calculate() → Backend → SignalR → Frontend

Referencias:
    Dashboard_presión_flujo_opciones.txt (fórmulas institucionales)
    volume_tracker.py (patrón arquitectónico)
"""
import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class PressureEngine:
    """
    Motor institucional de presión de mercado.
    
    Implementa análisis de flujo institucional para detectar:
    - Presión direccional de dealers
    - Régimen gamma (aceleración vs frenado)
    - Riesgo de pinning magnético
    - Strikes dominantes fuera ATM
    """
    
    def __init__(self, lookback_seconds: int = 300):
        """
        Inicializa el motor de presión.
        
        Args:
            lookback_seconds: Ventana temporal para rolling metrics (default 5min = 300s)
        """
        self.lookback_seconds = lookback_seconds
        
        # Rolling windows para métricas temporales
        self.flow_history = deque(maxlen=lookback_seconds)  # [(timestamp, call_flow, put_flow, spy_price), ...]
        self.price_history = deque(maxlen=60)  # Últimos 60s para detectar tendencia
        
        # Estado interno
        self.last_dpi = 0.0
        self.last_dri = 0.0
        self.last_mri = 0.0
        
        logger.info(f"PressureEngine initialized with lookback={lookback_seconds}s")
    
    def calculate_pressure_metrics(
        self,
        options_data: List[Dict],
        spy_price: float,
        cum_call_flow: float,
        cum_put_flow: float
    ) -> Dict:
        """
        Calcula las 4 métricas institucionales principales.
        
        Args:
            options_data: Lista de contratos con keys: strike, option_type, bid, ask, volume, mid, last
            spy_price: Precio actual SPY underlying
            cum_call_flow: Flujo acumulado calls (signed premium)
            cum_put_flow: Flujo acumulado puts (signed premium)
            
        Returns:
            {
                'timestamp': int,
                'directional_pressure': float,     # -1 a +1
                'dealer_regime': float,            # -1 a +1 (short gamma: -1, long gamma: +1)
                'magnet_risk': float,              # 0 a 1
                'magnetic_strikes': List[Dict],    # Top 5: [{strike, type, score, distance}, ...]
                'atm_pressure': float,             # Presión en ATM
                'net_flow': float,                 # call_flow - put_flow
                'gamma_weighted_flow': float       # GWF
            }
        """
        timestamp = int(datetime.utcnow().timestamp())
        
        # Validaciones defensivas
        if not options_data:
            logger.warning("No options data provided to PressureEngine")
            return self._empty_metrics(timestamp)
        
        if spy_price <= 0:
            logger.error(f"Invalid spy_price: {spy_price}")
            return self._empty_metrics(timestamp)
        
        # Actualizar historial
        self.flow_history.append((timestamp, cum_call_flow, cum_put_flow, spy_price))
        self.price_history.append(spy_price)
        
        try:
            # Calcular ATM strike
            atm_strike = round(spy_price)
            
            # 1. Calcular métricas base
            net_flow = cum_call_flow - cum_put_flow
            
            # 2. Calcular Gamma Weighted Flow (GWF)
            gamma_weighted_flow = self._calculate_gamma_weighted_flow(
                options_data, spy_price, atm_strike
            )
            
            # 3. Calcular ATM Pressure
            atm_pressure = self._calculate_atm_pressure(
                options_data, spy_price, atm_strike
            )
            
            # 4. Calcular DPI (Directional Pressure Index)
            dpi = self._calculate_dpi(
                net_flow, gamma_weighted_flow, atm_pressure
            )
            
            # 5. Calcular DRI (Dealer Regime Index)
            dri = self._calculate_dri(
                gamma_weighted_flow, spy_price
            )
            
            # 6. Calcular MRI (Magnet Risk Index)
            mri = self._calculate_mri(
                options_data, spy_price, atm_strike
            )
            
            # 7. Detectar Magnetic Strikes (Top 5)
            magnetic_strikes = self._find_magnetic_strikes(
                options_data, spy_price, atm_strike
            )
            
            # Guardar estado
            self.last_dpi = dpi
            self.last_dri = dri
            self.last_mri = mri
            
            result = {
                'timestamp': timestamp,
                'directional_pressure': round(dpi, 3),
                'dealer_regime': round(dri, 3),
                'magnet_risk': round(mri, 3),
                'magnetic_strikes': magnetic_strikes,
                'atm_pressure': round(atm_pressure, 3),
                'net_flow': round(net_flow, 2),
                'gamma_weighted_flow': round(gamma_weighted_flow, 2)
            }
            
            logger.info(
                f"Pressure metrics: DPI={dpi:.3f}, DRI={dri:.3f}, MRI={mri:.3f}, "
                f"ATM_pressure={atm_pressure:.3f}, GWF={gamma_weighted_flow:.2f}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating pressure metrics: {e}", exc_info=True)
            return self._empty_metrics(timestamp)
    
    def _calculate_gamma_weighted_flow(
        self, 
        options_data: List[Dict], 
        spy_price: float,
        atm_strike: float
    ) -> float:
        """
        Calcula flujo ponderado por gamma (institucional).
        
        Formula: GWF = Σ(delta_flow × gamma_proxy)
        gamma_proxy = 1 / (|strike - spot| + 0.25)
        
        Args:
            options_data: Lista de contratos
            spy_price: Precio SPY
            atm_strike: Strike ATM calculado
            
        Returns:
            Gamma weighted flow (puede ser negativo)
        """
        gwf = 0.0
        
        for option in options_data:
            try:
                strike = option.get('strike', 0)
                option_type = option.get('option_type', '').upper()
                volume = option.get('volume', 0)
                last = option.get('last', 0)
                
                if not strike or not last or volume <= 0:
                    continue
                
                # Gamma proxy simple (institucional)
                distance = abs(strike - spy_price)
                gamma_proxy = 1.0 / (distance + 0.25)
                
                # Delta proxy aproximado
                if option_type == 'C':
                    delta = 0.5 if strike == atm_strike else (0.7 if strike < atm_strike else 0.3)
                else:  # PUT
                    delta = -0.5 if strike == atm_strike else (-0.7 if strike > atm_strike else -0.3)
                
                # Flujo direccional (asumimos compra si hay volumen)
                flow = volume * last * 100 * delta
                
                # Ponderar por gamma
                gwf += flow * gamma_proxy
                
            except Exception as e:
                logger.debug(f"Error processing option for GWF: {e}")
                continue
        
        return gwf
    
    def _calculate_atm_pressure(
        self,
        options_data: List[Dict],
        spy_price: float,
        atm_strike: float
    ) -> float:
        """
        Calcula presión concentrada en strikes ATM.
        
        Args:
            options_data: Lista de contratos
            spy_price: Precio SPY
            atm_strike: Strike ATM
            
        Returns:
            ATM pressure normalizado [-1, 1]
        """
        atm_call_flow = 0.0
        atm_put_flow = 0.0
        
        # Considerar ±1 strike como ATM
        atm_range = [atm_strike - 1, atm_strike, atm_strike + 1]
        
        for option in options_data:
            try:
                strike = option.get('strike', 0)
                if strike not in atm_range:
                    continue
                
                option_type = option.get('option_type', '').upper()
                volume = option.get('volume', 0)
                last = option.get('last', 0)
                
                if not last or volume <= 0:
                    continue
                
                flow = volume * last * 100
                
                if option_type == 'C':
                    atm_call_flow += flow
                else:
                    atm_put_flow += flow
                    
            except Exception as e:
                logger.debug(f"Error processing ATM option: {e}")
                continue
        
        # Normalizar
        total = atm_call_flow + atm_put_flow
        if total == 0:
            return 0.0
        
        net = atm_call_flow - atm_put_flow
        return np.clip(net / total, -1.0, 1.0)
    
    def _calculate_dpi(
        self,
        net_flow: float,
        gamma_weighted_flow: float,
        atm_pressure: float
    ) -> float:
        """
        Calcula Directional Pressure Index (institucional).
        
        Formula:
            DPI = (net_flow_norm * 0.4) + (gwf_norm * 0.4) + (atm_pressure * 0.2)
        
        Args:
            net_flow: Flujo neto (calls - puts)
            gamma_weighted_flow: GWF calculado
            atm_pressure: Presión ATM [-1, 1]
            
        Returns:
            DPI en rango [-1, 1]
        """
        # Normalizar net_flow (simple scaling)
        # Asumimos rango típico ±10M para 0DTE SPY
        net_flow_norm = np.clip(net_flow / 10_000_000, -1.0, 1.0)
        
        # Normalizar GWF (similar)
        gwf_norm = np.clip(gamma_weighted_flow / 5_000_000, -1.0, 1.0)
        
        # Combinar con pesos institucionales
        dpi = (net_flow_norm * 0.4) + (gwf_norm * 0.4) + (atm_pressure * 0.2)
        
        return np.clip(dpi, -1.0, 1.0)
    
    def _calculate_dri(
        self,
        gamma_weighted_flow: float,
        spy_price: float
    ) -> float:
        """
        Calcula Dealer Regime Index.
        
        Detecta si dealers están:
        - SHORT GAMMA (-1): amplifican movimientos
        - LONG GAMMA (+1): neutralizan movimientos
        
        Proxy: correlación entre GWF y movimiento precio reciente
        
        Args:
            gamma_weighted_flow: GWF actual
            spy_price: Precio actual
            
        Returns:
            DRI en rango [-1, 1]
        """
        # Necesitamos historial mínimo
        if len(self.price_history) < 10 or len(self.flow_history) < 10:
            return 0.0
        
        try:
            # Calcular movimiento precio reciente (últimos 30s)
            recent_prices = list(self.price_history)[-30:]
            price_change = recent_prices[-1] - recent_prices[0]
            
            # Si GWF alto y precio sigue flujo → SHORT GAMMA
            gwf_threshold = 1_000_000
            
            if abs(gamma_weighted_flow) > gwf_threshold:
                # Correlación simple: mismo signo → short gamma
                if (gamma_weighted_flow > 0 and price_change > 0) or \
                   (gamma_weighted_flow < 0 and price_change < 0):
                    return -1.0  # SHORT GAMMA (amplifican)
                else:
                    return 1.0   # LONG GAMMA (neutralizan)
            
            # Flujo bajo → régimen neutral
            return 0.0
            
        except Exception as e:
            logger.debug(f"Error calculating DRI: {e}")
            return 0.0
    
    def _calculate_mri(
        self,
        options_data: List[Dict],
        spy_price: float,
        atm_strike: float
    ) -> float:
        """
        Calcula Magnet Risk Index.
        
        Formula:
            magnetism_score = OI × gamma_proxy × volumen_reciente
            MRI = max(magnetism_scores) normalizado [0, 1]
        
        Args:
            options_data: Lista de contratos
            spy_price: Precio SPY
            atm_strike: Strike ATM
            
        Returns:
            MRI en rango [0, 1]
        """
        max_magnetism = 0.0
        
        for option in options_data:
            try:
                strike = option.get('strike', 0)
                volume = option.get('volume', 0)
                open_interest = option.get('open_interest', 0)  # Puede no estar disponible
                
                if not strike or volume <= 0:
                    continue
                
                # Gamma proxy
                distance = abs(strike - spy_price)
                gamma_proxy = 1.0 / (distance + 0.25)
                
                # Magnetism score (sin OI si no disponible)
                oi_factor = max(open_interest, volume)  # Fallback a volume
                magnetism = oi_factor * gamma_proxy * volume
                
                max_magnetism = max(max_magnetism, magnetism)
                
            except Exception as e:
                logger.debug(f"Error processing MRI option: {e}")
                continue
        
        # Normalizar (asumimos max típico ~1M para SPY 0DTE)
        mri = min(max_magnetism / 1_000_000, 1.0)
        
        return round(mri, 3)
    
    def _find_magnetic_strikes(
        self,
        options_data: List[Dict],
        spy_price: float,
        atm_strike: float
    ) -> List[Dict]:
        """
        Detecta strikes magnéticos FUERA del ATM con volumen irregular.
        
        Criterio institucional:
        - Strikes fuera de ±2 del ATM
        - Alto magnetism score
        - Top 5
        
        Args:
            options_data: Lista de contratos
            spy_price: Precio SPY
            atm_strike: Strike ATM
            
        Returns:
            Lista de Top 5 strikes: [
                {
                    'strike': float,
                    'type': str,
                    'score': float,
                    'distance': float,
                    'volume': int
                }, ...
            ]
        """
        magnetic_candidates = []
        
        # Rango ATM a excluir (±2 strikes)
        atm_exclusion_range = set(range(atm_strike - 2, atm_strike + 3))
        
        for option in options_data:
            try:
                strike = option.get('strike', 0)
                
                # Filtrar strikes ATM
                if strike in atm_exclusion_range:
                    continue
                
                option_type = option.get('option_type', '').upper()
                volume = option.get('volume', 0)
                open_interest = option.get('open_interest', 0)
                
                if volume <= 0:
                    continue
                
                # Gamma proxy
                distance = abs(strike - spy_price)
                gamma_proxy = 1.0 / (distance + 0.25)
                
                # Magnetism score
                oi_factor = max(open_interest, volume)
                magnetism_score = oi_factor * gamma_proxy * volume
                
                magnetic_candidates.append({
                    'strike': float(strike),
                    'type': option_type,
                    'score': round(magnetism_score, 2),
                    'distance': round(distance, 2),
                    'volume': int(volume)
                })
                
            except Exception as e:
                logger.debug(f"Error processing magnetic strike: {e}")
                continue
        
        # Ordenar por score descendente y tomar Top 5
        magnetic_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        return magnetic_candidates[:5]
    
    def _empty_metrics(self, timestamp: int) -> Dict:
        """
        Retorna métricas vacías en caso de error.
        
        Args:
            timestamp: Unix timestamp actual
            
        Returns:
            Dict con valores default
        """
        return {
            'timestamp': timestamp,
            'directional_pressure': 0.0,
            'dealer_regime': 0.0,
            'magnet_risk': 0.0,
            'magnetic_strikes': [],
            'atm_pressure': 0.0,
            'net_flow': 0.0,
            'gamma_weighted_flow': 0.0
        }


# ========================================
# SINGLETON PATTERN (patrón volume_aggregator.py)
# ========================================

_pressure_engine = None


def get_pressure_engine() -> PressureEngine:
    """
    Obtiene instancia singleton del PressureEngine.
    
    Returns:
        Instancia global de PressureEngine
    """
    global _pressure_engine
    if _pressure_engine is None:
        _pressure_engine = PressureEngine(lookback_seconds=300)
        logger.info("PressureEngine singleton created")
    return _pressure_engine
