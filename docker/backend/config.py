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
    app_version: str = "1.1.0"
    
    class Config:
        """Pydantic config to read from environment variables."""
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
settings = Settings()
