#!/usr/bin/env python3
"""Exercise actual Verum storage across processes and conflicting writers.

The temporary directory belongs to this test. No registry installation is used.
This checks the record transaction, not archive admission or the HTTP service.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import os
import shutil
import signal
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def record(key, value):
    magic = b"VRPUB001"
    digest = hashlib.sha256(magic + key.encode("ascii") + value).digest()
    return magic + len(value).to_bytes(8, "little") + digest + value


def run(command, cwd, timeout, environment=None):
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True,
                               env={**os.environ, "NO_COLOR": "1", **(environment or {})})
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        raise RuntimeError(f"timed out after {timeout}s: {command}\n"
                           + stderr.decode(errors="replace")[-32768:]
                           + stdout.decode(errors="replace")[-4096:]) from None
    if process.returncode:
        raise RuntimeError(f"exit {process.returncode}: {command}\n"
                           + stderr.decode(errors="replace")
                           + stdout.decode(errors="replace"))
    return stdout.decode("utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", type=Path)
    parser.add_argument("--tier", choices=("interpret", "aot"), default="interpret")
    parser.add_argument("--timeout", type=float, default=600)
    options = parser.parse_args()
    executable = str(options.verum.resolve(strict=True))
    if not 0 < options.timeout <= 1800:
        parser.error("timeout must be between 0 and 1800 seconds")
    with tempfile.TemporaryDirectory(prefix="registry-publication-storage-") as temporary:
        project = Path(temporary)
        (project / "src/node").mkdir(parents=True)
        (project / "verum.toml").write_text(
            '[cog]\nname = "verum-registry"\nversion = "0.1.0"\nedition = "2026"\n')
        for module in ("storage_contract", "local_storage"):
            relative = f"src/node/publication_{module}.vr"
            shutil.copyfile(ROOT / relative, project / relative)
        fixture = (ROOT / "tests/publication_storage.vr").read_text()
        header = "module verum_registry.tests.publication_storage;"
        assert fixture.count(header) == 1
        (project / "src/main.vr").write_text(
            fixture.replace(header, "module verum_registry.main;", 1))
        directory = project / "store"
        directory.mkdir()
        if options.tier == "aot":
            run([executable, "build", "--tier", "aot", "--strict-codegen",
                 "--strict-intrinsics"], project, options.timeout)
            binary = project / "target/debug/verum-registry"
            if os.name == "nt":
                binary = binary.with_suffix(".exe")
            command = [str(binary)]
        else:
            command = [executable, "run", "--tier", "interpret"]

        def phase(name):
            # Each invocation starts a fresh process. No in-memory state is
            # carried from the first publication into recovery or competitors.
            return run(command, project, options.timeout, {
                "VERUM_STORAGE_TEST_DIRECTORY": str(directory),
                "VERUM_STORAGE_TEST_PHASE": name,
            })

        assert phase("write") == "publication-storage: created"
        print(f"publication storage ({options.tier}): initial commit passed", flush=True)
        expected = bytes(index % 256 for index in range(10003))
        accepted = directory / ("1" * 64 + ".publication")
        assert accepted.read_bytes() == record("1" * 64, expected)
        initial = accepted.read_bytes()

        # Different framing/integrity failures, including a correctly framed
        # record copied under the wrong coordinate, must all fail closed.
        invalid = {
            "2": b"INVALID!" + record("2" * 64, expected)[8:],
            "3": record("3" * 64, expected)[:-1],
            "4": record("4" * 64, expected)[:48] + b"x" + expected[1:],
            "5": record("5" * 64, expected) + b"trailing",
            "6": initial,
            "9": b"",
            "a": record("a" * 64, b"x" * 32769),
        }
        for digit, value in invalid.items():
            (directory / (digit * 64 + ".publication")).write_bytes(value)
        (directory / ("7" * 64 + ".publication")).symlink_to(accepted.name)
        (directory / ("8" * 64 + ".publication")).mkdir()
        (directory / ".pending-interrupted").write_bytes(b"VRPUB001\x01")
        (directory / "symlink-root").symlink_to(".", target_is_directory=True)
        (directory / "file-root").write_bytes(b"not a directory")
        assert phase("restart") == "publication-storage: restart and refusals"
        print(f"publication storage ({options.tier}): restart and refusals passed", flush=True)
        assert accepted.read_bytes() == initial
        assert not (directory / ("0" * 64 + ".publication")).exists()
        for digit, value in invalid.items():
            assert (directory / (digit * 64 + ".publication")).read_bytes() == value

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(phase, ("race-a", "race-b")))
        assert sorted(outcomes) == ["publication-storage: race conflict",
                                    "publication-storage: race created"]
        winner = (directory / ("c" * 64 + ".publication")).read_bytes()
        assert winner in (record("c" * 64, b"race-a"), record("c" * 64, b"race-b"))
        assert sorted(p.name for p in directory.glob(".pending-*")) == [".pending-interrupted"]
        print(f"publication storage ({options.tier}): passed")


if __name__ == "__main__":
    main()
