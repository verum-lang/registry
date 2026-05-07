# Verum Registry Specification

## Architecture-Aligned Reference Implementation on the Verum stdlib

---

**Status**: Authoritative — single canonical specification.
**Authors**: Verum Language Team

---

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Design Principles](#2-design-principles)
3.  [Architectural Overview](#3-architectural-overview)
4.  [stdlib Foundation](#4-stdlib-foundation)
5.  [Architectural Discipline (ATS-V)](#5-architectural-discipline-ats-v)
6.  [Domain Model](#6-domain-model)
7.  [Storage Layer](#7-storage-layer)
8.  [Services](#8-services)
9.  [HTTP API](#9-http-api)
10. [Security Architecture](#10-security-architecture)
11. [Supply Chain Discipline](#11-supply-chain-discipline)
12. [Audit Protocol](#12-audit-protocol)
13. [Developer Experience](#13-developer-experience)
14. [Operational Excellence](#14-operational-excellence)
15. [CVE Self-Application](#15-cve-self-application)
16. [Implementation Map](#16-implementation-map)

---

## 1. Executive Summary

### 1.1 Vision

The Verum Registry (`vcogs.io`) is the **canonical package distribution
system** for the Verum language ecosystem. It serves four overlapping
purposes:

1. **Production infrastructure** — receiving, validating, storing, and
   serving Verum cogs.
2. **A public transparency log** — every release is anchored on Sigstore
   Rekor; publishers' identities are bound via Fulcio-issued ephemeral
   certs.
3. **A reference Verum application** demonstrating idiomatic use of the
   language: refinement types, affine resources, async/await,
   protocol-driven composition, the CVE architectural discipline.
4. **A canonical exemplar of the ATS-V architectural-type system** —
   the registry is itself a `Lifecycle.Theorem` cog that passes full
   `verum audit --bundle` validation, demonstrating every primitive
   (Foundation, Stratum, Tier, Capability, Lifecycle, Shape) in
   load-bearing position.

### 1.2 The four core verbs

| Verb        | Description                                                          |
|-------------|----------------------------------------------------------------------|
| **Publish** | Receive a cog archive + manifest + Sigstore Bundle; verify; persist; index. |
| **Resolve** | Given a dependency constraint, return the canonical version + URL.   |
| **Verify**  | Given a `(name, version)`, return Rekor entry + Sigstore Bundle + audit verdict. |
| **Search**  | Given a query, return ranked matching cogs with optional Lifecycle / CVE filters. |

### 1.3 Key differentiators

| Concern                       | Verum Registry                                                  | npm / PyPI / crates.io        |
|-------------------------------|-----------------------------------------------------------------|-------------------------------|
| **Source-based publishing**   | Publishes `.vr` source; validation runs the Verum compiler.    | Publishes pre-built artifacts.|
| **CVE Lifecycle**             | Every cog carries `[T]/[D]/[C]/[P]/[H]/[I]/[✗]` classification. | Code only.                    |
| **Anti-pattern catalog**      | 40 AP-001..AP-040 patterns checked on every publish.            | None.                         |
| **Keyless publishing**        | Sigstore Fulcio-issued ephemeral cert; OIDC-bound identity.     | API tokens (often leaked).    |
| **Transparency log**          | Sigstore Rekor + registry-side mirror.                          | Hash-list (npm) or none.      |
| **Trust-root distribution**   | TUF metadata served at `/tuf/...`; full §5 client compatible.   | Hard-coded TLS pin or none.   |
| **Passwordless login**        | WebAuthn passkeys.                                              | Password+OTP primary.         |
| **Provenance attestations**   | SLSA + in-toto via DSSE envelopes.                              | None or external.             |
| **Manifest as a typed cog**   | `core.cog.manifest::CogManifest` — refinement-validated.        | TOML/JSON without schema.     |
| **Audit Protocol**            | Dual-audience bundle (developer + auditor) per L0..L6 layer.    | None.                         |
| **Self-application**          | Registry serves cogs; registry IS a cog; registry's cog served by registry — Banach fixpoint witness. | None. |

### 1.4 What the registry is *not*

* **Not a build server.** Compilation runs server-side only for
  validation; the registry does not produce binaries for arbitrary
  targets.
* **Not a CDN.** Source archives are served via signed URLs to a
  downstream CDN tier.
* **Not a git host.** Repository-style features are out of scope.
* **Not a curator.** The registry hosts whatever validates; the
  canonical-corpus discipline is community / governance, not a hosting
  concern.
* **Not a Sigstore replacement.** It *consumes* Sigstore (as a client)
  and *mirrors* Rekor entries for offline verification; it is not
  itself a public CT log.

---

## 2. Design Principles

```
1. SEMANTIC HONESTY      — Every type describes meaning, not implementation.
2. SECURITY BY DEFAULT   — Verification, signing, and transparency are mandatory.
3. STDLIB COMPOSITION    — Every facility uses canonical stdlib; no duplication.
4. KEYLESS BY DEFAULT    — Sigstore is the primary publishing pathway; long-
                            lived API tokens are a fallback for offline CI only.
5. CVE-CLOSED            — Every artefact (including the registry itself) is
                            CVE-Lifecycle-classified.
6. AUDIT-PROTOCOL CLOSED — The registry's own audit bundle passes
                            `verum audit --bundle` at Theorem level.
7. SELF-APPLICATION      — The registry articulates and proves its own
                            architectural shape via SelfReferenceWitness.
8. CATEGORICAL STRUCTURE — Public surfaces form natural categories;
                            verification factors as a pullback.
```

### 2.1 The minimalism criterion

```
Is this feature:
  1. Essential for cog distribution? OR
  2. Essential for supply-chain integrity? OR
  3. Uniquely valuable for Verum's verification story? OR
  4. Already provided by Verum stdlib (then: USE IT)?

If NO to all four → DO NOT include.
```

### 2.2 The composition criterion

```
Is the facility duplicated or paralleled in Verum stdlib?

  YES → use the stdlib facility.
  NO  → propose a stdlib extension; discuss; if accepted, land in stdlib.
        If rejected (legitimately registry-specific), implement here.
```

### 2.3 The articulation criterion

```
Does the registry's own @arch_module declaration use this primitive?
  Foundation, Stratum, Tier, Capability, Lifecycle, ShapeDeclarations,
  SelfReferenceWitness, Purpose, CognitiveSubstrate, FormalAnchoring,
  ExecutabilitySense.

YES → the primitive is exercised at the load-bearing apex of the system.
NO  → either the primitive is irrelevant, OR the architecture is
      under-articulated. Audit which.
```

The registry is the canonical demonstrator: every ATS-V primitive
appears in its `@arch_module` or in the audit hooks it exposes about
registered cogs.

---

## 3. Architectural Overview

### 3.1 High-level architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         VERUM REGISTRY ARCHITECTURE                      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────┐         ┌────────────────────────────────────┐ │
│  │  Web frontend       │ ◄─────► │  HTTP API (core.net.weft)          │ │
│  │  (passkey login,    │         │  /api/...    /tuf/...    /audit/   │ │
│  │   package browser)  │         │  Routes / middleware / mTLS        │ │
│  └─────────────────────┘         │                                    │ │
│                                  │  ┌──────────────────────────────┐  │ │
│  ┌─────────────────────┐         │  │  Service layer               │  │ │
│  │  verum CLI          │ ◄─────► │  │  ─ PublishService            │  │ │
│  │  (verum add / pub.  │         │  │  ─ SearchService             │  │ │
│  │  / resolve / verify)│         │  │  ─ SumdbService              │  │ │
│  └─────────────────────┘         │  │  ─ AuthService               │  │ │
│                                  │  │  ─ SigstoreService           │  │ │
│  ┌─────────────────────┐         │  │  ─ TufService                │  │ │
│  │  CI runners (GH /   │ ◄─────► │  │  ─ WebAuthnService           │  │ │
│  │  GitLab / sigstore) │ OIDC    │  │  ─ ProvenanceService         │  │ │
│  └─────────────────────┘         │  │  ─ AuditService              │  │ │
│                                  │  └──────────────────────────────┘  │ │
│                                  │                                    │ │
│                                  │  ┌──────────────────────────────┐  │ │
│                                  │  │  Domain layer                │  │ │
│                                  │  │  ─ CogManifest               │  │ │
│                                  │  │  ─ Passkey / Sigstore /TUF   │  │ │
│                                  │  │  ─ CogAuditRecord            │  │ │
│                                  │  │  ─ Owner / User / Token      │  │ │
│                                  │  └──────────────────────────────┘  │ │
│                                  └────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                       Persistence layer                            │ │
│  │  PostgreSQL  S3-compat  Redis  Transparency-log (Merkle + Rekor)   │ │
│  │  + audit tables + passkeys + TUF metadata + Sigstore bundles       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 The publish request flow (Sigstore keyless pathway)

A CI runner authenticates to Sigstore Fulcio with its OIDC token,
receives an ephemeral X.509 cert, signs a DSSE envelope (containing a
SLSA Build L3 statement) with the cert's keypair, posts the entry to
Rekor, builds a Sigstore Bundle, and submits it to the registry.

The registry verifies the bundle end-to-end via
`core.security.sigstore.verify_bundle` — chain → Fulcio CA (loaded
via TUF) → integratedTime in cert validity → DSSE sig vs cert SPKI →
Rekor SET + RFC-6962 inclusion proof → envelope-hash-in-log → OIDC
identity matched against the package's
`[publish.trusted_publishers]` config. Success → publish proceeds;
the Sigstore Bundle is persisted, the source archive is stored in S3,
Postgres rows are inserted, the local sumdb is appended, the TUF
targets metadata is re-signed.

### 3.3 Component responsibility matrix

| Component         | Responsibility                                       | Stdlib used                                            |
|-------------------|------------------------------------------------------|--------------------------------------------------------|
| HTTP API          | Routing, body parsing, middleware                    | `core.net.weft`                                        |
| Auth service      | OIDC + WebAuthn + Sigstore Bundle + API tokens       | `core.security.{oidc, webauthn, sigstore, password_hash}` |
| Publish service   | Validate, store, index, sumdb-append, TUF-resign     | (orchestrates everything below)                        |
| Manifest parsing  | Parse + validate `verum.toml`                        | `core.configuration.toml`, `core.cog.manifest`         |
| Archive packaging | Pack/unpack source bundle                            | `core.archive.tar`, `core.compress.{gzip, zstd}`       |
| Compilation       | Validate the cog compiles                            | `verum_kernel`, `verum_compiler` (in-process)          |
| Anti-pattern check| Run 40-pattern catalog                               | `verum_kernel::arch_anti_pattern::check_all_anti_patterns` |
| Sigstore          | Bundle verification + persistence                    | `core.security.sigstore`                               |
| TUF               | Trust-root distribution + metadata signing           | `core.security.tuf`                                    |
| WebAuthn          | Passkey registration + authentication ceremonies     | `core.security.webauthn`                               |
| Transparency log  | Local sumdb mirror (Rekor entries + own STH)         | `core.security.transparency_log`                       |
| Provenance        | SLSA / in-toto attestation parsing                   | `core.security.provenance`                             |
| Audit             | L0..L6 audit-bundle generation per registered cog    | `verum_kernel::arch_audit`, `core.architecture.types`  |
| Storage           | Postgres for metadata, S3 for blobs                  | `core.database.postgres`, `core.storage.s3`            |
| Migrations        | Schema evolution                                     | `core.database.postgres.migrations`                    |
| Cache             | Redis for hot path + WebAuthn challenge store        | `core.cache.redis`                                     |
| Search            | Full-text + faceted (incl. Lifecycle / CVE facets)   | `core.search.meilisearch`                              |
| Resilience        | Per-IP rate limit, backpressure, circuit breakers    | `core.net.weft.{backpressure, listener}`               |

---

## 4. stdlib Foundation

The registry composes against the following stdlib subsystems. Every
subsystem is implemented and shipping; the registry is exercised
against the production tree.

### 4.1 Configuration

`core.configuration` — `ConfigValue` ADT hub + `ConfigFormat`
protocol + open registry; `toml.vr` adapter is used for `verum.toml`.

### 4.2 Cog tooling

`core.cog`:
* `manifest.vr` — typed `CogManifest` with refinement-validated fields.
* `sign.vr` — Ed25519 cog-signature envelope.
* `archive.vr` — `.vbca` archive reader (kernel-bridged).
* `resolve.vr` — pubgrub-style dependency resolver.

### 4.3 SemVer constraints

`core.base.semver_constraint` — Cargo+npm-flavoured constraint
parser/matcher.

### 4.4 Archive packaging

`core.archive` — `Archive` protocol + USTAR + PAX-extended adapter.
Composes with `core.compress.{gzip, zstd, brotli, lz4}`.

### 4.5 X.509

`core.security.x509` — full RFC 5280 implementation: DER parser, DFS
path building with AKI/SKI bond ranking, algorithm-precise §6.1 path
validation (state machine, policy tree, full name constraints
DN/DNS/IP/email/URI), OCSP / CRL clients, end-to-end verifier with
purpose-aware EKU enforcement and revocation policies. Used for
Fulcio-issued ephemeral cert validation.

### 4.6 OIDC

`core.security.oidc` — discovery, JWKS cache with TTL +
kid-miss-triggered refresh, RFC-8725 token validation.

### 4.7 SLSA / in-toto / DSSE

`core.security.provenance` — DSSE envelope + in-toto Statement +
SLSA Build L3 predicate + Sigstore Bundle wrapping.

### 4.8 TUF (The Update Framework)

`core.security.tuf` — full TUF spec implementation: types, JCS-
canonical signing, threshold signature verification, repository
abstraction (HTTP / Local), full §5 client workflow with rollback /
freeze / mix-and-match / fast-forward / endless-data detection.

### 4.9 Sigstore

`core.security.sigstore` — Rekor v2 client (submit + fetch + SET
verify + RFC-6962 inclusion proof), Fulcio v2 client (OIDC + CSR +
proof-of-possession + lifetime cap), end-to-end keyless verification.

### 4.10 WebAuthn / FIDO2

`core.security.webauthn` — full WebAuthn L3 server-side relying
party: types, COSE_Key codec, AuthData parser, attestation verifiers
(none / packed / fido-u2f / apple), registration ceremony,
authentication ceremony with signCount monotonicity (cloning
detection).

### 4.11 Transparency log

`core.security.transparency_log` — RFC 6962 + RFC 9162 Merkle log
with tile-addressed proofs, signed tree heads, consistency proofs.
Used for the registry's local sumdb mirror.

### 4.12 Database

`core.database.postgres` — `AsyncPgPool`, compile-time `sql#"..."`
meta-fn, affine `Transaction`, `core.database.postgres.migrations`
with `pg_advisory_lock`-serialised migration runner, LISTEN/NOTIFY.

### 4.13 HTTP server

`core.net.weft` — `WeftApp`, `Server<H>`, `Router` with
refined-typed path parameters, HTTP/2 with Rapid-Reset defence,
HTTP/3, TLS + SPIFFE + 0-RTT gating, `Json<T>` extractor with
five-gate typed deserialisation, WebSocket, backpressure, rate
limiting, metrics, timeouts.

### 4.14 Crypto primitives

`core.security` — Ed25519, ECDSA P-256/P-384/P-521, RSA PKCS#1 v1.5
+ PSS, AES-GCM, ChaCha20-Poly1305, SHA-256/384/512, BLAKE3, HKDF,
Argon2id.

### 4.15 Architecture types

`core.architecture.types` (cross-side-pinned with
`verum_kernel::arch::*`) — Foundation, Stratum, Tier,
ShapeDeclarations, Lifecycle, Capability, AntiPatternId,
SelfReferenceWitness, Purpose, CognitiveSubstrate, FormalAnchoring,
ExecutabilitySense. The registry's `@arch_module` declaration uses
every primitive.

### 4.16 Identifiers + text distance

`core.base.{ulid, uuid, snowflake, nanoid}`,
`core.base.string_distance` (Damerau–Levenshtein for typosquatting).

---

## 5. Architectural Discipline (ATS-V)

The registry is itself an ATS-V `Lifecycle.Theorem` cog. Section 15
documents the registry's own self-application; this section
catalogues what the registry **enforces about cogs it hosts**.

### 5.1 The seven-symbol Lifecycle

Every published cog declares one of:

| Glyph | Variant            | C   | V         | E   | Use                                   |
|-------|--------------------|-----|-----------|-----|---------------------------------------|
| `[T]` | `Theorem(version)` | ✓   | ✓         | ✓   | Full closure — proven + executable    |
| `[D]` | `Definition`       | ✓   | trivial   | ✓   | Boundary by fiat (types, constants)   |
| `[C]` | `Conditional`      | ✓   | conditional| ✓  | Proven under listed hypotheses        |
| `[P]` | `Postulate`        | ✓   | external  | ✓   | Accepted via external citation        |
| `[H]` | `Hypothesis`       | partial | absent | absent | Speculative — MUST carry `@plan(...)` (AP-034) |
| `[I]` | `Interpretation`   | absent | absent | absent | Descriptive only — strict mode rejects (AP-035) |
| `[✗]` | `Retracted`        | n/a | n/a       | n/a | Withdrawn — citing forbidden (AP-033) |

The registry enforces:
* AP-009 — high-rank cogs can only cite high-rank cogs (no
  `[T]` citing `[H]`, etc.).
* AP-034 — `[H]` cogs must carry `@plan` metadata.
* AP-035 — `[I]` cogs are rejected from `strict: true` corpora.
* AP-033 — citations to `[✗]` cogs are rejected at publish time.

### 5.2 The 40-pattern anti-pattern catalog

Every publish runs `verum_kernel::arch_anti_pattern::check_all_anti_patterns`
across the cog's source tree. The result is persisted in
`cog_audit_records` with a per-AP verdict. The catalog has four bands:

* **Classical / Composition** (AP-001..AP-010): CapabilityEscalation,
  CapabilityLeak, DependencyCycle, TierMixing, FoundationDrift,
  RegisterMixing, StratumAdmissibility, TxStraddling,
  LifecycleRegression, CveIncomplete.
* **Boundary / Ontology** (AP-011..AP-026): Capability flavours,
  boundary invariants, wire encoding, authentication, determinism,
  time-bound contracts, transitive lifecycle, declaration drift,
  foundation–content alignment.
* **Modal-Temporal** (AP-027..AP-032): TemporalInconsistency,
  CounterfactualBrittleness, MissedAdjoint,
  UniversalPropertyViolation, PhantomEvolution, YonedaInequivalent.
* **CVE Articulation Hygiene** (AP-033..AP-040): RetractedCitation,
  HypothesisWithoutPlan, InterpretationInMature, ObserverImpersonation,
  BoundlessAudit, ImplicitSubstrate, AnchoringOverextension,
  SelfReferenceWithoutOperator.

A `Severity.Error` finding aborts publish; `Warning` emits to
`cog_audit_records` and does not block.

### 5.3 ShapeDeclarations enforcement

Every published cog must declare `Purpose` (with K/V/E thresholds).
`Lifecycle.Theorem` cogs additionally must declare `CognitiveSubstrate`
(AP-038), `FormalAnchoring` for non-CHL foundations (AP-039), and a
`SelfReferenceWitness` if `composes_with` includes self (AP-040).

### 5.4 Foundation, Stratum, Tier coordinates

Every cog's `@arch_module` declares its `(Foundation, Stratum, Tier)`
coordinate. The registry indexes this triple and exposes it as a
search facet:

* `foundation`: ZfcTwoInacc | Hott | Cic | Cubical | Mltt | Eff
* `stratum`: LFnd | LCls | LClsTop | LAbs (LAbs requires
  `@admissibility_certificate` — AP-007 / AP-011)
* `at_tier`: Interp | Aot | Gpu | Check | MultiTier([...])

Cross-tier composition without bridge → AP-004 TierMixing →
publish blocked.

---

## 6. Domain Model

### 6.1 Domain entities

The registry's domain types are thin records over Verum's
refinement-typed primitives. Everything is `@derive(Serialize,
Deserialize, Eq, Clone)` for Postgres roundtrip + JSON wire.

#### 6.1.1 PackageScope

```verum
@derive(Serialize, Deserialize, Eq, Clone, Hash)
public type PackageScope is Text {
    where self.matches(r"^(@[a-z0-9][a-z0-9-]{0,63}/)?[a-z][a-z0-9_-]{0,63}$")
};
```

#### 6.1.2 PackageRecord

```verum
@derive(Serialize, Deserialize, Eq, Clone)
public type PackageRecord is {
    id: PackageScope,
    description: Text { len <= 500, !contains("\n") },
    homepage: Maybe<Url>,
    repository: Maybe<Url>,
    license: SpdxExpression,
    keywords: List<Keyword> { len <= 5 },
    latest_version: SemVer,
    downloads: Int { >= 0 },
    score: Int { >= 0, <= 100 },
    created_at: Rfc3339Time,
    updated_at: Rfc3339Time,
    owners: List<UserId> { len >= 1 },
};
```

#### 6.1.3 PackageVersion

```verum
@derive(Serialize, Deserialize, Eq, Clone)
public type PackageVersion is {
    package_id: PackageScope,
    version: SemVer,
    edition: Text,
    language_profile: LanguageProfile,
    dependencies: Map<Text, DependencySpec>,
    dev_dependencies: Map<Text, DependencySpec>,
    build_dependencies: Map<Text, DependencySpec>,
    features: Map<Text, List<Text>>,
    default_features: List<Text>,
    source_sha256: Hex64,
    /// ATS-V coordinates exposed by the cog's @arch_module.
    foundation: Foundation,
    stratum: MsfsStratum,
    at_tier: Tier,
    cve_lifecycle: Lifecycle,
    /// Hash of the canonicalised ShapeDeclarations record.
    shape_declarations_digest: Hex64,
    /// Highest verification level achieved.
    verification_level: VerificationLevel,
    published_at: Rfc3339Time,
    /// Discriminated union over four pathways.
    published_by: PublishIdentity,
    yanked: Bool,
    yank_reason: Maybe<Text>,
    /// FK to SigstoreBundleRecord (set iff PublishIdentity::Sigstore).
    bundle_id: Maybe<Ulid>,
};

@derive(Serialize, Deserialize, Eq, Clone, Debug)
public type PublishIdentity is
    | Sigstore { issuer: Text, subject: Text, log_index: Int, integrated_time: Rfc3339Time }
    | OidcDirect { issuer: Text, subject: Text }
    | ApiToken(UserId)
    | WebAuthn(UserId);
```

#### 6.1.4 Passkey

WebAuthn `VerifiedCredential` persisted with cloning-detection state
(see `core.security.webauthn`).

#### 6.1.5 SigstoreBundleRecord

Verified Sigstore Bundle indexed by version_id with envelope hash,
cert chain leaf hash, Rekor log_index, integrated_time, and OIDC
identity. Stored verbatim for client re-verification.

#### 6.1.6 TufRootSnapshot / TufSignedMetadata

Versioned TUF metadata for the registry's own
`/tuf/<role>.json` distribution.

#### 6.1.7 CogAuditRecord

```verum
@derive(Serialize, Deserialize, Eq, Clone)
public type CogAuditRecord is {
    /// FK to versions.id (one audit per version).
    version_id: Int,
    /// CVE-closure axis verdicts.
    constructive: AxisVerdict,
    verifiable:   AxisVerdict,
    executable:   AxisVerdict,
    /// Per-AP verdict for each AP-001..AP-040. Sparse: only
    /// entries that fired (Error or Warning) are stored.
    anti_pattern_findings: List<AntiPatternFinding>,
    /// Load-bearing verdict — pass iff every AP is Ok and every
    /// CVE axis is Closed.
    load_bearing: Bool,
    /// Per-layer verdicts L0..L6 (see audit-protocol.md).
    layer_l0: LayerVerdict,
    layer_l1: LayerVerdict,
    layer_l2: LayerVerdict,
    layer_l3: LayerVerdict,
    layer_l4: LayerVerdict,
    layer_l5: LayerVerdict,
    layer_l6: LayerVerdict,
    audited_at: Rfc3339Time,
};
```

### 6.2 Domain–stdlib mapping

Every domain type is a thin record over a stdlib type. The registry
domain layer **owns** none of these types' implementation; it only
**assembles** them into the domain shape.

---

## 7. Storage Layer

### 7.1 Postgres schema

The schema lives in `migrations/`. Migrations are authored as
`core.database.common.migrations.Migration` records and applied
through the Postgres `MigrationRunner` with `pg_advisory_lock(<key>)`
for concurrent-instance serialisation.

```sql
-- 0001_initial_schema.sql       — packages / versions / users / etc.
-- 0002_passkeys.sql              — WebAuthn passkey storage
-- 0003_tuf_metadata.sql          — TUF root_history + signed_metadata
-- 0004_sigstore_bundles.sql      — Sigstore Bundle storage
-- 0005_publish_identity.sql      — versions.published_by* + bundle_id
-- 0006_cog_audit.sql             — cog_audit_records + ATS-V coords
```

### 7.2 Object storage (S3)

```
packages/<scope>/<name>/<version>/source.tar.zst
packages/<scope>/<name>/<version>/sigstore-bundle.json
```

Both immutable.

### 7.3 Cache (Redis)

Hot-path cache for package/version metadata, sumdb (immutable),
Sigstore bundles (immutable), TUF metadata, WebAuthn ceremony
challenges (5min TTL), rate-limit counters, OIDC JWKS, audit
verdicts.

### 7.4 Search (MeiliSearch)

Indexed: `id`, `description` (full-text), `keywords` (faceted),
`latest_version`, `downloads`/`score` (sortable),
`cve_lifecycle`/`language_profile`/`verification_level`/`foundation`/`stratum`/`at_tier`
(faceted).

---

## 8. Services

The service layer is the **business-logic core**. Each service is a
Verum cog with declared `@arch_module(...)`; CVE ShapeDeclarations
are mandatory.

### 8.1 PublishService — eight-phase workflow

```verum
implement PublishService {
    public async fn publish(
        &self,
        identity: PublishIdentity,
        manifest_text: Text,
        source_archive: List<Byte>,
        bundle: Maybe<SigstoreBundle>,
    ) -> Result<PackageVersion, PublishError>
        using [Database, Storage, Cache, Search, Sumdb, Tuf, Audit, Logger, Metrics]
    {
        let manifest = self.phase1_parse_manifest(&manifest_text)?;
        if let Some(b) = &bundle {
            self.phase1b_verify_bundle(&identity, b, &manifest, &source_archive).await?;
        }
        self.phase2_check_ownership(&identity, &manifest.cog.name).await?;
        self.phase3_check_version_bump(&manifest).await?;
        self.phase4_security_analysis(&manifest, &source_archive).await?;
        let analyzed = self.phase5_analyze_archive(&manifest, &source_archive).await?;
        let audit_record = self.phase5b_arch_audit(&analyzed).await?;
        let artefacts = self.phase6_generate_artefacts(&manifest, &analyzed).await?;
        let version = self.phase7_persist(
            &identity, &manifest, &source_archive, &bundle, &artefacts, &audit_record,
        ).await?;
        self.phase8_post_publish(&version).await;
        Ok(version)
    }
}
```

* **Phase 1** — `core.cog.manifest.parse_text`.
* **Phase 1b** — Sigstore Bundle verification via
  `core.security.sigstore.verify_bundle`.
* **Phase 2** — identity-aware ownership check (Sigstore /
  OidcDirect / ApiToken / WebAuthn).
* **Phase 3** — SemVer monotonicity.
* **Phase 4** — typosquatting + malware analysis.
* **Phase 5** — zstd-decode + tar-unpack + compile-validate +
  shape-declaration extraction.
* **Phase 5b (NEW)** — full ATS-V audit:
  `verum_kernel::arch_anti_pattern::check_all_anti_patterns` +
  CVE-closure verdict + L0..L6 layer evaluation. Persisted as
  `CogAuditRecord`.
* **Phase 6** — sumdb leaf, cog signature, provenance attestation.
* **Phase 7** — transactional persist (Postgres + S3 + sumdb +
  TUF targets re-sign).
* **Phase 8** — async post-publish: search, webhooks, cache.

### 8.2 SigstoreService

Verifies + persists Sigstore Bundles; serves them at
`/api/packages/.../bundle`; supports server-side `verify` for
constrained clients. Trust root pinned from TUF metadata.

### 8.3 TufService

Serves the registry's own TUF metadata at `/tuf/...`. Quarterly
root rotation via `rotate_root`; hourly timestamp + daily
snapshot refresh via `run_refresh_loop`. Targets re-signed on
every publish.

### 8.4 WebAuthnService

Begin/finish registration + authentication ceremonies; passkey
management. Cloning detection via signCount monotonicity.

### 8.5 AuthService

Four authentication shapes: Sigstore Bundle (preferred for
publish), OIDC Bearer JWT (legacy CI), WebAuthn-issued session
(web UI), API token (offline CI fallback).

### 8.6 AuditService

Demonstrates Verum's audit-protocol per §12. Surfaces:
* `lifecycle_distribution` — % T/D/C/P/H/I across the corpus.
* `anti_pattern_roster` — per-cog AP-001..AP-040 verdicts.
* `cve_bundle` — dual-audience report (terse + JSON).
* `self_audit` — registry runs its own bundle audit.

### 8.7 SearchService, SumdbService, ProvenanceService

`SearchService` — full-text + faceted with new ATS-V coordinate
facets. `SumdbService` — local Merkle log mirror.
`ProvenanceService` — DSSE envelope parsing + persistence.

---

## 9. HTTP API

### 9.1 Routes

```
/api/
  packages/
    GET  /:scope/:name                        — package metadata
    GET  /:scope/:name/versions               — version list
    GET  /:scope/:name/:version               — version metadata + ATS-V coords
    GET  /:scope/:name/:version/source        — source archive (302 to S3)
    GET  /:scope/:name/:version/manifest      — verum.toml
    GET  /:scope/:name/:version/bundle        — Sigstore Bundle JSON
    GET  /:scope/:name/:version/provenance    — DSSE envelope (legacy)
    GET  /:scope/:name/:version/audit         — CogAuditRecord (full)
    POST /                                    — publish a new version

  packages/:scope/:name/:version/
    POST /yank
    POST /unyank

  packages/:scope/:name/owners/
    GET  /
    POST /
    DELETE /:user

  search                                      — GET ?q=...&lifecycle=T&tier=Aot
  resolve                                     — POST { dependencies }

  auth/
    POST /login
    POST /oidc/discover/:provider
    POST /tokens
    DELETE /tokens/:id

    webauthn/
      POST /register/begin
      POST /register/finish
      POST /authenticate/begin
      POST /authenticate/finish

    passkeys/
      GET  /
      DELETE /:passkey_id

  sigstore/
    POST /verify

  audit/
    GET /lifecycle                            — corpus-wide T/D/C/P/H/I distribution
    GET /anti-patterns                        — corpus-wide AP-roster summary
    GET /anti-patterns/:scope/:name/:version  — per-cog AP verdicts
    GET /cve-bundle/:scope/:name/:version     — dual-audience bundle
    GET /self                                 — registry's OWN audit bundle

  users/:username

/sumdb/                                       (local Verum sumdb)
  GET  /lookup/:scope/:name@:version
  GET  /latest
  GET  /tile/:level/:index

/tuf/                                         (registry's TUF root)
  GET  /:version.root.json
  GET  /timestamp.json
  GET  /:version.snapshot.json
  GET  /:version.targets.json

/health/
  GET  /live
  GET  /ready
  GET  /version

/metrics                                      — Prometheus (mTLS-restricted)
```

### 9.2 Wire formats

JSON for API responses; TOML for manifest body in publish; multipart
for publish; tar+zstd for source archives; Sigstore Bundle JSON;
TUF metadata as canonical JSON.

### 9.3 Rate limiting

Token-bucket per `(client-identity, endpoint-class)` via
`core.net.weft.backpressure.RateLimitLayer`.

| Endpoint class    | Anonymous   | Authenticated |
|-------------------|-------------|---------------|
| Read              | 60 / min    | 300 / min     |
| Search            | 30 / min    | 120 / min     |
| Publish           | n/a         | 30 / hour     |
| Sumdb             | 600 / min   | 600 / min     |
| TUF metadata      | 600 / min   | 600 / min     |
| Auth              | 10 / min    | 10 / min      |
| WebAuthn ceremony | 30 / hour   | 60 / hour     |
| Sigstore verify   | 60 / min    | 600 / min     |
| Audit             | 30 / min    | 300 / min     |

### 9.4 Server bootstrap

```verum
async fn main() -> Result<(), Box<dyn Error>> {
    let config   = Config.from_env()?;
    let db_pool  = postgres.async_pool.connect(&config.postgres).await?;
    let storage  = s3.connect(&config.s3).await?;
    let cache    = redis.connect(&config.redis).await?;
    let search   = meilisearch.connect(&config.meilisearch).await?;
    let oidc     = oidc_provider_registry_from_config(&config.oidc).await?;
    let tuf      = TufService.new(load_tuf_keys(&config)?, &db_pool).await?;
    let trust    = tuf.fetch_sigstore_trust_root(&config.tuf).await?;
    let sigstore = SigstoreService.new(trust);
    let webauthn = WebAuthnService.new(&config.webauthn);
    let audit    = AuditService.new();

    let services = ServiceRegistry {
        publish:    PublishService {},
        search:     SearchService {},
        sumdb:      SumdbService { log: load_sumdb_log(&db_pool).await? },
        auth:       AuthService { oidc_provider_registry: oidc },
        provenance: ProvenanceService {},
        sigstore, tuf: tuf.clone(), webauthn, audit,
    };

    spawn(tuf.run_refresh_loop());

    let app = make_router(services)
        .layer(MetricsLayer.new())
        .layer(RateLimitLayer.new(rate_limit_config(&config)))
        .layer(LoggingMiddleware.new())
        .layer(SpiffeAuthLayer.optional(spiffe_bundles_from_config(&config)?));

    Server.bind(&config.bind_address)?
        .with_router(app)
        .serve_tls(tls_config_from(&config)?)
        .await?;
    Ok(())
}
```

---

## 10. Security Architecture

### 10.1 Threat model

| Vector                              | Defence                                                        |
|-------------------------------------|----------------------------------------------------------------|
| Credential leak (API token)         | Argon2id storage; mandatory expiry; revocation                |
| Credential leak (publisher OIDC)    | Sigstore: cert is short-lived (≤ 10 min); never persisted      |
| Cog tampering (silent re-publish)   | Sigstore Rekor inclusion + envelope-hash binding              |
| Trust-root compromise               | TUF root rotation (quarterly, threshold-signed, offline keys) |
| Passkey theft (cloning)             | WebAuthn signCount monotonicity check                         |
| Account takeover                    | WebAuthn passkeys + Sigstore-bound publisher identities       |
| Typosquatting                       | Damerau–Levenshtein vs high-download names                    |
| Dependency confusion                | Scope-required for new namespace claim                        |
| Malicious code                      | Static-pattern scanner + manual-review queue                  |
| Architectural anti-pattern slip     | Phase-5b 40-pattern audit; Severity.Error blocks publish      |
| Denial-of-service                   | Per-IP rate limit; concurrency limit; backpressure            |
| Cryptographic break                 | Post-quantum migration via `core.security.pq`                 |
| Cert chain compromise               | RFC 5280 §6.1 + OCSP/CRL revocation via `x509.verifier`       |

### 10.2 Sigstore keyless publishing

Primary publishing pathway. The publisher's private key never
touches the registry; identity is bound by Fulcio cert SAN +
Rekor inclusion.

### 10.3 OIDC trusted publishing

Legacy pathway for environments without Sigstore. Validate against
issuer's JWKS via `core.security.oidc`.

```toml
[publish.trusted_publishers]
[[publish.trusted_publishers.github]]
repository  = "myorg/mycog"
workflow    = ".github/workflows/release.yml"
ref         = "refs/tags/v*"
environment = "production"
```

### 10.4 WebAuthn passwordless login

Primary login UX is passkey-based. Password+OTP fallback exists for
legacy users (deprecated; will be removed).

### 10.5 TUF-anchored trust distribution

Clients fetch the registry's `root.json` (anchored offline) and
walk the standard TUF flow to obtain the registry's Fulcio CA + Rekor
pubkey + per-cog target metadata. A fresh consumer needs only the
TUF root to bootstrap *all* trust.

### 10.6 Local sumdb

RFC 6962-shape Merkle log retained for offline consumers + non-
Sigstore deployments. Defence-in-depth against TUF compromise.

---

## 11. Supply Chain Discipline

### 11.1 Yank semantics

Yanked version: hidden from new resolutions; remains downloadable
for existing lock files. Owner-only; `yank_reason` required.

### 11.2 Security advisories

Immutable once published. Affected versions (`SemVerConstraint`),
fixed versions, severity (low / medium / high / critical), CVE IDs.

### 11.3 Lock file integrity

`verum.lock` includes:
* sumdb tree-head at resolution time.
* Sigstore Bundle digest for each cog.
* TUF snapshot version + digest at resolution time.

`verum install --frozen` walks the standard TUF client workflow,
verifies each cog's source SHA-256 against `targets.json`, runs
`core.security.sigstore.verify_bundle` for Sigstore-published cogs,
and verifies the local sumdb tree-head's consistency with the
current registry tree-head.

### 11.4 Provenance

When the publish was Sigstore-keyless, the SLSA Build L3 statement
is embedded in the bundle's DSSE envelope. When publisher uploaded
a DSSE envelope directly, the registry stores it verbatim.

---

## 12. Audit Protocol

The registry exposes a load-bearing **dual-audience** audit surface
per `architecture-types/audit-protocol.md` and `dual-audience.md`.

### 12.1 The two audiences

* **Developer view** — terse summary on the package page:
  ```
  @team/server@1.2.3
    Lifecycle:  [T] Theorem (v1.2)
    CVE:        ✓ Constructive ✓ Verifiable ✓ Executable
    AP roster:  40/40 ok
    Audit:      load-bearing ✓
  ```
* **Auditor view** — exhaustive JSON at
  `GET /api/audit/cve-bundle/:scope/:name/:version`:
  ```json
  {
    "schema_version": "1.0",
    "cog": "@team/server@1.2.3",
    "lifecycle": { "glyph": "T", "version": "1.2" },
    "shape_declarations": { ... full Shape ... },
    "cve_closure": { "C": "Closed", "V": "Closed", "E": "Closed" },
    "anti_patterns": [
      { "id": "AP-001", "name": "CapabilityEscalation", "verdict": "ok" },
      ...
      { "id": "AP-040", "name": "SelfReferenceWithoutOperator", "verdict": "ok" }
    ],
    "layers": {
      "L0": { "verdict": "pass" },
      "L1": { "verdict": "pass", "kernel_recheck": "ok" },
      "L2": { "verdict": "pass", "tactics": [...], "smt_certs": [...] },
      "L3": { "verdict": "pass", "meta_theory": "ZfcTwoInacc" },
      "L4": { "verdict": "pass", "load_bearing": true },
      "L5": { "verdict": "pass", "schema_version_pinned": true },
      "L6": { "verdict": "pass", "register_prohibition_violations": [] }
    },
    "load_bearing": true,
    "audited_at": "2026-05-08T10:00:00Z"
  }
  ```

Both views compute from the same compiled Shape; zero drift.

### 12.2 The seven layers

| Layer | Subject                          | Audit gate                                |
|-------|----------------------------------|-------------------------------------------|
| L0    | Object (code, value, statement)  | `verum check`, `verum verify`              |
| L1    | Proof term / SMT certificate     | `verum audit --kernel-recheck`             |
| L2    | Proof method (tactic / SMT / synth) | `verum audit --kernel-soundness`        |
| L3    | Meta-theory (ZFC, HoTT, CIC, …)  | `verum audit --reflection-tower`           |
| L4    | Architectural Shape              | `verum audit --arch-discharges`            |
| L5    | Audit-report communication       | bundle JSON validator                      |
| L6    | CVE applied to itself            | `verum audit --bundle` + register-prohibition |

`verum audit --bundle` reports `verdict: load-bearing` when L0..L6
all pass.

### 12.3 Corpus-wide observatories

* `GET /api/audit/lifecycle` — distribution + AP-009 violations
  across the whole corpus.
* `GET /api/audit/anti-patterns` — per-AP error/warning counts.

These power the "ecosystem health" dashboard and the registry's
quarterly transparency report.

### 12.4 Self-audit

`GET /api/audit/self` returns the registry's OWN audit bundle —
the registry runs its own publish-pipeline anti-pattern check on
its own source. This is the operational form of the
self-application discipline (§15).

---

## 13. Developer Experience

### 13.1 Publish UX (Sigstore pathway)

```bash
$ verum publish
  manifest        verum.toml ✓
  source archive  built (12.4 MiB → 2.1 MiB after zstd)
  ─ Sigstore keyless flow
  oidc token      requested from CI (audience=sigstore) ✓
  fulcio          POST /api/v2/signingCert ✓
  signing         DSSE envelope (Ed25519) ✓
  rekor           POST /api/v2/log/entries ✓ (log_index=12345678)
  bundle          built (canonical sigstore bundle.json)
  uploading       https://vcogs.io/api/publish ████ 100%
  validation      compile ✓ · 40/40 anti-patterns ✓ · CVE-closure ✓
                  bundle verified end-to-end ✓
                  audit-bundle: load-bearing ✓
  ─ published    @team/server@1.2.3 ✓
                  bundle: vcogs.io/api/.../bundle
                  rekor:  rekor.sigstore.dev/.../log_index=12345678
                  audit:  vcogs.io/api/audit/cve-bundle/team/server/1.2.3
```

### 13.2 Resolve UX

```bash
$ verum add http-client
  searching       1 candidate (@verum-stdlib/http-client)
  selecting       1.5.2  (latest stable matching ^1.0)
  ─ TUF metadata
  root            v=8 ✓     snapshot v=247 ✓   targets v=12348 ✓
  fetching        https://.../1.5.2/source ✓
  verifying       sha256 ✓ · sumdb proof ✓ · bundle ✓ · rekor proof ✓
                  identity: github.com/verum-lang/http-client@refs/tags/v1.5.2
  audit           [T] Theorem · 40/40 ok · load-bearing ✓
  unpacking       ./.verum/cache/@verum-stdlib/http-client/1.5.2/
  lock            verum.lock updated
  ─ added        @verum-stdlib/http-client = "^1.5"
```

### 13.3 Login UX (WebAuthn)

```
[ Verum Registry — Sign in ]

  Username: alice
  ▷ Sign in with passkey
  ▷ Sign in with OIDC provider
    Sign in with password (deprecated)

  → "Use Touch ID to sign in to vcogs.io?"  [Use Touch ID]

  ✓ Signed in as alice. (Passkey: Yubikey 5 — work)
```

### 13.4 Audit UX

```bash
$ verum audit @team/server@1.2.3
  fetching        vcogs.io/api/audit/cve-bundle/team/server/1.2.3 ✓
  ─ summary
  Lifecycle       [T] Theorem (v1.2)
  Foundation      ZfcTwoInacc
  Stratum         LCls
  Tier            Aot
  CVE             ✓ ✓ ✓
  AP roster       40/40 ok
  Verdict         load-bearing ✓
```

### 13.5 Quality scoring

| Component             | Max | Sources                                                      |
|-----------------------|-----|--------------------------------------------------------------|
| Documentation         | 20  | README (5), module docs (10), all-symbol docs (5)            |
| Testing               | 20  | tests present (10), coverage > 50% (5), > 80% (5)            |
| Verification          | 25  | `[D]` (5), `[C]` (10), `[T]` (15), no unsafe (5)             |
| Architectural hygiene | 15  | 0 AP errors (10), 0 AP warnings (5)                          |
| Code quality          | 10  | no warnings (5), `verum fmt` clean (5)                       |
| Maintenance           | 10  | recent updates ≤ 6 mo (5), responsive issue tracker (5)      |

Recomputed every publish + every 7 days.

---

## 14. Operational Excellence

### 14.1 Deployment topology

* API tier: 4 instances, 2–4 vCPU / 4–8 GiB. Stateless.
* Postgres: 1 primary + 2 replicas. 8–16 vCPU / 32–64 GiB.
* Redis: 3-node cluster.
* MeiliSearch: 2 instances.
* S3: managed.
* CDN: in front of source-archive URLs.
* TUF offline-key signing infrastructure: HSM or air-gapped.

### 14.2 SLOs

| Metric                            | Target         |
|-----------------------------------|----------------|
| API latency (p50)                 | < 50 ms        |
| API latency (p95)                 | < 200 ms       |
| API latency (p99)                 | < 500 ms       |
| Publish E2E (Sigstore)            | < 45 s         |
| Publish E2E (OIDC legacy)         | < 30 s         |
| Search (p95)                      | < 50 ms        |
| Source-archive CDN-hit            | < 100 ms       |
| TUF metadata fetch (p95)          | < 50 ms        |
| WebAuthn ceremony (p95)           | < 200 ms       |
| Sigstore bundle verify (p95)      | < 500 ms       |
| Audit bundle fetch (p95)          | < 100 ms       |
| Uptime                            | 99.9%          |

### 14.3 Observability

OTLP via `core.tracing` + `core.metrics`. Standard panels: request
rate / latency / error rate, publish-pipeline phases, security
counters, DB pool stats, sumdb append rate, cache hit ratio, score
histogram, Sigstore verify success/failure ratio, WebAuthn
register/authenticate counts + clone-detection rejections, TUF
role-fetch counts, anti-pattern observatory.

### 14.4 Incident severity

| Level | Response | Examples                                      |
|-------|----------|-----------------------------------------------|
| P1    | 15 min   | API offline; data corruption; security breach |
| P2    | 1 hour   | Publish failures > 10%; sumdb inconsistency   |
| P3    | 4 hours  | Elevated error rates; component degradation  |
| P4    | 24 hours | Minor bugs; documentation; non-critical       |

### 14.5 Backup and DR

* Postgres: hourly logical + 6-hourly base + WAL. RPO 5 min, RTO 30 min.
* S3: versioning + cross-region replication. RPO 0, RTO 5 min.
* Sumdb: append-only and signed; restorable from any consistent backup.
* TUF state: every `tuf_root_history` row is journalled +
  cryptographically signed; full history reconstructible.
* Sigstore bundles: immutable + dual-stored.

---

## 15. CVE Self-Application

The registry itself is a `Lifecycle.Theorem` cog subject to CVE
classification. Section 12's audit hooks surface the registry's
own bundle at `GET /api/audit/self`.

### 15.1 The registry's @arch_module

```verum
@arch_module(
    foundation:    Foundation.ZfcTwoInacc,
    stratum:       MsfsStratum.LCls,
    at_tier:       Tier.MultiTier([Tier.Aot, Tier.Check]),
    lifecycle:     Lifecycle.Theorem("canonical"),
    exposes: [
        Capability.Network(NetProtocol.Http2, NetDirection.Inbound),
        Capability.Network(NetProtocol.Http,  NetDirection.Outbound),
        Capability.Read(ResourceTag.Filesystem),
        Capability.Write(ResourceTag.Filesystem),
        Capability.Persist(PersistenceMedium.Postgres),
        Capability.Persist(PersistenceMedium.S3),
        Capability.Persist(PersistenceMedium.Ledger),
        Capability.Spawn(TaskLifetime.Bounded),
        Capability.TimeBound(Duration.from_hours(1)),
    ],
    requires:      [],
    composes_with: [
        "core.architecture.types",
        "core.architecture.anti_patterns",
        "core.architecture.lifecycle",
        "core.cog.manifest",
        "core.security.sigstore",
        "core.security.tuf",
        "core.security.webauthn",
        "core.security.x509",
        "core.security.oidc",
        "core.security.provenance",
        "core.security.transparency_log",
        "core.database.postgres",
        "core.net.weft",
    ],
    strict:        true,
    declarations: ShapeDeclarations {
        purpose: Some(Purpose {
            role: "canonical Verum cog registry — exposes seven-symbol Lifecycle + 40-AP catalog + audit-protocol + Sigstore + TUF + WebAuthn",
            k_min: CveThresholdK.FullWitness,
            v_min: CveThresholdV.NamedCertification,
            e_min: CveThresholdE.StructurallyReady,
        }),
        substrate:      Some(CognitiveSubstrate.AnalyticDecompositional),
        anchoring:      Some(FormalAnchoring.CurryHowardLawvere),
        e_sense:        Some(ExecutabilitySense.StructuralReadiness),
        self_reference: Some(SelfReferenceWitness {
            operator:    "verum_registry.services.publish_service.publish_with_sigstore",
            fixed_point: "verum-registry@<current-version>",
            fixpoint_class: fixpoint_class_banach(),
        }),
    },
)
module verum_registry.main;
```

Every primitive is exercised:
* **Foundation** + **Stratum** + **Tier** declared.
* Nine `Capability` variants in `exposes`.
* 13 `composes_with` entries (every load-bearing stdlib subsystem).
* Full `ShapeDeclarations` including non-trivial `SelfReferenceWitness`.

### 15.2 Self-reference semantics

The registry serves cogs; the registry is itself a cog; the
registry's cog is served by the registry. The `SelfReferenceWitness`
articulates this as a Banach contracting fixed point: each
self-publish iteration narrows admissible registry-cog versions to
those passing the publish pipeline.

The registry's own publishes go through the **Sigstore keyless
pathway**: the project's CI authenticates to Fulcio with its OIDC
token, signs the registry's source archive, posts to Rekor, and
POSTs to a *different* Verum registry instance (staging) which
verifies the bundle exactly as any other consumer would.
Production then promotes from staging. Every released registry
version is itself end-to-end Sigstore-verified.

### 15.3 Audit dogfood

```bash
$ curl https://vcogs.io/api/audit/self | jq '.layers'
{
  "L0": { "verdict": "pass" },
  "L1": { "verdict": "pass", "kernel_recheck": "ok" },
  "L2": { "verdict": "pass", "tactics": [...], "smt_certs": [...] },
  "L3": { "verdict": "pass", "meta_theory": "ZfcTwoInacc" },
  "L4": { "verdict": "pass", "load_bearing": true },
  "L5": { "verdict": "pass", "schema_version_pinned": true },
  "L6": { "verdict": "pass", "register_prohibition_violations": [] }
}
```

A failing self-audit blocks release of the next registry version.

---

## 16. Implementation Map

### 16.1 Source layout

```
registry/
├── verum.toml                          — manifest (registry-as-cog)
├── docs/
│   └── spec.md                         — this document
├── migrations/
│   ├── 0001_initial_schema.sql
│   ├── 0002_passkeys.sql
│   ├── 0003_tuf_metadata.sql
│   ├── 0004_sigstore_bundles.sql
│   ├── 0005_publish_identity.sql
│   └── 0006_cog_audit.sql
├── src/
│   ├── main.vr                         — entry + service registry
│   ├── config.vr                       — load via core.configuration
│   │
│   ├── domain/                         — domain entities (§6)
│   │   ├── mod.vr
│   │   ├── package.vr
│   │   ├── version.vr                  — PublishIdentity + ATS-V coords
│   │   ├── user.vr
│   │   ├── owner.vr
│   │   ├── sumdb.vr
│   │   ├── advisory.vr
│   │   ├── passkey.vr
│   │   ├── tuf_state.vr
│   │   ├── sigstore_bundle.vr
│   │   ├── cog_audit_record.vr
│   │   └── errors.vr
│   │
│   ├── persistence/                    — storage layer (§7)
│   │   ├── mod.vr
│   │   ├── package_repository.vr
│   │   ├── version_repository.vr
│   │   ├── user_repository.vr
│   │   ├── token_repository.vr
│   │   ├── owner_repository.vr
│   │   ├── sumdb_repository.vr
│   │   ├── advisory_repository.vr
│   │   ├── passkey_repository.vr
│   │   ├── tuf_metadata_repository.vr
│   │   ├── sigstore_bundle_repository.vr
│   │   ├── cog_audit_repository.vr
│   │   └── object_store.vr
│   │
│   ├── services/                       — business logic (§8)
│   │   ├── mod.vr
│   │   ├── publish_service.vr
│   │   ├── search_service.vr
│   │   ├── sumdb_service.vr
│   │   ├── auth_service.vr
│   │   ├── provenance_service.vr
│   │   ├── sigstore_service.vr
│   │   ├── tuf_service.vr
│   │   ├── webauthn_service.vr
│   │   └── audit_service.vr
│   │
│   ├── audit/                          — load-bearing audit (§12)
│   │   ├── mod.vr
│   │   ├── lifecycle.vr                — corpus distribution
│   │   ├── anti_patterns.vr            — 40-AP enumeration
│   │   ├── cve_bundle.vr               — dual-audience report
│   │   └── self_reference.vr           — registry's own audit
│   │
│   ├── http/                           — HTTP layer (§9)
│   │   ├── mod.vr
│   │   ├── router.vr
│   │   ├── middleware.vr
│   │   ├── handlers/
│   │   │   ├── packages.vr
│   │   │   ├── publish.vr
│   │   │   ├── search.vr
│   │   │   ├── sumdb.vr
│   │   │   ├── auth.vr
│   │   │   ├── owners.vr
│   │   │   ├── advisories.vr
│   │   │   ├── health.vr
│   │   │   ├── webauthn.vr
│   │   │   ├── tuf.vr
│   │   │   ├── sigstore.vr
│   │   │   └── audit.vr
│   │   └── error_response.vr
│   │
│   └── observability/
│       ├── mod.vr
│       ├── metrics.vr
│       └── tracing.vr
│
└── tests/
    └── ...
```

---

## Appendix A — Configuration

```toml
[bind]
address = "0.0.0.0:8443"
tls_cert = "/etc/verum-registry/tls.crt"
tls_key  = "/etc/verum-registry/tls.key"

[postgres]
url = "postgres://registry:secret@localhost:5432/registry"
min_connections = 5
max_connections = 50

[s3]
endpoint = "https://s3.us-west-2.amazonaws.com"
region   = "us-west-2"
bucket   = "verum-registry-prod"

[redis]
url = "redis://localhost:6379/0"

[meilisearch]
url     = "https://search.internal:7700"
api_key = "..."

[sumdb]
signing_key = "/etc/verum-registry/sumdb-ed25519.seed"

[tuf]
root_offline_keys        = "/etc/verum-registry/tuf-root.seeds"
timestamp_signing_key    = "/etc/verum-registry/tuf-timestamp.seed"
snapshot_signing_key     = "/etc/verum-registry/tuf-snapshot.seed"
targets_signing_key      = "/etc/verum-registry/tuf-targets.seed"
root_validity_days       = 365
timestamp_validity_hours = 24
snapshot_validity_days   = 7
targets_validity_days    = 30
sigstore_fulcio_ca_path  = "/etc/verum-registry/fulcio-ca.pem"
sigstore_rekor_pubkey    = "/etc/verum-registry/rekor-pubkey.pem"
sigstore_rekor_log_id    = "c0d23d6ad406973f9559f3ba2d1ca01f84147d8ffc5b8445c224f98b9591801d"

[webauthn]
rp_id    = "vcogs.io"
rp_name  = "Verum Registry"
origins  = ["https://vcogs.io", "https://www.vcogs.io"]

[oidc.providers.github]
issuer   = "https://token.actions.githubusercontent.com"
audience = "https://vcogs.io"

[oidc.providers.gitlab]
issuer   = "https://gitlab.com"
audience = "https://vcogs.io"

[oidc.providers.sigstore]
issuer   = "https://oauth2.sigstore.dev/auth"
audience = "sigstore"
```

## Appendix B — Glossary

| Term                | Meaning                                                  |
|---------------------|----------------------------------------------------------|
| **Cog**             | A Verum package — source + manifest + metadata.          |
| **Manifest**        | The `verum.toml` file at the cog root.                   |
| **Sumdb**           | Local registry transparency log of published checksums.   |
| **STH**             | Signed Tree Head — Ed25519 commitment to log state.       |
| **Tile**            | RFC 9162 Merkle-tree slice (256 leaves).                 |
| **Anti-pattern**    | One of 40 architectural defects (`AP-001..AP-040`).      |
| **Lifecycle**       | CVE seven-symbol status (T / D / C / P / H / I / ✗).     |
| **Trusted publishing** | OIDC-flow-authenticated publish from CI/CD.            |
| **Yank**            | Hide a version from new resolutions; existing locks ok.   |
| **Provenance**      | SLSA / in-toto attestation of build origin.              |
| **Sigstore**        | Public keyless-signing infrastructure (Rekor + Fulcio).  |
| **Rekor**           | Sigstore's transparency log for signature anchoring.     |
| **Fulcio**          | Sigstore's CA for ephemeral OIDC-bound certs.            |
| **TUF**             | The Update Framework — compromise-resilient distribution. |
| **WebAuthn**        | W3C standard for public-key user authentication.         |
| **Passkey**         | A WebAuthn credential — phishing-resistant + cloud-synced. |
| **AAGUID**          | Authenticator Attestation Globally Unique Identifier.    |
| **DSSE**            | Dead Simple Signing Envelope (in-toto attestation wrap). |
| **SET**             | Signed Entry Timestamp (Rekor's inclusion promise).      |
| **ATS-V**           | Architectural Type System for Verum.                     |
| **Foundation**      | Logical foundation (ZFC, HoTT, CIC, ...).                |
| **Stratum**         | MSFS modulus level (LFnd / LCls / LClsTop / LAbs).       |
| **Tier**            | Execution placement (Interp / Aot / Gpu / Check / MultiTier). |
| **Capability**      | Declared resource access (Network, Read, Write, …).      |
| **ShapeDeclarations** | Block of `Purpose`, `CognitiveSubstrate`, `FormalAnchoring`, `ExecutabilitySense`, `SelfReferenceWitness`. |
| **Audit-protocol**  | The seven-layer (L0..L6) bundle-verdict procedure.        |
| **Dual-audience**   | Developer (terse) + auditor (exhaustive JSON) reports from the same compiled Shape. |

---

*End of specification.*
