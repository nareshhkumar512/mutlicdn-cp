#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
REVISION="${2:-v1}"
WATCH_LOGS="${WATCH_LOGS:-true}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-200}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Rolling back ${ENV_NAME} to ${REVISION}"
WATCH_LOGS="${WATCH_LOGS}" LOG_TAIL_LINES="${LOG_TAIL_LINES}" \
  "${SCRIPT_DIR}/12-apply-env-claim.sh" "${ENV_NAME}" "${REVISION}"
