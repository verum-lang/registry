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

echo "== proofs =="
# chapter:expected-proved:expected-failed
for row in versions:6:0 theorems:4:0 capabilities:3:0 ownership:4:0; do
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

[ "$fail" -eq 0 ] && echo "showcase intact" || echo "showcase CHANGED — update EXPECTED.txt only if the change is intended"
exit "$fail"
