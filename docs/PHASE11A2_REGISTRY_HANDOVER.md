# Phase 11A.2 registry repair — partial continuation

## Current continuation: registry + reservation checkpoint committed, exception-ABI entry conventions implemented and tested

Initial tree recovered at `48e76dfa096397824bc11dee137ea6287c5068f2`.
Focused local commits: registry `4bfbe60a1d66152d9a8210d0bb37bd49ad082db9`;
reserved-frame admission + mandatory identity gate `8f02162d857ddcfae49d4f0b937474b5bd1392f6`
(current HEAD). Only scoped source/test files were committed; index-only staging
kept unrelated work out of both checkpoints.

Reserved/uncovered runtime mapping now requires actual current allocation
eligibility (`FrameAllocator::is_live_allocation`), not merely `!is_free`. Boot
identity mapping remains borrowed and unchanged. This is NOT nonduplicable caller
authority, a mapping pin or complete B19. Three standalone real-module probes
remain RED for free-while-mapped, cross-PageMap exclusive aliases and stale
numeric release.

Exception-entry conventions: `#AC(17)` now routes through the error-code
`CpuErrorFrame` shape (`exception_handler_with_error!` + IDT offset install in
`src/interrupt.rs`); the `CPU_ERROR_CODE_VECTORS` oracle set `{8,10,11,12,13,14,17}`
matches the Intel Vol. 2 table-12 contract and its comments were corrected. Four
ABI oracle tests pass; the mandatory `phase11_exception_abi` gate family was
added to acceptance (57→58 gates). Full acceptance `run_20261017T175909_983725Z`
completed **58/58 PASS, exit 0**, host 285/0/2, B26 52/0. This is still
`phase=11A-prerequisite`, `phase11_release_ready=false`. No TSS, no CPL3, no
user-mode execution occurred.

Current design: `docs/PHASE11A2_OWNERSHIP_PLAN.md`. Current A–K status, exact
verification/commit boundaries and next task: `docs/PHASE11_HANDOVER.md`.
Evidence: `test_results/phase11a2_continuation/`. The earlier sections below
are retained historical registry-repair evidence, not the current Git status.

## Historical registry repair — scope and repository preservation

Continued on `maintenance/phase10` at
`48e76dfa096397824bc11dee137ea6287c5068f2`; no isolation requirement was
identified. No branch, commit, push, reset, history rewrite or deployment was
performed for this repair. Existing exception ABI work and ownership tests were
preserved. Unrelated `d1/` and `scripts/b13_boot_fixture.py.backup` were not edited.

This is a registry/backing repair, **not complete B19 or Phase 11A acceptance**.
No TSS, guarded transition stack or CPL3 payload has been added.

## Reproduced defects and implementation

1. The old bitmap allocation occurred inside page-map construction under
   `FRAME_ALLOC`. The focused inherited B26 validation test returned exit 101:
   `ALLOCS` was 1 rather than 0. Other failures in the earlier acceptance log
   included mutex-poison fallout, not four independent allocator defects.
2. `prepare` now makes three fallible reserves before acquiring map/frame
   ownership: permanent pins, table vector and payload bitmap. Registry refusal
   returns the static diagnostic `payload registry backing allocation failed`
   before frame mutation. The validation allocation test explicitly changes its
   expected count from two to three; zero allocations/destruction under the
   frame guard and zero diagnostic fallback allocations remain mandatory.
3. The production builder `build_identity_map_with_backing_in_place` borrows
   all three backings, checks their shape/initial state before frame allocation,
   retains them on failure, resets released table slots and transfers backing
   only after successful construction. Convenience allocating adapters are
   `cfg(test)` only and explicitly require an unlocked context.
4. The registry is one bit per managed physical frame, avoiding the earlier
   linear payload-vector scan. Its scope is runtime mappings in one PageMap,
   not every boot identity alias or every address space.
5. An additional regression demonstrated that unmapping the boot identity
   alias of a runtime payload cleared the runtime registry bit. The focused
   test returned exit 101 at rejection of a second runtime alias. Runtime PTEs
   now carry software-available bit 9; only unmapping an entry carrying that
   marker clears its registry reference. The same focused test then passed.

## Commands and evidence

Both RED commands ran from `C:/Users/iamsv`:

- `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_b26/Cargo.toml --lib b26_validation_failure_returns_directory_and_table_frames_without_locked_drop -- --test-threads=1`
- `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml phase11a2_unmapping_boot_alias_preserves_live_runtime_payload_reference`

Both returned actual exit 101 with the specific assertion failures above.
Their terminal output is in session history; no synthetic RED log was created.

Reproducible sequential driver:

`python -B test_results/phase11a2_registry/verify_registry.py --full-acceptance`

Current run:
`test_results/phase11a2_registry/run_20261017T152028_345139Z/`.
Its `verification.json` records exact commands, working directories, timestamps,
exit statuses, logs and production kernel SHA-256. Earlier pre-bit-9 verification
is retained at the evidence root and must not be attributed to later source.

Verified on the bit-9 tree before canonical acceptance:

- kernel and host formatting exit 0;
- main host suite: **284 passed, 0 failed, 2 ignored**, default parallelism and
  serially;
- independent B26-root crate: **51 passed, 0 failed**, parallel and serially;
- production `cargo build` exit 0;
- focused paging exit 0 at 128/512 MiB;
- `nomodule` and `validmodule` boot-metadata/growth fixtures exit 0 on the
  ELF/GRUB x 128/512 MiB matrix (8 scenarios), including full fsstress and
  module-byte preservation checks.

Canonical full inherited acceptance is **PASS 56/56**, actual runner exit 0:
`run_20261017T152028_345139Z/acceptance/acceptance_20261017T152202Z_dinjvg9b/acceptance.json`.
This is `phase=11A-prerequisite`, with `phase11_release_ready=false`, not a full
Phase 11A/CPL3 acceptance result.

Read-only closeout command, exit 0:

`python -B test_results/phase11a2_registry/verify_closeout.py C:/Users/iamsv/Documents/Rust-OS/test_results/phase11a2_registry/run_20261017T152028_345139Z/acceptance/acceptance_20261017T152202Z_dinjvg9b/acceptance.json`

`run_20261017T152028_345139Z/closeout.json` verifies 139 independently rediscovered
source/build input hashes, the identical inherited 56-gate multiset, 159 nested
reports, 280 true cleanup assertions, the 56-scenario initramfs matrix, exact
ISO-extracted kernel/archive contents, unchanged rollback media and no remaining
QEMU processes. These cleanup assertions are not 280 distinct guests.

Prerequisite ISO: `dist/rosti_phase11a_prerequisite_20261017T152202Z.iso`.
SHA-256: `010170a958175859db8c70a21d8f04b9234c0c81205966c59aaddd29d5a390a9`.
Kernel SHA-256: `f2bd30c5afba4401c915a806c962f110cd25845d9d2ae2246cfa2c004b0174e5`.

Scoped independent static review:
`test_results/phase11a2_registry/independent_registry_review.json`.
No new repair-blocking production defect found; all eight reviewed byte hashes
match the final tree. Full ownership, TSS and CPL3 approval are explicitly false.
One nonblocking verification gap is deferred: allocator instrumentation observes
FRAME_ALLOC but not PAGE_MAP-only ownership and does not cover every backing
destruction layout. Present ordering is supported by direct code inspection;
broader lock-observation tests belong in the next RED/GREEN slice, not changes
to frozen inputs during this accepted run.

## Explicit remaining gates

- Reserved/unowned physical frames can still enter raw runtime mappings.
  Distinguish borrowed permanent supervisor aliases from newly owned payloads;
  do not bypass the predecessor tests with a blanket reserved-frame rule.
- Raw allocator `free` remains a caller-precondition API; this PageMap-local
  registry does not prevent release/reallocation while a mapping remains live,
  does not pin CPU/table references and does not prove cross-PageMap authority.
- The inherited boot identity mappings intentionally remain separate from
  runtime payload ownership. A registry bit is not a nonduplicable frame token.
- Exception ABI changes are present and compile; this repair does not establish
  recoverable #GP, user-fault continuation, TSS or CPL3 isolation.
- No final milestone commit or release-ready claim is appropriate until the
  outstanding ownership/CPU gates and independently reviewed evidence pass.

Next bounded implementation must use RED tests for reserved-frame authority,
free-while-mapped and cross-owner release, followed by an allocator-integrated
ledger or nonduplicable ownership API. Do not move on to USER publication merely
because inherited supervisor-mode acceptance passes.
