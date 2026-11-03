#!/usr/bin/env python3
"""Exercise production archive admission and durable publishing in real processes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time

from test_publication_storage import run

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = b'[cog]\nname = "widget"\nversion = "1.2.3"\n'
COMMON = (
    "protocol/identity",
    "protocol/publication", "protocol/publication_metadata", "protocol/publication_encoding",
    "node/publication_record", "node/publication_manifest", "node/publication_archive",
)
TRANSACTION = (
    "protocol/authority", "node/publication_auth", "node/publication_prepare",
    "node/publication_storage_contract", "node/publication_local_storage",
    "node/publication_postgres_storage", "node/publication_storage", "node/publication_commit",
)


def archive(entries, format=tarfile.GNU_FORMAT):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=format) as writer:
        for name, contents, kind in entries:
            header = tarfile.TarInfo(name)
            header.type, header.mode, header.mtime = kind, 0o644, 0
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                header.linkname = "src/main.vr"
            header.size = len(contents) if kind == tarfile.REGTYPE else 0
            writer.addfile(header, io.BytesIO(contents))
    return output.getvalue()


def fixtures(directory):
    regular, folder = tarfile.REGTYPE, tarfile.DIRTYPE
    manifest = ("Verum.toml", MANIFEST, regular)
    source = ("src/main.vr", b"module widget.main;\nfn main() { print(42); }\n", regular)
    base = [manifest, source]
    cases = {
        "gnu": archive([manifest, ("src/" + "long-" * 30 + ".vr", bytes(range(256)), regular)]),
        "ustar": archive(base, tarfile.USTAR_FORMAT),
        "pax": archive([manifest, ("src/" + "long-" * 30 + ".vr", b"source", regular)], tarfile.PAX_FORMAT),
        "readme": archive(base + [("README.md", b"# Widget\n", regular)]),
        "directory": archive([manifest, ("src/", b"", folder), source]),
        "duplicate": archive(base + [source]),
        "duplicate-directory": archive([manifest, ("src/", b"", folder), ("src", b"", folder)]),
        "file-parent": archive([manifest, ("src", b"file", regular), source]),
        "child-parent": archive(base + [("src", b"file", regular)]),
        "case-manifest": archive(base + [("verum.toml", MANIFEST.replace(b"widget", b"other"), regular)]),
        "case-file-parent": archive([manifest, ("SRC", b"file", regular), source]),
        "case-child-parent": archive(base + [("SRC", b"file", regular)]),
        "symlink": archive(base + [("link", b"", tarfile.SYMTYPE)]),
        "hardlink": archive(base + [("link", b"", tarfile.LNKTYPE)]),
        "missing-manifest": archive([source]),
        "nested-manifest": archive([("nested/Verum.toml", MANIFEST, regular), source]),
        "directory-manifest": archive([("Verum.toml", b"", folder), source]),
        "manifest-utf8": archive([("Verum.toml", b"\xff\xfe", regular), source]),
        "manifest-coordinate": archive([("Verum.toml", MANIFEST.replace(b"widget", b"other"), regular), source]),
    }
    for name, path in {
        "traversal": "../escape", "absolute": "/escape", "backslash": "src\\escape",
        "drive": "C:/escape", "empty-component": "src//escape", "device": "src/CON.txt",
        "trailing-dot": "src/escape.",
    }.items():
        cases[name] = archive(base + [(path, b"unsafe", regular)])
    raw = archive(base, tarfile.USTAR_FORMAT)
    cases.update({"tar-terminator": raw[:2048], "tar-trailing": raw + b"x", "tar-payload": raw[:516]})
    for name, data in cases.items():
        (directory / f"{name}.gz").write_bytes(gzip.compress(data, mtime=0))
    good = (directory / "ustar.gz").read_bytes()
    damaged = bytearray(good)
    damaged[-8] ^= 1
    for name, data in {
        "gzip-trailing": good + b"x", "gzip-concatenated": good + good,
        "gzip-truncated": good[:-1], "gzip-crc": bytes(damaged),
    }.items():
        (directory / f"{name}.gz").write_bytes(data)


def unpack_record(path):
    """Independent framing/digest oracle; does not call registry codec code."""
    data = path.read_bytes()
    key = path.name.removesuffix(".publication")
    assert data[:8] == b"VRPUB001"
    assert int.from_bytes(data[8:16], "little") == len(data) - 48
    assert data[16:48] == hashlib.sha256(data[:8] + key.encode() + data[48:]).digest()
    payload = data[48:]
    assert payload[:8] == b"VRREL001"
    position, fields = 8, []
    for _ in range(7):
        size = int.from_bytes(payload[position:position + 4], "little")
        position += 4
        fields.append(payload[position:position + size].decode("utf-8"))
        position += size
    metadata = json.loads(fields[6])
    compressed = payload[position:]
    assert metadata["checksum"] == hashlib.sha256(compressed).hexdigest()
    assert key == hashlib.sha256(b"verum-source-release-v1\0" + metadata["name"].encode()
                                 + b"\0" + metadata["version"].encode()).hexdigest()
    return fields[:6], metadata, compressed


def stage_component(project, modules, fixture):
    for module in modules:
        destination = project / f"src/{module}.vr"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / f"src/{module}.vr", destination)
    (project / "verum.toml").write_text(
        '[cog]\nname = "verum-registry"\nversion = "0.1.0"\nedition = "2026"\n')
    source = (ROOT / f"tests/{fixture}.vr").read_text()
    header = f"module verum_registry.tests.{Path(fixture).name};"
    assert source.count(header) == 1
    (project / "src/main.vr").write_text(source.replace(header, "module verum_registry.main;", 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--component", choices=("archive", "commit", "receipt-private"), default="archive")
    parser.add_argument("--timeout", type=float, default=600)
    options = parser.parse_args()
    if not 0 < options.timeout <= 1800:
        parser.error("timeout must be between 0 and 1800 seconds")
    executable = str(options.verum.resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix="registry-publication-admission-") as temporary:
        project = Path(temporary)
        modules = COMMON + (TRANSACTION if options.component != "archive" else ())
        fixture = ("language/publication_receipt_construct" if options.component == "receipt-private"
                   else f"publication_{options.component}")
        stage_component(project, modules, fixture)
        if options.component == "receipt-private":
            try:
                run([executable, "check"], project, options.timeout)
            except RuntimeError as error:
                diagnostic = str(error)
                assert diagnostic.startswith(("exit 1:", "exit 101:")), diagnostic
                # The checker stops at the first inaccessible literal field.
                assert diagnostic.count("error<E") == 1, diagnostic
                expected = ("error<E202>: visibility error: 'name' is Private in module "
                            "'verum_registry.node.publication_commit'")
                assert expected in diagnostic, diagnostic
            else:
                raise AssertionError("foreign code manufactured a publication receipt")
            print("publication receipt: foreign construction refused", flush=True)
            return
        data = project / "fixtures"
        data.mkdir()
        fixtures(data)
        command = [executable, "run", "--tier", "interpret"]
        environment = {"VERUM_PUBLICATION_FIXTURES": str(data)}
        if options.component == "archive":
            assert run(command, project, options.timeout, environment) == "publication-archive: ok"
            print("publication archive: valid formats, paths, bounds and refusals passed", flush=True)
            return
        storage = project / "store"
        storage.mkdir()

        def phase(name, directory=storage):
            return run(command, project, options.timeout, {**environment,
                "VERUM_PUBLICATION_STORE": str(directory), "VERUM_PUBLICATION_PHASE": name})

        before = int(time.time())
        assert phase("create") == "publication-commit: created"
        accepted, = storage.glob("*.publication")
        initial = accepted.read_bytes()
        provenance, metadata, compressed = unpack_record(accepted)
        assert provenance[:5] == ["alice", "active", "local", "exact", "widget"]
        assert before <= int(provenance[5]) <= int(time.time())
        assert metadata["name"] == "widget" and metadata["version"] == "1.2.3"
        assert compressed == (data / "readme.gz").read_bytes()
        print("publication transaction: exact bytes and provenance persisted", flush=True)
        (storage / ".pending-interrupted").write_bytes(b"VRPUB001\x01")
        assert phase("restart") == "publication-commit: restart and conflicts"
        assert accepted.read_bytes() == initial
        assert sorted(p.name for p in storage.glob(".pending-*")) == [".pending-interrupted"]
        print("publication transaction: restart, credential rotation and conflicts passed", flush=True)
        accepted.write_bytes(initial[:-1])
        assert phase("corrupt") == "publication-commit: corruption refused"
        assert accepted.read_bytes() == initial[:-1]
        race = project / "race"
        race.mkdir()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda name: phase(name, race), ("race-a", "race-b")))
        assert sorted(outcomes) == ["publication-commit: race conflict", "publication-commit: race created"]
        winner, = race.glob("*.publication")
        _, winner_metadata, winner_archive = unpack_record(winner)
        assert winner_metadata["readme"] in (None, "# Widget\n")
        assert winner_archive == compressed
        assert not list(race.glob(".pending-*"))
        print("publication transaction: competing immutable publications passed", flush=True)


if __name__ == "__main__":
    main()
