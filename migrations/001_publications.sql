BEGIN;
CREATE TABLE public.verum_publications (
    record_key text COLLATE "C" PRIMARY KEY
        CHECK (record_key ~ '^[0-9a-f]{64}$'),
    record bytea NOT NULL
        CHECK (octet_length(record) BETWEEN 48 AND 100663344)
);
COMMENT ON TABLE public.verum_publications IS
    'Immutable complete publication records. Runtime roles require SELECT and INSERT only.';
COMMIT;
