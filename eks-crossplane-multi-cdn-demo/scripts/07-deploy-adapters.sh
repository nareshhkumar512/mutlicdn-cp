#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

kubectl apply -f manifests/adapters/adapter-serviceaccount.yaml
kubectl apply -f manifests/adapters/adapter-clusterrole.yaml
kubectl apply -f manifests/adapters/adapter-clusterrolebinding.yaml
kubectl apply -f manifests/adapters/adapter-pvc.yaml
kubectl apply -f manifests/adapters/adapter-deployment.yaml
kubectl apply -f manifests/adapters/adapter-secret.yaml

echo "Adapters and secrets deployed."