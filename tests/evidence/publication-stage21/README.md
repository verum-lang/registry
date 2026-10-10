# Authentication candidate and compiler boundaries

The [comparison](comparison.json) records the fresh automatic CLI build and
complete-project check of candidate `c02238261`. All 33 inputs from the previous
check are unchanged; 16 compilation inputs were added, including three
production authentication/preparation modules. The candidate finishes with two
errors in slice task-handle typing (T1681). The earlier response assignment and
two IoResult pattern errors are absent. Context warnings remain.

Actual authentication and private-state isolation components pass. The latter
appends a test-only helper and does not prove external privacy. Preparation,
credential-file loading and the bounds fixture stop before runtime on method
or constructor ownership errors; preparation also has a borrowed array/List
mismatch. These failures remain distinct from unmeasured runtime behavior.

The public single-consumption control passes and affine reuse is specifically
refused with E310. Four external private-field read/construction controls are
incorrectly accepted (T1713). T1714 tracks the archive producer that currently
promotes record fields to public. The authentication candidate is therefore
held separately from registry main.

The language repository's committed `registry-stage21-runtime` and
`registry-stage21-publication` evidence directories retain exact project/source
bytes, runners and raw outputs. This directory retains the registry-facing
receipts and diagnostics, together with the build identity. Original failed
receipts are retained without replacing their verdicts. No whole-service,
durable storage, deployment, installation or AOT acceptance follows.
