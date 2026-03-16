"""
Azure SignalR REST API client (serverless mode).
Replaces Python SDK for broadcast-only operations.

v2: añadido broadcast_async() con httpx.AsyncClient para eliminar
    la sobrecarga de threads (asyncio.to_thread) en el backend FastAPI.
"""
import asyncio
import jwt
import time
from typing import Dict, Any
import logging

import httpx
import requests

from config import settings
from metrics import signalr_broadcast_latency_seconds

logger = logging.getLogger(__name__)

# Límites del pool de conexiones HTTP async hacia Azure SignalR
_HTTPX_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=30,
)


class SignalRRestClient:
    """REST API client for Azure SignalR serverless broadcast.

    Expone dos métodos de broadcast:
    - broadcast()       → síncrono (requests), para uso en threads/detector
    - broadcast_async() → async nativo (httpx), para endpoints FastAPI async
    """

    def __init__(self):
        self.endpoint = settings.azure_signalr_endpoint
        self.access_key = settings.azure_signalr_access_key
        # Cliente async compartido con connection pooling (se inicializa en startup)
        self._async_client: httpx.AsyncClient | None = None
        logger.info(f"SignalR REST client initialized: {self.endpoint}")

    async def init_async_client(self):
        """Inicializar el cliente async. Llamar desde FastAPI startup."""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                limits=_HTTPX_LIMITS,
                timeout=httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0),
            )
            logger.info("✅ httpx.AsyncClient inicializado con connection pooling")

    async def close_async_client(self):
        """Cerrar el cliente async limpiamente. Llamar desde FastAPI shutdown."""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
            logger.info("httpx.AsyncClient cerrado")

    def _generate_token(self, hub_name: str, ttl_seconds: int = 3600) -> str:
        """Generate JWT token for SignalR REST API authentication."""
        endpoint_url = f"{self.endpoint}/api/v1/hubs/{hub_name}"
        payload = {
            "aud": endpoint_url,
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl_seconds,
        }
        return jwt.encode(payload, self.access_key, algorithm="HS256")

    def broadcast(self, hub_name: str, event_name: str, data: Dict[Any, Any]) -> bool:
        """Broadcast síncrono (requests). Usado por el detector/threads."""
        try:
            url = f"{self.endpoint}/api/v1/hubs/{hub_name}"
            token = self._generate_token(hub_name)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = {"target": event_name, "arguments": [data]}
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            logger.debug(f"[OK] SignalR broadcast (sync): {event_name}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"[ERROR] SignalR broadcast failed ({event_name}): {e}")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error in SignalR broadcast: {e}")
            return False

    async def broadcast_async(
        self, hub_name: str, event_name: str, data: Dict[Any, Any]
    ) -> bool:
        """Broadcast async nativo con httpx (sin threads adicionales).

        Requiere que init_async_client() haya sido llamado en startup.
        """
        if self._async_client is None or self._async_client.is_closed:
            logger.warning("⚠️ async_client no inicializado, usando broadcast síncrono como fallback")
            return await asyncio.to_thread(self.broadcast, hub_name, event_name, data)

        try:
            url = f"{self.endpoint}/api/v1/hubs/{hub_name}"
            token = self._generate_token(hub_name)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = {"target": event_name, "arguments": [data]}
            
            with signalr_broadcast_latency_seconds.labels(event_name=event_name).time():
                response = await self._async_client.post(url, json=payload, headers=headers)
            
            response.raise_for_status()
            logger.debug(f"[OK] SignalR broadcast (async): {event_name}")
            return True
        except httpx.RequestError as e:
            logger.error(f"[ERROR] SignalR async broadcast failed ({event_name}): {e}")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error in async SignalR broadcast: {e}")
            return False


# Singleton instance
signalr_rest = SignalRRestClient()