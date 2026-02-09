"""
Pydantic models for API request/response schemas.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    service: str = "spy-backend"
    version: str = "1.1.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Anomaly(BaseModel):
    """Anomaly detection result."""
    timestamp: datetime
    symbol: str = "SPY"
    strike: float
    option_type: str  # "CALL" or "PUT"
    bid: float
    ask: float
    mid_price: float
    expected_price: float
    deviation_percent: float
    volume: int
    open_interest: int
    severity: str  # "LOW", "MEDIUM", "HIGH"


class AnomaliesResponse(BaseModel):
    """Response for /anomalies endpoint."""
    count: int
    anomalies: List[Anomaly]
    last_scan: Optional[datetime] = None

class VolumeSnapshot(BaseModel):
    """Volume aggregation snapshot for ATM strikes."""
    timestamp: datetime
    spy_price: float
    calls_volume_atm: int
    puts_volume_atm: int
    atm_range: dict  # {"min_strike": float, "max_strike": float}
    strikes_count: dict  # {"calls": int, "puts": int}
    calls_volume_delta: int  # Incremental volume since last scan
    puts_volume_delta: int   # Incremental volume since last scan


class Signal(BaseModel):
    """Trading signal to broadcast."""
    signal_id: str
    timestamp: datetime
    action: str  # "BUY", "SELL", "HOLD"
    symbol: str = "SPY"
    strike: float
    option_type: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class SignalResponse(BaseModel):
    """Response after broadcasting signal."""
    signal_id: str
    status: str = "broadcasted"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
