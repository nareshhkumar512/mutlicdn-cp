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

echo ""
echo "Current claim state:"
kubectl get xdeliveryservices.delivery.milionmonkee.win static-assets \
  -o custom-columns=NAME:.metadata.name,GENERATION:.metadata.generation,REVISION:.metadata.labels.milionmonkee\\.win/claim-revision,SYNCED:.status.conditions[0].status,READY:.status.conditions[2].status
