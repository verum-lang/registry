-- =============================================================================
-- 0003_tuf_metadata.sql — TUF metadata storage (spec v3.0 §6.1, §9.5)
-- =============================================================================
-- The registry runs its own TUF instance; this schema stores every
-- versioned root rotation + the current timestamp/snapshot/targets
-- metadata. Served via /tuf/<role>.json.
-- Composes against core.security.tuf::types.
-- =============================================================================

-- Root metadata history. Each row is a `Signed<RootMetadata>` envelope.
-- Threshold-signed (3-of-5 Ed25519); rotated quarterly.
CREATE TABLE tuf_root_history (
    version          INTEGER PRIMARY KEY CHECK (version >= 1),
    -- Canonical JSON of the Signed<RootMetadata>.
    content_bytes    BYTEA NOT NULL,
    -- SHA-256 of content_bytes — used as cache key + binding.
    content_sha256   CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Timestamp / snapshot / targets — every signed metadata produced by the
-- registry's TUF service. Old versions are retained to support
-- consistent-snapshot mode for clients fetching historical states.
CREATE TABLE tuf_signed_metadata (
    role             TEXT NOT NULL CHECK (role IN ('timestamp','snapshot','targets')),
    version          INTEGER NOT NULL CHECK (version >= 1),
    content_bytes    BYTEA NOT NULL,
    content_sha256   CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role, version)
);

CREATE INDEX tuf_signed_metadata_role_latest_idx
    ON tuf_signed_metadata (role, version DESC);

-- View of the latest version per role — handy for the timestamp-fetch
-- hot path (timestamp.json is unversioned in the URL).
CREATE OR REPLACE VIEW tuf_latest_metadata AS
SELECT DISTINCT ON (role)
    role, version, content_bytes, content_sha256, expires_at, created_at
FROM tuf_signed_metadata
ORDER BY role, version DESC;

COMMENT ON TABLE tuf_root_history IS
    'TUF root.json history. Each row is one quarterly rotation. spec v3.0 §9.5';
COMMENT ON TABLE tuf_signed_metadata IS
    'TUF timestamp/snapshot/targets metadata, all versions retained for consistent_snapshot mode';
