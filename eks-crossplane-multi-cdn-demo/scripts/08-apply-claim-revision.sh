#!/usr/bin/env bash
set -euo pipefail

REVISION="${1:-v1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAIM_DIR="${SCRIPT_DIR}/../manifests/demo/revisions"
CLAIM_FILE="${CLAIM_DIR}/static-assets-claim-${REVISION}.yaml"

if [[ ! -f "${CLAIM_FILE}" ]]; then
  echo "Unknown revision: ${REVISION}"
  echo "Available revisions:"
  ls -1 "${CLAIM_DIR}" | sed 's/^/  - /'
  exit 1
fi

echo "Applying claim revision ${REVISION} from ${CLAIM_FILE}"
kubectl apply -f "${CLAIM_FILE}"

REQUEST_NAMESPACE="${REQUEST_NAMESPACE:-crossplane-system}"
CLAIM_NAME="static-assets"
AKAMAI_REQUEST_CM="${CLAIM_NAME}-akamai-terraform-request"
CLOUDFLARE_REQUEST_CM="${CLAIM_NAME}-cloudflare-native-request"

trigger_object_reconcile() {
  local request_cm_name="$1"
  local object_name
  object_name="$(kubectl get object.kubernetes.crossplane.io -o jsonpath="{range .items[?(@.spec.forProvider.manifest.metadata.name==\"${request_cm_name}\")]}{.metadata.name}{end}")"
  if [[ -n "${object_name}" ]]; then
    kubectl annotate object.kubernetes.crossplane.io "${object_name}" \
      "reconcile.now=$(date -u +%Y%m%dT%H%M%SZ)" \
      --overwrite >/dev/null || true
    echo "Triggered reconcile for Object ${object_name} (${request_cm_name})"
  fi
}

echo ""
echo "Refreshing adapter request ConfigMaps to prevent stale optional keys"
kubectl delete configmap -n "${REQUEST_NAMESPACE}" \
  "${AKAMAI_REQUEST_CM}" \
  "${CLOUDFLARE_REQUEST_CM}" \
  --ignore-not-found=true

trigger_object_reconcile "${AKAMAI_REQUEST_CM}"
trigger_object_reconcile "${CLOUDFLARE_REQUEST_CM}"

for cm in "${AKAMAI_REQUEST_CM}" "${CLOUDFLARE_REQUEST_CM}"; do
  echo -n "Waiting for ${cm} to be recreated"
  for _ in {1..30}; do
    if kubectl get configmap -n "${REQUEST_NAMESPACE}" "${cm}" >/dev/null 2>&1; then
      echo " ... recreated"
      break
    fi
    echo -n "."
    sleep 2
  done

  if ! kubectl get configmap -n "${REQUEST_NAMESPACE}" "${cm}" >/dev/null 2>&1; then
    echo ""
    echo "Timed out waiting for ${cm} recreation in namespace ${REQUEST_NAMESPACE}"
    exit 1
  fi
done

RETRY_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kubectl annotate configmap -n "${REQUEST_NAMESPACE}" \
  "${AKAMAI_REQUEST_CM}" "${CLOUDFLARE_REQUEST_CM}" \
  milionmonkee.win/retry="${RETRY_TS}" \
  --overwrite >/dev/null
echo "Triggered adapter retry annotation at ${RETRY_TS}"

echo ""
echo "Current claim state:"
kubectl get xdeliveryservices.delivery.milionmonkee.win static-assets \
  -o custom-columns=NAME:.metadata.name,GENERATION:.metadata.generation,REVISION:.metadata.labels.milionmonkee\\.win/claim-revision,SYNCED:.status.conditions[0].status,READY:.status.conditions[2].status
