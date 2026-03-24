"""
Gamma Exposure Engine - Industry-standard SPY 0DTE Gamma Metrics.

Implements institutional gamma exposure analysis based on options flow:
- Net GEX (Net Gamma Exposure): directional gamma pressure 0 to 100 (0=bearish, 50=neutral, 100=bullish)
- Gamma Regime: dealer positioning 0 to 100 (0=SHORT GAMMA, 50=NEUTRAL, 100=LONG GAMMA)
- Pinning Risk: strike magnetism concentration 0 to 100 (0=no pinning, 100=maximum pinning)
- Gamma Walls: Top 5 strikes with highest gamma concentration

Architecture:
    IBKR → detector.py → gamma_engine.calculate() → Backend → SignalR → Frontend

Academic References:
    - SpotGamma NetGEX methodology
    - SqueezeMetrics Dealer Positioning
    - Barbon & Buraschi (2021) "Gamma Fragility"
    - Cboe Volatility Insights (2023)
    
Code Pattern:
    volume_tracker.py (architectural reference)
"""
import logging
import math
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class GammaExposureEngine:
    """
    Industry-standard Gamma Exposure Engine.
    
    Implements institutional gamma exposure analysis to detect:
    - Net directional gamma pressure (Net GEX)
    - Dealer gamma regime (long vs short gamma positioning)
    - Strike pinning risk (magnetic price behavior)
    - Gamma walls (dominant strikes outside ATM)
    """
    
    def __init__(self, lookback_seconds: int = 300):
        """
        Initializes the Gamma Exposure Engine.
        
        Args:
            lookback_seconds: Time window for rolling metrics (default 5min = 300s)
        """
        self.lookback_seconds = lookback_seconds
        
        # Rolling windows for temporal metrics
        self.flow_history = deque(maxlen=lookback_seconds)  # [(timestamp, call_flow, put_flow, spy_price), ...]
        self.price_history = deque(maxlen=60)  # Last 60s for trend detection
        
        # Internal state (legacy field names for backward compatibility)
        self.last_net_gex = 0.0
        self.last_gamma_regime = 0.0
        self.last_pinning_risk = 0.0
        
        logger.info(f"GammaExposureEngine initialized with lookback={lookback_seconds}s")
    
    def _sanitize_float(self, value: float, default: float = 0.0) -> float:
        """
        Sanitizes float values to prevent inf/NaN from breaking JSON serialization.
        
        Critical fix for: "Out of range float values are not JSON compliant" error.
        np.clip() does NOT sanitize inf/NaN — must use math.isinf() explicitly.
        
        Args:
            value: Float value to sanitize
            default: Default value if inf/NaN detected (default: 0.0)
            
        Returns:
            Sanitized float value
        """
        if math.isinf(value) or math.isnan(value):
            logger.warning(f"⚠️ Sanitized invalid float: {value} → {default}")
            return default
        return value
    
    def calculate_gamma_metrics(
        self,
        options_data: List[Dict],
        spy_price: float,
        cum_call_flow: float,
        cum_put_flow: float
    ) -> Dict:
        """
        Calculates industry-standard gamma exposure metrics.
        
        Args:
            options_data: List of contracts with keys: strike, option_type, bid, ask, volume, mid, last
            spy_price: Current SPY underlying price
            cum_call_flow: Cumulative calls flow (signed premium)
            cum_put_flow: Cumulative puts flow (signed premium)
            
        Returns:
            {
                'timestamp': int,
                'net_gex': float,              # 0 to 100 (Net Gamma Exposure: 0=bearish, 50=neutral, 100=bullish)
                'gamma_regime': float,         # 0 to 100 (0=SHORT GAMMA, 50=NEUTRAL, 100=LONG GAMMA)
                'pinning_risk': float,         # 0 to 100 (Strike pinning risk: 0=no pinning, 100=maximum)
                'gamma_walls': List[Dict],     # Top 5: [{strike, type, gamma, distance}, ...]
                'atm_flow': float,             # ATM flow pressure
                'net_flow': float,             # call_flow - put_flow
                'gamma_weighted_flow': float   # GWF (Gamma Weighted Flow)
            }
        """
        timestamp = int(datetime.utcnow().timestamp())
        
        # Defensive validations
        if not options_data:
            logger.warning("No options data provided to GammaExposureEngine")
            return self._empty_metrics(timestamp)
        
        if spy_price <= 0:
            logger.error(f"Invalid spy_price: {spy_price}")
            return self._empty_metrics(timestamp)
        
        # Update history
        self.flow_history.append((timestamp, cum_call_flow, cum_put_flow, spy_price))
        self.price_history.append(spy_price)
        
        try:
            # Calculate ATM strike
            atm_strike = round(spy_price)
            
            # 1. Calculate base metrics
            net_flow = cum_call_flow - cum_put_flow
            
            # 2. Calculate Gamma Weighted Flow (GWF)
            gamma_weighted_flow = self._calculate_gamma_weighted_flow(
                options_data, spy_price, atm_strike
            )
            
            # 3. Calculate ATM Flow
            atm_flow = self._calculate_atm_flow(
                options_data, spy_price, atm_strike
            )
            
            # 4. Calculate Net GEX (Net Gamma Exposure)
            net_gex = self._calculate_net_gex(
                net_flow, gamma_weighted_flow, atm_flow
            )
            
            # 5. Calculate Gamma Regime
            gamma_regime = self._calculate_gamma_regime(
                gamma_weighted_flow, spy_price
            )
            
            # 6. Calculate Pinning Risk
            pinning_risk = self._calculate_pinning_risk(
                options_data, spy_price, atm_strike
            )
            
            # 7. Detect Gamma Walls (Top 5)
            gamma_walls = self._find_gamma_walls(
                options_data, spy_price, atm_strike
            )
            
            # Save state
            self.last_net_gex = net_gex
            self.last_gamma_regime = gamma_regime
            self.last_pinning_risk = pinning_risk
            
            # ✅ CRITICAL: Sanitize ALL float values before returning
            result = {
                'timestamp': timestamp,
                'net_gex': round(self._sanitize_float(net_gex), 1),
                'gamma_regime': round(self._sanitize_float(gamma_regime), 1),
                'pinning_risk': round(self._sanitize_float(pinning_risk), 1),
                'gamma_walls': gamma_walls,
                'atm_flow': round(self._sanitize_float(atm_flow), 3),
                'net_flow': round(self._sanitize_float(net_flow), 2),
                'gamma_weighted_flow': round(self._sanitize_float(gamma_weighted_flow), 2)
            }
            
            logger.info(
                f"Gamma metrics: NetGEX={net_gex:.3f}, Regime={gamma_regime:.3f}, Pinning={pinning_risk:.3f}, "
                f"ATM_flow={atm_flow:.3f}, GWF={gamma_weighted_flow:.2f}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating gamma metrics: {e}", exc_info=True)
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
                
                # Weight by gamma (with overflow protection)
                contribution = flow * gamma_proxy
                if not math.isinf(contribution) and not math.isnan(contribution):
                    gwf += contribution
                else:
                    logger.warning(f"⚠️ Skipping inf contribution at strike {strike}")
                
            except Exception as e:
                logger.debug(f"Error processing option for GWF: {e}")
                continue
        
        return gwf
    
    def _calculate_atm_flow(
        self,
        options_data: List[Dict],
        spy_price: float,
        atm_strike: float
    ) -> float:
        """
        Calculates flow concentration at ATM strikes.
        
        Args:
            options_data: List of contracts
            spy_price: SPY price
            atm_strike: ATM strike
            
        Returns:
            ATM flow pressure normalized [-1, 1]
        """
        atm_call_flow = 0.0
        atm_put_flow = 0.0
        
        # Consider ±1 strike as ATM
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
        
        # Normalize
        total = atm_call_flow + atm_put_flow
        if total == 0:
            return 0.0
        
        net = atm_call_flow - atm_put_flow
        return np.clip(net / total, -1.0, 1.0)
    
    def _calculate_net_gex(
        self,
        net_flow: float,
        gamma_weighted_flow: float,
        atm_flow: float
    ) -> float:
        """
        Calculates Net Gamma Exposure (industry standard).
        
        Formula (SpotGamma methodology):
            Net GEX = (net_flow_norm * 0.5) + (gwf_norm * 0.5)
        
        Args:
            net_flow: Net flow (calls - puts)
            gamma_weighted_flow: Calculated GWF
            atm_flow: ATM flow pressure [-1, 1]
            
        Returns:
            Net GEX scaled to [0, 100] for dashboard visualization
            (0=maximum bearish, 50=neutral, 100=maximum bullish)
        """
        # ? CRITICAL: Sanitize FIRST (before any division)
        net_flow = self._sanitize_float(net_flow, 0.0)
        gamma_weighted_flow = self._sanitize_float(gamma_weighted_flow, 0.0)
        
        # Normalize net_flow (simple scaling)
        # Assume typical range ñ10M for 0DTE SPY
        net_flow_norm = net_flow / 10_000_000
        
        # Normalize GWF (similar)
        gwf_norm = gamma_weighted_flow / 5_000_000
        
        # Clip after sanitization
        net_flow_norm = np.clip(net_flow_norm, -1.0, 1.0)
        gwf_norm = np.clip(gwf_norm, -1.0, 1.0)
        
        # Combine with institutional weights (simplified from 3-component to 2-component)
        net_gex = (net_flow_norm * 0.5) + (gwf_norm * 0.5)
        net_gex = np.clip(net_gex, -1.0, 1.0)
        
        # Scale to 0-100 for dashboard visualization (institutional standard)
        # -1 → 0 (SHORT GAMMA), 0 → 50 (NEUTRAL), +1 → 100 (LONG GAMMA)
        net_gex_scaled = (net_gex + 1.0) * 50.0
        
        return round(net_gex_scaled, 1)
    
    def _calculate_gamma_regime(
        self,
        gamma_weighted_flow: float,
        spy_price: float
    ) -> float:
        """
        Calculates Gamma Regime (industry standard).
        
        Detects dealer positioning:
        - SHORT GAMMA (0): dealers amplify moves (selling into rallies, buying dips)
        - NEUTRAL (50): balanced positioning
        - LONG GAMMA (100): dealers stabilize price (buying rallies, selling dips)
        
        Methodology: Correlation between GWF and recent price movement
        
        Args:
            gamma_weighted_flow: Current GWF
            spy_price: Current price
            
        Returns:
            Gamma Regime scaled to [0, 100] for dashboard visualization
        """
        # Need minimum history
        if len(self.price_history) < 10 or len(self.flow_history) < 10:
            return 50.0  # Return NEUTRAL (50) when insufficient data
        
        try:
            # Calculate recent price movement (last 30s)
            recent_prices = list(self.price_history)[-30:]
            price_change = recent_prices[-1] - recent_prices[0]
            
            # If high GWF and price follows flow → SHORT GAMMA
            gwf_threshold = 1_000_000
            
            if abs(gamma_weighted_flow) > gwf_threshold:
                # Simple correlation: same sign → short gamma
                if (gamma_weighted_flow > 0 and price_change > 0) or \
                   (gamma_weighted_flow < 0 and price_change < 0):
                    return 0.0   # SHORT GAMMA (amplify) - scaled to 0
                else:
                    return 100.0  # LONG GAMMA (stabilize) - scaled to 100
            
            # Low flow → neutral regime
            return 50.0  # NEUTRAL - scaled to 50
            
        except Exception as e:
            logger.debug(f"Error calculating gamma regime: {e}")
            return 0.0
    
    def _calculate_pinning_risk(
        self,
        options_data: List[Dict],
        spy_price: float,
        atm_strike: float
    ) -> float:
        """
        Calculates Strike Pinning Risk (industry standard).
        
        Formula:
            gamma_concentration = OI × gamma_proxy × volume
            Pinning Risk = max(gamma_concentration) normalized [0, 1]
        
        Args:
            options_data: List of contracts
            spy_price: SPY price
            atm_strike: ATM strike
            
        Returns:
            Pinning Risk scaled to [0, 100] (0=no pinning, 100=maximum pinning)
        """
        max_magnetism = 0.0
        
        for option in options_data:
            try:
                strike = option.get('strike', 0)
                volume = option.get('volume', 0)
                open_interest = option.get('open_interest', 0)  # May not be available
                
                if not strike or volume <= 0:
                    continue
                
                # Gamma proxy
                distance = abs(strike - spy_price)
                gamma_proxy = 1.0 / (distance + 0.25)
                
                # Gamma concentration score (fallback to volume if OI unavailable)
                # ? Cap to prevent overflow (500k is institutional threshold)
                oi_factor = min(max(open_interest, volume), 500_000)
                magnetism = oi_factor * gamma_proxy * volume
                
                max_magnetism = max(max_magnetism, magnetism)
                
            except Exception as e:
                logger.debug(f"Error processing pinning risk option: {e}")
                continue
        
        # ✅ CRITICAL: Sanitize before normalization
        if math.isinf(max_magnetism) or math.isnan(max_magnetism):
            return 0.0
        
        # Normalize (assume typical max ~1M for SPY 0DTE)
        pinning_risk = min(max_magnetism / 1_000_000, 1.0)
        
        # Scale to 0-100 for dashboard visualization
        pinning_risk_scaled = pinning_risk * 100.0
        
        return round(pinning_risk_scaled, 1)
    
    def _find_gamma_walls(
        self,
        options_data: List[Dict],
        spy_price: float,
        atm_strike: float
    ) -> List[Dict]:
        """
        Detects gamma walls OUTSIDE ATM with high concentration.
        
        Industry criteria:
        - Strikes outside ±2 from ATM
        - High gamma concentration score
        - Top 5 by score
        
        Args:
            options_data: List of contracts
            spy_price: SPY price
            atm_strike: ATM strike
            
        Returns:
            List of Top 5 gamma walls: [
                {
                    'strike': float,
                    'type': str,
                    'score': float,
                    'distance': float,
                    'volume': int
                }, ...
            ]
        """
        gamma_wall_candidates = []
        
        # ATM exclusion range (±2 strikes)
        atm_exclusion_range = set(range(atm_strike - 2, atm_strike + 3))
        
        for option in options_data:
            try:
                strike = option.get('strike', 0)
                
                # Filter out ATM strikes
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
                
                # Gamma concentration score
                # ? Cap to prevent overflow (500k is institutional threshold)
                oi_factor = min(max(open_interest, volume), 500_000)
                gamma_concentration = oi_factor * gamma_proxy * volume
                
                gamma_wall_candidates.append({
                    'strike': float(strike),
                    'type': option_type,
                    'score': round(self._sanitize_float(gamma_concentration), 2),
                    'distance': round(self._sanitize_float(distance), 2),
                    'volume': int(volume)
                })
                
            except Exception as e:
                logger.debug(f"Error processing gamma wall: {e}")
                continue
        
        # Sort by score descending and take Top 5
        gamma_wall_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        return gamma_wall_candidates[:5]
    
    def _empty_metrics(self, timestamp: int) -> Dict:
        """
        Returns empty metrics in case of error.
        
        Args:
            timestamp: Current Unix timestamp
            
        Returns:
            Dict with default values
        """
        return {
            'timestamp': timestamp,
            'net_gex': 0.0,
            'gamma_regime': 0.0,
            'pinning_risk': 0.0,
            'gamma_walls': [],
            'atm_flow': 0.0,
            'net_flow': 0.0,
            'gamma_weighted_flow': 0.0
        }


# ========================================
# SINGLETON PATTERN (pattern: volume_aggregator.py)
# ========================================

_gamma_engine = None


def get_gamma_engine() -> GammaExposureEngine:
    """
    Gets singleton instance of GammaExposureEngine.
    
    Returns:
        Global instance of GammaExposureEngine
    """
    global _gamma_engine
    if _gamma_engine is None:
        _gamma_engine = GammaExposureEngine(lookback_seconds=300)
        logger.info("✅ GammaExposureEngine singleton created")
    return _gamma_engine


# Backward compatibility alias (DEPRECATED)
def get_pressure_engine() -> GammaExposureEngine:
    """DEPRECATED: Use get_gamma_engine() instead."""
    logger.warning("⚠️ get_pressure_engine() is deprecated, use get_gamma_engine()")
    return get_gamma_engine()
