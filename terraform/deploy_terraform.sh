#!/bin/bash
# ============================================
# 🚀 PROFESSIONAL TERRAFORM DEPLOYMENT SCRIPT
# SPY Options Platform - Remote Backend Mode
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
echo -e "🚀 ${GREEN}SPY Options Platform - Professional Deployment${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. CODE SYNC CONFIRMATION
echo -e "\n🔍 ${BLUE}Phase 1: Code Synchronization Check${NC}"
echo -e "State is now REMOTE (No manual .tfstate sync needed! 🎉)"
read -p "Did you copy the latest CODE files from Windows? [y/N]: " CODE_CONFIRM
if [[ ! "$CODE_CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Please sync your code files first. Aborting.${NC}"
    exit 1
fi

# 2. AZURE CONTEXT CHECK
echo -e "\n🔍 ${BLUE}Phase 2: Azure Context Check${NC}"
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

# 3. TERRAFORM PLAN & RISK ASSESSMENT
echo -e "\n🔍 ${BLUE}Phase 3: Remote Planning & Risk Assessment${NC}"
cd "$TF_DIR"
echo "Initializing/Syncing with Remote Backend..."
terraform init -input=false

echo "Generating execution plan from Azure state..."
terraform plan -out=tfplan -no-color > plan_output.txt

# Sanity check: Avoid accidental duplication
if grep -q "azurerm_resource_group.main will be created" plan_output.txt; then
    echo -e "${RED}🚨 SECURITY ALERT: The plan attempts to CREATE the Resource Group.${NC}"
    echo -e "This should NOT happen with Remote Backend unless Azure is empty."
    echo -e "OPERACIÓN CANCELADA POR SEGURIDAD.${NC}"
    exit 1
fi

# Summary of changes
ADDED=$(grep -o "Plan: [0-9]* to add" plan_output.txt | cut -d' ' -f2 || echo "0")
CHANGED=$(grep -o "[0-9]* to change" plan_output.txt | cut -d' ' -f1 || echo "0")
DESTROYED=$(grep -o "[0-9]* to destroy" plan_output.txt | cut -d' ' -f1 || echo "0")

echo -e "--------------------------------------------------"
echo -e "📋 ${GREEN}Resumen del Plan (Remoto):${NC}"
echo -e "➕ Añadir:     ${ADDED:-0}"
echo -e "🔄 Cambiar:    ${CHANGED:-0}"
echo -e "❌ Destruir:   ${DESTROYED:-0}"
echo -e "--------------------------------------------------"

# 4. FINAL APPROVAL
echo -e "\n🎯 ${BLUE}Phase 4: Final Confirmation${NC}"
if [[ "$DESTROYED" -gt "0" ]]; then
    echo -e "${RED}⚠️  WARNING: Resources will be DESTROYED!${NC}"
fi

read -p "Do you want to apply these changes? [type 'si' to confirm]: " FINAL_CONFIRM
if [ "$FINAL_CONFIRM" == "si" ]; then
    echo -e "\n🚀 ${GREEN}Applying changes to Azure...${NC}"
    terraform apply -auto-approve tfplan
    echo -e "\n✅ ${GREEN}Deployment successful!${NC}"
    echo -e "${GREEN}The state has been updated automatically in Azure Storage.${NC}"
else
    echo -e "${YELLOW}Deployment cancelled.${NC}"
fi
