"""
SPY Options Backend API - FastAPI application with Azure integration.
Optimized v1.8.1 - Asynchronous task handling to prevent K8s timeouts.
"""
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
from config import settings
from models import Anomaly, AnomaliesResponse, HealthResponse, VolumeSnapshot, FlowSnapshot, SpyMarketSnapshot, MarketState
from services.storage_client import storage_client
from services.signalr_rest import signalr_rest
from services.signalr_negotiate import router as signalr_negotiate_router
from metrics import (
    http_requests_total,
    anomalies_detected_total,
    anomalies_current
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app initialization
app = FastAPI(
    title="SPY Options Backend API",
    description="Backend API for SPY Options Trading Platform with Azure integration",
    version=settings.app_version
)

# Register routers
app.include_router(signalr_negotiate_router, prefix="")


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup."""
    logger.info(f"Starting SPY Options Backend API v{settings.app_version}")
    try:
        storage_client.connect()
        logger.info("✅ Azure Table Storage connected")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Storage: {e}")
    logger.info("✅ Azure SignalR REST client initialized")

@app.get("/", tags=["Info"])
async def root():
    http_requests_total.labels(method="GET", endpoint="/", status="200").inc()
    return {
        "service": "SPY Options Backend API",
        "version": settings.app_version,
        "status": "operational"
    }

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    http_requests_total.labels(method="GET", endpoint="/health", status="200").inc()
    return HealthResponse(
        status="healthy",
        service="spy-backend",
        version=settings.app_version,
        timestamp=datetime.utcnow()
    )

@app.get("/metrics", response_class=PlainTextResponse, tags=["Monitoring"])
async def metrics():
    return generate_latest().decode('utf-8')

# === SPY MARKET ENDPOINTS (NUEVO) ===

@app.post("/spy-market", tags=["Market"])
async def receive_spy_market(market: SpyMarketSnapshot):
    """Recibe precio SPY underlying y actualiza marketstate si ATM cambia."""
    http_requests_total.labels(method="POST", endpoint="/spy-market", status="201").inc()
    
    try:
        # 1. Guardar en tabla spymarket
        storage_client.save_spy_market(market)
        
        # 2. Verificar si ATM cambió
        current_state = storage_client.get_market_state()
        new_atm_center = round(market.price)
        
        if not current_state or current_state.get("atm_center") != new_atm_center:
            # ATM cambió → Actualizar marketstate
            storage_client.update_market_state({
                "atm_center": new_atm_center,
                "atm_min": new_atm_center - 5,
                "atm_max": new_atm_center + 5
            })
            logger.info(f"🎯 ATM actualizado: {new_atm_center} (±5 strikes)")
        
        # 3. Broadcast precio via SignalR (canal "price")
        asyncio.create_task(asyncio.to_thread(
            signalr_rest.broadcast,
            hub_name="spyoptions",
            event_name="price",
            data={
                "timestamp": market.timestamp,
                "price": float(market.price)
            }
        ))
        
        logger.debug(f"📊 SPY market: ${market.price:.2f}")
        return {"status": "success", "timestamp": market.timestamp}
        
    except Exception as e:
        logger.error(f"❌ Error processing SPY market: {e}")
        http_requests_total.labels(method="POST", endpoint="/spy-market", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/market/state", tags=["Market"])
async def update_market_state_endpoint(state: Dict[str, Any]):
    """Actualiza estado genérico del mercado (previous_close, market_status, etc)."""
    http_requests_total.labels(method="POST", endpoint="/market/state", status="201").inc()
    
    try:
        success = storage_client.update_market_state(state)
        if success:
            logger.info(f"🎯 Market state updated: {list(state.keys())}")
            return {"status": "success", "updated_fields": list(state.keys())}
        else:
            raise HTTPException(status_code=500, detail="Failed to update market state")
    except Exception as e:
        logger.error(f"❌ Error updating market state: {e}")
        http_requests_total.labels(method="POST", endpoint="/market/state", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/state", tags=["Market"])
async def get_market_state_endpoint():
    """Obtiene estado genérico del mercado (1 llamada inicial frontend)."""
    http_requests_total.labels(method="GET", endpoint="/api/market/state", status="200").inc()
    
    try:
        state = storage_client.get_market_state()
        if not state:
            # Primera inicialización - retornar valores por defecto
            return {
                "previous_close": 0.0,
                "atm_center": 0,
                "atm_min": 0,
                "atm_max": 0,
                "market_status": "UNKNOWN",
                "daily_high": None,
                "daily_low": None,
                "last_updated": datetime.utcnow().isoformat() + "Z"
            }
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Error getting market state: {e}")
        http_requests_total.labels(method="GET", endpoint="/api/market/state", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spy-market/current", tags=["Market"])
async def get_current_spy_price():
    """Obtiene precio actual SPY desde tabla spymarket."""
    http_requests_total.labels(method="GET", endpoint="/api/spy-market/current", status="200").inc()
    
    try:
        market_data = storage_client.get_latest_spy_market()
        if not market_data:
            raise HTTPException(status_code=503, detail="No SPY market data available")
        
        return market_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting SPY market: {e}")
        http_requests_total.labels(method="GET", endpoint="/api/spy-market/current", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/anomalies", tags=["Anomalies"])
async def create_anomaly(payload: AnomaliesResponse):
    """Procesa anomalías de forma asíncrona para evitar bloqueos."""
    http_requests_total.labels(method="POST", endpoint="/anomalies", status="201").inc()
    try:
        logger.info(f"📥 Recibidas {payload.count} anomalías")
        
        for anomaly in payload.anomalies:
            # 1. Guardado síncrono (crítico para persistencia)
            storage_client.save_anomaly(anomaly)
            anomalies_detected_total.labels(severity=anomaly.severity).inc()
            
            # 2. Broadcast asíncrono (evita esperar latencia de SignalR)
            asyncio.create_task(asyncio.to_thread(
                signalr_rest.broadcast,
                hub_name="spyoptions",
                event_name="anomalyDetected",
                data={
                    "timestamp": anomaly.timestamp.isoformat(),
                    "strike": float(anomaly.strike),
                    "option_type": anomaly.option_type,
                    "mid_price": float(anomaly.mid_price),
                    "bid": float(anomaly.bid),
                    "ask": float(anomaly.ask),
                    "deviation_percent": float(anomaly.deviation_percent),
                    "volume": int(anomaly.volume),
                    "open_interest": int(anomaly.open_interest),
                    "severity": anomaly.severity
                }
            ))
        return {"status": "success", "count": payload.count}
    except Exception as e:
        logger.error(f"❌ Error processing anomalies: {e}")
        http_requests_total.labels(method="POST", endpoint="/anomalies", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/volumes", tags=["Volumes"])
async def receive_volumes(volume: VolumeSnapshot):
    """Procesa volúmenes ATM de forma asíncrona."""
    http_requests_total.labels(method="POST", endpoint="/volumes", status="201").inc()
    try:
        logger.info(f"📊 Volúmenes recibidos: C={volume.calls_volume_atm}, P={volume.puts_volume_atm}")
        
        # Guardado en Storage
        storage_client.save_volume_snapshot(volume)
        
        # Broadcast asíncrono
        asyncio.create_task(asyncio.to_thread(
            signalr_rest.broadcast,
            hub_name="spyoptions",
            event_name="volumeUpdate",
            data={
                "timestamp": volume.timestamp.isoformat(),
                "spy_price": float(volume.spy_price),
                "calls_volume_atm": volume.calls_volume_atm,
                "puts_volume_atm": volume.puts_volume_atm,
                "calls_volume_delta": volume.calls_volume_delta,
                "puts_volume_delta": volume.puts_volume_delta,
                "atm_range": volume.atm_range,
                "strikes_count": volume.strikes_count,
                "spy_change_pct": float(volume.spy_change_pct) if volume.spy_change_pct else 0.0
            }
        ))
        return {"status": "success", "timestamp": volume.timestamp.isoformat()}
    except Exception as e:
        logger.error(f"❌ Error processing volumes: {e}")
        http_requests_total.labels(method="POST", endpoint="/volumes", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/flow", tags=["Flow"])
async def receive_flow(flow: FlowSnapshot):
    """
    Recibe signed premium flow LIMPIO (solo opciones).
    Derivados calculados en otros endpoints.
    """
    http_requests_total.labels(method="POST", endpoint="/flow", status="201").inc()
    
    try:
        # FASE 1 - CALCULAR DERIVADOS EN BACKEND
        # 1. % Change diario
        spy_change_pct = 0.0
        if flow.previous_close and flow.previous_close > 0:
            spy_change_pct = ((flow.spy_price - flow.previous_close) / flow.previous_close) * 100
            logger.info(f"📈 % Change calculado: {spy_change_pct:.2f}%")
        
        # 2. ATM Range (±5 strikes fijos)
        atm_center = round(flow.spy_price)
        atm_range = {
            "min_strike": atm_center - 5,
            "max_strike": atm_center + 5
        }
        logger.info(f"🎯 ATM Range: {atm_range['min_strike']} - {atm_range['max_strike']}")
        
        logger.info(
            f"📊 Flow recibido: SPY=${flow.spy_price:.2f} ({spy_change_pct:+.2f}%) | "
            f"Calls=${flow.cum_call_flow:,.0f} | Puts=${flow.cum_put_flow:,.0f}"
        )
        
        # Broadcast via SignalR CON DERIVADOS
        # Broadcast SOLO flow (sin derivados)
        signalr_rest.broadcast(
            hub_name="spyoptions",
            event_name="flow",
            data={
                "timestamp": flow.timestamp,
                "cum_call_flow": float(flow.cum_call_flow),
                "cum_put_flow": float(flow.cum_put_flow),
                "net_flow": float(flow.net_flow)
            }
        )
        
        # ✅ NUEVO: Persistir en Azure
        storage_client.save_flow_snapshot(flow.dict())
        
        return {"status": "success", "timestamp": flow.timestamp}
        
    except Exception as e:
        logger.error(f"❌ Error processing flow: {e}")
        http_requests_total.labels(method="POST", endpoint="/flow", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.get("/anomalies", response_model=AnomaliesResponse, tags=["Anomalies"])
async def get_anomalies(limit: int = Query(default=10, ge=1, le=100)):
    http_requests_total.labels(method="GET", endpoint="/anomalies", status="200").inc()
    try:
        anomalies = storage_client.get_recent_anomalies(limit=limit)
        anomalies_current.set(len(anomalies))
        return AnomaliesResponse(
            count=len(anomalies),
            anomalies=anomalies,
            last_scan=datetime.utcnow()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/snapshot", response_model=AnomaliesResponse, tags=["Anomalies"])
async def get_dashboard_snapshot(limit: int = Query(default=50)): # Aumentado a 50
    """Alias para satisfacer la ruta que busca el frontend"""
    return await get_anomalies(limit=limit)

@app.get("/volumes/snapshot", response_model=dict, tags=["Volumes"])
async def get_volume_history(hours: int = Query(default=72, ge=1, le=120)): # Default 72h (3 días), Máximo 120h (5 días)
    """Retorna el historial de volúmenes (hasta 72h por defecto) para cubrir fines de semana"""
    try:
        history = storage_client.get_volume_history(hours=hours)
        return {"hours": hours, "count": len(history), "history": history}
    except Exception as e:
        # Nota: Mantengo tu lógica de métricas si la tienes implementada
        if 'http_requests_total' in globals():
            http_requests_total.labels(method="GET", endpoint="/volumes/snapshot", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/flow/snapshot", response_model=dict, tags=["Flow"])
async def get_flow_history(hours: int = Query(default=72, ge=1, le=120)):
    """Retorna el historial de flow acumulado (hasta 72h por defecto)."""
    try:
        history = storage_client.get_flow_history(hours=hours)
        return {"hours": hours, "count": len(history), "history": history}
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/flow/snapshot", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")