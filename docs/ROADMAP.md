# 🗺️ SPY Options Platform - Implementation Roadmap

## Overview

Phase-by-phase technical implementation guide for deploying the complete hybrid cloud trading platform.

**Total Duration:** 3-4 weeks (part-time, 2-3h/day)  
**Phases:** 10  
**Approach:** Incremental, test after each phase

---

## 📋 Implementation Phases

| Phase | Name | Duration | Deliverable |
|-------|------|----------|-------------|
| 0 | Environment Setup | 3-4 days | Tools installed, accounts configured |
| 1 | Azure Infrastructure (Terraform) | 5-7 days | All Azure resources deployed |
| 2 | Docker Containers | 4-5 days | All applications containerized |
| 3 | Kubernetes Cluster | 5-7 days | On-premises orchestration ready |
| 4 | Helm Charts | 2-3 days | Declarative deployments |
| 5 | Monitoring Stack | 2-3 days | Prometheus + Grafana operational |
| 6 | CI/CD Pipeline | 3-4 days | Automated build & deploy |
| 7 | VPN Configuration | 2-3 days | Hybrid connectivity established |
| 8 | Frontend Dashboard | 3-4 days | Real-time visualization |
| 9 | Trading Logic | 4-5 days | IBKR integration + detection |
| 10 | Testing & Optimization | 2-3 days | End-to-end validation |

---

## Phase 0: Environment Setup

**Goal:** All tools installed and accounts configured

### 0.1 Azure Account

1. Create Azure account: https://azure.microsoft.com/free
2. Activate €200 free credits (30 days)
3. Configure cost alerts (80%, 90%, 100% of budget)
4. Set spending limit if needed

**Docs:** [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/quick-acm-cost-analysis)

### 0.2 Interactive Brokers

1. Open Paper Trading account: https://www.interactivebrokers.com/en/trading/paper-trading.php
2. Request US Options market data subscription (~$4.50/month)
3. Download IB Gateway or TWS
4. Note credentials and API settings

**Docs:** [IBKR Paper Trading](https://www.interactivebrokers.com/en/trading/paper-trading.php)

### 0.3 Install Local Tools
```bash
# Verify installations
docker --version        # Should be 24.0+
kubectl version         # Client version shown
helm version            # v3.x
terraform --version     # 1.6+
az --version            # Azure CLI
git --version           # 2.x
python --version        # 3.11+
```

**Installation Links:**
- Docker: https://docs.docker.com/get-docker/
- kubectl: https://kubernetes.io/docs/tasks/tools/
- Helm: https://helm.sh/docs/intro/install/
- Terraform: https://developer.hashicorp.com/terraform/install
- Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli
- Python: https://www.python.org/downloads/

### 0.4 GitHub Repository

1. Create private repo: `spy-options-platform`
2. Clone locally
3. Copy project structure from this repo
4. Initial commit with README
```bash
git clone https://github.com/YOUR-USERNAME/spy-options-platform.git
cd spy-options-platform
git add .
git commit -m "Initial project structure"
git push origin main
```

### ✅ Phase 0 Checklist

- [ ] Azure account created, cost alerts configured
- [ ] IBKR Paper Trading account active
- [ ] All tools installed and verified
- [ ] GitHub repo created and cloned
- [ ] VS Code installed with extensions

---

## Phase 1: Azure Infrastructure (Terraform)

**Goal:** Deploy all Azure resources using Infrastructure as Code

### 1.1 Terraform Setup
```bash
cd terraform
terraform init
```

**Create:** `providers.tf`
```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
  }
}

provider "azurerm" {
  features {}
}
```

**Docs:** [Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)

### 1.2 Resource Group & Networking

**Resources to create:**
- Resource Group
- Virtual Network (10.0.0.0/16)
- Subnets (GatewaySubnet, AppSubnet, ContainerSubnet)
- Network Security Groups

**Docs:**
- [azurerm_resource_group](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group)
- [azurerm_virtual_network](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/virtual_network)

### 1.3 VPN Gateway

**Note:** Takes 30-45 minutes to provision
```hcl
resource "azurerm_virtual_network_gateway" "vpn" {
  name                = "spy-vpn-gateway"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  
  type     = "Vpn"
  vpn_type = "RouteBased"
  
  sku = "Basic"
  
  ip_configuration {
    name                          = "vnetGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.vpn.id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway.id
  }
}
```

**Docs:** [VPN Gateway](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/virtual_network_gateway)

### 1.4 Container Registry
```hcl
resource "azurerm_container_registry" "acr" {
  name                = "spyoptionsacr"  # Must be globally unique
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
}
```

**Docs:** [ACR](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_registry)

### 1.5 App Service
```hcl
resource "azurerm_service_plan" "main" {
  name                = "spy-app-service-plan"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "B1"
}

resource "azurerm_linux_web_app" "backend" {
  name                = "spy-backend-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_service_plan.main.location
  service_plan_id     = azurerm_service_plan.main.id
  
  site_config {
    always_on = true
    application_stack {
      python_version = "3.11"
    }
  }
}
```

**Docs:** [App Service](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/linux_web_app)

### 1.6 SignalR Service
```hcl
resource "azurerm_signalr_service" "main" {
  name                = "spy-signalr"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  
  sku {
    name     = "Free_F1"
    capacity = 1
  }
  
  service_mode = "Default"
}
```

**Docs:** [SignalR](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/signalr_service)

### 1.7 Storage & Key Vault

**Storage Account:** For Table Storage and Terraform remote state
**Key Vault:** For secrets management

**Docs:**
- [Storage Account](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account)
- [Key Vault](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault)

### 1.8 Application Insights
```hcl
resource "azurerm_application_insights" "main" {
  name                = "spy-app-insights"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  application_type    = "web"
}
```

### 1.9 Static Web App
```hcl
resource "azurerm_static_site" "frontend" {
  name                = "spy-dashboard"
  resource_group_name = azurerm_resource_group.main.name
  location            = "westeurope"
  sku_tier            = "Free"
  sku_size            = "Free"
}
```

### 1.10 Deploy Infrastructure
```bash
# Review changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan

# Verify in Azure Portal
```

### ✅ Phase 1 Checklist

- [ ] Resource Group created
- [ ] VNet and subnets configured
- [ ] VPN Gateway provisioned (wait 30-45 min)
- [ ] Container Registry accessible
- [ ] App Service deployed
- [ ] SignalR Service ready
- [ ] Storage Account created
- [ ] Key Vault configured
- [ ] Application Insights active
- [ ] Static Web App deployed

---

## Phase 2: Docker Containers

**Goal:** Containerize all applications and push to ACR

### 2.1 Backend API Dockerfile

**File:** `docker/backend/Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**File:** `docker/backend/requirements.txt`
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
ib-insync==0.9.86
pandas==2.1.3
numpy==1.26.2
azure-signalr==1.1.0
prometheus-client==0.19.0
```

### 2.2 Trading Bot Dockerfile

**File:** `docker/bot/Dockerfile`
```dockerfile
FROM python:3.11-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser -D -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

EXPOSE 8080

CMD ["python", "trading_bot.py"]
```

### 2.3 Build and Push Images
```bash
# Login to ACR
az acr login --name spyoptionsacr

# Build images
docker build -t spyoptionsacr.azurecr.io/spy-backend:v1.0 ./docker/backend
docker build -t spyoptionsacr.azurecr.io/spy-bot:v1.0 ./docker/bot
docker build -t spyoptionsacr.azurecr.io/spy-detector:v1.0 ./docker/detector

# Push to ACR
docker push spyoptionsacr.azurecr.io/spy-backend:v1.0
docker push spyoptionsacr.azurecr.io/spy-bot:v1.0
docker push spyoptionsacr.azurecr.io/spy-detector:v1.0

# Verify
az acr repository list --name spyoptionsacr --output table
```

### 2.4 IBKR Gateway Configuration

Use existing image: `ghcr.io/gnzsnz/ib-gateway:stable`

**File:** `docker/ibkr-gateway/config.ini`
```ini
[IBGateway]
Username=your_paper_username
Password=your_paper_password
TradingMode=paper
ApiPort=4002
```

### ✅ Phase 2 Checklist

- [ ] Backend Dockerfile created and optimized
- [ ] Trading bot Dockerfile created
- [ ] Detector Dockerfile created
- [ ] All images built successfully
- [ ] Images pushed to ACR
- [ ] IBKR Gateway configured

---

## Phase 3: Kubernetes Cluster

**Goal:** Deploy and configure on-premises Kubernetes cluster

### 3.1 Install Kubernetes

**Linux (k3s):**
```bash
curl -sfL https://get.k3s.io | sh -
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
```

**Windows/Mac (minikube):**
```bash
minikube start --cpus=4 --memory=8192 --driver=docker
minikube addons enable metrics-server
```

**Verify:**
```bash
kubectl cluster-info
kubectl get nodes
```

### 3.2 Create Namespaces

**File:** `kubernetes/namespaces/trading-bots.yaml`
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: trading-bots
  labels:
    name: trading-bots
    environment: production
```
```bash
kubectl apply -f kubernetes/namespaces/
kubectl get namespaces
```

### 3.3 ACR Registry Secret
```bash
# Get ACR credentials
az acr credential show --name spyoptionsacr

# Create secret
kubectl create secret docker-registry acr-secret \
  --docker-server=spyoptionsacr.azurecr.io \
  --docker-username=<username> \
  --docker-password=<password> \
  -n trading-bots
```

### 3.4 ConfigMaps & Secrets

**File:** `kubernetes/configmaps/bot-config.yaml`
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: bot-config
  namespace: trading-bots
data:
  LOG_LEVEL: "INFO"
  STRATEGY_TYPE: "anomaly-arbitrage"
  MAX_POSITIONS: "5"
  THRESHOLD: "0.5"
```

**File:** `kubernetes/secrets/ibkr-credentials.yaml`
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ibkr-credentials
  namespace: trading-bots
type: Opaque
data:
  username: <base64-encoded-username>
  password: <base64-encoded-password>
```
```bash
# Create secrets
echo -n 'your_username' | base64
echo -n 'your_password' | base64

kubectl apply -f kubernetes/configmaps/
kubectl apply -f kubernetes/secrets/
```

### 3.5 Persistent Volumes

**File:** `kubernetes/persistent-volumes/pv-sqlite.yaml`
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: sqlite-pv
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /data/sqlite
  storageClassName: local-storage
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: sqlite-pvc
  namespace: trading-bots
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: local-storage
```

### 3.6 Trading Bot Deployment

**File:** `kubernetes/deployments/trading-bot.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trading-bot
  namespace: trading-bots
spec:
  replicas: 3
  selector:
    matchLabels:
      app: trading-bot
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: trading-bot
    spec:
      imagePullSecrets:
      - name: acr-secret
      containers:
      - name: bot
        image: spyoptionsacr.azurecr.io/spy-bot:v1.0
        ports:
        - containerPort: 8080
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
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
        envFrom:
        - configMapRef:
            name: bot-config
        env:
        - name: IBKR_USERNAME
          valueFrom:
            secretKeyRef:
              name: ibkr-credentials
              key: username
        - name: IBKR_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ibkr-credentials
              key: password
```

### 3.7 IBKR Gateway StatefulSet

**File:** `kubernetes/statefulsets/ibkr-gateway.yaml`
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ibkr-gateway
  namespace: trading-bots
spec:
  serviceName: ibkr-gateway-service
  replicas: 1
  selector:
    matchLabels:
      app: ibkr-gateway
  template:
    metadata:
      labels:
        app: ibkr-gateway
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
  volumeClaimTemplates:
  - metadata:
      name: ibkr-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 5Gi
```

### 3.8 Services

**File:** `kubernetes/services/trading-bot-service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: trading-bot-service
  namespace: trading-bots
spec:
  selector:
    app: trading-bot
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP
```

### 3.9 Deploy to Cluster
```bash
kubectl apply -f kubernetes/deployments/
kubectl apply -f kubernetes/statefulsets/
kubectl apply -f kubernetes/services/

# Verify
kubectl get pods -n trading-bots
kubectl get svc -n trading-bots
kubectl logs -f deployment/trading-bot -n trading-bots
```

### ✅ Phase 3 Checklist

- [ ] Kubernetes cluster installed and running
- [ ] Namespaces created
- [ ] ConfigMaps and Secrets configured
- [ ] Persistent Volumes provisioned
- [ ] Trading bot deployment (3 replicas) running
- [ ] IBKR Gateway StatefulSet running
- [ ] Services accessible within cluster

---

## Phase 4: Helm Charts

**Goal:** Package Kubernetes deployments with Helm

### 4.1 Create Helm Chart
```bash
cd helm
helm create spy-trading-bot
```

### 4.2 Chart Structure
```
helm/spy-trading-bot/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-prod.yaml
└── templates/
    ├── deployment.yaml
    ├── statefulset.yaml
    ├── service.yaml
    ├── configmap.yaml
    ├── secret.yaml
    └── _helpers.tpl
```

### 4.3 Chart.yaml
```yaml
apiVersion: v2
name: spy-trading-bot
description: SPY Options Trading Bot Helm Chart
type: application
version: 1.0.0
appVersion: "1.0"
```

### 4.4 values.yaml
```yaml
replicaCount: 3

image:
  repository: spyoptionsacr.azurecr.io/spy-bot
  tag: "v1.0"
  pullPolicy: IfNotPresent

imagePullSecrets:
  - name: acr-secret

resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"

config:
  logLevel: "INFO"
  strategyType: "anomaly-arbitrage"
  maxPositions: 5
```

### 4.5 Install via Helm
```bash
# Lint chart
helm lint ./spy-trading-bot

# Dry run
helm install spy-bot ./spy-trading-bot \
  -f values-prod.yaml \
  --dry-run --debug \
  -n trading-bots

# Install
helm install spy-bot ./spy-trading-bot \
  -f values-prod.yaml \
  -n trading-bots

# Verify
helm list -n trading-bots
kubectl get pods -n trading-bots
```

### ✅ Phase 4 Checklist

- [ ] Helm chart created
- [ ] Templates configured
- [ ] Values files for dev/prod
- [ ] Chart validated (lint)
- [ ] Deployed via Helm successfully

---

## Phase 5: Monitoring Stack

**Goal:** Deploy Prometheus + Grafana for observability

### 5.1 Install Prometheus Stack
```bash
# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --create-namespace
```

### 5.2 Access Prometheus
```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
# Open: http://localhost:9090
```

### 5.3 Access Grafana
```bash
# Get admin password
kubectl get secret -n monitoring prometheus-grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode

# Port forward
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
# Open: http://localhost:3000
# Username: admin
# Password: <from above>
```

### 5.4 Import Dashboards

In Grafana UI:
1. Click "+" → Import
2. Import dashboard IDs:
   - 7249 (Kubernetes Cluster)
   - 1860 (Node Exporter)
   - 6417 (Kubernetes Pods)

### ✅ Phase 5 Checklist

- [ ] Prometheus installed
- [ ] Grafana accessible
- [ ] Dashboards imported
- [ ] Metrics visible for pods

---

## Phase 6: CI/CD Pipeline

**Goal:** Automate build and deployment with GitHub Actions

### 6.1 GitHub Secrets

In GitHub repo → Settings → Secrets → Actions, add:
```
ACR_REGISTRY=spyoptionsacr.azurecr.io
ACR_USERNAME=<from Azure>
ACR_PASSWORD=<from Azure>
KUBECONFIG=<base64 encoded>
```

### 6.2 Build Workflow

**File:** `.github/workflows/docker-build.yml`
```yaml
name: Build and Push Docker Images

on:
  push:
    branches: [ main ]
    paths:
      - 'docker/**'
      - 'backend/**'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Login to ACR
      uses: docker/login-action@v2
      with:
        registry: ${{ secrets.ACR_REGISTRY }}
        username: ${{ secrets.ACR_USERNAME }}
        password: ${{ secrets.ACR_PASSWORD }}
    
    - name: Build and push
      uses: docker/build-push-action@v4
      with:
        context: ./docker/bot
        push: true
        tags: |
          ${{ secrets.ACR_REGISTRY }}/spy-bot:latest
          ${{ secrets.ACR_REGISTRY }}/spy-bot:${{ github.sha }}
    
    - name: Scan with Trivy
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: ${{ secrets.ACR_REGISTRY }}/spy-bot:${{ github.sha }}
        format: 'sarif'
        output: 'trivy-results.sarif'
```

### 6.3 Deploy Workflow

**File:** `.github/workflows/deploy.yml`
```yaml
name: Deploy to Kubernetes

on:
  workflow_run:
    workflows: ["Build and Push Docker Images"]
    types: [ completed ]
    branches: [ main ]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup kubectl
      uses: azure/setup-kubectl@v3
    
    - name: Setup Helm
      uses: azure/setup-helm@v3
    
    - name: Deploy
      run: |
        echo "${{ secrets.KUBECONFIG }}" | base64 -d > kubeconfig
        export KUBECONFIG=kubeconfig
        helm upgrade spy-bot ./helm/spy-trading-bot \
          -f values-prod.yaml \
          --set image.tag=${{ github.sha }} \
          -n trading-bots
```

### ✅ Phase 6 Checklist

- [ ] GitHub Secrets configured
- [ ] Build workflow created
- [ ] Deploy workflow created
- [ ] Push to main triggers build
- [ ] Automated deployment works

---

## Phase 7: VPN Configuration

**Goal:** Establish Site-to-Site VPN between Azure and on-premises

### 7.1 Get VPN Gateway Public IP
```bash
az network public-ip show \
  --resource-group spy-options-rg \
  --name vpn-gateway-ip \
  --query ipAddress -o tsv
```

### 7.2 Configure On-Premises VPN Client

**Option A: strongSwan (Linux)**
```bash
sudo apt-get install strongswan

# Edit /etc/ipsec.conf
conn azure-vpn
    authby=secret
    auto=start
    keyexchange=ikev2
    ike=aes256-sha256-modp2048
    esp=aes256-sha256
    left=%defaultroute
    leftsubnet=192.168.1.0/24
    right=<AZURE_VPN_GATEWAY_IP>
    rightsubnet=10.0.0.0/16
    type=tunnel

# Edit /etc/ipsec.secrets
<ON_PREM_IP> <AZURE_VPN_IP> : PSK "<PRE_SHARED_KEY>"

# Start
sudo systemctl restart strongswan
sudo ipsec status
```

**Option B: pfSense (GUI-based)**

Follow: https://docs.netgate.com/pfsense/en/latest/vpn/ipsec/configuring.html

### 7.3 Verify Connectivity
```bash
# From on-premises, ping Azure VNet
ping 10.0.1.4

# Check VPN status
sudo ipsec statusall

# Verify routes
ip route show
```

### ✅ Phase 7 Checklist

- [ ] VPN Gateway public IP obtained
- [ ] On-premises VPN client configured
- [ ] VPN tunnel established
- [ ] Ping test successful (Azure ↔ on-prem)
- [ ] Latency <30ms RTT

---

## Phase 8: Frontend Dashboard

**Goal:** Deploy real-time visualization dashboard

### 8.1 Create Dashboard

**File:** `frontend/index.html`
```html
<!DOCTYPE html>
<html>
<head>
    <title>SPY Options Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/@microsoft/signalr@7.0.0/dist/browser/signalr.min.js"></script>
</head>
<body>
    <canvas id="chart" width="1200" height="600"></canvas>
    <script src="app.js"></script>
</body>
</html>
```

**File:** `frontend/app.js`
```javascript
const connection = new signalR.HubConnectionBuilder()
    .withUrl('https://spy-signalr.service.signalr.net/hub')
    .withAutomaticReconnect()
    .build();

connection.on('anomalyDetected', (data) => {
    console.log('Anomaly:', data);
    updateChart(data);
});

connection.start().catch(err => console.error(err));

function updateChart(data) {
    const canvas = document.getElementById('chart');
    const ctx = canvas.getContext('2d');
    // Draw visualization
}
```

### 8.2 Deploy to Static Web App
```bash
# Get deployment token
az staticwebapp secrets list \
  --name spy-dashboard \
  --query properties.apiKey -o tsv

# Deploy via GitHub Actions or Azure CLI
az staticwebapp deploy \
  --name spy-dashboard \
  --source ./frontend \
  --token <DEPLOYMENT_TOKEN>
```

### ✅ Phase 8 Checklist

- [ ] Dashboard HTML/CSS/JS created
- [ ] SignalR client configured
- [ ] Canvas visualization implemented
- [ ] Deployed to Static Web App
- [ ] Dashboard accessible via URL

---

## Phase 9: Trading Logic

**Goal:** Implement IBKR integration and anomaly detection

### 9.1 Backend API

**File:** `backend/app.py`
```python
from fastapi import FastAPI
from ib_insync import *
import pandas as pd

app = FastAPI()
ib = IB()

@app.on_event("startup")
async def startup():
    ib.connect('ibkr-gateway-service', 4002, clientId=1)

@app.get("/health")
def health():
    return {"status": "healthy", "ibkr_connected": ib.isConnected()}

@app.get("/options/chain")
async def get_chain():
    spy = Stock('SPY', 'SMART', 'USD')
    chains = ib.reqSecDefOptParams(spy.symbol, '', spy.secType, spy.conId)
    return {"chains": chains}
```

### 9.2 Anomaly Detection

**File:** `backend/anomaly_detector.py`
```python
import pandas as pd
import numpy as np

def detect_anomalies(options_df, threshold=0.5):
    """
    Detect pricing anomalies in options chain
    """
    df = options_df.sort_values('strike')
    df['mid'] = (df['bid'] + df['ask']) / 2
    df['price_change_pct'] = df['mid'].pct_change().abs() * 100
    
    anomalies = df[df['price_change_pct'] > threshold * 100]
    return anomalies.to_dict('records')
```

### 9.3 SignalR Broadcasting

**File:** `backend/signalr_client.py`
```python
from azure.signalr import SignalRClient

client = SignalRClient(connection_string=os.getenv('SIGNALR_CONNECTION'))

async def broadcast_anomaly(anomaly_data):
    await client.send_to_all(
        target='anomalyDetected',
        arguments=[anomaly_data]
    )
```

### ✅ Phase 9 Checklist

- [ ] Backend API implemented
- [ ] IBKR connection working
- [ ] Anomaly detection algorithm functional
- [ ] SignalR broadcasting active
- [ ] End-to-end signal flow verified

---

## Phase 10: Testing & Optimization

**Goal:** Validate system and optimize performance

### 10.1 System Tests
```bash
# Infrastructure
terraform plan  # Should show no changes

# Kubernetes
kubectl get pods -A  # All running
kubectl top nodes    # Resource usage
kubectl top pods -n trading-bots

# VPN
ping 10.0.1.4  # Azure from on-prem
ping 192.168.1.100  # On-prem from Azure

# Application
curl http://localhost:8000/health
curl http://localhost:8000/options/chain
```

### 10.2 Performance Metrics
```bash
# Latency tests
ab -n 1000 -c 10 http://localhost:8000/health

# Monitor Prometheus
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

### 10.3 Load Testing
```python
# locust load test
from locust import HttpUser, task

class TradingBotUser(HttpUser):
    @task
    def check_health(self):
        self.client.get("/health")
```

### ✅ Phase 10 Checklist

- [ ] All infrastructure tests pass
- [ ] Kubernetes pods healthy
- [ ] VPN connectivity stable
- [ ] Application endpoints responding
- [ ] Latency within targets (<500ms)
- [ ] Load test passed
- [ ] Monitoring dashboards populated
- [ ] Documentation updated

---

## 📊 Success Metrics

| Metric | Target | Validation |
|--------|--------|------------|
| **Infrastructure Deploy** | <10 min | `terraform apply` time |
| **VPN Latency** | <30ms RTT | `ping` test |
| **Signal Latency** | <500ms | Prometheus metric |
| **Pod Startup** | <30s | `kubectl get pods` |
| **Uptime** | 99.9% | 30-day observation |
| **Rolling Update** | 0 downtime | Traffic during update |

---

## 🔧 Troubleshooting

### Common Issues

**VPN not connecting:**
```bash
# Check Azure VPN status
az network vnet-gateway show --name spy-vpn-gateway --resource-group spy-options-rg

# Check on-prem logs
sudo journalctl -u strongswan -f
```

**Pods not starting:**
```bash
kubectl describe pod <pod-name> -n trading-bots
kubectl logs <pod-name> -n trading-bots
```

**ACR pull errors:**
```bash
# Verify secret
kubectl get secret acr-secret -n trading-bots -o yaml

# Test manually
docker pull spyoptionsacr.azurecr.io/spy-bot:v1.0
```

---

## 🚀 Next Steps After Completion

1. **Monitor for 30 days** - Collect performance data
2. **Document lessons learned** - Update troubleshooting guide
3. **Optimize costs** - Review Azure Advisor recommendations
4. **Scale testing** - Increase replicas, test limits
5. **Security hardening** - Regular vulnerability scans

---

**Last Updated:** December 2025  
**Roadmap Version:** 1.0  
**Status:** Production Implementation Guide