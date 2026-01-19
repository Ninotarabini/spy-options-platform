# 🔐 VPN Site-to-Site Configuration

**Project:** SPY Options Hybrid Cloud Platform  
**Phase:** 7 - VPN Configuration  
**Status:** ✅ COMPLETED  
**Date:** January 19, 2026

---

## 📋 Overview

This document describes the VPN Site-to-Site (S2S) configuration between on-premises infrastructure (Ubuntu server with strongSwan) and Azure Virtual Network (VPN Gateway).

**Purpose:**
- Secure encrypted tunnel between on-premises edge infrastructure and Azure VNet
- Enable hybrid cloud architecture (analysis edge + cloud services)
- Prepare for future private resources (VMs, AKS private nodes, Private Endpoints)

**Current Status:**
- ✅ VPN tunnel ESTABLISHED (IKE Phase 1)
- ⏸️ ESP Phase 2 idle (no private IPs in Azure VNet yet)
- ✅ DPD keepalive active (14-second intervals)
- ✅ Ready for future private resource deployment

---

## 🏗️ Architecture

```
┌─────────────────────────────────────┐
│    Azure Cloud (10.0.0.0/16)       │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  VPN Gateway                 │  │
│  │  20.8.215.244               │  │
│  │  Basic SKU                   │  │
│  └────────────┬─────────────────┘  │
│               │                     │
└───────────────┼─────────────────────┘
                │
                │ IPsec Tunnel (IKEv2)
                │ UDP 500/4500
                │ AES-256 + SHA2-256
                │
┌───────────────┼─────────────────────┐
│  On-Premises (192.168.1.0/24)      │
│               │                     │
│  ┌────────────▼─────────────────┐  │
│  │  Ubuntu Server               │  │
│  │  192.168.1.134              │  │
│  │  strongSwan v5.9.13         │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  Orange ISP Router           │  │
│  │  Public IP: 84.78.45.143     │  │
│  │  NAT-T enabled               │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

---

## 🔧 Azure Configuration

### Resources Created

#### 1. VPN Gateway
```
Name:               vpn-gateway-spy-options
Resource Group:     rg-spy-options-prod
Location:           westeurope
SKU:                Basic
Gateway Type:       Vpn
VPN Type:           RouteBased
Public IP:          20.8.215.244
Generation:         Generation1
Status:             Succeeded
```

**Creation (via Terraform in Phase 1):**
```hcl
resource "azurerm_virtual_network_gateway" "vpn_gateway" {
  name                = "vpn-gateway-spy-options"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  
  type     = "Vpn"
  vpn_type = "RouteBased"
  
  active_active = false
  enable_bgp    = false
  sku           = "Basic"
  
  ip_configuration {
    name                          = "vnetGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.vpn_gateway_ip.id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway_subnet.id
  }
}
```

#### 2. Local Network Gateway
```
Name:               lng-onprem-spy
Resource Group:     rg-spy-options-prod
Gateway IP:         84.78.45.143 (on-premises public IP)
Address Space:      192.168.1.0/24
Status:             Succeeded
```

**Creation (via PowerShell):**
```powershell
az network local-gateway create \
  --name lng-onprem-spy \
  --resource-group rg-spy-options-prod \
  --gateway-ip-address 84.78.45.143 \
  --local-address-prefixes 192.168.1.0/24 \
  --location westeurope
```

#### 3. VPN Connection
```
Name:                   conn-onprem-spy
Connection Type:        IPsec
Routing Type:           PolicyBased
Shared Key:             [32-character PSK stored in KeyVault]
Connection Protocol:    IKEv2
Connection Status:      Connected
```

**Creation (via Azure CLI):**
```bash
az network vpn-connection create \
  --name conn-onprem-spy \
  --resource-group rg-spy-options-prod \
  --vnet-gateway1 vpn-gateway-spy-options \
  --local-gateway2 lng-onprem-spy \
  --location westeurope \
  --shared-key <YOUR_32_CHAR_PSK>
```

#### 4. Network Security Group Rule
```
Name:                   Allow-VPN-Traffic
Priority:               120
Direction:              Inbound
Access:                 Allow
Protocol:               All (*)
Source:                 192.168.1.0/24
Source Port Range:      *
Destination:            10.0.0.0/16
Destination Port Range: *
```

**Creation:**
```bash
az network nsg rule create \
  --resource-group rg-spy-options-prod \
  --nsg-name nsg-spy-options \
  --name Allow-VPN-Traffic \
  --priority 120 \
  --direction Inbound \
  --access Allow \
  --protocol '*' \
  --source-address-prefixes 192.168.1.0/24 \
  --source-port-ranges '*' \
  --destination-address-prefixes 10.0.0.0/16 \
  --destination-port-ranges '*'
```

---

## 🐧 Ubuntu strongSwan Configuration

### Installation

```bash
# Update package list
sudo apt update

# Install strongSwan
sudo apt install -y strongswan strongswan-pki

# Verify installation
sudo ipsec version
# Expected: Linux strongSwan U5.9.13/K6.11.0-9-generic
```

### Configuration Files

#### /etc/ipsec.conf

```
# /etc/ipsec.conf - strongSwan IPsec configuration file

config setup
    charondebug="ike 2, knl 2, cfg 2"
    uniqueids=never

conn azure-vpn
    type=tunnel
    authby=secret
    left=%defaultroute
    leftsubnet=192.168.1.0/24
    leftid=84.78.45.143
    right=20.8.215.244
    rightsubnet=10.0.0.0/16
    ike=aes256-sha256-modp1024!
    esp=aes256-sha256!
    keyingtries=%forever
    ikelifetime=3h
    lifetime=1h
    dpddelay=30
    dpdtimeout=120
    dpdaction=restart
    auto=start
```

**Configuration Breakdown:**

- `type=tunnel`: IPsec tunnel mode (vs transport mode)
- `authby=secret`: Use pre-shared key authentication
- `left=%defaultroute`: Automatically detect outgoing interface
- `leftsubnet=192.168.1.0/24`: On-premises network CIDR
- `leftid=84.78.45.143`: On-premises public IP (for identification)
- `right=20.8.215.244`: Azure VPN Gateway public IP
- `rightsubnet=10.0.0.0/16`: Azure VNet CIDR
- `ike=aes256-sha256-modp1024!`: IKE Phase 1 parameters (! = strict)
- `esp=aes256-sha256!`: ESP Phase 2 parameters
- `keyingtries=%forever`: Never give up rekeying
- `ikelifetime=3h`: IKE SA lifetime (3 hours)
- `lifetime=1h`: ESP SA lifetime (1 hour)
- `dpddelay=30`: Dead Peer Detection check every 30 seconds
- `dpdtimeout=120`: Timeout after 120 seconds
- `dpdaction=restart`: Restart connection on failure
- `auto=start`: Auto-start on boot

#### /etc/ipsec.secrets

```
# /etc/ipsec.secrets - strongSwan PSK configuration

# On-premises public IP : Azure VPN Gateway IP : PSK type : shared secret
84.78.45.143 20.8.215.244 : PSK "YOUR_32_CHARACTER_PRE_SHARED_KEY_HERE"
```

**⚠️ Security Note:**
- This file contains the pre-shared key
- **NEVER commit this file to Git**
- Permissions: `sudo chmod 600 /etc/ipsec.secrets`
- Owner: `sudo chown root:root /etc/ipsec.secrets`

### Service Management

```bash
# Restart strongSwan service
sudo systemctl restart strongswan-starter

# Enable on boot
sudo systemctl enable strongswan-starter

# Check service status
sudo systemctl status strongswan-starter

# View logs
sudo journalctl -u strongswan-starter -f
```

---

## ✅ Validation & Testing

### 1. Check Tunnel Status (Ubuntu)

```bash
# View all IPsec connections
sudo ipsec statusall

# Expected output:
# Security Associations (1 up, 0 connecting):
#   azure-vpn[1]: ESTABLISHED 14 seconds ago
#     20.8.215.244[84.78.45.143]...20.8.215.244
#     IKEv2 SPIs: abc123_i* def456_r
#     IKE proposal: AES_CBC_256/HMAC_SHA2_256_128/PRF_HMAC_SHA2_256/MODP_1024
```

### 2. Check Connection Status (Azure)

```bash
# Via Azure CLI
az network vpn-connection show \
  --resource-group rg-spy-options-prod \
  --name conn-onprem-spy \
  --query connectionStatus

# Expected: "Connected"
```

### 3. View Logs (Ubuntu)

```bash
# Real-time strongSwan logs
sudo journalctl -u strongswan-starter -f

# Expected keepalive traffic:
# ipsec[123]: 14|IKE|2 sending keep alive to 20.8.215.244:4500
# ipsec[123]: 14|IKE|2 received keep alive
```

### 4. Verify Azure Portal

Navigate to: Azure Portal → VPN Gateway → Connections → conn-onprem-spy

**Status should show:**
- Connection Status: ✅ Connected
- Ingress Bytes: > 0
- Egress Bytes: > 0
- Last Connected: [Recent timestamp]

### 5. Test Private IP Connectivity (Future)

Once private resources are deployed in Azure VNet:

```bash
# From on-premises server
ping 10.0.1.10

# Test SSH
ssh user@10.0.1.10

# Test HTTP
curl http://10.0.1.10:8000/health
```

---

## 🔐 Security Configuration

### Encryption & Integrity

**IKE Phase 1 (SA establishment):**
- Encryption: AES-256 CBC
- Integrity: SHA2-256 (HMAC)
- DH Group: MODP 1024
- Lifetime: 3 hours

**ESP Phase 2 (Data encryption):**
- Encryption: AES-256 CBC
- Integrity: SHA2-256 (HMAC)
- Lifetime: 1 hour

### Authentication

- Method: Pre-Shared Key (PSK)
- Key Length: 32 characters
- Key Storage: 
  - Ubuntu: `/etc/ipsec.secrets` (permissions 600)
  - Azure: Stored in connection configuration (encrypted at rest)

### Network Security

**Azure NSG:**
- Rule: Allow-VPN-Traffic (Priority 120)
- Source: 192.168.1.0/24
- Destination: 10.0.0.0/16
- Protocol: All

**Ubuntu UFW:**
```bash
# Allow IPsec ports
sudo ufw allow 500/udp
sudo ufw allow 4500/udp

# Verify rules
sudo ufw status
```

### Dead Peer Detection (DPD)

- Delay: 30 seconds
- Timeout: 120 seconds
- Action: Restart connection
- Purpose: Detect connection failures and auto-reconnect

---

## 🔍 Troubleshooting

### Issue 1: Tunnel Not Establishing

**Symptoms:**
- `sudo ipsec statusall` shows no connection
- Azure Portal shows "Not connected"

**Checks:**
```bash
# 1. Verify strongSwan is running
sudo systemctl status strongswan-starter

# 2. Check for errors in logs
sudo journalctl -u strongswan-starter | grep -i error

# 3. Verify PSK matches on both sides
sudo cat /etc/ipsec.secrets

# 4. Test UDP port connectivity
sudo nc -vzu 20.8.215.244 500
sudo nc -vzu 20.8.215.244 4500
```

**Common Causes:**
- PSK mismatch between Azure and strongSwan
- Firewall blocking UDP 500/4500
- Incorrect public IP in configuration
- Azure VPN Gateway not fully provisioned

### Issue 2: Connection Established but No Traffic

**Symptoms:**
- IKE Phase 1 shows ESTABLISHED
- Cannot ping Azure private IPs

**Checks:**
```bash
# 1. Verify ESP phase (Child SA)
sudo ipsec statusall | grep -i "child"

# 2. Check routing
ip route show

# 3. Verify NSG rules in Azure
az network nsg rule list \
  --resource-group rg-spy-options-prod \
  --nsg-name nsg-spy-options \
  --output table
```

**Common Causes:**
- No private resources in Azure VNet (ESP idle)
- NSG blocking traffic
- Incorrect subnet configuration
- IP forwarding not enabled

### Issue 3: Connection Drops Frequently

**Symptoms:**
- Connection established but disconnects every few minutes
- DPD timeouts in logs

**Checks:**
```bash
# 1. Check DPD configuration
sudo cat /etc/ipsec.conf | grep -i dpd

# 2. Monitor keepalive traffic
sudo journalctl -u strongswan-starter -f | grep -i "keep alive"

# 3. Verify NAT-T is working
sudo ss -ulpn | grep -E "(500|4500)"
```

**Solution:**
- Increase `dpddelay` to 30s (already configured)
- Verify NAT-T is enabled (no `natd=yes` needed, auto-detected)
- Check for ISP connection stability

### Issue 4: Azure Shows "Connecting" Status

**Symptoms:**
- Azure Portal connection status stuck in "Connecting"
- strongSwan shows ESTABLISHED

**Checks:**
```bash
# 1. Verify Local Network Gateway config
az network local-gateway show \
  --resource-group rg-spy-options-prod \
  --name lng-onprem-spy

# 2. Check Azure VPN Gateway provisioning state
az network vnet-gateway show \
  --resource-group rg-spy-options-prod \
  --name vpn-gateway-spy-options \
  --query provisioningState
```

**Common Causes:**
- Azure VPN Gateway still provisioning (takes 30-45 min)
- Local Network Gateway IP mismatch
- Azure backend issues (retry after 5 minutes)

---

## 📊 Monitoring & Logs

### strongSwan Logs

```bash
# View all IPsec logs
sudo journalctl -u strongswan-starter

# Real-time monitoring
sudo journalctl -u strongswan-starter -f

# Filter by severity
sudo journalctl -u strongswan-starter -p err

# Show logs since 1 hour ago
sudo journalctl -u strongswan-starter --since "1 hour ago"
```

### Azure Monitoring

**Metrics to Track:**
- Connection Status (Connected/Not Connected)
- Ingress Bytes
- Egress Bytes
- Tunnel Ingress Bandwidth
- Tunnel Egress Bandwidth

**Access:**
- Azure Portal → VPN Gateway → Monitoring → Metrics

### Automated Alerts (Optional)

```bash
# Azure Monitor alert for VPN disconnect
az monitor metrics alert create \
  --name "VPN-Disconnected" \
  --resource-group rg-spy-options-prod \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-spy-options-prod/providers/Microsoft.Network/connections/conn-onprem-spy \
  --condition "connectionStatus == 0" \
  --description "VPN S2S connection is disconnected"
```

---

## 💰 Cost Analysis

| Resource | SKU/Tier | Monthly Cost | Notes |
|----------|----------|--------------|-------|
| VPN Gateway | Basic | $27.00 | Deployed in Phase 1 |
| Data Transfer (Ingress) | - | $0.00 | Free in Azure |
| Data Transfer (Egress) | First 5GB | $0.00 | Free tier |
| Data Transfer (Egress) | >5GB | ~$0.087/GB | Estimated minimal usage |
| strongSwan | Open Source | $0.00 | No licensing costs |
| **TOTAL** | | **~$27.00/mo** | No additional costs |

**Notes:**
- VPN Gateway cost already included in Phase 1 budget ($53/mo Azure total)
- Minimal data transfer expected (primarily keepalive packets)
- Phase 7 added $0 to monthly operating costs

---

## 🚀 Next Steps

### Phase 8: Frontend Dashboard
- Deploy dashboard to Azure Static Web App
- No VPN required (public endpoint)

### Phase 9: Backend & Trading Logic
- Current PaaS services (App Service, SignalR) use public endpoints
- VPN not actively used for data plane traffic yet

### Future Private Resources (Post-Phase 10)
When deploying private resources in Azure VNet:

1. **Deploy VM in Azure (10.0.1.10)**
```bash
# Test connectivity
ping 10.0.1.10
ssh user@10.0.1.10
```

2. **Configure Private Endpoints**
- Storage Account Private Endpoint
- SignalR Private Endpoint
- App Service Private Endpoint

3. **Deploy AKS with Private Nodes**
- Private Kubernetes API server
- Node subnet in Azure VNet (10.0.2.0/24)

---

## 📚 References

### Official Documentation
- [Azure VPN Gateway Overview](https://learn.microsoft.com/en-us/azure/vpn-gateway/vpn-gateway-about-vpngateways)
- [Site-to-Site VPN Tutorial](https://learn.microsoft.com/en-us/azure/vpn-gateway/tutorial-site-to-site-portal)
- [strongSwan Documentation](https://wiki.strongswan.org/projects/strongswan/wiki/UserDocumentation)
- [IPsec Protocol RFC](https://datatracker.ietf.org/doc/html/rfc4301)

### Project Documentation
- [Implementation Roadmap - Phase 7](../implementation-roadmap.md#phase-7-vpn-configuration)
- [PROGRESS.md - Phase 7](../../PROGRESS.md#phase-7-vpn-configuration)
- [ipsec.conf Template](../../kubernetes/vpn/ipsec.conf.template)

---

**✅ Phase 7 Status:** COMPLETED  
**🎯 Next Phase:** Frontend Dashboard (Phase 8)  
**📅 Last Updated:** January 19, 2026
