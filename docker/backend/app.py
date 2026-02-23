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
from models import Anomaly, AnomaliesResponse, HealthResponse, VolumeSnapshot, FlowSnapshot
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
    Recibe y broadcastea signed premium flow en tiempo real.
    """
    http_requests_total.labels(method="POST", endpoint="/flow", status="201").inc()
    
    try:
        logger.info(
            f"📊 Flow recibido: SPY=${flow.spy_price:.2f} | "
            f"Calls=${flow.cum_call_flow:,.0f} | Puts=${flow.cum_put_flow:,.0f}"
        )
        
        # Broadcast via SignalR
        signalr_rest.broadcast(
            hub_name="spyoptions",
            event_name="flow",
            data={
                "timestamp": flow.timestamp,
                "spy_price": float(flow.spy_price),
                "previous_close": float(flow.previous_close) if hasattr(flow, 'previous_close') and flow.previous_close else None,
                "spy_change_pct": float(flow.spy_change_pct) if hasattr(flow, 'spy_change_pct') and flow.spy_change_pct else 0.0,
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