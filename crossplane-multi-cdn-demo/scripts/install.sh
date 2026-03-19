#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-crossplane-demo}"

command -v kind >/dev/null 2>&1 || { echo "kind is required"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "helm is required"; exit 1; }

if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "Creating kind cluster: ${CLUSTER_NAME}"
  kind create cluster --name "${CLUSTER_NAME}"
else
  echo "Using existing kind cluster: ${CLUSTER_NAME}"
fi

echo "Installing Crossplane..."
helm repo add crossplane-stable https://charts.crossplane.io/stable >/dev/null 2>&1 || true
helm repo update >/dev/null 2>&1
helm upgrade --install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --wait

echo "Installing function-patch-and-transform..."
kubectl apply -f - <<'EOF'
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-patch-and-transform
spec:
  package: xpkg.crossplane.io/crossplane-contrib/function-patch-and-transform:v0.8.2
EOF

echo "Installing provider-kubernetes..."
kubectl apply -f - <<'EOF'
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
spec:
  package: xpkg.crossplane.io/crossplane-contrib/provider-kubernetes:v0.15.0
EOF

echo "Waiting for provider deployments..."
kubectl wait --for=condition=Healthy provider/provider-kubernetes --timeout=300s || true
kubectl wait --for=condition=Healthy function/function-patch-and-transform --timeout=300s || true

echo "Creating provider config for in-cluster target..."
kubectl apply -f - <<'EOF'
apiVersion: kubernetes.crossplane.io/v1alpha1
kind: ProviderConfig
metadata:
  name: in-cluster
spec:
  credentials:
    source: InjectedIdentity
EOF

echo "Applying XRD and Composition..."
kubectl apply -f apis/xdeliveryservice-xrd.yaml
kubectl apply -f compositions/xdeliveryservice-composition.yaml

echo "Waiting for XRD to establish..."
sleep 10

echo "Creating sample delivery service..."
kubectl apply -f claims/demo-deliveryservice.yaml

echo
echo "Install complete."
echo "Run: bash scripts/inspect.sh"
