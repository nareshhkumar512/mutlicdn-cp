# Demo architecture notes

This demo uses:
- Crossplane XRD for the canonical API
- Crossplane Composition in pipeline mode
- function-patch-and-transform for rendering
- provider-kubernetes to create Kubernetes-native output objects

Why ConfigMaps?
Because they make the demo fully runnable without real Akamai/Cloudflare credentials.

How this becomes real:
- Replace ConfigMaps with custom managed resources or adapter services
- Add provider readback and drift detection
- Add OPA/Gatekeeper policy
- Add approval and audit workflows
