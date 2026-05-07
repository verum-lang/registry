-- =============================================================================
-- 0005_publish_identity.sql — extend versions with publish-identity
-- =============================================================================
-- spec v3.0 §5.1.3 — PublishIdentity supports four pathways:
--   sigstore    — Sigstore-keyless Bundle (preferred)
--   oidc_direct — legacy direct OIDC token
--   api_token   — long-lived API token
--   webauthn    — manually published via web UI
-- =============================================================================

ALTER TABLE versions
    ADD COLUMN published_by_kind     TEXT NOT NULL DEFAULT 'api_token'
        CHECK (published_by_kind IN ('sigstore','oidc_direct','api_token','webauthn')),
    -- OIDC subject when sigstore/oidc_direct (NULL otherwise).
    ADD COLUMN published_by_subject  TEXT,
    -- OIDC issuer when sigstore/oidc_direct (NULL otherwise).
    ADD COLUMN published_by_issuer   TEXT,
    -- FK to sigstore_bundles when published_by_kind='sigstore'.
    ADD COLUMN bundle_id             TEXT REFERENCES sigstore_bundles(id);

-- When sigstore/oidc_direct, both subject + issuer must be set.
-- When api_token/webauthn, subject + issuer must be NULL.
ALTER TABLE versions
    ADD CONSTRAINT versions_publish_identity_consistency
    CHECK (
        (published_by_kind IN ('sigstore','oidc_direct')
            AND published_by_subject IS NOT NULL
            AND published_by_issuer IS NOT NULL)
        OR
        (published_by_kind IN ('api_token','webauthn')
            AND published_by_subject IS NULL
            AND published_by_issuer IS NULL)
    );

-- When sigstore, bundle_id MUST be set; otherwise it MUST be NULL.
ALTER TABLE versions
    ADD CONSTRAINT versions_bundle_id_consistency
    CHECK (
        (published_by_kind = 'sigstore' AND bundle_id IS NOT NULL)
        OR
        (published_by_kind != 'sigstore' AND bundle_id IS NULL)
    );

CREATE INDEX versions_published_by_idx
    ON versions (published_by_kind, published_by_issuer, published_by_subject);

COMMENT ON COLUMN versions.published_by_kind IS
    'PublishIdentity discriminant per spec v3.0 §5.1.3';
COMMENT ON COLUMN versions.bundle_id IS
    'FK to sigstore_bundles for Sigstore-keyless publishes';
