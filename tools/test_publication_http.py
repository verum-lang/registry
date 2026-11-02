#!/usr/bin/env python3
"""Check authenticated publishing and restart through the actual Verum listener."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from test_publication_admission import ROOT, unpack_record
from test_publication_storage import run

TOKEN = "vrp1_" + bytes(range(32)).hex()
MEDIA_TYPE = "application/vnd.verum.cog-publish.v1"


def write_credentials(credentials):
    credentials.write_text(json.dumps({"version": 1,
        "principals": [{"id": "alice", "grants": [{"authority": "local", "names": [{"exact": "widget"}]}]}],
        "credentials": [{"id": "active", "principal": "alice", "active": True,
                         "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest()}]}))


def envelope(metadata, content):
    encoded = json.dumps(metadata, separators=(",", ":")).encode()
    return len(encoded).to_bytes(4, "little") + encoded + len(content).to_bytes(8, "little") + content


def package_profile(profile):
    """The CLI resolves its OS cache and signing keys inside this disposable client profile."""
    profile.mkdir()
    return {"HOME": str(profile), "XDG_CACHE_HOME": str(profile / "cache"),
            "XDG_CONFIG_HOME": str(profile / "config"), "LOCALAPPDATA": str(profile / "local"),
            "APPDATA": str(profile / "roaming"), "USERPROFILE": str(profile), "NO_COLOR": "1",
            "HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1",
            "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}


def check_installed(consumer, profile, base, digest, archive):
    artifact, = profile.rglob("widget-1.2.3.tar.gz")
    assert artifact.read_bytes() == archive
    manifest = tomllib.loads((consumer / "Verum.toml").read_text())
    assert manifest["dependencies"]["widget"] == "1.2.3"
    lockfile, = [p for p in consumer.iterdir() if p.name.lower() == "verum.lock"]
    entry, = tomllib.loads(lockfile.read_text())["packages"]
    assert entry["name"] == "widget" and entry["version"] == "1.2.3" and entry["checksum"] == digest
    assert entry["source"] == {"type": "registry", "registry": base, "version": "1.2.3"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--postgres-config", type=Path,
                        help="private configuration from test_publication_postgres.py")
    options = parser.parse_args()
    if not 0 < options.timeout <= 1800:
        parser.error("timeout must be between 0 and 1800 seconds")
    executable = str(options.verum.resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix="registry-publication-http-") as temporary:
        project = Path(temporary)
        storage = project / "store"
        storage.mkdir()
        reports = project / "reports"
        reports.mkdir()
        credentials = project / "credentials.json"
        write_credentials(credentials)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        client = build_opener(ProxyHandler({}))
        environment = {**os.environ, "NO_COLOR": "1", "VERUM_NO_OBJECT_CACHE": "1",
                       "VERUM_REGISTRY_LISTEN": f"127.0.0.1:{port}",
                       "VERUM_REGISTRY_STORAGE": "files", "VERUM_REGISTRY_ADVISORIES": str(reports),
                       "VERUM_REGISTRY_STORE": str(storage), "VERUM_REGISTRY_CREDENTIALS": str(credentials),
                       "VERUM_REGISTRY_AUTHORITY": "local", "VERUM_REGISTRY_OWNED_NAMES": "widget"}

        postgres = None
        if options.postgres_config:
            postgres = json.loads(options.postgres_config.read_text())
            container = postgres["container"]
            label = subprocess.check_output(["docker", "inspect", "--format",
                '{{index .Config.Labels "verum.registry-test"}}', container], text=True).strip()
            if label != "publication-http":
                raise RuntimeError("refusing fault injection outside an isolated publication test container")
            environment["VERUM_REGISTRY_STORAGE"] = "postgres"
            environment["VERUM_REGISTRY_PG_TLS"] = "disable"
            environment["VERUM_REGISTRY_PG_CONNECTIONS"] = "2"
            for key in ("host", "port", "user", "password", "database"):
                environment["VERUM_REGISTRY_PG_" + key.upper()] = str(postgres[key])

        def sql(query):
            return subprocess.check_output(["docker", "exec", "-i", postgres["container"],
                "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", postgres["admin_user"],
                "-d", postgres["database"], "-At"], input=query, text=True, stderr=subprocess.PIPE).strip()

        def stored_keys():
            if postgres:
                output = sql("SELECT record_key FROM verum_publications ORDER BY record_key;")
                return output.splitlines() if output else []
            return sorted(path.stem for path in storage.glob("*.publication"))

        def stored_bytes(key):
            assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
            if postgres:
                return bytes.fromhex(sql(f"SELECT encode(record, 'hex') FROM verum_publications WHERE record_key = '{key}';"))
            return (storage / (key + ".publication")).read_bytes()

        def corrupt_record(key, contents):
            assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
            if postgres:
                sql(f"UPDATE verum_publications SET record = decode('{contents.hex()}', 'hex') WHERE record_key = '{key}';")
            else:
                (storage / (key + ".publication")).write_bytes(contents)

        def restart_database():
            if not postgres:
                return
            # Crash the test database after an acknowledged publication. Its
            # container-owned volume survives, so this exercises WAL recovery.
            subprocess.run(["docker", "kill", "--signal", "KILL", postgres["container"]],
                           check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["docker", "start", postgres["container"]],
                           check=True, stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if sql("SELECT 1;") == "1":
                        return
                except subprocess.CalledProcessError:
                    pass
                time.sleep(0.25)
            raise RuntimeError("test PostgreSQL did not recover after crash")

        def request(path, body=None, authenticated=False, content_type=MEDIA_TYPE, timeout=120):
            headers = {"Content-Type": content_type} if body is not None else {}
            if authenticated:
                headers["Authorization"] = f"Bearer {TOKEN}"
            try:
                response = client.open(Request(base + path, body, headers), timeout=timeout)
            except HTTPError as error:
                response = error
            with response:
                payload = response.read()
                assert response.headers.get("Content-Length") == str(len(payload))
                return response.status, response.headers, payload

        def expect_status(expected, path, body=None, authenticated=False):
            status, headers, payload = request(path, body, authenticated)
            assert status == expected, f"{path}: expected {expected}, got {status}: {payload!r}"
            return headers, payload

        process = None
        output = project / "server.log"

        def stop():
            nonlocal process
            if process is not None:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                process = None

        def start():
            nonlocal process
            with output.open("ab") as log:
                process = subprocess.Popen([executable, "run", "--tier", "interpret", "--", "serve-publications"], cwd=ROOT,
                                           stdout=log, stderr=log, env=environment, start_new_session=True)
            deadline = time.monotonic() + options.timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"listener exited {process.returncode}\n" + output.read_text()[-24000:])
                try:
                    status, headers, body = request("/api/v1/cogs/publish", timeout=1)
                    if status == 405 and headers.get("Allow") == "POST" and body == b"publication request refused":
                        return
                except (URLError, ConnectionError, TimeoutError):
                    pass
                time.sleep(0.2)
            raise RuntimeError("listener startup timed out\n" + output.read_text()[-24000:])

        try:
            start()
            print("publication HTTP: listener ready", flush=True)
            expect_status(404, "/api/v1/cogs/widget/1.2.3")
            expect_status(401, "/api/v1/cogs/publish", b"invalid")
            # The first four bytes declare the metadata size. ASCII garbage
            # declares an oversized size; a short length field is truncated.
            expect_status(413, "/api/v1/cogs/publish", b"invalid", True)
            expect_status(400, "/api/v1/cogs/publish", b"\x00\x00\x00", True)
            assert stored_keys() == []

            # This produces the same public CLI archive/envelope/receipt path
            # used by developers. All registry access is pinned to this listener.
            publisher = project / "publisher"
            (publisher / "src").mkdir(parents=True)
            (publisher / "Verum.toml").write_text(
                f'[cog]\nname="widget"\nversion="1.2.3"\nedition="2026"\n'
                f'\n[registry]\nindex="{base}"\n')
            (publisher / "src/main.vr").write_text('module widget.main;\nfn main() { print(42); }\n')
            (publisher / "README.md").write_text("# Widget\n")
            run([executable, "package", "publish", "--allow-dirty"], publisher, options.timeout,
                {**package_profile(project / "publisher-profile"), "VERUM_REGISTRY_TOKEN": TOKEN})
            accepted, = stored_keys()
            original = stored_bytes(accepted)
            snapshot = project / (accepted + ".publication")
            snapshot.write_bytes(original)
            provenance, source_metadata, archive = unpack_record(snapshot)
            assert provenance[:5] == ["alice", "active", "local", "exact", "widget"]
            status, headers, downloaded = request("/api/v1/cogs/widget/1.2.3/download")
            assert status == 200 and headers["Content-Type"] == "application/gzip"
            assert downloaded == archive
            status, headers, body = request("/api/v1/cogs/widget/1.2.3")
            metadata = json.loads(body)
            assert status == 200 and headers["Content-Type"] == "application/json"
            assert all(metadata[key] == value for key, value in source_metadata.items())
            assert metadata["published_at"] == int(provenance[5])
            assert metadata["signature"] is None and metadata["proofs"] is None
            print("publication HTTP: real CLI publish and exact metadata/download passed", flush=True)

            report = {"package": "widget", "version": "1.2.3", "vulnerabilities": []}
            digest = source_metadata["checksum"]
            (reports / f"{accepted}-{digest}.json").write_text(json.dumps(report))
            consumer = project / "consumer"
            consumer.mkdir()
            (consumer / "Verum.toml").write_text(
                f'[cog]\nname="consumer"\nversion="1.0.0"\nedition="2026"\n[registry]\nindex="{base}"\n')
            profile = project / "consumer-profile"
            run([executable, "package", "install", "widget", "--version", "1.2.3"],
                consumer, options.timeout, package_profile(profile))
            check_installed(consumer, profile, base, digest, archive)
            print("publication HTTP: fresh package client installed exact archive and lock entry", flush=True)

            status, _, body = request("/api/v1/cogs/publish", envelope(source_metadata, archive), True)
            assert status == 200 and json.loads(body)["checksum"] == source_metadata["checksum"]
            # A valid token grants only configured names. Even a well-framed
            # request must be refused before any immutable record is created.
            forbidden = {**source_metadata, "name": "unowned-widget"}
            expect_status(403, "/api/v1/cogs/publish", envelope(forbidden, archive), True)
            assert stored_keys() == [accepted]
            corrupted = archive[:-1] + bytes([archive[-1] ^ 1])
            expect_status(422, "/api/v1/cogs/publish", envelope(source_metadata, corrupted), True)
            conflicting = {**source_metadata,
                           "readme": None if source_metadata.get("readme") is not None else "# Widget\n"}
            assert request("/api/v1/cogs/publish", envelope(conflicting, archive), True)[0] == 409
            assert stored_bytes(accepted) == original
            restart_database()
            if postgres:
                # The live application's cached socket died with PostgreSQL.
                # A failure must discard it; the next request must reconnect.
                status, _, recovered = request("/api/v1/cogs/widget/1.2.3/download")
                assert status in (200, 500)
                if status == 500:
                    status, _, recovered = request("/api/v1/cogs/widget/1.2.3/download")
                assert status == 200 and recovered == archive
                print("publication HTTP: database crash recovery and pool reconnect passed", flush=True)
            stop()
            start()
            assert request("/api/v1/cogs/widget/1.2.3/download")[2] == archive
            assert request("/api/v1/cogs/publish", envelope(source_metadata, archive), True)[0] == 200
            corrupt_record(accepted, original[:-1])
            assert request("/api/v1/cogs/widget/1.2.3/download")[0] == 500
            assert request("/api/v1/cogs/publish", envelope(source_metadata, archive), True)[0] == 500
            assert stored_bytes(accepted) == original[:-1]
            print("publication HTTP: retry, conflict, restart and corruption refusals passed", flush=True)
        except Exception as error:
            raise RuntimeError(f"{error}\n" + output.read_text(errors="replace")[-24000:]) from error
        finally:
            stop()


if __name__ == "__main__":
    main()
