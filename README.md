# Verum Registry

The registry is the delivery application for the Verum language platform.
Its first release must let a developer publish a cog and another developer
install and run that exact release in a fresh project. Official and private
registries use the same application with explicit configuration and trust
anchors.

The current application is a domain model and development service. Public
publishing is not ready: authenticated upload, durable release storage and
the client installation path still need integration and acceptance.

## Develop and validate

Use an identified Verum CLI build. Record its source commit and executable
hash when reporting results; an older executable does not validate the
current language source.

From this repository:

```sh
verum check
python3 -m unittest discover -s tests/tooling -v
tools/verify_obligations.sh /absolute/path/to/verum --timeout 600
python3 tools/census.py --check-absences
```

These commands have different purposes:

- Argument-less `verum check` checks the whole project. A successful check
  of one source file cannot replace it.
- The Python tests exercise the verification and component runners,
  including invalid reports and execution results. They do not execute
  the registry or establish theorem proofs.
- The obligation runner requires two false controls to fail and a true
  control to prove, then accounts for every declared obligation. Exit `0`
  means all measured obligations proved, `1` means open obligations, and
  `2` means the measurement is invalid. A timeout is never a pass.
- The census counts source constructs. Counts establish neither runtime
  coverage nor correct implementations of those constructs.

The rebuilt CLI at language commit `d61c11aa5` completed the whole-project
check in **211.317 seconds with 11 compilation errors**. The
[receipt](tests/evidence/project-check-stage16.json) identifies the executable
and every project input; the [raw log](tests/evidence/project-check-stage16.log)
preserves the diagnostics. The remaining errors concern spawned handles,
protocol implementation bounds, `IoResult` pattern checking, HTTP response
fields and transducer types. Context-declaration warnings also remain.
The registry does not yet pass project checking.

The previous `b12135c9f` product reported **64 errors in 217.97 seconds**;
its [receipt](tests/evidence/project-check-stage15.json) and
[log](tests/evidence/project-check-stage15.log) remain available. Every input
in that earlier receipt is byte-identical in the new run; the publication
envelope module and its fixture were added. The
[comparison](tests/evidence/stage16-comparison.json) records that boundary.
Multiple compiler changes separate the products, so these results do not
isolate the effect of one fix. The new
[build receipt](tests/evidence/compiler-stage16.json) and
[build log](tests/evidence/compiler-stage16.log) preserve the fresh automatic
standard-library bake and executable identity.

The separate typed publication-metadata candidate at `399cc41` was run with
that same compiler. It failed compilation with **18 errors in 69.97 seconds**:
one forward-reference error for a variant payload and seventeen mismatches
when a borrowed JSON object is passed to a typed map helper. The
[component receipt](tests/evidence/publication-metadata-stage16/result.json)
and [diagnostics](tests/evidence/publication-metadata-stage16/stderr.log)
preserve its unchanged production sources and fixture identity. The fixture
did not execute; this candidate has not been integrated into the registry
main branch. Passing standalone strict JSON controls in the language
repository does not establish typed metadata or publication admission.

The earlier [whole-project baseline](tests/evidence/project-check-stage14.json)
reached its 600-second deadline without a verdict on identical registry
`.vr` sources. The rebuilt product contains several language changes;
these two runs do not isolate the performance effect of one fix.

The runner's real three-theorem control passed on the same identified
CLI: both false theorems failed and the true theorem proved. Its
[receipt](tests/evidence/verifier-control-stage14.json) and
[complete report](tests/evidence/verifier-control-stage14.log) validate
the report contract; they do not establish the registry's proof outcomes.

The subsequent [registry proof sweep](tests/evidence/proof-census-stage14.json)
was refused because `src/node/cache.vr` failed compilation before producing
a verification report. No registry proof totals were accepted. The
[project-mode publication control](tests/evidence/publication-project-stage14.json)
also reached its 180-second deadline before runtime. These recorded
proof and publication controls remain pending replay with the rebuilt CLI.

The publication envelope component passes with the identified `b12135c9f`
interpreter. Its [receipt](tests/evidence/publication-envelope-stage15-retained/result.json),
[stdout](tests/evidence/publication-envelope-stage15-retained/stdout.log) and
[diagnostics](tests/evidence/publication-envelope-stage15-retained/stderr.log)
record the exact production module, fixture and executable hashes. The
179.91-second run checks UTF-8 and binary-byte fidelity, every truncated
prefix, malformed lengths, configured limits and trailing bytes. It also
retains one decoded result while changing the request: the retained result
stays unchanged and a second decode sees the changed metadata and archive.
This component result does not validate JSON schema, archive contents or
digests, authentication, persistence, AOT, or the complete service.

Replay it with an ordinary CLI and its full 40-digit source commit:

```sh
python3 tools/run_publication_envelope.py /absolute/path/to/verum \
  --language-commit FULL_SOURCE_COMMIT \
  --evidence-dir /absolute/path/to/new-evidence-directory
```

The evidence directory's parent must exist; the directory itself must be
new. The runner copies the production module byte for byte into a temporary
minimal project and changes only the fixture's entry module header. It
requires exact stdout, exit `0`, unchanged inputs and executable, and
completion within 600 seconds. Use `--expected-cli-sha256` to pin an
executable and `--timeout` to shorten the deadline. The earlier
[180-second timeout](tests/evidence/publication-envelope-stage15-timeout.json)
and [188.95-second completion](tests/evidence/publication-envelope-stage15-extended.json)
retain the original fixture's results separately; they do not measure a
performance change.

The exact-release catalog candidate at `e298e4e` was checked as a complete
project with its catalog control installed as the entry module. The same
`b12135c9f` CLI returned **49 compilation errors in 235.28 seconds**, including
source-owner resolution failures. Its [receipt](tests/evidence/catalog-check-stage15.json)
and [diagnostics](tests/evidence/catalog-check-stage15.log) preserve that
candidate's inputs separately from the registry main branch. No catalog
runtime, history isolation or restart acceptance follows from this failed
check; replay remains required with the corrected compiler.

The demonstration in `src/main.vr` uses a frozen clock and fixed local
configuration. Its default scenes access `/tmp/verum-registry-store`.
Its `serve` mode binds a local development listener; it is not a production
deployment configuration.

## First release acceptance

Each row needs an executable positive and negative control. A feature
annotation, generated page or successful process exit alone cannot close it.

| Boundary | Required observable result | Current work |
| --- | --- | --- |
| Authentication and upload | An authorized publisher uploads one source cog; missing, revoked and wrong-scope credentials are refused without mutation. The CLI and server agree on metadata and archive framing. | T1636, T1639 |
| Immutable publication | `name + exact version` identifies one release. Identical content is idempotent; different content is refused after newer versions, cache eviction and restart. Authority changes preserve original attribution. | T1632 covers in-memory history; T1647 covers durable history. |
| Artifact storage and recovery | Stored bytes match the accepted digest. Acknowledgement follows a durable commit; interrupted writes and concurrent conflicting publishes cannot expose partial or rewritten releases. | T1647 |
| Exact resolution and download | Metadata, archive and lockfile identify the configured registry and the same release. Corrupt bytes and unavailable releases are refused explicitly. | T1634, T1642 |
| Install, mount and run | A fresh project installs the published cog, mounts its exported function and runs it. Cache contents alone do not satisfy this boundary. | T1637, T1638 |
| Trust evidence | The client verifies actual signatures and log proofs over canonical content. Invalid signatures, changed bytes and altered upstream provenance are refused. | T1648 replaces the current evidence model with cryptographic verification. |
| Generated specifications | Contracts describe the implementation. Proof status is backed by a complete verification result tied to source and tool identity. | T1633, T1640, T1641 |

Run the complete flow against a temporary local service and empty client
home/cache, then repeat after restarting the service. Keep server state and
published bytes in test-owned directories. Record interpreter and AOT
results separately. The AOT artifact must also satisfy the platform's
runtime dependency policy.

## Language development through the registry

Develop registry behavior and the language support it needs together.
Context requirements, typed refusals, immutable coordinates, publication
resources and pure validation belong in the actual request path. Each
mechanism needs a control that breaks its claimed guarantee.

When a valid registry program reveals a language defect, retain the
program as a regression and repair the implementation. Do not replace
meaningful types with string encodings simply to avoid a compiler defect.
Federation, air-gap transfer and compiled-cog delivery build on the first
working source-cog publication flow.

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership and module boundaries.
Work is coordinated in the language project's shared task pool; this
repository has its own Git history. Commit small validated changes and
land them on `main` frequently.
