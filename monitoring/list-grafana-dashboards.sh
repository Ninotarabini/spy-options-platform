GRAFANA_URL="http://localhost:32354"
GRAFANA_USER="admin"
GRAFANA_PASS="<tu-password>"  # Del prometheus-values.yaml

# UIDs a MANTENER
KEEP_UIDS=("os6Bh8Omk" "rYdddlPWk" "4XuMd2Iiz")

echo "📊 DASHBOARDS EN GRAFANA:"
echo "========================"

curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
  "$GRAFANA_URL/api/search?type=dash-db" | \
  jq -r '.[] | "\(.uid)|\(.title)"' | \
  while IFS='|' read -r uid title; do
    if [[ " ${KEEP_UIDS[@]} " =~ " ${uid} " ]]; then
      echo "✅ KEEP  | $uid | $title"
    else
      echo "🗑️  DELETE | $uid | $title"
    fi
  done

echo ""
echo "RESUMEN:"
TOTAL=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" "$GRAFANA_URL/api/search?type=dash-db" | jq '. | length')
echo "Total: $TOTAL dashboards"
echo "Keep: 3 | Delete: $((TOTAL - 3))"
