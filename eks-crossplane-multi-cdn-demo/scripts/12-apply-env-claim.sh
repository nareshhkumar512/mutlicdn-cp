#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
REVISION="${2:-v1}"
WATCH_LOGS="${WATCH_LOGS:-true}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-200}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAIM_DIR="${SCRIPT_DIR}/../manifests/demo/environments"

case "${ENV_NAME}" in
  dev) CLAIM_BASENAME="dev-assets" ;;
  qa) CLAIM_BASENAME="qa-assets" ;;
  prod) CLAIM_BASENAME="assets" ;;
  *)
    echo "Unknown env: ${ENV_NAME}"
    echo "Use one of: dev, qa, prod"
    exit 1
    ;;
esac

CLAIM_FILE="${CLAIM_DIR}/${CLAIM_BASENAME}-claim-${REVISION}.yaml"
if [[ ! -f "${CLAIM_FILE}" ]]; then
  echo "Claim manifest not found: ${CLAIM_FILE}"
  exit 1
fi

echo "Applying ${ENV_NAME} claim revision ${REVISION} from ${CLAIM_FILE}"
kubectl apply --validate=false -f "${CLAIM_FILE}"

echo ""
echo "Current ${ENV_NAME} claim state:"
kubectl get xdeliveryservices.delivery.milionmonkee.win "${CLAIM_BASENAME}" \
  -o custom-columns=NAME:.metadata.name,GENERATION:.metadata.generation,REVISION:.metadata.labels.milionmonkee\\.win/claim-revision,SYNCED:.status.conditions[0].status,READY:.status.conditions[2].status

if [[ "${WATCH_LOGS}" == "true" ]]; then
  echo ""
  echo "Streaming adapter logs (Ctrl+C to stop):"
  kubectl logs -n multi-cdn-demo deploy/multi-cdn-adapter -f --tail="${LOG_TAIL_LINES}"
fi
