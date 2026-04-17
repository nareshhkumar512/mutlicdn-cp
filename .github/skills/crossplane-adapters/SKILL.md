---
#Example usages:
# $crossplane-adapters build/push adapter image, redeploy adapter, and trigger reconcile retry

# $crossplane-adapters add a known-failure pattern to SKILL.md and README troubleshooting section


name: crossplane-adapters
description: "Skill for maintaining the demo Crossplane multi-CDN adapter runtime, including Akamai via Terraform, Cloudflare native API wiring, and claim revision/rollback workflow."

---

# Crossplane Multi-CDN Adapter Skill

Use this skill when you need to:
- generate or update adapter runtime code in `eks-crossplane-multi-cdn-demo/adapters/`
- keep Akamai wired through `adapterType: terraform-module`
- keep Cloudflare wired through `adapterType: native-api`
- update Crossplane request payload mapping in `manifests/demo/xdeliveryservice-composition.yaml`
- maintain claim revision and rollback assets under `manifests/demo/revisions/` and `scripts/08-apply-claim-revision.sh`, `scripts/09-rollback-claim.sh`
- keep CIO-facing demo docs aligned (`README.md`, `docs/DEMO_RUNBOOK.md`)

## Included workflow
- inspect current repository and demo folder structure
- create or update `eks-crossplane-multi-cdn-demo/adapters/`
- create deployment manifests in `eks-crossplane-multi-cdn-demo/manifests/adapters/`
- update composition request payloads in `eks-crossplane-multi-cdn-demo/manifests/demo/xdeliveryservice-composition.yaml`
- add/update helper scripts under `eks-crossplane-multi-cdn-demo/scripts/`
- keep canonical claim at `eks-crossplane-multi-cdn-demo/manifests/demo/static-assets-claim.yaml`
- maintain versioned claims in `eks-crossplane-multi-cdn-demo/manifests/demo/revisions/`
- document runbook updates in `eks-crossplane-multi-cdn-demo/docs/DEMO_RUNBOOK.md`

## CIO demo guardrails
- Do not introduce alternate one-off claim files outside `manifests/demo/revisions/` unless explicitly requested.
- Keep one canonical composition file: `manifests/demo/xdeliveryservice-composition.yaml`.
- Keep one canonical install flow script: `scripts/02-install-demo.sh` using `manifests/demo/static-assets-claim.yaml`.
- If adding cache behavior variants, wire them from claim fields through composition into adapters (do not hardcode per-environment values in adapter code).
- If updating adapter secrets, preserve key names used by `manifests/adapters/adapter-deployment.yaml`.
- For Akamai in this demo, keep `adapterType: terraform-module`; block/avoid Akamai `native-api`.

## New findings (Apr 2026)
- Composition JSON formatting matters: when rendering Terraform numeric fields in `CombineFromComposite`, use `%v` (not `%s`) for integer/number claim fields to avoid malformed JSON (example failure: `%!s(float64=3600)` in `tfvars`).
- Cloudflare pool APIs are account-scoped, not zone-scoped:
  - Use `/accounts/{account_id}/load_balancers/pools`.
  - Resolve `account_id` from zone lookup or provide `CLOUDFLARE_ACCOUNT_ID`.
- Prefer claim-provided zone/hostname when resolving Cloudflare zone; only fall back to `CLOUDFLARE_ZONE_ID` if claim does not provide one.
- If adapter pod logs show `exec format error`, rebuild/push image for `linux/amd64` (EKS nodes in this demo are amd64) and restart adapter deployment.
- Cloudflare decommission naming must account for hostname-derived service labels:
  - Objects may be created with names based on hostname label (for example `assets129-cf-origin-pool`) while claim `serviceName` may be different (for example `static-assets`).
  - Decommission must clean up using both aliases: claim `service_name` and hostname-derived label.
  - Rules cleanup should match both description alias and hostname/expression to remove stale rules like `Block non-allowlisted paths for assets129-cf`.
- `scripts/11-decommission-cdns.sh` should set Cloudflare delete `service_name` from `cloudflareHostname` first label; this avoids pool/monitor misses when claim service name differs.
- Request `ConfigMap` idempotency: `kubectl apply` may show `unchanged` and not retrigger adapter processing; use a retry annotation on request configmaps to force reconcile.

## Operational guard rails (must follow)
- Respect token-scope boundaries:
  - Treat Cloudflare `10000` / `9109` as auth/scope issues and surface clearly.
  - Do not silently "code around" missing permissions; report exact API and code.
- Respect Cloudflare throttling:
  - Treat `10429` and HTTP `429` as rate limit.
  - Retry with `Retry-After` header when present; otherwise backoff.
- Keep Cloudflare payloads API-compatible:
  - Origin pool `weight` values must be floats in `[0.0, 1.0]` (not `100/50`).
  - Do not use `route` action inside `http_request_cache_settings` ruleset phase.
  - Use expression syntax compatible with CF Rules language (for example `starts_with(...)`).
  - If zone phase limit is hit (`20217`), return controlled status (skip ruleset) rather than hard fail.
- Keep DNS operations idempotent:
  - `81053` (record already exists) is non-fatal for this demo path; treat as reusable/existing.
  - Avoid CNAME self-reference attempts when LB already owns DNS (`content == name`).
- Keep decommission idempotent and name-agnostic:
  - Delete Cloudflare LB by hostname.
  - Delete pools/monitors for both possible service aliases (claim name and hostname-derived label).
  - Remove entrypoint rules by alias and hostname match (not alias-only), then treat "not found" as non-fatal cleanup.
- Enforce LB hostname-zone alignment:
  - LB hostname must belong to the resolved zone; if claim hostname is out-of-zone, derive a zone-valid hostname from `service_name + zone`.
  - Resolve zone candidates from FQDN suffixes (for example `assets.a.b.com` -> `a.b.com` -> `b.com`) before falling back.
- Akamai Terraform guard rails:
  - Keep `adapterType=terraform-module`; do not route Akamai through native API in this demo.
  - Use provider-v5-compatible rule schema and enum values (for example valid `verificationMode` values).
  - Keep origin1 as default origin behavior in generated Akamai rule tree.
  - Prevent property-name collisions across retries; naming must be deterministic and collision-resistant.
- Rollout and verification discipline:
  - After image push, restart adapter deployment and wait until exactly one healthy pod is serving.
  - Trigger reconcile via request `ConfigMap` annotation and read `*-request-status` only after retry.
  - Cross-check status with adapter logs when results appear inconsistent.
  - For decommission verification, inspect `*-decommission-request-status` result payload and confirm rule/pool/endpoint deletion explicitly.
- User preference guard rail:
  - When failures are permission-related, report permission issues first and explicitly, instead of defaulting to adapter code changes.

## Real Akamai path (v5 provider)
- The current demo Terraform module may include provider-incompatible schema patterns; a production path requires a provider-v5-compatible module.
- Real Akamai refactor is a larger effort and needs explicit product/workflow choices up front (for example Property Manager workflow, activation model, group/contract lookup strategy, and required behaviors).
- If full refactor is out of scope for a live demo, keep Terraform adapter flow but use a simplified/compatible module that validates cleanly.

## Known failure patterns (signature -> cause -> action)
- `Unable to parse tfvars JSON` / `JSONDecodeError` -> malformed JSON from composition formatting -> use `%v` for numeric fields and reapply composition/claim.
- Cloudflare `errors:[{code:7003|7000, message:"Could not route to /zones/.../pools"}]` -> wrong endpoint scope for pools -> use account-scoped pools API and confirm `account_id`.
- Cloudflare `10000` / `9109` -> token missing permissions -> update Cloudflare token scopes; do not patch adapter logic to bypass.
- Cloudflare `10429` or HTTP `429` -> rate limiting -> honor `Retry-After`, backoff, and retry (prefer serialized DNS creates during churn).
- Cloudflare `81053` (DNS already exists) -> idempotent duplicate create -> treat as reusable existing record.
- Cloudflare decommission leaves `*-origin-pool` / `*-primary` / `*-secondary` -> service-name mismatch (claim name vs hostname-derived label) -> delete using both aliases and rerun decommission.
- Firewall rule remains (for example `Block non-allowlisted paths for assets129-cf`) -> cleanup matched only one alias -> remove entrypoint rules by alias plus hostname/expression match.
- `kubectl apply` shows request ConfigMap `unchanged` but no new adapter run -> no reconcile trigger -> annotate request ConfigMap with retry timestamp.
- Crossplane provider install wait timeout + `no matches for kind "ProviderConfig"` -> provider package/CRDs not healthy yet (or bad package tag) -> fix package version, wait for `Healthy`, then apply ProviderConfig.
- Provider unpack error `MANIFEST_UNKNOWN` from `xpkg.crossplane.io` -> non-existent package tag -> switch to valid provider version and retry install.
- Terraform Akamai `invalid product Id` -> product not enabled/incorrect for contract-group -> use valid Akamai `product_id` from account entitlements.
- Terraform `Error: ... name already in use` for Akamai property/edge host/cpcode -> non-idempotent naming across retries -> reuse-or-update existing resources; avoid always creating new names.
- Adapter pod `exec format error` -> image architecture mismatch -> rebuild image for `linux/amd64`, redeploy adapter.
- EKS bootstrap `DescribeClusterVersions 403`, `CreateStack 403`, `iam:CreateRole unauthorized`, `UnauthorizedTaggingOperation` -> missing IAM permissions -> fix IAM policies before retrying cluster/bootstrap scripts.
- Akamai `cant-delete-active` / `Cannot Delete Active Property` during `terraform destroy` -> property still active when destroy runs -> two causes: (1) deactivation wait timeout too short (now 720s), (2) Crossplane reconcile loop re-activates property via provisioning ConfigMap while decommission is running. Fix: `13-decommission-env.sh` now deletes claim immediately after capturing decommission data to stop Crossplane reconciliation before adapter starts CDN teardown.
- Decommission + reconcile circular conflict -> composition hardcodes `activate_property:true` in provisioning ConfigMap; Crossplane periodically updates it (new resource_version) -> adapter reprocesses after decommission completes -> terraform apply + re-activation. Fix: delete claim before decommission adapter runs so provisioning ConfigMaps are removed and no reconcile can re-activate.
- Terraform state lost after pod restart -> adapter skips destroy (no-state) -> Akamai property/cpcode/edge-hostname orphaned. Fix: (1) PVC at `/data/terraform-adapter` persists state across restarts (`manifests/adapters/adapter-pvc.yaml`), (2) API-based fallback `_api_based_akamai_cleanup` deactivates+deletes property via PAPI when state is missing.

## State cleanliness check (automated)
When the user asks "is everything clean?", "is state clean?", or any variant, run these checks automatically without prompting:

### Check procedure
Run all checks against the cluster and report findings:

```bash
# 1. Claims — should be empty after decommission
kubectl get xdeliveryservice 2>/dev/null

# 2. Composed Crossplane objects — should be empty after decommission
kubectl get object.kubernetes.crossplane.io 2>/dev/null | grep "${CLAIM_NAME}" || true

# 3. Adapter ConfigMaps in crossplane-system — should be empty after decommission
kubectl get configmaps -n crossplane-system | grep "${CLAIM_NAME}" || true

# 4. Terraform state on PVC — should only contain lost+found after decommission
kubectl exec deployment/multi-cdn-adapter -n multi-cdn-demo -- ls -la /data/terraform-adapter/ 2>/dev/null || true

# 5. Adapter pod health — should show 1/1 Running
kubectl get pods -n multi-cdn-demo -l app=multi-cdn-adapter
```

Where `CLAIM_NAME` is derived from environment (dev → `dev-assets`, qa → `qa-assets`, prod → `assets`). If no environment is specified, check for all three patterns.

### Result interpretation
- **Clean**: no claims, no composed objects, no `${CLAIM_NAME}-*` ConfigMaps, PVC has only `lost+found`, adapter pod is 1/1 Running.
- **Not clean**: report each leftover resource and offer to delete. Typical leftovers after decommission:
  - `${CLAIM_NAME}-akamai-terraform-request-status` — original provision status ConfigMap
  - `${CLAIM_NAME}-akamai-terraform-decommission-request` — decommission input ConfigMap
  - `${CLAIM_NAME}-akamai-terraform-decommission-request-status` — decommission result ConfigMap
  - `${CLAIM_NAME}-cloudflare-native-request-status` — original provision status ConfigMap
  - `${CLAIM_NAME}-cloudflare-native-decommission-request` — decommission input ConfigMap
  - `${CLAIM_NAME}-cloudflare-native-decommission-request-status` — decommission result ConfigMap
  - Terraform workspace directories under `/data/terraform-adapter/${CLAIM_NAME}/`

### Cleanup commands (execute when user confirms)
```bash
# Delete all leftover ConfigMaps for the claim
kubectl delete configmap -n crossplane-system -l milionmonkee.win/adapter=true 2>/dev/null
kubectl delete configmap -n crossplane-system \
  ${CLAIM_NAME}-akamai-terraform-decommission-request \
  ${CLAIM_NAME}-akamai-terraform-decommission-request-status \
  ${CLAIM_NAME}-akamai-terraform-request-status \
  ${CLAIM_NAME}-cloudflare-native-decommission-request \
  ${CLAIM_NAME}-cloudflare-native-decommission-request-status \
  ${CLAIM_NAME}-cloudflare-native-request-status \
  2>/dev/null || true

# Clean TF workspace if leftover
kubectl exec deployment/multi-cdn-adapter -n multi-cdn-demo -- rm -rf /data/terraform-adapter/${CLAIM_NAME} 2>/dev/null || true
```

### Re-verify after cleanup
Re-run the check procedure and confirm "Clean — no ${CLAIM_NAME} resources remain" before telling the user the state is ready for a fresh apply.

## Build and push adapter image (automated defaults)
When the user says "build and push image", execute these steps automatically without prompting:
1. Ensure Docker is running: `docker info >/dev/null 2>&1` — if it fails, tell the user to start Docker Desktop and wait for confirmation.
2. Build and push in one command:
   ```bash
   cd eks-crossplane-multi-cdn-demo && REGISTRY=nareshhkumar512 bash scripts/06-build-adapter-image.sh
   ```
   - **Registry**: Docker Hub (`nareshhkumar512`)
   - **Image**: `nareshhkumar512/multi-cdn-adapter:latest`
   - **Platform**: `linux/amd64` (default in script, required for EKS amd64 nodes)
3. After successful push, restart the adapter deployment:
   ```bash
   kubectl rollout restart deployment/multi-cdn-adapter -n multi-cdn-demo
   ```
4. Verify rollout:
   ```bash
   kubectl rollout status deployment/multi-cdn-adapter -n multi-cdn-demo --timeout=120s
   ```
5. Confirm exactly one healthy pod:
   ```bash
   kubectl get pods -n multi-cdn-demo -l app=multi-cdn-adapter
   ```
Do NOT ask which registry or repo to use — the defaults above are authoritative.

## When to use
- "is everything clean?" / "is state clean?" (see state cleanliness check above)
- "build and push image" (see automated defaults above)
- "build agent skills folder"
- "create Crossplane adapter runtime"
- "generate Cloudflare / Akamai adapter scaffolding"
- "wire claim revisions and rollback scripts"
- "add adapter tests and CIO demo docs"
