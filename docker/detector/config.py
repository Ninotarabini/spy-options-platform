"""Configuration management for Detector service.
Loads settings from Kubernetes ConfigMap and Secrets via environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # IBKR Connection (from ConfigMap bot-config)
    ibkr_host: str = Field(default="ibkr-gateway-service", alias="IBKR_HOST")
    ibkr_port: int = Field(default=4003, alias="IBKR_PORT")
    ibkr_client_id: int = Field(default=1, alias="IBKR_CLIENT_ID")
    
    # IBKR Credentials (from Secret ibkr-credentials)
    ibkr_username: str = Field(alias="IBKR_USERNAME")
    ibkr_password: str = Field(alias="IBKR_PASSWORD")
    
    # Trading Parameters (from ConfigMap bot-config)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    strategy_type: str = Field(default="anomaly-arbitrage", alias="STRATEGY_TYPE")
    anomaly_threshold: float = Field(default=0.5, alias="ANOMALY_THRESHOLD")
    scan_interval_seconds: int = Field(default=30, alias="SCAN_INTERVAL_SECONDS")
    strikes_range_percent: float = Field(default=1.0, alias="STRIKES_RANGE_PERCENT")
    
    # Backend API (from ConfigMap bot-config)
    backend_url: str = Field(default="http://backend-service:8000", alias="BACKEND_URL")
    
    # Azure SignalR (from Secret azure-credentials) - Optional for detector
    azure_signalr_connection_string: str = Field(default="", alias="AZURE_SIGNALR_CONNECTION_STRING")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
