# Metadata diagnostic work

T1685 addresses eager indexed error paths in the T1666 schema decoder.
The original `399cc41` candidate remains unchanged for its independent
post-T1684 runtime replay.

Previously `text_list` formatted `f"{path}[{index}]"` before every call to
`text_value`, even for valid strings. A feature or dependency name becomes
part of `path`, so the work scales with key length multiplied by item count.
Those names are unvalidated source spellings at this decoding stage.

[source-analysis.json](source-analysis.json) records a source-derived
counterexample: the existing metadata baseline with a 65,536-byte feature
key and 50,000 empty-string members occupies 215,809 JSON bytes, below the
262,144-byte default. The final indexed paths alone contain
3,277,588,890 bytes cumulatively:

```python
sum(len("features.") + 65536 + len(str(i)) + 2 for i in range(50000))
```

This is arithmetic from the source loop, not measured interpreter timing,
allocation statistics or peak memory. No large stress input was executed.

The bounded [component fixture](../../publication_metadata.vr) uses a
1,024-byte key and 256 members alternating `"ok"` and `""`. Its 2,321-byte
document is below the fixture's explicit 4,096-byte ceiling. Every decoded
member must retain its value. Late invalid members must preserve exactly
`authors[2]`, `features.<the complete key>[2]` and
`dependencies.codec.features[2]`, with expected type `string`.

The repair formats an indexed path only in the type-refusal branch; valid
members use the same `JsonValue.as_string` extraction without constructing
that path. The explicit borrowed element access stays intact. Strict parsing,
schema and byte limits are unchanged.

These controls remain pending ordinary component execution after T1684.
Source and grammar review do not establish runtime, admission or AOT
acceptance.
