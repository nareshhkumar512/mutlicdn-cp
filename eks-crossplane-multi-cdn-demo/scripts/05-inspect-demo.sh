#!/usr/bin/env bash
set -euo pipefail

echo "Crossplane Multi-CDN CIO Demo Status"
echo "===================================="

echo ""
echo "XDeliveryService Claims:"
kubectl get xdeliveryservices.delivery.milionmonkee.win -A 2>/dev/null || echo "No XDeliveryService claims found"

echo ""
echo "Generated ConfigMaps (Adapter Requests):"
kubectl get configmaps -n crossplane-system -l 'milionmonkee.win/adapter' 2>/dev/null | \
  awk 'NR==1{print} NR>1{print "  " $1 " (" $3 ")"}' || echo "No adapter ConfigMaps found"

echo ""
echo "Adapter request status objects:"
kubectl get configmaps -n crossplane-system -l 'milionmonkee.win/adapter-status' 2>/dev/null | \
  awk 'NR==1{print} NR>1{print "  " $1 " (" $3 ")"}' || echo "No adapter status ConfigMaps found"

echo ""
echo "Resource Status Summary:"
TOTAL_RESOURCES=$(kubectl get objects -n crossplane-system -l 'crossplane.io/composite=static-assets' --no-headers 2>/dev/null | wc -l || echo "0")
READY_RESOURCES=$(kubectl get objects -n crossplane-system -l 'crossplane.io/composite=static-assets' --no-headers 2>/dev/null | grep -c "True.*True" || echo "0")

echo "  Total managed resources: $TOTAL_RESOURCES"
echo "  Ready resources: $READY_RESOURCES"

if [ "$TOTAL_RESOURCES" -gt 0 ] && [ "$READY_RESOURCES" -eq "$TOTAL_RESOURCES" ]; then
    echo "  All resources are SYNCED and READY"
elif [ "$READY_RESOURCES" -gt 0 ]; then
    echo "  Some resources are still provisioning"
else
    echo "  Resources are not ready yet"
fi

echo ""
echo "Web Dashboard Status:"
kubectl get svc multi-cdn-demo-web -n multi-cdn-demo 2>/dev/null | \
  awk 'NR==1{print} NR>1{print "  " $1 " (" $4 ")"}' || echo "Web service not deployed"

echo ""
echo "Next steps:"
echo "  1. If resources are not ready, wait a few minutes and re-run this script"
echo "  2. Check the web dashboard: ./04-get-demo-url.sh"
echo "  3. View detailed logs: kubectl logs -n crossplane-system -l app.kubernetes.io/name=crossplane"
