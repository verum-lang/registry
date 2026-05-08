-- =============================================================================
-- 0007_sbom.sql — SBOM artifact pointers (REG-8)
-- =============================================================================
--
-- Adds SBOM-related columns to `versions`.  The actual SBOM bytes
-- live in the object store (S3) at deterministic keys; the columns
-- here record the SHA-256 hashes for tamper-detection at fetch time
-- and a generation timestamp for audit.
--
-- Two formats: CycloneDX 1.5 (community standard, NTIA-aligned) and
-- SPDX 2.3 (Linux-Foundation, EU CRA-aligned).  Both populated on
-- every successful publish from REG-8 onward.
-- =============================================================================

ALTER TABLE versions
    ADD COLUMN sbom_cyclonedx_sha256  TEXT,
    ADD COLUMN sbom_spdx_sha256       TEXT,
    ADD COLUMN sbom_generated_at      TIMESTAMPTZ;

COMMENT ON COLUMN versions.sbom_cyclonedx_sha256 IS
  'SHA-256 (hex) of the CycloneDX 1.5 SBOM JSON bytes; NULL pre-REG-8';
COMMENT ON COLUMN versions.sbom_spdx_sha256 IS
  'SHA-256 (hex) of the SPDX 2.3 SBOM JSON bytes; NULL pre-REG-8';
COMMENT ON COLUMN versions.sbom_generated_at IS
  'Timestamp at which both SBOMs were generated; NULL pre-REG-8';

-- Index supports the audit query "find cogs whose SBOM is older than N days"
-- (used by the periodic SBOM-staleness reconciler that re-runs SBOM
-- generation when a dependency's hash changes upstream).
CREATE INDEX versions_sbom_generated_at_idx
    ON versions (sbom_generated_at)
    WHERE sbom_generated_at IS NOT NULL;
