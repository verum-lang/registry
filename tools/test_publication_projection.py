"""Contracts for the actual migration and prepared publication INSERT."""

import json
from pathlib import Path

from publication_test_records import literal, publication
from test_publication_postgres_schema import production_statements


ROOT = Path(__file__).resolve().parents[1]


def check_projection(sql):
    migration = (ROOT / "migrations/002_publication_projection.sql").read_text()
    first = publication("1.0.0", b"original")
    # Refusing an old populated store is transactional: its rows and schema
    # remain v1. An upgrade cannot acknowledge a partially indexed catalog.
    sql("DROP TABLE public.verum_publications; " + (ROOT / "migrations/001_publications.sql").read_text())
    sql("INSERT INTO public.verum_publications (record_key,record) VALUES (" +
        literal(first.key) + ",decode(" + literal(first.record.hex()) + ",'hex'));")
    refused = sql(migration, check=False)
    assert refused.returncode != 0 and "requires verified migration" in refused.stderr
    assert sql("SELECT count(*) FROM pg_catalog.pg_attribute WHERE attrelid = "
               "'public.verum_publications'::regclass AND attname='index_entry';").stdout.strip() == "0"
    assert bytes.fromhex(sql("SELECT encode(record,'hex') FROM public.verum_publications;").stdout) == first.record
    sql("DELETE FROM public.verum_publications; " + migration +
        " GRANT SELECT,INSERT ON public.verum_publications TO registry_publisher;")
    print("PostgreSQL projection: populated v1 migration refused without changing bytes or schema", flush=True)

    _, insert = production_statements()
    prepare = "SET ROLE registry_publisher; PREPARE publication(text,bytea,text,text,text) AS " + insert + "; "

    def commit(candidate):
        return sql(prepare + "EXECUTE publication(" + candidate.arguments() + ");")

    assert commit(first).stdout.strip().endswith("1")
    for _ in range(2):
        assert not commit(first).stdout.strip().endswith("1")
    rival = publication("1.0.0", b"conflicting bytes")
    assert not commit(rival).stdout.strip().endswith("1")
    row = sql("SELECT encode(record,'hex'),release_name,release_version,index_entry "
              "FROM public.verum_publications;").stdout.strip().split("|", 3)
    assert row == [first.record.hex(), "widget", "1.0.0", first.projection]
    print("PostgreSQL projection: production INSERT retained one complete immutable winner on retry/conflict", flush=True)

    for statement in ("UPDATE public.verum_publications SET index_entry=index_entry;",
                      "DELETE FROM public.verum_publications;"):
        result = sql("SET ROLE registry_publisher; " + statement, check=False)
        assert result.returncode != 0 and "permission denied" in result.stderr

    second = publication("1.1.0", b"new version")
    entry = json.loads(second.projection)
    invalid = [None, "not json", "{}", "[]"]
    for field in entry:
        missing = dict(entry)
        del missing[field]
        invalid.append(json.dumps(missing))
        nulled = dict(entry, **{field: None})
        invalid.append(json.dumps(nulled))
    invalid += [json.dumps(dict(entry, version="9.0.0")), json.dumps(dict(entry, checksum="invalid")),
                json.dumps(dict(entry, yanked=True)), json.dumps(dict(entry, features=[]))]
    for damaged in invalid:
        fields = [literal(second.key), "decode(" + literal(second.record.hex()) + ",'hex')",
                  literal("widget"), literal("1.1.0"), "NULL" if damaged is None else literal(damaged)]
        result = sql(prepare + "EXECUTE publication(" + ",".join(fields) + ");", check=False)
        assert result.returncode != 0, damaged
        assert sql("SELECT count(*) FROM public.verum_publications;").stdout.strip() == "1"
    print(f"PostgreSQL projection: {len(invalid)} malformed projections atomically refused; no archive row escaped", flush=True)
    assert commit(second).stdout.strip().endswith("1")
    other = publication("1.0.0", b"other package", name="another")
    assert commit(other).stdout.strip().endswith("1")
    selected = sql("SELECT index_entry FROM public.verum_publications "
                   "WHERE release_name='widget' ORDER BY release_version;")
    assert [json.loads(line) for line in selected.stdout.splitlines()] == [json.loads(first.projection), json.loads(second.projection)]
    # Native hash indexing owns collision rechecks and permits long names.
    plan = sql("SET enable_seqscan=off; EXPLAIN SELECT index_entry FROM public.verum_publications "
               "WHERE release_name='widget';").stdout
    assert "verum_publications_name" in plan and "release_name = 'widget'" in plan
    print("PostgreSQL projection: indexed package lookup preserves names, versions, checksums and all features", flush=True)
    long_name = publication("1.0.0", b"long package name", name="w" * 4096)
    assert commit(long_name).stdout.strip().endswith("1")
    observed = sql("SELECT index_entry FROM public.verum_publications WHERE release_name=" + literal(long_name.metadata["name"]) + ";")
    assert observed.stdout.strip() == long_name.projection
    print("PostgreSQL projection: existing 4096-byte name contract retained", flush=True)
    sql("DELETE FROM public.verum_publications;")
