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

### PostgreSQL publication storage

Apply `migrations/001_publications.sql` as the schema owner. Grant the
registry's separate login role `USAGE` on schema `public` and only
`SELECT, INSERT` on `public.verum_publications`. Use a logged table on a
writable primary with `fsync` and `full_page_writes` enabled. The registry
requires synchronous local commits for each publication.

Set `VERUM_REGISTRY_STORAGE=postgres` and supply `VERUM_REGISTRY_PG_HOST`,
`VERUM_REGISTRY_PG_PORT`, `VERUM_REGISTRY_PG_DATABASE`,
`VERUM_REGISTRY_PG_USER` and `VERUM_REGISTRY_PG_PASSWORD` alongside the
listener, credential and authority settings. TLS defaults to `verify-full`.
The local test selects `VERUM_REGISTRY_PG_TLS=disable` for its isolated
loopback database. `VERUM_REGISTRY_PG_CONNECTIONS` sets the pool maximum
from 1 to 64 and defaults to 8. The default file backend uses
`VERUM_REGISTRY_STORE`.

The isolated Docker runner uses a locally available `postgres:17-alpine`
image and an identified Verum CLI. Run the adapter, authenticated transaction
and listener gates independently with
`python3 tools/test_publication_postgres.py /absolute/path/to/verum --component storage`,
then `--component transaction`, `--component handler` and `--component http`.
The handler gate sends requests through the production Weft handler, reads the
accepted bytes from PostgreSQL independently and verifies exact downloads both
before and after restarting PostgreSQL and the application process. The HTTP
gate opens the TCP listener and invokes the public package client.
`--component reconnect` terminates the database session during a blocked
publication and verifies that the running pool replaces it and safely retries.

### Exact-version installation and advisories

Configure `VERUM_REGISTRY_ADVISORIES` to point to a separate directory owned by
the registry's advisory operator. Grant the service read-only filesystem access.
The publication API cannot write reports. Provision a report for each reviewed source archive using
the filename `<coordinate-key>-<archive-sha256>.json`. The coordinate key is
SHA-256 of `verum-source-release-v1` followed by a NUL, the UTF-8 package name,
a NUL and the UTF-8 version. Install updates to a report with an atomic rename.

A report contains `package`, `version` and `vulnerabilities`. Each finding has
`id`, `severity` (`low`, `medium`, `high` or `critical`), `title`,
`description` and a `patched_versions` array of strings. Write an empty array
only for a reviewed release with no recorded findings. A missing directory
configuration, absent report or invalid report makes the advisory query for a
published release return 503. A configured directory must exist at startup.
Reports are limited to 256 KiB.

Run `python3 tools/test_publication_install.py /absolute/path/to/verum` to
publish and install with real package commands and fresh client profiles.
Its loopback HTTP transport forwards requests to the production Weft handler.
The client verifies the downloaded SHA-256, then records the dependency and
exact registry coordinate in its manifest and lockfile. Add `--execute-installed`
to publish a unique export and run it from a fresh consumer with the publisher's
source removed. The gate also changes and removes the cached archive and checks
that the consumer refuses both cases without contacting the registry.

Registry commit `8ad0abc` passed the whole-project check. The CLI with
SHA-256 `077b3e309558074ae8e2b1481e137f3264c1d8c0cd0a6d6e990538942ddbf2ae`
checked all 40 production files in 71 seconds.

An earlier whole-project check evaluated authentication candidate
`c02238261` with the freshly baked CLI from language commit `49559a042`.
It completed in **349.31 seconds with 2 compilation errors** and exited 101:
the slice importer disagrees with the language's spawned-handle and await
result types (T1681). The earlier response-field assignment and two IoResult
pattern errors are absent; context-declaration warnings remain. The
[receipt](tests/evidence/publication-stage21/whole-project/result.json) and
[diagnostics](tests/evidence/publication-stage21/whole-project/stderr.log.gz)
identify the exact candidate, tool and inputs. Registry main has not been
relabelled as that tested candidate.

The [comparison](tests/evidence/publication-stage21/comparison.json) records all
33 unchanged inputs from the preceding five-error check and 16 added
compilation inputs, including three authentication/preparation modules.
Several compiler changes separate the products; totals and run times do not
isolate one fix or establish a performance improvement. The previous
[five-error receipt](tests/evidence/project-check-stage20.json) and
[raw log](tests/evidence/project-check-stage20.log) remain available.

The actual authentication component now passes using configuration, SHA-256,
authority and scope validation. The public prepared-value consumption control
also passes, and a second consuming use is refused with E310. However, four
external private-field access/construction controls are incorrectly accepted
(T1713), and compiled field visibility also needs repair (T1714). Preparation,
credential-file loading and bounds fixtures stop before runtime on compiler
ownership errors. The [boundary report](tests/evidence/publication-stage21/README.md)
retains these distinct outcomes. The authentication candidate remains separate
from main; public upload and durable publication are not ready.

The previous `faabbe696` check reported
[9 errors in 216.409 seconds](tests/evidence/project-check-stage18.json).
Its four source-protocol bound errors were absent in the subsequent five-error result.
The [comparison](tests/evidence/stage20-comparison.json) records every common,
changed and added input, including the newly integrated publication decoder.
Several compiler changes and source additions separate the checks; the
reported totals do not isolate one fix or establish a performance change.
These checks do not establish runtime, AOT or deployment acceptance.

The earlier `d61c11aa5` product reported
[11 errors in 211.317 seconds](tests/evidence/project-check-stage16.json).
Every earlier source input is unchanged; three standalone task-handle controls
were added outside `src`. The [comparison](tests/evidence/stage18-comparison.json)
records the exact boundary. The current reader's
[build receipt](tests/evidence/publication-metadata-stage18/build-manifest.json)
identifies the reused standard-library producer artifacts. These checks do not
establish runtime, AOT or deployment acceptance.

The previous `b12135c9f` product reported **64 errors in 217.97 seconds**;
its [receipt](tests/evidence/project-check-stage15.json) and
[log](tests/evidence/project-check-stage15.log) remain available. Every input
in that earlier receipt was byte-identical in stage16; the publication
envelope module and its fixture were added. The
[comparison](tests/evidence/stage16-comparison.json) records that boundary.
Multiple compiler changes separate the products, so these results do not
isolate the effect of one fix. The stage16
[build receipt](tests/evidence/compiler-stage16.json) and
[build log](tests/evidence/compiler-stage16.log) preserve the fresh automatic
standard-library bake and executable identity.

The complete typed publication-metadata component passes with the fresh
`9b9c04a8a` interpreter. The original `399cc41` candidate passed in **210.71
seconds**; the accepted lazy diagnostic-path candidate `24bc455` passed in
**213.26 seconds**. Both require exact stdout and unchanged source, generated
project and executable hashes. Their
[comparison](tests/evidence/publication-metadata-stage20/comparison.json),
[original receipt](tests/evidence/publication-metadata-stage20/original/result.json)
and [accepted-source receipt](tests/evidence/publication-metadata-stage20/lazy/result.json)
retain the complete results and fresh compiler identity. The integrated
production modules, fixture and runner are byte-identical to the tested lazy
candidate. The prepared integration also passed all 64 Python tooling tests.

This checks strict JSON/schema decoding, required-field and duplicate-key
refusals, typed dependency options, null/empty/false preservation, framing and
archive-byte preservation. The bounded lazy-path controls retain exact
nonzero-index diagnostic paths without constructing them for successful list
items. The run times above do not measure a performance improvement.
Semantic name/version/checksum admission, digest and archive validation,
authentication, durable storage, AOT and the whole service remain separate.

The earlier `22a061ae6` product passed valid-value checks but accepted a document
missing the required nullable description. Its
[174.83-second failure](tests/evidence/publication-metadata-stage19/result.json)
and [diagnostics](tests/evidence/publication-metadata-stage19/stderr.log)
remain preserved. The original fixture and both production modules are
unchanged in the passing replay. The language repair separates a callable's
residual return type from a record field's temporary type hint. The preceding
[array-reference failure](tests/evidence/publication-metadata-stage18/result.json)
is also retained as its own boundary.

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

Select the metadata component with the same runner:

```sh
python3 tools/run_publication_envelope.py /absolute/path/to/verum \
  --component metadata --language-commit FULL_SOURCE_COMMIT \
  --expected-cli-sha256 EXECUTABLE_SHA256 \
  --evidence-dir /absolute/path/to/new-metadata-evidence-directory
```

This requires a CLI whose standard library includes `parse_strict`. It copies
both `publication.vr` and `publication_metadata.vr` unchanged and runs the
metadata fixture with the same input, output and deadline checks. The receipt
identifies metadata decoding separately from the default envelope component.
The complete component passes on the identified `9b9c04a8a` interpreter.
It covers envelope composition and strict JSON schema decoding, without
establishing semantic name/version/checksum admission, archive validity,
authentication or persistence.

This integration combines the decoder and component runner from `399cc41`
with the lazy diagnostic-path change and controls from `24bc455`, without
further algorithm changes. Both original candidates remain preserved for
independent replay. The stage19 failure above remains a baseline for its
identified inputs. The passing original and lazy replays establish the
component boundary for the exact integrated code and fixtures.

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
| Advisory availability | The configured registry returns a valid report for the exact coordinate from an actual authoritative query. Unavailable, malformed and wrong-coordinate reports stop installation before archive download or manifest/lockfile changes; an unavailable source never becomes an empty report. | T1636 service integration; T1673 defines the client refusal policy. |
| Install, mount and run | A fresh project installs the published cog, mounts its exported function and runs it. Cache contents alone do not satisfy this boundary. | T1637, T1638 |
| Trust evidence | The client verifies actual signatures and log proofs over canonical content. Invalid signatures, changed bytes and altered upstream provenance are refused. | T1648 replaces the current evidence model with cryptographic verification. |
| Generated specifications | Contracts describe the implementation. Proof status is backed by a complete verification result tied to source and tool identity. | T1633, T1640, T1641 |

Publication metadata and archive endpoints alone are insufficient for CLI
installation: the registry must also answer
`GET /api/v1/security/vulnerabilities/<name>/<version>`. See the
[advisory read contract](ARCHITECTURE.md#advisory-read-contract) for the
response authority, current client policy and refusal controls.

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
