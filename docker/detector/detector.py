# -*- coding: utf-8 -*-
"""
Detector service entrypoint.

Responsabilidades:
- Obtener precio SPY y cadena de opciones via IBKR
- Ejecutar algoritmo de deteccion de anomalias
- Normalizar resultados al contrato oficial del backend
- Enviar payload valido al endpoint /anomalies

Fuente de verdad del contrato:
- backend/models.py
- detector/models.py (identico)
"""

from __future__ import annotations
import os
import logging
import time
import signal
from threading import Thread
from datetime import datetime
from typing import List
from volume_aggregator import get_volume_tracker, get_flow_aggregator
#from signalr_client import broadcast_flow
import requests
from pydantic import ValidationError
from prometheus_client import start_http_server
from config import settings
from metrics import (
    ibkr_connection_status,
    spy_price_current,
    anomalies_detected_total,
    backend_requests_total,
    scan_duration_seconds,
    scan_errors_total,
)
from ibkr_client import IBKRClient
from anomaly_algo import detect_anomalies
# from volume_aggregator import aggregate_atm_volumes  # COMENTADO
from models import AnomaliesSnapshot, AnomaliesResponse, VolumesSnapshot, SpymarketSnapshot
from market_hours import is_detector_active, seconds_until_detector_active, is_market_open

# ============================================
# CONFIGURACIÓN MANUAL - Cambia a True para forzar activación, False respeta def run_detector_loop()
FORCE_DETECTOR_ACTIVE = False  
# ============================================

# -----------------------------------------------------------------------------
#  Logging (Configurarlo ANTES de crear el cliente)
# -----------------------------------------------------------------------------
logger = logging.getLogger("detector")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# -----------------------------------------------------------------------------
#  Inicializacion del Cliente IBKR
# -----------------------------------------------------------------------------
# Calculamos el ID unico (esto evita que dos bots choquen en la misma cuenta)
pod_name = os.getenv("HOSTNAME", "detector-0")
unique_client_id = abs(hash(pod_name)) % 1000

# CREAMOS EL CLIENTE PASANDOLE LA CONFIGURACION
# Esto soluciona el error de "AttributeError: config"
ibkr_client = IBKRClient(config=settings) 

# Le pasamos el ID Ãºnico al cliente
ibkr_client.client_id = unique_client_id




# Silenciar logs verbose de ib_async
logging.getLogger("ib_async.wrapper").setLevel(logging.WARNING)
logging.getLogger("ib_async.ib").setLevel(logging.WARNING)


RUNNING = True


def _handle_sigterm(signum, frame):
    global RUNNING
    logger.info("SIGTERM recibido, cerrando detector...")
    RUNNING = False
    try:
        ibkr_client.shutdown()
    except Exception:
        pass


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _post_async(func, *args, **kwargs):
    """
    Ejecuta POST en thread separado (fire-and-forget).
    """
    thread = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    thread.start()

def _get_market_status() -> str:
    """
    Calcula el estado del mercado basado en market_hours.py
    Returns: 'OPEN' o 'CLOSED'
    """
    return "OPEN" if is_market_open() else "CLOSED"


def _map_algo_anomaly_to_contract(raw: dict) -> AnomaliesSnapshot:
    """
    Mapea una anomalia producida por anomaly_algo.py
    al contrato oficial del backend (Pydantic).

    Falla rapido si falta algun campo.
    """

    option_type = "CALL" if raw["right"] == "C" else "PUT"

    return AnomaliesSnapshot(
        timestamp=int(datetime.utcnow().timestamp()),
        symbol="SPY",
        strike=raw["strike"],
        option_type=option_type,
        bid=raw["bid"],
        ask=raw["ask"],
        mid_price=raw["price"],
        expected_price=raw["expected_price"],
        deviation_percent=raw["deviation_pct"],
        volume=raw["volume"],
        open_interest=raw["open_interest"],
        severity=raw["severity"],
    )


def _post_anomalies(anomalies: List[AnomaliesSnapshot]) -> None:
    """
    Envia anomalias al backend.
    Valida payload antes de enviar.
    """

    payload = AnomaliesResponse(
        count=len(anomalies),
        anomalies=anomalies,
        last_scan=datetime.utcnow(),
    )

    url = f"{settings.backend_url}/anomalies"

    logger.info(
        "Enviando %d anomalias al backend (%s)",
        payload.count,
        url,
    )
    try:
        response = requests.post(
            url,
            json=payload.model_dump(mode="json"),
            timeout=5,
        )
        backend_requests_total.labels(
            method="POST",
            endpoint="/anomalies",
            status=str(response.status_code)
        ).inc()
        
        if response.status_code >= 400:
            logger.error("Error enviando anomalias | status=%s", response.status_code)
            response.raise_for_status()
        
        logger.info("Anomali­as enviadas correctamente")
    
    except requests.exceptions.Timeout:
        logger.warning("Backend timeout (30s) - Anomalias no enviadas")
    except Exception as e:
        logger.error("Error enviando Anomalias: %s", e)




def _post_volumes(volume_data: dict) -> None:
    """
    Envia la ACTIVIDAD (deltas) al backend para ver fluctuaciones.
    """
    # Cambiamos el mapeo para que el backend reciba el delta como volumen principal si asÃ­ lo deseas
    
    url = f"{settings.backend_url}/volumes"
    
    logger.info(
        "Actividad ATM (Deltas): CALLS +%d, PUTS +%d | SPY=%.2f",
        volume_data["calls_volume_delta"],
        volume_data["puts_volume_delta"],
        volume_data["spy_price"],
    )
    
    try:
        # Enviamos todo el snapshot que ya incluye los deltas calculados
        response = requests.post(
            url,
            json=volume_data, 
            timeout=5,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Error enviando fluctuaciÃ³n: %s", e)

        
# -----------------------------------------------------------------------------
# Run detector
# -----------------------------------------------------------------------------



def _post_spymarket(
    spy_price: float,
    timestamp: int,
    previous_close: float,
    market_status: str = "OPEN",
    bid: float = None,
    ask: float = None,
    last: float = None,
    volume: int = None
) -> None:
    """
    Envia snapshot SPY unificado al backend.
    
    El backend calculará:
    - spy_change_pct
    - atm_center, atm_min, atm_max
    """
    url = f"{settings.backend_url}/spymarket"
    
    payload = {
        "timestamp": timestamp,
        "price": round(spy_price, 2),
        "previous_close": round(previous_close, 2),
        "market_status": market_status,
        "bid": round(bid, 2) if bid else None,
        "ask": round(ask, 2) if ask else None,
        "last": round(last, 2) if last else None,
        "volume": volume
    }
    
    try:
        response = requests.post(url, json=payload, timeout=2)
        response.raise_for_status()
        
        logger.info(
            f"📊 SPY market sent | "
            f"${spy_price:.2f} | "
            f"Status: {market_status}"
        )
        
    except requests.exceptions.Timeout:
        logger.warning("⏱️ Backend timeout sending SPY market")
    except Exception as e:
        logger.error(f"❌ Error sending SPY market: {e}")


def run_detector_loop() -> None:
    logger.info("Iniciando detector (modo servicio)")
    
    # Prometheus metrics HTTP server
    start_http_server(9100)
    logger.info("Prometheus metrics server iniciado en puerto 9100")

    while RUNNING:
        
        scan_start_time = time.time()
        
        try:
            if FORCE_DETECTOR_ACTIVE:
               logger.warning("⚠️ MODO FORZADO ACTIVADO - Ejecutando fuera de horario")
            # --- Market hours ------------------------------------------------
            elif not is_detector_active():
                sleep_seconds = seconds_until_detector_active()
                logger.info(
                    "Mercado cerrado. Durmiendo %d segundos hasta apertura.",
                    sleep_seconds,
                )
                time.sleep(min(sleep_seconds, 300))  # wake up periodically
                continue
            # --- Ensure IBKR --------------------------------------------------
            if not ibkr_client.ensure_connected():
                ibkr_connection_status.set(0)
                logger.error("IBKR no disponible, reintentando en 10s")
                time.sleep(10)
                continue
            
            ibkr_connection_status.set(1)
            
            spy_price = ibkr_client.get_spy_price()
            
            # ===== ENVIAR SPY MARKET SNAPSHOT =====
            if ibkr_client.spy_prev_close:
                try:
                    _post_spymarket(
                        spy_price=spy_price,
                        timestamp=int(time.time()),
                        previous_close=ibkr_client.spy_prev_close,
                        market_status=_get_market_status(),
                        bid=getattr(ibkr_client, 'spy_bid', None),
                        ask=getattr(ibkr_client, 'spy_ask', None),
                        last=spy_price,
                        volume=getattr(ibkr_client, 'spy_volume', None)
                    )
                except Exception as e:
                    logger.error(f"Error sending SPY market: {e}")
            # ======================================
            
            if spy_price is None:
                logger.warning("SPY price no disponible, retry en 5s")
                time.sleep(5)
                continue

            logger.debug("Precio SPY: %.2f", spy_price)
            spy_price_current.set(spy_price)         
          
            # POST market/state (solo primera vez o cambio de sesión)
            
            # ===== FALLBACK: Asegurar que hay previous_close =====
            if ibkr_client.spy_prev_close is None:
                ibkr_client.spy_prev_close = 693.15
                logger.warning("⚠️ Usando previous_close por defecto: 693.15")
            # =====================================================

            if not hasattr(ibkr_client, '_market_state_sent') or not ibkr_client._market_state_sent:
                if ibkr_client.spy_prev_close and ibkr_client.spy_prev_close > 0:
                    _post_spymarket(
                        spy_price=spy_price,  # cambio: current_price → spy_price
                        timestamp=int(time.time()),
                        previous_close=ibkr_client.spy_prev_close,
                        market_status=_get_market_status()
                    )
                    
                    ibkr_client._market_state_sent = True
                    ibkr_client._last_atm_center = round(spy_price)  # Inicializar

            
            # 1. Obtener datos y actualizar suscripciones
            options_data = ibkr_client.update_atm_subscriptions(spy_price)
            
            # 2. FILTRO CRITICO: Validar que existan datos reales antes de seguir.
            # Esto evita enviar volumenes en 0 o errores de calculo al backend.
            valid_options = [
                o for o in options_data
                if o['mid'] > 0 or o['bid'] > 0 or o['ask'] > 0
            ]
            
            if not valid_options:
                logger.info("Esperando flujo de datos de IBKR (datos actuales en cero o vacias)")
                time.sleep(1.5)
                continue

            # 3. Deteccion de Anomalias con datos validados
            raw_anomalies = detect_anomalies(valid_options, spy_price)
            
            if not raw_anomalies:
                logger.info("No se detectaron Anomalias en %d contratos validos", len(valid_options))
            else:
                anomalies: List[AnomaliesSnapshot] = []
                for raw in raw_anomalies:
                    try:
                        anomaly = _map_algo_anomaly_to_contract(raw)
                        anomalies.append(anomaly)
                    except Exception as e:
                        logger.error("Anomalia invalida | data=%s | error=%s", raw, e)

                if anomalies:
                # Incrementar métricas por severidad
                    for anomaly in anomalies:
                        anomalies_detected_total.labels(severity=anomaly.severity).inc()
                    _post_async(_post_anomalies, anomalies)
                
                # --- INICIO DEL BLOQUE AJUSTADO PARA FLUCTUACIÃ“N ---
            """try:
                raw_volumes = aggregate_atm_volumes(valid_options, spy_price)
                raw_volumes['spy_change_pct'] = 0.0  
                # AÃ±adir % cambio diario si disponible
                if ibkr_client.spy_prev_close and ibkr_client.spy_prev_close > 0:
                    raw_volumes['spy_change_pct'] = round(
                        ((spy_price - ibkr_client.spy_prev_close) / ibkr_client.spy_prev_close) * 100, 2
                    )

                snapshot = VolumesSnapshot(**raw_volumes)
                        
                logger.info(
                    f"Actividad ATM Detectada: CALLS={snapshot.calls_volume_atm} (+{snapshot.calls_volume_delta}), " 
                    f"PUTS={snapshot.puts_volume_atm} (+{snapshot.puts_volume_delta}) | SPY: {spy_price:.2f}"
                )

                _post_volumes(snapshot.model_dump(mode="json"))
            except ValidationError as ve:
                    logger.error("Error de validaciÃ³n Pydantic en VolÃºmenes: %s", ve)
            except Exception as e:
                    logger.error("Error procesando volÃºmenes ATM (fluctuaciÃ³n): %s", e)           
            """
        # --- NUEVO: PROCESAMIENTO DE SIGNED PREMIUM FLOW ---
            try:
                volume_tracker = get_volume_tracker()
                flow_aggregator = get_flow_aggregator()
    
                # --- VERIFICAR CAMBIO DE ATM ---
                current_atm_center = round(spy_price)
                if not hasattr(ibkr_client, '_last_atm_center') or ibkr_client._last_atm_center != current_atm_center:
                    # Enviar market state con nuevo ATM range
                    if ibkr_client.spy_prev_close and ibkr_client.spy_prev_close > 0:
                        _post_spymarket(
                            spy_price=spy_price,
                            timestamp=int(time.time()),
                            previous_close=ibkr_client.spy_prev_close,
                            market_status=_get_market_status()
                        )
                        ibkr_client._last_atm_center = current_atm_center
                        logger.info(f"ATM cambio: {current_atm_center} (enviado a backend)")
                        
                        
                # --- FIN VERIFICACION ---               
                                
                # Procesar cada opcion individualmente
                for option in valid_options:
                    call_flow, put_flow = volume_tracker.process_option_tick(option)
                    
                    # AÃ±adir al bucket temporal (cierra cada segundo)
                    bucket_result = flow_aggregator.add_signed_flow(call_flow, put_flow)
                    
                # Si el bucket cierra, enviar datos acumulados
                    if bucket_result:
                        from datetime import datetime
                        
                        timestamp_unix = bucket_result["timestamp"]
                        timestamp_iso = datetime.fromtimestamp(timestamp_unix).isoformat() + "Z"
                        
                        # FLOW LIMPIO - Solo opciones
                        flow_payload = {
                            "timestamp": bucket_result["timestamp"],
                            "cum_call_flow": round(volume_tracker.cum_call_flow, 2),
                            "cum_put_flow": round(volume_tracker.cum_put_flow, 2),
                            "net_flow": round(volume_tracker.cum_call_flow - volume_tracker.cum_put_flow, 2),
                            "spy_price": round(spy_price, 2)  # Para línea del chart
                        }
                        
                        logger.info(
                            f"Flow Update | Timestamp: {flow_payload['timestamp']} | "
                            f"Cum Calls: ${flow_payload['cum_call_flow']:,.0f} | "
                            f"Cum Puts: ${flow_payload['cum_put_flow']:,.0f} | "
                            f"Net: ${flow_payload['net_flow']:,.0f}"
                        )
                        # Enviar via SignalR al frontend
                        
                        _post_async(
                            requests.post,
                            f"{settings.backend_url}/flow",
                            json=flow_payload,
                            timeout=2
                        )
                                               
            except Exception as e:
                logger.error(f"Error procesando flow acumulado: {e}")
        # --- FIN NUEVO BLOQUE ---    
        # --- FIN DEL BLOQUE AJUSTADO ---
                
                
        except Exception as exc:
            scan_errors_total.labels(error_type=type(exc).__name__).inc()
            logger.exception("Error inesperado en loop principal: %s", exc)
        finally:
             # Record scan duration
            scan_duration = time.time() - scan_start_time
            scan_duration_seconds.observe(scan_duration)

            # â±ï¸ Intervalo entre scans
            time.sleep(settings.scan_interval_seconds)
            
            

    logger.info("Detector detenido limpiamente")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    run_detector_loop()
