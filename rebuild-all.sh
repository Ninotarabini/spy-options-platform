#!/bin/bash
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DELAY=90

echo -e "${BOLD}${BLUE}============================================${NC}"
echo -e "${BOLD}${BLUE}🚀 SPY OPTIONS PLATFORM - REBUILD ALL${NC}"
echo -e "${BOLD}${BLUE}============================================${NC}"
echo ""
echo -e "${YELLOW}⏱️  Delay entre componentes: ${DELAY}s${NC}"
echo ""

# ========================================
# 1. BACKEND
# ========================================
echo -e "${BOLD}${GREEN}[1/3] 🔨 Rebuilding BACKEND...${NC}"
cd ~/spy-options-platform/docker/backend
./rebuild-backend.sh

echo ""
echo -e "${YELLOW}⏳ Esperando ${DELAY}s antes del siguiente componente...${NC}"
sleep ${DELAY}

# ========================================
# 2. DETECTOR
# ========================================
echo ""
echo -e "${BOLD}${GREEN}[2/3] 🔨 Rebuilding DETECTOR...${NC}"
cd ~/spy-options-platform/docker/detector
./rebuild-detector.sh

echo ""
echo -e "${YELLOW}⏳ Esperando ${DELAY}s antes del siguiente componente...${NC}"
sleep ${DELAY}

# ========================================
# 3. FRONTEND
# ========================================
echo ""
echo -e "${BOLD}${GREEN}[3/3] 🔨 Rebuilding FRONTEND...${NC}"
cd ~/spy-options-platform/docker/frontend
./rebuild-frontend.sh

# ========================================
# RESUMEN FINAL
# ========================================
echo ""
echo -e "${BOLD}${BLUE}============================================${NC}"
echo -e "${BOLD}${GREEN}✅ REBUILD ALL COMPLETADO${NC}"
echo -e "${BOLD}${BLUE}============================================${NC}"
echo ""
echo "📦 Verificar imágenes desplegadas:"
kubectl get pods -n spy-options-bot -o custom-columns=POD:.metadata.name,IMAGE:.spec.containers[0].image,STATUS:.status.phase

echo ""
echo "📝 Verificar Helm values.yaml actualizado:"
grep -A 1 "repository: spy-" ~/spy-options-platform/helm/spy-trading-bot/values.yaml | grep "tag:"
