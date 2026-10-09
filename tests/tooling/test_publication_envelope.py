"""Control the component runner with fake executables, not Verum acceptance.

The real decoder is validated separately by the identified ordinary CLI.
These controls ensure a harness failure cannot turn into a component pass.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
FAKE = r'''
import os
from pathlib import Path
import subprocess
import sys
import time

assert sys.argv[1:] == ["run", "--tier", "interpret"]
Path(os.environ["INVOCATION_MARKER"]).write_text("invoked")
original = Path(os.environ["FIXTURE_REPOSITORY"])
component = os.environ["EXPECTED_COMPONENT"]
modules = [Path("src/protocol/publication.vr")]
if component == "metadata":
    modules.append(Path("src/protocol/publication_metadata.vr"))
for module in modules:
    assert module.read_bytes() == (original / module).read_bytes()
assert set(Path("src").rglob("*.vr")) == set(modules) | {Path("src/main.vr")}
fixture_path = Path(f"tests/publication_{component}.vr")
expected_path = Path(f"tests/publication_{component}.expected")
fixture = (original / fixture_path).read_bytes()
assert Path("src/main.vr").read_bytes() == fixture.replace(
    f"module verum_registry.tests.publication_{component};\n".encode(),
    b"module verum_registry.main;\n", 1)
assert Path("verum.toml").read_bytes() == (
    b'[cog]\nname = "verum-registry"\nversion = "0.1.0"\nedition = "2026"\n')
assert os.environ["VERUM_NO_OBJECT_CACHE"] == "1"
scenario = os.environ.get("SCENARIO", "success")
expected = (original / expected_path).read_bytes()
print("simulated CLI diagnostic", file=sys.stderr)
if scenario == "timeout":
    sentinel = Path(os.environ["CHILD_SENTINEL"])
    subprocess.Popen([sys.executable, "-c",
        "import time; from pathlib import Path; time.sleep(1.5); "
        f"Path({str(sentinel)!r}).write_text('survived')"])
    Path(os.environ["TIMEOUT_READY"]).write_text("started")
    time.sleep(20)
if scenario == "empty":
    sys.exit(0)
if scenario == "stderr_only":
    sys.stderr.buffer.write(expected)
    sys.exit(0)
if scenario == "wrong_component_output":
    sys.stdout.buffer.write(b"publication_envelope: passed\n")
    sys.exit(0)
sys.stdout.buffer.write(expected)
if scenario == "extra":
    sys.stdout.buffer.write(b"unexpected extra output\n")
if scenario == "duplicate":
    sys.stdout.buffer.write(expected)
changed_source = {
    "source_changed": modules[-1],
    "shared_source_changed": modules[0],
    "fixture_changed": fixture_path,
    "runner_changed": Path("tools/run_publication_envelope.py"),
}.get(scenario)
if changed_source is not None:
    path = original / changed_source
    path.write_bytes(path.read_bytes() + b"\n// changed during execution\n")
if scenario == "expected_changed":
    (original / expected_path).write_bytes(b"changed\n")
if scenario in ("project_changed", "shared_project_changed"):
    module = modules[0] if scenario == "shared_project_changed" else modules[-1]
    module.write_bytes(module.read_bytes() + b"\n// changed during execution\n")
if scenario == "project_added":
    Path("src/extra.vr").write_text("module unexpected;\n")
if scenario == "project_deleted":
    modules[-1].unlink()
if scenario == "executable_changed":
    path = Path(sys.argv[0])
    path.write_bytes(path.read_bytes() + b"\n# changed executable\n")
sys.exit(101 if scenario == "nonzero" else 0)
'''


class PublicationRunnerControls:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="publication-runner-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "repository with spaces"
        self.modules = ["src/protocol/publication.vr"]
        if self.component == "metadata":
            self.modules.append("src/protocol/publication_metadata.vr")
        self.fixture = f"tests/publication_{self.component}.vr"
        self.expected = f"tests/publication_{self.component}.expected"
        for name in ("tools/run_publication_envelope.py", *self.modules,
                     self.fixture, self.expected):
            destination = self.project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        self.executable = self.base / "fake verum"
        self.executable.write_text(f"#!{sys.executable}\n{FAKE}", encoding="utf-8")
        self.executable.chmod(0o755)
        self.scratch = self.base / "scratch"
        self.scratch.mkdir()

    def invoke(self, scenario="success", extra=()):
        evidence = self.base / f"evidence-{scenario}"
        selection = () if self.component == "envelope" else ("--component", self.component)
        result = subprocess.run(
            [sys.executable, str(self.project / "tools/run_publication_envelope.py"),
             str(self.executable), "--language-commit", "a" * 40,
             "--evidence-dir", str(evidence), *selection, *extra],
            env=self.environment(scenario),
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(list(self.scratch.iterdir()), [])
        return result, evidence

    def environment(self, scenario):
        return {**os.environ, "TMPDIR": str(self.scratch), "SCENARIO": scenario,
                "FIXTURE_REPOSITORY": str(self.project),
                "EXPECTED_COMPONENT": self.component,
                "INVOCATION_MARKER": str(self.base / "invoked"),
                "CHILD_SENTINEL": str(self.base / "child-survived"),
                "TIMEOUT_READY": str(self.base / "timeout-ready")}

    def test_exact_component_copy_output_and_recorded_identities(self):
        cli_hash = hashlib.sha256(self.executable.read_bytes()).hexdigest()
        result, evidence = self.invoke(extra=("--expected-cli-sha256", cli_hash))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["component"], self.component)
        self.assertIn(f"publication {self.component} component: passed", result.stdout)
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["cli_sha256"], cli_hash)
        self.assertEqual(receipt["cli_sha256_after"], cli_hash)
        self.assertEqual(set(receipt["source_inputs"]),
                         {*self.modules, self.fixture, self.expected,
                          "tools/run_publication_envelope.py"})
        self.assertEqual(set(receipt["project_inputs"]),
                         {*self.modules, "src/main.vr", "verum.toml"})
        for module in self.modules:
            self.assertEqual(receipt["source_inputs"][module], receipt["project_inputs"][module])
        self.assertEqual(receipt["source_inputs"], receipt["source_inputs_after"])
        self.assertEqual(receipt["project_inputs"], receipt["project_inputs_after"])
        self.assertFalse(Path(receipt["working_directory"]).exists())
        for log, digest in receipt["logs"].items():
            self.assertEqual(digest, hashlib.sha256((evidence / log).read_bytes()).hexdigest())

    def test_zero_exit_requires_exact_nonempty_stdout(self):
        for scenario in ("empty", "stderr_only", "extra", "duplicate"):
            with self.subTest(scenario=scenario):
                result, evidence = self.invoke(scenario)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                receipt = json.loads((evidence / "result.json").read_text())
                self.assertFalse(receipt["checks"]["exact_stdout"])
                self.assertEqual(receipt["status"], "failed")

    def test_expected_output_with_failed_process_is_not_success(self):
        result, evidence = self.invoke("nonzero")
        self.assertEqual(result.returncode, 1)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertTrue(receipt["checks"]["exact_stdout"])
        self.assertFalse(receipt["checks"]["exit_zero"])

    def test_changed_sources_and_expected_output_invalidate_result(self):
        for scenario in ("source_changed", "expected_changed", "fixture_changed", "runner_changed"):
            with self.subTest(scenario=scenario):
                result, evidence = self.invoke(scenario)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                receipt = json.loads((evidence / "result.json").read_text())
                self.assertFalse(receipt["checks"]["source_unchanged"])

    def test_changed_added_or_missing_project_source_invalidates_result(self):
        for scenario in ("project_changed", "project_added", "project_deleted"):
            with self.subTest(scenario=scenario):
                result, evidence = self.invoke(scenario)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                receipt = json.loads((evidence / "result.json").read_text())
                self.assertFalse(receipt["checks"]["project_unchanged"])

    def test_changed_executable_invalidates_result(self):
        result, evidence = self.invoke("executable_changed")
        self.assertEqual(result.returncode, 1)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertFalse(receipt["checks"]["executable_unchanged"])

    def test_timeout_is_recorded_and_cancels_descendants(self):
        # Establish the child-process precondition before the runner starts its
        # wait deadline. A busy machine may need more than 0.5s just to launch
        # Python; killing it before then does not exercise descendant cleanup.
        spec = importlib.util.spec_from_file_location(
            "publication_component_runner", self.project / "tools/run_publication_envelope.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        real_popen = subprocess.Popen
        ready = self.base / "timeout-ready"

        def launch_ready_fixture(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            startup_deadline = time.monotonic() + 5
            while not ready.exists():
                if process.poll() is not None or time.monotonic() >= startup_deadline:
                    runner.stop(process)
                    self.fail("timeout fixture did not establish its child-process precondition")
                time.sleep(0.01)
            return process

        evidence = self.base / "evidence-timeout"
        args = argparse.Namespace(
            verum=str(self.executable), component=self.component,
            language_commit="a" * 40, expected_cli_sha256=None,
            evidence_dir=str(evidence), timeout=0.5)
        with mock.patch.dict(os.environ, self.environment("timeout")), \
                mock.patch.object(runner.subprocess, "Popen", launch_ready_fixture), \
                mock.patch.object(runner.tempfile, "tempdir", str(self.scratch)), \
                contextlib.redirect_stdout(io.StringIO()):
            returncode = runner.run(args)
        self.assertEqual(returncode, 124)
        self.assertEqual(list(self.scratch.iterdir()), [])
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertEqual(receipt["status"], "timed_out")
        self.assertTrue(receipt["timed_out"])
        self.assertFalse(receipt["checks"]["within_deadline"])
        self.assertTrue((self.base / "timeout-ready").exists())
        time.sleep(1.6)
        self.assertFalse((self.base / "child-survived").exists())

    def test_cli_deadline_does_not_require_fixture_startup(self):
        result, evidence = self.invoke("timeout", ("--timeout", "0.01"))
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertEqual(receipt["status"], "timed_out")
        self.assertFalse(receipt["checks"]["within_deadline"])

    def test_existing_evidence_is_never_overwritten(self):
        evidence = self.base / "evidence-success"
        evidence.mkdir()
        marker = evidence / "result.json"
        marker.write_text("previous result")
        result, _ = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(marker.read_text(), "previous result")
        self.assertEqual(list(evidence.iterdir()), [marker])

    def test_mismatched_executable_hash_refuses_invocation(self):
        result, evidence = self.invoke(extra=("--expected-cli-sha256", "0" * 64))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(evidence.exists())

    def test_missing_or_duplicate_entry_header_refuses_invocation(self):
        fixture = self.project / self.fixture
        for contents in (b"fn main() {}\n",
                         f"module verum_registry.tests.publication_{self.component};\n".encode() * 2):
            fixture.write_bytes(contents)
            result, evidence = self.invoke()
            self.assertEqual(result.returncode, 2)
            self.assertFalse(evidence.exists())
            self.assertIn(f"publication {self.component} component", result.stderr)
            self.assertIn(self.fixture, result.stderr)
            self.assertFalse((self.base / "invoked").exists())

    def test_empty_expected_output_refuses_invocation(self):
        (self.project / self.expected).write_bytes(b" \n")
        result, evidence = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn(self.expected, result.stderr)
        self.assertFalse(evidence.exists())
        self.assertFalse((self.base / "invoked").exists())

    def test_invalid_deadline_cannot_disable_the_bound(self):
        for timeout in ("0", "-1", "nan", "inf", "601"):
            with self.subTest(timeout=timeout):
                result, evidence = self.invoke(extra=("--timeout", timeout))
                self.assertEqual(result.returncode, 2)
                self.assertFalse(evidence.exists())


class PublicationEnvelopeRunnerTests(PublicationRunnerControls, unittest.TestCase):
    component = "envelope"

    def test_explicit_envelope_selection_preserves_default_inputs_and_scope(self):
        default, default_evidence = self.invoke()
        explicit, explicit_evidence = self.invoke("explicit", ("--component", "envelope"))
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        default_receipt = json.loads((default_evidence / "result.json").read_text())
        explicit_receipt = json.loads((explicit_evidence / "result.json").read_text())
        for field in ("task", "component", "scope", "source_inputs", "project_inputs"):
            self.assertEqual(default_receipt[field], explicit_receipt[field])
        self.assertEqual(default_receipt["task"], "T1652")
        self.assertIn("does not check the whole registry, HTTP admission, JSON", default_receipt["scope"])

    def test_unknown_component_refuses_invocation(self):
        result, evidence = self.invoke(extra=("--component", "whole-registry"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertFalse(evidence.exists())
        self.assertFalse((self.base / "invoked").exists())


class PublicationMetadataRunnerTests(PublicationRunnerControls, unittest.TestCase):
    component = "metadata"

    def test_metadata_receipts_identify_decoding_without_admission(self):
        result, evidence = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads((evidence / "result.json").read_text())
        started = json.loads((evidence / "started.json").read_text())
        for record in (receipt, started):
            self.assertEqual(record["task"], "T1666")
            self.assertEqual(record["component"], "metadata")
            self.assertIn("strict JSON schema decoding", record["scope"])
            self.assertIn("does not establish semantic name/version/checksum admission", record["scope"])
            self.assertNotIn("tests/publication_envelope.vr", record["source_inputs"])

    def test_envelope_output_cannot_satisfy_metadata_component(self):
        result, evidence = self.invoke("wrong_component_output")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertFalse(receipt["checks"]["exact_stdout"])
        self.assertEqual(receipt["status"], "failed")

    def test_shared_envelope_source_and_project_mutations_invalidate_metadata(self):
        for scenario, failed_check in (("shared_source_changed", "source_unchanged"),
                                       ("shared_project_changed", "project_unchanged")):
            with self.subTest(scenario=scenario):
                result, evidence = self.invoke(scenario)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                receipt = json.loads((evidence / "result.json").read_text())
                self.assertFalse(receipt["checks"][failed_check])

    def test_missing_metadata_inputs_refuse_instead_of_falling_back_to_envelope(self):
        for name in ("src/protocol/publication_metadata.vr", self.fixture, self.expected):
            with self.subTest(name=name):
                path = self.project / name
                contents = path.read_bytes()
                path.unlink()
                try:
                    result, evidence = self.invoke()
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("publication metadata component", result.stderr)
                    self.assertIn(name, result.stderr)
                    self.assertFalse(evidence.exists())
                    self.assertFalse((self.base / "invoked").exists())
                finally:
                    path.write_bytes(contents)


if __name__ == "__main__":
    unittest.main()
