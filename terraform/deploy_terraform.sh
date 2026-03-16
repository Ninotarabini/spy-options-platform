#!/bin/bash
# ============================================
# 🚀 SAFE TERRAFORM DEPLOYMENT SCRIPT
# SPY Options Platform - Enhanced Interactive
# ============================================

set -e  # Exit on error

# 🎨 Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$PROJECT_DIR/terraform"

# Cleanup function
cleanup() {
    rm -f "$TF_DIR/plan_output.txt"
}
trap cleanup EXIT

echo -e "${BLUE}==================================================${NC}"
echo -e "🚀 ${GREEN}SPY Options Platform - Safe Deployment${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. MANUAL SYNC CONFIRMATION
echo -e "\n🔍 ${BLUE}Phase 1: Manual Files Synchronization${NC}"
echo -e "Since Ubuntu is not connected to Git, you must ensure files are synced."
echo -e "Did you manually copy the latest code and .tfstate from Windows? [y/N]"
read -p "Confirmation: " SYNC_CONFIRM
if [[ ! "$SYNC_CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Please sync your files first. Aborting.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Proceeding with local files.${NC}"

# 2. STATE EXISTENCE CHECK
echo -e "\n🔍 ${BLUE}Phase 2: Terraform State Check${NC}"
if [ ! -f "$TF_DIR/terraform.tfstate" ]; then
    echo -e "${RED}🚨 CRITICAL: 'terraform.tfstate' NOT FORMED in $TF_DIR!${NC}"
    echo -e "If you continue, Terraform will try to create 29+ resources from scratch."
    echo -e "This WILL FAIL because resources already exist in Azure."
    echo ""
    read -p "ARE YOU ABSOLUTELY SURE you want to proceed without a state file? [type 'YES' to continue]: " CONFIRM_STATE
    if [ "$CONFIRM_STATE" != "YES" ]; then
        echo -e "${RED}Aborting deployment.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Local state file found.${NC}"
fi

# 3. AZURE CONTEXT CHECK
echo -e "\n🔍 ${BLUE}Phase 3: Azure Context Check${NC}"
if ! az account show &> /dev/null; then
    echo -e "${RED}❌ Not logged in to Azure CLI. Run 'az login' first.${NC}"
    exit 1
fi
SUBSCRIPTION=$(az account show --query name -o tsv)
USER_EMAIL=$(az account show --query user.name -o tsv)
echo -e "👤 User: ${YELLOW}$USER_EMAIL${NC}"
echo -e "💳 Subscription: ${YELLOW}$SUBSCRIPTION${NC}"
read -p "Is this the correct Azure target? [y/N]: " CONFIRM_AZ
if [[ ! "$CONFIRM_AZ" =~ ^[Yy]$ ]]; then
    exit 1
fi

# 4. TERRAFORM PLAN & RISK ASSESSMENT
echo -e "\n🔍 ${BLUE}Phase 4: Planning & Risk Assessment${NC}"
cd "$TF_DIR"
echo "Initializing Terraform..."
terraform init -input=false

echo "Generating execution plan..."
terraform plan -out=tfplan -no-color > plan_output.txt

# Parse plan for risks (e.g., creating the Resource Group)
if grep -q "azurerm_resource_group.main will be created" plan_output.txt; then
    echo -e "${RED}🚨 SECURITY ALERT: The plan attempts to CREATE the Resource Group.${NC}"
    echo -e "This means your local State is out of sync with Azure (or missing)."
    echo -e "OPERACIÓN CANCELADA POR SEGURIDAD para evitar colisiones.${NC}"
    exit 1
fi

# Summary of changes
ADDED=$(grep -o "Plan: [0-9]* to add" plan_output.txt | cut -d' ' -f2 || echo "0")
CHANGED=$(grep -o "[0-9]* to change" plan_output.txt | cut -d' ' -f1 || echo "0")
DESTROYED=$(grep -o "[0-9]* to destroy" plan_output.txt | cut -d' ' -f1 || echo "0")

echo -e "--------------------------------------------------"
echo -e "📋 ${GREEN}Resumen del Plan:${NC}"
echo -e "➕ Añadir:     ${ADDED:-0}"
echo -e "🔄 Cambiar:    ${CHANGED:-0}"
echo -e "❌ Destruir:   ${DESTROYED:-0}"
echo -e "--------------------------------------------------"

# 5. FINAL APPROVAL
echo -e "\n🎯 ${BLUE}Phase 5: Final Confirmation${NC}"
if [[ "$DESTROYED" -gt "0" ]]; then
    echo -e "${RED}⚠️  WARNING: Resources will be DESTROYED!${NC}"
fi

read -p "Do you want to apply these changes? [type 'si' to confirm]: " FINAL_CONFIRM
if [ "$FINAL_CONFIRM" == "si" ]; then
    echo -e "\n🚀 ${GREEN}Applying changes...${NC}"
    terraform apply -auto-approve tfplan
    echo -e "\n✅ ${GREEN}Deployment successful!${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANT: Remember to manually synchronize your 'terraform.tfstate' file${NC}"
    echo -e "${YELLOW}   from Ubuntu back to Windows to keep them in sync.${NC}"
else
    echo -e "${YELLOW}Deployment cancelled.${NC}"
fi
