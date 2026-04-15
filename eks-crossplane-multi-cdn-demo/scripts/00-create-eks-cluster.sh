#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="/Users/nareshkumarrengasamy/Documents/multicdn-cp/tools/bin:$PATH"

export AWS_PROFILE=default
export AWS_REGION=us-east-2
export CLUSTER_NAME=multicdn-demo-eks
export SSH_ALLOW=false


AWS_PROFILE="${AWS_PROFILE:-}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
CLUSTER_NAME="${CLUSTER_NAME:-multicdn-demo-eks}"
K8S_VERSION="${K8S_VERSION:-1.29}"

export AWS_PAGER=""
NODEGROUP_NAME="${NODEGROUP_NAME:-platform-ng}"
NODE_TYPE="${NODE_TYPE:-t3.large}"
NODE_VOLUME_SIZE="${NODE_VOLUME_SIZE:-20}"
NODES_DESIRED="${NODES_DESIRED:-2}"
NODES_MIN="${NODES_MIN:-2}"
NODES_MAX="${NODES_MAX:-3}"
SSH_ALLOW="${SSH_ALLOW:-false}"

export AWS_PAGER=""

usage() {
  cat <<EOF
Create or reconnect to an EKS cluster for the multi-CDN Crossplane demo.

Usage:
  $(basename "$0") [cluster-name] [region]

Examples:
  $(basename "$0")
  $(basename "$0") multicdn-demo us-east-1
  AWS_PROFILE=my-sandbox NODE_TYPE=m5.large $(basename "$0")

Environment variables:
  AWS_PROFILE        Optional AWS CLI profile to use
  AWS_REGION         AWS region (default: ${AWS_REGION})
  CLUSTER_NAME       Cluster name (default: ${CLUSTER_NAME})
  K8S_VERSION        Kubernetes version (default: ${K8S_VERSION})
  NODEGROUP_NAME     Managed nodegroup name (default: ${NODEGROUP_NAME})
  NODE_TYPE          EC2 instance type for worker nodes (default: ${NODE_TYPE})
  NODE_VOLUME_SIZE   Root volume size in GiB (default: ${NODE_VOLUME_SIZE})
  NODES_DESIRED      Desired worker node count (default: ${NODES_DESIRED})
  NODES_MIN          Minimum worker node count (default: ${NODES_MIN})
  NODES_MAX          Maximum worker node count (default: ${NODES_MAX})
  SSH_ALLOW          Set to true to allow SSH access to nodes (default: ${SSH_ALLOW})
EOF
}

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

aws_cmd() {
  if [[ -n "${AWS_PROFILE}" ]]; then
    aws --profile "${AWS_PROFILE}" "$@"
  else
    aws "$@"
  fi
}

eksctl_cmd() {
  if [[ -n "${AWS_PROFILE}" ]]; then
    eksctl --profile "${AWS_PROFILE}" "$@"
  else
    eksctl "$@"
  fi
}

kubectl_cmd() {
  kubectl "$@"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ge 1 ]]; then
  CLUSTER_NAME="$1"
fi

if [[ $# -ge 2 ]]; then
  AWS_REGION="$2"
fi

require_cmd aws
require_cmd eksctl
require_cmd kubectl

log "Using project root: ${PROJECT_ROOT}"
log "Validating AWS credentials for region ${AWS_REGION}"

ACCOUNT_ID="$(aws_cmd sts get-caller-identity --query Account --output text)"
CALLER_ARN="$(aws_cmd sts get-caller-identity --query Arn --output text)"

log "Authenticated to AWS account ${ACCOUNT_ID} as ${CALLER_ARN}"

cluster_exists() {
  aws_cmd eks describe-cluster \
    --name "${CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    >/dev/null 2>&1
}

associate_oidc() {
  log "Associating IAM OIDC provider with cluster ${CLUSTER_NAME}"
  eksctl_cmd utils associate-iam-oidc-provider \
    --cluster "${CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    --approve
}

write_kubeconfig() {
  log "Updating kubeconfig for cluster ${CLUSTER_NAME}"
  if [[ -n "${AWS_PROFILE}" ]]; then
    aws_cmd eks update-kubeconfig \
      --name "${CLUSTER_NAME}" \
      --region "${AWS_REGION}" \
      --alias "${CLUSTER_NAME}"
  else
    aws eks update-kubeconfig \
      --name "${CLUSTER_NAME}" \
      --region "${AWS_REGION}" \
      --alias "${CLUSTER_NAME}"
  fi
}

if cluster_exists; then
  log "Cluster ${CLUSTER_NAME} already exists in ${AWS_REGION}; skipping creation"
  associate_oidc
  write_kubeconfig
  kubectl_cmd get nodes -o wide
  exit 0
fi

TMP_CONFIG="$(mktemp)"
trap 'rm -f "${TMP_CONFIG}"' EXIT

cat > "${TMP_CONFIG}" <<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig

metadata:
  name: ${CLUSTER_NAME}
  region: ${AWS_REGION}
  version: "${K8S_VERSION}"
  tags:
    Project: multicdn-crossplane-demo
    ManagedBy: eksctl

iam:
  withOIDC: true

cloudWatch:
  clusterLogging:
    enableTypes: ["api", "audit", "authenticator", "controllerManager", "scheduler"]

managedNodeGroups:
  - name: ${NODEGROUP_NAME}
    instanceType: ${NODE_TYPE}
    desiredCapacity: ${NODES_DESIRED}
    minSize: ${NODES_MIN}
    maxSize: ${NODES_MAX}
    volumeSize: ${NODE_VOLUME_SIZE}
    privateNetworking: true
    ssh:
      allow: ${SSH_ALLOW}
    iam:
      withAddonPolicies:
        autoScaler: true
        certManager: true
        cloudWatch: true
        ebs: true
        efs: true
        externalDNS: true
        imageBuilder: true
        xRay: true
EOF

log "Creating EKS cluster ${CLUSTER_NAME} in ${AWS_REGION}"
eksctl_cmd create cluster -f "${TMP_CONFIG}"

write_kubeconfig

log "Verifying cluster connectivity"
kubectl_cmd get nodes -o wide

cat <<EOF

Cluster is ready.

Next steps:
  1. Bootstrap Crossplane:
     ${SCRIPT_DIR}/01-bootstrap-crossplane.sh
  2. Install the demo:
     ${SCRIPT_DIR}/02-install-demo.sh

Cluster details:
  Name:   ${CLUSTER_NAME}
  Region: ${AWS_REGION}
  AWS account: ${ACCOUNT_ID}
EOF
