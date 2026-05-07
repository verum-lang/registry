-- =============================================================================
-- 0004_sigstore_bundles.sql — Sigstore Bundle storage (spec v3.0 §6.1, §9.2)
-- =============================================================================
-- Persists a Sigstore Bundle per package version. The bundle wraps:
--   * DSSE envelope (publisher's signed SLSA / in-toto attestation)
--   * Fulcio-issued ephemeral cert chain (PEM)
--   * Rekor inclusion proofs (SET + Merkle audit hashes)
--
-- Composes against core.security.sigstore::SigstoreBundle.
-- One row per (version_id) — a version has at most one bundle
-- (additional re-publishes are forbidden by spec §10.1).
-- =============================================================================

CREATE TABLE sigstore_bundles (
    id                       TEXT PRIMARY KEY,    -- ULID
    version_id               BIGINT NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
    -- Verbatim Sigstore Bundle JSON (canonicalised). Served at
    -- /api/v3/packages/.../bundle.
    bundle_json              TEXT NOT NULL,
    -- SHA-256 of the canonicalised DSSE envelope. Cross-checked against
    -- the Rekor entry body for inclusion-proof binding.
    envelope_sha256          CHAR(64) NOT NULL CHECK (envelope_sha256 ~ '^[0-9a-f]{64}$'),
    -- SHA-256 of the leaf cert in the Fulcio-issued chain (DER).
    cert_chain_leaf_sha256   CHAR(64) NOT NULL CHECK (cert_chain_leaf_sha256 ~ '^[0-9a-f]{64}$'),
    -- Rekor log index — the cog's transparency-log coordinate.
    rekor_log_index          BIGINT NOT NULL CHECK (rekor_log_index >= 0),
    integrated_time          TIMESTAMPTZ NOT NULL,
    -- OIDC issuer URL extracted from the cert custom extension
    -- (1.3.6.1.4.1.57264.1.{1,8}).
    oidc_issuer              TEXT NOT NULL,
    -- OIDC subject from the cert SAN (email / URI / SPIFFE).
    oidc_subject             TEXT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id)
);

CREATE INDEX sigstore_bundles_envelope_sha_idx ON sigstore_bundles (envelope_sha256);
CREATE INDEX sigstore_bundles_oidc_idx         ON sigstore_bundles (oidc_issuer, oidc_subject);
CREATE INDEX sigstore_bundles_rekor_idx        ON sigstore_bundles (rekor_log_index);

COMMENT ON TABLE sigstore_bundles IS
    'Sigstore Bundles for Sigstore-keyless publishes. spec v3.0 §6.1, §9.2';
COMMENT ON COLUMN sigstore_bundles.envelope_sha256 IS
    'SHA-256 of canonical DSSE envelope. Must match the Rekor entry body';
COMMENT ON COLUMN sigstore_bundles.rekor_log_index IS
    'Public Rekor log index — verifiable at rekor.sigstore.dev/?logIndex=<n>';
