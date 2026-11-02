#!/usr/bin/env python3
"""What this programme actually puts through the compiler.

A proving ground is worth its name only for the constructs it EXERCISES,
so `ARCHITECTURE.md` carries a census — and a census that lives in prose
is a memory of a measurement rather than a measurement.  This is the
instrument, so the table can be re-run instead of trusted.

IT COUNTS CODE, NOT PROSE, and that distinction is the reason it exists.
The first version of the table was written with a plain `grep` and
counted comment lines as usages:

    claimed  measured   construct
        14         4    capabilities `with [ ]`
         3         0    rank-2 function types `fn<R>`
        23        70    sum-type variants

Every one of those gaps is a paragraph ABOUT the construct being counted
as a USE of it.  A document that discusses its own vocabulary at length —
which this one does deliberately — will always over-count itself that
way, and the more carefully it explains a construct the more it inflates.

`fn<R>` reaching ZERO is the sharpest case and the most useful: this
programme USES rank-2 types, through `Transducer<A, B>`, whose `transform`
field is declared `fn<R>(Reducer<B, R>) -> Reducer<A, R>` in
`core/base/iterator.vr`.  It never DECLARES one.  Those are different
claims about a proving ground and the table should not conflate them.

Run:  python3 tools/census.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def code_only(text: str) -> str:
    """Drop `//` comments, including trailing ones, without cutting inside a
    string literal — a `//` in a URL or a JSON body is code."""
    kept = []
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        cut, in_string, escaped = None, False, False
        for i, ch in enumerate(line):
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string and ch == "/" and line[i + 1: i + 2] == "/":
                cut = i
                break
        kept.append(line if cut is None else line[:cut])
    return "\n".join(kept)


# (label, pattern, what one hit means)
COUNTS = [
    ("format literals",            r'f"',                              "an f-string opens"),
    ("match arms",                 r'=>',                              "an arm arrow"),
    ("type declarations",          r'^(public )?type ',                "a top-level `type`"),
    ("`pure fn`",                  r'\bpure fn\b',                     "a purity-declared function"),
    ("sum-type variants",          r'^\s*\| [A-Z]',                    "a `| Variant` line"),
    ("contexts `using [ ]`",       r'using \[',                        "a `using` clause"),
    ("refinement types",           r'\{\s*it\s',                       "an `{it …}` refinement"),
    ("capabilities `with [ ]`",    r'with \[',                         "a `with` attenuation"),
    ("`@verify(formal)`",          r'@verify\(formal\)',               "an SMT obligation"),
    ("`@verify(runtime)`",         r'@verify\(runtime\)',              "a checked obligation"),
    ("theorems and lemmas",        r'^(public )?(theorem|lemma) ',     "a stated claim"),
    ("`async fn`",                 r'\basync fn\b',                    "an async declaration"),
    ("CBGR `&checked` / `&unsafe`", r'&checked\b|&unsafe\b',           "a tier annotation"),
    ("rank-2 types DECLARED",      r'fn<[A-Z]',                        "a `fn<R>` in a type"),
    ("protocol declarations",      r'is protocol',                     "a protocol"),
    ("generic impl blocks",        r'^implement<',                     "an `implement<T>` head"),
    ("`@cfg`",                     r'@cfg',                            "a conditional block"),
    ("`unsafe` blocks",            r'\bunsafe\s*\{',                   "an unsafe block"),
]


def sources() -> list[str]:
    out = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, "src")):
        for fn in sorted(files):
            if fn.endswith(".vr"):
                out.append(os.path.join(dirpath, fn))
    mod = os.path.join(ROOT, "mod.vr")
    if os.path.exists(mod):
        out.append(mod)
    return sorted(out)


def main(argv: list[str]) -> int:
    files = sources()
    text = "\n".join(code_only(open(p, encoding="utf-8").read()) for p in files)
    lines = sum(1 for l in text.splitlines() if l.strip())

    rows = [(label, len(re.findall(pat, text, re.M)), meaning)
            for label, pat, meaning in COUNTS]
    rows.sort(key=lambda r: -r[1])

    width = max(len(r[0]) for r in rows)
    for label, n, meaning in rows:
        print(f"  {n:5d}  {label:<{width}}  {meaning}")
    print(f"\n{len(files)} source files, {lines} lines of code "
          f"(comments and blank lines excluded)")

    if "--check-absences" in argv:
        # The absences the document claims are ZERO. An absence is a claim
        # like any other and rots the same way.
        #
        # `generic impl blocks` LEFT THIS LIST on 2026-09-06, and the way it
        # left is the point: the document argued the absence was the gap
        # worth closing, `node/store` closed it, and this check went red on
        # the same commit that made the prose true. A claim retired by being
        # made false is the only honest way off the list — an entry deleted
        # because it became inconvenient is how the list stops meaning
        # anything.
        bad = [label for label, n, _ in rows
               if n and label in ("`@cfg`", "`unsafe` blocks")]
        if bad:
            print(f"\nABSENCE CLAIM BROKEN: {', '.join(bad)} is no longer zero — "
                  f"ARCHITECTURE.md says it is.")
            return 1
        # And the reverse polarity: a construct the document now claims is
        # PRESENT must not quietly go back to zero.
        gone = [label for label, n, _ in rows
                if not n and label in ("generic impl blocks",)]
        if gone:
            print(f"\nPRESENCE CLAIM BROKEN: {', '.join(gone)} is back to zero — "
                  f"ARCHITECTURE.md says the programme writes one.")
            return 1
        print("\nabsence claims hold: no @cfg, no unsafe block; "
              "presence holds: at least one generic impl block")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
