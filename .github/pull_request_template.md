# Pull Request

## Summary

<!-- 1-3 bullet points describing what changes and WHY. -->



## Test plan

<!-- Bulleted markdown checklist of TODOs for testing. -->
- [ ] `verum check --strict` passes locally
- [ ] `verum test --release` passes locally
- [ ] `verum audit --bundle --gate` passes locally (no new AP violations)
- [ ] Updated migrations are append-only (no edits to existing migration files)
- [ ] If touching ATS-V annotations: `@arch_module` / `@arch_corpus` lint clean

## ATS-V impact

<!-- Required when changing src/main.vr, src/audit/, or any @arch_module declaration. -->

- AP-001..AP-040 catalog: <!-- new pattern instances? -->
- Corpus invariants: <!-- NoCircularDependencies / FoundationConsistency / NoLAbsClaim / CapabilityClosure status -->
- SelfReferenceWitness: <!-- only main.vr should declare the canonical witness -->

## Security impact

<!-- Required when touching auth / publish / sigstore / tuf / webauthn / migrations. -->

- Threat-model deltas: <!-- which threats become more/less feasible? -->
- New capabilities required: <!-- list new `Capability.X` entries in `requires` slot -->
- Cryptographic primitives: <!-- algorithm + parameter changes -->

## Operational impact

- SLO impact: <!-- which SLOs (availability / publish latency p99 / search latency p99 / audit p99) does this affect? -->
- Backwards-incompatible? <!-- yes/no — if yes, link migration plan -->
- Rollback procedure: <!-- specific commands to undo if needed -->
