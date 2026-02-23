"""
Pydantic models for API request/response schemas.

⚠️ CRITICAL: Este archivo está DUPLICADO en docker/detector/models.py
Al modificar Anomaly, AnomaliesResponse o VolumeSnapshot:
1. Sincronizar MANUALMENTE backend/models.py - detector/models.py
2. Rebuild AMBOS servicios (backend + detector)

"""
from datetime import datetime
from typing import Optional, List, Dict
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
    previous_close: float  # Precio cierre anterior (capturado al inicio sesión)
    calls_volume_atm: int
    puts_volume_atm: int
    atm_range: dict  # {"min_strike": float, "max_strike": float}
    strikes_count: dict  # {"calls": int, "puts": int}
    calls_volume_delta: int  # Incremental volume since last scan
    puts_volume_delta: int   # Incremental volume since last scan
    spy_change_pct: Optional[float] = None  # % cambio diario SPY vs cierre anterior

class SpyMarketSnapshot(BaseModel):
    """SPY underlying price snapshot (tabla spymarket)."""
    timestamp: int  # Unix timestamp
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None

class MarketState(BaseModel):
    """Estado genérico del mercado (tabla marketstate - 1 fila única)."""
    previous_close: float  # Capturado al inicio sesión, constante todo el día
    atm_center: int        # Round(spy_price), se actualiza ~5 veces/día
    atm_min: int           # atm_center - 5
    atm_max: int           # atm_center + 5
    market_status: str     # "OPEN", "CLOSED", "PREMARKET"
    daily_high: Optional[float] = None
    daily_low: Optional[float] = None
    last_updated: str      # ISO 8601 timestamp

class FlowSnapshot(BaseModel):
    """Real-time signed premium flow LIMPIO (solo opciones)."""
    timestamp: int  # Unix timestamp
    cum_call_flow: float  # Flujo acumulado de calls (signed premium)
    cum_put_flow: float   # Flujo acumulado de puts (signed premium)
    net_flow: float       # cum_call_flow - cum_put_flow

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
