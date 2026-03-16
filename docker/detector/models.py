"""
Pydantic models for API request/response schemas.

⚠️ CRITICAL: Este archivo está DUPLICADO en docker/detector/models.py
Al modificar modelos compartidos:
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


class SpymarketSnapshot(BaseModel):
    """
    SPY Market Unified Snapshot.
    
    Fuente de verdad única para:
    - Precio underlying (tick data)
    - Estado de mercado (metadata)
    - Datos derivados (cálculos)
    
    Tabla destino: spymarket (Azure Table Storage)
    """
    # Timestamp
    timestamp: int  # Unix timestamp (segundos)
    previous_close: Optional[float] = None
    market_status: Optional[str] = None
    
    # Tick Data (desde IBKR)
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    
    # Derived Data (calculado en backend)
    spy_change_pct: float
    atm_center: int
    atm_min: int
    atm_max: int


class AnomaliesSnapshot(BaseModel):
    """Anomaly detection result."""
    timestamp: int
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
    anomalies: List[AnomaliesSnapshot]
    last_scan: Optional[datetime] = None


class VolumesSnapshot(BaseModel):
    """Volume aggregation snapshot for ATM strikes."""
    timestamp: datetime
    spy_price: float
    previous_close: float
    calls_volume_atm: int
    puts_volume_atm: int
    atm_range: dict  # {"min_strike": float, "max_strike": float}
    strikes_count: dict  # {"calls": int, "puts": int}
    calls_volume_delta: int
    puts_volume_delta: int
    spy_change_pct: Optional[float] = None


class MarketState(BaseModel):
    """Estado genérico del mercado (tabla marketstate - OBSOLETO)."""
    previous_close: float
    current_price: float
    atm_center: int
    atm_min: int
    atm_max: int
    spy_change_pct: Optional[float] = None
    market_status: str
    daily_high: Optional[float] = None
    daily_low: Optional[float] = None
    last_updated: str


class FlowSnapshot(BaseModel):
    """Real-time signed premium flow."""
    timestamp: int
    cum_call_flow: float
    cum_put_flow: float
    net_flow: float
    spy_price: float


class MarketEvent(BaseModel):
    """Market timing event."""
    event_type: str
    timestamp: str


class MarketEventsResponse(BaseModel):
    """Response for /market-events endpoint."""
    hours: int
    count: int
    events: List[MarketEvent]


class Signal(BaseModel):
    """Trading signal to broadcast."""
    signal_id: str
    timestamp: datetime
    action: str
    symbol: str = "SPY"
    strike: float
    option_type: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class TradingViewSignal(BaseModel):
    """
    Signal from TradingView webhook.
    
    Standardized payload for real-time broadcast and persistence in marketevents table.
    """
    timestamp: int  # Unix timestamp
    action: str     # "LONG", "SHORT", "BUY", "SELL"
    price: float
    option_type: Optional[str] = "N/A"
    symbol: str = "SPY"
    secret: Optional[str] = None


class TradingViewResponse(BaseModel):
    """Response after processing a TradingView webhook."""
    status: str = "accepted"
    timestamp: int
    action: str


class SignalResponse(BaseModel):
    """Response after broadcasting signal."""
    signal_id: str
    status: str = "broadcasted"
    timestamp: datetime = Field(default_factory=datetime.utcnow)