#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Rolling back static-assets claim to baseline revision v1"
"${SCRIPT_DIR}/08-apply-claim-revision.sh" v1

