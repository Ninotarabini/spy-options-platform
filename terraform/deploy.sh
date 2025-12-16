#!/bin/bash
# ============================================
# TERRAFORM DEPLOYMENT SCRIPT
# SPY Options Platform - Phase 1
# ============================================

set -e  # Exit on error

PROJECT_DIR="/home/nino/spy-options-platform"
TF_DIR="$PROJECT_DIR/terraform"

echo "=================================================="
echo "🚀 SPY Options Platform - Terraform Deployment"
echo "=================================================="
echo ""

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform not found. Installing..."
    cd /tmp
    wget https://releases.hashicorp.com/terraform/1.6.6/terraform_1.6.6_linux_amd64.zip
    unzip terraform_1.6.6_linux_amd64.zip
    sudo mv terraform /usr/local/bin/
    rm terraform_1.6.6_linux_amd64.zip
    echo "✅ Terraform installed"
else
    echo "✅ Terraform already installed: $(terraform version -json | jq -r '.terraform_version')"
fi

echo ""
echo "📂 Working directory: $TF_DIR"
cd "$TF_DIR"

# Check Azure CLI login
echo ""
echo "🔐 Checking Azure CLI authentication..."
if ! az account show &> /dev/null; then
    echo "❌ Not logged in to Azure CLI"
    echo "Run: az login"
    exit 1
fi
echo "✅ Azure CLI authenticated"
echo "   Subscription: $(az account show --query name -o tsv)"

# Terraform workflow
echo ""
echo "=================================================="
echo "STEP 1: Terraform Init"
echo "=================================================="
terraform init

echo ""
echo "=================================================="
echo "STEP 2: Terraform Format"
echo "=================================================="
terraform fmt

echo ""
echo "=================================================="
echo "STEP 3: Terraform Validate"
echo "=================================================="
terraform validate

echo ""
echo "=================================================="
echo "STEP 4: Terraform Plan"
echo "=================================================="
terraform plan -out=tfplan

echo ""
echo "=================================================="
echo "🎯 Ready to apply!"
echo "=================================================="
echo ""
echo "Review the plan above. To apply, run:"
echo "  terraform apply tfplan"
echo ""
echo "Or to apply automatically:"
echo "  terraform apply -auto-approve"
echo ""
echo "To destroy everything:"
echo "  terraform destroy"
echo ""
