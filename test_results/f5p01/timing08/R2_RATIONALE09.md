# R2 revision09 and predecessor-regression recovery

STATUS=R2_REVISION09_QUALIFIED / F5 PARTIAL; no candidate or canonical approval.
Final qualification09 completed actual exit0,95 exact identities once, all ok,
complete OK, no skips, wall720.75s under1049, unchanged script inputs, no remaining
suite process observed. W remains839.0470000000205, minimum1049. Evidence:
qualification09.json/.log; owned launcherPID60828/sessionproc_a623e9b27fed.

R2 remains the selected remedy; no R1 tuning or performance optimization resumed.
Preserve R2_RATIONALE.md as the historical08 decision. Run08 completed its exact
95-test mock step exit0, unittest838.709s, wall839.0470000000205s under1009s.
Its slower complete observation must not be ignored: W=839.0470000000205;
1.25W=1048.8087500000256; minimum whole-second T=1049, below1500.
Extra maximum failure-detection latency149s relative to900. This is a measured
margin reconciliation, not another optimization trial or treating a timeout as W.
A new final qualification under1049s must precede the next full stream.

Canonical source changes relative to run07 remain exactly one timeout literal
for `acceptance runner regressions` (900->1049) and the matching harness control.
The original95-test source remains rawf6274eac8eb8ef3075597ed3d946df5a41f19fed14b0e616efe6038404288d2f.
No production, host Rust, B26, portable, system asset, build-profile, target or
linker bytes changed from run08. See scope_proof09.json. The collector/driver
pins these timing records, uses1049 for its mock step, exact95 verbose identities,
and a fresh unique F4-regression output. Historical250-pin freeze08 remains intact.

## Failed full stream08

OverallFAIL, actual driver1; source-before=source-after true; remainingQEMU empty.
Formatting/build/ELF/derivation/aliases/closure/harness/host/B26/F1/F2/F3/F4/F5 and
mock steps passed, but the mandatory F4 regression did NOT pass. Its historical
runner reached47/47 observed successful gates, then the real F2 validator refused
`F2 source freeze mismatch`. No48/48 or72/72 claim. Exact output is preserved in
../v08/report.json and ../v08/full_f4_regression.log and ../../f5r/r01/.

Root cause reproduced offline with the real F2 evidence validator:
- Accepted F4 runner's old source_snapshot records204 current inputs.
- Current real fixture extracts live canonical source_snapshot and records229.
- All204 shared pins match exactly; none dropped. Twenty-five task-local authority
  and direct helper inputs were missing from the historical collector.
- Real validate(report, old) refuses the exact mismatch; real validate(report,
  fixture_map) succeeds with10 returned pins. This is a compatibility diagnosis,
  not acceptance of stale evidence against changed sources. Raw details in
  f4_snapshot_diagnosis.json. No production validator was changed or bypassed.

## Bounded harness correction

The F5-owned run_f4_regression_06_01.py now preserves the authenticated accepted
runner blob verbatim, derives a separate execution copy changing only the SAME
mock gate900->1049 under R2, and binds its global source_snapshot to the actual
current canonical function used by guest fixtures. It first requires that the
historical inventory is a nonempty byte-identical subset of the live expanded
inventory. Exact equality remains enforced by every real validator and final
source re-enumeration. No source pin is omitted, relabeled or normalized.
The wrapper records original/derived/canonical hashes, both counts and every
added path. All72 predecessor gate identities and refusal semantics remain.
This is explicitly a narrowly adapted predecessor regression, not execution of
unaltered historical runner semantics and not canonical F5 acceptance.

Actual offline adapter controls pass2/2: complete live inventory and exact one-
timeout byte delta with identical gate AST identities; corrupt historical blob,
dropped and changed predecessor pins refused. Initial test authoring included an
incorrect guessed AST-call count71; actual count53 (dynamic loops emit more runtime
gates) made that assertion fail. That source-shape guess was removed in favor of
exact old/new AST multiset equality; the real final runtime72 multiset requirement
is unchanged. This was an offline test-authoring failure, not guest GREEN/RED.
No production correction or renewed design revision budget is claimed. Historical
correction constraints remain; no budget is reset by this recovery.

A new source/configuration freeze and complete independent candidate review must
cover this wrapper, its provenance, the expanded inventory, timeout, all failures
and new evidence. Completed hardware is rerun only because changed frozen harness
inputs produce a new exact source map that the mandatory real evidence validators
bind; it is not a new hardware investigation. No new full stream until qualification.
