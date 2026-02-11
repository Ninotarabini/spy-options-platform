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

import logging
import time
import signal
from datetime import datetime
from typing import List

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
from ibkr_client import ibkr_client
from anomaly_algo import detect_anomalies
from volume_aggregator import aggregate_atm_volumes
from models import Anomaly, AnomaliesResponse, VolumeSnapshot
from market_hours import is_detector_active, seconds_until_detector_active

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logger = logging.getLogger("detector")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

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

def _map_algo_anomaly_to_contract(raw: dict) -> Anomaly:
    """
    Mapea una anomalia producida por anomaly_algo.py
    al contrato oficial del backend (Pydantic).

    Falla rapido si falta algun campo.
    """

    option_type = "CALL" if raw["right"] == "C" else "PUT"

    return Anomaly(
        timestamp=datetime.fromisoformat(raw["timestamp"]),
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


def _post_anomalies(anomalies: List[Anomaly]) -> None:
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
    
    response = requests.post(
        url,
        json=payload.model_dump(mode="json"),
        timeout=10,
    )
    
    # Record backend request
    backend_requests_total.labels(
        method="POST",
        endpoint="/anomalies",
        status=str(response.status_code)
    ).inc()

    if response.status_code >= 400:
        logger.error(
            "Error enviando anomalias | status=%s | body=%s",
            response.status_code,
            response.text,
        )
        response.raise_for_status()

    logger.info("Anomali­as enviadas correctamente")

def _post_volumes(volume_data: dict) -> None:
    """
    Envia la ACTIVIDAD (deltas) al backend para ver fluctuaciones.
    """
    # Cambiamos el mapeo para que el backend reciba el delta como volumen principal si así lo deseas
    # O simplemente asegúrate de que tu modelo VolumeSnapshot acepte los deltas.
    
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
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Error enviando fluctuación: %s", e)

        
# -----------------------------------------------------------------------------
# Run detector
# -----------------------------------------------------------------------------

def run_detector_loop() -> None:
    logger.info("Iniciando detector (modo servicio)")
    
    # Prometheus metrics HTTP server
    start_http_server(9100)
    logger.info("Prometheus metrics server iniciado en puerto 9100")

    while RUNNING:
        
        scan_start_time = time.time()
        
        try:
            # --- Market hours ------------------------------------------------
            if not is_detector_active():
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
            if spy_price is None:
                logger.warning("SPY price no disponible, retry en 5s")
                time.sleep(5)
                continue

            logger.debug("Precio SPY: %.2f", spy_price)
            spy_price_current.set(spy_price)
            
            # 1. Obtener datos y actualizar suscripciones
            options_data = ibkr_client.update_atm_subscriptions(spy_price)
            
            # 2. FILTRO CRÍTICO: Validar que existan datos reales antes de seguir.
            # Esto evita enviar volúmenes en 0 o errores de cálculo al backend.
            valid_options = [o for o in options_data if o['volume'] > 0 or o['mid'] > 0]
            
            if not valid_options:
                logger.info("Esperando flujo de datos de IBKR (datos actuales en cero o vacíos)")
                continue

            # 3. Detección de anomalías con datos validados
            raw_anomalies = detect_anomalies(valid_options, spy_price)
            
            if not raw_anomalies:
                logger.info("No se detectaron anomalías en %d contratos válidos", len(valid_options))
            else:
                anomalies: List[Anomaly] = []
                for raw in raw_anomalies:
                    try:
                        anomaly = _map_anomaly_to_contract(raw)
                        anomalies.append(anomaly)
                    except Exception as e:
                        logger.error("Anomalía inválida | data=%s | error=%s", raw, e)

                if anomalies:
                    # Incrementar métricas por severidad
                    for anomaly in anomalies:
                        anomalies_detected_total.labels(severity=anomaly.severity).inc()
                        _post_anomalies(anomalies)
                
                # --- INICIO DEL BLOQUE AJUSTADO PARA FLUCTUACIÓN ---
                try:
                    # Usamos 'valid_options' para que el cálculo del delta sea sobre datos reales
                    volumes = aggregate_atm_volumes(valid_options, spy_price)
                
                    # Log informativo para verificar la fluctuación en consola
                    logger.info(
                       "Actividad ATM Detectada: CALLS +%d, PUTS +%d | SPY: %.2f",
                       volumes["calls_volume_delta"],
                       volumes["puts_volume_delta"],
                       spy_price
                    )
                
                    # Enviamos el snapshot que contiene los deltas al endpoint /volumes
                    _post_volumes(volumes)
                
                except Exception as e:
                     logger.error("Error procesando volúmenes ATM (fluctuación): %s", e)           
  
        # --- FIN DEL BLOQUE AJUSTADO ---
                
                
        except Exception as exc:
            scan_errors_total.labels(error_type=type(exc).__name__).inc()
            logger.exception("Error inesperado en loop principal: %s", exc)
        finally:
             # Record scan duration
            scan_duration = time.time() - scan_start_time
            scan_duration_seconds.observe(scan_duration)

            # ⏱️ Intervalo entre scans
            time.sleep(settings.scan_interval_seconds)
            
            

    logger.info("Detector detenido limpiamente")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    run_detector_loop()
