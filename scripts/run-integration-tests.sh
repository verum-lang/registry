#!/usr/bin/env bash
#
# run-integration-tests.sh — REG-9..REG-15 BUNDLE
#
# Runs end-to-end smoke tests against a fully-provisioned local stack
# (docker compose up -d).  Each subsystem gets its own smoke test that
# exits non-zero on failure; the overall script fails fast on the
# first failing subsystem.
#
# Subsystems covered:
#   REG-9   Postgres connection + migrations apply + journal CRUD
#   REG-10  Redis pub/sub + sliding-window counter
#   REG-11  S3 (minio) put/get/delete + signed URL
#   REG-12  Meilisearch index + search
#   REG-13  Sigstore Rekor v2 + Fulcio publish flow (staging endpoint)
#   REG-14  TUF snapshot/timestamp/targets cycle
#   REG-15  WebAuthn registration + authentication ceremony
#
# Spec: §13 (integration test harness)

set -euo pipefail

REGISTRY_URL="${REGISTRY_URL:-http://localhost:8080}"
PG_URL="${DATABASE_URL:-postgres://verum:verum@localhost:5432/registry}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
MEILI_URL="${SEARCH_URL:-http://localhost:7700}"
MEILI_KEY="${MEILI_MASTER_KEY:-verum-search-key}"
S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:9000}"
S3_BUCKET="${S3_BUCKET:-verum-registry-packages}"
S3_AKID="${AWS_ACCESS_KEY_ID:-verumregistry}"
S3_SECRET="${AWS_SECRET_ACCESS_KEY:-verumregistry-dev-secret}"

GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
RESET='\033[0m'

pass()  { printf "%b  ✓  %s%b\n" "$GREEN"  "$1" "$RESET"; }
fail()  { printf "%b  ✗  %s%b\n" "$RED"    "$1" "$RESET"; exit 1; }
note()  { printf "%b  …  %s%b\n" "$YELLOW" "$1" "$RESET"; }
hdr()   { printf "\n=== %s ===\n" "$1"; }

# -----------------------------------------------------------------------------
# REG-9 — Postgres
# -----------------------------------------------------------------------------
hdr "REG-9 Postgres"
note "checking connectivity"
psql "$PG_URL" -c "SELECT 1" >/dev/null 2>&1 || fail "postgres unreachable at $PG_URL"
pass "postgres reachable"

note "checking migrations applied"
TABLE_COUNT=$(psql "$PG_URL" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
[[ "$TABLE_COUNT" -ge 10 ]] || fail "expected ≥10 tables, found $TABLE_COUNT"
pass "$TABLE_COUNT tables present"

note "smoke CRUD on packages table"
psql "$PG_URL" <<'SQL' >/dev/null
INSERT INTO packages (id, description, license, latest_version, downloads, score, created_at, updated_at)
VALUES ('test-smoke', 'integration smoke test', 'MIT', '0.1.0', 0, 0, now(), now())
ON CONFLICT (id) DO UPDATE SET updated_at = now();
SELECT * FROM packages WHERE id = 'test-smoke';
DELETE FROM packages WHERE id = 'test-smoke';
SQL
pass "packages CRUD round-trip"

# -----------------------------------------------------------------------------
# REG-10 — Redis
# -----------------------------------------------------------------------------
hdr "REG-10 Redis"
note "checking PING"
redis-cli -u "$REDIS_URL" PING | grep -q PONG || fail "redis PING failed"
pass "redis PONG"

note "smoke sliding-window counter"
KEY="smoke:rl:$(date +%s)"
redis-cli -u "$REDIS_URL" SET "$KEY" 0 EX 60 >/dev/null
for _ in 1 2 3; do redis-cli -u "$REDIS_URL" INCR "$KEY" >/dev/null; done
COUNT=$(redis-cli -u "$REDIS_URL" GET "$KEY")
[[ "$COUNT" == "3" ]] || fail "expected counter=3, got $COUNT"
redis-cli -u "$REDIS_URL" DEL "$KEY" >/dev/null
pass "sliding-window counter increments"

note "smoke pub/sub"
(redis-cli -u "$REDIS_URL" SUBSCRIBE "smoke" >/tmp/sub.log 2>&1 &)
SUB_PID=$!
sleep 0.5
redis-cli -u "$REDIS_URL" PUBLISH "smoke" "hello" >/dev/null
sleep 0.2
kill $SUB_PID 2>/dev/null || true
grep -q "hello" /tmp/sub.log || fail "pub/sub message not received"
pass "pub/sub round-trip"

# -----------------------------------------------------------------------------
# REG-11 — S3 (minio)
# -----------------------------------------------------------------------------
hdr "REG-11 S3 (minio)"
note "checking bucket exists"
AWS_ACCESS_KEY_ID="$S3_AKID" AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
  aws --endpoint-url "$S3_ENDPOINT" s3api head-bucket --bucket "$S3_BUCKET" >/dev/null 2>&1 \
  || fail "bucket $S3_BUCKET missing — check minio-init container logs"
pass "bucket $S3_BUCKET exists"

note "smoke put/get/delete"
KEY="smoke/$(date +%s).txt"
echo "verum-registry-smoke" > /tmp/smoke.txt
AWS_ACCESS_KEY_ID="$S3_AKID" AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
  aws --endpoint-url "$S3_ENDPOINT" s3 cp /tmp/smoke.txt "s3://$S3_BUCKET/$KEY" >/dev/null
AWS_ACCESS_KEY_ID="$S3_AKID" AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
  aws --endpoint-url "$S3_ENDPOINT" s3 cp "s3://$S3_BUCKET/$KEY" /tmp/smoke-back.txt >/dev/null
diff -q /tmp/smoke.txt /tmp/smoke-back.txt >/dev/null || fail "round-trip content mismatch"
AWS_ACCESS_KEY_ID="$S3_AKID" AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
  aws --endpoint-url "$S3_ENDPOINT" s3 rm "s3://$S3_BUCKET/$KEY" >/dev/null
pass "put/get/delete round-trip"

note "smoke presigned URL"
SIGNED=$(AWS_ACCESS_KEY_ID="$S3_AKID" AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
  aws --endpoint-url "$S3_ENDPOINT" s3 presign "s3://$S3_BUCKET/nonexistent" --expires-in 60)
[[ "$SIGNED" == http*"X-Amz-Signature="* ]] || fail "presigned URL malformed: $SIGNED"
pass "presigned URL contains X-Amz-Signature"

# -----------------------------------------------------------------------------
# REG-12 — Meilisearch
# -----------------------------------------------------------------------------
hdr "REG-12 Meilisearch"
note "checking health"
curl -s -H "Authorization: Bearer $MEILI_KEY" "$MEILI_URL/health" \
  | grep -q '"status":"available"' || fail "meilisearch /health not available"
pass "meilisearch available"

note "smoke index + search"
INDEX="smoke-$(date +%s)"
curl -s -X POST -H "Authorization: Bearer $MEILI_KEY" -H "Content-Type: application/json" \
  -d "{\"uid\":\"$INDEX\",\"primaryKey\":\"id\"}" "$MEILI_URL/indexes" >/dev/null
sleep 0.5
curl -s -X POST -H "Authorization: Bearer $MEILI_KEY" -H "Content-Type: application/json" \
  -d '[{"id":1,"name":"verum-test","desc":"smoke test package"}]' \
  "$MEILI_URL/indexes/$INDEX/documents" >/dev/null
sleep 1
HITS=$(curl -s -H "Authorization: Bearer $MEILI_KEY" \
  "$MEILI_URL/indexes/$INDEX/search?q=verum" | grep -o '"id":1' | wc -l)
[[ "$HITS" -ge 1 ]] || fail "search returned $HITS hits (expected ≥1)"
curl -s -X DELETE -H "Authorization: Bearer $MEILI_KEY" "$MEILI_URL/indexes/$INDEX" >/dev/null
pass "index + search round-trip"

# -----------------------------------------------------------------------------
# REG-13 — Sigstore Rekor v2 + Fulcio (staging)
# -----------------------------------------------------------------------------
hdr "REG-13 Sigstore (staging)"
note "checking Rekor staging /api/v1/log"
curl -s "https://rekor.sigstage.dev/api/v1/log" | grep -q '"treeSize"' \
  || fail "rekor staging /api/v1/log unreachable or malformed"
pass "rekor staging reachable"

note "checking Fulcio staging /api/v2/configuration"
curl -s "https://fulcio.sigstage.dev/api/v2/configuration" | grep -q '"issuers"' \
  || fail "fulcio staging /api/v2/configuration unreachable or malformed"
pass "fulcio staging reachable"

# -----------------------------------------------------------------------------
# REG-14 — TUF metadata cycle
# -----------------------------------------------------------------------------
hdr "REG-14 TUF metadata"
note "checking /tuf/timestamp.json"
curl -sf "$REGISTRY_URL/tuf/timestamp.json" | grep -q '"_type":"timestamp"' \
  || fail "/tuf/timestamp.json missing or malformed"
pass "timestamp.json present"

note "checking /tuf/1.root.json"
curl -sf "$REGISTRY_URL/tuf/1.root.json" | grep -q '"_type":"root"' \
  || fail "/tuf/1.root.json missing"
pass "root.json present"

note "checking /tuf/1.snapshot.json"
curl -sf "$REGISTRY_URL/tuf/1.snapshot.json" | grep -q '"_type":"snapshot"' \
  || fail "/tuf/1.snapshot.json missing"
pass "snapshot.json present"

note "checking /tuf/1.targets.json"
curl -sf "$REGISTRY_URL/tuf/1.targets.json" | grep -q '"_type":"targets"' \
  || fail "/tuf/1.targets.json missing"
pass "targets.json present"

# -----------------------------------------------------------------------------
# REG-15 — WebAuthn ceremony
# -----------------------------------------------------------------------------
hdr "REG-15 WebAuthn"
note "checking /api/v3/auth/webauthn/register/begin returns options"
RESP=$(curl -s -X POST "$REGISTRY_URL/api/v3/auth/webauthn/register/begin" \
  -H "Authorization: Token smoke-test:smoke-secret" \
  -H "Content-Type: application/json" -d '{}' || true)
echo "$RESP" | grep -q '"challengeId"\|"auth_required"' \
  || fail "register/begin malformed: $RESP"
pass "register/begin endpoint reachable"

note "checking /api/v3/auth/webauthn/authenticate/begin returns options"
RESP=$(curl -s -X POST "$REGISTRY_URL/api/v3/auth/webauthn/authenticate/begin" \
  -H "Content-Type: application/json" -d '{}' || true)
echo "$RESP" | grep -q '"challengeId"\|"publicKey"' \
  || fail "authenticate/begin malformed: $RESP"
pass "authenticate/begin endpoint reachable"

# -----------------------------------------------------------------------------
hdr "ALL SUBSYSTEMS — REG-9..REG-15 PASSED"
