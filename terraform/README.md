# 🏗️ Terraform Infrastructure - SPY Options Platform

## 📋 Current Status
**Phase 1: Azure Infrastructure Setup**

### ✅ Created Resources
- Resource Group: `rg-spy-options-prod`
- Virtual Network: `vnet-spy-options` (10.0.0.0/16)
- 3 Subnets:
  - GatewaySubnet (10.0.0.0/27) - for VPN Gateway
  - AppSubnet (10.0.1.0/24) - for App Services
  - ContainerSubnet (10.0.2.0/24) - for Container Instances
- Network Security Group with VPN rules

### ⏳ Pending Resources
- VPN Gateway (30-45 min provisioning)
- Azure Container Registry
- App Service + Plan
- SignalR Service
- Storage Account
- Key Vault
- Application Insights
- Static Web App

---

## 🚀 Quick Start

### Prerequisites
```bash
# Verify tools installed
terraform --version  # Should be 1.6+
az --version         # Azure CLI
az account show      # Verify logged in
```

### Deploy Infrastructure
```bash
# Navigate to terraform directory
cd /home/nino/spy-options-platform/terraform

# Option A: Use deploy script (recommended)
chmod +x deploy.sh
./deploy.sh

# Option B: Manual steps
terraform init
terraform plan
terraform apply

# Option C: Auto-approve (use with caution)
terraform apply -auto-approve
```

---

## 📁 File Structure
```
terraform/
├── providers.tf              # Azure provider configuration
├── variables.tf              # Variable declarations (no sensitive defaults)
├── terraform.tfvars.example  # 🔓 Public template (safe for GitHub)
├── terraform.tfvars          # 🔒 PRIVATE (auto-generated, in .gitignore)
├── main.tf                   # Resource definitions
├── outputs.tf                # Output values after deployment
├── load-config.sh            # Script to generate tfvars from .env.project
├── deploy.sh                 # Automated deployment script
├── .gitignore                # Protects sensitive files
└── modules/                  # Future: Terraform modules
    └── (empty for now)
```

**Security Model:**
- ✅ **GitHub (public):** `variables.tf`, `terraform.tfvars.example`, all `.tf` files
- ❌ **Local only (private):** `terraform.tfvars`, `*.tfstate`, `.terraform/`

---

## 🔑 Configuration

### 🔒 Secure Setup (REQUIRED before deployment)

**Option A: Auto-generate from .env.project (Recommended)**
```bash
# 1. Ensure .env.project exists in project root
cd ~/spy-options-platform
cat .env.project  # Verify it contains your Azure credentials

# 2. Generate terraform.tfvars automatically
cd terraform
./load-config.sh

# 3. Verify generated file (never commit this!)
cat terraform.tfvars
```

**Option B: Manual setup**
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars  # Fill in your actual values
```

**⚠️ CRITICAL SECURITY:**
- `terraform.tfvars` contains sensitive data
- Already in `.gitignore` - never commit it!
- Use `terraform.tfvars.example` as public template

### Required Values (set in terraform.tfvars)
- **Azure Subscription ID** - Get with: `az account show`
- **Azure Tenant ID** - Get with: `az account show`
- **Region:** `westeurope` (or your preferred region)
- **Resource Group:** `rg-spy-options-prod`
- **VNet CIDR:** `10.0.0.0/16`

### Override Variables (optional)
Create `terraform.tfvars` file:
```hcl
# Custom overrides
onprem_public_ip = "your-public-ip"
vpn_shared_key   = "super-secret-key"
```

---

## 📊 Cost Estimation
Based on current configuration:

| Resource | SKU/Tier | Monthly Cost |
|----------|----------|--------------|
| VPN Gateway | Basic | $27 |
| App Service Plan | B1 | $13 |
| ACR | Basic | $5 |
| Storage Account | Standard LRS | $1 |
| Application Insights | Pay-as-you-go | $5 |
| **TOTAL** | | **~$53/mo** |

SignalR (Free), Static Web App (Free), Key Vault (Standard ~$0)

---

## 🔍 Verification

### Check deployed resources
```bash
# Azure Portal
https://portal.azure.com

# Azure CLI
az resource list --resource-group rg-spy-options-prod --output table

# Terraform
terraform show
terraform output
```

### Test networking
```bash
# List VNet
az network vnet show --name vnet-spy-options --resource-group rg-spy-options-prod

# List subnets
az network vnet subnet list --vnet-name vnet-spy-options --resource-group rg-spy-options-prod --output table
```

---

## 🔄 Common Commands

```bash
# Initialize (first time or after adding modules)
terraform init

# Format code
terraform fmt

# Validate syntax
terraform validate

# Preview changes
terraform plan

# Apply changes
terraform apply

# Show current state
terraform show

# List resources in state
terraform state list

# Destroy everything (⚠️ dangerous)
terraform destroy
```

---

## 🐛 Troubleshooting

### "Error: authentication failed"
```bash
# Re-login to Azure
az login
az account set --subscription bf692bd4-125a-4ed2-b9c8-87cebb2bfd71
```

### "Error: provider configuration not found"
```bash
# Re-initialize Terraform
terraform init -upgrade
```

### "Error: resource already exists"
```bash
# Import existing resource
terraform import azurerm_resource_group.main /subscriptions/bf692bd4-125a-4ed2-b9c8-87cebb2bfd71/resourceGroups/rg-spy-options-prod
```

### Check Azure costs
```bash
# Via CLI
az consumption usage list --start-date 2024-12-01 --end-date 2024-12-31

# Via Portal
https://portal.azure.com → Cost Management + Billing
```

---

## 📝 Next Steps (Phase 1 continued)

1. ✅ Basic networking deployed
2. ⏳ Add VPN Gateway resources
3. ⏳ Add ACR + App Service
4. ⏳ Add Storage + Key Vault
5. ⏳ Add Application Insights
6. ⏳ Configure remote state backend
7. ⏳ Validate all resources
8. ⏳ Update PROGRESS.md

---

## 🔐 Security Notes

- **Never commit** `terraform.tfstate` (contains sensitive data)
- **Never commit** `*.tfvars` files
- Use Azure Key Vault for secrets in production
- Enable soft-delete on Key Vault
- Review NSG rules regularly

---

## 📚 Documentation Links

- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure VNet](https://learn.microsoft.com/en-us/azure/virtual-network/)
- [Azure VPN Gateway](https://learn.microsoft.com/en-us/azure/vpn-gateway/)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)

---

**Last Updated:** December 16, 2024  
**Maintained by:** Nino (@Ninotarabini)
