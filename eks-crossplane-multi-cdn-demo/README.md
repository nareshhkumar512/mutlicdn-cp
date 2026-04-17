# EKS Crossplane Multi-CDN CIO Demo

This demo shows a single Crossplane claim driving a multi-CDN delivery service:
- Akamai provisioning through a Terraform module
- Cloudflare provisioning through native APIs
- internal DNS, certificate, and identity requests rendered as platform artifacts
- a small NGINX site to present the demo output

## Canonical demo flow

```bash
cd eks-crossplane-multi-cdn-demo
bash scripts/01-bootstrap-crossplane.sh
bash scripts/06-build-adapter-image.sh
# push the image to a registry your cluster can pull from
kubectl apply -f manifests/adapters/adapter-secret-example.yaml
bash scripts/07-deploy-adapters.sh
bash scripts/02-install-demo.sh
bash scripts/10-deploy-observability.sh
bash scripts/03-deploy-web.sh
bash scripts/04-get-demo-url.sh
```

## Primary files

- `manifests/demo/static-assets-claim.yaml`: canonical CIO demo claim
- `manifests/demo/revisions/`: claim revisions for live change + rollback demo
- `manifests/demo/xdeliveryservice-xrd.yaml`: platform API definition
- `manifests/demo/xdeliveryservice-composition.yaml`: composition that fans out to Akamai, Cloudflare, and internal integrations
- `manifests/adapters/`: adapter runtime deployment and credentials
- `manifests/observability/`: Fluent Bit + CloudWatch logging for selected namespaces
- `scripts/`: step-by-step cluster, platform, adapter, and demo helpers

## Notes

- Replace the placeholders in `manifests/adapters/adapter-secret-example.yaml` before deploying adapters.
- Update `manifests/adapters/adapter-deployment.yaml` if you need to use a different adapter image repository or tag.
- The optional AWS provider examples under `manifests/base/` are not required for this CIO demo path.
- Use `scripts/08-apply-claim-revision.sh v2` to show an in-place configuration change, and `scripts/09-rollback-claim.sh` to roll back.
- Observability setup is documented in `docs/OBSERVABILITY.md`.
- Akamai Terraform activation target is claim-driven via `spec.akamaiNetwork` (`STAGING` or `PRODUCTION`).
