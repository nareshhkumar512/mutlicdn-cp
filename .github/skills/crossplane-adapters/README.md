# Crossplane Adapters Skill

This skill folder provides agent-level guidance and documentation for working with the Crossplane multi-CDN adapter runtime in this repository.

It is intended to support:
- generating runtime adapter files
- creating Cloudflare native API and Terraform/Akamai adapter scaffolding
- producing deployment manifests and helper scripts
- adding tests and documentation for the adapter flow

## Canonical demo references

- Adapter runtime: `eks-crossplane-multi-cdn-demo/adapters/`
- Adapter deployment manifests: `eks-crossplane-multi-cdn-demo/manifests/adapters/`
- Canonical composition: `eks-crossplane-multi-cdn-demo/manifests/demo/xdeliveryservice-composition.yaml`
- Canonical claim: `eks-crossplane-multi-cdn-demo/manifests/demo/static-assets-claim.yaml`
- Claim revisions: `eks-crossplane-multi-cdn-demo/manifests/demo/revisions/`
- Revision scripts:
  - `eks-crossplane-multi-cdn-demo/scripts/08-apply-claim-revision.sh`
  - `eks-crossplane-multi-cdn-demo/scripts/09-rollback-claim.sh`
- Runbook: `eks-crossplane-multi-cdn-demo/docs/DEMO_RUNBOOK.md`

## Guardrails

- Keep Akamai requests on `terraform-module` path for this demo.
- Keep Cloudflare on `native-api` path.
- Avoid reintroducing deprecated or duplicate claim/composition variants outside the canonical + revisions structure.

## Latest operational findings

- Terraform payload rendering from composition must preserve number types (`%v` for numeric fields in JSON templates).
- Cloudflare origin pools are account-level resources; use account-level endpoints and ensure account resolution is correct.
- If `CLOUDFLARE_ZONE_ID` is stale/invalid, claim-provided hostname/zone should be used for zone resolution first.
- For EKS amd64 nodes, publish adapter images as `linux/amd64` to avoid container startup `exec format error`.
- Real Akamai provider-v5 implementation is a larger refactor and should be treated as a dedicated workstream with explicit Akamai workflow decisions.

## Guard rails for upcoming adapters

- Report permission issues first:
  - Cloudflare `10000` / `9109` and equivalent auth errors should be surfaced as token/scope problems.
  - Do not hide scope failures with code changes unless explicitly requested.
- Implement rate-limit resilience:
  - Handle Cloudflare `10429` / HTTP `429` with retries and `Retry-After` support.
- Keep Cloudflare requests schema-correct:
  - Pool weights in `[0.0, 1.0]`.
  - No `route` action in `http_request_cache_settings` rulesets.
  - Use valid rules expressions and tolerate phase cap (`20217`) gracefully.
- Keep reconciliation idempotent:
  - DNS `81053` (already exists) is non-fatal and should be treated as success.
  - Avoid self-referential DNS writes in LB flow.
- Keep LB names zone-valid:
  - LB hostname must belong to resolved zone from secret/claim.
  - If claim hostname is out-of-zone, derive a zone-valid host from service name + zone.
- Akamai Terraform path:
  - Keep Akamai on `terraform-module`.
  - Use provider-v5-compatible rule payloads and valid enum values.
  - Keep origin1 as the default origin behavior.
- Operational run discipline:
  - Build/push amd64 image, restart adapter deployment, ensure single healthy pod, trigger retry, then verify status + logs together.
