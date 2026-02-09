"""
Azure SignalR REST API client (serverless mode).
Replaces Python SDK for broadcast-only operations.
"""
import requests
import jwt
import time
from typing import Dict, Any
import logging
from config import settings

logger = logging.getLogger(__name__)


class SignalRRestClient:
    """REST API client for Azure SignalR serverless broadcast."""
    
    def __init__(self):
        """Initialize with endpoint and access key from config."""
        self.endpoint = settings.azure_signalr_endpoint  # https://xxx.service.signalr.net
        self.access_key = settings.azure_signalr_access_key
        logger.info(f"SignalR REST client initialized: {self.endpoint}")
        
    def _generate_token(self, hub_name: str, ttl_seconds: int = 3600) -> str:
        """
        Generate JWT token for SignalR REST API authentication.
        
        Args:
            hub_name: SignalR hub name (e.g., 'spyoptions')
            ttl_seconds: Token validity duration (default: 1 hour)
            
        Returns:
            JWT token string
        """
        endpoint_url = f"{self.endpoint}/api/v1/hubs/{hub_name}"
        
        payload = {
            "aud": endpoint_url,
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl_seconds
        }
        
        return jwt.encode(payload, self.access_key, algorithm="HS256")
    
    def broadcast(self, hub_name: str, event_name: str, data: Dict[Any, Any]) -> bool:
        """
        Broadcast event to all connected clients via REST API.
        
        Args:
            hub_name: SignalR hub name (e.g., 'spyoptions')
            event_name: Event name clients listen for (e.g., 'anomalyDetected')
            data: Event payload as dictionary
            
        Returns:
            True if broadcast succeeded, False otherwise
        """
        try:
            url = f"{self.endpoint}/api/v1/hubs/{hub_name}"
            token = self._generate_token(hub_name)
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "target": event_name,
                "arguments": [data]
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            
            logger.info(f"✅ SignalR broadcast: {event_name} to hub '{hub_name}'")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ SignalR broadcast failed ({event_name}): {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error in SignalR broadcast: {e}")
            return False


# Singleton instance
signalr_rest = SignalRRestClient()