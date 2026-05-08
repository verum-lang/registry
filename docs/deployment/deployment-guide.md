# Deployment guide — verum-registry

End-to-end procedure for bringing up a verum-registry instance from
scratch. Three deployment shapes are supported:

  1. **Hosted production** — the canonical `vcogs.io` topology.
  2. **Self-hosted enterprise** — internal mirror inside an org's
     own k8s cluster, federated with vcogs.io.
  3. **Local development** — single-node compose stack for local
     work and CI integration tests.

For day-2 operations once you're up, see
[`../operations/operator-runbook.md`](../operations/operator-runbook.md).

## 1. Architecture overview

```
                             ┌────────────────┐
   verum-cli ─── HTTPS ──→  │ ingress-nginx  │ ←─── TLS via cert-manager
   (publish/                 └───────┬────────┘
    install/                         │
    audit)                           ▼
                             ┌────────────────┐
                             │ verum-registry │ ← HPA 3-24 replicas
                             │   (deployment) │
                             └─┬────┬────┬────┘
                               │    │    │
                ┌──────────────┘    │    └─────────────┐
                ▼                   ▼                  ▼
          ┌──────────┐        ┌──────────┐       ┌──────────┐
          │ postgres │        │  redis   │       │  meili   │
          │ (PG 17)  │        │ sentinel │       │  search  │
          └──────────┘        └──────────┘       └──────────┘
                │
                ▼
          ┌──────────┐        ┌──────────┐       ┌──────────┐
          │   S3     │        │ sigstore │       │   TUF    │
          │ (cogs)   │        │ public   │       │ (CF+S3)  │
          └──────────┘        └──────────┘       └──────────┘
```

## 2. Prerequisites

| Requirement | Hosted prod | Enterprise | Local dev |
|---|---|---|---|
| Kubernetes 1.28+ | yes | yes | optional (kind/minikube) |
| Helm 3.12+ | yes | yes | yes |
| cert-manager | yes | yes | no |
| External DNS controller | yes | optional | no |
| Postgres 17 | yes (managed RDS preferred) | yes | docker |
| Redis 7 (sentinel) | yes | yes | docker |
| MeiliSearch 1.7+ | yes | yes | docker |
| S3-compatible store | AWS S3 | MinIO/S3 | MinIO |
| OIDC provider | login.verum-lang.org | own IdP | mock |
| Sigstore | public Rekor+Fulcio | private optional | private optional |
| TUF metadata host | tuf.vcogs.io | self-hosted CF or nginx | static file |

## 3. Hosted production deployment

### 3.1 Pre-flight
  - [ ] AWS account with EKS, RDS, ElastiCache, S3, IAM, CloudFront
        access provisioned by terraform/iac/.
  - [ ] DNS for vcogs.io + tuf.vcogs.io delegated to Route53.
  - [ ] GHCR pull secret created in cluster.
  - [ ] TUF root key ceremony §5 completed; signed root in
        `s3://verum-registry-tuf/1.root.json`.

### 3.2 Bootstrap (terraform first)
```bash
cd terraform/iac/prod
terraform init
terraform apply

# Outputs (you'll need these for helm values):
#   eks_cluster_name
#   pg_rds_endpoint
#   redis_elasticache_endpoint
#   s3_bucket_name
#   s3_kms_key_arn
#   tuf_cloudfront_distribution
```

### 3.3 Cluster prep
```bash
aws eks update-kubeconfig --name verum-prod-us-east-1

# Required cluster-level addons
helm repo add jetstack            https://charts.jetstack.io
helm repo add ingress-nginx       https://kubernetes.github.io/ingress-nginx
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana             https://grafana.github.io/helm-charts
helm repo add external-secrets    https://charts.external-secrets.io

# Install in sequence
helm upgrade --install --namespace cert-manager --create-namespace \
    cert-manager jetstack/cert-manager --set installCRDs=true

helm upgrade --install --namespace ingress-nginx --create-namespace \
    ingress-nginx ingress-nginx/ingress-nginx -f deploy/helm/ingress-nginx-values.yaml

helm upgrade --install --namespace external-secrets --create-namespace \
    external-secrets external-secrets/external-secrets

helm upgrade --install --namespace observability --create-namespace \
    kube-prometheus-stack prometheus-community/kube-prometheus-stack \
    -f deploy/observability/kube-prometheus-stack-values.yaml
```

### 3.4 Secrets
ExternalSecrets pull from AWS Secrets Manager (or Vault). The chart
expects a single secret `verum-registry-secrets` with keys:

```yaml
DATABASE_URL: postgres://...
REDIS_URL: redis://...
S3_ACCESS_KEY: AKIA...
S3_SECRET_KEY: ...
OIDC_CLIENT_SECRET: ...
ADMIN_TOKEN_REINDEX: ...
WEBAUTHN_PEPPER: ...
SIGNING_KEY: ${OFFLINE_HSM_PUBLIC}   # PUBLIC only; private stays in HSM
```

Apply the ExternalSecret resource:
```bash
kubectl apply -f deploy/helm/registry/external-secret.yaml
```

### 3.5 Deploy registry
```bash
helm --namespace verum-registry-prod upgrade --install registry \
    oci://ghcr.io/verum-lang/charts/registry \
    --version <X.Y.Z> \
    -f deploy/helm/registry/production.values.yaml \
    --create-namespace --atomic --timeout 15m --wait
```

### 3.6 Post-deploy verification
```bash
# Pods Ready
kubectl --namespace verum-registry-prod get pods

# DNS + TLS
curl -fsS -v https://vcogs.io/health/live   2>&1 | grep -E 'HTTP/|subject:'

# Self-audit must pass
curl -fsS https://vcogs.io/api/audit/self | jq '.passed'

# TUF root reachable
curl -fsS https://tuf.vcogs.io/root.json | jq '.signed.expires'

# Smoke publish (against staging cog)
verum publish --registry vcogs.io ./fixtures/hello-cog
verum search --registry vcogs.io hello
verum install --registry vcogs.io scope/hello
```

## 4. Self-hosted enterprise deployment

For an internal mirror federated with vcogs.io.

### 4.1 Federation modes
  - **Read-only mirror**: pulls from vcogs.io upstream; publishes
    rejected. Simplest, recommended for offline-friendly mirrors.
  - **Authoritative scope**: organization owns a scope (e.g.
    `acme/`); publishes locally + replicates to vcogs.io upstream.
  - **Air-gapped**: no upstream connectivity; runs own TUF root,
    own Sigstore (or trust-on-deployment).

### 4.2 Configuration deltas vs hosted prod
  - `values.yaml`:
    - `federation.upstream: https://vcogs.io` (read-only)
    - `federation.scopeOwnership: ["acme"]` (authoritative)
    - `federation.airGapped: true` (full air-gap)
  - Replace TUF root with self-signed (run §5 from
    [tuf-root-ceremony](../security/tuf-root-ceremony.md) with internal
    quorum holders).
  - Replace `vcogs.io` URLs in ingress with internal hostname.
  - `auditGate.mode: warn` initially; flip to `strict` once
    @arch_module annotations are stable across internal cogs.

### 4.3 Bootstrap
Same as §3.5 but with `enterprise.values.yaml`.

## 5. Local development deployment

```bash
cd deploy/compose
cp .env.example .env       # edit if needed
docker compose -f docker-compose.dev.yaml up -d

# Services:
#   localhost:8080  registry HTTP
#   localhost:5432  postgres (verum/verum/registry)
#   localhost:6379  redis
#   localhost:7700  meilisearch
#   localhost:9000  minio (S3)
#   localhost:9001  minio console

# Smoke
curl -fsS http://localhost:8080/health/live
verum publish --registry http://localhost:8080 ./fixtures/hello-cog
```

The dev compose uses:
  - Mock OIDC provider (test-tenant tokens).
  - Self-signed TUF root (regenerated each `compose up` unless
    `TUF_PERSIST=1`).
  - `auditGate.mode: warn` to avoid blocking local iteration.

## 6. Upgrade procedure

Always upgrade staging first; soak ≥24 h before promoting to prod.

```bash
# 1. Bump version
helm --namespace verum-registry-stage upgrade registry \
    oci://ghcr.io/verum-lang/charts/registry --version <NEW> \
    -f deploy/helm/registry/staging.values.yaml --wait

# 2. Smoke test on staging
make -C tests/e2e ENV=staging

# 3. Promote to prod once staging stable
helm --namespace verum-registry-prod upgrade registry \
    oci://ghcr.io/verum-lang/charts/registry --version <NEW> \
    -f deploy/helm/registry/production.values.yaml \
    --atomic --timeout 15m --wait
```

For rollback, see operator-runbook §3.2.

## 7. Decommissioning

If retiring a registry instance:
1. Add a deprecation banner via ConfigMap (`status.deprecation.enabled=true`).
2. Open 90-day notice window; communicate via blog/RSS.
3. Make read-only (helm value `mode.readOnly=true`); publishes 410.
4. After window: backup final database snapshot to long-term cold
   storage; archive S3 bucket via AWS Glacier deep-archive.
5. Tear down via `helm uninstall registry -n verum-registry-prod`
   then `terraform destroy`.
6. Retain TUF root metadata for ≥3 years post-decommission so
   archived clients can still verify historical artifacts.

## 8. Cross-reference

  - [`../operations/operator-runbook.md`](../operations/operator-runbook.md) — day-2 ops
  - [`../operations/incident-runbook.md`](../operations/incident-runbook.md) — incident triage
  - [`../operations/dr.md`](../operations/dr.md) — DR / failover
  - [`../security/tuf-root-ceremony.md`](../security/tuf-root-ceremony.md) — TUF rotation
  - [`../api/openapi.yaml`](../api/openapi.yaml) — public API surface
  - Helm chart: `deploy/helm/registry/`
