# Phase 11A.2 runtime table-access prerequisite — PARTIAL

## Current continuation

Resumed on `maintenance/phase10` from
`d55043d7511640d266084a6c6432d2401c8cbcc7`. Existing registry, reservation and
exception-entry checkpoints are preserved. No branch, reset, rebase, push,
deployment, TSS/CPL3, general ELF loader or syscall work was performed.
Unrelated `d1/`, `scripts/b13_boot_fixture.py.backup`, accepted ISOs and failed
evidence remain untouched. The new patch is uncommitted.

This document supersedes stale CURRENT/HEAD/next-task statements in the older
handovers. In particular, `8f02162` is the reservation checkpoint, not current
HEAD; `b82e9b1` is the exception-entry checkpoint and `d55043d` its documentation.
The vector oracle is the `exception_pushes_error_code` predicate, not a named
`CPU_ERROR_CODE_VECTORS` constant. Whole exception ABI/CPU continuation is unproven.

## Defect and bounded repair

`PageMap::map` allocated a missing runtime table then zeroed its physical address
as a virtual pointer without validating that alias. Removing or redirecting the
candidate's identity alias could fault or redirect writes; host MIRROR backing
concealed that hardware dependency.

Before zeroing or installing the table, runtime map now requires identity
translation and effective PRESENT/RW/supervisor permissions at both PDE and PTE.
If its first candidate fails, it returns that candidate to the ordinary allocator
and refuses the mapping. No scan for a later candidate is attempted: repeated
refusal despite other accessible capacity is an intentional conservative policy.
The caller's payload allocation/reference state remains unchanged. Counters and
capacity restore, but the allocator's historical `ever` bit may record the
allocate/free attempt; this is not a byte-identical allocator rollback.

No new storage field, lock, heap allocation or backing reservation was added.
The guard checks `self`, not live CR3. Its production accessibility argument
requires the existing sole published kernel-map path (`heap_grow_frame` under
heap -> PAGE_MAP -> FRAME_ALLOC); it does not support inactive/multiple active
address spaces, corrupted structure bookkeeping or arbitrary physical access.
Existing table/directory lifetime safety still depends on unresolved B19 roles.

## Tests and independent review

The removed-alias regression was observed RED (actual cargo exit101, failed
refusal assertion), then GREEN (exit0). It initially lived temporarily in the
ownership test module. The final separate `runtime_table_access_tests` module
contains five tests: removed alias, redirected alias, effective readonly at
either level, effective USER at both levels, and alias restoration/retry.
They check refusal before host zero_table, unchanged mapping/PDE/TLB/reference
state, capacity restoration and repeated candidate reacquisition. They do not
measure redirected physical payload bytes or CPU refusal/fault recovery.
The exact-eight ownership and four-test exception-ABI families are unchanged.

Evidence root: `test_results/phase11a2_continuation/`:
- `table_alias_absent_red.json/.log`, `table_alias_absent_green.json/.log`.
- `table_access_host_green.json/.log`: five current tests pass.
- `table_access_review.json`: independent bounded approval, no in-scope blocker;
  all eleven reviewed source hashes matched at parent read-back.
- `table_closeout_stale_red.json/.log`: old accepted tree rejected for source drift.
- `table_closeout_optimized_red.json/.log`: actual `python -O` refusal.

Review limitations include no direct new-guard test for absent parent/stale leaf,
no MMU payload-byte sentinel, and no heap_grow_frame-specific injection of this
new refusal. Existing effective-permission enumeration supports composition;
normal guest growth remains regression coverage, not CPU alias-refusal proof.
Older review artifacts were not edited or re-pinned for this continuation.

## Verification status

Sequential driver:
`python -B test_results/phase11a2_registry/verify_registry.py --full-acceptance`.
Invocation: `test_results/phase11a2_registry/run_20261017T235138_771737Z/`.
Host suites PASS: main290/0/2 ignored, B26-root57/0, serial and parallel.
Kernel/host formatting, production build, focused paging and eight ELF/GRUB
128/512 MiB boot-metadata/growth cases completed exit0.
Full acceptance completed **58/58 PASS, actual runner and driver exit0**. The
unchanged gate multiset and all140 source/build inputs were independently
rediscovered and hash-matched (new test module, changed paging.rs, no removals
relative to the previous accepted139-input tree). Acceptance remains
`11A-prerequisite`, `phase11_release_ready=false`.

Exact acceptance:
`test_results/phase11a2_registry/run_20261017T235138_771737Z/acceptance/acceptance_20261017T235315Z_1r1mkj6y/acceptance.json`.
Its SHA256 is
`c67b86dd37bfe5f1899b7187973bacb38e7eb90fd12ec743d4e3b0c080c37db2`;
completed driver SHA256 is
`da88aba6729ddd4d760795465f0985d06cd6b568b8c494b5c3eb5a44de587651`.

Read-back **PASS, exit0**:
`test_results/phase11a2_continuation/table_access_closeout.json`.
It checked the exact canonical invocation log/driver,140 frozen inputs, all58
gate identities,159 nested-report cardinality and280 true cleanup assertions,
56 initramfs scenarios/3379 checks, all9071 crash models and the eight focused
reports bound to source digest, full owned-stage image path, ELF/ISO flag,
scenario RAM argument and serial path. Cleanup counts are not independent
process-history identity completeness; the final live QEMU snapshot was empty.

Accepted ISO: `dist/rosti_phase11a_prerequisite_20261017T235315Z.iso`,11128832 bytes,
SHA256 `77a1e4f006a5a1c5af9d65b29d7edf772de13a057630045f61a6036a7fcd30d9`.
Extracted production kernel matches the final build, SHA256
`8375f04924ee4c64cd617c50f8a98f377fecabb60c62a7518e1a6ee81de163d6`.
The previous accepted ISO and its trusted archive remain unchanged.
ELF file6003216 bytes, allocated sections1967782 bytes, initialized830106 bytes,
static address span1977356 bytes; these are not runtime heap/stack high-water.
The proposed ownership ledger is not present in these measurements.

Read-back utility: `test_results/phase11a2_continuation/verify_table_access_checkpoint.py`.
It rejects stale and optimized evidence without modifying old closeout records.
Its initial reviews found focused-directory/source/boot identity gaps; preserved
RED/GREEN mutations cover the repairs. Six utility tests now pass.
`table_access_closeout_final_review.json` independently confirms F1-F4 resolved
within utility scope, not kernel/acceptance approval. The eleven kernel-review
source hashes and eighteen static utility-review pins matched on parent read-back;
the utility review's then-RUNNING driver hash remains historical, not re-pinned
to the later completed driver. All original review verdicts/pins are preserved.

## Next exact task and stop boundary

With this bounded acceptance/read-back complete, continue allocator-domain role/generation/lease
implementation from `docs/PHASE11A2_OWNERSHIP_PLAN.md` and the independent design
review. Mapped-free, cross-PageMap authority, stale numeric release, revocable
unpublished teardown and active CPU/heap/stack/table pins remain unresolved.
The proposed512KiB dense ledger is still design only, not allocated or approved
by this change. Preserve the three RED probes as blockers, not passed tests.
No USER/TSS/CPL3 or Phase12 until all ownership and real exception-ABI prerequisites
are implemented, tested and independently approved.
