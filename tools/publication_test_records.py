"""Independent valid release fixtures for storage and PostgreSQL contract tests."""

from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import tarfile

from test_publication_storage import record


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def literal(value):
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class Publication:
    key: str
    value: bytes
    metadata: dict

    @property
    def record(self):
        return record(self.key, self.value)

    @property
    def projection(self):
        return json_text({"version": self.metadata["version"], "checksum": self.metadata["checksum"],
                          "yanked": False, "features": self.metadata["features"]})

    def arguments(self):
        return ",".join((literal(self.key), "decode(" + literal(self.record.hex()) + ",'hex')",
                         literal(self.metadata["name"]), literal(self.metadata["version"]),
                         literal(self.projection)))

    def insert(self):
        return ("INSERT INTO public.verum_publications "
                "(record_key,record,release_name,release_version,index_entry) VALUES (" +
                self.arguments() + ") ON CONFLICT (record_key) DO NOTHING RETURNING 1;")


def publication(version, contents, name="widget"):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        manifest = f'[cog]\nname="{name}"\nversion="{version}"\n'.encode()
        for path, data in (("Verum.toml", manifest), ("payload.bin", contents)):
            entry = tarfile.TarInfo(path)
            entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
            tar.addfile(entry, io.BytesIO(data))
    archive = gzip.compress(output.getvalue(), mtime=0)
    metadata = {"name": name, "version": version, "description": None, "authors": [], "license": None,
                "repository": None, "homepage": None, "keywords": [], "categories": [], "readme": None,
                "dependencies": {}, "features": {"default": ["net", "tls"], "net": [], "tls": ["net"]},
                "checksum": hashlib.sha256(archive).hexdigest()}
    fields = ["alice", "active", "local", "exact", name, "1700000000", json_text(metadata)]
    value = b"VRREL001" + b"".join(len(field.encode()).to_bytes(4, "little") + field.encode() for field in fields) + archive
    key = hashlib.sha256(b"verum-source-release-v1\0" + name.encode() + b"\0" + version.encode()).hexdigest()
    return Publication(key, value, metadata)


def fixtures():
    payload = bytes(i % 256 for i in range(10003))
    return {"large": publication("1.0.0", payload), "changed": publication("1.0.0", b"x" + payload[1:]),
            "race-a": publication("2.0.0", bytes([1, 2, 3])), "race-b": publication("2.0.0", bytes([4, 5, 6])),
            "anchor": publication("3.0.0", bytes([0, 1, 127, 255])),
            "anchor-conflict": publication("3.0.0", bytes([0, 42, 254])),
            "pending": publication("4.0.0", bytes([0, 42, 254])),
            "pending-block": publication("4.0.0", b"uncommitted")}


def write_fixtures(directory):
    directory.mkdir(exist_ok=True)
    for name, value in fixtures().items():
        (directory / (name + ".release")).write_bytes(value.value)
