"""
Prometheus metrics for monitoring backend API.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST


# HTTP Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Anomaly Detection Metrics
anomalies_detected_total = Counter(
    'anomalies_detected_total',
    'Total anomalies detected',
    ['severity']
)

anomalies_current = Gauge(
    'anomalies_current',
    'Current anomalies in storage'
)

# SignalR Metrics
signals_broadcasted_total = Counter(
    'signals_broadcasted_total',
    'Total signals broadcasted to SignalR',
    ['action']
)

signalr_connection_status = Gauge(
    'signalr_connection_status',
    'SignalR connection status (1=connected, 0=disconnected)'
)

# Storage Metrics
storage_operations_total = Counter(
    'storage_operations_total',
    'Total Azure Table Storage operations',
    ['operation', 'status']
)
