# Disaster recovery — verum-registry

This document covers backup procedures, recovery time/point
objectives, regional failover, and full DR rebuild procedures.
For incident-time triage, see [`incident-runbook.md`](./incident-runbook.md).

## 1. Recovery objectives

| Asset | RPO | RTO | Notes |
|---|---|---|---|
| **Postgres metadata** | 1 min | 30 min | WAL streaming + nightly base-backup |
| **S3 object store (cog tarballs)** | 0 (versioning) | 0 (multi-AZ) | Object versioning + cross-region replication |
| **Redis cache** | ∞ (cache only) | 0 (cold start OK) | No DR; rebuild on read |
| **MeiliSearch index** | ∞ (rebuild from PG) | 30 min | Reindex from postgres on restart |
| **TUF root metadata** | 0 (HSM-stored) | 4-8h (ceremony) | 5-of-7 quorum required |
| **Container images** | 0 (Sigstore-signed in GHCR) | 0 | Multi-arch + cosign sig |

## 2. Postgres — backup + PITR

### 2.1 Daily base backup
Cron-scheduled at 02:00 UTC via Kubernetes CronJob:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: registry-pg-backup }
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: pg-basebackup
              image: postgres:17-alpine
              command:
                - /bin/sh
                - -c
                - |
                  set -e
                  ts=$(date -u +%Y%m%dT%H%M%SZ)
                  pg_basebackup -h $PGHOST -U $PGUSER -D /tmp/$ts -F t -X stream -P -v
                  age -r $(cat /etc/age/recipient.txt) /tmp/$ts/base.tar.gz \
                    | aws s3 cp - "s3://${BACKUP_BUCKET}/postgres/base/${ts}.tar.gz.age"
                  rm -rf /tmp/$ts
              envFrom:
                - secretRef: { name: registry-backup-secrets }
              volumeMounts:
                - { name: age-key, mountPath: /etc/age, readOnly: true }
          restartPolicy: OnFailure
          volumes:
            - name: age-key
              secret: { secretName: registry-backup-age-recipient }
```

### 2.2 Continuous WAL streaming
Postgres archives WAL to S3 via `archive_command`:

```ini
# postgresql.conf (production)
wal_level                  = replica
archive_mode               = on
archive_command            = 'aws s3 cp %p s3://verum-registry-backup/postgres/wal/%f'
archive_timeout            = 60                   # force WAL switch every 60s
max_wal_senders            = 4
hot_standby                = on
```

This gives PITR with 1-minute granularity (RPO = `archive_timeout`).

### 2.3 PITR recovery procedure

```bash
# 1. Spin up an empty postgres instance with the same major version
# 2. Restore the most-recent base backup
ts=$(aws s3 ls s3://verum-registry-backup/postgres/base/ | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://verum-registry-backup/postgres/base/${ts}" /tmp/base.tar.gz.age
age -d -i /etc/age/identity.txt /tmp/base.tar.gz.age | tar -xzf - -C /var/lib/postgresql/data

# 3. Configure recovery (target_time = the moment to restore to)
cat > /var/lib/postgresql/data/recovery.signal <<'EOF'
EOF
cat >> /var/lib/postgresql/data/postgresql.conf <<'EOF'
restore_command = 'aws s3 cp s3://verum-registry-backup/postgres/wal/%f %p'
recovery_target_time = '2026-05-08 14:30:00 UTC'   # adjust to incident time
recovery_target_action = 'promote'
EOF

# 4. Start postgres — it will replay WAL until target_time, then promote
pg_ctl -D /var/lib/postgresql/data start

# 5. Verify
psql -c "SELECT pg_is_in_recovery();"   # → false after promotion
psql -c "SELECT max(version) FROM cog_versions;"
```

## 3. S3 object store — versioning + cross-region replication

### 3.1 Bucket configuration

```hcl
resource "aws_s3_bucket" "registry" {
  bucket = "verum-registry-prod"
}

resource "aws_s3_bucket_versioning" "registry" {
  bucket = aws_s3_bucket.registry.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_replication_configuration" "registry" {
  role   = aws_iam_role.replication.arn
  bucket = aws_s3_bucket.registry.id
  rule {
    id     = "to-eu-west"
    status = "Enabled"
    destination {
      bucket        = "arn:aws:s3:::verum-registry-prod-replica-eu-west-1"
      storage_class = "STANDARD"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "registry" {
  bucket = aws_s3_bucket.registry.id
  rule {
    id     = "noncurrent-90d"
    status = "Enabled"
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
}
```

Object versions are retained 90 days; cross-region replication is
async (typical lag <60s).

### 3.2 Cog-tarball recovery
```bash
# Recover a specific (overwritten or deleted) version
aws s3api list-object-versions \
    --bucket verum-registry-prod \
    --prefix "cogs/scope/cog-name/v1.2.3.tar.zst" \
    --query 'Versions[*].[VersionId,LastModified,IsLatest]' \
    --output table

aws s3api copy-object \
    --copy-source "verum-registry-prod/cogs/scope/cog-name/v1.2.3.tar.zst?versionId=<old-id>" \
    --bucket verum-registry-prod \
    --key "cogs/scope/cog-name/v1.2.3.tar.zst"
```

## 4. MeiliSearch — index rebuild

MeiliSearch index is **fully rebuildable from postgres**. No
backups; on cold start the registry's `search_service` runs:

```verum
async fn reindex_from_postgres() {
    let mut cursor = db.query("SELECT * FROM cog_versions ORDER BY id").stream();
    while let Some(row) = cursor.next().await {
        search_index.upsert(SearchDocument::from(row)).await;
    }
}
```

Triggered automatically when `meilisearch.health()` returns
`indexes_total=0`.

## 5. TUF root — quorum recovery

See [`tuf-root-ceremony.md`](../security/tuf-root-ceremony.md) for
the 5-of-7 quorum procedure. DR-relevant points:

  - **Trust anchor**: all 7 root keys live in offline HSMs, geographically
    distributed across 3 regions (US-east, EU-west, AP-south).
  - **Quorum**: 5 of 7 holders must produce signatures within the
    `signing_window` (canonical: 14 days from ceremony invocation).
  - **Loss of <=2 holders**: recoverable with quorum from remaining 5.
  - **Loss of >=3 holders**: catastrophic. Requires emergency
    bootstrap with new root key set + community-attested out-of-band
    distribution (see §7).

## 6. Regional failover

Active-passive setup: `us-east-1` (primary) + `eu-west-1` (standby).

### 6.1 Standby readiness
  - Postgres: streaming replica with `hot_standby=on`.
  - S3: cross-region replication (§3.1).
  - Helm release deployed in standby cluster, scaled to 0.
  - DNS: Route53 weighted policy (100/0 default).

### 6.2 Failover procedure (planned)
```bash
# 1. Drain primary writes
helm --namespace verum-registry-prod upgrade registry oci://... \
     --set replicaCount=0 --wait

# 2. Promote standby postgres
psql -h pg-standby.eu-west.internal -c "SELECT pg_promote(true, 60);"

# 3. Update standby config to point at promoted DB
helm --namespace verum-registry-eu upgrade registry oci://... \
     --set replicaCount=6 \
     --set externalSecretName=verum-registry-secrets-promoted \
     --wait

# 4. Switch DNS
aws route53 change-resource-record-sets \
    --hosted-zone-id Z123 \
    --change-batch file://failover-to-eu.json

# 5. Verify
curl -fsS https://vcogs.io/health/ready
verum audit --self < should-pass
```

**Avg planned-failover time:** 15 minutes.

### 6.3 Failover procedure (unplanned — primary unreachable)
Same as planned, but skip step 1 (primary already offline) and add:
```bash
# 0. Confirm primary genuinely down (not a network blip)
for h in lhr nrt iad sfo syd; do
  curl -fsS --resolve vcogs.io:443:$(dig +short us-east.vcogs.io @1.1.1.1) \
       https://vcogs.io/health/live -o /dev/null -w "%{http_code}\n" || echo "from $h: down"
done

# 6. After failover, postmortem MUST capture data loss bound
#    (= time between last replicated WAL and promotion)
```

**Avg unplanned-failover time:** 30-45 minutes (includes data-loss
quantification).

## 7. Catastrophic full rebuild (last-resort scenario)

If both regions are lost AND the TUF quorum is broken:

1. Bring up clean infrastructure in a third region.
2. Restore postgres from oldest viable nightly base + WAL chain.
3. Restore S3 bucket from cross-region replica + Glacier cold storage.
4. Generate new TUF root via emergency bootstrap procedure (community
   attestation; not the standard 5-of-7).
5. Publish announcement: every existing client must trust-on-first-use
   the new root.
6. Reindex MeiliSearch.
7. Resume publishes from `verum audit --self` clean state.

**Estimated full rebuild:** 24-48 hours assuming all backups intact.
This is explicitly NOT a routine procedure — requires VP+ approval
and community communication plan.

## 8. DR drills

  - **Quarterly**: planned failover to eu-west, 15-min window.
  - **Semi-annually**: PITR drill (restore postgres to a
    timestamp 3 days ago in a sandbox).
  - **Annually**: tabletop exercise for the catastrophic-rebuild
    scenario.

Drills are tracked in the operations team's project board with
runbook updates as deliverables.

## 9. Cross-reference

  - [`incident-runbook.md`](./incident-runbook.md) — incident-time triage
  - [`operator-runbook.md`](./operator-runbook.md) — daily ops
  - [`tuf-root-ceremony.md`](../security/tuf-root-ceremony.md) — TUF rotation
  - [Helm chart](../../deploy/helm/registry/) — deployment manifests
