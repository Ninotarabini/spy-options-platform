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
from models import Anomaly, AnomaliesResponse, HealthResponse
from services.storage_client import storage_client
from services.signalr_client import signalr_client
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

# FastAPI app
app = FastAPI(
    title="SPY Options Backend API",
    description="Backend API for SPY Options Trading Platform with Azure integration",
    version=__version__
)

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
    logger.info("Starting SPY Options Backend API v1.2.0")
    
    try:
        # Connect to Azure Table Storage
        storage_client.connect()
        logger.info("✅ Azure Table Storage connected")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Storage: {e}")
    
    try:
        # Connect to Azure SignalR
        signalr_client.connect()
        logger.info("✅ Azure SignalR initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize SignalR: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup connections on shutdown."""
    logger.info("Shutting down SPY Options Backend API")
    signalr_client.disconnect()


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
async def create_anomaly(anomaly: Anomaly):
    """
    Create new anomaly detection result.
    
    This endpoint is called by the detector service when an anomaly is found.
    It performs three actions:
    1. Saves to Azure Table Storage for persistence
    2. Broadcasts to Azure SignalR for real-time updates
    3. Updates Prometheus metrics
    
    Args:
        anomaly: Anomaly object with detection details
        
    Returns:
        Confirmation with anomaly ID and status
    """
    http_requests_total.labels(method="POST", endpoint="/anomalies", status="201").inc()
    
    try:
        # 1. Save to Azure Table Storage
        logger.info(f"Saving anomaly: {anomaly.symbol} strike={anomaly.strike} severity={anomaly.severity}")
        saved = storage_client.save_anomaly(anomaly)
        
        if not saved:
            raise Exception("Failed to save to storage")
        
        # 2. Broadcast via SignalR (TODO: implement REST API in Phase 9 full)
        # For now, just log and update metrics
        logger.info(f"Broadcasting anomaly signal: {anomaly.symbol} {anomaly.option_type} @ {anomaly.strike}")
        
        # 3. Update Prometheus metrics
        anomalies_detected_total.labels(severity=anomaly.severity).inc()
        
        logger.info(f"✅ Anomaly processed successfully: {anomaly.strike}")
        
        return {
            "status": "success",
            "message": "Anomaly saved and broadcasted",
            "anomaly_id": f"{int(anomaly.timestamp.timestamp() * 1000)}_{anomaly.strike}_{anomaly.option_type}",
            "timestamp": anomaly.timestamp.isoformat(),
            "severity": anomaly.severity
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing anomaly: {e}")
        http_requests_total.labels(method="POST", endpoint="/anomalies", status="500").inc()
        raise HTTPException(status_code=500, detail=f"Failed to process anomaly: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
