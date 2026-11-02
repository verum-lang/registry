#!/usr/bin/env python3
"""Measure every declared theorem, lemma and corollary without false greens.

Usage: tools/verify_obligations.sh [path/to/verum] [--timeout SECONDS]
Requires Python 3.9+ and the Verum verifier's human report. `--timeout` bounds
each whole invocation, independently of the verifier's solver budget.

Exit 0 means complete coverage and every obligation proved. Exit 1 means
complete coverage with measured open/timeout verdicts. Exit 2 means the
measurement itself failed. These are proof-census results, not acceptance
of the registry's runtime, architecture, HTTP service or deployment.

The wire contract is VerifyCommand::display_report and CliError::exit_code
in the language repository. File verification has no JSON export; LSP mode
currently bypasses failure exit handling and omits skipped entries, so it
cannot supply this check. The runner checks full reports, summaries, exits
and exact declaration/result sets together. It does not infer proofs.
"""

import argparse
from collections import Counter
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
CONTROL = """pure fn is_false(b: Bool) -> Bool { b }
pure fn always_zero(n: Int) -> Bool { n == 0 }
public theorem every_bool_is_true(b: Bool) ensures is_false(b) proof by auto;
public theorem every_int_is_zero(n: Int) ensures always_zero(n) proof by auto;
public theorem a_bool_equals_itself(b: Bool) ensures b == b proof by auto;
fn main() { print("control"); }
"""
CONTROL_RESULTS = {
    "theorem every_bool_is_true": "failed",
    "theorem every_int_is_zero": "failed",
    "theorem a_bool_equals_itself": "proved",
}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
DECLARATION = re.compile(r"\b(theorem|lemma|corollary)\s+([^\W\d]\w*)\b")
RESULT = re.compile(
    r"^\s*([✓✗⚠-])\s+([^:]+): "
    r"(Proved in \d+(?:\.\d+)?s|Failed in \d+(?:\.\d+)?s|"
    r"Timeout after \d+(?:\.\d+)?s \(limit: \d+(?:\.\d+)?s\)|"
    r"Skipped \(no refinement types\))$"
)
SUMMARY = re.compile(
    r"^Summary: (\d+) proved, (\d+) failed, (\d+) timeout, (\d+) skipped$"
)
STATUS = {"✓": "proved", "✗": "failed", "⚠": "timeout", "-": "skipped"}
CHARACTER = re.compile(r"'(?:[^'\\]|\\(?:[nrt0abfv\\'\"]|x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}))'")
LIFETIME = re.compile(r"'[^\W\d]\w*")
LEGACY_RAW = re.compile(r'(?<!\w)r#{1,4}"')


class RunnerError(Exception):
    """No acceptance conclusion may be drawn from this invocation."""


def code_only(source):
    """Mask comments and literals for a conservative declaration inventory.

    This is not a Verum parser: the verifier still owns syntax and types.
    Missing, unexpected or duplicate declarations/results fail the census.
    Keep newlines while masking so source names can never come from prose.
    """
    out = list(source)
    i = 0
    while i < len(source):
        start = i
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
        elif source.startswith("/*", i):
            # The active lexer supports nesting; the EBNF's comment
            # production is not recursive. Never expose inner comment
            # prose as declarations while counting the compiler's input.
            depth = 1
            i += 2
            while i < len(source) and depth:
                if source.startswith("/*", i):
                    depth += 1
                    i += 2
                elif source.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise RunnerError("unterminated block comment in source inventory")
        elif LEGACY_RAW.match(source, i):
            raise RunnerError("legacy r# raw literal is outside the documented grammar; source inventory refused")
        elif source.startswith('"""', i):
            i += 3
            while i < len(source):
                if source.startswith('""""', i):
                    # EBNF calls four quotes an escaped triple quote;
                    # the active lexer closes on every run of >=3. A
                    # census cannot silently choose one interpretation.
                    raise RunnerError("ambiguous raw quote run: grammar and lexer disagree; source inventory refused")
                elif source.startswith('"""', i):
                    i += 3
                    break
                else:
                    i += 1
            else:
                raise RunnerError("unterminated raw literal in source inventory")
        elif source[i] == "'":
            # A char closes immediately after one character or escape;
            # a lifetime ('a, 'static) has no closing quote. Do not scan
            # from one lifetime to the next and mask intervening code.
            literal = CHARACTER.match(source, i) or LIFETIME.match(source, i)
            if not literal:
                raise RunnerError("malformed character/lifetime token in source inventory")
            i = literal.end()
        elif source[i] == '"':
            quote = source[i]
            i += 1
            while i < len(source):
                if source[i] == "\\":
                    i += 2
                elif source[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise RunnerError("unterminated literal in source inventory")
        else:
            i += 1
            continue
        for j in range(start, min(i, len(source))):
            if out[j] != "\n":
                out[j] = " "
    return "".join(out)


def snapshot_inputs():
    """Capture the source set, including files without their own theorem."""
    files = sorted((ROOT / "src").rglob("*.vr"))
    files += sorted(ROOT.glob("*.vr"))
    files += [ROOT / name for name in ("verum.toml", "verum.lock") if (ROOT / name).exists()]
    return {path: path.read_bytes() for path in files}


def inventory(inputs=None):
    inputs = snapshot_inputs() if inputs is None else inputs
    found = {}
    for path, contents in inputs.items():
        if path.suffix != ".vr":
            continue
        source = contents.decode("utf-8")
        names = [f"{kind} {name}" for kind, name in DECLARATION.findall(code_only(source))]
        if len(names) != len(set(names)):
            raise RunnerError(f"{path}: duplicate obligation name; coverage is ambiguous")
        if names:
            found[path] = (source, set(names))
    if not found:
        raise RunnerError("no theorem, lemma, or corollary declarations found; nothing was verified")
    return found


def parse_report(output, expected, exit_code, label):
    rows = {}
    summaries = []
    for line in ANSI.sub("", output).splitlines():
        match = RESULT.fullmatch(line)
        if match:
            marker, name, detail = match.groups()
            name = name.strip()
            if not name:
                raise RunnerError(f"{label}: empty result name")
            status = STATUS[marker]
            if not detail.lower().startswith(status):
                raise RunnerError(f"{label}: contradictory result marker: {line}")
            if name in rows:
                raise RunnerError(f"{label}: duplicate result for {name}")
            rows[name] = status
        summary = SUMMARY.fullmatch(line)
        if summary:
            summaries.append(tuple(map(int, summary.groups())))
    if len(summaries) != 1:
        raise RunnerError(f"{label}: expected one complete verification summary, found {len(summaries)}")
    counts = Counter(rows.values())
    actual_counts = tuple(counts[s] for s in ("proved", "failed", "timeout", "skipped"))
    if summaries[0] != actual_counts:
        raise RunnerError(f"{label}: report rows disagree with summary: {actual_counts} vs {summaries[0]}")
    obligations = {name for name in rows if name.split()[0] in ("theorem", "lemma", "corollary")}
    missing, extra = expected - obligations, obligations - expected
    if missing or extra:
        raise RunnerError(f"{label}: coverage mismatch; missing={sorted(missing)}, unexpected={sorted(extra)}")
    skipped = sorted(name for name in expected if rows[name] == "skipped")
    if skipped:
        raise RunnerError(f"{label}: declared obligations were skipped, not measured: {skipped}")
    # Current VerifyCommand returns 105 for Failed, but returns 0 for a
    # timeout-only report. The census still fails acceptance on timeouts.
    expected_exit = 105 if counts["failed"] else 0
    if exit_code != expected_exit:
        raise RunnerError(f"{label}: exit {exit_code} contradicts complete report (expected {expected_exit})")
    return rows


def verify(verum, path, expected, timeout):
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env.pop("VERUM_LSP_MODE", None)  # Require the complete human report.
    process = subprocess.Popen(
        [verum, "verify", str(path)], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        # Cancel the owned process group, including any external solver.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        if isinstance(error, KeyboardInterrupt):
            raise
        raise RunnerError(f"{path}: verifier invocation exceeded {timeout:g}s") from error
    try:
        return parse_report(output, expected, process.returncode, str(path))
    except RunnerError as error:
        raise RunnerError(f"{error}\nVerifier output:\n{output}") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verum", nargs="?", default="verum")
    parser.add_argument("--timeout", type=float, default=600, help="whole invocation deadline in seconds")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")
    # Resolve a supplied relative executable before entering the project.
    verum = str(Path(args.verum).resolve()) if os.sep in args.verum else args.verum
    try:
        inputs = snapshot_inputs()
        declarations = inventory(inputs)
        # An explicit bad TMPDIR is an error, never a fallback. The context
        # manager is installed only after creation succeeds and owns exactly
        # this directory; no derived parent path is ever recursively removed.
        with tempfile.TemporaryDirectory(prefix="registry-obligations-", dir=os.environ.get("TMPDIR")) as owned:
            control = Path(owned) / "control.vr"
            control.write_text(CONTROL, encoding="utf-8")
            rows = verify(verum, control, set(CONTROL_RESULTS), args.timeout)
            if any(rows[name] != status for name, status in CONTROL_RESULTS.items()):
                raise RunnerError("controls must refute both false theorems and prove the true theorem")
            print("control ok: both false theorems failed; true theorem proved")
            measured = []
            for path, (source, expected) in declarations.items():
                rows = verify(verum, path, expected, args.timeout)
                if path.read_text(encoding="utf-8") != source:
                    raise RunnerError(f"{path}: source changed during measurement")
                measured.append((path, expected, rows))
            # Re-read ALL inputs after the final invocation. A previously
            # verified file, an imported helper, or the discovered file set
            # can change while later files are being verified.
            final_inputs = snapshot_inputs()
            if final_inputs != inputs:
                added = sorted(str(p.relative_to(ROOT)) for p in final_inputs.keys() - inputs.keys())
                removed = sorted(str(p.relative_to(ROOT)) for p in inputs.keys() - final_inputs.keys())
                changed = sorted(str(p.relative_to(ROOT)) for p in inputs.keys() & final_inputs.keys()
                                 if inputs[p] != final_inputs[p])
                raise RunnerError(f"project inputs changed during measurement: added={added}, removed={removed}, changed={changed}")
        proved = opened = 0
        other_open = []
        for path, expected, rows in measured:
            for name in sorted(expected):
                status = rows[name]
                proved += status == "proved"
                opened += status != "proved"
                print(f"  {status.upper():7} {name:52} {path.relative_to(ROOT)}")
            other_open.extend((path, name, status) for name, status in rows.items()
                              if name not in expected and status in ("failed", "timeout"))
        print(f"\n{proved + opened} obligation(s) in {len(measured)} file(s): {proved} proved, {opened} open")
        for path, name, status in other_open:
            print(f"  Other verification obligation: {name}: {status} ({path.relative_to(ROOT)})")
        return 1 if opened or other_open else 0
    except (RunnerError, OSError, UnicodeError) as error:
        print(f"RUNNER ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
