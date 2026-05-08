# Sigstore TUF root pin — refresh procedure

The registry binary embeds a pinned copy of the upstream Sigstore
TUF root metadata as a content-addressed trust anchor. This
document covers WHEN, WHO, and HOW to rotate that pin.

## 1. Why content-pin a root at all

The TUF protocol assumes clients trust-on-first-use a root.json
out-of-band. For a registry that anchors a public software-supply
chain, that "out-of-band" hand-off must be reproducible from the
binary's own bytes — anyone auditing the registry image can
diff the embedded root against the upstream Sigstore CDN and
verify the SHA-256 matches what was committed.

The pin is **never** the only thing trusted: at startup the
registry walks the live Sigstore TUF chain forward from the
pinned root, validating every signature in every chain step.
The pin is the trust anchor; the chain walk is the trust transit.

## 2. Pin lifecycle

| Phase | Trigger | Action |
|---|---|---|
| Active | Default | Embedded root validates startup; chain walk advances to live tip |
| Approaching expiry | <60 days to expiry | Schedule rotation ceremony (next planned release) |
| Imminent expiry | <14 days to expiry, no rotation in flight | Page the architecture-team rotation lead |
| Out-of-cycle | Sigstore announces emergency rotation | Run rotation immediately |
| Expired | `signed.expires` < now() | Registry refuses to start; emergency rotation required |

Sigstore root expiry is currently 6-month rolling. Plan to refresh
every 4-5 months to maintain a healthy buffer.

## 3. Authority

  - **Trigger**: anyone (ops, security, architecture).
  - **Execute**: rotation lead from architecture-team (CODEOWNER for
    `src/services/sigstore_trust_bootstrap.vr`).
  - **Review**: a second architecture-team member + a security-team
    member.
  - **Merge**: only after both reviews approve.

## 4. Procedure

### 4.1 Prerequisites
  - Working copy of the registry repo on the rotation lead's machine.
  - `jq`, `curl`, `shasum` installed.
  - Network access to `https://tuf-repo-cdn.sigstore.dev`.
  - `verum` toolchain ≥ the version that ships in the next release.

### 4.2 Run the refresh script
```bash
cd registry
./scripts/refresh-sigstore-pinned-root.sh
```

The script:
1. Reads the currently-pinned version from
   `src/services/sigstore_trust_bootstrap.vr`.
2. Walks forward to find the highest reachable version on the
   Sigstore CDN.
3. Downloads the new root.json into `assets/sigstore/`.
4. Computes the SHA-256.
5. Verifies `signed.version` matches the filename.
6. Edits the constants in `sigstore_trust_bootstrap.vr` to reference
   the new file + new hash + new version.

### 4.3 Independent verification (REQUIRED)
The rotation lead MUST cross-check the downloaded bytes against at
least two independent sources before committing:

```bash
# Source 1: official Sigstore CDN (just downloaded)
shasum -a 256 assets/sigstore/<NEW>.root.json

# Source 2: GitHub mirror at sigstore/root-signing
curl -fsS "https://raw.githubusercontent.com/sigstore/root-signing/main/repository/repository/<NEW>.root.json" \
    | shasum -a 256

# Source 3: Sigstore Slack #releases announcement
#   (the new root version + hash is announced there at rotation time)
```

All three SHA-256 values must be identical. If any disagreement,
**STOP** and escalate to security-team — this could indicate
a key-server compromise.

### 4.4 Validate the new pin in the registry binary
```bash
# Compile-time embed must succeed (catches malformed JSON, wrong path)
verum check

# Runtime self-check must pass against new constants
verum test --filter sigstore_bootstrap

# Smoke: bootstrap end-to-end against the live CDN
VERUM_REGISTRY_CONFIG=tests/fixtures/registry-staging.toml \
    verum run --bin verum-registry --health-only
```

### 4.5 Open the PR
Branch naming convention: `chore/refresh-sigstore-pin-vN-to-vM`
where `N` is the previous version and `M` is the new one.

PR title: `chore(security): refresh Sigstore TUF pinned root vN → vM`

PR body must include:
  - Old version + hash + expiry.
  - New version + hash + expiry.
  - Confirmation of three-source cross-check (paste the three
    `shasum` outputs).
  - Confirmation of `verum check` + `verum test` passing.
  - Confirmation of staging-environment smoke test passing.

CODEOWNER routing (already in `.github/CODEOWNERS`):
  - `src/services/sigstore_trust_bootstrap.vr` →
    `@architecture-team @security-team`

### 4.6 Post-merge
  - Tag a security-relevant release: `vN.M.K-pinrot`.
  - Cosign-sign the release image (handled by the standard release
    workflow).
  - Production rollout follows the standard procedure (see
    [`../operations/operator-runbook.md`](../operations/operator-runbook.md)
    §3.1).
  - Update the Prometheus alert grace period if the new root expires
    sooner than usual.

## 5. Rollback plan

If the new pin fails validation in production (extremely rare —
validation runs in CI before merge):

```bash
# 1. Roll back the registry deployment
helm --namespace verum-registry-prod rollback registry --wait

# 2. Open an incident; treat as P1
#    See: docs/operations/incident-runbook.md

# 3. Re-run the refresh against the SAME upstream version that was
#    just rolled back. If it still fails, escalate to security-team
#    — likely an upstream issue or transient corruption.
```

Note: rolling back to a PIN with an expired root is **NOT** safe. If
the previous pin's `signed.expires` < now(), recovery requires
forward-rotation only.

## 6. Air-gapped enterprise deployments

Self-hosted enterprise registries running in air-gapped networks
override the in-binary pin via the optional config field:

```toml
[tuf]
sigstore_pinned_root_path = "/etc/verum-registry/sigstore-pinned-root.json"
```

The same SHA-256 self-check applies — the air-gap operator must
update both the file AND the SHA-256 constant in their custom build
when rotating. The procedure is otherwise identical.

## 7. Cross-reference

  - [`tuf-root-ceremony.md`](./tuf-root-ceremony.md) — registry's
    OWN TUF root ceremony (separate concern: the registry signs its
    own metadata; this doc is about the upstream Sigstore root).
  - [`../operations/incident-runbook.md`](../operations/incident-runbook.md)
    §3 — P0 TUF root expired procedures (covers both pins).
  - [`../../scripts/refresh-sigstore-pinned-root.sh`](../../scripts/refresh-sigstore-pinned-root.sh)
    — automation entry point.
  - Sigstore root signing repo: https://github.com/sigstore/root-signing
