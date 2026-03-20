"""
SPY Options Backend API - FastAPI application with Azure integration.
Optimized v1.9.0:
 - Broadcast-first: SignalR dispatch inmediato, Azure save en BackgroundTask
 - httpx.AsyncClient: sin threads extra para broadcasts
 - Caché de lectura en /anomalies (30s) y /spymarket/spy_latest (5s)
 - Deprecados eliminados: utcnow(), flow.dict(), @on_event, import duplicado
 - Métricas Prometheus con status real (al finalizar, no al inicio)
"""
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request, BackgroundTasks
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
from config import settings
from models import AnomaliesSnapshot, AnomaliesResponse, HealthResponse, VolumesSnapshot, FlowSnapshot, SpymarketSnapshot, MarketState, MarketEvent, MarketEventsResponse, GammaMetrics
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

# ─────────────────────────────────────────────
#  Caché de lectura en memoria (pod-local)
#  TTL ajustado por endpoint según criticidad
# ─────────────────────────────────────────────
_flow_cache: dict = {}
_flow_cache_time: dict = {}

_anomalies_cache: dict = {}
_anomalies_cache_time: dict = {}

_spymarket_cache: dict = {}
_spymarket_cache_ts: float = 0.0
_SPYMARKET_CACHE_TTL = 5       # segundos — dato muy fresco
_ANOMALIES_CACHE_TTL = 30      # segundos
_FLOW_CACHE_TTL = 60           # segundos


# ─────────────────────────────────────────────
#  Lifespan (reemplaza @on_event deprecado)
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: startup y shutdown."""
    # ── STARTUP ──
    logger.info(f"Starting SPY Options Backend API v{settings.app_version}")

    try:
        storage_client.connect()
        logger.info("✅ Azure Table Storage connected")
        annotation_calc = AnnotationCalculator(storage_client)
        app.state.annotation_calc = annotation_calc  # guardado en app.state
        logger.info("✅ Annotation calculator initialized")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Storage: {e}")

    # Inicializar cliente HTTP async para SignalR (elimina threads extra)
    await signalr_rest.init_async_client()
    logger.info("✅ SignalR httpx.AsyncClient inicializado")

    # Scheduler de limpieza automática
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

    yield  # ← la app corre aquí

    # ── SHUTDOWN ──
    await signalr_rest.close_async_client()
    logger.info("✅ SignalR httpx.AsyncClient cerrado")
    cleanup_scheduler.shutdown(wait=False)


# FastAPI app initialization
app = FastAPI(
    title="SPY Options Backend API",
    description="Backend API for SPY Options Trading Platform with Azure integration",
    version=settings.app_version,
    lifespan=lifespan,
)

# Register routers
app.include_router(signalr_negotiate_router, prefix="")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.1.134",
        "https://happy-water-04178ae03.3.azurestaticapps.net",
        "https://0dte-spy.com",
        "https://www.0dte-spy.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
#  Health & Metrics
# ─────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    http_requests_total.labels(method="GET", endpoint="/health", status="200").inc()
    return HealthResponse(
        status="healthy",
        service="spybackend",
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc)
    )

@app.get("/metrics", response_class=PlainTextResponse, tags=["Monitoring"])
async def metrics():
    return generate_latest().decode('utf-8')


# ─────────────────────────────────────────────
#  SPY MARKET
# ─────────────────────────────────────────────

@app.post("/spymarket", tags=["Market"])
async def receive_spymarket(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint único para recibir datos SPY desde detector.

    OPT v1.9: Broadcast-first — SignalR se dispara ANTES de guardar en Azure.
    El guardado en Azure se delega a BackgroundTask (no bloquea al detector).
    """
    try:
        data = await request.json()

        # Validación mínima
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
            ((price - previous_close) / previous_close) * 100, 2
        ) if previous_close > 0 else 0.0

        atm_center = round(price)
        atm_min = atm_center - 5
        atm_max = atm_center + 5

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

        broadcast_payload = {
            "current_price": price,
            "spy_change_pct": spy_change_pct,
            "atm_center": atm_center,
            "atm_min": atm_min,
            "atm_max": atm_max,
            "market_status": market_status,
            "previous_close": previous_close
        }

        # ✅ OPT 1: Broadcast PRIMERO — respuesta inmediata al detector
        await signalr_rest.broadcast_async(
            hub_name="spyoptions",
            event_name="marketState",
            data=broadcast_payload
        )

        # ✅ OPT 1: Guardar en Azure en background (no bloquea)
        def _save_spymarket():
            if not storage_client.save_spymarket(snapshot):
                logger.warning("⚠️ Background save_spymarket falló — dato no persistido")

        background_tasks.add_task(_save_spymarket)

        # Invalidar caché de /spymarket/spy_latest
        global _spymarket_cache, _spymarket_cache_ts
        _spymarket_cache = {}
        _spymarket_cache_ts = 0.0

        logger.debug(
            f"✅ SPY market processed | "
            f"${price:.2f} ({spy_change_pct:+.2f}%) | "
            f"ATM: {atm_center}"
        )

        http_requests_total.labels(method="POST", endpoint="/spymarket", status="201").inc()
        return {
            "status": "accepted",
            "timestamp": timestamp,
            "spy_change_pct": spy_change_pct,
            "atm_range": {"min": atm_min, "max": atm_max}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in /spymarket: {e}")
        http_requests_total.labels(method="POST", endpoint="/spymarket", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/spymarket/spy_latest", tags=["Market"])
async def get_spymarket_latest():
    """Obtiene el último snapshot de spymarket. Caché de 5s."""
    global _spymarket_cache, _spymarket_cache_ts

    now_ts = datetime.now(timezone.utc).timestamp()

    # ✅ OPT 4: Caché de 5s para /spymarket/spy_latest
    if _spymarket_cache and (now_ts - _spymarket_cache_ts) < _SPYMARKET_CACHE_TTL:
        return _spymarket_cache

    try:
        market_data = storage_client.get_spymarket_latest()
        if not market_data:
            return {}
        _spymarket_cache = market_data
        _spymarket_cache_ts = now_ts
        return market_data
    except Exception as e:
        logger.error(f"Error getting spymarket latest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  ANOMALIES
# ─────────────────────────────────────────────

@app.post("/anomalies", tags=["Anomalies"])
async def create_anomaly(payload: AnomaliesResponse, background_tasks: BackgroundTasks):
    """Procesa anomalías: broadcast inmediato, persistencia en background."""
    try:
        logger.info(f"Recibidas {payload.count} anomalías")

        for anomaly in payload.anomalies:
            anomalies_detected_total.labels(severity=anomaly.severity).inc()

            broadcast_data = {
                "timestamp": datetime.fromtimestamp(anomaly.timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
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

            # ✅ OPT 1: Broadcast PRIMERO
            await signalr_rest.broadcast_async(
                hub_name="spyoptions",
                event_name="anomalyDetected",
                data=broadcast_data
            )

            # ✅ OPT 1: Persistencia en background
            background_tasks.add_task(storage_client.save_anomalies, anomaly)

        # Invalidar caché de /anomalies
        _anomalies_cache.clear()
        _anomalies_cache_time.clear()

        http_requests_total.labels(method="POST", endpoint="/anomalies", status="201").inc()
        return {"status": "accepted", "count": payload.count}
    except Exception as e:
        logger.error(f"❌ Error processing anomalies: {e}")
        http_requests_total.labels(method="POST", endpoint="/anomalies", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/anomalies", response_model=dict, tags=["Anomalies"])
async def get_anomalies(hours: int = Query(default=4, ge=1, le=168), limit: int = Query(default=100, ge=1, le=500)):
    """✅ OPT: Filtro de campos para reducir payload y caché de 30s."""
    cache_key = f"anomalies_{limit}"
    now = datetime.now(timezone.utc)

    if cache_key in _anomalies_cache:
        cache_age = (now - _anomalies_cache_time.get(cache_key, now)).total_seconds()
        if cache_age < _ANOMALIES_CACHE_TTL:
            return _anomalies_cache[cache_key]

    try:
        raw_anomalies = storage_client.get_anomalies(limit=limit)
            
        # ✅ Filtramos para enviar SOLO lo que el frontend usa en cards y Strike Walls
        # Usamos .get() y fallbacks para evitar 500 si algún registro está incompleto
        clean_anomalies = [
            {
                "timestamp": a.get("timestamp"),
                "strike": a.get("strike", 0.0),
                "option_type": a.get("option_type", "UNKNOWN"),
                "mid_price": a.get("mid_price", 0.0),
                "expected_price": a.get("expected_price", 0.0),
                "deviation_percent": round(a.get("deviation_percent", 0.0), 2),
                "severity": a.get("severity", "LOW")
            }
            for a in raw_anomalies
        ]
            
        result = {
            "count": len(clean_anomalies),
            "anomalies": clean_anomalies,
            "last_scan": now.isoformat().replace("+00:00", "Z") # Estándar ISO con Z
        }
        
        _anomalies_cache[cache_key] = result
        _anomalies_cache_time[cache_key] = now
        return result

    except Exception as e:
        logger.error(f"❌ Error en get_anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  FLOW
# ─────────────────────────────────────────────

@app.post("/flow", tags=["Flow"])
async def receive_flow(flow: FlowSnapshot, background_tasks: BackgroundTasks):
    """
    Recibe signed premium flow. Broadcast-first, guardado en background.
    """
    try:
        logger.info(
            f"🚀 Flow recibido: "
            f"Calls=${flow.cum_call_flow:,.0f} | Puts=${flow.cum_put_flow:,.0f} | "
            f"Net=${flow.net_flow:,.0f}"
        )

        flow_data = {
            "timestamp": flow.timestamp,
            "cum_call_flow": float(flow.cum_call_flow),
            "cum_put_flow": float(flow.cum_put_flow),
            "net_flow": float(flow.net_flow),
            "spy_price": float(flow.spy_price)
        }

        # ✅ OPT 1: Broadcast PRIMERO
        await signalr_rest.broadcast_async(
            hub_name="spyoptions",
            event_name="flow",
            data=flow_data
        )

        # ✅ OPT 1: Persistencia en background
        background_tasks.add_task(storage_client.save_flow, flow.model_dump())  # ✅ Fix: model_dump()

        http_requests_total.labels(method="POST", endpoint="/flow", status="201").inc()
        return {"status": "accepted", "timestamp": flow.timestamp}

    except Exception as e:
        logger.error(f"❌ Error processing flow: {e}")
        http_requests_total.labels(method="POST", endpoint="/flow", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/flow", response_model=dict, tags=["Flow"])
async def get_flow(limit: int = Query(default=8000, ge=1, le=20000)):
    """Retorna los últimos 'limit' registros de flow. Con caché de 60s."""
    cache_key = f"flow_{limit}"
    now = datetime.now(timezone.utc)

    if cache_key in _flow_cache:
        cache_age = (now - _flow_cache_time.get(cache_key, now)).total_seconds()
        if cache_age < _FLOW_CACHE_TTL:
            return _flow_cache[cache_key]

    try:
        history = storage_client.get_flow(limit=limit)
        # history ya viene ASC (cronológico) de storage_client
        result = {"limit": limit, "count": len(history), "history": history}
        _flow_cache[cache_key] = result
        _flow_cache_time[cache_key] = now
        return result
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/flow", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  GAMMA EXPOSURE METRICS (INSTITUTIONAL)
# ─────────────────────────────────────────────

@app.post("/gamma", tags=["Gamma"])
async def receive_gamma(request: Request, background_tasks: BackgroundTasks):
    """
    Receives institutional gamma exposure metrics (Net GEX, Gamma Regime, Pinning Risk).
    Broadcast-first, background persistence.
    
    Payload: GammaMetrics from detector/pressure_engine.py (GammaExposureEngine)
    """
    try:
        data = await request.json()
        
        logger.info(
            f"🌡️ Gamma metrics received: "
            f"NetGEX={data.get('net_gex', 0):.3f}, "
            f"Regime={data.get('gamma_regime', 0):.3f}, "
            f"Pinning={data.get('pinning_risk', 0):.3f}"
        )
        
        # ✅ OPT 1: Broadcast FIRST (immediate response)
        await signalr_rest.broadcast_async(
            hub_name="spyoptions",
            event_name="gammaUpdate",
            data=data
        )
        
        # ✅ OPT 1: Background persistence (non-blocking)
        background_tasks.add_task(storage_client.save_gamma_metrics, data)
        
        http_requests_total.labels(method="POST", endpoint="/gamma", status="201").inc()
        return {
            "status": "accepted",
            "timestamp": data.get("timestamp"),
            "net_gex": data.get("net_gex"),
            "gamma_regime": data.get("gamma_regime"),
            "pinning_risk": data.get("pinning_risk")
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing gamma metrics: {e}")
        http_requests_total.labels(method="POST", endpoint="/gamma", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  VOLUMES
# ─────────────────────────────────────────────



@app.get("/gamma/gamma_snap", tags=["Gamma"])
async def get_gamma_snap(limit: int = Query(default=20, ge=1, le=100)):
    """
    Historical gamma metrics snapshot (last N records).
    Compatible with frontend cache pattern (similar to /anomalies/anom_snap).
    
    Returns:
        {
            "count": int,
            "gamma_metrics": [
                {
                    "timestamp": str,
                    "net_gex": float,
                    "gamma_regime": float,
                    "pinning_risk": float,
                    "gamma_walls": [{"strike": float, "type": str, ...}, ...]
                }
            ]
        }
    """
    cache_key = f"gamma_snap_{limit}"
    now = datetime.now(timezone.utc)
    
    # Caché 30s (consistente con anomalies)
    if cache_key in _anomalies_cache:
        cache_age = (now - _anomalies_cache_time.get(cache_key, now)).total_seconds()
        if cache_age < _ANOMALIES_CACHE_TTL:
            return _anomalies_cache[cache_key]
    
    try:
        raw_gamma = storage_client.get_gamma_metrics(limit=limit)
        
        # Filtrar campos para optimizar payload
        clean_gamma = [
            {
                "timestamp": g.get("timestamp"),
                "net_gex": g.get("net_gex", 0.0),
                "gamma_regime": g.get("gamma_regime", 0.0),
                "pinning_risk": g.get("pinning_risk", 0.0),
                "gamma_walls": g.get("gamma_walls", [])
            }
            for g in raw_gamma
        ]
        
        response = {
            "count": len(clean_gamma),
            "gamma_metrics": clean_gamma
        }
        
        # Actualizar caché
        _anomalies_cache[cache_key] = response
        _anomalies_cache_time[cache_key] = now
        
        logger.info(f"📊 GET /gamma/gamma_snap: {len(clean_gamma)} registros (cache={cache_key})")
        http_requests_total.labels(method="GET", endpoint="/gamma/gamma_snap", status="200").inc()
        return response
        
    except Exception as e:
        logger.error(f"❌ Error get_gamma_snap: {e}")
        http_requests_total.labels(method="GET", endpoint="/gamma/gamma_snap", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/volumes", response_model=dict, tags=["Volumes"])
async def get_volumes(hours: int = Query(default=120, ge=1, le=168), limit: int = Query(default=4000, ge=1, le=8000)):
    """Retorna el historial de volúmenes."""
    try:
        history = storage_client.get_volumes(hours=hours, max_results=limit)
        http_requests_total.labels(method="GET", endpoint="/volumes", status="200").inc()
        return {"hours": hours, "limit": limit, "count": len(history), "history": history}
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/volumes", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  ALIAS ENDPOINTS (compatibilidad frontend)
# ─────────────────────────────────────────────

@app.get("/volumes/snap_last_4h", tags=["Volumes"])
async def get_volumes_snap_last_4h(hours: int = Query(default=72), limit: int = Query(default=4000)):
    """Alias para compatibilidad con frontend"""
    return await get_volumes(hours=hours, limit=limit)

@app.get("/flow/Flow_snap_last_4h", tags=["Flow"])
async def get_flow_snap_last_4h(limit: int = Query(default=8000, ge=1, le=12000)):
    """Alias para compatibilidad con frontend"""
    return await get_flow(limit=limit)

@app.get("/anomalies/anom_snap", tags=["Anomalies"])
async def get_anomalies_snap_last_4h(hours: int = Query(default=4), limit: int = Query(default=50)):
    """Alias para compatibilidad con frontend — últimas 4h"""
    return await get_anomalies(hours=hours, limit=limit)


# ─────────────────────────────────────────────
#  TRADINGVIEW WEBHOOKS
# ─────────────────────────────────────────────

# ============================================
# HELPER: Procesamiento de Señales TradingView
# ============================================

async def _process_tv_signal(data: dict):
    """
    Procesa señal de TradingView en background.
    - Broadcast a SignalR (si disponible)
    - Persistencia en Azure Table Storage
    """
    try:
        # Broadcast a SignalR
        await signalr_rest.broadcast_async(
            hub_name="spyoptions",
            event_name="tvSignal",
            data=data
        )
        logger.info(f"📡 Signal broadcasted: {data.get('action')}")
        
        # Persistir en storage
        storage_client.save_market_event(data)
        logger.info(f"💾 Signal saved: {data.get('action')} @ {data.get('price')}")
        
    except Exception as e:
        logger.error(f"❌ Error processing TV signal: {e}")


@app.post("/api/webhooks/tradingview", tags=["Webhooks"])
async def tradingview_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives alerts from TradingView.
    Standardized flow: Broadcast-First, Background Persistence.
    """
    try:
        data = await request.json()
        logger.info(f"🔍 WEBHOOK RAW data received: {repr(data)}")
        
        # 🔐 VALIDACIÓN DE SEGURIDAD
        if data.get("secret") != settings.tv_webhook_secret:
            logger.warning(f"⚠️ Unauthorized Webhook attempt. Invalid secret.")
            return {"status": "error", "message": "Invalid secret"}

        # Standardize timestamp if missing
        if "timestamp" not in data:
            data["timestamp"] = int(datetime.now(timezone.utc).timestamp())

        # ✅ NUEVO: Procesamiento completo en background (sin await)
        # Esto permite respuesta inmediata <1s a TradingView
        background_tasks.add_task(_process_tv_signal, data)

        logger.info(f"🚩 TradingView Signal queued: {data.get('action')} @ {data.get('price')}")

        http_requests_total.labels(method="POST", endpoint="/api/webhooks/tradingview", status="202").inc()
        return {
            "status": "accepted",
            "timestamp": data["timestamp"],
            "action": data.get("action")
        }

    except Exception as e:
        http_requests_total.labels(method="POST", endpoint="/api/webhooks/tradingview", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market-events", tags=["Webhooks"])
async def get_market_events(limit: int = Query(default=100, ge=1, le=500)):
    """
    Retrieves historical market events (signals).
    """
    try:
        events = storage_client.get_market_events(limit=limit)
        return {
            "count": len(events),
            "events": events
        }
    except Exception as e:
        logger.error(f"❌ Error in get_market_events: {e}")
        raise HTTPException(status_code=500, detail=str(e))
