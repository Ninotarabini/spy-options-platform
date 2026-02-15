#!/bin/bash
set -e

IMAGE="acrspyoptions.azurecr.io/spy-frontend"

# TAG con Fecha y Hora para trazabilidad total
TAG="v2.0-$(date +%Y%m%d-%H%M%S)"

echo "🚀 Nueva versión: ${IMAGE}:${TAG}"

# Inyectar el TAG en el código fuente
sed -i "s/##APP_VERSION##/${TAG}/g" ~/spy-options-platform/docker/frontend/config.template.js

echo "🔨 Build..."
docker build --no-cache --pull \
  -t ${IMAGE}:${TAG} \
  ~/spy-options-platform/docker/frontend/

# Restaurar el marcador en el archivo local inmediatamente después del build
# Esto evita que el timestamp se quede "pegado" en tu código fuente
sed -i "s/${TAG}/##APP_VERSION##/g" ~/spy-options-platform/docker/frontend/config.template.js

az acr login --name acrspyoptions
echo "⬆️  Push..."
docker push ${IMAGE}:${TAG}

echo "📝 Actualizando deployment..."
kubectl set image deployment/frontend \
  frontend=${IMAGE}:${TAG} \
  -n spy-options-bot

echo "🔄 Esperando rollout..."
kubectl rollout status deployment/frontend -n spy-options-bot

echo "✅ Deploy completado"

