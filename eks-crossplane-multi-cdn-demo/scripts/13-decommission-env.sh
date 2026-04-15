#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
WATCH_LOGS="${WATCH_LOGS:-true}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-200}"
DELETE_CLAIM_AFTER_DECOM="${DELETE_CLAIM_AFTER_DECOM:-true}"
FORCE_RETRY="${FORCE_RETRY:-true}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${ENV_NAME}" in
  dev) CLAIM_NAME="dev-assets" ;;
  qa) CLAIM_NAME="qa-assets" ;;
  prod) CLAIM_NAME="assets" ;;
  *)
    echo "Unknown env: ${ENV_NAME}"
    echo "Use one of: dev, qa, prod"
    exit 1
    ;;
esac

echo "Submitting decommission for ${ENV_NAME} (${CLAIM_NAME})"
"${SCRIPT_DIR}/11-decommission-cdns.sh" "${CLAIM_NAME}"

if [[ "${FORCE_RETRY}" == "true" ]]; then
  echo "Forcing decommission request retries..."
  kubectl annotate configmap "${CLAIM_NAME}-akamai-terraform-decommission-request" \
    -n crossplane-system milionmonkee.win/retry-ts="$(date +%s)" --overwrite >/dev/null || true
  kubectl annotate configmap "${CLAIM_NAME}-cloudflare-native-decommission-request" \
    -n crossplane-system milionmonkee.win/retry-ts="$(date +%s)" --overwrite >/dev/null || true
fi

if [[ "${DELETE_CLAIM_AFTER_DECOM}" == "true" ]]; then
  echo "Deleting claim to prevent recreate: ${CLAIM_NAME}"
  kubectl delete xdeliveryservice "${CLAIM_NAME}" --ignore-not-found
fi

if [[ "${WATCH_LOGS}" == "true" ]]; then
  echo ""
  echo "Streaming adapter logs (Ctrl+C to stop):"
  kubectl logs -n multi-cdn-demo deploy/multi-cdn-adapter -f --tail="${LOG_TAIL_LINES}"
fi
