"""
Detector service entrypoint.

Responsabilidades:
- Obtener precio SPY y cadena de opciones vía IBKR
- Ejecutar algoritmo de detección de anomalías
- Normalizar resultados al contrato oficial del backend
- Enviar payload válido al endpoint /anomalies

Fuente de verdad del contrato:
- backend/models.py
- detector/models.py (idéntico)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import List

import requests
from pydantic import ValidationError

from config import settings
from ibkr_client import ibkr_client
from anomaly_algo import detect_anomalies
from models import Anomaly, AnomaliesResponse

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logger = logging.getLogger("detector")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _map_algo_anomaly_to_contract(raw: dict) -> Anomaly:
    """
    Mapea una anomalía producida por anomaly_algo.py
    al contrato oficial del backend (Pydantic).

    Falla rápido si falta algún campo.
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
    Envía anomalías al backend.
    Valida payload antes de enviar.
    """

    payload = AnomaliesResponse(
        count=len(anomalies),
        anomalies=anomalies,
        last_scan=datetime.utcnow(),
    )

    url = f"{settings.backend_url}/anomalies"

    logger.info(
        "Enviando %d anomalías al backend (%s)",
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
            "Error enviando anomalías | status=%s | body=%s",
            response.status_code,
            response.text,
        )
        response.raise_for_status()

    logger.info("Anomalías enviadas correctamente")


# -----------------------------------------------------------------------------
# Main flow
# -----------------------------------------------------------------------------

def run_detector() -> None:
    logger.info("Iniciando detector")

    # --- IBKR connection ------------------------------------------------------

    if not ibkr_client.ensure_connected():
        logger.critical("No se pudo conectar a IBKR")
        sys.exit(1)

    spy_price = ibkr_client.get_spy_price()
    if spy_price is None:
        logger.critical("No se pudo obtener el precio de SPY")
        sys.exit(1)

    logger.info("Precio SPY: %.2f", spy_price)

    options_data = ibkr_client.get_0dte_options(spy_price)
    if not options_data:
        logger.warning("No se obtuvo data de opciones 0DTE")
        return

    logger.info("Opciones recibidas: %d", len(options_data))

    # --- Detection ------------------------------------------------------------

    raw_anomalies = detect_anomalies(options_data, spy_price)
    if not raw_anomalies:
        logger.info("No se detectaron anomalías")
        return

    logger.info("Anomalías detectadas: %d", len(raw_anomalies))

    # --- Normalization & validation ------------------------------------------

    anomalies: List[Anomaly] = []

    for raw in raw_anomalies:
        try:
            anomaly = _map_algo_anomaly_to_contract(raw)
            anomalies.append(anomaly)
        except ValidationError as e:
            logger.error(
                "Anomalía inválida (contrato) | data=%s | error=%s",
                raw,
                e,
            )
        except KeyError as e:
            logger.error(
                "Campo faltante en anomalía | campo=%s | data=%s",
                e,
                raw,
            )

    if not anomalies:
        logger.warning("Todas las anomalías fueron inválidas")
        return

    # --- Send to backend ------------------------------------------------------

    _post_anomalies(anomalies)


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_detector()
    except Exception as exc:
        logger.exception("Fallo fatal del detector: %s", exc)
        raise
