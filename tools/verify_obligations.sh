#!/usr/bin/env bash
# Which of this programme's stated obligations the prover actually
# discharges.
#
# `ARCHITECTURE.md` carries the answer, and a number in a document is the
# memory of a measurement. This is the measurement, shipped beside the
# claim for the same reason `tools/census.py` is — and it found the claim
# wrong twice: the document said all obligations were unproved while one
# is proved, and it recorded a language limitation that no longer exists.
#
# THE CONTROL IS NOT DECORATION. `verify` reporting "N proved, 0 failed"
# is evidence only if a FALSE claim in the same run would have failed.
# Every goal reports 0.00s, which is exactly what a vacuous pass looks
# like, so the run begins by proving two deliberately false theorems must
# FAIL. If the control does not fire, the script refuses to print a
# census at all rather than publishing numbers it cannot stand behind.
#
# Usage:  tools/verify_obligations.sh [path/to/verum]
set -u
VERUM="${1:-verum}"
cd "$(dirname "$0")/.." || exit 2

CTL="$(mktemp -d)/control.vr"
trap 'rm -rf "$(dirname "$CTL")"' EXIT
cat > "$CTL" <<'EOF'
pure fn is_false(b: Bool) -> Bool { b }
pure fn always_zero(n: Int) -> Bool { n == 0 }
public theorem every_bool_is_true(b: Bool) ensures is_false(b) proof by auto;
public theorem every_int_is_zero(n: Int) ensures always_zero(n) proof by auto;
fn main() { print("control"); }
EOF

if ! "$VERUM" verify "$CTL" 2>&1 | grep -q '✗ theorem every_int_is_zero'; then
    echo "CONTROL BROKEN: a deliberately false theorem was not reported failed."
    echo "Every number this script could print would be void. Refusing to print one."
    exit 2
fi
echo "control ok: a false theorem is reported failed"
echo

proved=0; failed=0; files=0
for f in $(grep -rl '^public theorem\|^public lemma' src/ | sort); do
    files=$((files + 1))
    out="$("$VERUM" verify "$f" 2>&1)"
    p="$(printf '%s' "$out" | grep -oE '✓ theorem [a-z_]+' | sed 's/✓ theorem //')"
    x="$(printf '%s' "$out" | grep -oE '✗ theorem [a-z_]+' | sed 's/✗ theorem //')"
    for t in $p; do proved=$((proved + 1)); printf '  PROVED  %-46s %s\n' "$t" "$f"; done
    for t in $x; do failed=$((failed + 1)); printf '  open    %-46s %s\n' "$t" "$f"; done
done

echo
echo "$((proved + failed)) theorem(s) in $files file(s): $proved proved, $failed open"
