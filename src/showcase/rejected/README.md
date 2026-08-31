# Programs the compiler must REJECT

Every chapter of the showcase states, in prose, what the compiler
*refuses*. Those statements were measured once, by hand, and then guarded
by nothing — a chapter could stop rejecting and its comment would keep
claiming the guarantee. That already happened once to `versions.vr`,
which reported 4 proved / 2 failed for three weeks while its guide
asserted the opposite.

Each file here is one such claim, made executable. `check-showcase.sh`
compiles all of them and requires the named error code; a program that
starts compiling is a gate failure, not a curiosity.

These files are DELIBERATELY not valid. They are not mounted by
`main.vr` and must never be added to it.
