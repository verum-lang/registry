# How this program is put together

This describes the arrangement that emerged and the reasons for it. It
is meant to be read as a worked example of structuring a Verum program,
not as a set of rules invented in advance.

## The layers, and what each is allowed to know

```
protocol/       the rules.        Pure. No contexts. No I/O.
  authority     who may answer for a name
  evidence      what a client checks before believing
  hash          a digest carries its width in its type
  query         what a question means, and what it costs
  source        where bytes come from (a protocol + two implementations)
  version       which version a constraint means

node/           the policy.       Uses contexts. Still no I/O.
  ambient       the contexts themselves, and backends for them
  cache         what a node keeps and what it says offline
  consistency   auditing a cache against the heads it has seen
  durable       surviving a restart
  handshake     meeting an upstream, once per session
  publish       the write path
  search        one question, three answers
  slice         carrying a registry across an air gap

main.vr         the composition root.
                The ONLY place that names a concrete backend.
```

The direction of knowledge is one-way and worth stating positively:
`protocol/` does not know that nodes exist, `node/` does not know which
clock it runs against, and `main.vr` is the only file that knows both.

### The rule layer is `pure`, and that is checked

Every free function in `protocol/` is declared `pure`. It is not a
label: `pure` is compiler-verified, and a pure function may not perform
I/O or call an impure one, so the layering is a fact the compiler holds
rather than a convention a reviewer has to notice.

The claim was confirmed by breaking it — a `print` added to
`digest_of` is refused with `error<E503>: pure function has side
effects: IO`. Worth knowing while reading this: `verum check` enforces
it and `verum run` currently does not in project mode, which is filed;
the annotations are honest under the command that verifies them.

### Why `protocol/` takes no contexts

Everything in `protocol/` is a function from stated inputs to a stated
answer. `verify` takes a manifest, a signature and a proof and returns a
`Verified` or a typed refusal; it reads no clock and asks no network.

That is not asceticism. It is what makes those functions the ones a
theorem can be written about, and what lets the same call be made from a
node, from a test, and from a slice importer without any of them setting
anything up first. A rule that reached for the time would be a rule
whose answer depends on when you ask it.

### Why `node/` takes contexts and not parameters

Three facts are true of every decision a node makes and are not
arguments to any of them: what time it is, who this node is, and whether
the upstream is reachable.

```verum
publish(authorities, cache, request, our_log, published_at)
publish(cache, request) using [Clock, NodeIdentity, Uplink]
```

The second is shorter, but that is not the reason. A date threaded by
hand is a date some path forgets, and the forgetting is invisible
because the type still checks — `0` is a perfectly good `Int`. A context
cannot be forgotten: a function that needs one says so, and will not
compile where none is provided.

Reachability shows what else it buys. Passing a `Link` value down is a
fact about the moment it was captured, presented as a fact about now.
As a context, exercising both states is a scoped `provide`:

```verum
provide Uplink = StatedLink { up: false } in {
    say(&"cached/offline", cache.lookup(&held));
};
```

The same lookup, a different world.

### Why the composition root is one file

`main.vr` is the only file that mentions `FrozenClock`, `ConfiguredNode`
or `StatedLink`. Everything under it runs against the contexts, so the
same rules execute under a frozen clock here and a system clock in
production with no line of them changing — and a test's frozen clock is
one `provide`, not a mock threaded through five call sites.

## Where to look for each part of the language

This programme is also the language's proving ground, so it is worth
saying where each thing it leans on actually lives. Nothing here is
decoration: every entry is load-bearing for the domain, and several of
them found defects in the language while being written.

| what | where | why the domain wants it |
|---|---|---|
| refinement types | `cache.len`, `query.clause_cost`, `version.Version` | invariants a node computes about ITSELF, so a violation is our bug and halting is right |
| theorems beside the rules | every `protocol/` module | a comment claiming a property stops being true silently; a theorem stops compiling |
| contexts (DI) | `node/ambient`, every `node/` module | what time it is, who this node is, whether the upstream is up — true of every decision, argument to none |
| scoped `provide … in { }` | `main.vr` | exercising both states of the world without a mock threaded through five call sites |
| `pure`, compiler-verified | all of `protocol/` | the layering is a fact the compiler holds, not a convention a reviewer notices — **checked by breaking it**, see below |
| structured concurrency | `node/slice` | all-or-nothing import becomes a CONSEQUENCE of the parent-outlives-child law, not a comment |
| `async` as an inherited fact | `node/slice` → `node/durable` → `main` | one function fans out and waits; every caller up the chain says so, because `.await` outside an async context is a refusal and not a silent block |
| protocols with associated types | `protocol/source` | two sources with different reference shapes, one rule over both |
| rank-2 transducers | `protocol/query`, `node/search` | one query definition, three consumers, no filter chain free to drift |
| meta parameters with refinements | `protocol/hash` | a digest width is part of the type, and SHA-1's width is not a type at all |
| the CBGR tier dial | `protocol/hash` | one place, with the proof and the measurement written beside it |
| `@derive`, and its absence | `protocol/revocation` vs `protocol/authority` | derive when the structure IS the meaning; write it out when comparing is a decision somebody must make |
| the `is` operator | `revocation.may_publish`, `revocation.installable` | a one-state question answered by a `Bool`, not by a match with arms that exist to say `false` |
| an explicit `proof { … }` | `revocation.a_standing_never_goes_back` | the case analysis is short enough to read, so it is written rather than left to `auto` |
| gradual verification | `revocation.apply_all` | the same property over a WALK is not provable today — the claim keeps its enforcement, at run time, stated in the signature |
| `select` over racing futures | `node/resolution.race_mirrors` | order and race are DIFFERENT questions — precedence must be preserved, mirrors must not be waited on; the two sit side by side rather than behind a flag |
| dynamic dispatch, where generics stop | `node/resolution` | a configured source list is HETEROGENEOUS by definition; `List<S>` holds one S, and the heterogeneity is the data, not a weak signature |
| affine resources | `node/publish`'s `PublishSlot` | one release, one log entry — a retry that republishes is the split-brain a transparency log exists to prevent, and the slot is consumed by being spent |
| architectural obligations | every module's `@arch_module` | the audit gates on them |

Two are deliberately ABSENT and say so where they would go: `&unsafe`
anywhere (`protocol/hash` states why), and disjunction in a query
(`protocol/query` states why).

A fifth is a claim `PublishSlot` deliberately does NOT make. Affinity
governs this node's own code path: it removes the double-publish a retry
loop or a restarted worker produces locally. It cannot reach a second
request arriving over the network, which is not one program using a
value twice but two programs asking the same question — so the
idempotent `AlreadyIdentical` answer stays, and says why.

A fourth is `&mut` on the revocation ledger. `apply_all` takes the
ledger by reference and RETURNS a new one, because a batch that is
refused half-way must leave nothing behind — and a function that mutates
in place cannot promise that without an undo log nobody would trust.

A third absence is worth naming because it was a temptation rather than
a design: `block_on` at the boundary where `import_slice` became async.
It exists in the standard library and is the right tool at an FFI edge,
but using it here would have let every caller keep a synchronous
signature while a fan-out ran underneath — and the all-or-nothing
guarantee `node/slice` claims would have become a comment again. The
chain says `async` all the way to `main` instead.

### The purity claim, checked rather than asserted

Every function in `protocol/` is `pure`, and the table above says the
layering is the compiler's fact rather than a convention. A claim like
that is worth exactly as much as the last time somebody tried to
falsify it, so: adding one `print` to `query.clause_cost` gives

```text
error<E503>: pure function `clause_cost` has side effects: IO
```

and removing it returns the project to zero errors. The check is
transitive — a `pure` function calling an impure one is refused the same
way — which is what makes it a LAYER rather than a per-function label.

Re-run it whenever the claim starts feeling like decoration. It costs
two edits and one `verum check`, and a demonstration nobody has tried to
break is a demonstration of nothing.

Three of the table's claims have been falsified this way. Each row is
one edit to the programme, the diagnostic it produced, and a revert:

| claim | the edit | what the compiler said |
|---|---|---|
| `pure`, compiler-verified | a `print` inside `query.clause_cost` | `error<E503>: pure function 'clause_cost' has side effects: IO` |
| meta parameters with refinements | `Narrow` re-typed to `Hash<20>` | `error<E506>: meta argument 1 of 'Hash' violates its refinement: '20' does not satisfy 'it == 32 \|\| it == 64'` |
| `async` as an inherited fact | `async` removed from `durable.restore` | `Cannot await non-future type: Ok(Int{it >= 0}) \| Err(ImportError)` |

The third one holds and is worth reading twice, because the diagnostic
is weaker than the guarantee. The programme IS refused — but the message
names the symptom (the awaited value is not a future, which follows) and
not the cause (the enclosing function stopped being `async`), and it
carries no error code, so a gate filtering on `error<E…>` scores it
zero. The guarantee is real; the way it is reported would send somebody
to the wrong line. Filed against the diagnostics debt rather than papered
over here.

## Choices that keep coming up

### A refusal is a value, an invariant is a refinement

The line is about WHO the fact belongs to.

A **refinement** states an invariant of a value this node computes about
itself, so a violation is this node's own bug and halting is right:

```verum
public fn len(&self) -> Int{it >= 0}
```

Anything arriving from a peer is checked by a function that RETURNS a
refusal instead. Asserting on a malformed message from an untrusted
party would let that party halt the node — a refinement in that position
is a denial of service with a helpful message.

### Every refusal names something actionable

There is no `VerificationFailed` anywhere. There is
`ProofFromWrongLog(Text)`, `TrustAnchorChanged(Text, Text)`,
`NotClosed(Text, Text)`, `VersionAlreadyPublished(Text)`. An operator on
a disconnected machine cannot ask anyone what happened, so the refusal
has to carry what they would have asked.

Where two parties matter, both are named: `TrustAnchorChanged` carries
what we trusted AND what answered, because the person resolving it needs
to see what changed.

### Two absences are never one

"I cannot see it" and "it does not exist" are different facts. `Answer`
has `UpstreamUnreachable` and `NotFound` and no third variant meaning
"absent, probably". A build system that conflates them either fails a
build that should have used the cache, or hides a typo as an outage.

The same distinction shows up in `SourceError`, and it is why
`ResolutionError` has NO unreachability variant: resolution asks who
answers for a name, which configuration alone decides. Whether they
answered is a different question, asked later.

### Guarantees are not flattened

A registry publishes into a log, so what it answers for is auditable. A
git remote has no log: content-addressed, therefore immutable and
attributable, but "everyone got the same answer" is not a claim it can
make. A common `fetch` returning `Verified` would be lying by
uniformity — so `Assurance` is a sum the caller matches on, not an
`auditable: Bool` that reads as a quality setting and gets inverted half
the time.

### Structure enforces order, comments do not

The slice import must verify everything before storing anything. Rather
than a comment asking the next reader to keep two loops apart, the
verifications are spawned and JOINED before the storing loop begins.
Structured concurrency says a parent does not finish before its
children; all-or-nothing says nothing is stored until everything is
verified. Making the second a consequence of the first means there is no
arrangement of the code in which a store runs while a verification is
outstanding.

### Scale is a design-time decision

The cache is a `Map` keyed by package name, not a list scanned linearly.
A registry holds millions of coordinates, and a linear scan is not a
smaller version of an index — it is a different asymptote, and one that
only shows up where it is expensive to change.

The consistency audit is deliberately the opposite: it compares ALL
PAIRS of heads rather than consecutive ones, because a node that serves
an old view, then a newer one, then the old one again passes a
consecutive check twice while the record as a whole is a fork. That is a
correctness requirement, and the note in the module says so, so nobody
"optimises" it back into a bug.

## What is stated and not yet proved

The three obligations the protocol spec §6 requires are written as
theorems next to the rules they describe, and all three are UNPROVED.
What stops them has moved once already, and the distinction is worth
keeping straight because the two states print almost identically.

They used to be UNSTATEABLE. A predicate's parameters and its own
declaration disagreed about what sort a record or a variant has, so the
claim never reached the solver — and a claim that cannot be put is not
a claim that failed. Writing this program is what surfaced that, and it
is fixed: `let` bindings, field reads, records, variants and `match`
over an enum are all inside the reach now, and every obligation here is
put to the solver.

What remains is genuine reach. Each of these predicates walks a LIST or
matches over a `Result`, and the prover unfolds neither, so it answers
with a counterexample it invented rather than a proof.

They stay in the source, saying so in place. An obligation nobody has
discharged is an audit finding, which is the honest record, and it
becomes a proof the day the reach covers it without anyone having to
remember to come back.

## Reading order

`protocol/authority.vr` first — it is the smallest complete rule and
sets the tone for the refusals. Then `protocol/evidence.vr`, which is
where "checked" stops being a claim a code path makes about itself and
becomes a value it either holds or does not. Then any of `node/`.
`main.vr` last: it is a list of scenes, each printing what it concluded,
so a rule that stops holding changes the output rather than going quiet.
