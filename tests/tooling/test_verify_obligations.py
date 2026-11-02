"""Exercise the obligation runner without invoking a Verum compiler.

Run: python3 -m unittest discover -s tests/tooling -v
The fake emits the report format and exits implemented by Verum's
VerifyCommand and CliError; its outputs are harness fixtures, not proofs.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
FAKE = r'''
import os
from pathlib import Path
import sys
import time

path = Path(sys.argv[2])
scenario = os.environ.get("FAKE_SCENARIO", "proved")
control = path.name == "control.vr"
if control:
    rows = [("theorem every_bool_is_true", "failed"),
            ("theorem every_int_is_zero", "failed"),
            ("theorem a_bool_equals_itself", "proved")]
    if scenario == "control_missing":
        rows = [rows[1]]
    if scenario == "control_false_proved":
        rows[0] = (rows[0][0], "proved")
    if scenario == "control_true_failed":
        rows[2] = (rows[2][0], "failed")
else:
    if scenario == "parser_failure":
        print("error: deliberately simulated parser failure")
        sys.exit(105)
    if scenario == "process_timeout":
        time.sleep(10)
    rows = ([("theorem alpha", "proved")] if path.name == "first.vr"
            else [("lemma beta_2", "proved"), ("corollary gamma", "proved")])
    if scenario in ("open", "wrong_exit", "timeout", "skipped"):
        status = {"open": "failed", "wrong_exit": "failed",
                  "timeout": "timeout", "skipped": "skipped"}[scenario]
        rows[0] = (rows[0][0], status)
    if scenario == "missing":
        rows = rows[1:]
    if scenario == "duplicate":
        rows.append(rows[0])
    if scenario == "unknown":
        rows.append(("theorem unexpected", "proved"))
    if scenario == "function_failed":
        rows.append(("helper", "failed"))
    if scenario == "empty_name":
        rows.append(("  ", "proved"))
    if path.name == "second.vr":
        if scenario == "changed_after":
            previous = path.with_name("first.vr")
            previous.write_text(previous.read_text() + "\n// changed after verification\n")
        if scenario == "deleted_after":
            path.with_name("first.vr").unlink()
        if scenario == "created_after":
            path.with_name("new_helper.vr").write_text("pure fn added() -> Bool { true }\n")
        if scenario == "dependency_changed":
            path.with_name("helpers.vr").write_text("pure fn helper() -> Bool { false }\n")
        if scenario == "manifest_changed":
            Path("verum.toml").write_text('[cog]\nname = "changed"\n')
    rows.append(("unconstrained_helper", "skipped"))

styles = {"proved": ("✓", "Proved in 0.01s"),
          "failed": ("✗", "Failed in 0.01s"),
          "timeout": ("⚠", "Timeout after 0.01s (limit: 0.01s)"),
          "skipped": ("-", "Skipped (no refinement types)")}
print("Verification Report:")
print("=" * 60)
for name, status in rows:
    marker, detail = styles[status]
    line = f"  {marker} {name}: {detail}"
    if scenario == "ansi":
        line = f"\x1b[32m{line}\x1b[0m"
    print(line)
    if status == "failed":
        print("      Counterexample: fixture only")
counts = {status: sum(row[1] == status for row in rows) for status in styles}
if scenario == "bad_summary" and not control:
    counts["proved"] += 1
if not (scenario == "no_summary" and not control):
    print("Summary: {proved} proved, {failed} failed, {timeout} timeout, "
          "{skipped} skipped".format(**counts))
if scenario in ("wrong_exit", "control_missing"):
    sys.exit(0)
if scenario == "exit_failure" and not control:
    sys.exit(101)
sys.exit(105 if counts["failed"] else 0)
'''


class ObligationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="registry-runner-test-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project with spaces"
        (self.project / "tools").mkdir(parents=True)
        (self.project / "src").mkdir()
        self.scratch = Path(self.temp.name) / "scratch"
        self.scratch.mkdir()
        for name in ("verify_obligations.sh", "verify_obligations.py"):
            source = ROOT / "tools" / name
            if source.exists():
                shutil.copy2(source, self.project / "tools" / name)
        (self.project / "src/first.vr").write_text(
            '// public theorem not_a_declaration() ensures false;\n'
            '/* public theorem also_not_a_declaration() ensures false; */\n'
            'const text = "public theorem not_code() ensures false;";\n'
            'public theorem alpha() ensures true proof by auto;\n',
            encoding="utf-8",
        )
        (self.project / "src/second.vr").write_text(
            'public lemma beta_2() ensures true proof by auto;\n'
            'corollary gamma() from alpha proof by auto;\n', encoding="utf-8"
        )
        (self.project / "src/helpers.vr").write_text("pure fn helper() -> Bool { true }\n")
        (self.project / "verum.toml").write_text('[cog]\nname = "fixture"\n')
        self.verifier = Path(self.temp.name) / "fake verifier"
        self.verifier.write_text(f"#!{sys.executable}\n{FAKE}", encoding="utf-8")
        self.verifier.chmod(0o755)

    def run_runner(self, scenario="proved", extra=(), environment=None):
        env = os.environ.copy()
        env.update(TMPDIR=str(self.scratch), FAKE_SCENARIO=scenario)
        if environment:
            env.update(environment)
        return subprocess.run(
            ["bash", str(self.project / "tools/verify_obligations.sh"),
             str(self.verifier), *extra],
            cwd=self.temp.name, env=env, text=True, capture_output=True, timeout=15,
        )

    def assert_runner_error(self, scenario):
        result = self.run_runner(scenario)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("RUNNER ERROR", result.stderr)
        self.assertNotIn("0 theorem(s)", result.stdout)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_complete_proofs_and_both_false_controls(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("3 obligation(s) in 2 file(s): 3 proved, 0 open", result.stdout)
        self.assertIn("lemma beta_2", result.stdout)
        self.assertIn("corollary gamma", result.stdout)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_colored_report(self):
        result = self.run_runner("ansi")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_real_parser_failures_are_not_zero_coverage_success(self):
        self.assert_runner_error("parser_failure")

    def test_both_negative_controls_are_required(self):
        self.assert_runner_error("control_missing")

    def test_false_control_must_not_prove(self):
        self.assert_runner_error("control_false_proved")

    def test_positive_control_must_prove(self):
        self.assert_runner_error("control_true_failed")

    def test_missing_result(self):
        self.assert_runner_error("missing")

    def test_duplicate_result(self):
        self.assert_runner_error("duplicate")

    def test_unknown_result(self):
        self.assert_runner_error("unknown")

    def test_empty_result_name(self):
        self.assert_runner_error("empty_name")

    def test_previously_verified_source_changed(self):
        self.assert_runner_error("changed_after")

    def test_previously_verified_source_deleted(self):
        self.assert_runner_error("deleted_after")

    def test_new_source_without_theorems_created(self):
        self.assert_runner_error("created_after")

    def test_dependency_without_theorems_changed(self):
        self.assert_runner_error("dependency_changed")

    def test_manifest_changed(self):
        self.assert_runner_error("manifest_changed")

    def assert_inventory_accepts(self, prefix):
        first = self.project / "src/first.vr"
        first.write_text(prefix + '\npublic theorem alpha() ensures true proof by auto;\n')
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("3 obligation(s)", result.stdout)

    def test_nested_comments_do_not_create_declarations(self):
        self.assert_inventory_accepts('''/* outer /* inner */
public theorem comment_only() ensures false;
*/''')

    def test_lifetimes_and_escaped_characters_do_not_hide_declarations(self):
        self.assert_inventory_accepts(r'''fn borrow<'a>(x: &'a Text) -> &'a Text { x }
const apostrophe = '\'';
const slash = '\\';
const newline = '\n';
const unicode = '\u{1234}';
const byte = b'\x41';''')

    def test_triple_and_tagged_raw_literals_do_not_create_declarations(self):
        self.assert_inventory_accepts('''const text = """
public theorem raw_only() ensures false;
" and "" are content; so are // and /*
""";
const empty = """""";
const tagged = json#"""{ "text": "public theorem also_raw()" }""";''')

    def test_ambiguous_quote_run_fails_closed(self):
        first = self.project / "src/first.vr"
        first.write_text('const raw = """raw """"\npublic theorem hidden();\n""";\n')
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ambiguous raw quote run", result.stderr)

    def test_legacy_raw_literal_fails_closed(self):
        first = self.project / "src/first.vr"
        first.write_text('const raw = r#"theorem hidden()"#;\n')
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("legacy r# raw literal", result.stderr)

    def test_missing_summary(self):
        self.assert_runner_error("no_summary")

    def test_incorrect_summary(self):
        self.assert_runner_error("bad_summary")

    def test_failed_result_cannot_exit_success(self):
        self.assert_runner_error("wrong_exit")

    def test_report_cannot_mask_invocation_failure(self):
        self.assert_runner_error("exit_failure")

    def test_skipped_theorem_is_unmeasured(self):
        self.assert_runner_error("skipped")

    def test_open_proofs_are_distinct_from_runner_failure(self):
        result = self.run_runner("open")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("1 proved, 2 open", result.stdout)
        self.assertNotIn("RUNNER ERROR", result.stderr)

    def test_solver_timeout_is_a_measured_open_obligation(self):
        result = self.run_runner("timeout")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("TIMEOUT", result.stdout)
        self.assertNotIn("RUNNER ERROR", result.stderr)

    def test_failed_helper_does_not_become_theorem_success(self):
        result = self.run_runner("function_failed")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("helper", result.stdout)

    def test_process_timeout_is_runner_failure(self):
        result = self.run_runner("process_timeout", extra=("--timeout", "1"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("RUNNER ERROR", result.stderr)
        self.assertIn("control ok", result.stdout)
        self.assertIn("first.vr: verifier invocation exceeded", result.stderr)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_missing_verifier_is_runner_failure(self):
        self.verifier.unlink()
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("RUNNER ERROR", result.stderr)

    def test_empty_inventory_is_not_success(self):
        for path in (self.project / "src").glob("*.vr"):
            path.unlink()
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("no theorem, lemma, or corollary declarations", result.stderr)

    def test_temp_creation_failure_never_cleans_a_parent(self):
        # Intercept rm as an extra safety guard when testing the old shell
        # implementation: its unchecked mktemp failure tried to remove `/`.
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir()
        cleanup_log = Path(self.temp.name) / "cleanup.log"
        intercept = bin_dir / "rm"
        intercept.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CLEANUP_LOG"\nexit 77\n')
        intercept.chmod(0o755)
        result = self.run_runner(environment={
            "TMPDIR": str(self.scratch / "missing"),
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "CLEANUP_LOG": str(cleanup_log),
        })
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("RUNNER ERROR", result.stderr)
        self.assertFalse(cleanup_log.exists(), "cleanup ran without an owned directory")


if __name__ == "__main__":
    unittest.main()
