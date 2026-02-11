"""
Configuration management using environment variables.
All variables are injected via Kubernetes ConfigMap and Secrets.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Azure Services (from azure-credentials secret)
    azure_signalr_connection_string: str
    azure_storage_connection_string: str
    appinsights_instrumentationkey: str
    
    # Azure SignalR REST API (parsed from connection string or explicit)
    azure_signalr_endpoint: Optional[str] = None
    azure_signalr_access_key: Optional[str] = None
    
    # IBKR Credentials (from azure-credentials secret - mixed)
    ibkr_username: str
    ibkr_password: str
    
    # IBKR Configuration (from bot-config configmap)
    ibkr_host: str = "ibkr-gateway-service"
    ibkr_port: int = 4002
    ibkr_client_id: int = 1
    
    # Trading Strategy (from bot-config configmap)
    strategy_type: str = "anomaly-arbitrage"
    anomaly_threshold: float = 0.15
    max_positions: int = 5
    strikes_range_percent: float = 1.0
    scan_interval_seconds: int = 60
    
    # Logging (from bot-config configmap)
    log_level: str = "INFO"
    
    # Application
    app_name: str = "SPY Options Backend API"
    app_version: str = "1.8.0"  # ← Actualizado
    
    def __init__(self, **kwargs):
        """Initialize and parse SignalR connection string if needed."""
        super().__init__(**kwargs)
        
        # If endpoint/key not explicitly provided, parse from connection string
        if not self.azure_signalr_endpoint or not self.azure_signalr_access_key:
            self._parse_signalr_connection_string()
    
    def _parse_signalr_connection_string(self):
        """Extract endpoint and access key from connection string."""
        # Format: Endpoint=https://xxx.service.signalr.net;AccessKey=xxx;Version=1.0;
        try:
            parts = self.azure_signalr_connection_string.split(';')
            for part in parts:
                if part.startswith('Endpoint='):
                    self.azure_signalr_endpoint = part.replace('Endpoint=', '').strip()
                elif part.startswith('AccessKey='):
                    self.azure_signalr_access_key = part.replace('AccessKey=', '').strip()
        except Exception as e:
            raise ValueError(f"Failed to parse SignalR connection string: {e}")
    
    class Config:
        """Pydantic config to read from environment variables."""
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
settings = Settings()