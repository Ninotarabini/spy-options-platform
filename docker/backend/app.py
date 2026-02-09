"""
SPY Options Backend API - FastAPI application with Azure integration.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
from datetime import datetime
import logging
from __version__ import __version__
from models import Anomaly, AnomaliesResponse, HealthResponse, VolumeSnapshot
from services.storage_client import storage_client
from services.signalr_rest import signalr_rest  # ← CAMBIO: REST API en lugar de Python SDK
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

from fastapi import FastAPI
from services.signalr_negotiate import router as signalr_negotiate_router
from __version__ import __version__

# FastAPI app
app = FastAPI(
    title="SPY Options Backend API",
    description="Backend API for SPY Options Trading Platform with Azure integration",
    version=__version__
)
#  Registrar routers
app.include_router(signalr_negotiate_router)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup."""
    logger.info("Starting SPY Options Backend API v1.8.0")
    
    try:
        # Connect to Azure Table Storage
        storage_client.connect()
        logger.info("✅ Azure Table Storage connected")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Storage: {e}")
    
    # SignalR REST client is stateless - no connection needed
    logger.info("✅ Azure SignalR REST client initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup connections on shutdown."""
    logger.info("Shutting down SPY Options Backend API")
    # No cleanup needed for REST client


@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with API information."""
    http_requests_total.labels(method="GET", endpoint="/", status="200").inc()
    return {
        "service": "SPY Options Backend API",
        "version": __version__,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "anomalies_get": "GET /anomalies",
            "anomalies_post": "POST /anomalies"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Health check endpoint for Kubernetes probes."""
    http_requests_total.labels(method="GET", endpoint="/health", status="200").inc()
    return HealthResponse(
        status="healthy",
        service="spy-backend",
        version= __version__,
        timestamp=datetime.utcnow()
    )


@app.get("/metrics", response_class=PlainTextResponse, tags=["Monitoring"])
async def metrics():
    """Prometheus metrics endpoint for ServiceMonitor."""
    return generate_latest().decode('utf-8')

    
@app.get("/anomalies", response_model=AnomaliesResponse, tags=["Anomalies"])
async def get_anomalies(limit: int = Query(default=10, ge=1, le=100)):
    """
    Get recent anomalies from Azure Table Storage.
    
    Args:
        limit: Maximum number of anomalies to return (1-100, default: 10)
        
    Returns:
        AnomaliesResponse with count and list of anomalies
    """
    http_requests_total.labels(method="GET", endpoint="/anomalies", status="200").inc()
    
    try:
        anomalies = storage_client.get_recent_anomalies(limit=limit)
        
        # Update gauge metric
        anomalies_current.set(len(anomalies))
        
        return AnomaliesResponse(
            count=len(anomalies),
            anomalies=anomalies,
            last_scan=datetime.utcnow()
        )
    except Exception as e:
        logger.error(f"Error fetching anomalies: {e}")
        http_requests_total.labels(method="GET", endpoint="/anomalies", status="500").inc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch anomalies: {str(e)}")


@app.post("/anomalies", tags=["Anomalies"])
async def create_anomaly(payload: AnomaliesResponse):  
    """
    Receive batch of anomalies from detector service.
    """
    http_requests_total.labels(method="POST", endpoint="/anomalies", status="201").inc()
    
    try:
        logger.info(f"Received {payload.count} anomalies")
        # Process each anomaly in the batch
        for anomaly in payload.anomalies:
            # 1. Save to storage
            storage_client.save_anomaly(anomaly)
            anomalies_detected_total.labels(severity=anomaly.severity).inc()
            logger.info(f"Saved: {anomaly.symbol} {anomaly.option_type} @ {anomaly.strike}")
    
            # 2. Broadcast to SignalR via REST API ← CAMBIO AQUÍ
            signalr_rest.broadcast(
                hub_name="spyoptions",
                event_name="anomalyDetected",
                data={
                    "strike": float(anomaly.strike),
                    "type": anomaly.option_type,
                    "price": float(anomaly.mid_price),
                    "deviation": float(anomaly.deviation_percent),
                    "timestamp": anomaly.timestamp.isoformat()
                }
            )
        
        return {
            "status": "success",
            "count": payload.count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error processing anomalies: {e}")
        http_requests_total.labels(method="POST", endpoint="/anomalies", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/volumes", tags=["Volumes"])
async def receive_volumes(volume: VolumeSnapshot):
    """
    Receive aggregated ATM volumes from detector service.
    """
    http_requests_total.labels(method="POST", endpoint="/volumes", status="201").inc()
    
    try:
        logger.info(
            f"Received volumes: CALLS={volume.calls_volume_atm:,}, "
            f"PUTS={volume.puts_volume_atm:,}, SPY={volume.spy_price:.2f}"
        )
        
        # 1. Save to Azure Table Storage (volumehistory table)
        storage_client.save_volume_snapshot(volume)
        
        # 2. Broadcast to SignalR via REST API ← CAMBIO AQUÍ
        signalr_rest.broadcast(
            hub_name="spyoptions",
            event_name="volumeUpdate",
            data={
                "timestamp": volume.timestamp.isoformat(),
                "spy_price": float(volume.spy_price),
                "calls_volume_atm": volume.calls_volume_atm,
                "puts_volume_atm": volume.puts_volume_atm,
                "atm_range": volume.atm_range,
                "strikes_count": volume.strikes_count
            }
        )
        logger.info("Volume update broadcasted via SignalR")
        
        return {
            "status": "success",
            "timestamp": volume.timestamp.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error processing volumes: {e}")
        http_requests_total.labels(method="POST", endpoint="/volumes", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/volumes/snapshot", response_model=dict, tags=["Volumes"])
async def get_volume_history(hours: int = Query(default=2, ge=1, le=24)):
    """
    Get historical volume snapshots for the last N hours.
    Used by frontend to load initial state.
    """
    http_requests_total.labels(method="GET", endpoint="/volumes/snapshot", status="200").inc()
    
    try:
        history = storage_client.get_volume_history(hours=hours)
        
        return {
            "hours": hours,
            "count": len(history),
            "history": history
        }
        
    except Exception as e:
        logger.error(f"Error fetching volume history: {e}")
        http_requests_total.labels(method="GET", endpoint="/volumes/snapshot", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/debug/replay", tags=["Debug"])
async def replay_historical():
    """
    Replay historical anomalies from storage via SignalR.
    For testing dashboard with real data when market is closed.
    """
    try:
        anomalies = storage_client.get_recent_anomalies(limit=10)
        
        if not anomalies:
            return {"status": "no_data", "count": 0}
        
        logger.info(f"🎬 Replaying {len(anomalies)} anomalies...")
        
        for anomaly in anomalies:
            # Broadcast via REST API ← CAMBIO AQUÍ
            signalr_rest.broadcast(
                hub_name="spyoptions",
                event_name="anomalyDetected",
                data={
                    "strike": float(anomaly.strike),
                    "type": anomaly.option_type,
                    "price": float(anomaly.mid_price),
                    "deviation": float(anomaly.deviation_percent),
                    "timestamp": anomaly.timestamp.isoformat()
                }
            )
            
            # Delay 0.5s entre anomalías (simular live)
            import asyncio
            await asyncio.sleep(0.5)
        
        return {
            "status": "success",
            "replayed": len(anomalies),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Replay failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/public/anomalies", response_model=AnomaliesResponse, tags=["Public"])
async def get_public_anomalies(limit: int = Query(default=100, le=500)):
    """
    Public endpoint - 15-minute delayed anomaly data.
    No authentication required. Compliance with market data regulations.
    """
    try:
        from datetime import timedelta
        
        # Get recent anomalies
        all_anomalies = storage_client.get_recent_anomalies(limit=limit)
        
        # Filter: only data older than 15 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=15)
        delayed_anomalies = [
            a for a in all_anomalies 
            if a.timestamp.replace(tzinfo=None) < cutoff_time
        ]
        
        logger.info(f"📊 Public API: {len(delayed_anomalies)}/{len(all_anomalies)} anomalies (15min delay)")
        
        return AnomaliesResponse(
            anomalies=delayed_anomalies,
            count=len(delayed_anomalies),
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"❌ Public API failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/snapshot", response_model=dict, tags=["Public"])
async def get_dashboard_snapshot():
    """
    Public endpoint - Dashboard snapshot for real-time monitoring.
    Returns last 10 anomalies + basic statistics.
    No authentication required.
    """
    http_requests_total.labels(method="GET", endpoint="/api/dashboard/snapshot", status="200").inc()
    
    try:
        anomalies = storage_client.get_recent_anomalies(limit=10)
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "anomalies": [
                {
                    "strike": float(a.strike),
                    "type": a.option_type,
                    "price": float(a.mid_price),
                    "deviation": float(a.deviation_percent),
                    "timestamp": a.timestamp.isoformat() + "Z"
                }
                for a in anomalies
            ],
            "stats": {
                "total": len(anomalies),
                "last_update": anomalies[0].timestamp.isoformat() + "Z" if anomalies else None
            }
        }
    except Exception as e:
        logger.error(f"Dashboard snapshot error: {e}")
        http_requests_total.labels(method="GET", endpoint="/api/dashboard/snapshot", status="500").inc()
        raise HTTPException(status_code=500, detail="Internal server error")
    
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")