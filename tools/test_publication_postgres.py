#!/usr/bin/env python3
"""Run actual publishing against an isolated Docker PostgreSQL with SCRAM.

Uses a container-owned volume to test crash recovery. Removes only that
container and its anonymous volume on exit; no installed database is used.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from test_publication_storage import record, run
from test_publication_admission import COMMON, TRANSACTION, fixtures, stage_component, unpack_record

ROOT = Path(__file__).resolve().parents[1]


def check_uncommitted_visibility(container, sql):
    """A second writer waits on the unique key, then wins after a rollback."""
    key = "b" * 64

    def insert(payload):
        data = record(key, payload).hex()
        return ("INSERT INTO public.verum_publications (record_key, record) "
                f"VALUES ('{key}', decode('{data}', 'hex')) "
                "ON CONFLICT (record_key) DO NOTHING RETURNING 1;")

    def wait_session(predicate):
        deadline = time.monotonic() + 15
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
                    text=True, capture_output=True, check=True, timeout=25)
                try:
                    wait_session("application_name = 'publication_contender' AND wait_event_type = 'Lock'")
                finally:
                    first.communicate("ROLLBACK;\n", timeout=10)
                assert first.returncode == 0 and contender.result().stdout.strip() == "1"
        finally:
            if first.poll() is None:
                first.stdin.close()
                first.wait(timeout=10)
    observed = sql(f"SELECT encode(record,'hex') FROM public.verum_publications WHERE record_key = '{key}';")
    assert bytes.fromhex(observed.stdout) == record(key, b"committed")
    print("PostgreSQL SQL: uncommitted row invisible; waiting writer committed exact bytes after rollback", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--image", default="postgres:17-alpine")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--component", choices=("all", "storage", "transaction", "http", "sql"), default="all")
    options = parser.parse_args()
    executable = str(options.verum.resolve(strict=True))
    if not 0 < options.timeout <= 1800:
        parser.error("timeout must be between 0 and 1800 seconds")
    container = None
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
            container = subprocess.check_output([
                "docker", "run", "-d", "--pull=never",
                "--name", "verum-publication-" + uuid.uuid4().hex[:12],
                "--label", "verum.registry-test=publication-http",
                "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
                "--publish", f"127.0.0.1:{port}:5432", "--env-file", str(environment), options.image,
            ], text=True).strip()

            def sql(query, check=True):
                return subprocess.run(["docker", "exec", "-i", container, "psql", "-X",
                    "-v", "ON_ERROR_STOP=1", "-U", "registry_admin", "-d", "registry_test", "-At"],
                    input=query, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)

            def wait_database():
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    # initdb briefly starts a Unix-socket-only server. Wait for
                    # the final TCP listener before installing application state.
                    ready = subprocess.run(["docker", "exec", container, "pg_isready",
                        "-h", "127.0.0.1", "-U", "registry_admin", "-d", "registry_test"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                    if ready.returncode == 0 and sql("SELECT 1;", check=False).returncode == 0:
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("isolated PostgreSQL did not start")

            def restart_database():
                subprocess.run(["docker", "kill", "--signal", "KILL", container],
                               check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["docker", "start", container], check=True, stdout=subprocess.DEVNULL)
                wait_database()

            wait_database()
            sql((ROOT / "migrations/001_publications.sql").read_text())
            password = secrets.token_hex(24)
            sql(f"CREATE ROLE registry_publisher LOGIN PASSWORD '{password}';"
                "GRANT USAGE ON SCHEMA public TO registry_publisher;"
                "GRANT SELECT, INSERT ON verum_publications TO registry_publisher;")
            for statement in ("DELETE FROM verum_publications;",
                              "UPDATE verum_publications SET record = record;"):
                denied = sql("SET ROLE registry_publisher; " + statement, check=False)
                assert denied.returncode != 0 and "permission denied" in denied.stderr
            address = subprocess.check_output(["docker", "port", container, "5432/tcp"], text=True).strip()
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

            def pg_environment():
                return {"VERUM_PG_TEST_" + key.upper(): str(connection[key])
                        for key in ("host", "port", "user", "password", "database")}
            if options.component in ("all", "sql", "storage"):
                check_uncommitted_visibility(container, sql)
                if options.component == "sql":
                    restart_database()
                    recovered = sql("SELECT encode(record,'hex') FROM public.verum_publications "
                                    "WHERE record_key = repeat('b',64);")
                    assert bytes.fromhex(recovered.stdout) == record("b" * 64, b"committed")
                    print("PostgreSQL SQL: committed row survived unclean server restart", flush=True)
                sql("DELETE FROM public.verum_publications WHERE record_key = repeat('b',64);")
            if options.component in ("all", "storage"):
                source = project / "storage-test"
                modules = tuple(f"node/publication_{part}" for part in
                                ("storage_contract", "local_storage", "postgres_storage", "storage"))
                stage_component(source, modules, "postgres_publication_storage")
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
                assert stored("c" * 64) == record("c" * 64, bytes(i % 256 for i in range(10003)))
                print("PostgreSQL: Verum read after database crash, exact retry and differing bytes refused", flush=True)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(phase, ("race-a", "race-b")))
                assert sorted(outcomes) == ["postgres storage: race conflict", "postgres storage: race created"]
                assert stored("d" * 64) in (record("d" * 64, bytes([1, 2, 3])),
                                            record("d" * 64, bytes([4, 5, 6])))
                # Keep the outer framing length valid while corrupting a checksum-covered byte.
                sql("UPDATE public.verum_publications SET record = set_byte(record,48,255) "
                    "WHERE record_key = repeat('c',64);")
                assert phase("corrupt") == "postgres storage: corrupt row refused"
                damaged = bytearray(record("c" * 64, bytes(i % 256 for i in range(10003))))
                damaged[48] = 255
                assert stored("c" * 64) == damaged
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
            if options.component in ("all", "http"):
                subprocess.run([sys.executable, str(ROOT / "tools/test_publication_http.py"), executable,
                    "--timeout", str(options.timeout), "--postgres-config", str(configuration)], check=True)
        finally:
            if container:
                subprocess.run(["docker", "rm", "-fv", container], check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
