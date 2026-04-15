#!/usr/bin/env bash
set -euo pipefail
kubectl apply -f ../manifests/demo/namespace.yaml
kubectl apply -f ../manifests/demo/xdeliveryservice-xrd.yaml
kubectl apply -f ../manifests/demo/xdeliveryservice-composition.yaml
sleep 8
kubectl apply -f ../manifests/demo/static-assets-claim.yaml
echo 'Demo resources installed.'
