#!/usr/bin/env bash
# Gate: the showcase runs, prints what it printed last time, and every
# proof it states still discharges.
#
# The showcase is the project's argument for the language, so a chapter
# that silently stops proving is worse than one that never proved: the
# text around it keeps claiming the guarantee. Until this script existed
# the chapters were checked by hand, which is the same as not at all.
#
# THE PROOF COUNTS ARE PART OF THE GATE, not decoration. A compiler
# change can leave the printed output identical while a postcondition
# quietly stops discharging — that is exactly what happened to
# `versions.vr`, which reported 4 proved / 2 failed for three weeks
# while its guide asserted the opposite.
#
#   scripts/check-showcase.sh [path-to-verum]
set -uo pipefail

VERUM="${1:-verum}"
cd "$(dirname "$0")/.." || exit 2

fail=0

echo "== running the showcase =="
# No cache-bust here any more, and its absence is load-bearing history.
# It used to be mandatory: the persistent script cache was keyed on the
# ENTRY FILE'S CONTENT alone, so editing any mounted chapter left
# `verum run main.vr` executing the PREVIOUS build — with no warning and
# no note in the output. This gate once PASSED a deliberately broken
# chapter for exactly that reason.
#
# The cache now records the mount closure it compiled and re-verifies it
# on lookup (T1003), so an edited chapter is a miss. If a stale run ever
# reappears here, that check is the first thing to measure — not this
# script.
ENTRY=src/showcase/main.vr
actual=$("$VERUM" run "$ENTRY" 2>&1 | grep -v '^ *Running')
if ! diff -u src/showcase/EXPECTED.txt <(printf '%s\n' "$actual"); then
    echo "FAIL: output differs from src/showcase/EXPECTED.txt"
    fail=1
else
    echo "  output matches ($(wc -l < src/showcase/EXPECTED.txt | tr -d ' ') lines)"
fi

echo "== tier identity =="
# The `tiers` chapter claims that one bytecode has one behaviour. A claim
# a gate does not check is the thing this script exists to prevent, so the
# judge runs here over the WHOLE showcase — every chapter, not a probe
# written to pass.
#
# `verum diff-tiers` runs both tiers as subprocesses of the same binary,
# compares the program's output and exit status, and exits 3 on any
# difference. A tier that crashes is a recorded verdict, not a dead judge.
#
# This is the chapter's only claim, and it is the whole of it: if the two
# tiers ever disagree on the showcase, the chapter's text is false and this
# gate says so.
if verdict=$("$VERUM" diff-tiers "$ENTRY" 2>&1); then
    echo "  showcase: identical under both tiers"
else
    echo "$verdict" | sed -n '/verdict:/,$p' | head -12
    echo "FAIL: the tiers disagree on the showcase — src/showcase/tiers.vr claims they cannot"
    fail=1
fi

echo "== proofs =="
# chapter:expected-proved:expected-failed
for row in versions:6:0 theorems:4:0 capabilities:3:0 ownership:4:0 transducers:8:0 \
           termination:3:0; do
    ch="${row%%:*}"; rest="${row#*:}"
    want_p="${rest%%:*}"; want_f="${rest#*:}"
    line=$("$VERUM" verify "src/showcase/$ch.vr" 2>&1 | grep -oE 'Summary: [0-9]+ proved, [0-9]+ failed' | head -1)
    got_p=$(echo "$line" | grep -oE '^Summary: [0-9]+' | grep -oE '[0-9]+')
    got_f=$(echo "$line" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+')
    if [ "${got_p:-x}" = "$want_p" ] && [ "${got_f:-x}" = "$want_f" ]; then
        printf "  %-14s %s proved, %s failed\n" "$ch" "$got_p" "$got_f"
    else
        printf "  %-14s FAIL: expected %s proved / %s failed, got '%s'\n" \
               "$ch" "$want_p" "$want_f" "$line"
        fail=1
    fi
done

echo "== rejections =="
# Every chapter states in prose what the compiler REFUSES, and until now
# those statements were guarded by nothing: a chapter could stop
# rejecting and its comment would go on claiming the guarantee. That is
# the same failure `versions.vr` had — a claim outliving the thing it
# describes — one level up, in the text instead of the proof count.
#
# Each row is one such claim, made executable in src/showcase/rejected/.
# TWO things are checked, because either one alone drifts:
#   1. the program is still REJECTED, with the named code;
#   2. the chapter still CLAIMS that code — otherwise the gate goes on
#      testing a promise the text has already dropped.
# chapter:code:probe
for row in sizes:E400:width_mismatch \
           ownership:E310:use_after_move \
           effects:E503:pure_io \
           effects:E503:pure_calls_impure \
           effects:E503:pure_spawn \
           effects:E503:pure_mutates \
           transducers:E400:rank2_monomorphic_stage \
           termination:E321:measure_that_grows; do
    ch="${row%%:*}"; rest="${row#*:}"
    code="${rest%%:*}"; probe="${rest#*:}"
    got=$("$VERUM" check "src/showcase/rejected/$probe.vr" 2>&1 \
          | grep -oE 'error<E[0-9]+>' | head -1)
    if [ "$got" != "error<$code>" ]; then
        printf "  %-20s FAIL: expected %s, got '%s'\n" \
               "$probe" "$code" "${got:-no error at all}"
        fail=1
    elif ! grep -q "$code" "src/showcase/$ch.vr"; then
        printf "  %-20s FAIL: %s no longer claims %s — the gate is testing a promise the chapter dropped\n" \
               "$probe" "$ch.vr" "$code"
        fail=1
    else
        printf "  %-20s rejected with %s (claimed by %s)\n" \
               "$probe" "$code" "$ch.vr"
    fi
done

[ "$fail" -eq 0 ] && echo "showcase intact" || echo "showcase CHANGED — update EXPECTED.txt only if the change is intended"
exit "$fail"
