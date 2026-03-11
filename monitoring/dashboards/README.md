# SPY Platform Grafana Dashboards

## Dashboard #1: SPY Platform Overview

### Acceso a Grafana:
- **URL:** http://192.168.1.134:32354
- **Usuario:** admin
- **Password:** admin123

### Importación Manual (Opción Rápida):

1. Accede a Grafana UI
2. Click en + (Create) > Import
3. Copia el contenido de `spy-platform-overview.json`
4. Click "Load" > "Import"

### Panels Incluidos:

1. **IBKR Connection Status** - Estado conexión IBKR Gateway (gauge)
   - Métrica: `ibkr_connection_status`
   - Verde = Connected, Rojo = Disconnected

2. **SPY Price (Current)** - Precio actual SPY (stat + graph)
   - Métrica: `spy_price_current`
   
3. **Anomalies Detected (Last Hour)** - Anomalías por severity (timeseries)
   - Métrica: `increase(anomalies_detected_total[1h])`
   - Colores: HIGH=Red, MEDIUM=Orange, LOW=Yellow

4. **Detector Scan Duration** - Performance del detector (timeseries)
   - Métricas: P95 y P50 de `scan_duration_seconds`
   
5. **Backend Request Rate** - Throughput HTTP por status (timeseries stacked)
   - Métrica: `sum(rate(http_requests_total[5m])) by (status)`
   
6. **Backend Latency P95** - Latencia 95 percentil (stat)
   - Métrica: `histogram_quantile(0.95, http_request_duration_seconds)`
   
7. **Options Scan Rate** - Velocidad scan CALL vs PUT (stat)
   - Métrica: `sum(rate(options_scanned_total[5m])) by (option_type)`

### Configuración:
- **Refresh:** 15 segundos (auto-refresh)
- **Time Range:** Last 1 hour (configurable)
- **Datasource:** Prometheus (uid: prometheus)

### Próximos Dashboards:
- **Dashboard #2:** Business Metrics (Flow total, Top anomalies)
- **Dashboard #3:** Infrastructure Health (CPU, Memory, PVC usage)

---
**Creado:** 2026-03-09 14:10 CET
**FASE 3:** Dashboards Grafana