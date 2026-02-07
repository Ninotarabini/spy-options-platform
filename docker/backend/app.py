"""
SPY Options Backend API - FastAPI application with Azure integration.
Optimized v1.8.1 - Asynchronous task handling to prevent K8s timeouts.
"""
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
from config import settings
from models import AnomaliesSnapshot, AnomaliesResponse, HealthResponse, VolumesSnapshot, FlowSnapshot, SpymarketSnapshot, MarketState, MarketEvent, MarketEventsResponse
from services.storage_client import storage_client
from services.signalr_rest import signalr_rest
from services.annotation_calculator import AnnotationCalculator
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

"""
# =====================================
# MARKET EVENT SCHEDULER
# =====================================

 class MarketEventScheduler:
     #Scheduler for market timing events.
     
     def __init__(self, storage_client, signalr_client):
        self.storage = storage_client
        self.signalr = signalr_client
        self.scheduler = AsyncIOScheduler(timezone='Europe/Madrid')
        self.events_sent_today = set()
        logger.info("⚙️ MarketEventScheduler initialized")
    
    def start(self):
        Start the scheduler (checks every minute).
        self.scheduler.add_job(
            self.check_market_events,
            'cron',
            minute='*',
            timezone='Europe/Madrid'
        )
        self.scheduler.start()
        logger.info("✅ Market event scheduler started (checks every minute)")
    
    def check_market_events(self):
        #Check if we should emit market events.
        try:
            now_cet = datetime.now(ZoneInfo('Europe/Madrid'))
            today_key = now_cet.strftime('%Y-%m-%d')
            hour, minute = now_cet.hour, now_cet.minute
            
            # Event 1: marketPreOpen (15:15 CET)
            if hour == 15 and minute == 15:
                event_key = f"{today_key}-preopen"
                if event_key not in self.events_sent_today:
                    self._emit_event("marketPreOpen", now_cet)
                    self.events_sent_today.add(event_key)
            
            # Event 2: marketOpen (15:30 CET)
            elif hour == 15 and minute == 30:
                event_key = f"{today_key}-open"
                if event_key not in self.events_sent_today:
                    self._emit_event("marketOpen", now_cet)
                    self.events_sent_today.add(event_key)
            
            # Event 3: marketCloseStart (22:00 CET)
            elif hour == 22 and minute == 0:
                event_key = f"{today_key}-close-start"
                if event_key not in self.events_sent_today:
                    self._emit_event("marketCloseStart", now_cet)
                    self.events_sent_today.add(event_key)
            
            # Event 4: marketCloseEnd (22:15 CET)
            elif hour == 22 and minute == 15:
                event_key = f"{today_key}-close-end"
                if event_key not in self.events_sent_today:
                    self._emit_event("marketCloseEnd", now_cet, freeze=True)
                    self.events_sent_today.add(event_key)
            
            # Reset events_sent at midnight
            if hour == 0 and minute == 0:
                self.events_sent_today.clear()
                logger.info("🔄 Events cache cleared (new day)")
                
        except Exception as e:
            logger.error(f"❌ Error in check_market_events: {e}")
    
    def _emit_event(self, event_type: str, timestamp_dt: datetime, freeze: bool = False):
        #Emit market event (persist + broadcast).
        try:
            timestamp_str = timestamp_dt.isoformat()
            
            # 1. Persist to Azure
            self.storage.save_market_event(event_type, timestamp_str)
            
            # 2. Broadcast via SignalR
            data = {
                "type": event_type,
                "timestamp": timestamp_str
            }
            if freeze:
                data["action"] = "freeze"
            elif event_type == "marketOpen":
                data["action"] = "unfreeze"
            
            self.signalr.broadcast(
                hub_name="spyoptions",
                event_name="marketEvent",
                data=data
            )
            
            logger.info(f"📡 Market event emitted: {event_type} at {timestamp_str}")
            
        except Exception as e:
            logger.error(f"❌ Failed to emit event {event_type}: {e}")
"""
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
        annotation_calc = AnnotationCalculator(storage_client)
        logger.info("✅ Annotation calculator initialized")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Storage: {e}")
    logger.info("✅ Azure SignalR REST client initialized")
    
#     # Initialize and start Market Event Scheduler
#     try:
#         market_scheduler = MarketEventScheduler(storage_client, signalr_rest)
#         market_scheduler.start()
#         logger.info("✅ Market event scheduler initialized and started")
#     except Exception as e:
#         logger.error(f"❌ Failed to start market scheduler: {e}")
    
    # Scheduler de limpieza automática (ejecuta cada 24h)
    cleanup_scheduler = AsyncIOScheduler(timezone='UTC')
    cleanup_scheduler.add_job(
        func=lambda: storage_client.purge_old_data(days=7),
        trigger='cron',
        hour=2,
        minute=0,
        id='azure_cleanup',
        replace_existing=True
    )
    cleanup_scheduler.start()
    logger.info("✅ Azure cleanup scheduler started (daily at 02:00 UTC)")

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    http_requests_total.labels(method="GET", endpoint="/health", status="200").inc()
    return HealthResponse(
        status="healthy",
        service="spybackend",
        version=settings.app_version,
        timestamp=datetime.utcnow()
    )

@app.get("/metrics", response_class=PlainTextResponse, tags=["Monitoring"])
async def metrics():
    return generate_latest().decode('utf-8')

# === SPY MARKET ENDPOINTS (NUEVO) ===


@app.post("/spymarket", tags=["Market"])
async def receive_spymarket(request: Request):
    """
    Endpoint único para recibir datos SPY desde detector.
    
    El backend:
    1. Recibe datos raw (price, previous_close, market_status)
    2. Calcula datos derivados (spy_change_pct, ATM range)
    3. Guarda en tabla spymarket (única fuente de verdad)
    4. Hace broadcast SignalR al frontend
    
    Payload esperado:
    {
        "timestamp": int,
        "price": float,
        "bid": float | null,
        "ask": float | null,
        "last": float | null,
        "volume": int | null,
        "previous_close": float,
        "market_status": str
    }
    """
    http_requests_total.labels(
        method="POST", 
        endpoint="/spymarket", 
        status="201"
    ).inc()
    
    try:
        data = await request.json()
        
        # Validacion mínima
        required = ["timestamp", "price", "previous_close"]
        missing = [f for f in required if f not in data]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(missing)}"
            )
        
        # Extraer datos base
        timestamp = int(data["timestamp"])
        price = float(data["price"])
        previous_close = float(data["previous_close"])

        # Si previous_close es 0, recuperar último válido de Azure
        if previous_close == 0.0:
            last = storage_client.get_spymarket_latest()
            if last and last.get("previous_close", 0.0) > 0:
                previous_close = last["previous_close"]
                logger.warning(f"⚠️ previous_close=0 recibido, usando último válido: {previous_close}")
        market_status = data.get("market_status", "UNKNOWN")
        
        # Calcular datos derivados
        spy_change_pct = round(
            ((price - previous_close) / previous_close) * 100,
            2
        ) if previous_close > 0 else 0.0
        
        atm_center = round(price)
        atm_min = atm_center - 5
        atm_max = atm_center + 5
        
        # Crear snapshot unificado
        snapshot = SpymarketSnapshot(
            timestamp=timestamp,
            price=price,
            bid=data.get("bid"),
            ask=data.get("ask"),
            last=data.get("last"),
            volume=data.get("volume"),
            previous_close=previous_close,
            market_status=market_status,
            spy_change_pct=spy_change_pct,
            atm_center=atm_center,
            atm_min=atm_min,
            atm_max=atm_max
        )
        
        # Guardar en Azure
        success = storage_client.save_spymarket(snapshot)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save SPY market data"
            )
        
        # Preparar payload para SignalR
        broadcast_payload = {
            "current_price": price,
            "spy_change_pct": spy_change_pct,
            "atm_center": atm_center,
            "atm_min": atm_min,
            "atm_max": atm_max,
            "market_status": market_status,
            "previous_close": previous_close
        }
        
        # Broadcast vía SignalR
        asyncio.create_task(asyncio.to_thread(
            signalr_rest.broadcast,
            hub_name="spyoptions",
            event_name="marketState",
            data=broadcast_payload
        ))
        
        logger.debug(
            f"✅ SPY market processed | "
            f"${price:.2f} ({spy_change_pct:+.2f}%) | "
            f"ATM: {atm_center}"
        )
        
        return {
            "status": "success",
            "timestamp": timestamp,
            "spy_change_pct": spy_change_pct,
            "atm_range": {"min": atm_min, "max": atm_max}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in /spymarket: {e}")
        http_requests_total.labels(
            method="POST",
            endpoint="/spymarket",
            status="500"
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/spymarket/spy_latest", tags=["Market"])
async def get_spymarket_latest():
    """Obtiene el último snapshot de spymarket."""
    try:
        logger.info("[DEBUG] Llamando storage_client.get_spymarket_latest()")
        market_data = storage_client.get_spymarket_latest()
        
        logger.info(f"[DEBUG] Tipo de dato recibido: {type(market_data)}")
        logger.info(f"[DEBUG] Keys: {list(market_data.keys()) if market_data else 'None'}")
        
        if not market_data:
            logger.warning("[DEBUG] market_data está vacío, retornando {}")
            return {}
        
        logger.info(f"[DEBUG] Retornando market_data con {len(market_data)} campos")
        return market_data
    except Exception as e:
        logger.error(f"Error getting spymarket latest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

"""    
@app.get("/spymarket/snap_last_4h", tags=["Market"])
async def get_spymarket_last_4h():
    
    http_requests_total.labels(
        method="GET",
        endpoint="/spymarket/snap_last_4h",
        status="200"
    ).inc()
    
    try:
        history = storage_client.get_spymarket(hours=4)
            
        if not history:
            return []
            
        # Invertir a ASC (cronologico) para Chart.js
        history.reverse()
        return history
        
    except Exception as e:
        logger.error(f"❌ Error getting spymarket history: {e}")
        http_requests_total.labels(
            method="GET",
            endpoint="/spymarket/snap_last_4h",
            status="500"
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))
"""

@app.post("/anomalies", tags=["Anomalies"])
async def create_anomaly(payload: AnomaliesResponse):
    """Procesa anomalias de forma asincrona para evitar bloqueos."""
    http_requests_total.labels(method="POST", endpoint="/anomalies", status="201").inc()
    try:
        logger.info(f"X Recibidas {payload.count} anomalias")
        
        for anomaly in payload.anomalies:
            # 1. Guardado sincrono (critico para persistencia)
            storage_client.save_anomalies(anomaly)
            anomalies_detected_total.labels(severity=anomaly.severity).inc()
            
            # 2. Broadcast asincrono (evita esperar latencia de SignalR)
            asyncio.create_task(asyncio.to_thread(
                signalr_rest.broadcast,
                hub_name="spyoptions",
                event_name="anomalyDetected",
                data={
                    "timestamp": anomaly.timestamp,
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

"""
@app.post("/volumes", tags=["Volumes"])
async def receive_volumes(volume: VolumesSnapshot):
    
    http_requests_total.labels(method="POST", endpoint="/volumes", status="201").inc()
    try:
        logger.info(f"🚀 Volumenes recibidos: C={volume.calls_volume_atm}, P={volume.puts_volume_atm}")
        
        # Guardado en Storage
        storage_client.save_volumes(volume)
        
        # Broadcast asincrono
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
"""

@app.post("/flow", tags=["Flow"])
async def receive_flow(flow: FlowSnapshot):
    """
    Recibe signed premium flow LIMPIO (solo opciones).
    Sin derivados - arquitectura limpia Fase 2.
    """
    http_requests_total.labels(method="POST", endpoint="/flow", status="201").inc()
    
    try:
        logger.info(
            f"🚀 Flow recibido: "
            f"Calls=${flow.cum_call_flow:,.0f} | Puts=${flow.cum_put_flow:,.0f} | "
            f"Net=${flow.net_flow:,.0f}"
        )
        
        # Broadcast SOLO flow (sin derivados)
        asyncio.create_task(asyncio.to_thread(
            signalr_rest.broadcast,
            hub_name="spyoptions",
            event_name="flow",
            data={
                "timestamp": flow.timestamp,
                "cum_call_flow": float(flow.cum_call_flow),
                "cum_put_flow": float(flow.cum_put_flow),
                "net_flow": float(flow.net_flow),
                "spy_price": float(flow.spy_price)  # Para línea del chart
            }
        ))
        
        # Persistir en Azure
        storage_client.save_flow(flow.dict())
        
        return {"status": "success", "timestamp": flow.timestamp}
        
    except Exception as e:
        logger.error(f"❌ Error processing flow: {e}")
        http_requests_total.labels(method="POST", endpoint="/flow", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.get("/anomalies", response_model=dict, tags=["Anomalies"])
async def get_anomalies(hours: int = Query(default=4, ge=1, le=168), limit: int = Query(default=50, ge=1, le=100)):
    http_requests_total.labels(method="GET", endpoint="/anomalies", status="200").inc()
    try:
        anomalies = storage_client.get_anomalies(hours=hours, limit=limit)
        anomalies_current.set(len(anomalies))
        return {
            "count": len(anomalies),
            "anomalies": anomalies,
            "last_scan": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/volumes", response_model=dict, tags=["Volumes"])
async def get_volumes(hours: int = Query(default=72, ge=1, le=120)): # Default 72h (3 dias), MÃ¡ximo 120h (5 dias)
    """Retorna el historial de volumenes (hasta 72h por defecto) para cubrir fines de semana"""
    try:
        history = storage_client.get_volumes(hours=hours)
        return {"hours": hours, "count": len(history), "history": history}
    except Exception as e:
        # Nota: Mantengo tu lÃ³gica de mÃ©tricas si la tienes implementada
        if 'http_requests_total' in globals():
            http_requests_total.labels(method="GET", endpoint="/volumes/snapshot", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))

from datetime import datetime, timedelta

# Caché simple en memoria para flow history (pod-specific)
_flow_cache = {}
_flow_cache_time = {}

@app.get("/flow", response_model=dict, tags=["Flow"])
async def get_flow(hours: int = Query(default=8, ge=1, le=128)):
    """Retorna el historial de flow acumulado (últimas 8h por defecto). Con caché de 60s."""
    
    cache_key = f"flow_{hours}"
    now = datetime.utcnow()
    
    # 1. Intentar servir desde caché (si existe y tiene menos de 60s)
    if cache_key in _flow_cache and now - _flow_cache_time.get(cache_key, now) < timedelta(seconds=60):
        return _flow_cache[cache_key]
    
    # 2. Si no hay caché o expiro, consultar Azure
    try:
        history = storage_client.get_flow(hours=hours)
        # Invertir a ASC (cronologico) para Chart.js
        history.reverse()
        result = {"hours": hours, "count": len(history), "history": history}
        
        # 3. Guardar en caché
        _flow_cache[cache_key] = result
        _flow_cache_time[cache_key] = now
        
        return result
        
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/flow/snapshot", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))
    
"""
# @app.get("/marketevents", response_model=MarketEventsResponse, tags=["MarketEvents"])
# async def get_marketevents(hours: int = Query(default=96, ge=1, le=168)):
#     
#     http_requests_total.labels(method="GET", endpoint="/market-events", status="200").inc()
#     try:
#         events = storage_client.get_market_events(hours=hours)
#         return MarketEventsResponse(
#             hours=hours,
#             count=len(events),
#             events=[MarketEvent(event_type=e["type"], timestamp=e["timestamp"]) for e in events]
#         )
#     except Exception as e:
#         logger.error(f"❌ Error getting market events: {e}")
#         http_requests_total.labels(method="GET", endpoint="/market-events", status="500").inc()
#         raise HTTPException(status_code=500, detail=str(e))
#     
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
# """
# 
@app.get("/volumes/snap_last_4h", tags=["Volumes"])
async def get_volumes_snap_last_4h(hours: int = Query(default=4)):
    """Alias para compatibilidad con frontend - últimas 4h"""
    return await get_volumes(hours=hours)
# 
@app.get("/flow/Flow_snap_last_4h", tags=["Flow"])
async def get_flow_snap_last_4h(hours: int = Query(default=4)):
    """Alias para compatibilidad con frontend - últimas 4h"""
    return await get_flow(hours=hours)
# 
@app.get("/anomalies/anom_snap", tags=["Anomalies"])
async def get_anomalies_snap_last_4h(hours: int = Query(default=4), limit: int = Query(default=50)):
    """Alias para compatibilidad con frontend - últimas 4h"""
    return await get_anomalies(hours=hours, limit=limit)
# 
# @app.get("/marketevents/snap_last_4h", tags=["MarketEvents"])
# async def get_marketevents_snap_last_4h(hours: int = Query(default=4)):
#     """Alias para compatibilidad con frontend - últimas 4h"""
#     return await get_marketevents(hours=hours)
