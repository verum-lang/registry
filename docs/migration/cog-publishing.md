# Migration guide — cog publishing

This guide walks through migrating an existing cog from the v2
publishing flow (or a non-Verum source registry) onto the v3.0
verum-registry.

  - **From v2 → v3.0**: drop legacy provenance, add Sigstore bundle,
    add `@arch_module` annotation, switch to passkey auth.
  - **From npm/cargo/PyPI → v3.0**: full first-time onboarding.

For day-to-day publishing reference, use `verum publish --help` and
[`../api/openapi.yaml`](../api/openapi.yaml).

## 1. What changed v2 → v3.0

| Concern | v2 | v3.0 | Action |
|---|---|---|---|
| **Provenance** | in-toto SLSA v0.2 envelope | Sigstore Bundle v0.3 (cosign-verifiable) | Replace `provenance.json` upload with `bundle.json` |
| **Auth** | username/password OR PAT | OIDC + WebAuthn passkeys (PAT remains for CI) | Add passkey for interactive use |
| **Trust root** | Long-lived publisher PGP keys | TUF root + Sigstore Fulcio short-lived certs | No publisher key management |
| **Audit gate** | Optional | `auditGate.mode=strict` rejects ATS-V violations | Add `@arch_module` annotation |
| **Manifest** | `[provenance.signature]` field | Removed (replaced by Sigstore bundle attached separately) | Strip section from manifest |
| **Publishing endpoint** | `POST /api/v2/packages` | `POST /api/v3/packages` (multipart) | `verum publish` handles automatically |
| **Yank semantics** | Hard-delete from index | Advisory-only (source remains downloadable) | Update internal docs/runbooks |

v2 endpoints redirect 301 → v3 equivalents, so existing scripts that
hit URLs directly continue to work for read paths. Publishing must
move to v3.

## 2. Pre-migration checklist

  - [ ] `verum --version` ≥ 0.5.2 (v3 client support).
  - [ ] vcogs.io account exists; OIDC linked (GitHub / GitLab /
        Google).
  - [ ] At least one WebAuthn passkey registered:
        ```bash
        verum auth passkey register --label "yubikey-prod"
        ```
  - [ ] PAT created for CI publishing (separate from interactive
        passkey):
        ```bash
        verum auth tokens create --name "ci-publish" \
            --scopes publish,yank --expires "+90d"
        ```
        Save the printed token to your CI secret store. **It is shown
        once; cannot be recovered.**
  - [ ] Cog manifest v3-compliant (run `verum manifest validate`).

## 3. Migrating an existing cog (v2 → v3)

### 3.1 Update the manifest

Drop the legacy `[provenance.signature]` section if present:

```diff
  [package]
  scope       = "myorg"
  name        = "my-cog"
  version     = "1.2.3"
  description = "..."
  license     = "MIT"

- [provenance.signature]
- key_fingerprint = "ABCD1234..."
- algorithm       = "ed25519"
-
  [dependencies]
  ...
```

### 3.2 Add `@arch_module` annotation

The audit gate (when strict) requires every published cog to declare
its architectural intent. Add the annotation to your top-level
`src/main.vr` (binary) or `src/lib.vr` (library):

```verum
@arch_module(
    foundation: Foundation.ZfcTwoInacc,
    stratum:    MsfsStratum.LFnd,
    lifecycle:  Lifecycle.Stable("v1.2"),
    declarations: ShapeDeclarations {
        purpose: Some(Purpose {
            role:  "<one-sentence what this cog is for>",
            k_min: CveThresholdK.NamedCertification,
            v_min: CveThresholdV.NamedCertification,
            e_min: CveThresholdE.StructurallyReady,
        }),
        substrate: Some(CognitiveSubstrate.AnalyticDecompositional),
        anchoring: Some(FormalAnchoring.CurryHowardLawvere),
        e_sense:   Some(ExecutabilitySense.StructuralReadiness),
        self_reference: None,
    },
)
module myorg.my_cog;
```

If your cog uses corpus-level invariants (multi-cog architectural
contracts), also add `@arch_corpus(...)` — see
[`architecture-types/primitives/corpus`](https://verum-lang.org/docs/architecture-types/primitives/corpus)
for fields and examples.

### 3.3 Run the audit locally before publishing

```bash
verum audit --self
# Expected output:
#   ✓ ATS-V invariants pass (8/8 primitives)
#   ✓ AP catalog pass (40/40 anti-patterns)
#   ✓ Self-reference fixpoint analysis pass
#   ✓ Lifecycle / foundation alignment pass
```

If anything fails, fix before continuing — production registry's
`auditGate.mode=strict` will reject the publish otherwise.

### 3.4 Publish

```bash
# Interactive (passkey-protected):
verum publish

# CI (PAT-protected):
VERUM_TOKEN=$CI_VERUM_PUBLISH_TOKEN verum publish --non-interactive
```

The CLI will:
1. Build the cog.
2. Run `verum audit --self` (failing the publish on violation).
3. Compress source into zstd-tar.
4. Sign via Sigstore (Fulcio short-lived cert via the OIDC token,
   Rekor inclusion proof attached as bundle).
5. Upload (multipart: source + manifest + bundle) to
   `POST /api/v3/packages`.
6. Wait for server-side audit gate verdict.
7. On success, print the canonical version URL +
   `https://search.sigstore.dev/?logIndex=...` link for transparency.

### 3.5 Verify the published artifact

```bash
# From a clean cache, install + verify
verum cache clean myorg/my-cog
verum install myorg/my-cog@1.2.3
# Above command verifies:
#   - Sigstore bundle (cert chain → Fulcio root, Rekor inclusion)
#   - Source SHA-256 matches manifest
#   - Manifest version matches what was requested
```

### 3.6 Update CI

Replace v2 publish steps in your CI:

```diff
- - name: Publish v2
-   run: |
-     gpg --import $GPG_KEY
-     verum-v2 publish --signing-key $GPG_FINGERPRINT
+ - name: Publish v3
+   uses: verum-lang/publish-action@v1
+   with:
+     scope: myorg
+     # OIDC handled via GitHub Actions OIDC → Fulcio (no long-lived key)
+   env:
+     # Optional fallback PAT for non-OIDC environments
+     VERUM_TOKEN: ${{ secrets.VERUM_PUBLISH_PAT }}
```

GitHub Actions, GitLab CI, and CircleCI native OIDC issuers are
trusted by Sigstore Fulcio public-good — no long-lived signing key
needed. The `verum-lang/publish-action@v1` GHA wires the OIDC token
into Fulcio automatically.

## 4. First-time onboarding (npm/cargo/PyPI → v3)

### 4.1 Reserve a scope

Scope reservations are first-come / first-served per username.
Reserve via:

```bash
verum auth login                          # interactive OIDC
verum scope claim myorg                   # only succeeds if free
```

If `myorg` is already taken, choose a different scope (registry
governance rejects squatting reports for stale-but-claimed scopes
older than 18 months).

### 4.2 Initialise the cog

```bash
mkdir my-cog && cd my-cog
verum new --scope myorg --name my-cog --kind library

# Generated tree:
#   my-cog/
#     verum.toml          (manifest)
#     src/
#       lib.vr            (with @arch_module already declared)
#     tests/
#     README.md
```

### 4.3 Add code, tests, doc

```bash
verum check               # type-check
verum test                # run tests
verum audit --self        # ATS-V invariants
```

### 4.4 Publish (first version)

Same as §3.4 above. The first publish for a new cog reserves the
package name within the scope.

## 5. Post-migration: yank → advisory transition

In v2, yanking a version hard-deleted it from the index. In v3,
yanks are advisory-only — the source remains downloadable; only
the resolver flags new resolutions as ineligible. This means:

  - **Existing lockfiles** continue to install yanked versions
    (good for reproducibility).
  - **New resolutions** skip yanked versions and warn (good for
    avoiding bad deploys).
  - **CVE response**: still publish a `verum advisory` entry for
    real security issues; yank alone is not sufficient
    user-communication.

```bash
verum yank myorg/my-cog 1.2.3 --reason "broken on macOS arm64"

# For security issues, additionally:
verum advisory new \
    --affected myorg/my-cog \
    --versions ">=1.0,<1.2.4" \
    --patched 1.2.4 \
    --severity high \
    --cve CVE-2026-1234 \
    --description "..."
```

## 6. Rollback / unpublish

The registry **does not support unpublish** (publishes are immutable
by spec — necessary for reproducible builds + transparency log).
If you published broken code:
1. **yank** the broken version (advisory).
2. **publish a fixed patch** version immediately.
3. If sensitive data was leaked, file a `verum advisory` AND
   contact security@verum-lang.org for off-band guidance on
   mitigation (key rotation, secret rotation upstream).

For accidental scope/name claims, contact ops@verum-lang.org with
proof-of-claim and a transition plan.

## 7. Compatibility window

  - v2 read endpoints: redirect 301 to v3 indefinitely.
  - v2 publish endpoint (`POST /api/v2/packages`): **removed
    2026-09-01**. CI must move to v3 publish before that date.
  - v2 PGP signing keys: deprecated; new publishes MUST use
    Sigstore bundles. Existing v2-published versions remain
    downloadable + verifiable against the legacy provenance
    endpoint indefinitely.

## 8. Cross-reference

  - [`../api/openapi.yaml`](../api/openapi.yaml) — full v3 API
  - [`../operations/operator-runbook.md`](../operations/operator-runbook.md) — operator perspective
  - [`../security/tuf-root-ceremony.md`](../security/tuf-root-ceremony.md) — TUF trust root
  - Sigstore docs: https://docs.sigstore.dev
  - ATS-V primitives: https://verum-lang.org/docs/architecture-types/primitives/
