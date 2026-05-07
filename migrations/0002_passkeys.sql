-- =============================================================================
-- 0002_passkeys.sql — WebAuthn passkey storage (spec v3.0 §6.1)
-- =============================================================================
-- Persistable VerifiedCredential (core.security.webauthn.types::VerifiedCredential).
-- One row per credential the user registers; cloning detection is enforced
-- at the application layer via signCount monotonicity (spec v3.0 §9.4).
-- =============================================================================

CREATE TABLE passkeys (
    id                  TEXT PRIMARY KEY,         -- ULID (core.base.ulid)
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Authenticator-chosen credential identifier; UNIQUE per registry.
    credential_id       BYTEA NOT NULL UNIQUE,
    -- COSE_Key bytes — encoded canonical CBOR.
    public_key_cose     BYTEA NOT NULL,
    -- Negotiated COSE algorithm: -7 ES256 / -8 EdDSA / -257 RS256 / -37 PS256
    cose_alg            INTEGER NOT NULL,
    -- 16-byte AAGUID identifying the authenticator model.
    aaguid              BYTEA NOT NULL CHECK (length(aaguid) = 16),
    -- Last observed signCount; updated on every successful authentication.
    sign_count          BIGINT NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
    -- Backup-eligible bit at registration (BE).
    backup_eligible     BOOLEAN NOT NULL DEFAULT false,
    -- Last observed backup-state bit (BS); changes flagged for UX hints.
    backup_state        BOOLEAN NOT NULL DEFAULT false,
    -- Attestation format from the registration ceremony.
    attestation_format  TEXT NOT NULL CHECK (
        attestation_format IN ('none','packed','fido-u2f','tpm','android-key',
                                'android-safetynet','apple','apple-appattest')
    ),
    -- User-friendly nickname (e.g., "Yubikey 5 — work").
    nickname            TEXT,
    -- Authenticator transports the client hinted ("usb","nfc","ble","internal","hybrid","smart-card").
    transports          TEXT[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ
);

CREATE INDEX passkeys_user_id_idx       ON passkeys (user_id);
CREATE INDEX passkeys_aaguid_idx        ON passkeys (aaguid);
CREATE INDEX passkeys_last_used_idx     ON passkeys (last_used_at DESC NULLS LAST);

COMMENT ON TABLE passkeys IS
    'WebAuthn passkeys (FIDO2 credentials). spec v3.0 §6.1, §9.4';
COMMENT ON COLUMN passkeys.sign_count IS
    'Monotonic counter for cloning detection per WebAuthn §6.1.1';
COMMENT ON COLUMN passkeys.aaguid IS
    'Authenticator Attestation GUID; all-zero AAGUID = none/synthetic';
