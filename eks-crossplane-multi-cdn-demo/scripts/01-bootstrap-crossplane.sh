#!/usr/bin/env bash
set -euo pipefail
kubectl cluster-info >/dev/null
helm repo add crossplane-stable https://charts.crossplane.io/stable >/dev/null 2>&1 || true
helm repo update >/dev/null 2>&1
helm upgrade --install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --wait
kubectl apply -f ../manifests/base/function-patch-and-transform.yaml
kubectl apply -f ../manifests/base/provider-kubernetes.yaml
kubectl wait --for=condition=Healthy function/function-patch-and-transform --timeout=300s || true
kubectl wait --for=condition=Healthy provider/provider-kubernetes --timeout=300s
kubectl apply -f ../manifests/base/provider-kubernetes-providerconfig.yaml
echo 'Crossplane bootstrap complete.'
