# 🔧 PROJECT CONFIGURATION GUIDE

Configuration variables required for SPY Options Hybrid Cloud Trading Platform.

---

## 📋 SETUP INSTRUCTIONS

### 1. Copy the template
```bash
cp .env.project.template .env.project
```

### 2. Fill your values
Edit `.env.project` with your real data.

### 3. Verify protection
```bash
git status
# .env.project should NOT appear (protected by .gitignore)
```

---

## 📊 VARIABLES DESCRIPTION

### GITHUB
| Variable | Description | Example |
|----------|-------------|---------|
| `GITHUB_USERNAME` | Your GitHub username | `your-username` |
| `GITHUB_REPO_NAME` | Repository name | `spy-options-platform` |
| `GITHUB_REPO_URL` | Full repository URL | `https://github.com/user/repo` |
| `GITHUB_PAGES_URL` | GitHub Pages URL | `https://user.github.io/repo` |

### LOCAL WORKSPACE
| Variable | Description | Example |
|----------|-------------|---------|
| `LOCAL_REPO_PATH` | Local project path | `C:\Users\Name\project` |

### SSH & UBUNTU REMOTE
| Variable | Description | Get with |
|----------|-------------|----------|
| `SSH_HOST` | Ubuntu server IP | `hostname -I` |
| `SSH_USER` | SSH username | `whoami` |
| `SSH_PORT` | SSH port (default 22) | - |
| `SSH_HOSTNAME` | Server hostname | `hostname` |
| `PROJECT_PATH_REMOTE` | Project path on Ubuntu | `/home/user/spy-options-platform` |
| `K8S_NAMESPACE` | Kubernetes namespace | `spy-options-bot` |

### AZURE CLOUD
| Variable | Description | Get with |
|----------|-------------|----------|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | `az account show` |
| `AZURE_TENANT_ID` | Azure tenant ID | `az account show` |
| `AZURE_EMAIL` | Azure account email | - |
| `AZURE_REGION` | Azure region | `westeurope` (recommended) |

#### Azure Resources (Phase 1)
| Variable | Description | Example |
|----------|-------------|---------|
| `RESOURCE_GROUP_NAME` | Resource group name | `rg-spy-options-prod` |
| `ACR_NAME` | Azure Container Registry name | `acrspyoptions` (no hyphens) |
| `ACR_LOGIN_SERVER` | ACR login server | `acrspyoptions.azurecr.io` |
| `VNET_NAME` | Virtual Network name | `vnet-spy-options` |

### INTERACTIVE BROKERS (Phase 9)
| Variable | Description | When |
|----------|-------------|------|
| `IBKR_USERNAME` | Paper trading username | Phase 9 |
| `IBKR_ACCOUNT_ID` | Account ID (e.g., DU1234567) | Phase 9 |
| `IBKR_CLIENT_ID` | API client ID | `1` (default) |

### NOTIFICATIONS
| Variable | Description | Optional |
|----------|-------------|----------|
| `NOTIFICATION_EMAIL` | Email for alerts | - |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Yes |

---

## 🌍 AZURE REGION SELECTION

### Recommendation: `westeurope` (Amsterdam)

**Reasons:**
- ✅ IBKR servers likely in Amsterdam/Frankfurt
- ✅ Latency from Spain: ~10-15ms
- ✅ Critical path (trades) is on-prem → IBKR direct
- ✅ Azure only for broadcast/logs (non-critical)

**Alternative:** `northeurope` (Dublin)
- Latency from Spain: ~30-40ms
- €5/month cheaper VPN Gateway
- Greater distance from on-premises

---

## 🔐 SECURITY NOTES

⚠️ **NEVER commit** `.env.project` to GitHub  
✅ **DO commit** `.env.project.template` (no real data)  
✅ File protected by `.gitignore`  
✅ Sensitive values only local

---

## 📁 FILE STRUCTURE

```
spy-options-platform/
├── .env.project              # ❌ LOCAL (your real data)
├── .env.project.template     # ✅ GITHUB (placeholders)
├── PROJECT_CONFIG.md         # ✅ GITHUB (this documentation)
└── .gitignore               # ✅ GITHUB (protects .env.project)
```

---

## 🚀 WORKFLOW

### Initial setup
1. Clone repository
2. Copy `.env.project.template` → `.env.project`
3. Fill real values
4. Verify: `git status` doesn't show `.env.project`

### Update configuration
1. Edit `.env.project` with new values
2. Never commit `.env.project`
3. If adding new variables, update `.env.project.template`

---

## 📝 CHANGELOG

- **2024-12-15**: Initial configuration
  - Variables: GitHub, SSH, Azure, IBKR
  - Recommended region: westeurope
  - Protection via .gitignore
