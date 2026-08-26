# How this program is put together

This describes the arrangement that emerged and the reasons for it. It
is meant to be read as a worked example of structuring a Verum program,
not as a set of rules invented in advance.

## The layers, and what each is allowed to know

```
protocol/       the rules.        Pure. No contexts. No I/O.
  authority     who may answer for a name
  evidence      what a client checks before believing
  source        where bytes come from (a protocol + two implementations)

node/           the policy.       Uses contexts. Still no I/O.
  ambient       the contexts themselves, and backends for them
  cache         what a node keeps and what it says offline
  consistency   auditing a cache against the heads it has seen
  handshake     meeting an upstream, once per session
  publish       the write path
  slice         carrying a registry across an air gap

main.vr         the composition root.
                The ONLY place that names a concrete backend.
```

The direction of knowledge is one-way and worth stating positively:
`protocol/` does not know that nodes exist, `node/` does not know which
clock it runs against, and `main.vr` is the only file that knows both.

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
The prover currently discharges a goal only when the predicate is a
single expression over primitive parameters — reading a struct field
defeats it — which is a limit of its reach and not a doubt about the
properties.

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
