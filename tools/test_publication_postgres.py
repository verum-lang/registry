#!/usr/bin/env python3
"""Run actual publishing against an isolated Docker PostgreSQL with SCRAM.

Uses a container-owned volume to test crash recovery. Removes only that
container and its anonymous volume on exit; no installed database is used.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from test_publication_http import TOKEN, envelope, write_credentials
from test_publication_storage import record, run
from test_publication_admission import COMMON, TRANSACTION, fixtures, stage_component, unpack_record
from test_publication_postgres_schema import check_publication_schema
from test_publication_projection import check_projection
from publication_test_records import publication, fixtures as storage_fixtures, write_fixtures

ROOT = Path(__file__).resolve().parents[1]



def remove_owned_container(container, owner, timeout):
    """Removal is restricted to this run's exact name and unpredictable label."""
    inspected = subprocess.run(["docker", "inspect", "--format",
        '{{index .Config.Labels "verum.registry-run-id"}}', container],
        capture_output=True, text=True, timeout=timeout)
    if inspected.returncode:
        if "no such object" in inspected.stderr.lower() or "no such container" in inspected.stderr.lower():
            return
        raise RuntimeError("could not confirm cleanup ownership for " + container + ": " + inspected.stderr)
    if inspected.stdout.strip() != owner:
        raise RuntimeError("refusing cleanup of a container with another owner: " + container)
    subprocess.run(["docker", "rm", "-fv", container], check=True,
                   stdout=subprocess.DEVNULL, timeout=timeout)
    print("PostgreSQL fixture: removed own container " + container, flush=True)


def check_uncommitted_visibility(container, sql, timeout):
    """A second writer waits on the unique key, then wins after a rollback."""
    key = publication("5.0.0", b"committed").key

    def insert(payload):
        return publication("5.0.0", payload).insert()

    def wait_session(predicate):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if sql("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE " + predicate).stdout.strip() == "1":
                return
            time.sleep(0.1)
        raise AssertionError("test writer failed to reach " + predicate)

    command = ["docker", "exec", "-i", container, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
               "-U", "registry_publisher", "-d", "registry_test"]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as first:
        try:
            first.stdin.write("SET application_name = 'publication_first'; BEGIN;\n" +
                              insert(b"rolled back") + "\n")
            first.stdin.flush()
            wait_session("application_name = 'publication_first' AND state = 'idle in transaction' "
                         "AND query LIKE 'INSERT INTO%'")
            assert sql(f"SELECT count(*) FROM public.verum_publications WHERE record_key = '{key}';").stdout.strip() == "0"
            with ThreadPoolExecutor(max_workers=1) as pool:
                contender = pool.submit(subprocess.run, command,
                    input="SET application_name = 'publication_contender'; " + insert(b"committed"),
                    text=True, capture_output=True, check=True, timeout=timeout * 2)
                try:
                    wait_session("application_name = 'publication_contender' AND wait_event_type = 'Lock'")
                finally:
                    first.communicate("ROLLBACK;\n", timeout=timeout)
                assert first.returncode == 0 and contender.result().stdout.strip() == "1"
        finally:
            if first.poll() is None:
                first.stdin.close()
                first.wait(timeout=timeout)
    observed = sql(f"SELECT encode(record,'hex') FROM public.verum_publications WHERE record_key = '{key}';")
    assert bytes.fromhex(observed.stdout) == publication("5.0.0", b"committed").record
    print("PostgreSQL SQL: uncommitted row invisible; waiting writer committed exact bytes after rollback", flush=True)


def check_pool_reconnect(container, sql, launch, timeout):
    """Terminate the sole checked-out connection while its INSERT waits on a publisher."""
    command = ["docker", "exec", "-i", container, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
               "-U", "registry_publisher", "-d", "registry_test"]
    def publisher_sql(query):
        return subprocess.run(command, input=query, text=True, capture_output=True,
                              check=True, timeout=10).stdout.strip()

    records = storage_fixtures()
    anchor, pending = records["anchor"].key, records["pending"].key
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as blocker:
        blocker.stdin.write("SET application_name = 'publication_pool_blocker'; BEGIN; " +
                            records["pending-block"].insert() + "\n")
        blocker.stdin.flush()
        with ThreadPoolExecutor(max_workers=1) as pool:
            client = pool.submit(launch)

            def wait_backend(previous=None):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if client.done():
                        raise AssertionError("Verum finished before a blocked INSERT: " + client.result())
                    query = """SELECT c.pid FROM pg_catalog.pg_stat_activity c
                        JOIN pg_catalog.pg_stat_activity b ON b.pid = ANY(pg_catalog.pg_blocking_pids(c.pid))
                        WHERE c.usename = 'registry_publisher' AND c.application_name = 'publication_pool_client'
                          AND b.usename = 'registry_publisher' AND b.application_name = 'publication_pool_blocker'
                          AND c.wait_event_type = 'Lock'"""
                    pid = publisher_sql(query)
                    if pid.isdigit() and pid != previous:
                        return pid
                    time.sleep(0.25)
                raise RuntimeError("publication INSERT did not wait on the test rollback")

            try:
                first = wait_backend()
                visible = publisher_sql("SELECT record_key FROM public.verum_publications;")
                assert visible == anchor
                # Only the fault is injected as the test administrator.
                assert sql(f"SELECT pg_catalog.pg_terminate_backend({first});").stdout.strip() == "t"
                replacement = wait_backend(previous=first)
                assert replacement != first
            finally:
                blocker.communicate("ROLLBACK;\n", timeout=10)
            assert blocker.returncode == 0
            assert client.result() == "postgres storage: discarded terminated backend and recovered in live pool"
    rows = publisher_sql("SELECT record_key, encode(record,'hex') FROM public.verum_publications ORDER BY record_key;")
    actual = {key: bytes.fromhex(value) for key, value in (line.split("|") for line in rows.splitlines())}
    assert actual == {anchor: records["anchor"].record, pending: records["pending"].record}
    print("PostgreSQL: terminated active INSERT, observed a different backend in the same pool, "
          "and verified both immutable records", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--image", default="postgres:17-alpine")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--docker-timeout", type=float, default=60,
                        help="deadline for each Docker command, not the SQL workflow")
    parser.add_argument("--startup-timeout", type=float, default=180,
                        help="readiness budget after each database start")
    parser.add_argument("--component", choices=("all", "storage", "transaction", "handler", "reconnect", "http", "sql", "schema", "schema-sql", "projection-sql"), default="all")
    options = parser.parse_args()
    executable = str(options.verum.resolve(strict=True))
    if not 0 < options.timeout <= 1800:
        parser.error("timeout must be between 0 and 1800 seconds")
    if not 0 < options.docker_timeout <= 300:
        parser.error("docker-timeout must be between 0 and 300 seconds")
    if not 0 < options.startup_timeout <= 600:
        parser.error("startup-timeout must be between 0 and 600 seconds")
    owner = uuid.uuid4().hex
    container = "verum-publication-" + owner[:12]
    with tempfile.TemporaryDirectory(prefix="registry-postgres-http-") as temporary:
        project = Path(temporary)
        environment = project / "postgres.env"
        environment.write_text("POSTGRES_USER=registry_admin\nPOSTGRES_DB=registry_test\n"
            + "POSTGRES_PASSWORD=" + secrets.token_hex(24) + "\n"
            + "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256\n")
        environment.chmod(0o600)
        # The running registry retains its configured address across a database crash.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        try:
            print("PostgreSQL fixture: starting own container " + container, flush=True)
            subprocess.run([
                "docker", "run", "-d", "--pull=never", "--name", container,
                "--label", "verum.registry-test=publication-http",
                "--label", "verum.registry-run-id=" + owner,
                "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
                "--publish", f"127.0.0.1:{port}:5432", "--env-file", str(environment), options.image,
            ], check=True, stdout=subprocess.DEVNULL, timeout=options.docker_timeout)

            def sql(query, check=True, timeout=None):
                return subprocess.run(["docker", "exec", "-i", container, "psql", "-X",
                    "-v", "ON_ERROR_STOP=1", "-U", "registry_admin", "-d", "registry_test", "-At"],
                    input=query, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
                    timeout=options.docker_timeout if timeout is None else timeout)

            def wait_database():
                deadline = time.monotonic() + options.startup_timeout
                while time.monotonic() < deadline:
                    # initdb briefly starts a Unix-socket-only server. Wait for
                    # the final TCP listener before installing application state.
                    try:
                        ready = subprocess.run(["docker", "exec", container, "pg_isready",
                            "-h", "127.0.0.1", "-U", "registry_admin", "-d", "registry_test"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=min(options.docker_timeout, 15, max(0.01, deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        continue
                    remaining = deadline - time.monotonic()
                    if ready.returncode == 0 and remaining > 0:
                        try:
                            if sql("SELECT 1;", check=False,
                                   timeout=min(options.docker_timeout, remaining)).returncode == 0:
                                break
                        except subprocess.TimeoutExpired:
                            continue
                    time.sleep(0.25)
                else:
                    logs = subprocess.run(["docker", "logs", "--tail", "40", container],
                                          capture_output=True, text=True, timeout=options.docker_timeout)
                    raise RuntimeError("isolated PostgreSQL did not start\n" + logs.stdout + logs.stderr)

            def restart_database():
                print("PostgreSQL fixture: crashing and restarting own database", flush=True)
                subprocess.run(["docker", "kill", "--signal", "KILL", container],
                               check=True, stdout=subprocess.DEVNULL, timeout=options.docker_timeout)
                subprocess.run(["docker", "start", container], check=True,
                               stdout=subprocess.DEVNULL, timeout=options.docker_timeout)
                wait_database()

            wait_database()
            for migration in ("001_publications.sql", "002_publication_projection.sql"):
                sql((ROOT / "migrations" / migration).read_text())
            password = secrets.token_hex(24)
            sql(f"CREATE ROLE registry_publisher LOGIN PASSWORD '{password}';"
                "GRANT USAGE ON SCHEMA public TO registry_publisher;"
                "GRANT SELECT, INSERT ON verum_publications TO registry_publisher;")
            for statement in ("DELETE FROM verum_publications;",
                              "UPDATE verum_publications SET record = record;"):
                denied = sql("SET ROLE registry_publisher; " + statement, check=False)
                assert denied.returncode != 0 and "permission denied" in denied.stderr
            address = subprocess.check_output(["docker", "port", container, "5432/tcp"],
                                              text=True, timeout=options.docker_timeout).strip()
            assert address == f"127.0.0.1:{port}"
            configuration = project / "connection.json"
            connection = {
                "container": container, "admin_user": "registry_admin", "database": "registry_test",
                "host": "127.0.0.1", "port": port,
                "user": "registry_publisher", "password": password,
            }
            configuration.write_text(json.dumps(connection))
            configuration.chmod(0o600)
            print("PostgreSQL: SCRAM test database and restricted publisher ready", flush=True)

            record_fixtures = project / "record-fixtures"
            write_fixtures(record_fixtures)
            records = storage_fixtures()

            def stage_storage(source, fixture):
                stage_component(source, COMMON + TRANSACTION, fixture)
                shutil.copyfile(ROOT / "tests/publication_storage_fixture.vr",
                                source / "src/node/publication_storage_fixture.vr")

            def pg_environment():
                return {"VERUM_PG_TEST_FIXTURES": str(record_fixtures), **{"VERUM_PG_TEST_" + key.upper(): str(connection[key])
                        for key in ("host", "port", "user", "password", "database")}}
            if options.component in ("all", "projection-sql"):
                check_projection(sql)
            if options.component in ("all", "schema", "schema-sql", "projection-sql"):
                probe_schema = None
                if options.component not in ("schema-sql", "projection-sql"):
                    source = project / "schema-test"
                    stage_storage(source, "postgres_publication_schema")
                    def probe_schema(accepted):
                        output = run([executable, "run", "--tier", "interpret"], source, options.timeout,
                                     {**pg_environment(), "VERUM_PG_SCHEMA_ACCEPTED": "yes" if accepted else "no",
                                      "VERUM_NO_OBJECT_CACHE": "1"})
                        assert output == ("postgres schema: accepted" if accepted else "postgres schema: refused"), output
                check_publication_schema(sql, probe_schema)
            if options.component in ("all", "sql", "storage", "projection-sql"):
                check_uncommitted_visibility(container, sql, options.docker_timeout)
                if options.component in ("sql", "projection-sql"):
                    restart_database()
                    recovered = sql("SELECT encode(record,'hex') FROM public.verum_publications "
                                    f"WHERE record_key = '{publication('5.0.0', b'committed').key}';")
                    assert bytes.fromhex(recovered.stdout) == publication("5.0.0", b"committed").record
                    assert sql("SELECT index_entry FROM public.verum_publications;").stdout.strip() == publication("5.0.0", b"committed").projection
                    print("PostgreSQL SQL: committed row survived unclean server restart", flush=True)
                sql(f"DELETE FROM public.verum_publications WHERE record_key = '{publication('5.0.0', b'committed').key}';")
            if options.component in ("all", "storage"):
                source = project / "storage-test"
                stage_storage(source, "postgres_publication_storage")
                def phase(name):
                    return run([executable, "run", "--tier", "interpret"], source, options.timeout,
                               {**pg_environment(), "VERUM_PG_STORAGE_PHASE": name, "VERUM_NO_OBJECT_CACHE": "1"})

                expected = "postgres storage: durable bytes, exact retry and conflict passed"
                assert phase("write") == expected
                print("PostgreSQL: Verum created and read the publication", flush=True)
                restart_database()
                assert phase("read") == expected
                def stored(key):
                    return bytes.fromhex(sql(
                        f"SELECT encode(record, 'hex') FROM verum_publications WHERE record_key = '{key}';").stdout.strip())
                assert stored(records["large"].key) == records["large"].record
                print("PostgreSQL: Verum read after database crash, exact retry and differing bytes refused", flush=True)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(phase, ("race-a", "race-b")))
                assert sorted(outcomes) == ["postgres storage: race conflict", "postgres storage: race created"]
                assert stored(records["race-a"].key) in (records["race-a"].record, records["race-b"].record)
                # Keep the outer framing length valid while corrupting a checksum-covered byte.
                sql("UPDATE public.verum_publications SET record = set_byte(record,48,255) "
                    f"WHERE record_key = '{records['large'].key}';")
                assert phase("corrupt") == "postgres storage: corrupt row refused"
                damaged = bytearray(records["large"].record)
                damaged[48] = 255
                assert stored(records["large"].key) == damaged
                print("PostgreSQL: competing Verum writers and corruption refusal passed", flush=True)
                sql("DELETE FROM verum_publications;")
            if options.component in ("all", "transaction"):
                source = project / "transaction-test"
                stage_component(source, COMMON + TRANSACTION, "publication_commit")
                data = source / "fixtures"
                data.mkdir()
                fixtures(data)

                def transaction(phase):
                    return run([executable, "run", "--tier", "interpret"], source, options.timeout,
                               {**pg_environment(), "VERUM_PUBLICATION_TEST_BACKEND": "postgres",
                                "VERUM_PUBLICATION_STORE": str(source), "VERUM_PUBLICATION_FIXTURES": str(data),
                                "VERUM_PUBLICATION_PHASE": phase, "VERUM_NO_OBJECT_CACHE": "1"})

                assert transaction("create") == "publication-commit: created"
                key = sql("SELECT record_key FROM public.verum_publications;").stdout.strip()
                assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
                def inspect_record():
                    return bytes.fromhex(sql("SELECT encode(record,'hex') FROM public.verum_publications;").stdout)
                original = inspect_record()
                accepted = source / (key + ".publication")
                accepted.write_bytes(original)
                provenance, metadata, archive = unpack_record(accepted)
                assert provenance[:5] == ["alice", "active", "local", "exact", "widget"]
                assert metadata["version"] == "1.2.3" and archive == (data / "readme.gz").read_bytes()
                restart_database()
                assert transaction("restart") == "publication-commit: restart and conflicts"
                assert inspect_record() == original
                sql("UPDATE public.verum_publications SET record = substring(record FOR octet_length(record) - 1);")
                assert transaction("corrupt") == "publication-commit: corruption refused"
                assert inspect_record() == original[:-1]
                sql("DELETE FROM public.verum_publications;")
                print("PostgreSQL: authenticated Verum preparation, admission, restart, retry and conflict passed", flush=True)
            if options.component in ("all", "reconnect"):
                source = project / "reconnect-test"
                stage_storage(source, "postgres_publication_reconnect")
                def reconnect():
                    return run([executable, "run", "--tier", "interpret"], source, options.timeout,
                               {**pg_environment(), "VERUM_NO_OBJECT_CACHE": "1"})
                check_pool_reconnect(container, sql, reconnect, options.timeout)
                sql("DELETE FROM public.verum_publications;")
            if options.component in ("all", "handler"):
                source = project / "handler-test"
                modules = COMMON + TRANSACTION + ("node/publication_credentials_file", "node/publication_advisories", "node/publication_service")
                stage_component(source, modules, "postgres_publication_handler")
                fixtures(source)
                write_credentials(source / "credentials.json")
                archive = (source / "readme.gz").read_bytes()
                checksum = hashlib.sha256(archive).hexdigest()
                metadata = {"name": "widget", "version": "1.2.3", "description": None, "authors": [],
                            "license": None, "repository": None, "homepage": None, "keywords": [],
                            "categories": [], "readme": None, "dependencies": {}, "features": {},
                            "checksum": checksum}
                for file, value in (("release", metadata), ("unowned", {**metadata, "name": "unowned-widget"}),
                                    ("conflict", {**metadata, "readme": "# Widget\n"})):
                    (source / (file + ".bin")).write_bytes(envelope(value, archive))

                def handler(phase):
                    output = run([executable, "run", "--tier", "interpret"], source, options.timeout,
                                 {**pg_environment(), "VERUM_PG_TEST_TOKEN": TOKEN,
                                  "VERUM_PG_HANDLER_PHASE": phase, "VERUM_NO_OBJECT_CACHE": "1"})
                    receipt, info = [json.loads(line) for line in output.splitlines()]
                    assert receipt == {"name": "widget", "version": "1.2.3", "checksum": checksum}
                    assert all(info[key] == value for key, value in metadata.items())
                    assert (source / "download.gz").read_bytes() == archive
                    return info

                initial = handler("create")
                key = sql("SELECT record_key FROM public.verum_publications;").stdout.strip()
                assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
                def release_bytes():
                    return bytes.fromhex(sql("SELECT encode(record,'hex') FROM public.verum_publications;").stdout)
                original = release_bytes()
                snapshot = source / (key + ".publication")
                snapshot.write_bytes(original)
                provenance, stored_metadata, stored_archive = unpack_record(snapshot)
                assert stored_metadata == metadata and stored_archive == archive
                assert provenance[:5] == ["alice", "active", "local", "exact", "widget"]
                assert initial["published_at"] == int(provenance[5])
                print("PostgreSQL handler: bearer refusals, 201, metadata and exact gzip passed", flush=True)
                restart_database()
                assert handler("restart") == initial
                assert release_bytes() == original
                sql("DELETE FROM public.verum_publications;")
                print("PostgreSQL handler: restart, 200 retry, 409 conflict and exact download passed", flush=True)
            if options.component in ("all", "http"):
                subprocess.run([sys.executable, str(ROOT / "tools/test_publication_http.py"), executable,
                    "--timeout", str(options.timeout), "--postgres-config", str(configuration)], check=True)
        finally:
            remove_owned_container(container, owner, options.docker_timeout)


if __name__ == "__main__":
    main()
