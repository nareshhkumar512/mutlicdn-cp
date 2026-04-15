#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
OBS_DIR="${ROOT_DIR}/manifests/observability"

kubectl apply -f "${OBS_DIR}/namespace.yaml"
kubectl apply -f "${OBS_DIR}/fluent-bit-rbac.yaml"
kubectl apply -f "${OBS_DIR}/fluent-bit-configmap.yaml"
kubectl apply -f "${OBS_DIR}/fluent-bit-daemonset.yaml"

echo "Fluent Bit deployed in amazon-cloudwatch namespace."
echo "Pod filter: multi-cdn-demo/multi-cdn-adapter-*"
echo "CloudWatch log group: /eks/multicdn-demo/selected-namespaces"
