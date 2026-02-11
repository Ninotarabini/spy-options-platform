"""Anomaly detection algorithm for SPY options pricing.
Detects pricing anomalies based on expected pricing curves.
"""
import logging
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from scipy import stats

from config import settings


logger = logging.getLogger(__name__)


def detect_anomalies(options_data: List[Dict[str, Any]], spy_price: float) -> List[Dict[str, Any]]:
    """Detect pricing anomalies in options data.
    
    Args:
        options_data: List of option data dicts (strike, bid, ask, etc)
        spy_price: Current SPY price for moneyness calculation
        
    Returns:
        list: Detected anomalies with deviation metrics
    """
    if not options_data:
        logger.warning("No options data provided for anomaly detection")
        return []
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(options_data)
    
    # Separate calls and puts
    calls = df[df['option_type'] == 'C'].copy()
    puts = df[df['option_type'] == 'P'].copy()
    
    anomalies = []
    
    # Detect anomalies in calls
    if len(calls) > 3:  # Need at least 3 points for trend
        call_anomalies = _detect_in_series(calls, spy_price, 'C')
        anomalies.extend(call_anomalies)
    
    # Detect anomalies in puts
    if len(puts) > 3:
        put_anomalies = _detect_in_series(puts, spy_price, 'P')
        anomalies.extend(put_anomalies)
    
    logger.info(f"Detected {len(anomalies)} anomalies (threshold: {settings.anomaly_threshold})")
    return anomalies


def _detect_in_series(df: pd.DataFrame, spy_price: float, right: str) -> List[Dict[str, Any]]:
    """Detect anomalies in a single option series (calls or puts).
    
    Args:
        df: DataFrame with option data (must have strike, mid, volume)
        spy_price: Current SPY price
        right: 'C' for calls, 'P' for puts
        
    Returns:
        list: Anomalies detected in this series
    """
    df = df.sort_values('strike').copy()
    
    # Calculate moneyness (distance from ATM)
    df['moneyness'] = (df['strike'] - spy_price) / spy_price
    
    # Calculate price change between consecutive strikes
    df['price_change_pct'] = df['mid'].pct_change().abs() * 100
    
    # Expected behavior: price decreases as we move away from ATM
    # For calls: price decreases as strike increases
    # For puts: price decreases as strike decreases
    
    # Calculate z-scores for price changes
    if len(df) > 3:
        mean_change = df['price_change_pct'].mean()
        std_change = df['price_change_pct'].std()
        
        if std_change > 0:
            df['z_score'] = (df['price_change_pct'] - mean_change) / std_change
        else:
            df['z_score'] = 0
    else:
        df['z_score'] = 0
    
    # Detect anomalies: z-score > threshold (default 0.5)
    anomalies = []
    threshold = settings.anomaly_threshold
    
    for idx, row in df.iterrows():
        if abs(row['z_score']) > threshold and row['price_change_pct'] > 0:
            expected_price = calculate_expected_price(float(row['strike']), spy_price, right)
            anomaly = {
                'timestamp': pd.Timestamp.now().isoformat(),
                'strike': float(row['strike']),
                'right': right,
                'price': float(row['mid']),
                'expected_price': float(expected_price),
                'bid': float(row['bid']),
                'ask': float(row['ask']),
                'volume': int(row['volume']),
                'open_interest': 0,
                'spy_price': float(spy_price),
                'moneyness': float(row['moneyness']),
                'deviation_pct': float(row['price_change_pct']),
                'z_score': float(row['z_score']),
                'severity': _calculate_severity(row['z_score'], row['price_change_pct'])
            }
            anomalies.append(anomaly)
            logger.info(f"Anomaly: {right} ${row['strike']:.0f} - "
                       f"deviation={row['price_change_pct']:.2f}%, "
                       f"z_score={row['z_score']:.2f}")
    
    return anomalies


def _calculate_severity(z_score: float, deviation_pct: float) -> str:
    """Calculate anomaly severity based on z-score and deviation.
    
    Args:
        z_score: Statistical z-score
        deviation_pct: Percentage deviation from expected
        
    Returns:
        str: 'LOW', 'MEDIUM', or 'HIGH'
    """
    abs_z = abs(z_score)
    
    if abs_z > 2.0 or deviation_pct > 50:
        return 'HIGH'
    elif abs_z > 1.0 or deviation_pct > 20:
        return 'MEDIUM'
    else:
        return 'LOW'


def calculate_expected_price(strike: float, spy_price: float, right: str) -> float:
    """Calculate expected option price (simple heuristic).
    
    This is a placeholder for more sophisticated pricing models (Black-Scholes, etc).
    Currently uses simple linear decay from ATM.
    
    Args:
        strike: Option strike price
        spy_price: Current SPY price
        right: 'C' for call, 'P' for put
        
    Returns:
        float: Expected option price
    """
    moneyness = abs(strike - spy_price) / spy_price
    
    # Simple linear decay (placeholder)
    if right == 'C':
        if strike <= spy_price:  # ITM
            intrinsic = spy_price - strike
            time_value = 2.0 * (1 - moneyness * 10)
            return max(intrinsic + time_value, intrinsic)
        else:  # OTM
            return max(2.0 * (1 - moneyness * 10), 0.01)
    else:  # Put
        if strike >= spy_price:  # ITM
            intrinsic = strike - spy_price
            time_value = 2.0 * (1 - moneyness * 10)
            return max(intrinsic + time_value, intrinsic)
        else:  # OTM
            return max(2.0 * (1 - moneyness * 10), 0.01)
