#!/bin/bash
set -e

echo "⚠️  ¿Has copiado values.yaml de Windows → Ubuntu? (y/n)"
read -r respuesta

if [[ ! $respuesta =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelado."
    exit 1
fi

echo "✅ Ejecutando helm upgrade..."
helm upgrade spy-bot ~/spy-options-platform/helm/spy-trading-bot \
  --reuse-values=false \
  -f ~/spy-options-platform/helm/spy-trading-bot/values.yaml \
  -n spy-options-bot

echo ""
echo "✅ Deployment completado"
