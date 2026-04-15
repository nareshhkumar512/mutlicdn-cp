#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for LoadBalancer to be ready..."
kubectl wait --for=condition=ready pod -l app=multi-cdn-demo-web -n multi-cdn-demo --timeout=300s

ENDPOINT="$(kubectl get svc multi-cdn-demo-web -n multi-cdn-demo -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
if [[ -z "${ENDPOINT}" ]]; then
  ENDPOINT="$(kubectl get svc multi-cdn-demo-web -n multi-cdn-demo -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
fi

if [[ -z "${ENDPOINT}" ]]; then
  echo "LoadBalancer not ready yet. Run 'kubectl get svc multi-cdn-demo-web -n multi-cdn-demo' to check status."
  exit 1
fi

echo "Demo endpoint: ${ENDPOINT}"
echo "Demo URL: http://${ENDPOINT}"
