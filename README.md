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
- The Python tests exercise the verification runner, including invalid
  reports. They do not execute the registry or establish theorem proofs.
- The obligation runner requires two false controls to fail and a true
  control to prove, then accounts for every declared obligation. Exit `0`
  means all measured obligations proved, `1` means open obligations, and
  `2` means the measurement is invalid. A timeout is never a pass.
- The census counts source constructs. Counts establish neither runtime
  coverage nor correct implementations of those constructs.

The whole-project baseline recorded in
[tests/evidence/project-check-stage14.json](tests/evidence/project-check-stage14.json)
reached its 600-second deadline without a verdict. It uses the recorded
older CLI product; current-source acceptance remains pending.

The runner's real three-theorem control passed on the same identified
CLI: both false theorems failed and the true theorem proved. Its
[receipt](tests/evidence/verifier-control-stage14.json) and
[complete report](tests/evidence/verifier-control-stage14.log) validate
the report contract; they do not establish the registry's proof outcomes.

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
| Immutable publication | `name + exact version` identifies one release. Identical content is idempotent; different content is refused after newer versions, cache eviction and restart. Authority changes preserve original attribution. | T1632 covers in-memory history; durable history remains open. |
| Artifact storage and recovery | Stored bytes match the accepted digest. Acknowledgement follows a durable commit; interrupted writes and concurrent conflicting publishes cannot expose partial or rewritten releases. | Storage and recovery acceptance remains open. |
| Exact resolution and download | Metadata, archive and lockfile identify the configured registry and the same release. Corrupt bytes and unavailable releases are refused explicitly. | T1634, T1642 |
| Install, mount and run | A fresh project installs the published cog, mounts its exported function and runs it. Cache contents alone do not satisfy this boundary. | T1637, T1638 |
| Trust evidence | The client verifies actual signatures and log proofs over canonical content. Invalid signatures, changed bytes and altered upstream provenance are refused. | Current evidence records model these relationships; cryptographic acceptance remains open. |
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
