# Observability: Adapter-Pod CloudWatch Logs

This demo uses Fluent Bit to send only adapter pod logs to CloudWatch Logs.

## Included pod filter

- namespace: `multi-cdn-demo`
- pod name: `multi-cdn-adapter-*`

Filter is configured in:
- `manifests/observability/fluent-bit-configmap.yaml`

## Deploy

```bash
bash scripts/10-deploy-observability.sh
```

## Verify

```bash
kubectl get pods -n amazon-cloudwatch
kubectl logs -n amazon-cloudwatch -l app=fluent-bit --tail=100
```

CloudWatch log group:
- `/eks/multicdn-demo/selected-namespaces`

## Notes

- Set `AWS_REGION` in `manifests/observability/fluent-bit-daemonset.yaml` if your demo cluster is not in `us-east-2`.
- The worker node role or Fluent Bit service account (IRSA) must allow:
  - `logs:CreateLogGroup`
  - `logs:CreateLogStream`
  - `logs:PutLogEvents`
  - `logs:DescribeLogStreams`
