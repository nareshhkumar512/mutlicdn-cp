#!/usr/bin/env bash
set -euo pipefail
kubectl apply -f manifests/web/demo-html-configmap.yaml
kubectl apply -f manifests/web/nginx-deployment.yaml
kubectl apply -f manifests/web/nginx-service.yaml
echo 'Demo web app deployed.'
