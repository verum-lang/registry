# TUF root key ceremony — verum-registry

This document specifies the procedure for creating, rotating, and
emergency-recovering the TUF root metadata that anchors the trust
chain for every published cog.

> The TUF root is the **single point of trust** for all signed
> cog distributions. Lose root quorum → lose every existing user's
> ability to verify cog integrity. Treat this document as
> safety-critical.

## 1. Trust model

  - **Root key set**: 7 keys, held by 7 distinct individuals
    (the *root key holders*). At least one holder per geographic
    region (Americas / EMEA / APAC) for resilience and time-zone
    coverage.
  - **Quorum**: 5 of 7 signatures required to produce a valid
    root.json. Tolerates loss of any 2 holders.
  - **Key material**: Yubikey 5C FIPS or AWS CloudHSM (per holder
    preference; both are acceptable). **Never** held in software-only
    form. **Never** uploaded to any registry account.
  - **Algorithm**: ed25519 (TUF-supported, fixed 32-byte signatures,
    no parameter ambiguity).
  - **Expiration policy**: root.json expires 12 months from issue.
    Rotation ceremony scheduled every 11 months (1-month buffer).

## 2. Roles and responsibilities

| Role | Count | Responsibility |
|---|---|---|
| Root key holder | 7 | Sign root.json with personal key during ceremonies |
| Ceremony master | 1 | Drive the ceremony agenda, collect signatures, publish |
| Witness | ≥2 | Independently verify each signature; sign attestation |
| Recorder | 1 | Capture transcript + screen-recording for audit log |

Roles must be filled by 4 distinct individuals minimum. Ceremony
master may also hold a root key.

## 3. Ceremony types

### 3.1 Scheduled rotation (every 11 months)
Routine. Triggers from `TUFRootExpiringSoon` warning at 30d-to-expiry.

### 3.2 Emergency rotation (compromised key suspected)
Same procedure as scheduled, but with reduced notice (any holder
suspecting compromise must declare; ceremony master convenes within
72 h). Declaration via PGP-signed mail to
`root-key-holders@verum-lang.org`.

### 3.3 Holder replacement
A holder steps down or loses key access. Treat as a special-case
rotation: new holder generates new key during ceremony; quorum signs
new root.json with the new public key replacing the old.

### 3.4 Catastrophic recovery (>2 holders lost)
Quorum impossible. Requires emergency bootstrap (§9). Out of normal
ceremony scope; documented separately because it has different trust
properties (community attestation rather than 5-of-7 quorum).

## 4. Pre-ceremony checklist (T-14 days)

  - [ ] Ceremony master sends T-14 invitation with calendar holds
        to all 7 holders (PGP-signed).
  - [ ] All holders confirm key-material accessibility (insert
        Yubikey, run `tuf-key health-check`, attach output).
  - [ ] Confirm Hashicorp Vault (or equivalent) sealed-state policy
        — at least 3 unseal-key holders available.
  - [ ] Reserve secured video bridge with E2E encryption (Signal
        bridge or Element room with `m.room.encryption` enabled).
  - [ ] Recorder confirms recording-software readiness; signed
        notice to all participants that the session will be recorded.
  - [ ] Witnesses receive draft `1.root.json` (or `N+1.root.json`)
        target for verification.

## 5. Ceremony procedure (live, ~2-3 h)

### 5.1 Roll call (10 min)
Ceremony master verifies attendance + identity (each holder reads
PGP fingerprint aloud + says current date in local timezone).

### 5.2 Threat declaration (5 min)
Each holder confirms "I have not been coerced. My key material is
under my sole control. I am acting on behalf of verum-lang.org root
trust." Witnesses note any hesitation in transcript.

### 5.3 Generate target metadata (15 min)

```bash
# Ceremony master prepares the unsigned root metadata
tuf-cli root init \
    --version "${PREVIOUS_VERSION+1}" \
    --expires "$(date -u -d '+1 year' +%Y-%m-%dT%H:%M:%SZ)" \
    --threshold 5 \
    --keys keys/holder-{1..7}.pub \
    --out unsigned-root.json

# Hash for verification
sha256sum unsigned-root.json | tee unsigned-root.sha256
```

The ceremony master broadcasts `unsigned-root.sha256` to the video
bridge chat. Every witness independently computes the hash and types
it into chat. They MUST match.

### 5.4 Collect signatures (60-90 min)
Ceremony master drives one-by-one:

```bash
# Holder N's turn
# 1. Holder downloads unsigned-root.json from ceremony S3 (read-only ACL)
aws s3 cp s3://verum-tuf-ceremony/unsigned-root.json .
sha256sum unsigned-root.json   # MUST match ceremony master's broadcast

# 2. Holder signs with their HSM
tuf-cli sign \
    --key-id ${HOLDER_KEY_ID} \
    --hsm yubikey-piv-slot-9c \
    --in  unsigned-root.json \
    --out signature-${HOLDER_NUM}.sig

# 3. Holder uploads signature
aws s3 cp signature-${HOLDER_NUM}.sig s3://verum-tuf-ceremony/

# 4. All witnesses verify
tuf-cli verify-signature \
    --root unsigned-root.json \
    --sig  signature-${HOLDER_NUM}.sig \
    --pub  keys/holder-${HOLDER_NUM}.pub
```

Repeat until ≥5 signatures collected. Stop at 5 unless rotation is
also replacing/adding a key (then collect from all 7 active holders).

### 5.5 Assemble final root.json (15 min)

```bash
# Ceremony master combines signatures
tuf-cli root assemble \
    --unsigned   unsigned-root.json \
    --signatures signature-{1,2,3,5,7}.sig \
    --out        signed-root.json

# Final hash for the public record
sha256sum signed-root.json | tee signed-root.sha256
```

Witnesses verify hash + content one final time.

### 5.6 Publish (15 min)

```bash
# 1. Push to TUF metadata bucket (versioned + immutable)
aws s3 cp signed-root.json \
    s3://verum-registry-tuf/${VERSION}.root.json \
    --acl public-read --content-type application/json

# 2. Update consistent-snapshot pointer
aws s3 cp signed-root.json \
    s3://verum-registry-tuf/root.json \
    --acl public-read --content-type application/json

# 3. Verify CloudFront/edge cache invalidation
aws cloudfront create-invalidation \
    --distribution-id ${TUF_CF_DIST} \
    --paths "/root.json" "/${VERSION}.root.json"

# 4. Sanity-check from a clean client
docker run --rm tufclient verify https://tuf.vcogs.io/root.json
```

### 5.7 Attestation (15 min)
Witnesses sign a transcript attesting the ceremony's integrity:

```yaml
ceremony:
  date: 2026-05-08T14:00:00Z
  type: scheduled-rotation
  version_from: 1
  version_to: 2
  expires: 2027-05-08T14:00:00Z
  participants:
    holders_present: [h1, h2, h3, h4, h5, h6, h7]   # listed by ID
    holders_signed:  [h1, h2, h3, h5, h7]
    ceremony_master: cm1
    witnesses:       [w1, w2, w3]
    recorder:        r1
  artifacts:
    unsigned_root_sha256: ${SHA1}
    signed_root_sha256:   ${SHA2}
  attestation:
    "I, <name>, witnessed this ceremony from beginning to end and
     attest that the procedure documented in tuf-root-ceremony.md §5
     was followed without deviation. Signed: <PGP signature>."
```

Stored in `s3://verum-registry-tuf/ceremonies/${DATE}/transcript.yaml`
+ public copy at https://verum-lang.org/transparency/tuf/.

## 6. Post-ceremony

  - [ ] Recorder uploads encrypted recording to long-term cold storage
        (10-year retention, restricted access).
  - [ ] Ceremony master updates the `verum_registry_tuf_root_expires_at`
        Prometheus metric (read from new `signed-root.json`).
  - [ ] All holders confirm new root.json is published + signature
        verifies on their independent client.
  - [ ] Public announcement on verum-lang.org/blog/ + RSS.
  - [ ] Schedule next ceremony in calendar (T-11 months from now).

## 7. Sealed-room hygiene

  - **Keys never leave HSM.** No exporting key material. No copying
    to filesystems. Holders MUST verify their HSM model matches the
    one registered with their public key.
  - **No unattended HSM.** Holders MUST keep Yubikey on their person
    for the entire ceremony; insert only at signing turn; remove
    immediately after.
  - **No screen-sharing of HSM PINs.** PIN entry happens off-camera
    if HSM uses a numeric pad; if PIN is host-typed, holder mutes
    keyboard audio + tilts screen away.
  - **Ceremony bridge access:** invite-only; pre-shared E2E room key.
    Drop participants who join late without out-of-band confirmation.

## 8. Failure modes during ceremony

| Failure | Response |
|---|---|
| Quorum-1 reached (4 sigs) — one holder unreachable | Reschedule next session within 14 days; this session was a dry run |
| Hash mismatch between ceremony master + witness | STOP. Investigate before any further signing. Likely indicates compromised state |
| Holder declares coercion / signs under duress (any signal) | STOP. Treat as catastrophic; convene emergency response |
| HSM rejects signing (broken hardware) | Treat as holder unreachable; reschedule. Holder replaces HSM offline |
| Network partition during signature collection | Pause; resume from last verified signature. No partial-sig publish |

## 9. Catastrophic recovery (>2 holders lost — quorum impossible)

This is the only path that does NOT use 5-of-7 quorum. It produces
a NEW root with a NEW key set, but at the cost of breaking trust
with every existing client (they must trust-on-first-use the new
root).

### 9.1 When to invoke
  - 3+ holders unrecoverably lost (death, key compromise, key
    destruction without backup).
  - Original root signing keys all believed compromised by an
    adversary.
  - Active state-actor coercion of multiple holders.

### 9.2 Procedure summary
1. Convene a community-attestation panel (verum-lang Foundation
   board + ≥3 independent technical reviewers).
2. Generate fresh 7-key set in a new ceremony following §5
   (substituting the panel attestation for previous-quorum
   continuity).
3. Publish new root with prominent versioning marker
   (`1000.root.json` to indicate discontinuity from prior chain).
4. Out-of-band distribution of root hash:
   - Cryptographic announcement on Foundation domain
     verum-lang.org over HTTPS+HSTS pinning.
   - Mirror on at least 3 community-operated Web pages.
   - Hash printed in a Foundation-issued newsletter (PGP-signed by
     ≥3 panel members).
5. CLI client update: bundle new root in the verum-cli release;
   include migration notes warning users of the discontinuity.
6. Postmortem published within 30 days, detailing the failure mode
   that caused quorum loss + remediations to prevent recurrence.

**Estimated time**: 4-8 weeks. This is explicitly NOT an emergency
hot-path; it is a governance event.

## 10. Cross-reference

  - [`incident-runbook.md`](../operations/incident-runbook.md) §3 —
    P0 TUF root expired
  - [`dr.md`](../operations/dr.md) §5 — TUF in DR posture
  - TUF spec: https://theupdateframework.io/specification/latest/
  - The Sigstore + TUF integration: https://docs.sigstore.dev/system_config/security_model
