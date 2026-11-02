# Spawned handle controls

All three controls failed before runtime with the ordinary interpreter
product from language commit `3821b1961cd057fd03c9e6d39cbf50609261e4eb`.
The [summary](summary.json) pins each fixture, receipt and log. The existing
[build manifest](../publication-metadata-stage17/build-manifest.json) identifies
the executable and its retained standard-library artifacts.

| Control | Observed failure | Elapsed |
| --- | --- | --- |
| [Inferred keyword handle](../../language/task_handle_inferred.vr) | VBC codegen: `Future implementation has no callable poll` | 64.240 s |
| [Declared source handle](../../language/task_handle_declared.vr) | VBC codegen: `variant 'Ready' not defined: Poll type must be in scope for Future await` | 67.412 s |
| [Record-held source handle](../../language/task_handle_record.vr) | Type checking: the `handle` field expects `core.async.task.JoinHandle<…>` but keyword spawn supplies `JoinHandle<…>` | 64.261 s |

Every process exited `1` before its 120-second deadline, with empty stdout.
The fixture and executable hashes remained unchanged. Each control's directory
contains the exact `result.json`, `stdout.log` and `stderr.log` from that run.
Their absolute scratch paths are historical run locations; the byte-identical
fixtures are tracked under `tests/language/`.

The inferred control asks for the compiler's raw keyword result, including a
child `Result`. The declared and record controls ask for the source
`JoinHandle<T>` implementation's `Result<T, JoinError>` output. These are
diagnostic controls for the competing contracts, not three interchangeable
spellings already known to work. T1681 tracks a consistent declaration,
runtime carrier and completion contract.

No child ran. These failures establish neither successful task completion nor
panic, cancellation, sibling draining or cache preservation. AOT and registry
service behavior were not tested.

## Invocation boundary

Replay one fixture at a time with an identified ordinary CLI. Copy the fixture
byte for byte to a new directory containing no `verum.toml`, preserving its
filename, and run from an otherwise empty directory:

```sh
NO_COLOR=1 VERUM_NO_OBJECT_CACHE=1 /absolute/pinned/verum \
  run --tier interpret /absolute/copied-fixture/task_handle_inferred.vr
```

Use the matching filename for the other two controls. Apply a 120-second
per-process deadline in the invoking harness, capture stdout and stderr,
and compare source and executable hashes before and after. The exact
commands, environment and expected stdout for these runs are retained in
each receipt. A compiler error or timeout is a failed control, even when
it matches one of the failures recorded here.

The production slice completion candidate is preserved separately at registry
commit `c2a47e4b0feb278e00d0f6ef9e9f0e25af962e6f`. That candidate contains
`tests/slice_completion.vr` and its expected output; they need a complete
registry project and cannot be run as these standalone files. Its source
changes and completion fixture are not included in this evidence commit.
T1678 remains blocked on T1681. No source reordering, fabricated join result
or registry-specific carrier workaround was used.
