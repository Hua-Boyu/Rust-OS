# Phase 11A.3 — generation-safe frame leases

## Current checkpoint — canonical PASS63/63; independent final readback PASS

Live mutable resume state (current Git HEAD, blocker and next command):
`test_results/phase11a3_generation_ownership/STATE.md`.
Complete technical results/provenance: task-local `FINAL_REPORT.md` and
`evidence_manifest.json`. Those are task records, not a general CONTEXT framework.
Initial HEAD was `dde07882be6e7a96f29b9839e0b11029f7c81e26` on
`maintenance/phase10`. The scoped local checkpoint commit contains this handover;
resolve current HEAD from Git/STATE.md rather than a self-referential literal.
No push/merge/rebase/tag/deployment occurred.
Historical handovers remain intact. This is not full B19 or a Phase11 release.

## Implementation and approved design corrections

1. release_frame validates allocator domain/live nonzero identity, then invokes
   the complete alignment/managed/coverage/history/runtime-pin/structure-pin
   refusal chain. Matching generation never bypasses a pin.
2. Raw free and lease release share exactly one validation/accounting helper.
3. Successful raw release zeroes the ordinary allocation identity too.
4. Ordinary allocations cannot select growth-reserved frames; growth claims have
   identity zero and keep exact-address growth-only rollback. There is no growth
   lease or duplicate lease-accounting branch.
5. A u32 identity issuer starts at1, uses checked increment, issues MAX once and
   then retires permanently at zero. Init clears the ledger but not next_id;
   independent nonwrapping domains protect allocator/reset separation. Live
   inventory refuses both init entry points before mutation.
6. FrameLease fields remain private. frame_addr borrows for observation only.
   No Copy/Clone/Drop auto-release. Even a refused consuming release loses that
   submitted token; potential leaks are fail-closed, not permission to free pins.
7. Move-only runtime oracles duplicate only negative probes via cfg(test) helper
   or module-internal forgery; legitimate tokens remain for cleanup. Negative
   trait assertions prove neither Copy nor Clone during host compilation.

Production FRAME_ALLOC is private; main/shell copy optional frame_stats and never
format under the owner. Test-only crate-private owner access preserves B26 lock
instrumentation. Raw methods remain pub(crate), as independently reviewed: fresh
structure acquisition/rollback and revoked private unpublished inventories are
trusted internal authority; growth remains its own class. No currently enabled
production ordinary-payload release bypass was found. Full classifications:
`test_results/phase11a3_generation_ownership/caller_audit.md`.
HEAP -> PAGE_MAP -> FRAME_ALLOC remains unchanged; no new backing allocation,
callback, IRQ entry or heap destruction under prohibited owners.

## Verified evidence so far

- Exact original review copied byte-for-byte:7218 bytes, SHA256
  `40d46e6b66b0b9baeec035b20f6fe931b13b458cbbb8b3d397f3b98f6c81cd79`.
  Literal verdict APPROVE-WITH-CHANGES; design approval, not source acceptance.
- RED v1/v2: preserved wrong-CWD/std/test compilation failures, invalid ownership
  RED. V3: preserved valid missing-API compilation RED29 errors. V4: corrected
  move-only oracle against isolated exact predecessor frame.rs, Cargo101 with31
  missing-API errors, zero runtime tests. Live source was never rolled back.
- Focused ownership8/ledger6/boundary6 PASS, exact identities/nonzero counts.
- Full host325 passed/0 failed/2 existing ignores; full B26 98/0; each serial and
  parallel. Existing ownership, pins, structure cleanup and detector controls kept.
- Acceptance contracts: targeted RED3 tests/41 failed assertions or subtests,
  then full GREEN56 tests. Existing runner unchanged except three exact8/6/6
  family tuples; expected63 gates, not an inferred61. Runtime report is authority.
- Production build exit0; sequential local paging at128/512MiB passed, no source
  or build/QEMU overlap. Driver: task-local candidate_checks.json (PASS/exit0).
- Independent source review: BOUNDED_APPROVAL, blockers=[], security blockers=[],
  all11 reviewed raw hashes independently matched. Complete findings in
  independent_source_review.json (SHA256
  `18076b1a55df5db5877d90ffa103c900bb4868c1fb165de7befc9dd632dac02b`).
  Four nonblocking documentation/compile-fail/diagnostic suggestions remain
  deferred to preserve reviewed source bytes. No full-phase approval claimed.
- Canonical command completed via verified existing run_step.py with notification;
  actual wrapper/runner exit0, explicit PASS63/63. Exact report:
  `test_results/phase11a3_generation_ownership/acceptance/acceptance_20261018T103450Z_v2091tta/acceptance.json`,
  SHA256 `a1a5415e495800928a3dfa4c1867a763fce555b900bb81dec14dffa83dabc539`.
  Wrapper name generation_full_acceptance, actual runner command:
  `python -B scripts/phase6_verify.py --output-dir C:/Users/iamsv/Documents/Rust-OS/test_results/phase11a3_generation_ownership/acceptance`.
  No competing builds/guests or acceptance lock unlink occurred. Independent final
  readback PASS/actual exit0:145 matching inputs,159 nested reports,280 true
  cleanup assertions (not distinct guests), exact56-scenario/3379-check Phase10
  and44-scenario metadata matrices, production restoration/extracted ISO identity,
  unchanged archive/rollback media and no remaining QEMU. Readback SHA256
  `4e1a95112ead1a9524b41f61715f381de2c8294a2c425ffebe712cc7e3d811d4`;
  full output/execution records are task-local independent_final_readback.json /
  independent_final_execution.json. Offline reader contracts:15 passed with
  explicit bundled-venv Python.

Versioned ISO: `dist/rosti_phase11a_prerequisite_20261018T103450Z.iso`,11442176
bytes, SHA256 `9d1d92052dbc30464c6897810bcabffd0ad2ea4d788589168cdfc32a17b7074b`.
Extracted production kernel SHA256
`6d15c9ee180f705788af16377f77b67c91fc2de2e0d6c7ff90cca1430b234b0e`.
Trusted archive remains
`8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7`.
Source hashes are in the byte-scoped review and all145 final source entries;
never replace those pins after modifying source. Post-commit verification is
recorded separately in task-local post_commit_verification.json.

## Resource evidence

`resource_readback.json` compares exact predecessor production kernel
`8b43ae2ee1d20e40bd1754e031202a1d0085ae21de8bb6162edbea671c2ba9b9`
with candidate `6d15c9ee180f705788af16377f77b67c91fc2de2e0d6c7ff90cca1430b234b0e`.
Ledger262144 bytes; measured host FrameAllocator311560 bytes; target DWARF
FrameAllocator311528 bytes (all11 emitted type records agree), emitted target
FRAME_ALLOC owner311532 bytes including SpinMutex metadata. .data+262212,
.bss delta0, allocated/initialized sections+263580, ELF file+272568 bytes.
Static span2264076 (+266240) fits4194304-byte linker region at0x200000.
The ledger lives in the initialized static owner, not necessarily .bss.
Bootstrap stack remains16384 bytes; no runtime allocator-sized construction.
Selected largest direct ESP subtracts: prepare1304, init552, allocate_stamped88,
release_by_address112, issue_allocation_id36. No selected stack-probe references.
These are not cumulative caller/IRQ stack high-water; peak heap/stack remains
UNKNOWN. Minimum128MiB guest passes; host default test stacks suffice in serial
and parallel without stack-size override.

## Stop boundaries and next exact action

Actual notified canonical exit0/PASS63/63 and independent final readback PASS are
recorded. The local checkpoint contains only named reviewed source/docs/sanitized
records; post-commit source/hash and Git-state verification remain separately
attested. Live HEAD/next command: STATE.md. Begin a later bounded B19 ownership
design/RED slice only after recovering this checkpoint; numeric map capability
admission/shared/CPU lifetime remain open. No push or history rewrite.
Keep USER/TSS/CPL3/Phase12/ELF/syscalls/scheduler/general teardown out of scope.
No pve/VM103/persistent storage mutation. Preserve d1/, script backup, accepted
media and all failed/aborted evidence. Inherited UNVERIFIED backlog is indexed in
task-local backlog.md; it is not patched by this checkpoint.

## Operational notes

Clef Omni is unavailable: exact skill lookup failed and installed list has no
clef-omni. The Clef approval connector is unrelated, not an architecture reviewer.
No invented recommendation or model switch. Session metadata exposes gpt-6.1-sol;
context limit/automatic compaction UNKNOWN. Windows native Git Bash/MSYS with
host Cargo always run from C:/Users/iamsv; wrapper accepts name,cwd,expected,*argv
and writes log/JSON beside itself, refusing overwrite. Candidate driver copies
its records here without rewriting originals.

Oracle patch ambiguity was resolved by rewriting the small enclosing test file,
not retrying ambiguous hunks. A sibling-writer warning prompted a pause; user
confirmed the earlier model stopped and explicitly allowed overwrite/resume.
Identical recovery/snapshot raw frame hashes do not prove concurrent mutation;
earlier partial_snapshot and manifest fields are historical interrupted evidence.
Decisions and failed strategies remain in decisions.md / rabbit_holes.md.
