# Verum Registry Specification

## A Reference Implementation for Industrial-Grade Package Distribution

---

**Version**: 1.0.0
**Status**: Draft
**Authors**: Verum Language Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Design Philosophy](#2-design-philosophy)
3. [Architecture Overview](#3-architecture-overview)
4. [Backend: Reference Verum Server Application](#4-backend-reference-verum-server-application)
5. [Frontend: SvelteKit Web Application](#5-frontend-sveltekit-web-application)
6. [API Specification](#6-api-specification)
7. [Security Architecture](#7-security-architecture)
8. [Data Model](#8-data-model)
9. [Supply Chain Security](#9-supply-chain-security)
10. [Developer Experience](#10-developer-experience)
11. [Operational Excellence](#11-operational-excellence)
12. [Implementation Roadmap](#12-implementation-roadmap)

---

## 1. Executive Summary

### 1.1 Vision

The Verum Registry (`packages.vr.lang`) is a **minimalist, verification-aware package distribution system** that serves as both:

1. **The official Verum package registry** - production infrastructure for the ecosystem
2. **A reference implementation** - demonstrating Verum's server-side capabilities

### 1.2 Key Differentiators

| Feature | Verum Registry | Other Registries |
|---------|----------------|------------------|
| **Source-based publishing** | Publish `.vr` source, registry compiles | Publish pre-built artifacts |
| **Verification portfolio** | Proofs, CBGR profiles, cost annotations | Code only |
| **Checksum database** | Go-style transparent log, separate from storage | Inline checksums |
| **Trusted publishing** | OIDC from CI/CD, no long-lived tokens | API tokens (often leaked) |
| **Proactive security** | Pre-publish typosquatting, malware scanning | Reactive detection |
| **Zero build complexity** | `verum publish` - that's it | Build scripts, CI configuration |
| **Auto documentation** | Generated from doc comments | External tools required |

### 1.3 Design Principles

```
1. SEMANTIC HONESTY    - All costs visible, no hidden magic
2. SECURITY BY DEFAULT - Verification separated from distribution
3. DEVELOPER FIRST     - Zero configuration, zero build steps
4. MINIMALISM          - Fewest moving parts that achieve all goals
5. VERUM SHOWCASE      - Demonstrate language capabilities in production
```

---

## 2. Design Philosophy

### 2.1 Lessons from Other Registries

**What We Adopt:**
- Go's **checksum database architecture** (separation of verification and distribution)
- JSR's **source-based publishing** (registry handles compilation)
- crates.io's **rapid incident response** (hours, not days)
- npm's **scoped namespaces** (@org/package)
- Elm's **semver enforcement** (API diff on publish)

**What We Avoid:**
- npm's **microservice authorization gaps** (single auth layer)
- PyPI's **3-year malware survival** (pre-publish scanning)
- crates.io's **flat namespace** (typosquatting)
- npm's **timing attacks** (privacy-preserving design)
- All registries' **reactive security** (proactive detection)

### 2.2 Minimalism Criteria

Every feature must pass this test:

```
Is this feature:
  1. Essential for package distribution? OR
  2. Essential for security? OR
  3. Uniquely valuable for Verum's verification story?

If NO to all three → Do not include.
```

### 2.3 Reference Application Goals

The backend demonstrates:

1. **Context System** - Two-level DI (static + dynamic)
2. **Async/Await** - Non-blocking I/O with structured concurrency
3. **Refinement Types** - Compile-time validation of invariants
4. **CBGR Memory Safety** - Zero-cost abstractions in practice
5. **Error Handling** - Five-level defense model
6. **Observability** - Structured logging, metrics, tracing

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VERUM REGISTRY ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────┐    ┌────────────────────────────────────┐  │
│  │   SvelteKit Frontend   │◄──►│     Verum API Server (Verum)       │  │
│  │   (packages.vr.lang)│    │     (api.packages.vr.lang)      │  │
│  │                        │    │                                     │  │
│  │   - Package browser    │    │   ┌─────────────────────────────┐  │  │
│  │   - Documentation      │    │   │      Context Providers       │  │  │
│  │   - Search             │    │   │  ┌────────┐  ┌──────────┐   │  │  │
│  │   - User dashboard     │    │   │  │Database│  │  Storage │   │  │  │
│  │   - Publish wizard     │    │   │  └────────┘  └──────────┘   │  │  │
│  └────────────────────────┘    │   │  ┌────────┐  ┌──────────┐   │  │  │
│                                │   │  │ Search │  │  Metrics │   │  │  │
│  ┌────────────────────────┐    │   │  └────────┘  └──────────┘   │  │  │
│  │     verum CLI          │◄──►│   └─────────────────────────────┘  │  │
│  │  (verum add, publish)  │    │                                     │  │
│  └────────────────────────┘    │   Handlers:                         │  │
│                                │   - GET  /packages/:scope/:name     │  │
│                                │   - POST /packages/publish          │  │
│                                │   - GET  /search                    │  │
│                                └────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    CHECKSUM DATABASE (sumdb)                       │  │
│  │                    (sumdb.vr.lang)                              │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────────────────────────────────────────┐ │  │
│  │  │   Transparent Log (Merkle Tree)                              │ │  │
│  │  │   - Append-only                                              │ │  │
│  │  │   - Cryptographically signed                                 │ │  │
│  │  │   - Gossip protocol for auditing                             │ │  │
│  │  │   - Separate from package storage                            │ │  │
│  │  └──────────────────────────────────────────────────────────────┘ │  │
│  │                                                                    │  │
│  │  GET /lookup/@scope/name@version → checksum                       │  │
│  │  GET /latest → tree head                                          │  │
│  │  GET /tile/:level/:index → Merkle tile                            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      STORAGE LAYER                                 │  │
│  │                                                                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │  │
│  │  │ PostgreSQL  │  │     S3      │  │    Redis    │  │ MeiliS.  │ │  │
│  │  │  Metadata   │  │  Packages   │  │    Cache    │  │  Search  │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                         CDN EDGE                                   │  │
│  │                   (Cloudflare / Fastly)                           │  │
│  │                                                                    │  │
│  │  - Immutable package caching (1 year TTL)                         │  │
│  │  - Documentation caching                                          │  │
│  │  - Global distribution                                            │  │
│  │  - DDoS protection                                                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibilities

| Component | Responsibility | Technology |
|-----------|----------------|------------|
| **API Server** | Package operations, auth, publish | Verum (reference impl) |
| **Frontend** | User interface, docs browser | SvelteKit |
| **Sumdb** | Checksum verification, transparency | Verum (stateless) |
| **PostgreSQL** | Package metadata, users, versions | PostgreSQL 17 |
| **S3** | Package source archives, artifacts | S3-compatible |
| **Redis** | Session cache, rate limiting | Redis 7 |
| **MeiliSearch** | Full-text search | MeiliSearch |
| **CDN** | Static content, global delivery | Cloudflare |

### 3.3 Request Flow

```
Developer                    Registry                         Storage
    │                           │                                │
    │  verum publish            │                                │
    │──────────────────────────►│                                │
    │                           │                                │
    │                    ┌──────┴──────┐                         │
    │                    │ 1. Validate │                         │
    │                    │    - OIDC token                       │
    │                    │    - Package name                     │
    │                    │    - Semver diff                      │
    │                    │    - Typosquatting                    │
    │                    │    - Malware scan                     │
    │                    └──────┬──────┘                         │
    │                           │                                │
    │                    ┌──────┴──────┐                         │
    │                    │ 2. Process  │                         │
    │                    │    - Parse source                     │
    │                    │    - Generate docs                    │
    │                    │    - Extract CBGR profile             │
    │                    │    - Compile artifacts                │
    │                    └──────┬──────┘                         │
    │                           │                                │
    │                           │  Store package                 │
    │                           │───────────────────────────────►│
    │                           │                                │
    │                    ┌──────┴──────┐                         │
    │                    │ 3. Register │                         │
    │                    │    - Add to sumdb                     │
    │                    │    - Update search index              │
    │                    │    - Notify dependents                │
    │                    └──────┬──────┘                         │
    │                           │                                │
    │  ◄──Success───────────────│                                │
    │                           │                                │
```

---

## 4. Backend: Reference Verum Server Application

### 4.1 Project Structure

```
registry/
├── verum.toml                    # Package manifest
├── src/
│   ├── main.vr                  # Entry point
│   ├── config.vr                # Configuration loading
│   │
│   ├── server/                   # HTTP server layer
│   │   ├── mod.vr               # Server module
│   │   ├── router.vr            # Route definitions
│   │   └── middleware.vr        # Auth, logging, rate limit
│   │
│   ├── handlers/                 # Request handlers
│   │   ├── mod.vr
│   │   ├── packages.vr          # Package CRUD
│   │   ├── publish.vr           # Publish pipeline
│   │   ├── search.vr            # Search endpoint
│   │   ├── auth.vr              # Authentication
│   │   └── sumdb.vr             # Checksum database
│   │
│   ├── services/                 # Business logic
│   │   ├── mod.vr
│   │   ├── package_service.vr   # Package operations
│   │   ├── publish_service.vr   # Publish workflow
│   │   ├── search_service.vr    # Search logic
│   │   ├── auth_service.vr      # Auth logic
│   │   └── sumdb_service.vr     # Checksum operations
│   │
│   ├── contexts/                 # Context definitions
│   │   ├── mod.vr
│   │   ├── database.vr          # Database context
│   │   ├── storage.vr           # S3 storage context
│   │   ├── cache.vr             # Redis cache context
│   │   ├── search.vr            # Search engine context
│   │   └── metrics.vr           # Metrics context
│   │
│   ├── domain/                   # Domain types
│   │   ├── mod.vr
│   │   ├── package.vr           # Package entity
│   │   ├── version.vr           # Version entity
│   │   ├── user.vr              # User entity
│   │   └── errors.vr            # Domain errors
│   │
│   └── infrastructure/           # External integrations
│       ├── mod.vr
│       ├── postgres.vr          # PostgreSQL client
│       ├── s3.vr                # S3 client
│       ├── redis.vr             # Redis client
│       └── meilisearch.vr       # Search client
│
├── tests/                        # Test suite
│   ├── integration/
│   │   ├── publish_test.vr
│   │   ├── search_test.vr
│   │   └── sumdb_test.vr
│   └── unit/
│       ├── version_test.vr
│       └── semver_test.vr
│
└── benches/                      # Performance benchmarks
    ├── publish_bench.vr
    └── search_bench.vr
```

### 4.2 Package Manifest (verum.toml)

```toml
[package]
name = "verum-registry"
version = "1.0.0"
edition = "2025"
authors = ["Verum Language Team <team@verum.lang>"]
description = "Official Verum package registry - reference server implementation"
license = "MIT OR Apache-2.0"
repository = "https://github.com/verum-lang/registry"

# Language profile: application (safe, async-first)
[language]
profile = "application"

[language.verification]
level = "runtime"               # Runtime checks for all refinements
timeout = 5000                  # 5s per function

# Dependencies
[dependencies]
verum-std = "1.0"               # Standard library

# Build profiles
[profile.dev]
tier = 1                        # JIT for fast iteration
verification = "runtime"
opt-level = 0
debug = true

[profile.release]
tier = 3                        # AOT for production
verification = "runtime"        # Keep runtime checks
opt-level = 3
lto = true

# Context requirements
[context]
requires = ["Database", "Storage", "Cache", "Search", "Logger", "Metrics"]

[[context.provides]]
name = "PackageRegistry"
operations = ["publish", "get", "search", "list_versions"]

# Distribution
[distribution]
include_source = true

[distribution.tier2]
binaries = true
platforms = ["x86_64-linux", "aarch64-linux", "x86_64-macos", "aarch64-macos"]
```

### 4.3 Entry Point (src/main.vr)

```verum
//! Verum Registry - Reference Server Implementation
//!
//! Demonstrates Verum's server-side capabilities:
//! - Two-level context system (static DI + dynamic contexts)
//! - Async/await with structured concurrency
//! - Refinement types for compile-time validation
//! - CBGR memory safety with ~15ns overhead
//! - Five-level error handling

module main

use std.server.{Server, ServerConfig}
use std.net.http.{Request, Response}
use std.env

use crate.config.Config
use crate.server.{create_router, create_middleware_chain}
use crate.contexts.{
    DatabaseProvider,
    StorageProvider,
    CacheProvider,
    SearchProvider,
    MetricsProvider,
}

/// Application entry point
///
/// # Context Requirements
/// None - this is the root that provides all contexts
///
/// # Properties
/// {Async, IO, Fallible}
async fn main() -> Result<()> {
    // 1. Load configuration (environment-based, 12-factor)
    let config = Config.from_env()?

    // 2. Initialize infrastructure (Level 1: Static DI)
    let db = DatabaseProvider.connect(&config.database_url).await?
    let storage = StorageProvider.connect(&config.s3_config).await?
    let cache = CacheProvider.connect(&config.redis_url).await?
    let search = SearchProvider.connect(&config.meilisearch_url).await?
    let metrics = MetricsProvider.new(&config.metrics_config)

    // 3. Create server with context provision (Level 2: Dynamic Contexts)
    let router = create_router()
    let middleware = create_middleware_chain(&config)

    let server = Server.new(&config.bind_address)
        .with_router(router)
        .with_middleware(middleware)
        .with_graceful_shutdown(config.shutdown_timeout)

    // 4. Start server with all contexts provided
    server.on_request(async |req: Request| {
        // Provide contexts for this request scope
        provide Database = &db
        provide Storage = &storage
        provide Cache = &cache
        provide Search = &search
        provide Metrics = &metrics
        provide Logger = Logger.with_request_id(req.id)

        router.handle(req).await
    }).await?

    // 5. Listen and serve
    Logger.log(Level.Info, f"Registry listening on {config.bind_address}")
    server.listen().await
}
```

### 4.4 Context Definitions (src/contexts/database.vr)

```verum
//! Database context - PostgreSQL connection management
//!
//! Demonstrates:
//! - Context protocol definition
//! - Async database operations
//! - Connection pooling
//! - SQL injection prevention via sql"..." literals

module contexts.database

use std.database.{Connection, Pool, PoolConfig, Row, Rows}
use std.database.postgres.PostgresPool

use crate.domain.errors.DatabaseError

/// Database context protocol
///
/// All database operations go through this context,
/// enabling:
/// - Dependency injection for testing
/// - Connection pooling
/// - Transaction management
/// - Query metrics
context async Database {
    /// Execute a query returning rows
    async fn query(sql: SqlQuery) -> Result<Rows, DatabaseError>

    /// Execute a query returning single row
    async fn query_one(sql: SqlQuery) -> Result<Row, DatabaseError>

    /// Execute a statement (INSERT, UPDATE, DELETE)
    async fn execute(sql: SqlQuery) -> Result<Int{>= 0}, DatabaseError>

    /// Begin a transaction
    async fn transaction<T>(
        f: async fn() -> Result<T, DatabaseError>
    ) -> Result<T, DatabaseError>
}

/// Production database provider
///
/// Uses connection pooling with health checks.
///
/// # CBGR Profile
/// - Reference overhead: ~15ns per query call
/// - Connection pool access: ~5ns (optimized path)
pub type DatabaseProvider is {
    pool: Shared<PostgresPool>,
}

impl DatabaseProvider {
    /// Connect to PostgreSQL with connection pooling
    ///
    /// # Configuration
    /// - Min connections: 5
    /// - Max connections: 20
    /// - Connection timeout: 5s
    /// - Idle timeout: 10min
    pub async fn connect(url: &Text) -> Result<Self, DatabaseError> {
        let config = PoolConfig {
            min_connections: 5,
            max_connections: 20,
            connect_timeout: Duration.seconds(5),
            idle_timeout: Duration.minutes(10),
            health_check_interval: Duration.seconds(30),
        }

        let pool = PostgresPool.connect(url, config).await?
        Ok(Self { pool: Shared.new(pool) })
    }
}

impl Database for DatabaseProvider {
    async fn query(sql: SqlQuery) -> Result<Rows, DatabaseError> {
        let conn = self.pool.acquire().await?
        conn.query(sql).await.map_err(DatabaseError.from)
    }

    async fn query_one(sql: SqlQuery) -> Result<Row, DatabaseError> {
        let conn = self.pool.acquire().await?
        conn.query_one(sql).await.map_err(DatabaseError.from)
    }

    async fn execute(sql: SqlQuery) -> Result<Int{>= 0}, DatabaseError> {
        let conn = self.pool.acquire().await?
        conn.execute(sql).await.map_err(DatabaseError.from)
    }

    async fn transaction<T>(
        f: async fn() -> Result<T, DatabaseError>
    ) -> Result<T, DatabaseError> {
        let conn = self.pool.acquire().await?
        let tx = conn.begin().await?

        match f().await {
            Ok(result) => {
                tx.commit().await?
                Ok(result)
            }
            Err(e) => {
                tx.rollback().await?
                Err(e)
            }
        }
    }
}

/// Mock database for testing
///
/// Allows unit tests without PostgreSQL.
pub type MockDatabase is {
    responses: Shared<Map<Text, Rows>>,
}

impl MockDatabase {
    pub fn new() -> Self {
        Self { responses: Shared.new(Map.new()) }
    }

    pub fn expect_query(&self, sql_pattern: &Text, response: Rows) {
        self.responses.write().insert(sql_pattern.clone(), response)
    }
}

impl Database for MockDatabase {
    async fn query(sql: SqlQuery) -> Result<Rows, DatabaseError> {
        let responses = self.responses.read()
        for (pattern, rows) in responses.iter() {
            if sql.to_text().contains(pattern) {
                return Ok(rows.clone())
            }
        }
        Err(DatabaseError.NotFound("No mock response configured"))
    }

    // ... other methods ...
}
```

### 4.5 Domain Types (src/domain/package.vr)

```verum
//! Package domain model
//!
//! Demonstrates:
//! - Refinement types for domain invariants
//! - Semantic types (Text, List, Map, Maybe)
//! - Derive macros for serialization
//! - Documentation with cost annotations

module domain.package

use std.time.DateTime
use std.crypto.Hash

/// Package scope (namespace)
///
/// # Format
/// - `@org/name` for organization packages
/// - `@user/name` for user packages
/// - `name` for global packages (restricted)
///
/// # Validation
/// - Scope: 1-64 chars, lowercase alphanumeric + hyphen
/// - Name: 1-64 chars, lowercase alphanumeric + hyphen + underscore
@derive(Serialize, Deserialize, Clone, Eq, Hash)
pub type PackageScope is Text {
    // Refinement: valid scope format
    where self.matches(r"^(@[a-z0-9][a-z0-9-]{0,63}/)?[a-z][a-z0-9_-]{0,63}$")
}

/// Semantic version with full SemVer 2.0 compliance
///
/// # Examples
/// - `1.0.0`
/// - `1.0.0-beta.1`
/// - `1.0.0+build.123`
@derive(Serialize, Deserialize, Clone, Ord, Eq, Hash)
pub type SemVer is {
    major: Int{>= 0},
    minor: Int{>= 0},
    patch: Int{>= 0},
    prerelease: Maybe<Text>,
    build_metadata: Maybe<Text>,
}

impl SemVer {
    /// Parse version string
    ///
    /// # Cost
    /// - Time: O(n) where n = string length
    /// - CBGR: ~15ns (single allocation)
    pub fn parse(s: &Text) -> Result<Self, VersionError> {
        // Implementation uses regex + validation
        // ...
    }

    /// Check if this version satisfies a requirement
    pub fn satisfies(req: &VersionReq) -> Bool {
        req.matches(self)
    }

    /// Compare versions (ignoring build metadata per SemVer spec)
    pub fn cmp(&self, other: &Self) -> Ordering {
        (self.major, self.minor, self.patch, &self.prerelease)
            .cmp(&(other.major, other.minor, other.patch, &other.prerelease))
    }
}

/// Package metadata
///
/// Represents a package in the registry.
///
/// # Invariants
/// - Name matches scope format
/// - At least one version published
/// - Created before or equal to updated
@derive(Serialize, Deserialize, Clone)
pub type Package is {
    /// Unique package identifier (scope/name)
    id: PackageScope,

    /// Human-readable description
    description: Text{len <= 500},

    /// Package homepage URL
    homepage: Maybe<Url>,

    /// Source repository URL
    repository: Maybe<Url>,

    /// SPDX license expression
    license: Text,

    /// Search keywords (max 5)
    keywords: List<Text>{len <= 5},

    /// Latest stable version
    latest_version: SemVer,

    /// Total download count
    downloads: Int{>= 0},

    /// Package score (0-100)
    score: Int{>= 0, <= 100},

    /// Creation timestamp
    created_at: DateTime,

    /// Last update timestamp
    updated_at: DateTime,

    /// Owner user IDs
    owners: List<UserId>{len >= 1},
}

/// Package version with all artifacts
///
/// # Artifacts Included
/// - Source code (.vr files)
/// - CBGR profile (performance characteristics)
/// - Generated documentation
/// - Tier-specific binaries (optional)
/// - Verification proofs (if @verify(proof))
@derive(Serialize, Deserialize, Clone)
pub type PackageVersion is {
    /// Parent package
    package_id: PackageScope,

    /// Version number
    version: SemVer,

    /// Verum edition required
    edition: Text,

    /// Language profile used
    language_profile: LanguageProfile,

    /// Dependencies
    dependencies: List<Dependency>,

    /// Development dependencies
    dev_dependencies: List<Dependency>,

    /// Feature flags
    features: Map<Text, List<Text>>,

    /// Default features enabled
    default_features: List<Text>,

    /// SHA-256 checksum of source archive
    checksum: Hash{algorithm == "sha256"},

    /// CBGR overhead profile
    cbgr_profile: CbgrProfile,

    /// Verification level achieved
    verification_level: VerificationLevel,

    /// Publication timestamp
    published_at: DateTime,

    /// Publisher user ID
    published_by: UserId,

    /// Yanked status (hidden from new resolves)
    yanked: Bool,

    /// Yank reason (if yanked)
    yank_reason: Maybe<Text>,
}

/// CBGR performance profile
///
/// Measured on reference hardware, distributed with package.
@derive(Serialize, Deserialize, Clone)
pub type CbgrProfile is {
    /// Average reference check overhead
    average_overhead_ns: Int{>= 0},

    /// 95th percentile overhead
    p95_overhead_ns: Int{>= 0},

    /// 99th percentile overhead
    p99_overhead_ns: Int{>= 0},

    /// Memory overhead percentage vs unsafe
    memory_overhead_percent: Float{>= 0.0},

    /// Hot paths with significant overhead
    hot_paths: List<HotPath>,
}

/// Verification level
@derive(Serialize, Deserialize, Clone, Eq, Ord)
pub enum VerificationLevel {
    /// No verification (@verify(none))
    None,

    /// Runtime checks only (@verify(runtime))
    Runtime,

    /// Static analysis passed (@verify(static))
    Static,

    /// Formal proofs verified (@verify(proof))
    Proof,
}

/// Language profile
@derive(Serialize, Deserialize, Clone, Eq)
pub enum LanguageProfile {
    /// Safe, productive, async-first (default)
    Application,

    /// Unsafe allowed, manual memory
    Systems,

    /// Formal verification, dependent types
    Research,
}

/// Dependency specification
@derive(Serialize, Deserialize, Clone)
pub type Dependency is {
    /// Package identifier
    package: PackageScope,

    /// Version requirement
    version_req: VersionReq,

    /// Required features
    features: List<Text>,

    /// Optional dependency
    optional: Bool,
}
```

### 4.6 Publish Handler (src/handlers/publish.vr)

```verum
//! Package publish handler
//!
//! Demonstrates:
//! - Context-based dependency injection
//! - Async request handling
//! - Multi-stage validation pipeline
//! - Error handling with rich context

module handlers.publish

use std.net.http.{Request, Response, StatusCode}
use std.archive.tar

use crate.domain.{Package, PackageVersion, SemVer, VerificationLevel}
use crate.services.publish_service.PublishService
use crate.domain.errors.{PublishError, ValidationError}

/// Handle package publish request
///
/// # Request
/// - Method: POST
/// - Path: /api/v1/packages/publish
/// - Auth: OIDC token (trusted publishing) or API token
/// - Body: multipart/form-data with source.tar.gz
///
/// # Response
/// - 201 Created: Package published successfully
/// - 400 Bad Request: Validation failed
/// - 401 Unauthorized: Authentication failed
/// - 409 Conflict: Version already exists
/// - 422 Unprocessable Entity: Package invalid
///
/// # Context Requirements
/// using [Database, Storage, Cache, Search, Logger, Metrics, Auth]
///
/// # Properties
/// {Async, IO, Fallible}
@verify(runtime)
pub async fn handle_publish(req: Request) -> Response
    using [Database, Storage, Cache, Search, Logger, Metrics, Auth]
{
    // 1. Authenticate request
    let user = match Auth.authenticate(&req).await {
        Ok(user) => user,
        Err(e) => {
            Logger.log(Level.Warn, f"Auth failed: {e}")
            return Response.json(e).status(StatusCode.Unauthorized)
        }
    }

    Logger.log(Level.Info, f"Publish request from {user.id}")
    Metrics.increment("publish.attempts")

    // 2. Parse multipart request
    let (manifest, source_archive) = match parse_publish_request(&req).await {
        Ok(data) => data,
        Err(e) => {
            Metrics.increment("publish.parse_errors")
            return Response.json(e).status(StatusCode.BadRequest)
        }
    }

    // 3. Run validation pipeline
    let publish_service = PublishService.new()

    match publish_service.publish(user, manifest, source_archive).await {
        Ok(version) => {
            Metrics.increment("publish.success")
            Logger.log(Level.Info, f"Published {version.package_id}@{version.version}")

            Response.json(PublishResponse {
                package: version.package_id,
                version: version.version,
                checksum: version.checksum,
                docs_url: f"https://docs.vr.lang/{version.package_id}/{version.version}",
            }).status(StatusCode.Created)
        }
        Err(PublishError.VersionExists(v)) => {
            Metrics.increment("publish.version_exists")
            Response.json(ErrorResponse {
                error: "version_exists",
                message: f"Version {v} already exists",
            }).status(StatusCode.Conflict)
        }
        Err(PublishError.ValidationFailed(errors)) => {
            Metrics.increment("publish.validation_failed")
            Response.json(ErrorResponse {
                error: "validation_failed",
                details: errors,
            }).status(StatusCode.UnprocessableEntity)
        }
        Err(e) => {
            Metrics.increment("publish.errors")
            Logger.log(Level.Error, f"Publish failed: {e}")
            Response.json(ErrorResponse {
                error: "internal_error",
                message: "Publication failed",
            }).status(StatusCode.InternalServerError)
        }
    }
}

/// Parse multipart publish request
async fn parse_publish_request(req: &Request) -> Result<(Manifest, List<u8>), ParseError> {
    let boundary = req.content_type()
        .and_then(|ct| ct.param("boundary"))
        .ok_or(ParseError.MissingBoundary)?

    let parts = req.body().parse_multipart(boundary).await?

    let manifest_part = parts.get("manifest")
        .ok_or(ParseError.MissingManifest)?
    let source_part = parts.get("source")
        .ok_or(ParseError.MissingSource)?

    let manifest: Manifest = toml.parse(&manifest_part.text()?)?
    let source = source_part.bytes()?

    Ok((manifest, source))
}

/// Publish response
@derive(Serialize)
type PublishResponse is {
    package: PackageScope,
    version: SemVer,
    checksum: Text,
    docs_url: Text,
}

/// Error response
@derive(Serialize)
type ErrorResponse is {
    error: Text,
    message: Maybe<Text>,
    details: Maybe<List<ValidationError>>,
}
```

### 4.7 Publish Service (src/services/publish_service.vr)

```verum
//! Publish service - core publication workflow
//!
//! Demonstrates:
//! - Service layer pattern
//! - Transaction management
//! - Multi-stage validation
//! - Background job spawning

module services.publish_service

use std.crypto.{sha256, ed25519}
use std.archive.tar
use std.async.spawn

use crate.domain.{Package, PackageVersion, User, Manifest}
use crate.domain.errors.PublishError
use crate.services.validation.{
    validate_manifest,
    validate_source,
    check_typosquatting,
    check_malware,
    validate_semver_bump,
}
use crate.services.documentation.generate_docs
use crate.services.cbgr.profile_cbgr

/// Publish service
///
/// Orchestrates the package publication workflow.
pub type PublishService is {}

impl PublishService {
    pub fn new() -> Self {
        Self {}
    }

    /// Publish a new package version
    ///
    /// # Workflow
    /// 1. Pre-publish validation (fast checks)
    /// 2. Content analysis (malware, typosquatting)
    /// 3. Source processing (parse, type-check)
    /// 4. Artifact generation (docs, CBGR profile)
    /// 5. Storage (S3, database)
    /// 6. Post-publish (sumdb, search index)
    ///
    /// # Properties
    /// {Async, IO, Fallible}
    pub async fn publish(
        &self,
        user: User,
        manifest: Manifest,
        source: List<u8>,
    ) -> Result<PackageVersion, PublishError>
        using [Database, Storage, Cache, Search, Logger, Metrics]
    {
        let package_id = manifest.package.name.clone()
        let version = manifest.package.version.clone()

        Logger.log(Level.Debug, f"Starting publish: {package_id}@{version}")

        // ============ PHASE 1: Pre-publish Validation ============
        // Fast checks that can reject early

        // 1.1 Validate manifest structure
        validate_manifest(&manifest)?

        // 1.2 Check user owns package (or package is new)
        self.check_ownership(&user, &package_id).await?

        // 1.3 Check version doesn't exist
        if self.version_exists(&package_id, &version).await? {
            return Err(PublishError.VersionExists(version))
        }

        // 1.4 Validate semver bump (API diff)
        if let Some(latest) = self.get_latest_version(&package_id).await? {
            validate_semver_bump(&latest, &version, &source)?
        }

        // ============ PHASE 2: Security Analysis ============
        // Protect ecosystem from malicious packages

        // 2.1 Typosquatting detection
        if let Some(similar) = check_typosquatting(&package_id).await? {
            Logger.log(Level.Warn, f"Typosquatting alert: {package_id} similar to {similar}")
            return Err(PublishError.TyposquattingDetected(similar))
        }

        // 2.2 Malware scanning (static analysis)
        if let Some(threat) = check_malware(&source).await? {
            Logger.log(Level.Error, f"Malware detected: {threat}")
            Metrics.increment("security.malware_blocked")
            return Err(PublishError.MalwareDetected(threat))
        }

        // ============ PHASE 3: Source Processing ============
        // Parse and validate source code

        // 3.1 Validate source archive
        let source_files = validate_source(&source)?

        // 3.2 Compute checksum
        let checksum = sha256(&source)

        // 3.3 Parse and type-check
        // (This validates the code compiles with the specified language profile)
        let ast = self.parse_source(&source_files, &manifest.language.profile)?

        // ============ PHASE 4: Artifact Generation ============
        // Generate documentation and profiles

        // 4.1 CBGR profile (measure reference overhead)
        let cbgr_profile = profile_cbgr(&ast)?

        // 4.2 Generate documentation
        let docs = generate_docs(&ast, &manifest)?

        // 4.3 Determine verification level
        let verification_level = self.determine_verification_level(&ast, &manifest)

        // ============ PHASE 5: Storage ============
        // Persist everything atomically

        Database.transaction(async || {
            // 5.1 Create package if new
            if !self.package_exists(&package_id).await? {
                self.create_package(&manifest, &user).await?
            }

            // 5.2 Store source archive in S3
            let source_key = f"packages/{package_id}/{version}/source.tar.gz"
            Storage.put(&source_key, &source).await?

            // 5.3 Store documentation
            let docs_key = f"docs/{package_id}/{version}/"
            Storage.put_directory(&docs_key, &docs).await?

            // 5.4 Create version record
            let version_record = PackageVersion {
                package_id: package_id.clone(),
                version: version.clone(),
                edition: manifest.package.edition.clone(),
                language_profile: manifest.language.profile.clone(),
                dependencies: manifest.dependencies.clone(),
                dev_dependencies: manifest.dev_dependencies.clone(),
                features: manifest.features.clone(),
                default_features: manifest.features.get("default").unwrap_or(List.new()),
                checksum: checksum.to_hex(),
                cbgr_profile,
                verification_level,
                published_at: DateTime.now(),
                published_by: user.id.clone(),
                yanked: false,
                yank_reason: Maybe.None,
            }

            self.insert_version(&version_record).await?

            // 5.5 Update package latest version
            self.update_latest_version(&package_id, &version).await?

            Ok(version_record)
        }).await?

        // ============ PHASE 6: Post-Publish ============
        // Non-transactional background tasks

        let version_record = version_record.clone()

        // 6.1 Add to checksum database (spawn in background)
        spawn(async move {
            if let Err(e) = self.add_to_sumdb(&package_id, &version, &checksum).await {
                Logger.log(Level.Error, f"Failed to update sumdb: {e}")
            }
        })

        // 6.2 Update search index (spawn in background)
        spawn(async move {
            if let Err(e) = Search.index_package(&version_record).await {
                Logger.log(Level.Error, f"Failed to update search index: {e}")
            }
        })

        // 6.3 Invalidate cache
        Cache.invalidate(&f"package:{package_id}").await?

        Ok(version_record)
    }

    // Private helper methods...

    async fn check_ownership(&self, user: &User, package_id: &PackageScope)
        -> Result<(), PublishError>
        using [Database]
    {
        let row = Database.query_one(sql"
            SELECT 1 FROM package_owners
            WHERE package_id = {package_id} AND user_id = {user.id}
        ").await

        match row {
            Ok(_) => Ok(()),
            Err(DatabaseError.NotFound(_)) => {
                // Package doesn't exist yet, ownership will be created
                if self.package_exists(package_id).await? {
                    Err(PublishError.NotOwner)
                } else {
                    Ok(())
                }
            }
            Err(e) => Err(e.into())
        }
    }

    async fn version_exists(&self, package_id: &PackageScope, version: &SemVer)
        -> Result<Bool, PublishError>
        using [Database]
    {
        let count = Database.query_one(sql"
            SELECT COUNT(*) as count FROM versions
            WHERE package_id = {package_id} AND version = {version.to_text()}
        ").await?

        Ok(count.get::<Int>("count")? > 0)
    }

    async fn add_to_sumdb(
        &self,
        package_id: &PackageScope,
        version: &SemVer,
        checksum: &Hash
    ) -> Result<(), SumdbError>
        using [Sumdb]
    {
        Sumdb.append(SumdbEntry {
            package: package_id.clone(),
            version: version.clone(),
            checksum: checksum.clone(),
            timestamp: DateTime.now(),
        }).await
    }
}
```

### 4.8 Checksum Database (src/handlers/sumdb.vr)

```verum
//! Checksum Database (sumdb) - Go-style transparent log
//!
//! Demonstrates:
//! - Cryptographic transparency (Merkle tree)
//! - Separation of verification from distribution
//! - Cache-friendly API design
//!
//! # Architecture
//! The sumdb is SEPARATE from the main registry database.
//! It provides cryptographic proof that a package+version
//! corresponds to a specific checksum.
//!
//! Clients can use ANY mirror/CDN but verify against sumdb.

module handlers.sumdb

use std.net.http.{Request, Response, StatusCode}
use std.crypto.{sha256, ed25519}
use std.encoding.base64

/// Sumdb entry in the transparent log
@derive(Serialize, Deserialize, Clone)
pub type SumdbEntry is {
    /// Package identifier
    package: PackageScope,

    /// Version
    version: SemVer,

    /// SHA-256 checksum of source archive
    checksum: Text{len == 64},  // Hex-encoded SHA-256

    /// Timestamp of entry
    timestamp: DateTime,
}

/// Merkle tree node
@derive(Serialize, Deserialize, Clone)
type TreeNode is {
    hash: Text,
    left: Maybe<Heap<TreeNode>>,
    right: Maybe<Heap<TreeNode>>,
}

/// Signed tree head
@derive(Serialize, Deserialize, Clone)
pub type TreeHead is {
    /// Number of entries in the tree
    tree_size: Int{>= 0},

    /// Root hash
    root_hash: Text,

    /// Timestamp
    timestamp: DateTime,

    /// Ed25519 signature over (tree_size || root_hash || timestamp)
    signature: Text,
}

/// Handle lookup request
///
/// GET /sumdb/lookup/@scope/name@version
///
/// Returns the checksum for a specific package version.
/// Clients MUST verify this checksum after downloading from ANY source.
///
/// # Cache
/// - Cache-Control: public, max-age=31536000, immutable
/// - Checksums never change for a given version
pub async fn handle_lookup(req: Request) -> Response
    using [Database, Cache, Metrics]
{
    let package = req.param("scope_name")?
    let version = req.param("version")?

    Metrics.increment("sumdb.lookups")

    // Try cache first
    let cache_key = f"sumdb:{package}@{version}"
    if let Some(entry) = Cache.get::<SumdbEntry>(&cache_key).await? {
        return Response.json(entry)
            .header("Cache-Control", "public, max-age=31536000, immutable")
    }

    // Query database
    let row = match Database.query_one(sql"
        SELECT package, version, checksum, timestamp
        FROM sumdb_entries
        WHERE package = {package} AND version = {version}
    ").await {
        Ok(row) => row,
        Err(DatabaseError.NotFound(_)) => {
            return Response.new()
                .status(StatusCode.NotFound)
                .body("NOTFOUND")
        }
        Err(e) => {
            return Response.new()
                .status(StatusCode.InternalServerError)
        }
    }

    let entry = SumdbEntry {
        package: row.get("package")?,
        version: row.get("version")?,
        checksum: row.get("checksum")?,
        timestamp: row.get("timestamp")?,
    }

    // Cache for future lookups
    Cache.set(&cache_key, &entry, Duration.days(365)).await?

    Response.json(entry)
        .header("Cache-Control", "public, max-age=31536000, immutable")
}

/// Handle tree head request
///
/// GET /sumdb/latest
///
/// Returns the current tree head (signed).
/// Clients use this to verify log consistency.
///
/// # Cache
/// - Cache-Control: public, max-age=60
/// - Tree head updates with each new entry
pub async fn handle_latest(req: Request) -> Response
    using [Database, Metrics]
{
    Metrics.increment("sumdb.latest")

    let row = Database.query_one(sql"
        SELECT tree_size, root_hash, timestamp, signature
        FROM sumdb_tree_head
        ORDER BY tree_size DESC
        LIMIT 1
    ").await?

    let head = TreeHead {
        tree_size: row.get("tree_size")?,
        root_hash: row.get("root_hash")?,
        timestamp: row.get("timestamp")?,
        signature: row.get("signature")?,
    }

    Response.json(head)
        .header("Cache-Control", "public, max-age=60")
}

/// Handle tile request
///
/// GET /sumdb/tile/:level/:index
///
/// Returns a Merkle tree tile for proof verification.
/// Tiles are 256 entries each, enabling efficient proofs.
///
/// # Cache
/// - Cache-Control: public, max-age=31536000, immutable
/// - Tiles are append-only, never change
pub async fn handle_tile(req: Request) -> Response
    using [Database, Cache, Metrics]
{
    let level: Int = req.param("level")?.parse()?
    let index: Int = req.param("index")?.parse()?

    Metrics.increment("sumdb.tiles")

    let cache_key = f"sumdb:tile:{level}:{index}"
    if let Some(tile) = Cache.get::<List<Text>>(&cache_key).await? {
        return Response.json(tile)
            .header("Cache-Control", "public, max-age=31536000, immutable")
    }

    // Compute tile hashes
    let start = index * 256
    let end = start + 256

    let rows = Database.query(sql"
        SELECT hash FROM sumdb_entries
        WHERE entry_id >= {start} AND entry_id < {end}
        ORDER BY entry_id
    ").await?

    let hashes: List<Text> = rows.iter().map(|r| r.get("hash")).collect()?

    Cache.set(&cache_key, &hashes, Duration.days(365)).await?

    Response.json(hashes)
        .header("Cache-Control", "public, max-age=31536000, immutable")
}

/// Sumdb context protocol
context async Sumdb {
    /// Append entry to the transparent log
    async fn append(entry: SumdbEntry) -> Result<Int, SumdbError>

    /// Verify an entry exists with given checksum
    async fn verify(package: &PackageScope, version: &SemVer, checksum: &Text)
        -> Result<Bool, SumdbError>
}

/// Sumdb service implementation
pub type SumdbService is {
    signing_key: ed25519.PrivateKey,
}

impl Sumdb for SumdbService {
    async fn append(entry: SumdbEntry) -> Result<Int, SumdbError>
        using [Database]
    {
        // 1. Compute entry hash
        let entry_hash = sha256(&entry.to_bytes())

        // 2. Insert into log (transactional)
        let entry_id = Database.transaction(async || {
            // Insert entry
            let result = Database.execute(sql"
                INSERT INTO sumdb_entries (package, version, checksum, timestamp, hash)
                VALUES ({entry.package}, {entry.version}, {entry.checksum}, {entry.timestamp}, {entry_hash})
                RETURNING entry_id
            ").await?

            let entry_id = result.get::<Int>("entry_id")?

            // Update Merkle tree
            self.update_tree(entry_id, &entry_hash).await?

            Ok(entry_id)
        }).await?

        Ok(entry_id)
    }

    async fn verify(package: &PackageScope, version: &SemVer, checksum: &Text)
        -> Result<Bool, SumdbError>
        using [Database]
    {
        let row = Database.query_one(sql"
            SELECT checksum FROM sumdb_entries
            WHERE package = {package} AND version = {version}
        ").await?

        Ok(row.get::<Text>("checksum")? == *checksum)
    }
}
```

### 4.9 Router Configuration (src/server/router.vr)

```verum
//! Route definitions
//!
//! Demonstrates:
//! - Declarative routing
//! - Path parameter extraction
//! - Method-based dispatch
//! - Route grouping

module server.router

use std.server.{Router, Route}

use crate.handlers.{
    packages::{handle_get_package, handle_list_versions, handle_get_version},
    publish::handle_publish,
    search::handle_search,
    auth::{handle_login, handle_oidc_callback, handle_token_refresh},
    sumdb::{handle_lookup, handle_latest, handle_tile},
    health::handle_health,
}

/// Create the application router
///
/// # Route Structure
/// ```
/// /api/v1/
///   ├── packages/
///   │   ├── GET  /:scope/:name           - Get package info
///   │   ├── GET  /:scope/:name/versions  - List versions
///   │   ├── GET  /:scope/:name/:version  - Get specific version
///   │   └── POST /publish                - Publish package
///   ├── search
///   │   └── GET  ?q=query                - Search packages
///   └── auth/
///       ├── POST /login                  - Login (API token)
///       ├── POST /oidc/callback          - OIDC callback
///       └── POST /token/refresh          - Refresh token
///
/// /sumdb/
///   ├── GET  /lookup/:scope_name@:version - Lookup checksum
///   ├── GET  /latest                      - Tree head
///   └── GET  /tile/:level/:index          - Merkle tile
///
/// /health
///   └── GET  /                            - Health check
/// ```
pub fn create_router() -> Router {
    let mut router = Router.new()

    // ========== Package API ==========
    router.group("/api/v1", |api| {
        // Package routes
        api.group("/packages", |packages| {
            packages.get("/:scope/:name", handle_get_package)
            packages.get("/:scope/:name/versions", handle_list_versions)
            packages.get("/:scope/:name/:version", handle_get_version)
            packages.post("/publish", handle_publish)
        })

        // Search
        api.get("/search", handle_search)

        // Auth
        api.group("/auth", |auth| {
            auth.post("/login", handle_login)
            auth.post("/oidc/callback", handle_oidc_callback)
            auth.post("/token/refresh", handle_token_refresh)
        })
    })

    // ========== Checksum Database ==========
    router.group("/sumdb", |sumdb| {
        sumdb.get("/lookup/:scope_name@:version", handle_lookup)
        sumdb.get("/latest", handle_latest)
        sumdb.get("/tile/:level/:index", handle_tile)
    })

    // ========== Health ==========
    router.get("/health", handle_health)

    router
}
```

### 4.10 Middleware Configuration (src/server/middleware.vr)

```verum
//! Middleware chain configuration
//!
//! Demonstrates:
//! - Request/response interception
//! - Cross-cutting concerns
//! - Middleware composition

module server.middleware

use std.server.{Middleware, MiddlewareChain, Request, Response}
use std.time.Instant

use crate.config.Config

/// Create the middleware chain
///
/// # Order (outside-in)
/// 1. Tracing (request ID, distributed tracing)
/// 2. Logging (request/response logging)
/// 3. Metrics (latency, status codes)
/// 4. RateLimit (protect from abuse)
/// 5. CORS (cross-origin requests)
/// 6. Auth (authentication, optional per-route)
pub fn create_middleware_chain(config: &Config) -> MiddlewareChain {
    MiddlewareChain.new()
        .add(TracingMiddleware.new())
        .add(LoggingMiddleware.new())
        .add(MetricsMiddleware.new())
        .add(RateLimitMiddleware.new(&config.rate_limit))
        .add(CorsMiddleware.new(&config.cors))
}

/// Tracing middleware - distributed tracing support
type TracingMiddleware is {}

impl Middleware for TracingMiddleware {
    async fn call(&self, req: Request, next: Next) -> Response {
        // Extract or generate trace ID
        let trace_id = req.header("X-Trace-Id")
            .unwrap_or_else(|| generate_trace_id())

        // Propagate to child contexts
        provide TraceContext = TraceContext { trace_id }

        let response = next.call(req).await

        response.header("X-Trace-Id", &trace_id)
    }
}

/// Logging middleware - structured request/response logging
type LoggingMiddleware is {}

impl Middleware for LoggingMiddleware {
    async fn call(&self, req: Request, next: Next) -> Response
        using [Logger]
    {
        let start = Instant.now()
        let method = req.method.clone()
        let path = req.path.clone()

        Logger.log(Level.Info, f"→ {method} {path}")

        let response = next.call(req).await

        let duration = start.elapsed()
        let status = response.status

        Logger.log(Level.Info, f"← {status} {duration.as_millis()}ms")

        response
    }
}

/// Metrics middleware - latency and status code tracking
type MetricsMiddleware is {}

impl Middleware for MetricsMiddleware {
    async fn call(&self, req: Request, next: Next) -> Response
        using [Metrics]
    {
        let start = Instant.now()
        let path = normalize_path(&req.path)  // Remove IDs for cardinality

        Metrics.increment(f"http.requests.{path}")

        let response = next.call(req).await

        let duration = start.elapsed()
        let status_class = response.status.as_u16() / 100  // 2xx, 4xx, 5xx

        Metrics.histogram(f"http.latency.{path}", duration.as_micros())
        Metrics.increment(f"http.status.{status_class}xx")

        response
    }
}

/// Rate limiting middleware - token bucket algorithm
type RateLimitMiddleware is {
    config: RateLimitConfig,
}

impl RateLimitMiddleware {
    fn new(config: &RateLimitConfig) -> Self {
        Self { config: config.clone() }
    }
}

impl Middleware for RateLimitMiddleware {
    async fn call(&self, req: Request, next: Next) -> Response
        using [Cache, Metrics]
    {
        // Identify client (API key, IP, or anonymous)
        let client_id = identify_client(&req)

        // Check rate limit
        let key = f"ratelimit:{client_id}"
        let current = Cache.incr(&key).await?

        if current == 1 {
            // First request in window, set expiry
            Cache.expire(&key, self.config.window).await?
        }

        if current > self.config.max_requests {
            Metrics.increment("http.rate_limited")

            return Response.new()
                .status(StatusCode.TooManyRequests)
                .header("Retry-After", self.config.window.as_secs().to_text())
                .json(json!{
                    "error": "rate_limit_exceeded",
                    "retry_after": self.config.window.as_secs()
                })
        }

        let response = next.call(req).await

        response
            .header("X-RateLimit-Limit", self.config.max_requests.to_text())
            .header("X-RateLimit-Remaining", (self.config.max_requests - current).to_text())
    }
}

/// CORS middleware - cross-origin resource sharing
type CorsMiddleware is {
    config: CorsConfig,
}

impl Middleware for CorsMiddleware {
    async fn call(&self, req: Request, next: Next) -> Response {
        // Handle preflight
        if req.method == Method.Options {
            return Response.new()
                .status(StatusCode.NoContent)
                .header("Access-Control-Allow-Origin", &self.config.allowed_origins)
                .header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
                .header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                .header("Access-Control-Max-Age", "86400")
        }

        let response = next.call(req).await

        response
            .header("Access-Control-Allow-Origin", &self.config.allowed_origins)
    }
}
```

---

## 5. Frontend: SvelteKit Web Application

### 5.1 Project Structure

```
registry-web/
├── package.json
├── svelte.config.js
├── vite.config.ts
├── tailwind.config.js
├── src/
│   ├── app.html                  # HTML template
│   ├── app.css                   # Global styles (Tailwind)
│   │
│   ├── lib/                      # Shared library
│   │   ├── api/
│   │   │   ├── client.ts         # API client
│   │   │   ├── packages.ts       # Package API
│   │   │   └── auth.ts           # Auth API
│   │   ├── components/
│   │   │   ├── Header.svelte
│   │   │   ├── Footer.svelte
│   │   │   ├── Search.svelte
│   │   │   ├── PackageCard.svelte
│   │   │   ├── VersionList.svelte
│   │   │   ├── Documentation.svelte
│   │   │   └── CodeBlock.svelte
│   │   ├── stores/
│   │   │   ├── auth.ts           # Auth state
│   │   │   └── search.ts         # Search state
│   │   └── utils/
│   │       ├── markdown.ts       # Markdown rendering
│   │       └── syntax.ts         # Syntax highlighting
│   │
│   └── routes/                   # Pages (file-based routing)
│       ├── +layout.svelte        # Root layout
│       ├── +page.svelte          # Home page
│       ├── search/
│       │   └── +page.svelte      # Search results
│       ├── packages/
│       │   ├── [scope]/
│       │   │   └── [name]/
│       │   │       ├── +page.svelte      # Package page
│       │   │       └── [version]/
│       │   │           └── +page.svelte  # Version page
│       ├── docs/
│       │   └── [scope]/
│       │       └── [name]/
│       │           └── [version]/
│       │               └── [...path]/
│       │                   └── +page.svelte  # Documentation viewer
│       ├── dashboard/
│       │   ├── +page.svelte      # User dashboard
│       │   └── packages/
│       │       └── +page.svelte  # User's packages
│       └── auth/
│           ├── login/
│           │   └── +page.svelte
│           └── callback/
│               └── +page.server.ts
│
├── static/                       # Static assets
│   ├── favicon.ico
│   └── logo.svg
│
└── tests/                        # E2E tests (Playwright)
    └── packages.spec.ts
```

### 5.2 Key Pages

#### Home Page (+page.svelte)

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Search from '$lib/components/Search.svelte';
  import PackageCard from '$lib/components/PackageCard.svelte';
  import { fetchPopularPackages, fetchRecentPackages } from '$lib/api/packages';

  let popularPackages = [];
  let recentPackages = [];

  onMount(async () => {
    [popularPackages, recentPackages] = await Promise.all([
      fetchPopularPackages(8),
      fetchRecentPackages(8)
    ]);
  });
</script>

<svelte:head>
  <title>Verum Registry - Package Distribution</title>
</svelte:head>

<div class="min-h-screen bg-gray-50">
  <!-- Hero Section -->
  <section class="bg-gradient-to-r from-purple-700 to-indigo-800 text-white py-20">
    <div class="container mx-auto px-4 text-center">
      <h1 class="text-5xl font-bold mb-4">Verum Registry</h1>
      <p class="text-xl mb-8 opacity-90">
        Verified packages for verified software
      </p>

      <Search placeholder="Search packages..." size="large" />

      <div class="mt-8 flex justify-center gap-6 text-sm opacity-80">
        <span>15,234 packages</span>
        <span>•</span>
        <span>8,192 verified with proofs</span>
        <span>•</span>
        <span>2.5M downloads/week</span>
      </div>
    </div>
  </section>

  <!-- Quick Start -->
  <section class="py-12 bg-white border-b">
    <div class="container mx-auto px-4">
      <h2 class="text-2xl font-bold mb-6">Quick Start</h2>

      <div class="bg-gray-900 rounded-lg p-6 text-gray-100 font-mono">
        <div class="text-gray-400 mb-2"># Install a package</div>
        <div>$ verum add http-client</div>
        <div class="mt-4 text-gray-400"># Publish your package</div>
        <div>$ verum publish</div>
      </div>
    </div>
  </section>

  <!-- Popular Packages -->
  <section class="py-12">
    <div class="container mx-auto px-4">
      <h2 class="text-2xl font-bold mb-6">Popular Packages</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {#each popularPackages as pkg}
          <PackageCard {pkg} />
        {/each}
      </div>
    </div>
  </section>

  <!-- Recent Packages -->
  <section class="py-12 bg-white">
    <div class="container mx-auto px-4">
      <h2 class="text-2xl font-bold mb-6">Recently Published</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {#each recentPackages as pkg}
          <PackageCard {pkg} />
        {/each}
      </div>
    </div>
  </section>
</div>
```

#### Package Card Component

```svelte
<!-- src/lib/components/PackageCard.svelte -->
<script lang="ts">
  import type { Package } from '$lib/api/types';

  export let pkg: Package;

  const verificationBadge = {
    'proof': { text: 'Proven', class: 'bg-green-100 text-green-800' },
    'static': { text: 'Static', class: 'bg-blue-100 text-blue-800' },
    'runtime': { text: 'Runtime', class: 'bg-yellow-100 text-yellow-800' },
    'none': { text: 'None', class: 'bg-gray-100 text-gray-800' },
  };

  $: badge = verificationBadge[pkg.verification_level];
</script>

<a
  href="/packages/{pkg.id}"
  class="block bg-white rounded-lg border hover:shadow-md transition-shadow p-4"
>
  <div class="flex items-start justify-between mb-2">
    <h3 class="font-semibold text-lg truncate">{pkg.id}</h3>
    <span class="text-sm text-gray-500">v{pkg.latest_version}</span>
  </div>

  <p class="text-gray-600 text-sm mb-3 line-clamp-2">
    {pkg.description}
  </p>

  <div class="flex items-center justify-between text-xs">
    <span class="px-2 py-1 rounded {badge.class}">
      {badge.text}
    </span>

    <div class="flex items-center gap-3 text-gray-500">
      <span title="Downloads">↓ {formatNumber(pkg.downloads)}</span>
      <span title="CBGR overhead">~{pkg.cbgr_profile.average_overhead_ns}ns</span>
    </div>
  </div>
</a>
```

#### Documentation Viewer

```svelte
<!-- src/routes/docs/[scope]/[name]/[version]/[...path]/+page.svelte -->
<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import CodeBlock from '$lib/components/CodeBlock.svelte';
  import { renderMarkdown } from '$lib/utils/markdown';

  export let data;

  $: doc = data.documentation;
  $: symbol = data.symbol;

  // Highlight CBGR overhead and verification level
  function renderCostAnnotation(cbgr_ns: number, verification: string) {
    return `
      <div class="flex gap-4 text-sm mt-2 p-2 bg-gray-50 rounded">
        <span class="text-purple-600">
          CBGR: ~${cbgr_ns}ns
        </span>
        <span class="text-blue-600">
          Verification: ${verification}
        </span>
      </div>
    `;
  }
</script>

<div class="flex min-h-screen">
  <!-- Sidebar: Symbol navigation -->
  <aside class="w-64 border-r bg-gray-50 p-4 overflow-y-auto">
    <nav>
      <h3 class="font-bold mb-2">Modules</h3>
      {#each doc.modules as mod}
        <a
          href="/docs/{$page.params.scope}/{$page.params.name}/{$page.params.version}/{mod.path}"
          class="block py-1 text-sm hover:text-purple-600"
          class:font-semibold={$page.params.path === mod.path}
        >
          {mod.name}
        </a>
      {/each}

      <h3 class="font-bold mt-6 mb-2">Functions</h3>
      {#each doc.functions as fn}
        <a
          href="#fn-{fn.name}"
          class="block py-1 text-sm hover:text-purple-600"
        >
          {fn.name}
        </a>
      {/each}

      <h3 class="font-bold mt-6 mb-2">Types</h3>
      {#each doc.types as type}
        <a
          href="#type-{type.name}"
          class="block py-1 text-sm hover:text-purple-600"
        >
          {type.name}
        </a>
      {/each}
    </nav>
  </aside>

  <!-- Main content -->
  <main class="flex-1 p-8 max-w-4xl">
    <h1 class="text-3xl font-bold mb-4">{symbol.name}</h1>

    <!-- Signature -->
    <CodeBlock language="verum" code={symbol.signature} />

    <!-- Cost annotation -->
    {@html renderCostAnnotation(symbol.cbgr_overhead_ns, symbol.verification)}

    <!-- Documentation -->
    <div class="prose mt-6">
      {@html renderMarkdown(symbol.documentation)}
    </div>

    <!-- Examples -->
    {#if symbol.examples.length > 0}
      <h2 class="text-xl font-bold mt-8 mb-4">Examples</h2>
      {#each symbol.examples as example}
        <CodeBlock language="verum" code={example} />
      {/each}
    {/if}

    <!-- Source link -->
    <div class="mt-8 text-sm text-gray-500">
      <a
        href="{symbol.source_url}"
        target="_blank"
        class="hover:text-purple-600"
      >
        View source →
      </a>
    </div>
  </main>
</div>
```

### 5.3 API Client

```typescript
// src/lib/api/client.ts
const API_BASE = import.meta.env.VITE_API_URL || 'https://api.packages.vr.lang';

export interface ApiError {
  error: string;
  message?: string;
  details?: unknown;
}

export async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error: ApiError = await response.json();
    throw new Error(error.message || error.error);
  }

  return response.json();
}

// src/lib/api/packages.ts
import { api } from './client';
import type { Package, PackageVersion, SearchResult } from './types';

export async function getPackage(scope: string, name: string): Promise<Package> {
  return api(`/api/v1/packages/${scope}/${name}`);
}

export async function getVersion(
  scope: string,
  name: string,
  version: string
): Promise<PackageVersion> {
  return api(`/api/v1/packages/${scope}/${name}/${version}`);
}

export async function search(
  query: string,
  options: { verified?: boolean; limit?: number } = {}
): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query });
  if (options.verified) params.set('verified', 'true');
  if (options.limit) params.set('limit', options.limit.toString());

  return api(`/api/v1/search?${params}`);
}

export async function fetchPopularPackages(limit: number): Promise<Package[]> {
  return api(`/api/v1/packages?sort=downloads&limit=${limit}`);
}

export async function fetchRecentPackages(limit: number): Promise<Package[]> {
  return api(`/api/v1/packages?sort=published_at&limit=${limit}`);
}
```

---

## 6. API Specification

### 6.1 REST API Endpoints

#### Packages

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/packages/:scope/:name` | Get package metadata |
| GET | `/api/v1/packages/:scope/:name/versions` | List all versions |
| GET | `/api/v1/packages/:scope/:name/:version` | Get specific version |
| GET | `/api/v1/packages/:scope/:name/:version/source.tar.gz` | Download source |
| POST | `/api/v1/packages/publish` | Publish new version |
| PUT | `/api/v1/packages/:scope/:name/:version/yank` | Yank version |
| DELETE | `/api/v1/packages/:scope/:name/:version/yank` | Unyank version |

#### Search

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/search?q=query` | Full-text search |

#### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login with API token |
| POST | `/api/v1/auth/oidc/callback` | OIDC callback |
| POST | `/api/v1/auth/token/refresh` | Refresh access token |

#### Checksum Database

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sumdb/lookup/:scope_name@:version` | Lookup checksum |
| GET | `/sumdb/latest` | Get tree head |
| GET | `/sumdb/tile/:level/:index` | Get Merkle tile |

### 6.2 Response Formats

#### Package Response

```json
{
  "id": "@verum/http",
  "description": "Fast, verified HTTP client",
  "homepage": "https://github.com/verum-lang/http",
  "repository": "https://github.com/verum-lang/http",
  "license": "MIT OR Apache-2.0",
  "keywords": ["http", "client", "async"],
  "latest_version": "1.2.3",
  "downloads": 125000,
  "score": 92,
  "verification_level": "proof",
  "cbgr_profile": {
    "average_overhead_ns": 15,
    "p95_overhead_ns": 25,
    "memory_overhead_percent": 3.2
  },
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-06-15T12:00:00Z"
}
```

#### Version Response

```json
{
  "package_id": "@verum/http",
  "version": "1.2.3",
  "edition": "2025",
  "language_profile": "application",
  "dependencies": [
    { "package": "@verum/async", "version_req": "^2.0", "optional": false }
  ],
  "features": {
    "default": ["tls"],
    "tls": [],
    "websocket": []
  },
  "checksum": "sha256:abc123...",
  "cbgr_profile": {
    "average_overhead_ns": 15,
    "hot_paths": [
      { "function": "connect", "overhead_ns": 45 }
    ]
  },
  "verification_level": "proof",
  "published_at": "2025-06-15T12:00:00Z",
  "yanked": false,
  "source_url": "https://cdn.vr.lang/packages/@verum/http/1.2.3/source.tar.gz"
}
```

#### Search Response

```json
{
  "results": [
    {
      "id": "@verum/http",
      "version": "1.2.3",
      "description": "Fast, verified HTTP client",
      "downloads": 125000,
      "verification_level": "proof",
      "cbgr_overhead_ns": 15,
      "score": 92
    }
  ],
  "total": 42,
  "page": 1,
  "per_page": 20
}
```

#### Sumdb Lookup Response

```json
{
  "package": "@verum/http",
  "version": "1.2.3",
  "checksum": "sha256:abc123def456...",
  "timestamp": "2025-06-15T12:00:00Z"
}
```

---

## 7. Security Architecture

### 7.1 Authentication

#### Trusted Publishing (Primary)

```
┌───────────────────────────────────────────────────────────────┐
│                    TRUSTED PUBLISHING FLOW                     │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  GitHub Actions                    Verum Registry              │
│  ┌──────────────┐                  ┌──────────────────────┐   │
│  │ OIDC Token   │────Request──────►│ Validate OIDC Token  │   │
│  │ (short-lived)│                  │                      │   │
│  └──────────────┘                  │ 1. Verify signature  │   │
│                                    │ 2. Check claims      │   │
│                                    │    - repo            │   │
│                                    │    - workflow        │   │
│                                    │    - ref             │   │
│                                    │ 3. Match trusted pub │   │
│                                    └──────────┬───────────┘   │
│                                               │               │
│                                               ▼               │
│                                    ┌──────────────────────┐   │
│                                    │ Issue Short-Lived    │   │
│                                    │ Publish Token        │   │
│                                    │ (15 min expiry)      │   │
│                                    └──────────────────────┘   │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

**Configuration in verum.toml:**

```toml
[publish]
trusted_publishers = [
    { provider = "github", repository = "verum-lang/http", workflow = "publish.yml" }
]
```

#### API Tokens (Fallback)

- Scoped to specific packages
- Maximum 90-day expiry
- Rate limited
- Revocable

### 7.2 Pre-Publish Security Checks

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY VALIDATION PIPELINE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. TYPOSQUATTING DETECTION                                     │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ • Levenshtein distance to existing packages             │ │
│     │ • Keyboard proximity analysis                           │ │
│     │ • Common substitution patterns (0/o, 1/l)               │ │
│     │ • Threshold: distance < 3 triggers review               │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
│  2. MALWARE SCANNING                                             │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ • Static analysis of source code                        │ │
│     │ • Network access patterns (suspicious domains)          │ │
│     │ • File system access patterns                           │ │
│     │ • Crypto wallet address detection                       │ │
│     │ • Known malware signatures                              │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
│  3. DEPENDENCY ANALYSIS                                          │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ • Vulnerable dependencies (CVE database)                │ │
│     │ • Dependency confusion check                            │ │
│     │ • License compatibility                                 │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
│  4. SEMVER VALIDATION                                            │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ • API diff against previous version                     │ │
│     │ • Breaking change detection                             │ │
│     │ • Major bump required for breaking changes              │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 Checksum Database Security

```
SECURITY PROPERTIES:

1. IMMUTABILITY
   - Once added, entries cannot be modified
   - Tree is append-only
   - Historical entries verifiable

2. TRANSPARENCY
   - All entries publicly auditable
   - Merkle tree enables efficient proofs
   - Gossip protocol detects tampering

3. SEPARATION
   - Sumdb is separate from package storage
   - Any mirror can serve packages
   - Verification happens against sumdb

4. CRYPTOGRAPHIC SIGNING
   - Tree head signed with Ed25519
   - Signature includes tree_size + root_hash + timestamp
   - Key rotation with transparency
```

---

## 8. Data Model

### 8.1 PostgreSQL Schema

```sql
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- Trigram for fuzzy search

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL CHECK (username ~ '^[a-z][a-z0-9_-]{1,63}$'),
    password_hash TEXT,  -- NULL for OIDC-only users
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);

-- API Tokens
CREATE TABLE api_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,  -- SHA-256 of token
    name TEXT NOT NULL,
    scopes TEXT[] NOT NULL,  -- ['publish:@scope/name', 'read:*']
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tokens_user ON api_tokens(user_id);
CREATE INDEX idx_tokens_hash ON api_tokens(token_hash);

-- Trusted Publishers
CREATE TABLE trusted_publishers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    package_id TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('github', 'gitlab')),
    repository TEXT NOT NULL,
    workflow_filename TEXT,
    environment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (package_id, provider, repository)
);

CREATE INDEX idx_trusted_pub_package ON trusted_publishers(package_id);

-- Packages
CREATE TABLE packages (
    id TEXT PRIMARY KEY CHECK (id ~ '^(@[a-z0-9][a-z0-9-]{0,63}/)?[a-z][a-z0-9_-]{0,63}$'),
    description TEXT NOT NULL CHECK (char_length(description) <= 500),
    homepage TEXT,
    repository TEXT,
    license TEXT NOT NULL,
    keywords TEXT[] NOT NULL CHECK (array_length(keywords, 1) <= 5),
    latest_version TEXT NOT NULL,
    downloads BIGINT NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_packages_downloads ON packages(downloads DESC);
CREATE INDEX idx_packages_score ON packages(score DESC);
CREATE INDEX idx_packages_updated ON packages(updated_at DESC);
CREATE INDEX idx_packages_keywords ON packages USING GIN(keywords);

-- Package Owners
CREATE TABLE package_owners (
    package_id TEXT NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'maintainer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (package_id, user_id)
);

-- Versions
CREATE TABLE versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    package_id TEXT NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    edition TEXT NOT NULL,
    language_profile TEXT NOT NULL CHECK (language_profile IN ('application', 'systems', 'research')),
    dependencies JSONB NOT NULL DEFAULT '[]',
    dev_dependencies JSONB NOT NULL DEFAULT '[]',
    features JSONB NOT NULL DEFAULT '{}',
    default_features TEXT[] NOT NULL DEFAULT '{}',
    checksum TEXT NOT NULL CHECK (char_length(checksum) = 64),
    cbgr_profile JSONB NOT NULL,
    verification_level TEXT NOT NULL CHECK (verification_level IN ('none', 'runtime', 'static', 'proof')),
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_by UUID NOT NULL REFERENCES users(id),
    yanked BOOLEAN NOT NULL DEFAULT FALSE,
    yank_reason TEXT,
    UNIQUE (package_id, version)
);

CREATE INDEX idx_versions_package ON versions(package_id);
CREATE INDEX idx_versions_published ON versions(published_at DESC);
CREATE INDEX idx_versions_verification ON versions(verification_level);

-- Downloads (time-series, partitioned by month)
CREATE TABLE downloads (
    id BIGSERIAL,
    package_id TEXT NOT NULL,
    version TEXT NOT NULL,
    downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_ip INET,
    user_agent TEXT
) PARTITION BY RANGE (downloaded_at);

-- Create monthly partitions
CREATE TABLE downloads_2025_01 PARTITION OF downloads
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
-- ... more partitions

CREATE INDEX idx_downloads_package ON downloads(package_id, downloaded_at);

-- Checksum Database (sumdb)
CREATE TABLE sumdb_entries (
    entry_id BIGSERIAL PRIMARY KEY,
    package TEXT NOT NULL,
    version TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK (char_length(checksum) = 64),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hash TEXT NOT NULL,  -- SHA-256(package || version || checksum)
    UNIQUE (package, version)
);

CREATE INDEX idx_sumdb_lookup ON sumdb_entries(package, version);
CREATE INDEX idx_sumdb_entry_id ON sumdb_entries(entry_id);

-- Tree head (signed)
CREATE TABLE sumdb_tree_head (
    id BIGSERIAL PRIMARY KEY,
    tree_size BIGINT NOT NULL,
    root_hash TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signature TEXT NOT NULL
);

CREATE INDEX idx_tree_head_size ON sumdb_tree_head(tree_size DESC);

-- Security Advisories
CREATE TABLE security_advisories (
    id TEXT PRIMARY KEY,  -- VSEC-YYYY-NNNN
    package_id TEXT NOT NULL,
    affected_versions TEXT NOT NULL,  -- Version range
    fixed_versions TEXT,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    cve_ids TEXT[],
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_advisories_package ON security_advisories(package_id);
CREATE INDEX idx_advisories_severity ON security_advisories(severity);
```

---

## 9. Supply Chain Security

### 9.1 Checksum Database Design

Based on Go's sumdb with Verum-specific extensions:

```
ARCHITECTURE:

┌─────────────────────────────────────────────────────────────────┐
│                      CHECKSUM DATABASE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   TRANSPARENT LOG                            ││
│  │                                                               ││
│  │   Entry 0: (@verum/core, 1.0.0, sha256:abc...)              ││
│  │   Entry 1: (@verum/http, 1.0.0, sha256:def...)              ││
│  │   Entry 2: (@verum/core, 1.0.1, sha256:ghi...)              ││
│  │   ...                                                         ││
│  │   Entry N: (@user/pkg, X.Y.Z, sha256:xyz...)                 ││
│  │                                                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    MERKLE TREE                                ││
│  │                                                               ││
│  │                    [Root Hash]                                ││
│  │                    /          \                               ││
│  │               [Hash]          [Hash]                          ││
│  │              /      \        /      \                         ││
│  │           [H0]    [H1]    [H2]    [H3]                       ││
│  │            │       │       │       │                          ││
│  │         Entry0  Entry1  Entry2  Entry3                       ││
│  │                                                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   SIGNED TREE HEAD                            ││
│  │                                                               ││
│  │   {                                                           ││
│  │     "tree_size": 12345,                                       ││
│  │     "root_hash": "sha256:abc123...",                          ││
│  │     "timestamp": "2025-06-15T12:00:00Z",                      ││
│  │     "signature": "ed25519:..."                                ││
│  │   }                                                           ││
│  │                                                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Client Verification Protocol

```verum
/// Verify downloaded package against sumdb
///
/// Called by `verum add` after downloading from any source.
///
/// # Security Properties
/// 1. Package content matches sumdb checksum
/// 2. Sumdb tree is consistent (no history rewriting)
/// 3. Tree head signature is valid
pub async fn verify_package(
    package: &PackageScope,
    version: &SemVer,
    content: &List<u8>,
) -> Result<(), VerifyError> {
    // 1. Compute local checksum
    let local_checksum = sha256(content)

    // 2. Fetch sumdb entry
    let entry = sumdb_client.lookup(package, version).await?

    // 3. Compare checksums
    if local_checksum != entry.checksum {
        return Err(VerifyError.ChecksumMismatch {
            expected: entry.checksum,
            actual: local_checksum,
        })
    }

    // 4. Verify tree consistency (optional, for paranoid mode)
    if config.verify_tree_consistency {
        let tree_head = sumdb_client.get_latest().await?
        verify_tree_signature(&tree_head)?
        verify_inclusion_proof(entry, &tree_head)?
    }

    Ok(())
}
```

### 9.3 Provenance

Package provenance is tracked using Sigstore-compatible attestations:

```json
{
  "_type": "https://in-toto.io/Statement/v0.1",
  "subject": [
    {
      "name": "@verum/http",
      "digest": { "sha256": "abc123..." }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v0.2",
  "predicate": {
    "buildType": "https://verum.lang/publish/v1",
    "builder": { "id": "https://github.com/verum-lang/http/.github/workflows/publish.yml" },
    "invocation": {
      "configSource": {
        "uri": "git+https://github.com/verum-lang/http@refs/tags/v1.2.3",
        "digest": { "sha1": "abc123" }
      }
    },
    "metadata": {
      "buildStartedOn": "2025-06-15T12:00:00Z",
      "buildFinishedOn": "2025-06-15T12:00:30Z"
    }
  }
}
```

---

## 10. Developer Experience

### 10.1 Zero-Configuration Publishing

```bash
# Create a new package
$ verum new my-package
$ cd my-package

# Write code in src/lib.vr
# ...

# Publish (no configuration needed for first publish)
$ verum publish

Publishing my-package@0.1.0...
✓ Authenticated via GitHub OIDC
✓ Source validated
✓ No typosquatting detected
✓ No malware detected
✓ Documentation generated
✓ CBGR profile: ~12ns average overhead
✓ Published to packages.vr.lang

Package URL: https://packages.vr.lang/my-package
Docs URL: https://docs.vr.lang/my-package/0.1.0
```

### 10.2 CLI Commands

```bash
# Package discovery
verum search "http client"        # Search packages
verum info @verum/http            # Show package info
verum doc @verum/http             # Open documentation

# Dependency management
verum add @verum/http             # Add latest version
verum add @verum/http@^1.2        # Add with version constraint
verum add @verum/http --dev       # Add as dev dependency
verum update                      # Update all dependencies
verum update @verum/http          # Update specific package

# Publishing
verum publish                     # Publish current package
verum publish --dry-run           # Validate without publishing
verum yank 0.1.0                  # Yank a version
verum yank --undo 0.1.0           # Unyank

# Security
verum audit                       # Check for vulnerabilities
verum audit --fix                 # Auto-update vulnerable deps
verum verify-checksums            # Verify all checksums against sumdb

# Local development
verum build                       # Build package
verum test                        # Run tests
verum doc --open                  # Generate and open docs
verum bench                       # Run benchmarks
```

### 10.3 Package Scoring

```
SCORE COMPONENTS (0-100):

Documentation (30 points max)
├── README present                    +5
├── Module-level docs                 +10
├── All public symbols documented     +15

Testing (25 points max)
├── Tests present                     +10
├── Test coverage > 50%               +5
├── Test coverage > 80%               +10

Verification (20 points max)
├── @verify(runtime) on all fns       +5
├── @verify(static) on some fns       +10
├── @verify(proof) on critical fns    +15
├── Zero unsafe blocks                +5

Quality (15 points max)
├── No compile warnings               +5
├── Formatted with verum fmt          +5
├── No deprecated dependencies        +5

Maintenance (10 points max)
├── Recent updates (< 6 months)       +5
├── Responsive to issues              +5
```

### 10.4 Auto-Generated Documentation

Documentation is generated from source code with Verum-specific annotations:

```verum
/// Connect to a remote server
///
/// Establishes a TCP connection with TLS if configured.
///
/// # Arguments
/// - `addr`: Server address in `host:port` format
/// - `config`: Optional TLS configuration
///
/// # Returns
/// A connected `Connection` or an error if connection failed.
///
/// # Example
/// ```verum
/// let conn = connect("api.example.com:443", Some(tls_config)).await?
/// ```
///
/// # Errors
/// - `ConnectionError.Timeout`: Connection timed out
/// - `ConnectionError.Refused`: Connection refused by server
/// - `ConnectionError.TlsFailed`: TLS handshake failed
@verify(runtime)
pub async fn connect(
    addr: &Text,
    config: Maybe<TlsConfig>,
) -> Result<Connection, ConnectionError>
    using [Logger]
{
    // ...
}
```

**Rendered as:**

```
┌─────────────────────────────────────────────────────────────────┐
│  fn connect                                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  async fn connect(                                               │
│      addr: &Text,                                                │
│      config: Maybe<TlsConfig>,                                   │
│  ) -> Result<Connection, ConnectionError>                        │
│      using [Logger]                                              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ CBGR: ~15ns   │   Verification: runtime   │   Async: yes   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Connect to a remote server.                                     │
│                                                                  │
│  Establishes a TCP connection with TLS if configured.           │
│                                                                  │
│  ## Arguments                                                    │
│  - addr: Server address in host:port format                     │
│  - config: Optional TLS configuration                           │
│                                                                  │
│  ## Example                                                      │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ let conn = connect("api.example.com:443", tls).await?     │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ## Errors                                                       │
│  - ConnectionError.Timeout                                       │
│  - ConnectionError.Refused                                       │
│  - ConnectionError.TlsFailed                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 11. Operational Excellence

### 11.1 Infrastructure Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **API Server** | 2 vCPU, 4GB RAM | 4 vCPU, 8GB RAM | Per instance |
| **PostgreSQL** | 4 vCPU, 16GB RAM | 8 vCPU, 32GB RAM | With read replicas |
| **Redis** | 2 vCPU, 4GB RAM | 4 vCPU, 8GB RAM | Cluster mode |
| **S3** | - | - | Use managed service |
| **MeiliSearch** | 2 vCPU, 4GB RAM | 4 vCPU, 8GB RAM | |

### 11.2 Performance Targets

| Metric | Target | SLA |
|--------|--------|-----|
| API latency (p50) | < 50ms | - |
| API latency (p95) | < 200ms | 99.9% |
| API latency (p99) | < 500ms | 99% |
| Publish time | < 30s | 99% |
| Search latency | < 50ms | 99.9% |
| Download (CDN hit) | < 100ms | 99.99% |
| Uptime | - | 99.9% |

### 11.3 Monitoring

```yaml
# Key metrics to track

# API Health
- http_requests_total{endpoint, status}
- http_request_duration_seconds{endpoint, quantile}
- http_active_connections

# Publish Pipeline
- publish_attempts_total
- publish_success_total
- publish_duration_seconds
- publish_validation_failures{reason}

# Security
- security_malware_blocked_total
- security_typosquatting_alerts_total
- auth_failures_total{reason}

# Dependencies
- db_connections_active
- db_query_duration_seconds{query_type}
- cache_hit_ratio
- s3_operations_total{operation}

# Business
- packages_total
- versions_total
- downloads_total{package}
- active_users_daily
```

### 11.4 Incident Response

```
SEVERITY LEVELS:

P1 (Critical) - 15 min response
- Registry unavailable
- Security breach detected
- Data corruption

P2 (High) - 1 hour response
- Publish failures > 10%
- Search unavailable
- Sumdb inconsistency

P3 (Medium) - 4 hour response
- Elevated error rates
- Slow performance
- Single component degradation

P4 (Low) - 24 hour response
- Minor bugs
- Documentation issues
- Non-critical feature issues
```

---

## 12. Implementation Roadmap

### Phase 1: Foundation (Months 1-2)

**Core Infrastructure:**
- [ ] Verum backend project structure
- [ ] PostgreSQL schema
- [ ] S3 storage integration
- [ ] Redis caching
- [ ] Basic authentication (API tokens)

**Basic API:**
- [ ] GET /packages/:scope/:name
- [ ] GET /packages/:scope/:name/versions
- [ ] POST /packages/publish (simple)
- [ ] Download source archives

**Minimal Frontend:**
- [ ] SvelteKit project setup
- [ ] Package listing page
- [ ] Package detail page
- [ ] Basic search

**CLI Integration:**
- [ ] `verum add` with new registry
- [ ] `verum publish` basic flow

### Phase 2: Security (Months 3-4)

**Trusted Publishing:**
- [ ] GitHub OIDC integration
- [ ] GitLab OIDC integration
- [ ] Short-lived token issuance

**Checksum Database:**
- [ ] Transparent log implementation
- [ ] Merkle tree construction
- [ ] Ed25519 signing
- [ ] Lookup/tile APIs

**Pre-publish Checks:**
- [ ] Typosquatting detection
- [ ] Basic malware scanning
- [ ] Semver validation

**CLI Integration:**
- [ ] `verum audit`
- [ ] `verum verify-checksums`

### Phase 3: Developer Experience (Months 5-6)

**Documentation:**
- [ ] Auto-generation from source
- [ ] Symbol-level docs
- [ ] Cost annotations (CBGR, verification)
- [ ] Docs viewer in frontend

**Search:**
- [ ] MeiliSearch integration
- [ ] Full-text search
- [ ] Filters (verified, profile, keywords)

**Package Scoring:**
- [ ] Score calculation
- [ ] Display in frontend
- [ ] Badges

**Frontend Polish:**
- [ ] User dashboard
- [ ] Package management
- [ ] Search improvements

### Phase 4: Scale & Polish (Months 7-8)

**Performance:**
- [ ] CDN integration
- [ ] Caching optimization
- [ ] Query optimization
- [ ] Load testing

**Operations:**
- [ ] Monitoring dashboards
- [ ] Alerting
- [ ] Runbooks
- [ ] Backup/restore

**Documentation:**
- [ ] User guide
- [ ] API documentation
- [ ] Contributing guide

### Phase 5: Launch (Month 9)

- [ ] Public beta announcement
- [ ] Migration tooling from existing packages
- [ ] Community feedback collection
- [ ] Stability monitoring
- [ ] Official launch

---

## Appendix A: Verum Language Features Demonstrated

This registry implementation showcases these Verum features:

| Feature | Location | Description |
|---------|----------|-------------|
| **Context System** | `src/contexts/*.vr` | Two-level DI with provide/using |
| **Async/Await** | Throughout | Non-blocking I/O |
| **Refinement Types** | `src/domain/*.vr` | Compile-time validation |
| **Pattern Matching** | Handlers | Exhaustive error handling |
| **Semantic Types** | Throughout | List, Text, Map, Maybe |
| **Error Handling** | Services | Result types, error context |
| **CBGR** | Implicit | ~15ns memory safety |
| **sql Literals** | Database queries | SQL injection prevention |
| **Derive Macros** | Domain types | Automatic serialization |

---

## Appendix B: Comparison with Existing Registries

| Aspect | Verum Registry | crates.io | npm | PyPI | Go Modules |
|--------|----------------|-----------|-----|------|------------|
| **Backend Language** | Verum | Rust | Node.js | Python | N/A |
| **Namespace** | Scoped | Flat | Scoped | Flat | By domain |
| **Trusted Publishing** | Day 1 | 2025 | Limited | Limited | N/A |
| **Checksum DB** | Yes | No | No | No | Yes |
| **Source Publishing** | Yes | No | No | No | Yes |
| **Auto Docs** | Yes | External | No | No | Yes |
| **Pre-publish Malware** | Yes | No | No | No | No |
| **Semver Enforcement** | Yes | No | No | No | Partial |
| **CBGR Profiles** | Yes | N/A | N/A | N/A | N/A |
| **Verification Levels** | Yes | N/A | N/A | N/A | N/A |

---

## Appendix C: API Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `package_not_found` | 404 | Package does not exist |
| `version_not_found` | 404 | Version does not exist |
| `version_exists` | 409 | Version already published |
| `unauthorized` | 401 | Authentication required |
| `forbidden` | 403 | Insufficient permissions |
| `validation_failed` | 422 | Manifest validation failed |
| `typosquatting_detected` | 422 | Similar package name exists |
| `malware_detected` | 422 | Malicious code detected |
| `rate_limited` | 429 | Too many requests |
| `internal_error` | 500 | Server error |

---

*This specification is a living document and will be updated as the registry evolves.*
