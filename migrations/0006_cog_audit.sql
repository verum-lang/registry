-- =============================================================================
-- 0006_cog_audit.sql — per-version audit records (spec §6.1.7, §12)
-- =============================================================================
-- Persists the CogAuditRecord produced by PublishService Phase 5b.
-- Two tables: a header table with one row per (version_id) +
-- a per-AP findings table (sparse — only Error/Warning entries
-- materialise).
-- Also augments versions with the ATS-V coordinate triple
-- (foundation, stratum, at_tier) extracted from the cog's
-- @arch_module declaration.
-- =============================================================================

ALTER TABLE versions
    ADD COLUMN foundation TEXT NOT NULL DEFAULT 'ZfcTwoInacc',
    ADD COLUMN stratum    TEXT NOT NULL DEFAULT 'LFnd'
        CHECK (stratum IN ('LFnd','LCls','LClsTop','LAbs')),
    ADD COLUMN at_tier    TEXT NOT NULL DEFAULT 'Aot';

CREATE INDEX versions_foundation_idx ON versions (foundation);
CREATE INDEX versions_stratum_idx    ON versions (stratum);
CREATE INDEX versions_at_tier_idx    ON versions (at_tier);

-- Header table: one row per version_id.
CREATE TABLE cog_audit_records (
    version_id              BIGINT PRIMARY KEY REFERENCES versions(id) ON DELETE CASCADE,
    -- CVE-closure axes
    constructive_verdict    TEXT NOT NULL CHECK (constructive_verdict IN ('closed','conditional','open')),
    constructive_detail     TEXT,
    verifiable_verdict      TEXT NOT NULL CHECK (verifiable_verdict   IN ('closed','conditional','open')),
    verifiable_detail       TEXT,
    executable_verdict      TEXT NOT NULL CHECK (executable_verdict   IN ('closed','conditional','open')),
    executable_detail       TEXT,
    -- Per-layer L0..L6
    layer_l0                TEXT NOT NULL CHECK (layer_l0 IN ('pass','fail','n/a')),
    layer_l0_detail         TEXT,
    layer_l1                TEXT NOT NULL CHECK (layer_l1 IN ('pass','fail','n/a')),
    layer_l1_detail         TEXT,
    layer_l2                TEXT NOT NULL CHECK (layer_l2 IN ('pass','fail','n/a')),
    layer_l2_detail         TEXT,
    layer_l3                TEXT NOT NULL CHECK (layer_l3 IN ('pass','fail','n/a')),
    layer_l3_detail         TEXT,
    layer_l4                TEXT NOT NULL CHECK (layer_l4 IN ('pass','fail','n/a')),
    layer_l4_detail         TEXT,
    layer_l5                TEXT NOT NULL CHECK (layer_l5 IN ('pass','fail','n/a')),
    layer_l5_detail         TEXT,
    layer_l6                TEXT NOT NULL CHECK (layer_l6 IN ('pass','fail','n/a')),
    layer_l6_detail         TEXT,
    -- Aggregate AP counts (dense roster reconstructed via JOIN).
    error_count             INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    warning_count           INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    -- Top-level verdict
    load_bearing            BOOLEAN NOT NULL,
    audited_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-AP findings (sparse — only Error/Warning materialise).
CREATE TABLE cog_audit_findings (
    version_id  BIGINT NOT NULL REFERENCES cog_audit_records(version_id) ON DELETE CASCADE,
    ap_id       TEXT NOT NULL CHECK (ap_id ~ '^AP-[0-9]{3}$'),
    verdict     TEXT NOT NULL CHECK (verdict IN ('ok','warning','error')),
    message     TEXT,
    cite        TEXT,
    PRIMARY KEY (version_id, ap_id)
);

CREATE INDEX cog_audit_findings_ap_idx          ON cog_audit_findings (ap_id);
CREATE INDEX cog_audit_findings_verdict_idx     ON cog_audit_findings (verdict);
CREATE INDEX cog_audit_records_load_bearing_idx ON cog_audit_records (load_bearing);
CREATE INDEX cog_audit_records_error_idx        ON cog_audit_records (error_count DESC);

-- Helper for the AP-009 transitive poset-violation observatory:
-- maps Lifecycle textual form to a partial-order rank.  Higher rank
-- citing lower rank is an AP-009 violation.
--   T = 6, D = C = P = 5, H = 2, I = 1, ✗ = 0.
CREATE OR REPLACE FUNCTION lifecycle_rank(lc TEXT) RETURNS INTEGER AS $$
    SELECT CASE
        WHEN lc LIKE 'Theorem%' THEN 6
        WHEN lc = 'Definition'  THEN 5
        WHEN lc = 'Conditional' THEN 5
        WHEN lc = 'Postulate'   THEN 5
        WHEN lc = 'Hypothesis'  THEN 2
        WHEN lc = 'Interpretation' THEN 1
        WHEN lc = 'Retracted'   THEN 0
        ELSE 0
    END
$$ LANGUAGE SQL IMMUTABLE STRICT;

COMMENT ON TABLE cog_audit_records IS
    'Per-version CVE audit verdict produced by PublishService Phase 5b. spec §6.1.7';
COMMENT ON TABLE cog_audit_findings IS
    'Sparse per-AP findings — only Error/Warning materialise; Ok densified at read time';
COMMENT ON FUNCTION lifecycle_rank IS
    'CVE poset rank — used by audit/lifecycle.vr::detect_poset_violations';
