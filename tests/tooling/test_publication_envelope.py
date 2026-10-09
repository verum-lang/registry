"""Control the component runner with fake executables, not Verum acceptance.

The real decoder is validated separately by the identified ordinary CLI.
These controls ensure a harness failure cannot turn into a component pass.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
FAKE = r'''
import os
from pathlib import Path
import subprocess
import sys
import time

assert sys.argv[1:] == ["run", "--tier", "interpret"]
original = Path(os.environ["FIXTURE_REPOSITORY"])
module = Path("src/protocol/publication.vr")
assert module.read_bytes() == (original / module).read_bytes()
fixture = (original / "tests/publication_envelope.vr").read_bytes()
assert Path("src/main.vr").read_bytes() == fixture.replace(
    b"module verum_registry.tests.publication_envelope;\n",
    b"module verum_registry.main;\n", 1)
assert Path("verum.toml").read_bytes() == (
    b'[cog]\nname = "verum-registry"\nversion = "0.1.0"\nedition = "2026"\n')
assert os.environ["VERUM_NO_OBJECT_CACHE"] == "1"
scenario = os.environ.get("SCENARIO", "success")
expected = (original / "tests/publication_envelope.expected").read_bytes()
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
sys.stdout.buffer.write(expected)
if scenario == "extra":
    sys.stdout.buffer.write(b"unexpected extra output\n")
if scenario == "duplicate":
    sys.stdout.buffer.write(expected)
if scenario == "source_changed":
    path = original / module
    path.write_bytes(path.read_bytes() + b"\n// changed during execution\n")
if scenario == "expected_changed":
    (original / "tests/publication_envelope.expected").write_bytes(b"changed\n")
if scenario == "project_changed":
    module.write_bytes(module.read_bytes() + b"\n// changed during execution\n")
if scenario == "project_added":
    Path("src/extra.vr").write_text("module unexpected;\n")
if scenario == "project_deleted":
    module.unlink()
if scenario == "executable_changed":
    path = Path(sys.argv[0])
    path.write_bytes(path.read_bytes() + b"\n# changed executable\n")
sys.exit(101 if scenario == "nonzero" else 0)
'''


class PublicationEnvelopeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="publication-runner-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "repository with spaces"
        for name in ("tools/run_publication_envelope.py", "src/protocol/publication.vr",
                     "tests/publication_envelope.vr", "tests/publication_envelope.expected"):
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
        result = subprocess.run(
            [sys.executable, str(self.project / "tools/run_publication_envelope.py"),
             str(self.executable), "--language-commit", "a" * 40,
             "--evidence-dir", str(evidence), *extra],
            env={**os.environ, "TMPDIR": str(self.scratch), "SCENARIO": scenario,
                 "FIXTURE_REPOSITORY": str(self.project),
                 "CHILD_SENTINEL": str(self.base / "child-survived"),
                 "TIMEOUT_READY": str(self.base / "timeout-ready")},
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(list(self.scratch.iterdir()), [])
        return result, evidence

    def test_exact_component_copy_output_and_recorded_identities(self):
        cli_hash = hashlib.sha256(self.executable.read_bytes()).hexdigest()
        result, evidence = self.invoke(extra=("--expected-cli-sha256", cli_hash))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertEqual(receipt["status"], "passed")
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["cli_sha256"], cli_hash)
        self.assertEqual(receipt["cli_sha256_after"], cli_hash)
        self.assertEqual(receipt["source_inputs"]["src/protocol/publication.vr"],
                         receipt["project_inputs"]["src/protocol/publication.vr"])
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
        for scenario in ("source_changed", "expected_changed"):
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
        result, evidence = self.invoke("timeout", ("--timeout", "0.5"))
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        receipt = json.loads((evidence / "result.json").read_text())
        self.assertEqual(receipt["status"], "timed_out")
        self.assertTrue(receipt["timed_out"])
        self.assertFalse(receipt["checks"]["within_deadline"])
        self.assertTrue((self.base / "timeout-ready").exists())
        time.sleep(1.6)
        self.assertFalse((self.base / "child-survived").exists())

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
        fixture = self.project / "tests/publication_envelope.vr"
        for contents in (b"fn main() {}\n",
                         b"module verum_registry.tests.publication_envelope;\n" * 2):
            fixture.write_bytes(contents)
            result, evidence = self.invoke()
            self.assertEqual(result.returncode, 2)
            self.assertFalse(evidence.exists())

    def test_invalid_deadline_cannot_disable_the_bound(self):
        for timeout in ("0", "-1", "nan", "inf", "601"):
            with self.subTest(timeout=timeout):
                result, evidence = self.invoke(extra=("--timeout", timeout))
                self.assertEqual(result.returncode, 2)
                self.assertFalse(evidence.exists())


if __name__ == "__main__":
    unittest.main()
