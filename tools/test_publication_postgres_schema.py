"""Check the production startup query against real PostgreSQL schema variants."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def production_statements():
    source = (ROOT / "src/node/publication_postgres_storage.vr").read_text()
    ready, = re.findall(r'let ready = connection\.query_all\(&("""[\s\S]*?"""|"[^"\n]*")\)\?;', source)
    insert, = re.findall(r'let insert = connection\.prepare\(&"([^"\n]*)"\)\?;', source)
    # Both are literal SQL from the actual adapter, not a Python reimplementation.
    return (ready[3:-3] if ready.startswith('"""') else ready[1:-1]), insert


def check_publication_schema(sql, run_storage=None):
    ready, insert = production_statements()
    migration = (ROOT / "migrations/001_publications.sql").read_text()
    plain = "CREATE TABLE public.verum_publications (record_key text NOT NULL, record bytea NOT NULL);"
    primary = "CREATE TABLE public.verum_publications (record_key text PRIMARY KEY, record bytea NOT NULL);"
    cases = (
        ("migration", migration, True),
        ("unique-constraint", plain + "ALTER TABLE public.verum_publications ADD UNIQUE (record_key);", True),
        ("unique-index", plain + "CREATE UNIQUE INDEX release_key ON public.verum_publications(record_key);", True),
        ("included-column", plain + "CREATE UNIQUE INDEX release_key ON public.verum_publications(record_key) INCLUDE (record);", True),
        ("reordered-columns", "CREATE TABLE public.verum_publications (record bytea NOT NULL, record_key text PRIMARY KEY);", True),
        ("nulls-not-distinct", plain + "CREATE UNIQUE INDEX release_key ON public.verum_publications(record_key) NULLS NOT DISTINCT;", True),
        ("unrelated-deferred-key", primary + "ALTER TABLE public.verum_publications ADD UNIQUE (record) DEFERRABLE INITIALLY DEFERRED;", True),
        ("extra-partial-index", primary + "CREATE UNIQUE INDEX partial_key ON public.verum_publications(record_key) WHERE record_key <> '';", True),
        ("missing-unique-key", plain, False),
        ("nonunique-index", plain + "CREATE INDEX release_key ON public.verum_publications(record_key);", False),
        ("partial-index", plain + "CREATE UNIQUE INDEX release_key ON public.verum_publications(record_key) WHERE record_key <> '';", False),
        ("expression-index", plain + "CREATE UNIQUE INDEX release_key ON public.verum_publications(lower(record_key));", False),
        ("composite-index", plain + "CREATE UNIQUE INDEX release_key ON public.verum_publications(record_key, record);", False),
        ("exclusion-key", plain + "ALTER TABLE public.verum_publications ADD EXCLUDE USING btree(record_key WITH =);", False),
        ("deferrable-immediate", plain + "ALTER TABLE public.verum_publications ADD UNIQUE (record_key) DEFERRABLE INITIALLY IMMEDIATE;", False),
        ("deferrable-deferred", plain + "ALTER TABLE public.verum_publications ADD UNIQUE (record_key) DEFERRABLE INITIALLY DEFERRED;", False),
        ("mixed-arbiters", primary + "ALTER TABLE public.verum_publications ADD UNIQUE (record_key) DEFERRABLE INITIALLY DEFERRED;", False),
    )
    mismatches = []
    try:
        for name, schema, accepted in cases:
            sql("DROP TABLE public.verum_publications; " + schema +
                " GRANT SELECT, INSERT ON public.verum_publications TO registry_publisher;")
            prefix = "SET ROLE registry_publisher; SET search_path = pg_catalog; "
            prepared = sql(prefix + "PREPARE publication(text,bytea) AS " + insert + "; SELECT 'prepared';")
            assert prepared.stdout.strip().endswith("prepared"), (name, prepared.stdout)
            observed = [line for line in sql(prefix + ready + ";").stdout.splitlines() if line != "SET"]
            actual = observed == ["1"]
            if actual != accepted:
                mismatches.append(name)
            # Independently ask PostgreSQL to exercise the real INSERT. Every
            # probe rolls back; no fake publication is part of startup itself.
            executed = sql(prefix + "BEGIN; PREPARE publication(text,bytea) AS " + insert +
                           "; EXECUTE publication(repeat('a',64),decode(repeat('00',48),'hex')); ROLLBACK;",
                           check=False)
            assert (executed.returncode == 0) == accepted, (name, executed.stdout, executed.stderr)
            print(f"PostgreSQL schema {name}: prepared=true startup={actual} insert={accepted}", flush=True)
            if run_storage is not None:
                run_storage(accepted)
            assert sql("SELECT count(*) FROM public.verum_publications;").stdout.strip() == "0"
    finally:
        sql("DROP TABLE public.verum_publications; " + migration +
            " GRANT SELECT, INSERT ON public.verum_publications TO registry_publisher;")
    assert not mismatches, "startup incorrectly accepts/refuses schemas: " + ", ".join(mismatches)
    print(f"PostgreSQL: production startup query matched actual INSERT compatibility for {len(cases)} schemas", flush=True)
    if run_storage is not None:
        print("PostgreSQL: actual Verum storage startup accepted/refused every schema without publishing rows", flush=True)
