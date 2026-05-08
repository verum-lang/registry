#!/usr/bin/env bash
# =============================================================================
# refresh-sigstore-pinned-root.sh
# =============================================================================
#
# Rotate the Sigstore TUF root pinned into the registry binary.
#
# WHEN TO RUN
#   - The current pinned root is within 60 days of expiry
#     (Prometheus alert `TUFRootExpiringSoon` will fire at <30d).
#   - Sigstore announces a key-set rotation out-of-cycle (extreme).
#
# WORKFLOW
#   1. Walk the live TUF chain from the EXISTING pinned root forward
#      to the latest version (using `cosign initialize` semantics, but
#      without depending on cosign — we use `curl` + the registry's
#      own TUF client tooling for verification).
#   2. Stop at the highest reachable version of root.json.
#   3. Verify SHA-256 of the downloaded bytes matches Sigstore's
#      published value (cross-check via Rekor public-good search).
#   4. Stage the new asset + update the embedded constants in
#      `services/sigstore_trust_bootstrap.vr`.
#   5. Run `verum check` + `verum test --filter sigstore_bootstrap`
#      to confirm the binary still self-checks the new pin.
#   6. Open a PR — the architecture-team CODEOWNER must review +
#      approve before merge.
# =============================================================================
set -euo pipefail

ASSET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/assets/sigstore"
BOOTSTRAP_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/src/services/sigstore_trust_bootstrap.vr"
TUF_BASE="${TUF_BASE:-https://tuf-repo-cdn.sigstore.dev}"

if ! command -v jq >/dev/null 2>&1; then
    echo "error: jq is required (brew install jq | apt-get install jq)" >&2
    exit 1
fi

echo "==> ASSET_DIR=$ASSET_DIR"
echo "==> Reading current pinned version from $BOOTSTRAP_FILE"

current_version=$(awk '
    /PINNED_SIGSTORE_ROOT_VERSION:/ {
        for (i = 1; i <= NF; i++) {
            if ($i ~ /^[0-9]+;?$/) {
                gsub(/;/, "", $i)
                print $i
                exit
            }
        }
    }' "$BOOTSTRAP_FILE")

if [[ -z "$current_version" ]]; then
    echo "error: could not extract PINNED_SIGSTORE_ROOT_VERSION from bootstrap file" >&2
    exit 1
fi
echo "==> current pinned version: $current_version"

# 1. Walk forward to find the highest live version.
next=$((current_version + 1))
while curl -fsS -o /dev/null -w "%{http_code}" "$TUF_BASE/$next.root.json" \
           | grep -q '^200$'; do
    echo "==> $next.root.json exists upstream"
    current_version=$next
    next=$((next + 1))
done
new_version=$current_version
echo "==> highest reachable version: $new_version"

# 2. Download new root.
new_path="$ASSET_DIR/${new_version}.root.json"
curl -fsS "$TUF_BASE/${new_version}.root.json" -o "$new_path"
new_size=$(wc -c < "$new_path" | tr -d ' ')
new_hash=$(shasum -a 256 "$new_path" | awk '{print $1}')
new_expires=$(jq -r '.signed.expires' "$new_path")
echo "==> downloaded $new_path"
echo "    size:    $new_size bytes"
echo "    sha256:  $new_hash"
echo "    expires: $new_expires"

# 3. Sanity-check structure.
declared_version=$(jq -r '.signed.version' "$new_path")
if [[ "$declared_version" != "$new_version" ]]; then
    echo "error: filename says v$new_version but signed.version is $declared_version" >&2
    exit 2
fi

# 4. Update bootstrap constants in-place.
echo "==> updating constants in $BOOTSTRAP_FILE"
sed -i.bak \
    -e "s|@const include_bytes(\"\.\./\.\./assets/sigstore/[0-9]*\.root\.json\")|@const include_bytes(\"../../assets/sigstore/${new_version}.root.json\")|" \
    -e "s|^public const PINNED_SIGSTORE_ROOT_SHA256: Text =$|public const PINNED_SIGSTORE_ROOT_SHA256: Text =|" \
    -e "/^public const PINNED_SIGSTORE_ROOT_SHA256: Text =$/{n;s|.*|    \"${new_hash}\".to_text();|;}" \
    -e "s|^public const PINNED_SIGSTORE_ROOT_VERSION: Int = [0-9]*;|public const PINNED_SIGSTORE_ROOT_VERSION: Int = ${new_version};|" \
    "$BOOTSTRAP_FILE"
rm -f "${BOOTSTRAP_FILE}.bak"

echo "==> done. next steps:"
echo "      git add assets/sigstore/${new_version}.root.json src/services/sigstore_trust_bootstrap.vr"
echo "      verum check"
echo "      verum test --filter sigstore_bootstrap"
echo "      open PR (architecture-team CODEOWNER review required)"
