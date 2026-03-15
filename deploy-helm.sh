#!/bin/bash
helm upgrade spy-bot ~/spy-options-platform/helm/spy-trading-bot \
  --reuse-values=false \
  -f ~/spy-options-platform/helm/spy-trading-bot/values.yaml \
  -n spy-options-bot
