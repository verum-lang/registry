# Operator runbook — verum-registry

Daily-operations reference for the registry's on-call rotation.
For incident-time triage, see [`incident-runbook.md`](./incident-runbook.md).
For DR, see [`dr.md`](./dr.md).

## 1. Where things live

| Concern | Location |
|---|---|
| Production cluster | `aws-eks/verum-prod-us-east-1` |
| Standby cluster | `aws-eks/verum-prod-eu-west-1` |
| Helm release | `verum-registry-prod` namespace, `registry` chart |
| Container image | `ghcr.io/verum-lang/registry:<tag>` (cosign-signed) |
| Postgres | `pg-prod-0` StatefulSet, namespace `verum-registry-prod` |
| Redis | `redis-prod-0/1/2` (3-node sentinel) |
| MeiliSearch | `meili-prod-0` StatefulSet |
| MinIO/S3 | AWS S3, bucket `verum-registry-prod` |
| TUF metadata | `s3://verum-registry-tuf/` + CloudFront `tuf.vcogs.io` |
| Sigstore | Public-good Rekor + Fulcio (no self-hosted) |
| Backups | `s3://verum-registry-backup/` (age-encrypted) |

## 2. Daily checklist (on-call, ~10 min)

### Morning sync
```bash
# Cluster health
kubectl --namespace=verum-registry-prod get pods,svc,ingress

# Pod-level resource pressure (top consumers)
kubectl --namespace=verum-registry-prod top pods --sort-by=memory | head -20

# Recent restart count (anything >0 in last 24h?)
kubectl --namespace=verum-registry-prod get pods \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}' \
    | awk '$2 > 0'

# Self-audit must pass
curl -fsS https://vcogs.io/api/audit/self | jq -r '.passed // "FAIL"'
```

### Dashboards to scan (Grafana)
1. `verum-registry-overview` — request rate, error rate, latency.
   Anything off-baseline?
2. `verum-registry-supply-chain` — Sigstore success rate, TUF
   root age, audit-self status.
3. `kube-state-metrics-cluster` — node pressure, pod restarts.

### Log spot-check
```bash
# Anything ERROR-level in the last hour?
kubectl --namespace=verum-registry-prod logs \
    -l app.kubernetes.io/name=verum-registry --since=1h \
    --max-log-requests=10 | grep -i 'level=error' | head -50
```

If anything looks off → follow [`incident-runbook.md`](./incident-runbook.md).

## 3. Routine operations

### 3.1 Deploy a new registry version
```bash
# 1. Verify the candidate image cosign-verifies
cosign verify ghcr.io/verum-lang/registry:v0.5.2 \
    --certificate-identity-regexp='https://github.com/verum-lang/.*' \
    --certificate-oidc-issuer='https://token.actions.githubusercontent.com'

# 2. Helm dry-run on production values
helm --namespace verum-registry-prod template registry \
    oci://ghcr.io/verum-lang/charts/registry \
    --version 0.5.2 \
    -f deploy/helm/registry/production.values.yaml \
    | tee /tmp/registry-rendered.yaml

# 3. Apply (rolling deploy, surge=25% maxUnavailable=0)
helm --namespace verum-registry-prod upgrade registry \
    oci://ghcr.io/verum-lang/charts/registry \
    --version 0.5.2 \
    -f deploy/helm/registry/production.values.yaml \
    --atomic --timeout 10m --wait

# 4. Watch rollout
kubectl --namespace verum-registry-prod rollout status \
    deployment/verum-registry -w

# 5. Smoke check
curl -fsS https://vcogs.io/health/live
curl -fsS https://vcogs.io/health/ready
verum search example | head -5

# 6. Confirm self-audit passes after rollout
curl -fsS https://vcogs.io/api/audit/self | jq '.passed'
```

### 3.2 Rollback
```bash
# Inspect history
helm --namespace verum-registry-prod history registry

# Roll back to previous revision
helm --namespace verum-registry-prod rollback registry --wait

# Or to a specific revision
helm --namespace verum-registry-prod rollback registry 42 --wait
```

### 3.3 Scale up/down for traffic surge
```bash
# Manual scale (HPA is authoritative; this is for emergency overrides)
kubectl --namespace verum-registry-prod scale \
    deployment/verum-registry --replicas=12

# Inspect HPA status
kubectl --namespace verum-registry-prod get hpa registry-hpa
```

### 3.4 Drain a node (planned maintenance)
```bash
# 1. Cordon
kubectl cordon ip-10-0-1-50.ec2.internal

# 2. Drain (PDB will block if under 80% of healthy)
kubectl drain ip-10-0-1-50.ec2.internal \
    --ignore-daemonsets --delete-emptydir-data --grace-period=120
```

### 3.5 Postgres maintenance (vacuum / reindex)
```bash
# Connect via session
kubectl --namespace verum-registry-prod exec -it postgres-prod-0 -- \
    psql -U verum -d registry

# Background VACUUM ANALYZE on the largest table
\timing
VACUUM (ANALYZE, VERBOSE) cog_versions;

# Bloat check
SELECT schemaname, relname, n_live_tup, n_dead_tup,
       round(n_dead_tup * 100.0 / nullif(n_live_tup, 0), 2) AS pct_dead
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC LIMIT 10;
```

### 3.6 Redis maintenance
```bash
# Memory + key-space stats
kubectl --namespace verum-registry-prod exec -it redis-prod-0 -- \
    redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human'
kubectl --namespace verum-registry-prod exec -it redis-prod-0 -- \
    redis-cli INFO keyspace

# Sentinel quorum check
kubectl --namespace verum-registry-prod exec -it redis-prod-0 -- \
    redis-cli -p 26379 SENTINEL get-master-addr-by-name verum-master
```

### 3.7 MeiliSearch reindex
```bash
# Full reindex from postgres (degrades search latency for ~10-15min)
curl -X POST https://vcogs.io/admin/search/reindex \
    -H "X-Admin-Token: $(kubectl --namespace verum-registry-prod \
                          get secret admin-tokens -o jsonpath='{.data.reindex}' \
                          | base64 -d)"

# Watch progress
watch -n 5 'curl -s https://meili.internal/indexes/cogs/stats | jq .'
```

### 3.8 Rotate database credentials
```bash
# 1. Generate new password via Vault
vault write -force database/rotate-role/registry-app

# 2. Watch ExternalSecret refresh (default 60s sync)
kubectl --namespace verum-registry-prod get externalsecret verum-registry-secrets -w

# 3. Trigger rolling restart so pods pick up the new password
kubectl --namespace verum-registry-prod rollout restart \
    deployment/verum-registry
```

### 3.9 Rotate WebAuthn / OIDC keys
Done quarterly. See [`security/key-rotation.md`](../security/key-rotation.md)
(planned; tracked separately).

## 4. Configuration reference

### 4.1 Environment variables (registry pod)
| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | from secret | postgres DSN |
| `DATABASE_MAX_POOL` | 64 | per-replica pool size |
| `REDIS_URL` | from secret | sentinel URL |
| `S3_BUCKET` | `verum-registry-prod` | object store |
| `MEILI_URL` | `http://meili-prod:7700` | search backend |
| `SIGSTORE_REKOR_URL` | `https://rekor.sigstore.dev` | swappable for HA |
| `TUF_REMOTE` | `https://tuf.vcogs.io` | client-facing TUF root |
| `OIDC_ISSUER` | `https://login.verum-lang.org` | auth |
| `WEBAUTHN_RP_ID` | `vcogs.io` | passkey relying-party id |
| `LOG_LEVEL` | `info` | one of `trace|debug|info|warn|error` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | trace export |

### 4.2 Helm value overrides
See `deploy/helm/registry/values.yaml` for the full schema.
Production overrides are in `deploy/helm/registry/production.values.yaml`.

## 5. Common ops queries

### Top publishing scopes (last 7 days)
```sql
SELECT scope, count(*) AS publishes
FROM cog_versions
WHERE published_at > now() - interval '7 days'
GROUP BY scope
ORDER BY publishes DESC LIMIT 20;
```

### Cogs by total download count (last 30 days)
```sql
SELECT scope || '/' || name AS cog, sum(downloads_30d) AS total
FROM cog_metrics_daily
WHERE day > now() - interval '30 days'
GROUP BY cog ORDER BY total DESC LIMIT 50;
```

### Failed publishes by user (last 24h)
```sql
SELECT publisher_id, count(*) AS failures, max(failure_reason) AS reason_sample
FROM publish_audit
WHERE failed_at > now() - interval '24 hours'
GROUP BY publisher_id
ORDER BY failures DESC;
```

## 6. On-call escalation

  - **L1 (you)**: Acknowledge, follow runbook, mitigate.
  - **L2 (architecture-team)**: Escalate when AP-pattern violations
    or core type-system bugs surface (>30min triage with no path).
  - **L3 (security-team)**: Escalate ANY suspected supply-chain
    compromise — TUF metadata anomaly, Sigstore signature
    validation failures with no upstream cause, unauthorized
    publish-audit events.
  - **VP / Foundation board**: Catastrophic events (multi-region
    outage, TUF quorum loss, suspected coordinated attack).

PagerDuty schedules are in https://verum-lang.pagerduty.com/schedules.

## 7. Cross-reference

  - [`incident-runbook.md`](./incident-runbook.md) — incident triage
  - [`dr.md`](./dr.md) — disaster recovery
  - [`../security/tuf-root-ceremony.md`](../security/tuf-root-ceremony.md) — TUF rotation
  - [`../deployment/deployment-guide.md`](../deployment/deployment-guide.md) — first-time setup
