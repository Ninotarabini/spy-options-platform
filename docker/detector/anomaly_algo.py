
import logging
import numpy as np
from typing import List, Dict, Any
from datetime import datetime, timezone

from config import settings

logger = logging.getLogger(__name__)


def detect_anomalies(options_data: List[Dict[str, Any]], spy_price: float):

    if not options_data:
        return []

    # Separación ultra barata
    calls = [o for o in options_data if o["option_type"] == "C"]
    puts = [o for o in options_data if o["option_type"] == "P"]

    anomalies = []

    if len(calls) > 3:
        anomalies.extend(_detect_series_fast(calls, spy_price, "C"))

    if len(puts) > 3:
        anomalies.extend(_detect_series_fast(puts, spy_price, "P"))

    return anomalies


def _detect_series_fast(series, spy_price, right):

    # ---- Structured NumPy array (menos overhead) ----
    dtype = np.dtype([
        ("strike", "f8"),
        ("mid", "f8"),
        ("bid", "f8"),
        ("ask", "f8"),
        ("volume", "f8"),
    ])

    data = np.array(
        [(o["strike"], o["mid"], o["bid"], o["ask"], o["volume"]) for o in series],
        dtype=dtype,
    )

    # ---- Early filtering (🔥 GRAN mejora real) ----
    valid_mask = (data["mid"] > 0.05) & (data["bid"] >= 0)

    data = data[valid_mask]

    if len(data) < 4:
        return []

    # ---- Orden por strike ----
    order = np.argsort(data["strike"])
    data = data[order]

    strikes = data["strike"]
    mids = data["mid"]

    # ---- Price change vectorizado ----
    prev_mids = np.maximum(mids[:-1], 0.05)

    price_change_pct = np.zeros_like(mids)
    price_change_pct[1:] = np.abs((mids[1:] - mids[:-1]) / prev_mids) * 100

    # ---- Z-score optimizado (single-pass math) ----
    mean = price_change_pct.mean()
    var = price_change_pct.var()

    if var > 0:
        std = np.sqrt(var)
        z_scores = (price_change_pct - mean) / std
    else:
        z_scores = np.zeros_like(price_change_pct)

    threshold = settings.anomaly_threshold

    # ---- Máscara vectorizada ----
    anomaly_mask = (np.abs(z_scores) > threshold) & (price_change_pct > 0)

    indices = np.where(anomaly_mask)[0]

    if len(indices) == 0:
        return []

    timestamp = datetime.now(timezone.utc).isoformat()

    anomalies = []

    for i in indices:

        strike = strikes[i]
        mid = mids[i]

        expected_price = calculate_expected_price(strike, spy_price, right)

        anomalies.append({
            "timestamp": timestamp,
            "strike": float(strike),
            "right": right,
            "price": float(mid),
            "expected_price": float(expected_price),
            "bid": float(data["bid"][i]),
            "ask": float(data["ask"][i]),
            "volume": int(data["volume"][i]),
            "open_interest": 0,
            "spy_price": float(spy_price),
            "moneyness": float((strike - spy_price) / spy_price),
            "deviation_pct": float(price_change_pct[i]),
            "z_score": float(z_scores[i]),
            "severity": _calculate_severity(z_scores[i], price_change_pct[i]),
        })

    return anomalies


def _calculate_severity(z_score, deviation_pct):

    abs_z = abs(z_score)

    if abs_z > 2.0 or deviation_pct > 50:
        return "HIGH"
    elif abs_z > 1.0 or deviation_pct > 20:
        return "MEDIUM"
    return "LOW"


def calculate_expected_price(strike, spy_price, right):

    moneyness = abs(strike - spy_price) / spy_price
    decay = max(2.0 * (1 - moneyness * 10), 0.01)

    if right == "C":
        if strike <= spy_price:
            intrinsic = spy_price - strike
            return max(intrinsic + decay, intrinsic)
        return decay

    else:
        if strike >= spy_price:
            intrinsic = strike - spy_price
            return max(intrinsic + decay, intrinsic)
        return decay
