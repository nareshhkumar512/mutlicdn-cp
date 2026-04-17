#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
WATCH_LOGS="${WATCH_LOGS:-true}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-200}"
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

# ── Step 1: Delete the claim BEFORE submitting decommission requests.
# Why: While the claim exists, Crossplane continuously reconciles the
# composition, which updates the provisioning request ConfigMaps
# (dev-assets-akamai-terraform-request, etc.) with activate_property=true.
# The adapter watches ALL ConfigMaps with the adapter label. If a
# provisioning ConfigMap gets a new resource_version during decommission,
# the adapter will process it after the decommission completes — running
# terraform apply and re-activating the Akamai property. This creates a
# circular conflict: decommission deactivates → reconcile re-activates.
#
# The 11-decommission-cdns.sh script reads claim fields to build the
# decommission request, so we call it first (to capture claim data into
# the decommission ConfigMaps), then immediately delete the claim.
"${SCRIPT_DIR}/11-decommission-cdns.sh" "${CLAIM_NAME}"

echo "Deleting claim to stop Crossplane reconciliation: ${CLAIM_NAME}"
kubectl delete xdeliveryservice "${CLAIM_NAME}" --ignore-not-found
# Give Crossplane a moment to remove composed provisioning ConfigMaps
sleep 5

if [[ "${FORCE_RETRY}" == "true" ]]; then
  echo "Forcing decommission request retries..."
  kubectl annotate configmap "${CLAIM_NAME}-akamai-terraform-decommission-request" \
    -n crossplane-system milionmonkee.win/retry-ts="$(date +%s)" --overwrite >/dev/null || true
  kubectl annotate configmap "${CLAIM_NAME}-cloudflare-native-decommission-request" \
    -n crossplane-system milionmonkee.win/retry-ts="$(date +%s)" --overwrite >/dev/null || true
fi

# Wait for both decommission status ConfigMaps before deleting the claim.
# This prevents removing the claim while adapters are still working
# (Akamai deactivation can take 5-15+ minutes).
DECOM_TIMEOUT="${DECOM_TIMEOUT:-900}"
DECOM_POLL="${DECOM_POLL:-15}"
AK_STATUS_CM="${CLAIM_NAME}-akamai-terraform-decommission-request-status"
CF_STATUS_CM="${CLAIM_NAME}-cloudflare-native-decommission-request-status"

wait_for_decom_status() {
  local cm_name="$1" provider="$2"
  local elapsed=0
  echo "Waiting for ${provider} decommission to complete (timeout ${DECOM_TIMEOUT}s)..."
  while (( elapsed < DECOM_TIMEOUT )); do
    local status
    status="$(kubectl get configmap "${cm_name}" -n crossplane-system -o jsonpath='{.data.status}' 2>/dev/null || true)"
    if [[ "${status}" == "completed" ]]; then
      echo "${provider} decommission completed."
      return 0
    elif [[ "${status}" == "failed" ]]; then
      echo "WARNING: ${provider} decommission FAILED. Check status ConfigMap: ${cm_name}"
      return 1
    fi
    sleep "${DECOM_POLL}"
    elapsed=$(( elapsed + DECOM_POLL ))
  done
  echo "WARNING: ${provider} decommission timed out after ${DECOM_TIMEOUT}s."
  return 1
}

ak_ok=0; cf_ok=0
wait_for_decom_status "${AK_STATUS_CM}" "Akamai"   || ak_ok=1
wait_for_decom_status "${CF_STATUS_CM}" "Cloudflare" || cf_ok=1

if (( ak_ok + cf_ok > 0 )); then
  echo "One or more decommission requests did not complete successfully."
  echo "Claim was already deleted. To retry decommission, re-run this script."
  echo "  Akamai status:     kubectl get configmap ${AK_STATUS_CM} -n crossplane-system -o yaml"
  echo "  Cloudflare status: kubectl get configmap ${CF_STATUS_CM} -n crossplane-system -o yaml"
  echo "  Adapter logs:      kubectl logs -n multi-cdn-demo deploy/multi-cdn-adapter --tail=200"
fi

if [[ "${WATCH_LOGS}" == "true" ]]; then
  echo ""
  echo "Streaming adapter logs (Ctrl+C to stop):"
  kubectl logs -n multi-cdn-demo deploy/multi-cdn-adapter -f --tail="${LOG_TAIL_LINES}"
fi
