# Typed metadata runtime failure

T1666 remains open. The unchanged metadata candidate `399cc41` now reaches
interpreter execution, then fails with `Index out of bounds: index 0 for list
of length 0`. The ordinary run exits 1 after **166.19 seconds** with empty
stdout; it does not complete the metadata fixture.

The [run receipt](result.json) and original [stderr](stderr.log) identify
the exact CLI, component inputs and generated project. Source, project and
executable hashes stayed unchanged. The
[comparison](comparison.json) confirms every source/project hash matches
the [stage17 run](../publication-metadata-stage17/result.json), whose
forward-payload `DecodedDependencyOptions` E101 diagnostic is absent here.
The preserved candidate remains separate from registry main.

The [build manifest](build-manifest.json) identifies language reader
`faabbe696f1ee928f6b3a9bb6c7980ba20577513` and executable SHA256
`bb4ea411ab107ebc0426a0161d6c974df4d6ee1a209f14df9b21ac37e82c72d4`.
Its [build log](cli-build.log) records a precompile cache hit. The archived
`runtime.vbca`, `runtime.core_metadata` and `runtime.symbol_graph` were
rehashed against their manifests and are byte-identical to stage17 and the
original [stage16 producer](../compiler-stage16.json) at `d61c11aa5`.
This is a rebuilt compiler reader using the earlier producer artifacts.

The separate [diagnostic trace](diagnostic-trace/stderr.log) ends with
`publication_metadata.text_list` calling `JsonValue.as_array` before the
same runtime error. Its additional `VERUM_TRACE_CALLS=1` and
`VERUM_TRACE_PC=schema_values` settings are explicitly recorded in
[trace-environment.json](diagnostic-trace/trace-environment.json): the
unmodified runner receipt omits inherited trace flags. That diagnostic run
took 162.79 seconds and is not the ordinary run above. The last recorded
call narrows investigation; it does not prove the failing opcode or cause.
The runtime defect is tracked separately as T1684.

These receipts establish removal of the earlier component compilation
blocker and the subsequent execution failure. They establish neither
successful metadata decoding or publication admission, nor AOT or
whole-project acceptance.
