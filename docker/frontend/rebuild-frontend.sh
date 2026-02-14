#!/bin/bash
set -e

IMAGE="acrspyoptions.azurecr.io/spy-frontend"

# TAG único por build (timestamp)
TAG="v2.0-async-$(date +%H%M%S)"
##"v$(date +%Y%m%d-%H%M%S)"

echo "🚀 Nueva versión: ${IMAGE}:${TAG}"

echo "🔨 Build..."
docker build --no-cache --pull \
  -t ${IMAGE}:${TAG} \
  ~/spy-options-platform/docker/frontend/

echo "⬆️  Push..."
docker push ${IMAGE}:${TAG}

echo "📝 Actualizando deployment..."
kubectl set image deployment/frontend \
  frontend=${IMAGE}:${TAG} \
  -n spy-options-bot

echo "🔄 Esperando rollout..."
kubectl rollout status deployment/frontend -n spy-options-bot

echo "✅ Deploy completado"

