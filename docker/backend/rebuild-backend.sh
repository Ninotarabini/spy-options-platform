#!/bin/bash
set -e

# ✅ Validar sincronización de models.py entre servicios
echo "🔍 Verificando sincronización de models.py..."
    if ! diff ~/spy-options-platform/docker/backend/models.py \
              ~/spy-options-platform/docker/detector/models.py > /dev/null 2>&1; then
    echo "❌ ERROR: models.py DESINCRONIZADO entre backend y detector"
    echo "   Sincroniza manualmente antes de hacer rebuild"
    diff ~/spy-options-platform/docker/backend/models.py \
         ~/spy-options-platform/docker/detector/models.py
    exit 1
fi
echo "✅ models.py sincronizados"

IMAGE="acrspyoptions.azurecr.io/spy-backend"

# TAG con Fecha y Hora para trazabilidad total
TAG="v-Back-$(date +%Y%m%d-%H%M%S)"

echo "🚀 Nueva versión: ${IMAGE}:${TAG}"

echo "🔨 Build..."
docker build --no-cache --pull \
  --build-arg BUILD_VERSION=${TAG} \
  -t ${IMAGE}:${TAG} \
  ~/spy-options-platform/docker/backend/

az acr login --name acrspyoptions
echo "⬆️  Push..."
docker push ${IMAGE}:${TAG}

echo "📝 Actualizando deployment..."
kubectl set image deployment/backend \
  backend=${IMAGE}:${TAG} \
  -n spy-options-bot

echo "🔄 Esperando rollout..."
kubectl rollout status deployment/backend -n spy-options-bot

echo "📝 Actualizando Helm values.yaml..."
sed -i '/repository: spy-backend/,/tag:/ s/tag:.*/tag: '"${TAG}"'/' \
  ~/spy-options-platform/helm/spy-trading-bot/values.yaml

echo "✅ Deploy completado"
echo ""
echo "⚠️  SINCRONIZACIÓN REQUERIDA ANTES DE GIT PUSH:"
echo "   Copiar a Windows: helm/spy-trading-bot/values.yaml"
echo "   Tag deployed: ${TAG}"
echo ""