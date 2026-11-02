#!/usr/bin/env python3
"""Run ordinary package publish/install via a loopback transport to the real Weft handler."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import selectors
import secrets
import shutil
import tarfile
import signal
import subprocess
import tempfile
import threading

from test_publication_admission import COMMON, TRANSACTION, stage_component, unpack_record
from test_publication_http import TOKEN, check_installed, package_profile, write_credentials

META = "/api/v1/cogs/widget/1.2.3"
REPORT = "/api/v1/security/vulnerabilities/widget/1.2.3"
DOWNLOAD = META + "/download"


def exercise(exe, root, timeout, execute_installed=False, dependency_main=False):
    source = root / "handler"
    modules = COMMON + TRANSACTION + ("node/publication_credentials_file", "node/publication_advisories",
                                      "node/publication_service")
    stage_component(source, modules, "publication_install_bridge")
    (source / "store").mkdir()
    reports = source / "reports"
    reports.mkdir()
    write_credentials(source / "credentials.json")
    events = []
    damaged = False
    server = None
    with (root / "handler.stderr").open("w") as log, selectors.DefaultSelector() as selector:
        proc = subprocess.Popen([exe, "run", "--tier", "interpret"], cwd=source,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, bufsize=0,
                                env={**os.environ, "VERUM_NO_OBJECT_CACHE": "1", "NO_COLOR": "1"},
                                start_new_session=True)
        selector.register(proc.stdout, selectors.EVENT_READ)

        def line():
            if not selector.select(timeout):
                raise RuntimeError("Verum handler timed out")
            data = proc.stdout.readline().decode().strip()
            if not data:
                raise RuntimeError("Verum handler exited\n" + (root / "handler.stderr").read_text()[-5000:])
            return data

        class Transport(http.server.BaseHTTPRequestHandler):
            def relay(self):
                # The fixture owns HTTP framing only. Forward the client's path, body and authentication verbatim.
                (source / "request.path").write_text(self.path)
                (source / "request.media").write_text(self.headers.get("Content-Type", ""))
                (source / "request.authorization").write_text(self.headers.get("Authorization", ""))
                (source / "request.bin").write_bytes(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                proc.stdin.write(self.command.encode() + b"\n")
                marker = line()
                assert marker.startswith("response="), marker
                status = int(marker.split("=", 1)[1])
                body = (source / "response.bin").read_bytes()
                # Corrupt transport bytes after the handler only in the explicit checksum negative.
                if damaged and self.path == DOWNLOAD and status == 200:
                    body = body[:-1] + bytes([body[-1] ^ 1])
                events.append((self.path, status))
                self.send_response(status)
                self.send_header("Content-Type", (source / "response.media").read_text())
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = relay

            def log_message(self, fmt, *args):
                pass

        try:
            assert line() == "handler-ready"
            server = http.server.HTTPServer(("127.0.0.1", 0), Transport)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}"

            def project(label, name):
                directory = root / label
                directory.mkdir()
                (directory / "Verum.toml").write_text(
                    f'[cog]\nname="{name}"\nversion="1.2.3"\nedition="2026"\n[registry]\nindex="{base}"\n')
                return directory

            def invoke(directory, args, profile_env):
                env = {**os.environ, **profile_env}
                return subprocess.run([exe, "package", *args], cwd=directory, env=env,
                                      capture_output=True, text=True, timeout=timeout)

            publisher = project("publisher", "widget")
            (publisher / "src").mkdir()
            if not execute_installed or dependency_main:
                (publisher / "src/main.vr").write_text('module widget.main;\nfn main() { print(42); }\n')
            marker = "published-" + secrets.token_hex(12)
            exported = f'module widget.api;\npublic fn published_value() -> Text {{ "{marker}" }}\n'
            if execute_installed:
                (publisher / "src/api.vr").write_text(exported)
            outcome = invoke(publisher, ["publish", "--allow-dirty"],
                             {**package_profile(publisher / "profile"), "VERUM_REGISTRY_TOKEN": TOKEN})
            assert outcome.returncode == 0, outcome.stderr
            assert events == [("/api/v1/cogs/publish", 201)], events
            snapshot, = (source / "store").glob("*.publication")
            attribution, metadata, archive = unpack_record(snapshot)
            assert attribution[:5] == ["alice", "active", "local", "exact", "widget"]
            digest = hashlib.sha256(archive).hexdigest()
            assert metadata["checksum"] == digest
            report_file = reports / f"{snapshot.stem}-{digest}.json"
            empty = {"package": "widget", "version": "1.2.3", "vulnerabilities": []}
            finding = {"id": "TEST-1", "severity": "high", "title": "Fixture finding",
                       "description": "Independent test advisory", "patched_versions": ["1.2.4"]}

            def install(label, report, success=False):
                events.clear()
                if report is not None:
                    report_file.write_text(report if isinstance(report, str) else json.dumps(report))
                consumer = project(label, "consumer")
                manifest = consumer / "Verum.toml"
                before = manifest.read_bytes()
                env = package_profile(consumer / "profile")
                result = invoke(consumer, ["install", "widget", "--version", "1.2.3"], env)
                output = result.stdout + result.stderr
                assert (result.returncode == 0) == success, (label, output)
                expected = [(META, 200), (REPORT, 200 if success or damaged else 503)]
                if success or damaged:
                    expected.append((DOWNLOAD, 200))
                assert events == expected, (label, events, output)
                archives = list((consumer / "profile").rglob("widget-1.2.3.tar.gz"))
                lockfiles = [p for p in consumer.iterdir() if p.name.lower() == "verum.lock"]
                if not success:
                    assert manifest.read_bytes() == before and not lockfiles and not archives
                    assert "No known vulnerabilities" not in output or damaged
                    if damaged:
                        assert "checksum" in output.lower()
                    return
                check_installed(consumer, consumer / "profile", base, digest, archive)
                assert ("No known vulnerabilities" in output) == (report == empty)
                if report != empty:
                    assert finding["description"] in output

                return consumer, env

            if execute_installed:
                consumer, env = install("consumer-run", empty, True)
                cached, = (consumer / "profile").rglob("widget-1.2.3.tar.gz")
                with tarfile.open(cached, "r:gz") as accepted:
                    assert accepted.extractfile("src/api.vr").read().decode() == exported
                # The registry and the consumer are now the only holders of this cog.
                shutil.rmtree(publisher)
                (consumer / "src").mkdir()
                (consumer / "src/main.vr").write_text(
                    "module consumer.main;\nmount widget.api.published_value;\n"
                    "fn main() { print(published_value()); }\n")
                def run(args):
                    return subprocess.run([exe, *args], cwd=consumer, env={**os.environ, **env},
                                          text=True, capture_output=True, timeout=timeout)

                events.clear()
                lock, = [p for p in consumer.iterdir() if p.name.lower() == "verum.lock"]
                manifest = consumer / "Verum.toml"
                original = (lock.read_bytes(), manifest.read_bytes())
                checked = run(["check"])
                assert checked.returncode == 0, checked.stderr
                result = run(["run", "--tier", "interpret"])
                assert result.returncode == 0, result.stderr
                assert result.stdout.strip() == marker, result.stdout

                cached.write_bytes(archive[:-1] + bytes([archive[-1] ^ 1]))
                result = run(["run", "--tier", "interpret"])
                assert result.returncode != 0 and "Checksum mismatch for installed cog" in result.stderr, result
                assert marker not in result.stdout
                cached.unlink()
                result = run(["run", "--tier", "interpret"])
                assert result.returncode != 0 and "Cannot open installed archive" in result.stderr, result
                assert marker not in result.stdout and not cached.exists()
                assert (lock.read_bytes(), manifest.read_bytes()) == original
                assert not events, events
                print("Installed cog: fresh consumer checked and ran the published function offline; "
                      "changed and missing archives were refused.")
                return

            # A report about different archive bytes cannot authorize this coordinate.
            (reports / f"{snapshot.stem}-{'0' * 64}.json").write_text(json.dumps(empty))
            install("missing", None)
            install("malformed", "{")
            install("missing-field", {"package": "widget", "version": "1.2.3"})
            install("wrong-name", {**empty, "package": "other"})
            install("wrong-version", {**empty, "version": "1.2.4"})
            install("invalid-finding", {**empty, "vulnerabilities": [{**finding, "severity": "unknown"}]})
            install("nonempty", {**empty, "vulnerabilities": [finding]}, True)
            install("empty", empty, True)
            damaged = True
            install("tampered-download", empty)
            print("Real package client: published, refused missing/invalid reports and wrong digest, "
                  "then verified exact cached archive, dependency and registry lock entry on valid reports.")
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--execute-installed", action="store_true", help="mount and run the installed export")
    parser.add_argument("--dependency-main", action="store_true",
                        help="also publish a dependency entry point when exercising the installed export")
    options = parser.parse_args()
    if options.dependency_main and not options.execute_installed:
        parser.error("--dependency-main requires --execute-installed")
    with tempfile.TemporaryDirectory(prefix="verum-publish-install-") as tmp:
        exercise(str(options.verum.resolve(strict=True)), Path(tmp), options.timeout, options.execute_installed, options.dependency_main)
