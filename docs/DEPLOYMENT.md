# Deployment

## Helm

The chart is `helm/aiwf` (v0.2.0). It deploys the backend, frontend, Service,
Ingress, HPA/PDB, optional NetworkPolicy and a pre-install/pre-upgrade migration Job
that runs `alembic upgrade head`.

The chart expects external PostgreSQL and Redis. Create the secret first:

```bash
kubectl create namespace aiwf
kubectl -n aiwf create secret generic aiwf-secrets \
  --from-literal=SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  --from-literal=DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/aiwf" \
  --from-literal=REDIS_URL="redis://:pass@redis:6379/0" \
  --from-literal=METRICS_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

Install or upgrade:

```bash
helm lint helm/aiwf -f helm/aiwf/values-production.yaml
helm template aiwf helm/aiwf -f helm/aiwf/values-production.yaml --namespace aiwf > /tmp/rendered.yaml
helm upgrade --install aiwf helm/aiwf -f helm/aiwf/values-production.yaml --namespace aiwf
```

Set `backend.image.digest` / `frontend.image.digest` for release pinning. Set
`monitoring.serviceMonitor.enabled=true` only when the Prometheus Operator CRDs exist.
`networkPolicy` allows the ingress controller, same-namespace traffic and egress to
DNS/PostgreSQL/Redis/OPA/OTLP ports; adjust it for your platform.

Roll back with `helm rollback aiwf <revision>`. The migration hook runs before the
Deployment rolls, so a failed migration aborts the upgrade.

## Local compose

`docker compose up -d --build` includes Prometheus (`:9090`), Alertmanager (`:9093`)
and Grafana (`:3000`, admin password via `GRAFANA_PASSWORD`, default `admin`). Grafana
provisions the Prometheus datasource and the dashboard in
`infrastructure/grafana/dashboards`.

## Production checklist

- Set a real `SECRET_KEY`, database and Redis credentials; `SEED_DEMO_USERS=false`.
- Do not expose `/metrics` publicly; set `METRICS_TOKEN`. The middleware accepts either `X-Metrics-Token` or `Authorization: Bearer <token>` (configure the scraper accordingly).
- Point `OTEL_EXPORTER_OTLP_ENDPOINT` at your collector.
- Confirm `WORKER_ENABLED=true` on every replica; claims are conditional so multiple
  workers are safe.
- Keep the evidence artifact from `ci/ci.yml` with the release.
