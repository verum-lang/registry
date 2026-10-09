# Registry architecture

The registry is a Verum application with pure domain rules, explicit
environmental dependencies and a transport boundary. The release criterion
is the publish-to-install flow in [README.md](README.md), including its
failure controls and restart behavior.

## Responsibilities

| Area | Responsibility |
| --- | --- |
| `src/protocol/authority.vr` | Assign a name to one configured authority; refuse ambiguous ownership. |
| `src/protocol/evidence.vr` | Represent the manifest/evidence relationship and typed refusals. Its current checks are a model, not cryptographic verification. |
| `src/protocol/query.vr`, `version.vr`, `source.vr` | Define query, version and source semantics independently of a selected backend. |
| `src/node/ambient.vr` | Declare clock, node identity and upstream availability contexts. |
| `src/node/publish.vr` | Apply publication policy and consume a publication slot. |
| `src/node/cache.vr`, `store.vr`, `retention.vr` | Maintain an evictable read projection with explicit retention capabilities. |
| `src/node/durable.vr`, `slice.vr`, `ingest.vr` | Model persistence and import boundaries. Production publication must connect them to durable artifact storage and recovery. |
| `src/node/serve.vr` | Adapt HTTP requests and typed domain results. Authentication and the CLI upload contract must be completed here and at the client boundary. |
| `src/main.vr` | Select concrete backends and run the demonstration or development listener. |

Domain rules should not depend on node or transport types. There is a
current violation: `protocol/wire.vr` imports `node/publish.PublishRequest`.
Reconcile that dependency when defining the shared upload contract. The
target layering is a design constraint, not a claim that the current
module graph already enforces it.

## Publication owns history; the cache owns a projection

A release coordinate consists of the package name and exact version.
Authority identifies the publisher and its provenance; it is not an extra
key field that permits a different release at the same coordinate after
configuration changes.

Publication history must retain all accepted versions. A name-keyed cache
can provide a convenient current answer, but advancing or evicting that
answer must not permit rewriting an earlier release. T1632 separates these
responsibilities in an exact-coordinate catalog. Its regression covers an
accepted v1, accepted v2 and a conflicting retry of v1, as well as identical
retries and authority changes. Parser checks are insufficient acceptance
for its `Map` key behavior.

The history must ultimately be durable. An accepted response must follow
the storage transaction, including archive bytes and their evidence.
In-memory insertion alone cannot guarantee immutability across a restart
or two service workers. Commit-or-abort resources should express this duty
on the production path and be tested under interrupted writes.

## Trust boundaries

Names, versions, metadata, credentials and archive bytes are untrusted
inputs. Invalid inputs return typed refusals without changing accepted
state. Refinements describe values the implementation has established;
they must not let malformed requests terminate the service.

The current `SignatureBundle` contains digest text and a signer name, and
`InclusionProof` contains digest text, log identity and tree size.
`digest_of` formats text. These values do not implement signatures,
cryptographic hashing or transparency proofs. The current verifier does
not authenticate the signer.

`Verified` also lacks the complete original evidence needed to forward an
upstream publication unchanged. The slice exporter currently reconstructs
placeholder evidence. The production format must retain the actual signed
manifest and proofs, verify them at the client, and bind them to archive
bytes. No proof or signature should be invented during caching or export.

Storage currently serializes pipe-separated fields without escaping.
Production persistence needs an unambiguous versioned encoding, bounded
parsing, integrity checks and atomic recovery. The development listener
starts with an empty cache and does not restore published releases.

## Language mechanisms and their acceptance

Use each mechanism where its semantics express a registry requirement.
Declarations and demonstration scenes alone do not establish request-path
coverage.

| Mechanism | Registry responsibility | Required control |
| --- | --- | --- |
| Pure functions | Validate ownership, versions and evidence from explicit inputs. | A forbidden I/O operation is rejected by whole-project checking. |
| Contexts and scoped providers | Supply clock, identity, storage and connectivity at the composition root. | Missing or incompatible providers fail; changing a provider changes only the relevant behavior. |
| Typed refusals | Preserve distinctions such as wrong authority, content conflict, unavailable upstream and corrupt storage. | Each refusal leaves prior accepted state intact. |
| Affine publication resources | Prevent duplicate completion within one request's control flow. | Reusing a slot is refused. Network retries still require coordinate-level idempotency. |
| Linear completion resources | Require commit or abort of a durable write. | Omitting either completion is refused; both outcomes execute correctly. |
| Capabilities | Limit cache and storage operations available to a helper. | A helper with eviction rights cannot write publications. |
| Structured concurrency | Complete or cancel all child work before publishing an import result. | A failed child leaves no partial accepted import. |
| Protocols and generic collections | Share real query and source behavior while preserving concrete value identity. | Distinct and equal values behave consistently across modules and execution tiers. |
| Theorems and refinements | State domain invariants beside their implementations. | Complete verifier reports, false controls and runtime checks establish the appropriate level of enforcement. |

`race_mirrors`, `ingest` and `ingest_volatile` are currently declared but
uncalled by the composition root. They are candidates for integration
when their domain boundary becomes part of the service. Their presence
must not be presented as end-to-end concurrency or durability acceptance.

The sources carry `@arch_module` annotations. The CLI does not implement a
`[build] arch-check` setting, so the manifest does not claim to enable one.
An architectural gate
needs an actual command, meaningful assertions and a deliberately invalid
module edge as a negative control.

## Evidence and documentation

Use `tools/census.py` for current construct counts and
`tools/verify_obligations.sh` for current proof outcomes. The previous
verification script could report success after verifier invocation errors;
its historical proof totals are not current acceptance evidence.

The replacement runner checks named results, source coverage, summaries,
exit semantics and positive/negative proof controls. Its tooling tests
validate report handling. Actual theorem results still require running
the real verifier on the identified project and tool build.

Generated specifications should carry source identity and verification
receipts as evidence. An `@verify` annotation requests verification; it
does not itself prove the annotated declaration. The language documentation
generator currently needs this distinction repaired under T1640.

Demonstration output is useful for exploration. Automated acceptance needs
assertions and exact output or state oracles, including corrupt input,
restart and conflicting publication controls. Track failures as failures;
do not substitute a parser pass, empty report or exit code for the result
the developer would observe.
