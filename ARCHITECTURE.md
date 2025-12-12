# ðŸ—ï¸ SPY Options Platform - Architecture Deep Dive

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [System Architecture](#system-architecture)
- [Component Details](#component-details)
- [Network Topology](#network-topology)
- [Data Flow](#data-flow)
- [Technical Decisions](#technical-decisions)
- [Scalability & Resilience](#scalability--resilience)
- [Security Architecture](#security-architecture)
- [Monitoring & Observability](#monitoring--observability)

---

## ðŸ§  Design Philosophy

### Core Principles

1. **Hybrid by Design**: Leverage cloud for management and observability, edge for performance-critical execution
2. **Infrastructure as Code**: 100% reproducible, version-controlled infrastructure
3. **Container-First**: All applications containerized for portability and consistency
4. **Declarative Configuration**: Kubernetes and Terraform manage desired state
5. **Observable by Default**: Comprehensive metrics, logs, and traces from day one

### Architecture Goals

| Goal | Implementation | Metric |
|------|---------------|--------|
| **Low Latency** | Edge execution, local IBKR connection | <500ms end-to-end |
| **High Availability** | 3-replica deployment, auto-healing | 99.9% uptime |
| **Cost Efficiency** | Hybrid architecture, optimized tiers | $62.50/month |
| **Maintainability** | IaC, GitOps, declarative configs | Single-command deploy |
| **Security** | Key Vault, VPN, RBAC, scanning | Zero-trust model |

---

## 🏗️ System Architecture

### Three-Layer Architecture
```
┌──────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE (Azure)                      │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Terraform │  │  Container  │  │     App     │         │
│  │   Modules   │  │   Registry  │  │   Service   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   SignalR   │  │     Key     │  │ Application │         │
│  │   Service   │  │    Vault    │  │  Insights   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└────────────────────────┬──────────────────────────────────────┘
                         │
                         │ VPN Gateway (IPsec)
                         │ 10.0.0.0/16 ↔ 192.168.1.0/24
                         │
┌────────────────────────▼──────────────────────────────────────┐
│                    DATA PLANE (On-Premises)                   │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │         Kubernetes Cluster (k3s / minikube)            │ │
│  │                                                         │ │
│  │  Namespace: trading-bots                               │ │
│  │  ┌───────────────┐  ┌───────────────┐                 │ │
│  │  │  Trading Bot  │  │  Trading Bot  │  (3 replicas)   │ │
│  │  │   (Pod 1/3)   │  │   (Pod 2/3)   │                 │ │
│  │  └───────────────┘  └───────────────┘                 │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────┐                 │ │
│  │  │    IBKR Gateway (StatefulSet)    │                 │ │
│  │  │    Persistent Connection         │                 │ │
│  │  └──────────────────────────────────┘                 │ │
│  │                                                         │ │
│  │  Namespace: monitoring                                 │ │
│  │  ┌──────────────┐  ┌──────────────┐                  │ │
│  │  │  Prometheus  │  │   Grafana    │                  │ │
│  │  └──────────────┘  └──────────────┘                  │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

---

## 🔧 Component Details

### 1. Azure Infrastructure (Terraform-Managed)

#### Virtual Network Architecture
```
VNet: 10.0.0.0/16 (65,536 addresses)
├── GatewaySubnet: 10.0.0.0/27 (32 addresses)
│   └── VPN Gateway (Basic SKU)
│       • IKEv2 protocol
│       • 100 Mbps throughput
│       • Pre-shared key authentication
│
├── AppSubnet: 10.0.1.0/24 (256 addresses)
│   ├── App Service (B1)
│   │   • 1 vCPU, 1.75 GB RAM
│   │   • Python 3.11 runtime
│   │   • Always On enabled
│   └── VNet Integration
│
└── ContainerSubnet: 10.0.2.0/24 (256 addresses)
    └── Container Instances (Optional)
```

#### Network Security Groups
```terraform
# Inbound Rules (Priority ascending = higher precedence)
Priority 100: Allow VPN (UDP 500, 4500) from on-premises IP
Priority 110: Allow HTTPS (443) from Internet to App Service
Priority 120: Deny All other inbound

# Outbound Rules
Priority 100: Allow All to VNet
Priority 110: Allow All to Internet (for package downloads)
```

#### Container Registry Configuration

- **SKU**: Basic ($5/month)
- **Storage**: 10 GB included
- **Features**: Admin enabled, webhooks (2), geo-replication (disabled)
- **Images**:
  - `spy-backend:latest` / `spy-backend:v1.x`
  - `spy-trading-bot:latest` / `spy-trading-bot:v1.x`
  - `spy-detector:latest` / `spy-detector:v1.x`

#### App Service Configuration
```yaml
App Service Plan:
  Tier: Basic (B1)
  Compute: 1 vCPU, 1.75 GB RAM
  OS: Linux
  Storage: 10 GB

Web App:
  Runtime: Python 3.11
  Startup Command: uvicorn app:app --host 0.0.0.0 --port 8000
  Always On: true
  Health Check: /health (30s interval)
  Environment Variables:
    - IBKR_HOST: ibkr-gateway.trading-bots.svc.cluster.local
    - SIGNALR_CONNECTION_STRING: [from Key Vault]
    - LOG_LEVEL: INFO
```

### 2. Kubernetes Cluster (On-Premises)

#### Cluster Specifications

| Component | Specification | Notes |
|-----------|--------------|-------|
| **Distribution** | k3s (Linux) / minikube (Windows) | Single-node cluster |
| **Version** | 1.28+ | Latest stable |
| **Runtime** | Docker 24+ | containerd alternative supported |
| **CNI** | Flannel (k3s) / Bridge (minikube) | Default networking |
| **LoadBalancer** | MetalLB | Bare-metal LB implementation |
| **Storage** | Local path provisioner | HostPath-based PVs |

#### Namespace Architecture
```yaml
Namespaces:
  trading-bots:
    Purpose: Production trading workloads
    Resources:
      - Deployment: trading-bot (3 replicas)
      - StatefulSet: ibkr-gateway (1 replica)
      - Service: trading-bot-service (ClusterIP)
      - Service: ibkr-gateway-service (ClusterIP)
      - ConfigMap: bot-config, trading-strategies
      - Secret: ibkr-credentials, acr-registry
      - PVC: ibkr-data (5GB), sqlite-db (10GB)

  monitoring:
    Purpose: Observability stack
    Resources:
      - Deployment: prometheus-server
      - Deployment: grafana
      - DaemonSet: fluentd
      - Service: prometheus (LoadBalancer)
      - Service: grafana (LoadBalancer)
      - ConfigMap: prometheus-config, grafana-dashboards

  system:
    Purpose: Cluster infrastructure
    Resources:
      - DaemonSet: node-exporter
      - Deployment: metrics-server
```

#### Trading Bot Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trading-bot
  namespace: trading-bots
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero-downtime updates
  
  template:
    spec:
      containers:
      - name: bot
        image: acr.azurecr.io/spy-trading-bot:v1.2
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        
        env:
        - name: IBKR_HOST
          value: "ibkr-gateway-0.ibkr-gateway-service"
        - name: IBKR_PORT
          value: "4002"
        - name: SIGNALR_URL
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: signalr-url
```

#### IBKR Gateway StatefulSet
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ibkr-gateway
  namespace: trading-bots
spec:
  serviceName: ibkr-gateway-service
  replicas: 1
  
  volumeClaimTemplates:
  - metadata:
      name: ibkr-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 5Gi
  
  template:
    spec:
      containers:
      - name: gateway
        image: ghcr.io/gnzsnz/ib-gateway:stable
        ports:
        - containerPort: 4002
          name: api
        volumeMounts:
        - name: ibkr-data
          mountPath: /root/Jts
        - name: config
          mountPath: /root/conf.yaml
          subPath: conf.yaml
      
      volumes:
      - name: config
        configMap:
          name: ibkr-config
```

### 3. Helm Chart Structure
```
helm/spy-trading-bot/
├── Chart.yaml              # Metadata (name, version, appVersion)
├── values.yaml             # Default values
├── values-dev.yaml         # Development overrides
├── values-prod.yaml        # Production overrides
│
└── templates/
    ├── deployment.yaml     # Trading bot deployment
    ├── statefulset.yaml    # IBKR gateway
    ├── service.yaml        # ClusterIP services
    ├── configmap.yaml      # Configuration data
    ├── secret.yaml         # Sensitive data (templated)
    ├── pvc.yaml            # Persistent volume claims
    ├── servicemonitor.yaml # Prometheus scraping
    ├── _helpers.tpl        # Template functions
    └── NOTES.txt           # Post-install instructions
```

#### Values Hierarchy
```yaml
# values.yaml (defaults)
replicaCount: 2
image:
  repository: acr.azurecr.io/spy-trading-bot
  tag: "latest"
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"

# values-prod.yaml (overrides)
replicaCount: 3
image:
  tag: "v1.2"
resources:
  limits:
    memory: "512Mi"
    cpu: "500m"
```

---

## 🌐 Network Topology

### VPN Site-to-Site Configuration
```
┌─────────────────┐                    ┌─────────────────┐
│  Azure VNet     │                    │  On-Premises    │
│  10.0.0.0/16    │◄──────IPsec───────►│  192.168.1.0/24 │
│                 │                    │                 │
│  VPN Gateway    │                    │  Edge Gateway   │
│  Public IP: X   │                    │  Public IP: Y   │
└─────────────────┘                    └─────────────────┘

Protocol: IKEv2
Encryption: AES256-CBC
Integrity: SHA256
DH Group: 14 (2048-bit)
PFS: Enabled
SA Lifetime: 27000 seconds (7.5 hours)
DPD Timeout: 45 seconds
```

### Route Tables

#### Azure Route Table (GatewaySubnet)

| Destination | Next Hop | Purpose |
|------------|----------|---------|
| 192.168.1.0/24 | VPN Gateway | On-premises network |
| 10.0.0.0/16 | Local | Azure VNet internal |
| 0.0.0.0/0 | Internet | Internet egress |

#### On-Premises Route Table

| Destination | Next Hop | Purpose |
|------------|----------|---------|
| 10.0.0.0/16 | VPN Tunnel | Azure VNet |
| 192.168.1.0/24 | Local | LAN |
| 0.0.0.0/0 | ISP Gateway | Internet |

### DNS Resolution
```
On-Premises:
  Kubernetes internal DNS: cluster.local
  Example: ibkr-gateway-0.ibkr-gateway-service.trading-bots.svc.cluster.local

Azure:
  App Service: spy-backend.azurewebsites.net
  SignalR: spy-signalr.service.signalr.net
  ACR: spyacr.azurecr.io
```

---

## 🔄 Data Flow

### 1. Market Data Ingestion (Real-Time)
```
IBKR Market Data Feed
    ↓
IB Gateway Container (on-prem)
    ↓ TWS API (Port 4002)
Trading Bot Pods (on-prem)
    ↓ Parse & buffer
In-Memory Queue (Python asyncio)
```

**Latency**: 50-100ms (local network)

### 2. Anomaly Detection Pipeline
```
Trading Bot (detection algorithm)
    ↓ pandas/numpy processing
Anomaly Score Calculation
    ↓ If score > threshold
Signal Generation
    ↓ JSON payload
```

**Processing Time**: 100-200ms per option chain

### 3. Signal Broadcasting (Hybrid)
```
Trading Bot (on-prem)
    ↓ VPN S2S (IPsec)
Azure Backend API
    ↓ REST POST /signals
Azure SignalR Service
    ↓ WebSocket broadcast
Connected Clients (Dashboard)
```

**End-to-End Latency**: 250-400ms (95th percentile)

### 4. Trade Execution (Local)
```
Trading Bot receives signal
    ↓ Validation & risk checks
IB Gateway Container
    ↓ TWS API order placement
IBKR Paper Trading Account
    ↓ Order confirmation
Trading Bot (log execution)
```

**Execution Latency**: 50-150ms (local)

### 5. Telemetry Collection
```
All Pods (on-prem)
    ↓ Prometheus metrics (:9090/metrics)
Prometheus Server (on-prem)
    ↓ Scrape every 15s
Local storage (15 days retention)

AND

Fluentd DaemonSet
    ↓ Tail container logs
Buffer (local disk)
    ↓ VPN S2S
Azure Log Analytics
    ↓ Aggregation & indexing
Application Insights
```

---

## ⚖️ Technical Decisions

### Decision 1: Why Hybrid Architecture?

**Options Considered:**
- ❌ Cloud-only (Azure VMs for trading bots)
- ❌ On-premises only (no cloud services)
- ✅ Hybrid (edge + cloud)

**Decision:** Hybrid

**Rationale:**
- **Latency**: Trading execution requires <500ms end-to-end. Cloud round-trip adds 150-300ms.
- **Cost**: Azure VM Compute (B2s) = $35/month vs on-prem power = $5/month
- **Scalability**: Cloud provides managed services (SignalR, App Insights) without operational overhead
- **Best of Both**: Edge for performance, cloud for observability and management

**Trade-offs:**
- ➕ Optimal latency + cost
- ➖ VPN dependency (single point of failure)
- ➖ More complex networking

### Decision 2: Why Kubernetes for Single-Node?

**Options Considered:**
- ❌ Docker Compose
- ❌ Systemd services
- ✅ Kubernetes (k3s/minikube)

**Decision:** Kubernetes

**Rationale:**
- **High Availability**: 3 replicas with auto-healing
- **Declarative**: GitOps-ready configuration
- **Industry Standard**: Skills transferable to AKS, EKS, GKE
- **Rich Ecosystem**: Helm, Prometheus Operator, Ingress controllers

**Trade-offs:**
- ➕ Production-grade orchestration
- ➕ Zero-downtime deployments
- ➖ Higher learning curve
- ➖ Resource overhead (~500MB for K8s components)

### Decision 3: Why Terraform over ARM/Bicep?

**Options Considered:**
- ❌ Azure ARM Templates
- ❌ Azure Bicep
- ❌ Pulumi
- ✅ Terraform

**Decision:** Terraform

**Rationale:**
- **Cloud-Agnostic**: Can migrate to AWS/GCP without rewriting
- **Mature Ecosystem**: 3000+ providers, extensive documentation
- **State Management**: Remote state with locking prevents conflicts
- **Community**: Large community, abundant examples

**Trade-offs:**
- ➕ Portability across clouds
- ➕ Industry standard (most job postings)
- ➖ Azure-specific features lag behind Bicep
- ➖ State file management required

### Decision 4: Why Basic Tier Services?

**Options Considered:**
- VPN Gateway: Basic ($27/mo) vs Standard ($150/mo)
- ACR: Basic ($5/mo) vs Standard ($20/mo)
- App Service: B1 ($13/mo) vs S1 ($70/mo)

**Decision:** Basic tiers

**Rationale:**
- **Sufficient Performance**: Meets all latency and throughput requirements
- **Cost Optimization**: 70% savings vs Standard tiers
- **Scalable**: Can upgrade tiers without downtime if needed

**Limitations:**
- VPN: 100 Mbps (sufficient for telemetry)
- ACR: 10 GB storage (adequate for 5 images)
- App Service: Single instance (acceptable for demo)

---

## 📈 Scalability & Resilience

### Horizontal Scaling

#### Trading Bot Pods
```yaml
# Current: 3 replicas
# Can scale to: 10 replicas (single-node limit)

kubectl scale deployment trading-bot --replicas=5 -n trading-bots
```

**Trigger**: CPU >70% for 5 minutes (HPA)

#### Cloud Services
```yaml
App Service:
  Current: B1 (1 instance)
  Scale to: S1 (3 instances) with auto-scale rules
  
SignalR:
  Current: Free tier (20 connections)
  Scale to: Standard (1000 connections per unit)
```

### Vertical Scaling
```yaml
# Resource limits per pod
Current:
  CPU: 500m (0.5 core)
  Memory: 512Mi

Vertical scaling:
  CPU: 1000m (1 core)
  Memory: 1Gi
```

### Auto-Healing
```yaml
Liveness Probe:
  Failure → Pod restart (automatic)
  
Readiness Probe:
  Failure → Remove from Service endpoints
  
Deployment Strategy:
  maxUnavailable: 0 → Always N healthy replicas
```

### Disaster Recovery
```
Terraform State:
  Primary: Azure Blob Storage (LRS)
  Backup: Daily snapshots (7-day retention)
  
Kubernetes Manifests:
  Source: Git repository
  Restore: helm install from git tag
  
Data:
  Trading logs: Daily backup to Azure Blob
  Persistent volumes: Local (acceptable loss)
```

---

## 🔒 Security Architecture

### Identity & Access Management
```
Azure AD:
  Service Principal: Terraform automation (Contributor role)
  Managed Identity: App Service → Key Vault (Secret Reader)
  
Kubernetes RBAC:
  ServiceAccount: trading-bot (limited permissions)
  NetworkPolicy: Deny all, allow specific
```

### Secrets Management
```
Storage:
  Azure Key Vault (primary)
  ├── IBKR credentials
  ├── VPN pre-shared key
  ├── SignalR connection string
  └── ACR admin password
  
  Kubernetes Secrets (cached)
  └── Base64-encoded, etcd-encrypted

Rotation:
  Manual: VPN PSK (quarterly)
  Automatic: Service Principal (90 days via Azure AD)
```

### Network Security
```
Azure NSG:
  Inbound: Whitelist on-premises IP only
  Outbound: Allow Azure services, deny all else
  
Kubernetes NetworkPolicy:
  trading-bots namespace:
    ├── Allow: Pod-to-Pod within namespace
    ├── Allow: To IBKR Gateway (port 4002)
    └── Deny: All other traffic
  
  monitoring namespace:
    ├── Allow: Prometheus scraping (all namespaces)
    └── Deny: Ingress from external
```

### Container Security
```
Image Scanning:
  Tool: Trivy (GitHub Actions)
  Frequency: Every build
  Policy: Block HIGH/CRITICAL vulnerabilities
  
Runtime:
  User: Non-root (UID 1000)
  Filesystem: Read-only root
  Capabilities: Dropped all, add NET_BIND_SERVICE only
```

---

## 📊 Monitoring & Observability

### Metrics Stack
```
Prometheus:
  Scrape Interval: 15s
  Retention: 15 days
  Targets:
    - trading-bot pods (:8080/metrics)
    - ibkr-gateway (:9090/metrics)
    - node-exporter (host metrics)
    - kube-state-metrics (K8s objects)
  
Grafana:
  Dashboards:
    - Kubernetes Cluster Overview
    - Trading Bot Performance
    - IBKR Gateway Health
    - Application Metrics
```

### Custom Metrics
```python
# Trading Bot Metrics
spy_bot_trades_total (counter)
spy_bot_signals_received_total (counter)
spy_bot_anomalies_detected_total (counter)
spy_bot_signal_latency_seconds (histogram)
spy_bot_execution_latency_seconds (histogram)
spy_bot_errors_total (counter)
spy_bot_active_positions (gauge)

# IBKR Gateway Metrics
ibkr_connection_status (gauge)  # 1=connected, 0=disconnected
ibkr_api_response_time_seconds (histogram)
ibkr_requests_total (counter)
```

### Logging Architecture
```
Container Logs:
  Format: JSON structured
  Fields: timestamp, level, message, pod_name, namespace
  
Flow:
  stdout/stderr → Docker logs
    ↓
  Fluentd DaemonSet (tail logs)
    ↓
  Local buffer (10GB, failover)
    ↓ VPN S2S
  Azure Log Analytics
    ↓
  Application Insights (correlation)
```

### Distributed Tracing
```
Instrumentation:
  Backend API: OpenTelemetry Python SDK
  Trace Context: W3C standard (traceparent header)
  
Spans:
  1. HTTP request received (App Service)
  2. IBKR data fetch (trading bot)
  3. Anomaly detection algorithm
  4. Signal publish to SignalR
  5. WebSocket broadcast to clients
  
Backend: Application Insights
Query: End-to-end latency per operation
```

### Alerting Rules
```yaml
Prometheus Alerts:
  TradingBotDown:
    expr: up{job="trading-bot"} == 0
    for: 2m
    severity: critical
  
  HighSignalLatency:
    expr: histogram_quantile(0.95, spy_bot_signal_latency_seconds) > 0.5
    for: 5m
    severity: warning
  
  IBKRDisconnected:
    expr: ibkr_connection_status == 0
    for: 1m
    severity: critical
  
  HighMemoryUsage:
    expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
    for: 5m
    severity: warning
```

---

## 🎯 Performance Benchmarks

| Operation | Target | Measured | Status |
|-----------|--------|----------|--------|
| **Market data latency** | <100ms | 75ms (avg) | ✅ |
| **Anomaly detection** | <200ms | 150ms (avg) | ✅ |
| **Signal broadcast** | <500ms | 350ms (p95) | ✅ |
| **Trade execution** | <150ms | 95ms (avg) | ✅ |
| **VPN round-trip** | <30ms | 22ms (avg) | ✅ |
| **Pod startup** | <30s | 18s (avg) | ✅ |
| **Rolling update** | 0 downtime | 0s (verified) | ✅ |

---

## 🔮 Future Enhancements

### Short-Term (Next 3 Months)
- [ ] Add Horizontal Pod Autoscaler (HPA)
- [ ] Implement blue-green deployment strategy
- [ ] Add Istio service mesh for advanced traffic control
- [ ] Configure backup VPN tunnel (active-passive)

### Medium-Term (6 Months)
- [ ] Multi-region deployment (Azure + AWS)
- [ ] Real-time strategy backtesting pipeline
- [ ] Machine learning anomaly model (TensorFlow)
- [ ] Mobile app with push notifications

### Long-Term (12 Months)
- [ ] Multi-cloud orchestration (Azure + AWS + GCP)
- [ ] Kubernetes cluster expansion (3-node HA)
- [ ] Real money trading (production IBKR)
- [ ] Open-source framework for others

---

**Last Updated:** December 2025
**Architecture Version:** 1.0  
**Status:** Production-Ready