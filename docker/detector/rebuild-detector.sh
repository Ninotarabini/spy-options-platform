#!/bin/bash
set -e

IMAGE="acrspyoptions.azurecr.io/spy-detector"

# TAG con Fecha y Hora para trazabilidad total
TAG="v2.0-$(date +%Y%m%d-%H%M%S)"

echo "🚀 Nueva versión: ${IMAGE}:${TAG}"


echo "🔨 Build..."
docker build --no-cache --pull \
  -t ${IMAGE}:${TAG} \
  ~/spy-options-platform/docker/detector/


az acr login --name acrspyoptions
echo "⬆️  Push..."
docker push ${IMAGE}:${TAG}

echo "📝 Actualizando deployment..."
kubectl set image deployment/detector \
  detector=${IMAGE}:${TAG} \
  -n spy-options-bot

echo "🔄 Esperando rollout..."
kubectl rollout status deployment/detector -n spy-options-bot

echo "✅ Deploy completado"
