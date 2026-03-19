#!/usr/bin/env bash
set -euo pipefail

echo "== XDeliveryService =="
kubectl get xdeliveryservices.delivery.bank.demo
echo

echo "== Crossplane managed Objects =="
kubectl get objects.kubernetes.crossplane.io -A
echo

echo "== Rendered provider-specific ConfigMaps =="
kubectl get configmaps -n crossplane-system | egrep 'retail-login-(akamai-plan|cloudflare-plan|summary)' || true
echo

for cm in retail-login-akamai-plan retail-login-cloudflare-plan retail-login-summary; do
  echo "----- ${cm} -----"
  kubectl get configmap "${cm}" -n crossplane-system -o yaml || true
  echo
done
