# Crossplane Multi-CDN Demo

This is a runnable Crossplane demo that shows the core idea for a bank-owned multi-CDN control plane:

- app teams submit one **canonical** `XDeliveryService`
- Crossplane composes it into provider-specific plans
- a shared gateway is referenced centrally
- RBAC/ownership metadata stays in the canonical object
- Akamai and Cloudflare outputs are rendered separately

## What this demo is and is not

This demo is intentionally honest.

It **is**:
- a real Crossplane model
- runnable on a local kind cluster
- useful to explain the control-plane concept to leadership
- structured the way a production design would start

It is **not**:
- a production-grade Akamai/Cloudflare provider
- a full compiler for every edge feature
- a replacement for rollout/approval/drift logic

The provider-specific outputs in this demo are rendered as Kubernetes `ConfigMap` objects via Crossplane's Kubernetes provider. That keeps the demo runnable without needing real Akamai or Cloudflare credentials.

## High-level flow

1. Install Crossplane and provider-kubernetes
2. Apply the XRD for `XDeliveryService`
3. Apply the Composition
4. Create one `XDeliveryService` instance
5. Watch Crossplane generate:
   - an Akamai plan ConfigMap
   - a Cloudflare plan ConfigMap
   - a summary ConfigMap

This demonstrates the key point:
**one canonical intent -> multiple provider-specific plans**

## Repo layout

- `apis/xdeliveryservice-xrd.yaml` - canonical API definition
- `compositions/xdeliveryservice-composition.yaml` - Crossplane Composition
- `claims/demo-deliveryservice.yaml` - sample app-team intent
- `scripts/install.sh` - install Crossplane + provider-kubernetes + demo
- `scripts/inspect.sh` - show generated resources

## Prereqs

- Docker
- kind
- kubectl
- helm

## Quick start

```bash
cd crossplane-multi-cdn-demo
bash scripts/install.sh
bash scripts/inspect.sh
```

## Expected result

You should see three ConfigMaps in the `crossplane-system` namespace:

- `retail-login-akamai-plan`
- `retail-login-cloudflare-plan`
- `retail-login-summary`

Each contains a provider-specific rendering of the same canonical `XDeliveryService`.

## What to say in the demo

Use this line with your director:

> "This shows the shape of the real solution. App teams define one bank-owned API. Crossplane reconciles that into vendor-specific plans. In production, these ConfigMaps become real Akamai and Cloudflare adapters with approvals, policy gates, and drift handling."

## Next production steps after this demo

1. Replace ConfigMap outputs with real custom providers/adapters
2. Add `SharedGateway` and `ProviderBinding` APIs
3. Add OPA/Gatekeeper policy
4. Add Backstage front-end
5. Add approval workflow and audit store
6. Add drift detection and provider readback


## Demo adapters

See `adapters/` for simple Akamai and Cloudflare translators you can run locally to show how the same canonical intent becomes two provider-specific plans.
