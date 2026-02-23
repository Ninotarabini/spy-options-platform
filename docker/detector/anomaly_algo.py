"""Anomaly detection algorithm for SPY options pricing.
Detects pricing anomalies based on expected exponential decay from ATM.

This implementation uses ATM-centered analysis with exponential regression
to detect mispriced options in 0DTE SPY contracts.
"""
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from scipy import stats
from scipy.optimize import curve_fit

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
    
    # Detect anomalies in calls (need at least 5 points for stable exponential fit)
    if len(calls) >= 5:
        call_anomalies = _detect_in_series_atm_centered(calls, spy_price, 'C')
        anomalies.extend(call_anomalies)
    else:
        logger.debug(f"Insufficient CALL data points ({len(calls)}) for ATM-centered detection")
    
    # Detect anomalies in puts
    if len(puts) >= 5:
        put_anomalies = _detect_in_series_atm_centered(puts, spy_price, 'P')
        anomalies.extend(put_anomalies)
    else:
        logger.debug(f"Insufficient PUT data points ({len(puts)}) for ATM-centered detection")
    
    logger.info(f"Detected {len(anomalies)} anomalies (threshold: {settings.anomaly_threshold})")
    return anomalies


def _exponential_decay(x: np.ndarray, a: float, b: float) -> np.ndarray:
    """Exponential decay function for option pricing from ATM.
    
    Formula: price = a * exp(-b * distance_from_atm)
    
    Args:
        x: Distance from ATM strike (in number of strikes)
        a: Initial price at ATM
        b: Decay rate
        
    Returns:
        Expected prices following exponential decay
    """
    return a * np.exp(-b * x)


def _detect_in_series_atm_centered(df: pd.DataFrame, spy_price: float, right: str) -> List[Dict[str, Any]]:
    """Detect anomalies using ATM-centered exponential regression approach.
    
    This method:
    1. Identifies ATM strike (closest integer to SPY price)
    2. Orders strikes from ATM towards extremes
    3. Fits exponential decay curve to the series
    4. Detects options that are significantly cheaper than expected
    
    Args:
        df: DataFrame with option data (must have strike, mid, volume)
        spy_price: Current SPY price
        right: 'C' for calls, 'P' for puts
        
    Returns:
        list: Anomalies detected in this series
    """
    # ATM strike is the nearest integer strike to SPY price
    atm_strike = round(spy_price)
    
    # Filter and order from ATM towards extremes
    if right == 'C':
        # CALLs: Take strikes >= ATM, order ascending
        df = df[df['strike'] >= atm_strike].sort_values('strike').copy()
    else:
        # PUTs: Take strikes <= ATM, order descending (away from ATM)
        df = df[df['strike'] <= atm_strike].sort_values('strike', ascending=False).copy()
    
    # Need minimum data points for stable regression
    if len(df) < 5:
        logger.debug(f"Insufficient {right} data from ATM ({len(df)} points)")
        return []
    
    # Calculate distance from ATM (in number of strikes)
    df['distance_from_atm'] = abs(df['strike'] - atm_strike)
    
    # Pre-filter: Remove options with invalid pricing
    # - Spread too wide (> 50% of mid)
    # - Mid price <= 0
    df = df[df['mid'] > 0].copy()
    spread = df['ask'] - df['bid']
    spread_pct = spread / df['mid']
    df = df[spread_pct < 0.5].copy()  # Filter spreads > 50%
    
    if len(df) < 5:
        logger.debug(f"Insufficient {right} data after filtering spreads")
        return []
    
    # Try exponential regression approach
    try:
        anomalies = _fit_and_detect_anomalies(df, spy_price, right, atm_strike)
        return anomalies
        
    except Exception as e:
        logger.warning(f"Exponential fit failed for {right}: {e}, using fallback method")
        return _fallback_detection(df, spy_price, right)


def _fit_and_detect_anomalies(df: pd.DataFrame, spy_price: float, right: str, atm_strike: float) -> List[Dict[str, Any]]:
    """Fit exponential decay and detect deviations.
    
    Args:
        df: Preprocessed DataFrame with distance_from_atm
        spy_price: Current SPY price
        right: Option type
        atm_strike: ATM strike price
        
    Returns:
        List of detected anomalies
    """
    x_data = df['distance_from_atm'].values
    y_data = df['mid'].values
    
    # Initial parameter guess: a = price at ATM, b = 0.1 (reasonable decay rate)
    # Bounds: a must be positive, b must be positive (decay, not growth)
    initial_guess = [y_data[0], 0.1]
    bounds = ([0, 0], [np.inf, 1.0])
    
    # Fit exponential decay curve
    popt, pcov = curve_fit(
        _exponential_decay, 
        x_data, 
        y_data,
        p0=initial_guess,
        bounds=bounds,
        maxfev=5000
    )
    
    a_fit, b_fit = popt
    logger.debug(f"{right} exponential fit: a={a_fit:.3f}, b={b_fit:.3f}")
    
    # Calculate expected prices and deviations
    df['expected_price'] = _exponential_decay(df['distance_from_atm'], a_fit, b_fit)
    df['deviation_pct'] = ((df['mid'] - df['expected_price']) / df['expected_price']) * 100
    
    # Calculate z-scores for deviation detection
    if len(df) > 3:
        mean_dev = df['deviation_pct'].mean()
        std_dev = df['deviation_pct'].std()
        
        if std_dev > 0:
            df['z_score'] = (df['deviation_pct'] - mean_dev) / std_dev
        else:
            df['z_score'] = 0
    else:
        df['z_score'] = 0
    
    # Detect anomalies: Options significantly CHEAPER than expected
    # Criteria:
    # 1. Deviation < -30% (price is 30% cheaper than expected curve)
    # 2. Z-score < -threshold (statistical outlier in the cheap direction)
    
    anomalies = []
    threshold = settings.anomaly_threshold
    
    for idx, row in df.iterrows():
        # Look for bargains: cheaper than expected
        is_cheap_anomaly = row['deviation_pct'] < -10.0 and row['z_score'] < -threshold
        
        if is_cheap_anomaly:
            anomaly = {
                'timestamp': pd.Timestamp.now().isoformat(),
                'strike': float(row['strike']),
                'right': right,
                'price': float(row['mid']),
                'expected_price': float(row['expected_price']),
                'bid': float(row['bid']),
                'ask': float(row['ask']),
                'volume': int(row['volume']),
                'open_interest': 0,
                'spy_price': float(spy_price),
                'moneyness': float((row['strike'] - spy_price) / spy_price),
                'deviation_pct': float(row['deviation_pct']),
                'z_score': float(row['z_score']),
                'severity': _calculate_severity(row['z_score'], abs(row['deviation_pct']))
            }
            anomalies.append(anomaly)
            
            logger.info(
                f"💰 BARGAIN DETECTED: {right} ${row['strike']:.0f} @ ${row['mid']:.2f} "
                f"(expected ${row['expected_price']:.2f}, {row['deviation_pct']:.1f}% cheaper, "
                f"z={row['z_score']:.2f})"
            )
    
    return anomalies


def _fallback_detection(df: pd.DataFrame, spy_price: float, right: str) -> List[Dict[str, Any]]:
    """Fallback detection method using simple statistics.
    
    Used when exponential regression fails (insufficient data, bad fit, etc).
    
    Args:
        df: DataFrame with option data
        spy_price: Current SPY price
        right: Option type
        
    Returns:
        List of detected anomalies
    """
    df = df.sort_values('strike').copy()
    
    # Calculate price change between consecutive strikes
    df['price_change_pct'] = df['mid'].pct_change() * 100
    
    # For PUTs ordered descending, pct_change will be negative when price increases
    # We want to detect when price DOESN'T decrease as much as expected
    # So we look at the absolute value and check statistical outliers
    
    if len(df) > 3:
        mean_change = df['price_change_pct'].mean()
        std_change = df['price_change_pct'].std()
        
        if std_change > 0:
            df['z_score'] = (df['price_change_pct'] - mean_change) / std_change
        else:
            df['z_score'] = 0
    else:
        df['z_score'] = 0
    
    anomalies = []
    threshold = settings.anomaly_threshold
    
    # Detect statistical outliers in price decay
    for idx, row in df.iterrows():
        # Look for z-scores indicating unusual pricing
        if abs(row['z_score']) > threshold:
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
                'moneyness': float((row['strike'] - spy_price) / spy_price),
                'deviation_pct': float(row['price_change_pct']),
                'z_score': float(row['z_score']),
                'severity': _calculate_severity(row['z_score'], abs(row['price_change_pct']))
            }
            anomalies.append(anomaly)
            
            logger.info(
                f"⚠️ Fallback detection: {right} ${row['strike']:.0f} - "
                f"pct_change={row['price_change_pct']:.2f}%, z={row['z_score']:.2f}"
            )
    
    return anomalies


def _calculate_severity(z_score: float, deviation_pct: float) -> str:
    """Calculate anomaly severity based on z-score and deviation magnitude.
    
    Args:
        z_score: Statistical z-score (can be negative)
        deviation_pct: Percentage deviation (use absolute value)
        
    Returns:
        str: 'LOW', 'MEDIUM', or 'HIGH'
    """
    abs_z = abs(z_score)
    abs_dev = abs(deviation_pct)
    
    # HIGH severity: Strong statistical signal OR very large deviation
    if abs_z > 2.0 or abs_dev > 50:
        return 'HIGH'
    # MEDIUM severity: Moderate statistical signal OR significant deviation
    elif abs_z > 1.0 or abs_dev > 30:
        return 'MEDIUM'
    # LOW severity: Weak signal
    else:
        return 'LOW'


def calculate_expected_price(strike: float, spy_price: float, right: str) -> float:
    """Calculate expected option price using simple heuristic.
    
    This is a basic model for fallback purposes. The main detection
    uses exponential regression on actual market data.
    
    Args:
        strike: Option strike price
        spy_price: Current SPY price
        right: 'C' for call, 'P' for put
        
    Returns:
        float: Expected option price
    """
    moneyness = abs(strike - spy_price) / spy_price
    
    # Simple linear decay (placeholder for basic estimation)
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
