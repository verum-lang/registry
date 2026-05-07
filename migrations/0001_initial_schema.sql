-- =============================================================================
-- migrations/0001_initial_schema.sql
-- =============================================================================
-- Spec: §6.1
--
-- Applied through `core.database.postgres.migrations.MigrationRunner`
-- with the Postgres-specific store (advisory-lock-serialised,
-- transactional DDL).  Tracking via `__verum_migrations` (created
-- automatically by the migration runner).
-- =============================================================================

-- ===== Users =====

CREATE TABLE users (
    id            TEXT PRIMARY KEY,           -- ULID
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT,                       -- Argon2id; NULL for OIDC-only
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_username_format CHECK (username ~ '^[a-z][a-z0-9_-]{1,63}$')
);

-- ===== OIDC identities (linked to users) =====

CREATE TABLE oidc_identities (
    user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issuer    TEXT NOT NULL,
    subject   TEXT NOT NULL,
    metadata  JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (issuer, subject)
);
CREATE INDEX oidc_identities_user_id_idx ON oidc_identities (user_id);

-- ===== API tokens =====

CREATE TABLE api_tokens (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    secret_hash   TEXT NOT NULL,
    scopes        JSONB NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked_at    TIMESTAMPTZ,
    last_used_at  TIMESTAMPTZ
);
CREATE INDEX api_tokens_user_id_idx ON api_tokens (user_id);

-- ===== Packages =====

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
CREATE INDEX packages_score_idx ON packages (score DESC);

-- ===== Package owners =====

CREATE TABLE package_owners (
    package_id    TEXT NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('owner', 'maintainer')),
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by    TEXT NOT NULL REFERENCES users(id),
    PRIMARY KEY (package_id, user_id)
);
CREATE INDEX package_owners_user_idx ON package_owners (user_id);

-- ===== Versions =====

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
    CONSTRAINT versions_sha256_format CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT versions_shape_digest_format CHECK (shape_declarations_digest ~ '^[0-9a-f]{64}$')
);
CREATE INDEX versions_package_pub_idx ON versions (package_id, published_at DESC);
CREATE INDEX versions_lifecycle_idx ON versions (cve_lifecycle);
CREATE INDEX versions_verification_idx ON versions (verification_level);

-- ===== Downloads (partitioned by month) =====

CREATE TABLE downloads (
    id            BIGSERIAL,
    package_id    TEXT NOT NULL REFERENCES packages(id),
    version       TEXT NOT NULL,
    downloaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    client_ip     INET,
    user_agent    TEXT,
    PRIMARY KEY (id, downloaded_at)
) PARTITION BY RANGE (downloaded_at);
CREATE INDEX downloads_package_idx ON downloads (package_id, downloaded_at);

-- ===== Sumdb =====

CREATE TABLE sumdb_entries (
    sequence    BIGSERIAL PRIMARY KEY,
    package_id  TEXT NOT NULL,
    version     TEXT NOT NULL,
    checksum    CHAR(64) NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    leaf_hash   BYTEA NOT NULL,
    UNIQUE (package_id, version),
    CONSTRAINT sumdb_checksum_format CHECK (checksum ~ '^[0-9a-f]{64}$')
);

CREATE TABLE sumdb_tree_heads (
    tree_size    BIGINT PRIMARY KEY,
    root_hash    BYTEA NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT now(),
    signature    BYTEA NOT NULL                  -- Ed25519 signature
);

-- ===== Security advisories =====

CREATE TABLE security_advisories (
    id                  TEXT PRIMARY KEY,        -- VSEC-YYYY-NNNN
    package_id          TEXT NOT NULL REFERENCES packages(id),
    affected_versions   TEXT NOT NULL,           -- SemVerConstraint expression
    fixed_versions      TEXT,                    -- SemVerConstraint or NULL
    severity            TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    cve_ids             TEXT[],
    summary             TEXT NOT NULL,
    details             TEXT,
    disclosed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT advisories_id_format CHECK (id ~ '^VSEC-\d{4}-\d{4}$')
);
CREATE INDEX advisories_package_idx ON security_advisories (package_id);
CREATE INDEX advisories_severity_idx ON security_advisories (severity);

-- ===== Pending S3 reconciler queue =====
-- Spec §7.1.7: S3 upload is non-transactional; on post-commit S3
-- failure, this table queues the object for the background reconciler.

CREATE TABLE pending_object_pushes (
    id              BIGSERIAL PRIMARY KEY,
    s3_key          TEXT NOT NULL,
    package_id      TEXT NOT NULL,
    version         TEXT NOT NULL,
    enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attempt_at TIMESTAMPTZ,
    attempts        INT NOT NULL DEFAULT 0,
    error           TEXT
);
CREATE INDEX pending_pushes_age_idx ON pending_object_pushes (enqueued_at);
