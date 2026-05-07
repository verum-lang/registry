# Verum Registry Specification

## Architecture-Aligned Reference Implementation on the Enriched Verum stdlib

---

**Version**: 2.0.0 (full rewrite — supersedes v1.0)
**Status**: Authoritative
**Authors**: Verum Language Team

---

## 0. Foreword — what changed from v1.0

Version 1.0 of this specification was authored before the Verum stdlib
underwent its current architectural reorganisation. v1.0 referred to
APIs that no longer exist (`std.server.{Server, ServerConfig}`,
`std.database.postgres.PostgresPool`, `std.crypto.{sha256, ed25519}`,
`std.archive.tar`, `std.async.spawn`, `std.encoding.base64`,
`std.time.{DateTime, Instant}`), used a runtime `sql"..."` literal
where the language now exposes a **compile-time** `sql#"..."`
meta-function, conflated configuration languages with wire-format
serialisation, and did not exist alongside the now-mature Verum
**configuration**, **archive**, **transparency-log**, **migration**,
and **cog** subsystems.

This v2.0 specification is a **full rewrite**. There is no backward
compatibility with v1.0. The implementation that v1.0 anchored
(currently in `registry/src/`) will be refactored against this
specification in a follow-up; the portions of that earlier code that
duplicated stdlib facilities are removed and replaced with the
canonical stdlib idioms.

The architectural pivot of v2.0: **the registry composes against the
enriched Verum stdlib at every layer**. Where v1.0 hand-rolled SemVer
constraint matching, malware-pattern Levenshtein distance, USTAR
packaging, Merkle-tree sumdb, Postgres migrations, OIDC validation,
and TOML manifest parsing, v2.0 *uses the stdlib*. The registry shrinks
to its essential domain logic: the *workflow* of receiving, validating,
storing, indexing, and serving knowledge artefacts (cogs).

---

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Design Principles](#2-design-principles)
3.  [Architectural Overview](#3-architectural-overview)
4.  [The Enriched stdlib Foundation](#4-the-enriched-stdlib-foundation)
5.  [Domain Model](#5-domain-model)
6.  [Storage Layer](#6-storage-layer)
7.  [Services](#7-services)
8.  [HTTP API](#8-http-api)
9.  [Security Architecture](#9-security-architecture)
10. [Supply Chain Discipline](#10-supply-chain-discipline)
11. [Developer Experience](#11-developer-experience)
12. [Operational Excellence](#12-operational-excellence)
13. [CVE Self-Application](#13-cve-self-application)
14. [Implementation Map](#14-implementation-map)

---

## 1. Executive Summary

### 1.1 Vision

The Verum Registry (`vcogs.io`) is the **canonical package
distribution system** for the Verum language ecosystem. It serves two
purposes simultaneously:

1. **Production infrastructure** for the ecosystem — receiving,
   validating, storing, and serving Verum cogs.
2. **A reference Verum application** — demonstrating idiomatic use of
   the language: refinement types, affine resources, async/await,
   protocol-driven composition, the CVE architectural discipline.

### 1.2 The four core verbs

The registry's surface reduces to four verbs:

| Verb        | Description                                                          |
|-------------|----------------------------------------------------------------------|
| **Publish** | Receive a cog archive + manifest, validate, sign, persist, index.    |
| **Resolve** | Given a dependency constraint, return the canonical version + URL.   |
| **Verify**  | Given a `(name, version)`, return signed-tree-head + checksum proof. |
| **Search**  | Given a query, return ranked matching cogs.                          |

### 1.3 Key differentiators (vs npm / crates.io / PyPI)

| Concern                       | Verum Registry                                                 | Other registries                      |
|-------------------------------|---------------------------------------------------------------|---------------------------------------|
| **Source-based publishing**   | Publishes `.vr` source; validation runs the Verum compiler.   | Publishes pre-built artifacts.        |
| **Verification portfolio**    | Cogs carry CVE Lifecycle, ShapeDeclarations, proofs.          | Code only.                            |
| **Transparency log**          | RFC 6962 Merkle log via `core.security.transparency_log`.     | Hash-list (npm) or none.              |
| **Trusted publishing**        | OIDC from CI/CD via `core.security.oidc`; no long-lived tokens. | API tokens (often leaked).          |
| **Proactive security**        | Pre-publish typosquatting + malware detection.                 | Reactive after-the-fact.             |
| **Provenance attestations**   | SLSA + in-toto via `core.security.provenance`.                | None or external.                    |
| **Manifest as a typed cog**   | `core.cog.manifest::CogManifest` — refinement-validated.      | TOML/JSON without typed schema.       |

### 1.4 What the registry is *not*

* **Not a build server.** Compilation runs server-side only for
  validation; the registry does not produce binaries for arbitrary
  targets. Pre-built artifacts are uploaded by the publisher.
* **Not a CDN.** It serves source archives, but caching/distribution
  to edge locations is delegated to a downstream CDN tier.
* **Not a git host.** Repository-style features (issues, PRs, CI hooks)
  are out of scope.
* **Not a curator.** The registry hosts whatever is published; the
  canonical-corpus discipline is community / governance, not a
  hosting concern.

---

## 2. Design Principles

```
1. SEMANTIC HONESTY      — Every type describes meaning, not implementation.
2. SECURITY BY DEFAULT   — Verification, signing, and transparency are mandatory.
3. STDLIB COMPOSITION    — Every facility uses canonical stdlib; no duplication.
4. DEVELOPER FIRST       — Zero configuration, zero boilerplate.
5. CVE-CLOSED            — Every artefact (including the registry itself) is
                            CVE-Lifecycle-classified.
6. CATEGORICAL STRUCTURE — Public surfaces form natural categories;
                            cross-format conversions factor canonically.
```

### 2.1 The minimalism criterion

Every feature passes this gate before inclusion:

```
Is this feature:
  1. Essential for cog distribution? OR
  2. Essential for security? OR
  3. Uniquely valuable for Verum's verification story? OR
  4. Already provided by Verum stdlib (then: USE IT)?

If NO to all four → DO NOT include.
```

### 2.2 The composition criterion

Every implementation passes this gate before merging:

```
Is the facility duplicated or paralleled in Verum stdlib?

  YES → use the stdlib facility.
  NO  → propose a stdlib extension; discuss; if accepted, land in stdlib.
        If rejected (legitimately registry-specific), implement here.
```

This is what rebuilt v2.0: every feature that was hand-rolled in v1.0
and has a stdlib analog is replaced by the stdlib analog. The
registry shrinks; the stdlib grows.

---

## 3. Architectural Overview

### 3.1 High-level architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       VERUM REGISTRY ARCHITECTURE                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────┐         ┌────────────────────────────────────┐ │
│  │  Web frontend       │ ◄─────► │  HTTP API (core/net/weft)          │ │
│  │  (SvelteKit)        │         │  Routes / middleware / mTLS / SPIFFE│ │
│  │                     │         │                                    │ │
│  │  package browser    │         │  ┌──────────────────────────────┐  │ │
│  │  search / docs      │         │  │  Service layer               │  │ │
│  │  publish wizard     │         │  │  ─ PublishService            │  │ │
│  └─────────────────────┘         │  │  ─ SearchService             │  │ │
│                                  │  │  ─ SumdbService              │  │ │
│  ┌─────────────────────┐         │  │  ─ AuthService (OIDC + tokens)│  │ │
│  │  verum CLI          │ ◄─────► │  │  ─ ProvenanceService          │  │ │
│  │  (verum add /       │         │  └──────────────────────────────┘  │ │
│  │  publish / resolve) │         │                                    │ │
│  └─────────────────────┘         │  ┌──────────────────────────────┐  │ │
│                                  │  │  Domain layer                │  │ │
│                                  │  │  ─ CogManifest (core.cog)    │  │ │
│                                  │  │  ─ CogArchive                │  │ │
│                                  │  │  ─ Owner / User / Token      │  │ │
│                                  │  │  ─ Sumdb entries             │  │ │
│                                  │  └──────────────────────────────┘  │ │
│                                  └────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                       Persistence layer                            │ │
│  │                                                                    │ │
│  │  ┌──────────────────┐ ┌─────────────┐ ┌─────────┐ ┌─────────────┐ │ │
│  │  │ PostgreSQL       │ │  S3-compat  │ │  Redis  │ │ Transparency │ │ │
│  │  │ (core.database)  │ │ (binary obj)│ │ (cache) │ │ log (Merkle) │ │ │
│  │  │ + migrations     │ │             │ │         │ │              │ │ │
│  │  └──────────────────┘ └─────────────┘ └─────────┘ └─────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 The publish request flow

```
Developer                      Registry                        Persistence
    │                              │                                │
    │   POST /api/v2/publish       │                                │
    │   (multipart: manifest.toml  │                                │
    │   + source.tar.zst)          │                                │
    │ ─────────────────────────► │                                │
    │                              │                                │
    │                       ┌──────┴──────┐                         │
    │                       │  AuthService │                         │
    │                       │  ─ verify OIDC token (core.oidc)      │
    │                       │  ─ OR API token (Argon2id)            │
    │                       └──────┬──────┘                         │
    │                              │                                │
    │                       ┌──────┴──────────────────────┐         │
    │                       │  PublishService              │         │
    │                       │                              │         │
    │                       │  1. Parse manifest.toml      │         │
    │                       │     (core.configuration.toml)│         │
    │                       │  2. Parse + validate         │         │
    │                       │     (core.cog.manifest)      │         │
    │                       │  3. Unpack source archive    │         │
    │                       │     (core.archive.tar)       │         │
    │                       │  4. Compile-validate         │         │
    │                       │     (verum_kernel)           │         │
    │                       │  5. Anti-pattern catalog     │         │
    │                       │     (40 APs via              │         │
    │                       │     check_all_anti_patterns) │         │
    │                       │  6. Pre-publish security     │         │
    │                       │     ─ typosquatting          │         │
    │                       │     ─ malware                │         │
    │                       │  7. SemVer monotone-bump     │         │
    │                       │     (core.base.semver_constraint)│     │
    │                       └──────┬──────────────────────┘         │
    │                              │                                │
    │                              │   transactional persist        │
    │                              │ ─────────────────────────────► │
    │                              │   ─ Postgres rows               │
    │                              │   ─ S3 source archive           │
    │                              │   ─ Append to sumdb log         │
    │                              │                                │
    │                       ┌──────┴──────┐                         │
    │                       │  201 Created │                         │
    │                       │  + signed STH│                         │
    │                       └──────┬──────┘                         │
    │ ◄─────────────────────────── │                                │
```

### 3.3 Component responsibility matrix

| Component         | Responsibility                                       | Stdlib used                                            |
|-------------------|------------------------------------------------------|--------------------------------------------------------|
| HTTP API          | Routing, body parsing, middleware                    | `core.net.weft`                                        |
| Auth service      | OIDC trusted publishing + API tokens                 | `core.security.oidc`, `core.security.password_hash`    |
| Publish service   | Validate, store, index, sumdb-append                 | (orchestrates everything below)                        |
| Manifest parsing  | Parse + validate `verum.toml`                        | `core.configuration.toml`, `core.cog.manifest`         |
| Archive packaging | Pack/unpack source bundle                            | `core.archive.tar`, `core.compress.{gzip, zstd}`       |
| Compilation       | Validate the cog compiles                            | `verum_kernel`, `verum_compiler` (in-process)          |
| Anti-pattern check| Run 40-pattern catalog                               | `verum_kernel::arch_anti_pattern::check_all_anti_patterns` |
| Cog signing       | Ed25519 sign archive + manifest hash                 | `core.security.ecc.ed25519`                            |
| Transparency log  | Append, signed STH, inclusion proofs                 | `core.security.transparency_log`                       |
| Provenance        | SLSA / in-toto attestations                          | `core.security.provenance`                             |
| Storage           | Postgres for metadata, S3 for blobs                  | `core.database.postgres`, `core.storage.s3`            |
| Migrations        | Schema evolution                                     | `core.database.postgres.migrations`                    |
| Cache             | Redis for hot path                                   | `core.cache.redis`                                     |
| Search            | Full-text + faceted                                  | `core.search.meilisearch`                              |
| Resilience        | Per-IP rate limit, backpressure, circuit breakers    | `core.net.weft.{backpressure, listener}`               |

---

## 4. The Enriched stdlib Foundation

The registry's complexity is a function of the stdlib's expressive
power. v2.0 stdlib provides the following load-bearing facilities;
the registry composes against them.

### 4.1 Configuration

`core.configuration` is the unified configuration subsystem.

* `value.vr` — `ConfigValue` ADT, the universal hub.
* `error.vr` — `ConfigError` taxonomy, 5-level error category.
* `format.vr` — `ConfigFormat` protocol + open registry.
* `convert.vr` — cross-format conversion via `ConfigValue` hub.
* `mod.vr` — `load_text(text, format_id)`, `dump_text`, `convert`.
* `toml.vr` — TOML 1.0 adapter (used by manifest parser).

Registry uses TOML for `verum.toml` parsing. The `ConfigValue` hub
permits future migration to YAML/JSON5/HCL without rewriting domain
logic.

### 4.2 Cog metadata

`core.cog.manifest` provides the typed surface:

```verum
public type CogManifest is {
    cog: CogIdentity,                              // name + version + authors + license + ...
    language: LanguageConfig,                      // Application / Systems / Research
    dependencies: Map<Text, DependencySpec>,
    dev_dependencies: Map<Text, DependencySpec>,
    build_dependencies: Map<Text, DependencySpec>,
    features: Map<Text, List<Text>>,
    default_features: List<Text>,
    meta: ConfigValue,                             // free-form vendor extensions
};
```

* `parse_text(toml_source) -> Result<CogManifest, ManifestError>` —
  reads verum.toml.
* `format_text(&manifest) -> Result<Text, ManifestError>` —
  round-trip writer.
* Refinement-typed `CogName` matching the regex
  `^(@[a-z0-9][a-z0-9-]{0,63}/)?[a-z][a-z0-9_-]{0,63}$`.

### 4.3 Version constraint algebra

`core.base.semver_constraint` provides:

* `SemVerConstraint` algebraic tree (`Eq` / `Gt` / `Gte` / `Lt` /
  `Lte` / `And` / `Or` / `Any` / `Empty`).
* `parse(s) -> Result<SemVerConstraint, ...>` — Cargo+npm-flavoured.
* `matches(c, v, opts) -> Bool`.
* `MatchOptions.allow_prerelease` for cross-stability matching.

The registry uses this for dependency-resolution path traversal.

### 4.4 Archive packaging

`core.archive` provides the unified packaging subsystem mirroring
`core.compress`:

* `Archive` protocol (`pack` / `unpack`) + `ArchiveAlgorithm` enum
  (Tar / Zip / Ar / Cpio).
* `tar.vr` — USTAR + PAX-extended adapter.
* Composes with `core.compress.{gzip, zstd, brotli, lz4}` for
  `.tar.gz` / `.tar.zst` / etc.

The registry uses tar+zstd for source archive distribution.

### 4.5 Transparency log

`core.security.transparency_log` provides:

* RFC 6962 + RFC 9162 Merkle log on top of `core.security.merkle`.
* Tile-addressed proofs (256 leaves per tile).
* Signed tree heads (Ed25519 via `core.security.ecc.ed25519`).
* Consistency proofs (RFC 6962 §2.1.2).

The registry uses this for the sumdb (Verum's analog of Go's
checksum database).

### 4.6 Database

`core.database.postgres` provides:

* `PgConnection` / `PgPool` / `AsyncPgPool` (connection pooling).
* Compile-time `sql#"..."` meta-function for type-safe queries.
* Affine `Transaction` (compiler-enforced commit/rollback).
* `core.database.postgres.migrations` — vendor-neutral migration
  framework with Postgres-specific advisory locks + transactional DDL.

### 4.7 HTTP server

`core.net.weft` provides:

* `WeftApp` / `Server<H>` — the canonical entry idiom.
* `Router` with refined-typed path parameters (`refined_routes.vr`).
* HTTP/2 with Rapid-Reset defence (`http2.vr`).
* TLS + SPIFFE + 0-RTT gating (`tls.vr`, `spiffe.vr`,
  `zero_rtt_gate.vr`).
* `Json<T>` extractor with five-gate typed deserialisation.
* WebSocket (`websocket.vr`).
* Backpressure, rate limiting, metrics, timeouts.

### 4.8 Crypto

`core.security` provides:

* `merkle.vr` — RFC 6962 Merkle tree.
* `ecc/ed25519.vr` — Ed25519 sign/verify with strict ZIP-215.
* `hash/{sha256, blake3, ...}.vr` — cryptographic hashing.
* `oidc.vr` *(forthcoming — G6)* — OIDC discovery + JWKS cache.
* `provenance.vr` *(forthcoming — G7)* — SLSA + in-toto attestations.

### 4.9 Identifiers

`core.base.{ulid, uuid, snowflake, nanoid}` provide identifier
generation. The registry uses ULIDs for monotonic
publication-ordered identifiers.

### 4.10 Text distance

`core.base.string_distance` provides Levenshtein and other distance
metrics. The registry uses this for typosquatting detection without
hand-rolling.

---

## 5. Domain Model

### 5.1 Domain entities

The registry's domain types are thin records over Verum's refinement-
typed primitives. Everything is `@derive(Serialize, Deserialize, Eq,
Clone)` for Postgres roundtrip and JSON wire encoding.

#### 5.1.1 PackageScope

```verum
/// Scoped or unscoped package identifier.
/// - `name`         for unscoped (restricted to verified-publisher names)
/// - `@org/name`    for scoped
@derive(Serialize, Deserialize, Eq, Clone, Hash)
public type PackageScope is Text {
    where self.matches(r"^(@[a-z0-9][a-z0-9-]{0,63}/)?[a-z][a-z0-9_-]{0,63}$")
};
```

This is identical to `core.cog.manifest::CogName` — they are aliased
in the registry domain layer.

#### 5.1.2 PackageRecord

```verum
@derive(Serialize, Deserialize, Eq, Clone)
public type PackageRecord is {
    /// Globally-unique scope/name.
    id: PackageScope,
    /// One-line description (≤ 500 bytes, NO newlines).
    description: Text { len <= 500, !contains("\n") },
    /// Canonical homepage URL (optional).
    homepage: Maybe<Url>,
    /// Source repository URL (optional).
    repository: Maybe<Url>,
    /// SPDX license expression. The registry validates this against
    /// `core.security.spdx::is_valid_expression`.
    license: SpdxExpression,
    /// Search keywords — at most 5 by SemVer-discipline convention.
    keywords: List<Keyword> { len <= 5 },
    /// Latest stable version (i.e., highest non-prerelease version that
    /// is not yanked).
    latest_version: SemVer,
    /// Total cumulative downloads.
    downloads: Int { >= 0 },
    /// Quality score (0–100; computed by the publish pipeline; see §11.4).
    score: Int { >= 0, <= 100 },
    /// Creation timestamp.
    created_at: Rfc3339Time,
    /// Last update timestamp.
    updated_at: Rfc3339Time,
    /// Owner user IDs (AT LEAST ONE — refinement-enforced).
    owners: List<UserId> { len >= 1 },
};
```

#### 5.1.3 PackageVersion

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
    /// SHA-256 of the source archive (hex-encoded, lowercase, 64 chars).
    source_sha256: Hex64,
    /// CVE Lifecycle declared by the cog's `@arch_module(...)`.
    cve_lifecycle: Lifecycle,
    /// CVE ShapeDeclarations digest — hash of the canonicalised
    /// declarations record. Lets the registry detect drift between
    /// the manifest's declared shape and the compiled cog's actual
    /// shape.
    shape_declarations_digest: Hex64,
    /// Verification level achieved (highest of the
    /// 9-strategy verification ladder that admits the cog).
    verification_level: VerificationLevel,
    published_at: Rfc3339Time,
    published_by: UserId,
    yanked: Bool,
    yank_reason: Maybe<Text>,
    provenance: Maybe<ProvenanceEnvelope>,
};
```

#### 5.1.4 User + ApiToken + Owner + SumdbEntry

(Schema details — see §6.1 for the full Postgres mapping.)

### 5.2 The domain–stdlib mapping

| Registry domain type | Underlying stdlib type / module                                      |
|----------------------|----------------------------------------------------------------------|
| `PackageScope`       | refinement on `Text` (alias of `core.cog.manifest::CogName`)         |
| `SemVer`             | `core.base.semver::SemVer`                                           |
| `Lifecycle`          | `core.architecture.types::Lifecycle`                                 |
| `LanguageProfile`    | `core.cog.manifest::LanguageProfile`                                 |
| `DependencySpec`     | `core.cog.manifest::DependencySpec`                                  |
| `Hex64`              | refinement on `Text`                                                 |
| `Ulid`               | `core.base.ulid::Ulid`                                               |
| `Rfc3339Time`        | `core.time.rfc3339::Rfc3339Time`                                     |
| `Url`                | `core.text.url::Url`                                                 |
| `EmailAddress`       | refinement on `Text` validated via `core.text.email`                 |
| `PasswordHash`       | `core.security.password_hash::Argon2idHash`                          |
| `ProvenanceEnvelope` | `core.security.provenance::DsseEnvelope` (G7)                        |
| `OidcIdentity`       | `core.security.oidc::OidcIdentity` (G6)                              |

The registry domain layer **owns** none of these types' implementation;
it only **assembles** them into the domain shape.

---

## 6. Storage Layer

### 6.1 Postgres schema

The schema lives in `migrations/v2/` as numbered SQL migrations
applied through `core.database.postgres.migrations`. The
`__verum_migrations` tracking table is created automatically.

```sql
-- 0001_initial_schema.sql

CREATE TABLE users (
    id            TEXT PRIMARY KEY,           -- ULID
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT,                       -- Argon2id; NULL for OIDC-only
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_username_format CHECK (username ~ '^[a-z][a-z0-9_-]{1,63}$')
);

CREATE TABLE oidc_identities (
    user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issuer    TEXT NOT NULL,
    subject   TEXT NOT NULL,
    metadata  JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (issuer, subject)
);
CREATE INDEX oidc_identities_user_id_idx ON oidc_identities (user_id);

CREATE TABLE api_tokens (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    secret_hash   TEXT NOT NULL,
    scopes        JSONB NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked_at    TIMESTAMPTZ,
    last_used_at  TIMESTAMPTZ
);

CREATE TABLE packages (
    id              TEXT PRIMARY KEY,
    description     TEXT NOT NULL,
    homepage        TEXT,
    repository      TEXT,
    license         TEXT NOT NULL,
    keywords        TEXT[] NOT NULL DEFAULT '{}',
    latest_version  TEXT NOT NULL,
    downloads       BIGINT NOT NULL DEFAULT 0,
    score           SMALLINT NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT packages_id_format
        CHECK (id ~ '^(@[a-z0-9][a-z0-9-]{0,63}/)?[a-z][a-z0-9_-]{0,63}$')
);
CREATE INDEX packages_keywords_gin ON packages USING GIN (keywords);
CREATE INDEX packages_downloads_idx ON packages (downloads DESC);
CREATE INDEX packages_updated_idx ON packages (updated_at DESC);

CREATE TABLE package_owners (
    package_id    TEXT NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('owner', 'maintainer')),
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by    TEXT NOT NULL REFERENCES users(id),
    PRIMARY KEY (package_id, user_id)
);

CREATE TABLE versions (
    id                         BIGSERIAL PRIMARY KEY,
    package_id                 TEXT NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    version                    TEXT NOT NULL,
    edition                    TEXT NOT NULL,
    language_profile           TEXT NOT NULL CHECK (language_profile IN ('application','systems','research')),
    dependencies               JSONB NOT NULL DEFAULT '{}',
    dev_dependencies           JSONB NOT NULL DEFAULT '{}',
    build_dependencies         JSONB NOT NULL DEFAULT '{}',
    features                   JSONB NOT NULL DEFAULT '{}',
    default_features           TEXT[] NOT NULL DEFAULT '{}',
    source_sha256              CHAR(64) NOT NULL,
    cve_lifecycle              TEXT NOT NULL,
    shape_declarations_digest  CHAR(64) NOT NULL,
    verification_level         TEXT NOT NULL,
    published_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_by               TEXT NOT NULL REFERENCES users(id),
    yanked                     BOOLEAN NOT NULL DEFAULT false,
    yank_reason                TEXT,
    provenance                 JSONB,
    UNIQUE (package_id, version),
    CONSTRAINT versions_yank_reason_required
        CHECK ((NOT yanked AND yank_reason IS NULL) OR (yanked AND yank_reason IS NOT NULL)),
    CONSTRAINT versions_sha256_format CHECK (source_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE sumdb_entries (
    sequence    BIGSERIAL PRIMARY KEY,
    package_id  TEXT NOT NULL,
    version     TEXT NOT NULL,
    checksum    CHAR(64) NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    leaf_hash   BYTEA NOT NULL,
    UNIQUE (package_id, version)
);

CREATE TABLE sumdb_tree_heads (
    tree_size    BIGINT PRIMARY KEY,
    root_hash    BYTEA NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT now(),
    signature    BYTEA NOT NULL
);

CREATE TABLE security_advisories (
    id                  TEXT PRIMARY KEY,
    package_id          TEXT NOT NULL REFERENCES packages(id),
    affected_versions   TEXT NOT NULL,
    fixed_versions      TEXT,
    severity            TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    cve_ids             TEXT[],
    summary             TEXT NOT NULL,
    details             TEXT,
    disclosed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2 Migrations

Migrations are authored as `core.database.common.migrations.Migration`
records and applied through the Postgres `MigrationRunner`. The
Postgres store acquires `pg_advisory_lock(<key>)` so concurrent
registry instances serialise without DDL races.

### 6.3 Object storage (S3)

Source archives at:

```
packages/<scope>/<name>/<version>/source.tar.zst
```

S3 objects are immutable: once written, never overwritten.

### 6.4 Cache (Redis)

| Key pattern                              | TTL    | Use                          |
|------------------------------------------|--------|------------------------------|
| `package:<scope>/<name>`                 | 5 min  | Package metadata cache       |
| `versions:<scope>/<name>`                | 5 min  | Version-list cache           |
| `version:<scope>/<name>:<version>`       | 1 hour | Single-version cache         |
| `sumdb:<scope>/<name>@<version>`         | 1 year | Checksum lookup (immutable)  |
| `sumdb:tile:<level>:<index>`             | 1 year | Merkle tile (immutable)      |
| `ratelimit:<client>`                     | 1 min  | Token-bucket counter         |
| `oidc:jwks:<issuer>`                     | 1 hour | JWKS cache (per-issuer)      |

### 6.5 Search (MeiliSearch)

Indexed: `id`, `description` (full-text), `keywords` (faceted),
`latest_version`, `downloads` / `score` (sortable), `cve_lifecycle`
/ `language_profile` / `verification_level` (faceted).

---

## 7. Services

The service layer is the **business-logic core**. Each service is a
Verum cog with a declared `@arch_module(...)` Shape; CVE
ShapeDeclarations are mandatory.

### 7.1 PublishService — eight-phase workflow

```verum
@arch_module(
    foundation:    Foundation.ZfcTwoInacc,
    stratum:       MsfsStratum.LCls,
    lifecycle:     Lifecycle.Theorem("v2.0"),
    declarations: ShapeDeclarations {
        purpose: Some(Purpose {
            role: "registry publish workflow — eight-phase validate-and-store pipeline",
            k_min: CveThresholdK.FullWitness,
            v_min: CveThresholdV.NamedCertification,
            e_min: CveThresholdE.StructurallyReady,
        }),
        substrate: Some(CognitiveSubstrate.AnalyticDecompositional),
        anchoring: Some(FormalAnchoring.CurryHowardLawvere),
        e_sense:   Some(ExecutabilitySense.StructuralReadiness),
        self_reference: None,
    },
)
module verum_registry.services.publish_service;

public type PublishService is {};

implement PublishService {
    public async fn publish(
        &self,
        user: User,
        manifest_text: Text,
        source_archive: List<Byte>,
    ) -> Result<PackageVersion, PublishError>
        using [Database, Storage, Cache, Search, Sumdb, Logger, Metrics]
    {
        let manifest = self.phase1_parse_manifest(&manifest_text)?;
        self.phase2_check_ownership(&user, &manifest.cog.name).await?;
        self.phase3_check_version_bump(&manifest).await?;
        self.phase4_security_analysis(&manifest).await?;
        let analyzed = self.phase5_analyze_archive(&manifest, &source_archive).await?;
        let artefacts = self.phase6_generate_artefacts(&manifest, &analyzed).await?;
        let version = self.phase7_persist(&user, &manifest, &source_archive, &artefacts).await?;
        self.phase8_post_publish(&version).await;
        Ok(version)
    }
}
```

**Phase 1** — parse manifest via `core.cog.manifest.parse_text`.

**Phase 2** — ownership check. First-publish: no entry exists yet (created
in Phase 7); else caller must be in `package_owners`.

**Phase 3** — SemVer monotonicity. New version > all existing; no
re-publication of historic versions.

**Phase 4** — security analysis:
* **Typosquatting**: `core.base.string_distance.damerau_levenshtein`
  vs high-download names; `d ≤ 2 and d > 0` triggers manual-review
  queue.
* **Malware**: static-pattern scan via `core.security.malware_patterns`
  (registry-side ruleset). Critical-severity matches abort the publish.

**Phase 5** — source-archive analysis:
* zstd-decode + tar-unpack via `core.compress.zstd` +
  `core.archive.tar`.
* `verum_kernel.compile_validate` (in-process).
* `arch_anti_pattern.check_all_anti_patterns` over 40-pattern
  catalog. Any `Severity.Error` aborts.
* Extract `Lifecycle`, `ShapeDeclarations` digest,
  `VerificationLevel`.

**Phase 6** — artefact generation:
* Sumdb leaf (canonical JSON of `SumdbEntry`).
* Cog signature via `core.security.ecc.ed25519`.
* Provenance attestation (when authenticated via OIDC).

**Phase 7** — transactional persist:
* Inside one Postgres transaction: insert `packages` + `versions` rows;
  insert ownership (if first publish); append to `sumdb_entries`;
  commit a new `sumdb_tree_heads` row with Ed25519 signature; emit
  `LISTEN` notification on `package_published` channel.
* Outside transaction: S3 upload (S3 is non-transactional). On post-
  commit S3 failure, write `pending_object_pushes` row; background
  reconciler retries.

**Phase 8** — async-spawned post-publish:
* Update MeiliSearch.
* Emit webhooks.
* Invalidate cache keys.

### 7.2 SearchService

```verum
public type SearchQuery is {
    q: Text,
    cve_lifecycle: Maybe<Lifecycle>,
    language_profile: Maybe<LanguageProfile>,
    verification_level_min: Maybe<VerificationLevel>,
    license: Maybe<SpdxExpression>,
    page: Int { >= 0 },
    per_page: Int { >= 1, <= 100 },
    sort: SortMode,
};

public type SortMode is SortRelevance | SortDownloads | SortRecent | SortScore;
```

### 7.3 SumdbService

Wraps `core.security.transparency_log` for HTTP exposure: `lookup`,
`latest_tree_head`, `tile`.

### 7.4 AuthService

Authenticates via either:
1. **OIDC trusted publishing** (preferred) — Bearer JWT validated
   against issuer's JWKS via `core.security.oidc`.
2. **API token** (fallback) — `Authorization: Token <id>:<secret>`,
   verified Argon2id.

### 7.5 ProvenanceService (G7)

Builds + verifies SLSA v1.0 statements wrapped in DSSE envelopes
via `core.security.provenance` (forthcoming).

---

## 8. HTTP API

### 8.1 Versioning

The API is versioned by URL path: `/api/v2/...`. Backward-incompatible
changes require a new major version (a new path); minor changes are
additive.

### 8.2 Routes

```
/api/v2/
  packages/
    GET  /:scope/:name                       — package metadata
    GET  /:scope/:name/versions              — version list
    GET  /:scope/:name/:version              — version metadata
    GET  /:scope/:name/:version/source       — source archive (302 to S3)
    GET  /:scope/:name/:version/manifest     — verum.toml
    GET  /:scope/:name/:version/provenance   — DSSE envelope
    POST /                                   — publish a new version

  packages/:scope/:name/:version/
    POST /yank                               — yank
    POST /unyank                             — unyank (≤ 24h after yank)

  packages/:scope/:name/owners/
    GET  /                                   — list owners
    POST /                                   — invite owner
    DELETE /:user                            — remove owner

  search                                     — GET ?q=...&page=...
  resolve                                    — POST { dependencies: { ... } }

  auth/
    POST /login                              — { username, password } → session
    POST /oidc/discover/:provider            — OIDC discovery + JWKS warmup
    POST /tokens                             — create API token
    DELETE /tokens/:id                       — revoke

  users/:username                            — GET public profile

/sumdb/
  GET  /lookup/:scope/:name@:version
  GET  /latest                               — signed tree head
  GET  /tile/:level/:index                   — Merkle tile

/health/
  GET  /live
  GET  /ready
  GET  /version

/metrics                                     — Prometheus (mTLS-restricted)
```

### 8.3 Wire formats

* JSON for API responses (`application/json; charset=utf-8`).
* TOML for manifest body in publish (`application/toml`).
* Multipart for publish (`multipart/form-data`).
* Tar+zstd for source archives (`application/vnd.verum.cog-source+tar+zstd`).

### 8.4 Error envelope

```json
{
  "error": {
    "code": "validation_failed",
    "message": "Manifest field 'cog.version' is not valid SemVer",
    "details": [
      { "path": "cog.version", "reason": "leading zero on patch" }
    ],
    "trace_id": "01HXM..."
  }
}
```

### 8.5 Rate limiting

Token-bucket per `(client-identity, endpoint-class)`:

| Endpoint class | Anonymous   | Authenticated |
|----------------|-------------|---------------|
| Read           | 60 / min    | 300 / min     |
| Search         | 30 / min    | 120 / min     |
| Publish        | n/a         | 30 / hour     |
| Sumdb          | 600 / min   | 600 / min     |
| Auth           | 10 / min    | 10 / min      |

Implemented via `core.net.weft.backpressure.RateLimitLayer` over
Redis-backed counters.

### 8.6 Server bootstrap

```verum
async fn main() -> Result<(), Box<dyn Error>> {
    let config = Config.from_env()?;

    let db_pool = postgres.async_pool.connect(&config.postgres).await?;
    let storage = s3.connect(&config.s3).await?;
    let cache = redis.connect(&config.redis).await?;
    let search = meilisearch.connect(&config.meilisearch).await?;
    let oidc = oidc_provider_registry_from_config(&config.oidc).await?;

    let services = ServiceRegistry {
        publish:    PublishService {},
        search:     SearchService {},
        sumdb:      SumdbService { log: load_sumdb_log(&db_pool).await? },
        auth:       AuthService { oidc_provider_registry: oidc },
        provenance: ProvenanceService {},
    };

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

## 9. Security Architecture

### 9.1 Threat model

| Vector                              | Defence                                              |
|-------------------------------------|------------------------------------------------------|
| Credential leak (API token)         | Argon2id storage; mandatory expiry; revocation       |
| Credential leak (OIDC bearer)       | Short-lived (≤ 15 min); JWKS-validated               |
| Typosquatting                       | Damerau–Levenshtein vs high-download names           |
| Dependency confusion                | Scope-required for new namespace claim               |
| Malicious code                      | Static-pattern scanner + manual-review queue         |
| Supply-chain (silent re-publish)    | Sumdb append-only; immutable S3; tree-head sig       |
| Account takeover                    | OIDC-only accounts; API tokens with scopes + expiry  |
| Denial-of-service                   | Per-IP rate limit; concurrency limit; backpressure   |
| Cryptographic break                 | Post-quantum migration via `core.security.pq`        |

### 9.2 OIDC trusted publishing

Validate against issuer's JWKS:
1. Token signature via `core.security.oidc::validate`.
2. Standard claims: `iss`, `aud`, `exp`, `nbf`, `iat`.
3. Provider-specific claims (e.g., GitHub Actions: `repository`,
   `workflow`, `ref`, `sub`) matched against package's
   trusted-publisher config.

```toml
[publish.trusted_publishers]
[[publish.trusted_publishers.github]]
repository = "myorg/mycog"
workflow   = ".github/workflows/release.yml"
ref        = "refs/tags/v*"
environment = "production"
```

### 9.3 Sumdb (transparency log)

Leaf format:
```json
{
  "package":   "@team/server",
  "version":   "1.2.3",
  "checksum":  "<hex64>",
  "timestamp": "2026-05-08T10:00:00Z"
}
```

JSON canonicalised, then `leaf_hash = SHA-256(0x00 || canonical_bytes)`.
Append via `core.security.transparency_log::append`. New tree head
signed Ed25519.

**Client verification** (`verum verify-checksums`):
```
$ verum verify-checksums
  package    @team/server@1.2.3
  computed   8c7e...
  expected   8c7e...
  proof      sha256(...) → ... → root
  tree-head  size=12345 root=... (Ed25519 ✓)
  verdict    VERIFIED
```

### 9.4 Cog signing

Registry signing key provisioned at deploy, rotated quarterly.
Public key at `https://vcogs.io/.well-known/verum-registry-pubkey`,
mirrored on a third-party note-storage. Signature scheme:
`Ed25519(SHA-256(manifest_canonical_json) || SHA-256(source_archive))`.

### 9.5 Provenance

When publisher authenticated via OIDC, registry constructs a SLSA
v1.0 statement embedding OIDC claims (provider, repository, workflow,
run ID). DSSE-signed by registry. Publisher-uploaded provenance is
also accepted; both are stored.

---

## 10. Supply Chain Discipline

### 10.1 Yank semantics

Yanked version: hidden from new resolutions; remains downloadable
for existing lock files. Requires:
* Caller is package owner or maintainer.
* `yank_reason` provided (≤ 500 bytes free-form text).

Unyank within 24 hours of yank; thereafter, publish a new version.

### 10.2 Security advisories

Immutable once published. Each specifies:
* Affected versions (`SemVerConstraint` expression).
* Fixed versions (`SemVerConstraint` or `null`).
* Severity (low / medium / high / critical).
* CVE IDs (optional).

### 10.3 Lock file integrity

Lock files include sumdb tree-head at resolution time. Subsequent
restores (`verum install --frozen`) verify each cog's checksum AND
the tree-head's consistency with the current registry tree-head.

---

## 11. Developer Experience

### 11.1 Publish UX

```bash
$ verum publish
  manifest        verum.toml ✓
  source archive  built (12.4 MiB → 2.1 MiB after zstd)
  authentication  OIDC (github / org/repo) ✓
  uploading       https://vcogs.io/api/v2/publish ████████████ 100%
  validation      compile ✓ · 40 anti-patterns ✓ · typosquatting ✓
  signing         registry sig ✓
  sumdb           appended at sequence 124881
  tree-head       size=124882 root=8c7e... (signed)
  ─ published    @team/server@1.2.3 ✓
```

### 11.2 Resolve UX

```bash
$ verum add http-client
  searching       1 candidate (@verum-stdlib/http-client)
  selecting       1.5.2  (latest stable matching ^1.0)
  fetching        https://.../1.5.2/source ✓
  verifying       sha256 ✓ · sumdb proof ✓ · ed25519 sig ✓
  unpacking       ./.verum/cache/@verum-stdlib/http-client/1.5.2/
  lock            verum.lock updated
  ─ added        @verum-stdlib/http-client = "^1.5"
```

### 11.3 Doc UX

Auto-generated docs at `docs.vcogs.io/<scope>/<name>/<version>/...`
extracted via `core.cli.doc::extract_docs`.

### 11.4 Quality scoring (0–100)

| Component             | Max | Sources                                                      |
|-----------------------|-----|--------------------------------------------------------------|
| Documentation         | 30  | README (5), module docs (10), all-symbol docs (15)           |
| Testing               | 25  | tests present (10), coverage > 50% (5), > 80% (10)           |
| Verification          | 20  | `[D]` cog (5), `[C]` (10), `[T]` (15), no unsafe (5)         |
| Code quality          | 15  | no warnings (5), `verum fmt` clean (5), no deprecated (5)    |
| Maintenance           | 10  | recent updates ≤ 6 mo (5), responsive issue tracker (5)      |

Recomputed every publish + every 7 days.

---

## 12. Operational Excellence

### 12.1 Deployment topology

* API tier: 4 instances, 2–4 vCPU / 4–8 GiB. Stateless.
* Postgres: 1 primary + 2 replicas. 8–16 vCPU / 32–64 GiB.
* Redis: 3-node cluster. 4 vCPU / 4 GiB each.
* MeiliSearch: 2 instances. 4 vCPU / 8 GiB each.
* S3: managed.
* CDN: in front of source-archive URLs.

### 12.2 SLOs

| Metric                            | Target         |
|-----------------------------------|----------------|
| API latency (p50)                 | < 50 ms        |
| API latency (p95)                 | < 200 ms       |
| API latency (p99)                 | < 500 ms       |
| Publish E2E                       | < 30 s         |
| Search (p95)                      | < 50 ms        |
| Source-archive CDN-hit            | < 100 ms       |
| Uptime                            | 99.9%          |

### 12.3 Observability

OTLP via `core.tracing` + `core.metrics`. Standard panels:
request rate / latency / error rate, publish-pipeline phases,
security counters, DB pool stats, sumdb append rate, cache
hit ratio, score histogram.

### 12.4 Incident severity

| Level | Response | Examples                                      |
|-------|----------|-----------------------------------------------|
| P1    | 15 min   | API offline; data corruption; security breach |
| P2    | 1 hour   | Publish failures > 10%; sumdb inconsistency   |
| P3    | 4 hours  | Elevated error rates; component degradation  |
| P4    | 24 hours | Minor bugs; documentation; non-critical       |

### 12.5 Backup and DR

* Postgres: hourly logical + 6-hourly base + WAL. RPO 5 min, RTO 30 min.
* S3: versioning + cross-region replication. RPO 0, RTO 5 min.
* Sumdb: by construction append-only and signed; restorable from any
  consistent backup with cryptographic integrity.

---

## 13. CVE Self-Application

The registry itself is a knowledge artefact subject to CVE
classification. Every service cog declares its `@arch_module(...)`;
every domain type is `Lifecycle.Definition`; every public function
carries pre/post-conditions enforced by `@verify`.

### 13.1 Anti-pattern self-audit

Before each release, CI runs:

```bash
$ verum audit --bundle
        --> Bundle audit · CVE-L4 load-bearing aggregator
  L0 — kernel rules                      ✓ 7/7 load-bearing
  L1 — proof bodies                      ✓ 156 proved
  L2 — tactic + SMT certs                ✓ replayed
  L3 — meta-theory (ZFC + 2-inacc)       ✓ cited
  L4 — architectural shapes              ✓ 89/89
  L5 — audit-report self-consistency     ✓ schema-pinned
  L6 — articulation hygiene              ✓ no register-prohibition triggered
```

A failing audit blocks release.

### 13.2 The self-reference closure

The registry serves cogs; the registry is itself a cog; the
registry's cog is served by the registry. Per AP-040
(`SelfReferenceWithoutOperator`), the registry declares:

```verum
self_reference: Some(SelfReferenceWitness {
    operator:       "verum_registry.self_publish_pipeline",
    fixed_point:    "verum_registry@<current-version>",
    fixpoint_class: fixpoint_class_banach(),
}),
```

Banach fixed point: each self-publish iteration narrows admissible
registry-cog versions to those passing the publish pipeline;
convergence is the published-and-verified state.

---

## 14. Implementation Map

### 14.1 Source layout (Reg-R target)

```
registry/
├── verum.toml                      — manifest (this is itself a cog)
├── docs/
│   └── spec.md                     — this document
├── migrations/
│   ├── 0001_initial_schema.sql
│   ├── 0002_add_provenance.sql
│   └── 0003_add_advisories.sql
├── src/
│   ├── main.vr                     — entry + service registry assembly
│   ├── config.vr                   — load via core.configuration
│   │
│   ├── domain/                     — domain entities (§5)
│   │   ├── mod.vr
│   │   ├── package.vr              — PackageRecord
│   │   ├── version.vr              — PackageVersion
│   │   ├── user.vr                 — User + ApiToken + OidcIdentity
│   │   ├── owner.vr                — PackageOwner + OwnerRole
│   │   ├── sumdb.vr                — SumdbEntry
│   │   ├── advisory.vr             — SecurityAdvisory
│   │   └── errors.vr               — domain error types
│   │
│   ├── persistence/                — storage layer (§6)
│   │   ├── mod.vr
│   │   ├── package_repository.vr   — Postgres queries (sql# meta-fn)
│   │   ├── version_repository.vr
│   │   ├── user_repository.vr
│   │   ├── token_repository.vr
│   │   ├── owner_repository.vr
│   │   ├── sumdb_repository.vr
│   │   ├── advisory_repository.vr
│   │   └── object_store.vr         — S3 wrapper
│   │
│   ├── services/                   — business logic (§7)
│   │   ├── mod.vr
│   │   ├── publish_service.vr
│   │   ├── search_service.vr
│   │   ├── sumdb_service.vr
│   │   ├── auth_service.vr
│   │   └── provenance_service.vr
│   │
│   ├── http/                       — HTTP layer (§8)
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
│   │   │   └── health.vr
│   │   └── error_response.vr
│   │
│   └── observability/
│       ├── mod.vr
│       ├── metrics.vr
│       └── tracing.vr
│
└── tests/
    ├── integration/
    │   ├── publish_test.vr
    │   ├── resolve_test.vr
    │   ├── sumdb_test.vr
    │   ├── search_test.vr
    │   ├── auth_test.vr
    │   └── advisory_test.vr
    └── unit/
        ├── publish_service_test.vr
        ├── search_query_test.vr
        └── ...
```

### 14.2 Refactor map (old → new)

| Old path                                       | Action                                |
|-----------------------------------------------|---------------------------------------|
| `src/main.vr`                                  | Refactor against new spec             |
| `src/config.vr`, `src/server/config.vr`        | Merge into `src/config.vr`            |
| `src/server/router.vr`                         | Move to `src/http/router.vr`          |
| `src/server/mod.vr`                            | Move to `src/http/mod.vr`             |
| `src/middleware/*`                             | Move to `src/http/middleware.vr`      |
| `src/handlers/*`                               | Move to `src/http/handlers/`          |
| `src/handlers/packages_with_repositories.vr`   | DELETE (premature factoring)          |
| `src/services/*`                               | Mostly preserved; refactor on stdlib  |
| `src/services/concurrency_service.vr`          | DELETE (use `core.net.weft.backpressure`) |
| `src/services/timing_service.vr`               | DELETE (use `core.time`)              |
| `src/services/security_service.vr`             | DELETE (use `core.security`)          |
| `src/services/checksum_service.vr`             | DELETE (use `core.security.hash`)     |
| `src/services/artifact_service.vr`             | DELETE (use `core.archive`)           |
| `src/services/validation_service*.vr`          | Replace with refinement-typed domain  |
| `src/services/webhook_service.vr`              | Preserve, refactor                    |
| `src/contexts/*`                               | DELETE (use weft `using` clauses)     |
| `src/converters/*`                             | DELETE (refinement types eliminate)   |
| `src/dto/*`                                    | DELETE (Json<T> extractor handles)    |
| `src/domain/repositories/*`                    | Move to `src/persistence/`            |
| `src/domain/refinements.vr`                    | DELETE (refinement types in domain)   |
| `src/domain/semver_constraint.vr`              | DELETE (use `core.base.semver_constraint`) |
| `src/domain/checksum.vr`                       | DELETE (use `Hex64` refinement)       |
| `src/domain/validation.vr`                     | DELETE (refinement types)             |
| `src/domain/webhook.vr`                        | Move to webhook subsystem             |
| `src/infrastructure/postgres/*`                | Move to `src/persistence/`            |
| `src/infrastructure/providers/*`               | DELETE (use stdlib pools directly)    |
| `src/resilience/*`                             | DELETE (use `core.net.weft` resilience) |
| `tests/*`                                      | Refactor against new types            |

Net result: ~130 files → ~50 files. The deletions are real:
duplicated stdlib facilities are replaced by stdlib calls.

### 14.3 Pending stdlib (Phase 2)

* `core.security.oidc` (G6)
* `core.security.provenance` (G7)
* `core.security.spdx` (SpdxExpression refinement)
* `core.security.malware_patterns` (Phase-4 security analysis)
* `core.text.email`, `core.text.url::Url`
* `core.cog.archive` (Verum-side `.vbca` reader — G5/archive)
* `core.cog.sign` (G5/sign)
* `core.cog.resolve` (pubgrub-style resolver — G5/resolve)
* `core.cache.redis`, `core.search.meilisearch`, `core.storage.s3`

Each of these is tracked as a separate stdlib task. Until they land,
the corresponding services are stubbed at the integration boundary.

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
region = "us-west-2"
bucket = "verum-registry-prod"
access_key_id = "..."
secret_access_key = "..."

[redis]
url = "redis://localhost:6379/0"

[meilisearch]
url = "https://search.internal:7700"
api_key = "..."

[sumdb]
signing_key = "/etc/verum-registry/sumdb-ed25519.seed"

[oidc.providers.github]
issuer = "https://token.actions.githubusercontent.com"
audience = "https://vcogs.io"
```

## Appendix B — Glossary

| Term                | Meaning                                                  |
|---------------------|----------------------------------------------------------|
| **Cog**             | A Verum package — source + manifest + metadata.          |
| **Manifest**        | The `verum.toml` file at the cog root.                   |
| **Sumdb**           | Transparency log of all published checksums.             |
| **STH**             | Signed Tree Head — Ed25519 commitment to log state.      |
| **Tile**            | RFC 9162 Merkle-tree slice (256 leaves).                 |
| **Anti-pattern**    | One of 40 architectural defects (`AP-001..AP-040`).      |
| **Lifecycle**       | CVE seven-symbol status (T / D / C / P / H / I / ✗).     |
| **Trusted publishing** | OIDC-flow-authenticated publish from CI/CD.           |
| **Yank**            | Hide a version from new resolutions; existing locks ok.  |
| **Provenance**      | SLSA / in-toto attestation of build origin.              |

## Appendix C — Compatibility table

| Spec version | Registry implementation       | Verum stdlib   | CVE-architecture |
|--------------|-------------------------------|----------------|------------------|
| v2.0 (this)  | `registry@>=2.0`              | `core@>=v0.4`  | v0.4             |
| v1.0         | `registry@<2.0` (deprecated)  | `core@<=v0.3`  | v0.3             |

---

*End of specification.*
