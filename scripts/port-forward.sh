#!/bin/bash
# Usage: ./scripts/port-forward.sh backend [port]
APP=$1
LOCAL_PORT=${2:-18000}
NAMESPACE="spy-options-bot"

pkill -f "port-forward" 2>/dev/null

POD=$(kubectl get pods -n $NAMESPACE -l app=$APP \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD" ]; then
  echo "❌ No running pod found for app=$APP"
  exit 1
fi

echo "🎯 Pod: $POD"
echo "🔗 Forwarding: localhost:$LOCAL_PORT → pod:8000"
echo "🧪 Test: curl http://localhost:$LOCAL_PORT/health"
echo ""
kubectl port-forward -n $NAMESPACE pod/$POD $LOCAL_PORT:8000
EOFcat > scripts/port-forward.sh << 'EOF'
#!/bin/bash
# Usage: ./scripts/port-forward.sh backend [port]
APP=$1
LOCAL_PORT=${2:-18000}
NAMESPACE="spy-options-bot"

pkill -f "port-forward" 2>/dev/null

POD=$(kubectl get pods -n $NAMESPACE -l app=$APP \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD" ]; then
  echo "❌ No running pod found for app=$APP"
  exit 1
fi

echo "🎯 Pod: $POD"
echo "🔗 Forwarding: localhost:$LOCAL_PORT → pod:8000"
echo "🧪 Test: curl http://localhost:$LOCAL_PORT/health"
echo ""
kubectl port-forward -n $NAMESPACE pod/$POD $LOCAL_PORT:8000
