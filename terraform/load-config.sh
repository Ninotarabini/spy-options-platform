#!/bin/bash
# ============================================
# LOAD TERRAFORM CONFIG FROM .env.project
# ============================================
# Generates terraform.tfvars from .env.project
# Usage: ./load-config.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env.project"
TFVARS_FILE="$SCRIPT_DIR/terraform.tfvars"

echo "🔧 Loading configuration from .env.project..."

# Check if .env.project exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env.project not found at $ENV_FILE"
    echo "💡 Create it from .env.project.template"
    exit 1
fi

# Source environment variables
set -a
source "$ENV_FILE"
set +a

# Validate required variables
REQUIRED_VARS=(
    "AZURE_SUBSCRIPTION_ID"
    "AZURE_TENANT_ID"
    "AZURE_REGION"
    "PROJECT_NAME"
    "ENVIRONMENT"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: Required variable $var not set in .env.project"
        exit 1
    fi
done

# Generate terraform.tfvars
echo "📝 Generating terraform.tfvars..."

cat > "$TFVARS_FILE" << EOF
# ============================================
# TERRAFORM VARIABLES
# ============================================
# 🤖 Auto-generated from .env.project
# 🔒 DO NOT commit this file to Git!
# Generated: $(date)

# ----------------
# Azure Credentials
# ----------------
azure_subscription_id = "$AZURE_SUBSCRIPTION_ID"
azure_tenant_id       = "$AZURE_TENANT_ID"

# ----------------
# Project Configuration
# ----------------
project_name = "$PROJECT_NAME"
environment  = "$ENVIRONMENT"
location     = "$AZURE_REGION"

# ----------------
# Resource Names
# ----------------
resource_group_name = "$RESOURCE_GROUP_NAME"
vnet_name          = "$VNET_NAME"
acr_name           = "$ACR_NAME"

# ----------------
# Networking
# ----------------
vnet_address_space       = ["$VNET_CIDR"]
gateway_subnet_prefix    = "$GATEWAY_SUBNET_CIDR"
app_subnet_prefix        = "$APP_SUBNET_CIDR"
container_subnet_prefix  = "$CONTAINER_SUBNET_CIDR"

# ----------------
# On-Premises Configuration
# ----------------
EOF

# Add optional on-prem config if set
if [ -n "$ONPREM_PUBLIC_IP" ]; then
    echo "onprem_public_ip    = \"$ONPREM_PUBLIC_IP\"" >> "$TFVARS_FILE"
fi

if [ -n "$ONPREM_CIDR" ]; then
    echo "onprem_address_space = [\"$ONPREM_CIDR\"]" >> "$TFVARS_FILE"
fi

if [ -n "$VPN_SHARED_KEY" ]; then
    echo "vpn_shared_key      = \"$VPN_SHARED_KEY\"" >> "$TFVARS_FILE"
fi

# Add tags
cat >> "$TFVARS_FILE" << EOF

# ----------------
# Tags
# ----------------
common_tags = {
  Project     = "SPY-Options-Platform"
  Environment = "$ENVIRONMENT"
  ManagedBy   = "Terraform"
  Owner       = "Nino"
  CostCenter  = "Trading-Infrastructure"
}
EOF

echo "✅ terraform.tfvars generated successfully!"
echo "📍 Location: $TFVARS_FILE"
echo ""
echo "🚀 Next steps:"
echo "   1. Review: cat terraform/terraform.tfvars"
echo "   2. Init: cd terraform && terraform init"
echo "   3. Plan: terraform plan"
echo ""
