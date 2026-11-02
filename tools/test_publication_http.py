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
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from test_publication_admission import ROOT, unpack_record
from test_publication_storage import run

TOKEN = "vrp1_" + bytes(range(32)).hex()
MEDIA_TYPE = "application/vnd.verum.cog-publish.v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    options = parser.parse_args()
    if not 0 < options.timeout <= 1800:
        parser.error("timeout must be between 0 and 1800 seconds")
    executable = str(options.verum.resolve(strict=True))
    # The public CLI automatically signs when a user key exists. This unsigned
    # source-publication test must never borrow the developer's signing identity.
    if sys.platform == "darwin":
        configuration = Path.home() / "Library/Application Support"
    elif os.name == "nt":
        configuration = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        configuration = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if any(path.exists() for path in (configuration / "verum/signing.key", Path.home() / ".verum/signing.key")):
        parser.error("use a clean unsigned test profile: the CLI signing-key locations must be absent")
    with tempfile.TemporaryDirectory(prefix="registry-publication-http-") as temporary:
        project = Path(temporary)
        storage = project / "store"
        storage.mkdir()
        credentials = project / "credentials.json"
        credentials.write_text(json.dumps({"version": 1,
            "principals": [{"id": "alice", "grants": [{"authority": "local", "names": [{"exact": "widget"}]}]}],
            "credentials": [{"id": "active", "principal": "alice", "active": True,
                             "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest()}]}))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        client = build_opener(ProxyHandler({}))
        environment = {**os.environ, "NO_COLOR": "1", "VERUM_NO_OBJECT_CACHE": "1",
                       "VERUM_REGISTRY_LISTEN": f"127.0.0.1:{port}",
                       "VERUM_REGISTRY_STORE": str(storage), "VERUM_REGISTRY_CREDENTIALS": str(credentials),
                       "VERUM_REGISTRY_AUTHORITY": "local", "VERUM_REGISTRY_OWNED_NAMES": "widget"}

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
            assert not list(storage.iterdir())

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
                {"VERUM_REGISTRY_TOKEN": TOKEN, "NO_PROXY": "127.0.0.1,localhost"})
            accepted, = storage.glob("*.publication")
            original = accepted.read_bytes()
            provenance, source_metadata, archive = unpack_record(accepted)
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

            def envelope(metadata, content):
                encoded = json.dumps(metadata, separators=(",", ":")).encode()
                return len(encoded).to_bytes(4, "little") + encoded + len(content).to_bytes(8, "little") + content

            status, _, body = request("/api/v1/cogs/publish", envelope(source_metadata, archive), True)
            assert status == 200 and json.loads(body)["checksum"] == source_metadata["checksum"]
            # A valid token grants only configured names. Even a well-framed
            # request must be refused before any immutable record is created.
            forbidden = {**source_metadata, "name": "unowned-widget"}
            expect_status(403, "/api/v1/cogs/publish", envelope(forbidden, archive), True)
            assert list(storage.glob("*.publication")) == [accepted]
            corrupted = archive[:-1] + bytes([archive[-1] ^ 1])
            expect_status(422, "/api/v1/cogs/publish", envelope(source_metadata, corrupted), True)
            conflicting = {**source_metadata,
                           "readme": None if source_metadata.get("readme") is not None else "# Widget\n"}
            assert request("/api/v1/cogs/publish", envelope(conflicting, archive), True)[0] == 409
            assert accepted.read_bytes() == original
            stop()
            start()
            assert request("/api/v1/cogs/widget/1.2.3/download")[2] == archive
            assert request("/api/v1/cogs/publish", envelope(source_metadata, archive), True)[0] == 200
            accepted.write_bytes(original[:-1])
            assert request("/api/v1/cogs/widget/1.2.3/download")[0] == 500
            assert request("/api/v1/cogs/publish", envelope(source_metadata, archive), True)[0] == 500
            assert accepted.read_bytes() == original[:-1]
            print("publication HTTP: retry, conflict, restart and corruption refusals passed", flush=True)
        except Exception as error:
            raise RuntimeError(f"{error}\n" + output.read_text(errors="replace")[-24000:]) from error
        finally:
            stop()


if __name__ == "__main__":
    main()
