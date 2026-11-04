BEGIN;
-- A populated v1 store needs a verified record-by-record migration. Do not
-- silently hide old publications behind NULL catalog fields or synthesize
-- metadata from an unrelated catalog. Refusal leaves v1 entirely unchanged.
LOCK TABLE public.verum_publications IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.verum_publications) THEN
        RAISE EXCEPTION 'publication projection requires verified migration of existing records';
    END IF;
END
$$;
ALTER TABLE public.verum_publications
    ADD COLUMN release_name text COLLATE "C" NOT NULL,
    ADD COLUMN release_version text COLLATE "C" NOT NULL,
    ADD COLUMN index_entry text NOT NULL,
    ADD CONSTRAINT publication_projection_shape CHECK (
        octet_length(release_name) BETWEEN 1 AND 4096
        AND octet_length(release_version) BETWEEN 1 AND 4096
        AND octet_length(index_entry) BETWEEN 1 AND 1048576
        AND jsonb_typeof(index_entry::jsonb) = 'object'
        AND index_entry::jsonb ?& ARRAY['version', 'checksum', 'features', 'yanked']
        AND jsonb_typeof(index_entry::jsonb -> 'version') = 'string'
        AND index_entry::jsonb ->> 'version' = release_version
        AND jsonb_typeof(index_entry::jsonb -> 'checksum') = 'string'
        AND index_entry::jsonb ->> 'checksum' ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(index_entry::jsonb -> 'features') = 'object'
        AND index_entry::jsonb -> 'yanked' = 'false'::jsonb
    );
-- Native equality indexing supports the existing 4096-byte name contract.
-- PostgreSQL owns hash collisions and their equality rechecks.
CREATE INDEX verum_publications_name ON public.verum_publications USING HASH (release_name);
COMMENT ON COLUMN public.verum_publications.index_entry IS
    'Immutable source version projection derived from the same admitted record as bytea. No yank operation is implemented.';
COMMIT;
