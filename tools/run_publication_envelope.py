#!/usr/bin/env python3
"""Run a selected publication component in an isolated interpreter project.

The envelope component remains the default. Metadata also includes the typed
source-metadata decoder; neither component establishes service admission.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("tools/run_publication_envelope.py")
NEW_HEADER = b"module verum_registry.main;\n"
MANIFEST = b'[cog]\nname = "verum-registry"\nversion = "0.1.0"\nedition = "2026"\n'
COMPONENTS = {
    "envelope": {
        "task": "T1652",
        "modules": (Path("src/protocol/publication.vr"),),
        "fixture": Path("tests/publication_envelope.vr"),
        "expected": Path("tests/publication_envelope.expected"),
        "header": b"module verum_registry.tests.publication_envelope;\n",
        "scope": (
            "Run the exact publication framing module in an isolated interpreter project.\n\n"
            "This component gate does not check the whole registry, HTTP admission, JSON,\n"
            "digest/archive validity, authentication, persistence, or AOT execution."
        ),
    },
    "metadata": {
        "task": "T1666",
        "modules": (Path("src/protocol/publication.vr"),
                    Path("src/protocol/publication_metadata.vr")),
        "fixture": Path("tests/publication_metadata.vr"),
        "expected": Path("tests/publication_metadata.expected"),
        "header": b"module verum_registry.tests.publication_metadata;\n",
        "scope": (
            "Run the exact publication framing and typed source-metadata modules "
            "in an isolated interpreter project.\n\n"
            "This component checks envelope composition and strict JSON schema decoding; "
            "it does not establish semantic name/version/checksum admission, "
            "archive validity, authentication, persistence, AOT, or whole-registry acceptance."
        ),
    },
}


def digest(contents):
    return hashlib.sha256(contents).hexdigest()


def file_digest(path):
    try:
        with path.open("rb") as source:
            result = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                result.update(block)
            return result.hexdigest()
    except OSError:
        return None


def write_json(path, record):
    with path.open("x", encoding="utf-8") as destination:
        json.dump(record, destination, indent=2)
        destination.write("\n")


def stop(process):
    # Kill only the process group created for this invocation, then reap it.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run(args):
    component = COMPONENTS[args.component]
    modules = component["modules"]
    fixture = component["fixture"]
    expected = component["expected"]
    old_header = component["header"]
    if os.name != "posix":
        raise ValueError("this runner requires POSIX process-group cancellation")
    verum = Path(args.verum).resolve(strict=True)
    if not verum.is_file() or not os.access(verum, os.X_OK):
        raise ValueError("supply an executable Verum CLI file")
    cli_hash = file_digest(verum)
    if cli_hash is None:
        raise ValueError("cannot hash the supplied Verum CLI")
    if args.expected_cli_sha256 and cli_hash != args.expected_cli_sha256:
        raise ValueError("the supplied CLI does not match --expected-cli-sha256")

    sources = {path: (ROOT / path).read_bytes()
               for path in (*modules, fixture, expected, RUNNER)}
    if sources[fixture].count(old_header) != 1:
        raise ValueError(f"{fixture} must contain exactly one expected entry module header")
    if not sources[expected].strip():
        raise ValueError(f"{expected} must be nonempty")
    inputs = {
        **{path: sources[path] for path in modules},
        Path("src/main.vr"): sources[fixture].replace(old_header, NEW_HEADER, 1),
        Path("verum.toml"): MANIFEST,
    }
    source_hashes = {str(path): digest(contents) for path, contents in sources.items()}
    input_hashes = {str(path): digest(contents) for path, contents in inputs.items()}
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir()  # A new directory is mandatory: never overwrite a previous run.

    with tempfile.TemporaryDirectory(prefix=f"verum-publication-{args.component}-") as temporary:
        project = Path(temporary).resolve()
        for path, contents in inputs.items():
            destination = project / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
        overrides = {"NO_COLOR": "1", "VERUM_NO_OBJECT_CACHE": "1",
                     "TMPDIR": str(project.parent)}
        command = [str(verum), "run", "--tier", "interpret"]
        record = {
            "task": component["task"],
            "component": args.component,
            "scope": component["scope"],
            "source_inputs": source_hashes,
            "project_inputs": input_hashes,
            "entry_transformation": "Only replace the fixture's module header with verum_registry.main.",
            "cli_sha256": cli_hash,
            "expected_cli_sha256": args.expected_cli_sha256,
            "language_source_commit_supplied": args.language_commit,
            "identity_boundary": "The executable hash is measured; its source commit is supplied by the operator.",
            "command": command,
            "working_directory": str(project),
            "environment_overrides": overrides,
            "deadline_seconds": args.timeout,
        }
        write_json(evidence / "started.json", record)
        timed_out = interrupted = False
        runner_error = None
        returncode = None
        start = time.monotonic()
        with (evidence / "stdout.log").open("xb") as stdout, \
                (evidence / "stderr.log").open("xb") as stderr:
            try:
                process = subprocess.Popen(
                    command, cwd=project, env={**os.environ, **overrides},
                    stdout=stdout, stderr=stderr, start_new_session=True,
                )
                try:
                    returncode = process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    stop(process)
                    returncode = process.returncode
                except KeyboardInterrupt:
                    interrupted = True
                    stop(process)
                    returncode = process.returncode
            except OSError as error:
                runner_error = str(error)
        elapsed = round(time.monotonic() - start, 2)
        sources_after = {str(path): file_digest(ROOT / path) for path in sources}
        # Include any added source file: a changed project cannot retain a pass.
        paths_after = set(project.rglob("*.vr")) | {project / "verum.toml"}
        inputs_after = {str(path.relative_to(project)): file_digest(path)
                        for path in sorted(paths_after)}
        cli_after = file_digest(verum)
        with (evidence / "stdout.log").open("rb") as stdout:
            # Reading one extra byte detects additional output without loading
            # an unbounded process log into memory.
            output_matches = stdout.read(len(sources[expected]) + 1) == sources[expected]
        checks = {
            "exit_zero": returncode == 0,
            "within_deadline": not timed_out and not interrupted,
            "exact_stdout": output_matches,
            "source_unchanged": sources_after == source_hashes,
            "project_unchanged": inputs_after == input_hashes,
            "executable_unchanged": cli_after == cli_hash,
        }
        passed = runner_error is None and all(checks.values())
        status = ("passed" if passed else "timed_out" if timed_out else
                  "interrupted" if interrupted else "runner_error" if runner_error else "failed")
        result = {
            **record, "status": status, "checks": checks,
            "elapsed_seconds": elapsed, "returncode": returncode,
            "timed_out": timed_out, "interrupted": interrupted,
            "runner_error": runner_error, "source_inputs_after": sources_after,
            "project_inputs_after": inputs_after, "cli_sha256_after": cli_after,
            "logs": {name: file_digest(evidence / name)
                     for name in ("stdout.log", "stderr.log")},
        }
        write_json(evidence / "result.json", result)
    print(f"publication {args.component} component: {status}; evidence: {evidence}", flush=True)
    return 0 if passed else 124 if timed_out else 130 if interrupted else 2 if runner_error else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", help="path to the ordinary Verum executable; no build is performed")
    parser.add_argument("--component", choices=COMPONENTS, default="envelope",
                        help="publication component to execute (default: envelope)")
    parser.add_argument("--language-commit", required=True, help="full source commit for that executable")
    parser.add_argument("--expected-cli-sha256", help="optional pinned SHA-256 of the executable")
    parser.add_argument("--evidence-dir", required=True, help="new directory beneath an existing parent")
    parser.add_argument("--timeout", type=float, default=600, help="invocation deadline in seconds (maximum 600)")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 600:
        parser.error("--timeout must be positive and at most 600 seconds")
    if not re.fullmatch(r"[0-9a-f]{40}", args.language_commit):
        parser.error("--language-commit must be a full lowercase Git SHA")
    if args.expected_cli_sha256 and not re.fullmatch(r"[0-9a-f]{64}", args.expected_cli_sha256):
        parser.error("--expected-cli-sha256 must be a lowercase SHA-256 digest")
    try:
        return run(args)
    except (OSError, ValueError) as error:
        parser.exit(2, f"RUNNER ERROR: publication {args.component} component: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
