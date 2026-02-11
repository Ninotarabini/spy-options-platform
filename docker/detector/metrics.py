"""
Prometheus metrics for detector service.
"""
from prometheus_client import Counter, Gauge, Histogram

# IBKR Connection
ibkr_connection_status = Gauge(
    'ibkr_connection_status',
    'IBKR Gateway connection status (1=connected, 0=disconnected)'
)

ibkr_reconnection_attempts = Counter(
    'ibkr_reconnection_attempts_total',
    'Total IBKR reconnection attempts'
)

# Market Data
spy_price_current = Gauge(
    'spy_price_current',
    'Current SPY market price'
)

options_scanned_total = Counter(
    'options_scanned_total',
    'Total options contracts scanned',
    ['option_type']  # CALL/PUT
)

# Anomaly Detection
anomalies_detected_total = Counter(
    'anomalies_detected_total',
    'Total anomalies detected',
    ['severity']  # LOW/MEDIUM/HIGH
)

anomalies_per_scan = Histogram(
    'anomalies_per_scan',
    'Number of anomalies detected per scan',
    buckets=[0, 5, 10, 20, 50, 100]
)

# Backend Communication
backend_requests_total = Counter(
    'backend_requests_total',
    'Total HTTP requests to backend',
    ['method', 'endpoint', 'status']
)

backend_request_duration_seconds = Histogram(
    'backend_request_duration_seconds',
    'Backend request latency',
    ['endpoint']
)

# Scan Operations
scan_duration_seconds = Histogram(
    'scan_duration_seconds',
    'Time taken for complete scan cycle',
    buckets=[1, 5, 10, 30, 60, 120]
)

scan_errors_total = Counter(
    'scan_errors_total',
    'Total scan errors',
    ['error_type']
)