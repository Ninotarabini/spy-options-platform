from fastapi import FastAPI
from datetime import datetime

app = FastAPI(title="SPY Options Backend API")

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker/K8s"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "spy-backend",
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    return {
        "message": "SPY Options Backend API",
        "version": "1.0.0",
        "endpoints": ["/health", "/anomalies", "/signals"]
    }