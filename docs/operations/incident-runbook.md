# Incident runbook — verum-registry

This runbook covers detection, triage, mitigation, and postmortem
for incidents affecting the canonical registry. Every alert in
[`deploy/observability/prometheus/alerts.yaml`](../../deploy/observability/prometheus/alerts.yaml)
maps to a section here.

## 1. Severity ladder

| Severity | Definition | Response time | Page |
|---|---|---|---|
| **P0** | Registry unreachable / signed-cog integrity broken / TUF root expired | <5min ack | yes (PagerDuty) |
| **P1** | Single SLO breaching / supply-chain integrity degraded / publish flow broken for >10% requests | <30min ack | yes |
| **P2** | Latency degraded but within SLO / scheduled maintenance overrun | <2h ack | no |
| **P3** | Cosmetic issues / non-blocking warnings | next business day | no |

## 2. P0 — Registry unreachable

**Alert.** `RegistryDown` for 5m, or `AvailabilityFastBurn`
(burn rate 14× over both 1h+6h windows).

### 2.1 Detection
  - PagerDuty: alertmanager → on-call.
  - Manual: `curl -fsS https://vcogs.io/health/live` returns non-200.
  - User reports: `verum publish` fails with 503/timeout.

### 2.2 Triage (first 5 min)
```bash
# 1. Pod state
kubectl --namespace=verum-registry-prod get pods \
    -l app.kubernetes.io/name=verum-registry

# 2. Recent events
kubectl --namespace=verum-registry-prod get events \
    --sort-by='.lastTimestamp' | tail -50

# 3. Recent logs (last 200 lines, all replicas)
kubectl --namespace=verum-registry-prod logs \
    -l app.kubernetes.io/name=verum-registry --tail=200 \
    --max-log-requests=20 --prefix

# 4. Nginx ingress controller logs (if pods are healthy but unreachable)
kubectl --namespace=ingress-nginx logs \
    -l app.kubernetes.io/name=ingress-nginx --tail=200
```

### 2.3 Common causes + mitigation

| Cause | Symptom | Mitigation |
|---|---|---|
| OOMKilled (memory leak) | `Reason: OOMKilled` in pod state | Bump memory limit OR rollback to last-known-good image. `kubectl rollout undo deployment/verum-registry` |
| Postgres connection pool exhausted | DB pool >90% saturated for 5m+; `DBPoolExhausted` firing | Restart registry replicas (clears stuck connections); investigate slow queries via `pg_stat_activity` |
| Image-pull failure | `ErrImagePull` / `ImagePullBackOff` | Verify GHCR pull secret; rollback to last image with known-good digest |
| Bad config rolled out | Single canary breaking, others fine | Roll back ConfigMap: `kubectl rollout undo deployment/verum-registry --to-revision=<N>` |
| Ingress TLS cert expired | TLS handshake failures in ingress logs | `cert-manager` renewal stuck; force renewal: `kubectl --namespace cert-manager delete certificate vcogs-io-tls && wait` |

### 2.4 Communication template (P0)

```text
🚨 P0 INCIDENT — verum-registry unreachable

Status:        INVESTIGATING / IDENTIFIED / MITIGATING / RESOLVED
Detected:      <timestamp UTC>
Impact:        Publishing + cog resolution unavailable
                (read-only mirror at https://mirror.vcogs.io is operational)
Affected SLOs: Availability burn rate <N>×

Mitigation:    <one sentence>
ETA:           <minutes>
Updates:       every 15 min until resolved
```

Post in #incidents Slack + status page. Pin the message.

## 3. P0 — TUF root expired

**Alert.** `TUFRootExpired`.

### 3.1 Impact
**EVERY signed cog is now untrusted.** Clients refuse to install
new cogs. This is treated as P0 because it breaks the supply-chain
trust anchor.

### 3.2 Mitigation (the only path)
1. **Halt publishes** — apply `cveClosure.auditGate=halt` ConfigMap
   patch + rollout, OR scale registry to 0 (`kubectl scale --replicas=0`).
2. **Convene root-key ceremony** — see
   [tuf-root-ceremony.md](../security/tuf-root-ceremony.md).
   Requires 5-of-7 quorum holders to assemble. Out-of-band
   communication via PGP-signed mail to root-key-holders@verum-lang.org.
3. **Sign new root** — produce `1.root.json` (or next version) with
   the new expiration.
4. **Distribute** — push new root to TUF metadata bucket
   (`s3://verum-registry-tuf/<consistent-snapshot>/1.root.json`).
5. **Restore service** — scale registry back up, switch audit-gate
   back to `strict`.

**Avg recovery time:** 4-8h once quorum is assembled.
**Recovery time without quorum:** undefined — quorum is mandatory.

### 3.3 Prevention
The `TUFRootExpiringSoon` warning fires at <30 days. Schedule the
rotation ceremony in the 14-day window after that alert. The 30-day
buffer is deliberate — quorum members may be on vacation; emergency
gathering is the exception, not the rule.

## 4. P1 — Sigstore publish failure rate high

**Alert.** `SigstorePublishFailureRateHigh` (>5% for 10m).

### 4.1 Triage
```bash
# 1. Distinguish Rekor vs Fulcio failure
kubectl logs -l app.kubernetes.io/name=verum-registry \
    --tail=500 | grep -E "(rekor|fulcio).*error" | head -20

# 2. Check upstream health
curl -fsS https://rekor.sigstore.dev/api/v1/log
curl -fsS https://fulcio.sigstore.dev/api/v2/configuration
```

### 4.2 Common causes

| Symptom | Cause | Mitigation |
|---|---|---|
| `rekor: 5xx` errors | Rekor public-good outage (check sigstore.dev status) | Wait for upstream, OR temporarily switch to private Rekor instance via `SIGSTORE_REKOR_URL` env var |
| `fulcio: certificate signing failed` | Fulcio trust chain stale | Refresh TUF root + Fulcio chain; restart registry |
| `clock skew` errors | Pod clock drift >5 min | Restart kubelet on affected nodes; check NTP sync |
| `OIDC: token exchange failed` | OIDC issuer down (e.g. github.com auth) | Wait; users with cached tokens unaffected |

## 5. P1 — Database pool exhausted

**Alert.** `DBPoolExhausted` (>90% saturated for 5m).

### 5.1 Triage
```bash
# 1. Connection count from pg side
kubectl --namespace verum-registry-prod exec -it postgres-0 -- \
    psql -U verum -d registry \
    -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# 2. Long-running queries
kubectl --namespace verum-registry-prod exec -it postgres-0 -- \
    psql -U verum -d registry \
    -c "SELECT pid, now() - query_start AS duration, state, query
        FROM pg_stat_activity
        WHERE state != 'idle'
        ORDER BY duration DESC LIMIT 20;"
```

### 5.2 Mitigation

| Cause | Mitigation |
|---|---|
| Stuck transactions (long-running publishes) | `SELECT pg_terminate_backend(<pid>);` for the worst offenders |
| Pool size too small for traffic | Bump `DATABASE_MAX_POOL` env var; rollout |
| Cardinality explosion in a query | Identify via `pg_stat_statements`; deploy hotfix |
| Replica lag spike (read pool starves) | Check WAL replication; promote standby if necessary |

## 6. P1 — Self-audit failing

**Alert.** `AuditSelfFailing` (>30m of `verum audit --self` non-zero).

### 6.1 Impact
The registry's own ATS-V invariants are violated. Block release of
the next registry version until resolved. Existing deployments
unaffected (the failure is a build-time gate, not a runtime gate).

### 6.2 Triage
```bash
# Run self-audit + capture full bundle
curl -fsS https://vcogs.io/api/audit/self | jq . > self-audit.json

# Check which AP / corpus invariant is failing
jq '.bundle.l4_arch_shape' self-audit.json

# Compare against last-known-good
git log --oneline -20 main.vr src/audit/anti_patterns.vr
```

### 6.3 Mitigation
Either fix the violating cog OR explicitly @suppress the AP with
written rationale (must be reviewed by architecture-team CODEOWNER
before merge).

## 7. Postmortem template

Every P0/P1 incident gets a postmortem within 5 business days.

```markdown
# Postmortem — verum-registry incident YYYY-MM-DD

## Summary

  - **Detected**: <timestamp>
  - **Mitigated**: <timestamp>
  - **Resolved**: <timestamp>
  - **Impact**: <one paragraph quantifying the user impact>

## Timeline (UTC)

  - HH:MM — first detection signal
  - HH:MM — on-call paged
  - HH:MM — root cause hypothesis
  - HH:MM — mitigation applied
  - HH:MM — service restored
  - HH:MM — postmortem opened

## Root cause

<2-3 paragraphs identifying the specific code path, configuration,
or external dependency that caused the incident. Avoid blame; focus
on the system's vulnerability.>

## What went well

  - <bullet>
  - <bullet>

## What went poorly

  - <bullet>
  - <bullet>

## Action items

| # | Owner | Action | Due |
|---|---|---|---|
| 1 | @user | <concrete change> | YYYY-MM-DD |
| 2 | @user | <concrete change> | YYYY-MM-DD |

## Related runbook updates

  - <link to PR updating this runbook with new triage steps>
```

## 8. Useful URLs

  - Status page: https://status.vcogs.io
  - Grafana dashboard: https://grafana.internal/d/verum-registry-overview
  - Sigstore search: https://search.sigstore.dev/?logIndex=auto
  - PagerDuty rotation: https://verum-lang.pagerduty.com/schedules

## 9. Cross-reference

  - [`dr.md`](./dr.md) — disaster recovery / regional failover
  - [`operator-runbook.md`](./operator-runbook.md) — daily ops
  - [`tuf-root-ceremony.md`](../security/tuf-root-ceremony.md) — TUF rotation
  - [`alerts.yaml`](../../deploy/observability/prometheus/alerts.yaml) — alert defs
