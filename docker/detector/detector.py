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
from config import settings
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
    Envia volumenes agregados ATM al backend.
    """
    # Convert dict to Pydantic model
    volume_snapshot = VolumeSnapshot(**volume_data)
    url = f"{settings.backend_url}/volumes"
    logger.info(
        "Enviando volúmenes ATM al backend: CALLS=%d, PUTS=%d, SPY=%.2f",
        volume_data["calls_volume_atm"],
        volume_data["puts_volume_atm"],
        volume_data["spy_price"],
    )
    try:
        response = requests.post(
            url,
            json=volume_snapshot.model_dump(mode="json"),
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Volúmenes enviados correctamente (status=%d)", response.status_code)
    except requests.exceptions.RequestException as e:
        logger.error("Error enviando volúmenes: %s", e)
        
        
# -----------------------------------------------------------------------------
# Run detector
# -----------------------------------------------------------------------------

def run_detector_loop() -> None:
    logger.info("Iniciando detector (modo servicio)")

    while RUNNING:
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
                logger.error("IBKR no disponible, reintentando en 10s")
                time.sleep(10)
                continue

            spy_price = ibkr_client.get_spy_price()
            if spy_price is None:
                logger.warning("SPY price no disponible, retry en 5s")
                time.sleep(5)
                continue

            logger.debug("Precio SPY: %.2f", spy_price)

            options_data = ibkr_client.get_0dte_options(spy_price)
            if not options_data:
                logger.info("Sin opciones 0DTE, siguiente ciclo")
                continue

            raw_anomalies = detect_anomalies(options_data, spy_price)
            if not raw_anomalies:
                logger.info("No se detectaron anomalías")
                continue

            anomalies: List[Anomaly] = []

            for raw in raw_anomalies:
                try:
                    anomaly = _map_algo_anomaly_to_contract(raw)
                    anomalies.append(anomaly)
                except Exception as e:
                    logger.error(
                        "Anomalía inválida | data=%s | error=%s",
                        raw,
                        e,
                    )

            if anomalies:
                _post_anomalies(anomalies)
                
            try:
                volumes = aggregate_atm_volumes(options_data, spy_price)
                _post_volumes(volumes)
            except Exception as e:
                logger.error("Error procesando volúmenes ATM: %s", e)           
                
        except Exception as exc:
            logger.exception("Error inesperado en loop principal: %s", exc)

        # ⏱️ Intervalo entre scans
        time.sleep(settings.scan_interval_seconds)

    logger.info("Detector detenido limpiamente")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    run_detector_loop()
