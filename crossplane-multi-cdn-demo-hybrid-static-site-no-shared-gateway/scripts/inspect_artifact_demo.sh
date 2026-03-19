#!/usr/bin/env bash
set -euo pipefail

kubectl get xdeliveryservices.delivery.bank.demo
echo
kubectl get configmaps -n crossplane-system | egrep 'static-assets-(summary|cloudflare-native-request|akamai-terraform-request)' || true
echo

for cm in static-assets-summary static-assets-cloudflare-native-request static-assets-akamai-terraform-request; do
  echo "----- ${cm} -----"
  kubectl get configmap "${cm}" -n crossplane-system -o yaml || true
  echo
done
