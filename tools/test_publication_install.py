#!/usr/bin/env python3
"""Run ordinary package publish/install via a loopback transport to the real Weft handler."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import threading

from test_publication_admission import COMMON, TRANSACTION, stage_component, unpack_record
from test_publication_http import TOKEN, check_installed, package_profile, write_credentials

META = "/api/v1/cogs/widget/1.2.3"
REPORT = "/api/v1/security/vulnerabilities/widget/1.2.3"
DOWNLOAD = META + "/download"


def exercise(exe, root, timeout):
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

            def invoke(directory, args, **extra):
                profile = directory / "profile"
                env = {**os.environ, **package_profile(profile), **extra}
                return subprocess.run([exe, "package", *args], cwd=directory, env=env,
                                      capture_output=True, text=True, timeout=timeout)

            publisher = project("publisher", "widget")
            (publisher / "src").mkdir()
            (publisher / "src/main.vr").write_text('module widget.main;\nfn main() { print(42); }\n')
            outcome = invoke(publisher, ["publish", "--allow-dirty"], VERUM_REGISTRY_TOKEN=TOKEN)
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
                result = invoke(consumer, ["install", "widget", "--version", "1.2.3"])
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
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="verum-publish-install-") as tmp:
        exercise(str(options.verum.resolve(strict=True)), Path(tmp), options.timeout)
