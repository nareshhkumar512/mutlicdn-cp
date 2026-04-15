#!/usr/bin/env bash
set -euo pipefail

CLAIM_NAME="${1:-static-assets}"
REQUEST_NAMESPACE="${REQUEST_NAMESPACE:-crossplane-system}"
CF_ZONE_OVERRIDE="${CLOUDFLARE_ZONE_ID:-}"

require_kubectl() {
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required but not installed"
    exit 1
  fi
}

get_claim_field() {
  local jsonpath="$1"
  kubectl get xdeliveryservice "${CLAIM_NAME}" -o "jsonpath=${jsonpath}" 2>/dev/null || true
}

require_kubectl

SERVICE_NAME="$(get_claim_field '{.spec.serviceName}')"
HOSTNAME="$(get_claim_field '{.spec.hostname}')"
CLOUDFLARE_HOSTNAME="$(get_claim_field '{.spec.cloudflareHostname}')"
AKAMAI_HOSTNAME="$(get_claim_field '{.spec.akamaiHostname}')"
RUNTIME_ALB_HOST="$(get_claim_field '{.spec.runtimeAlbHost}')"
PRIMARY_ORIGIN="$(get_claim_field '{.spec.originHost}')"
SECONDARY_ORIGIN="$(get_claim_field '{.spec.secondaryOriginHost}')"
PATH_PREFIX="$(get_claim_field '{.spec.pathPrefix}')"
CACHE_TTL_SECONDS="$(get_claim_field '{.spec.cacheTtlSeconds}')"
TEAM="$(get_claim_field '{.spec.team}')"
LOB="$(get_claim_field '{.spec.lob}')"
DNS_MODE="$(get_claim_field '{.spec.dnsMode}')"
CERT_MODE="$(get_claim_field '{.spec.certificateMode}')"
IDENTITY_PROVIDER="$(get_claim_field '{.spec.identityProvider}')"
AKAMAI_NETWORK="$(get_claim_field '{.spec.akamaiNetwork}')"
AKAMAI_CONTRACT_ID="$(get_claim_field '{.spec.akamaiContractId}')"
AKAMAI_GROUP_ID="$(get_claim_field '{.spec.akamaiGroupId}')"
AKAMAI_PRODUCT_ID="$(get_claim_field '{.spec.akamaiProductId}')"
if [[ -z "${CLOUDFLARE_HOSTNAME}" ]]; then CLOUDFLARE_HOSTNAME="${HOSTNAME}"; fi
if [[ -z "${AKAMAI_HOSTNAME}" ]]; then AKAMAI_HOSTNAME="${HOSTNAME}"; fi
CF_ZONE="${CF_ZONE_OVERRIDE:-${CLOUDFLARE_HOSTNAME}}"
CF_SERVICE_NAME="$(echo "${CLOUDFLARE_HOSTNAME}" | awk -F. '{print $1}')"
if [[ -z "${CF_SERVICE_NAME}" ]]; then CF_SERVICE_NAME="${SERVICE_NAME}"; fi

if [[ -z "${SERVICE_NAME}" || -z "${HOSTNAME}" || -z "${PRIMARY_ORIGIN}" || -z "${RUNTIME_ALB_HOST}" ]]; then
  echo "Claim ${CLAIM_NAME} is missing required fields (serviceName, hostname, runtimeAlbHost, originHost)"
  exit 1
fi

if [[ -z "${PATH_PREFIX}" ]]; then PATH_PREFIX="/static"; fi
if [[ -z "${CACHE_TTL_SECONDS}" ]]; then CACHE_TTL_SECONDS="3600"; fi
if [[ -z "${TEAM}" ]]; then TEAM="unknown-team"; fi
if [[ -z "${LOB}" ]]; then LOB="unknown-lob"; fi
if [[ -z "${DNS_MODE}" ]]; then DNS_MODE="internal-api"; fi
if [[ -z "${CERT_MODE}" ]]; then CERT_MODE="acme-or-custom-ca"; fi
if [[ -z "${IDENTITY_PROVIDER}" ]]; then IDENTITY_PROVIDER="IDAnywhere"; fi
if [[ -z "${AKAMAI_NETWORK}" ]]; then AKAMAI_NETWORK="STAGING"; fi
if [[ -z "${AKAMAI_PRODUCT_ID}" ]]; then AKAMAI_PRODUCT_ID="prd_Fresca"; fi

AKAMAI_TFVARS="$(cat <<EOF
{"service_name":"${SERVICE_NAME}","hostname":"${AKAMAI_HOSTNAME}","runtime_alb_host":"${RUNTIME_ALB_HOST}","primary_origin":"${PRIMARY_ORIGIN}","secondary_origin":"${SECONDARY_ORIGIN}","path_prefix":"${PATH_PREFIX}","cache_ttl_seconds":${CACHE_TTL_SECONDS},"owner_team":"${TEAM}","owner_lob":"${LOB}","dns_mode":"${DNS_MODE}","certificate_mode":"${CERT_MODE}","identity_provider":"${IDENTITY_PROVIDER}","network":"${AKAMAI_NETWORK}","contract_id":"${AKAMAI_CONTRACT_ID}","group_id":"${AKAMAI_GROUP_ID}","product_id":"${AKAMAI_PRODUCT_ID}","activate_property":false}
EOF
)"

AKAMAI_REQUEST="${SERVICE_NAME}-akamai-terraform-decommission-request"
CLOUDFLARE_REQUEST="${SERVICE_NAME}-cloudflare-native-decommission-request"

echo "Submitting Akamai and Cloudflare decommission requests for claim: ${CLAIM_NAME}"
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ${AKAMAI_REQUEST}
  namespace: ${REQUEST_NAMESPACE}
  labels:
    milionmonkee.win/adapter: "true"
    milionmonkee.win/provider: akamai
data:
  provider: akamai
  adapterType: terraform-module
  operation: delete
  modulePath: ./terraform/akamai_static_assets_module
  tfvars: |
    ${AKAMAI_TFVARS}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: ${CLOUDFLARE_REQUEST}
  namespace: ${REQUEST_NAMESPACE}
  labels:
    milionmonkee.win/adapter: "true"
    milionmonkee.win/provider: cloudflare
data:
  provider: cloudflare
  adapterType: native-api
  operation: delete
  zone: ${CF_ZONE}
  hostname: ${CLOUDFLARE_HOSTNAME}
  service_name: ${CF_SERVICE_NAME}
EOF

echo ""
echo "Decommission requests submitted:"
echo "  - ${REQUEST_NAMESPACE}/${AKAMAI_REQUEST}"
echo "  - ${REQUEST_NAMESPACE}/${CLOUDFLARE_REQUEST}"
echo ""
echo "Watch status:"
echo "  kubectl get configmaps -n ${REQUEST_NAMESPACE} -l milionmonkee.win/adapter-status"
echo "  kubectl get configmap -n ${REQUEST_NAMESPACE} ${AKAMAI_REQUEST}-status -o yaml"
echo "  kubectl get configmap -n ${REQUEST_NAMESPACE} ${CLOUDFLARE_REQUEST}-status -o yaml"
