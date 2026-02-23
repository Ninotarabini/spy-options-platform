#!/bin/bash
set -e

IMAGE="acrspyoptions.azurecr.io/spy-frontend"

# TAG con Fecha y Hora para trazabilidad total
TAG="v-Front-$(date +%Y%m%d-%H%M%S)"

echo "🚀 Nueva versión: ${IMAGE}:${TAG}"

echo "🔨 Build..."
docker build --no-cache --pull \
  --build-arg BUILD_VERSION=${TAG} \
  -t ${IMAGE}:${TAG} \
  ~/spy-options-platform/docker/frontend/

az acr login --name acrspyoptions
echo "⬆️  Push..."
docker push ${IMAGE}:${TAG}

echo "📝 Actualizando deployment..."
kubectl set image deployment/frontend \
  frontend=${IMAGE}:${TAG} \
  -n spy-options-bot

echo "🔄 Esperando rollout..."
kubectl rollout status deployment/frontend -n spy-options-bot

echo "📝 Actualizando Helm values.yaml..."
sed -i '/repository: spy-frontend/,/tag:/ s/tag:.*/tag: '"${TAG}"'/' \
  ~/spy-options-platform/helm/spy-trading-bot/values.yaml

echo "✅ Deploy completado"

