# Phase 11A.2 allocator-domain runtime payload pins — partial checkpoint

Status: **verified partial checkpoint**. The completed full driver
`run_20261018T011743_606410Z` finished with 59/59 gates PASS, and the
independent read-back `verify_mapping_pin_checkpoint.py` reported PASS with
exit 0 into `test_results/phase11a2_continuation/mapping_pin_closeout.json`.
This attests the allocator-domain runtime payload-pin prerequisite only — not
full B19, TSS, or CPL3.

## Implemented scope

- `FrameAllocator` has one allocator-wide runtime-payload pin bitmap. An
  ordinary or growth allocation cannot be freed while a runtime PTE owns its
  pin. Refusal preserves capacity/ownership and records an invalid free.
- A second PageMap in the same allocator cannot publish another runtime
  reference to that payload. This refusal occurs before missing-table allocation.
  Inherited supervisor identity aliases are borrowed, not runtime owners.
- Mutable map/unmap and unpublished cleanup bind to the allocator's nonzero
  domain. A monotonic checked atomic issuer never wraps/reuses a domain; a
  successful empty reset gets a fresh identity. Both init entry points refuse
  any live allocation before changing inventory, including malformed reservation
  requests. Production prepare propagates refusal after releasing the frame guard.
- Runtime unmap requires the matching allocator and consistent live/local/global
  pin state. It clears the PTE and invalidates the translation before clearing
  pins, and never frees the caller's payload. Boot-alias unmap cannot release a
  still-live runtime pin. All compiled host unmap callers were migrated.
- The previously accepted physical table-accessibility guard remains. This is
  still the single published kernel-map model, not safe inactive-map mutation.
- The new bitmap is 8,192 bytes of inline allocator metadata, not a 512 KiB
  generation ledger. Exact target ELF deltas and selected direct-function stack
  evidence are recorded separately after the completed driver.

## Test credibility repair

Four inherited subprocess isolation wrappers constructed `--exact` names from
`module_path!()` including the crate prefix. Libtest omits that prefix: the old
filter can select **zero tests and exit zero**. The wrappers now strip only that
prefix and require an explicit one-passed/zero-failed/zero-ignored child summary
as well as successful exit.

`mapping_pin_isolation_readback.json` corroborates all four actual child bodies:
each old filter selected zero, and each corrected filter ran one passing test.
The growth-conflict fixture no longer frees a mapped growth frame. Its host-only
helper unmaps/releases G before mapping separately allocated P at G, retaining
repeated failed-growth rollback and exact conflicting-translation checks.

Historical aggregates/reviews remain immutable. Their totals alone did not
establish execution of these isolated child bodies. Do not silently upgrade the
older checkpoint's evidence using this later repair.

## Verification and evidence

Canonical continuation: `test_results/phase11a2_continuation/`.

- Main host suite: **300 passed, 0 failed, 2 existing ignores**, both serial and
  eight-thread preliminary runs; the full driver repeats serial/default parallel.
- Independently rooted B26 suite: **67 passed**, serial and parallel.
- Acceptance harness contracts: **48 passed**. The exact eight pin identities
  are linked to actual Rust test declarations, not a repeated mock guess. Valid
  one-short/one-extra/duplicate/substituted output is rejected. Existing host/B26
  gates require the two domain tests and all four repaired isolation identities.
- Evidence utility contracts: **8 passed**; inherited focused contracts: **6**
  independently replayed by its reviewer. RUNNING and predecessor reports are
  not accepted as the new checkpoint; optimized Python is refused.
- The retained ownership blocker probe now has **2 passing, 1 failing** tests.
  The remaining intentional failure demonstrates stale numeric release.
- `remaining_structure_authority_probe.rs` compiles the production memory
  modules and retains **two intentional RED failures**: raw release of a live
  PageMap directory and a foreign directory admitted as another map's payload.
  These are unresolved prerequisites, not passing release tests or CPU proof.
- `mapping_pin_source_review.json`: primary source only; no source blocker in
  this bounded slice, not acceptance or full B19 approval.
- `mapping_pin_test_review.json`: original changes-required integration review,
  retained verbatim. Its real runner-to-Rust identity mismatch was reproduced.
- `mapping_pin_test_followup_review.json`: PIN-TEST-01/02/03 resolved for the
  required identities; no final guest-acceptance opinion.
- `mapping_pin_closeout_review.json`: evidence utility and host mutation contracts
  only; it observed RUNNING and expressly did not approve final acceptance.
- `verify_mapping_pin_checkpoint.py`: separate read-back utility; preserves all
  historical closeouts. It requires predecessor 58-gate multiset plus one pin
  gate, 141 matching source inputs, driver/log/path binding, actual host totals,
  guest matrices, focused provenance, ISO/kernel/archive equality and cleanup.

Full driver:
`test_results/phase11a2_registry/run_20261018T011743_606410Z/verification.json`

Invocation-owned acceptance:
`test_results/phase11a2_registry/run_20261018T011743_606410Z/acceptance/acceptance_20261018T011941Z_h0ei2f8t/acceptance.json`

The verification driver retains its historical registry filename/scope label;
it executes current frozen inputs, but its label is not a broader ownership claim.
Final **59/59**, source/artifact read-back and resource results are pending.

## Remaining blockers — do not advance to TSS/CPL3

1. Numeric allocation/free/map values are not nonduplicable generational leases.
   Stale release after reuse still succeeds; allocator-domain identity does not
   distinguish allocations within that domain.
2. Runtime payload pins are not allocator-wide page-structure role ownership.
   Foreign PageMap structures-as-payload and raw release of live structures remain
   possible. Complete active CPU/table lifetime pinning and safe teardown are open.
3. `release_unpublished_frames` remains call-once prepare-failure cleanup, not
   idempotent or generational teardown. Its new domain/payload guards do not solve
   stale same-domain cleanup after structure reuse.
4. Borrowed boot identity aliases are not runtime payload pins. No claim that
   every identity-mapped physical frame is nonfree, or that distinct allocators
   isolate overlapping physical inventories, is made.
5. Real recoverable exception entry/return and saved CPU-frame behavior remain
   unproven. Host mirrors and inherited ring-0 guest tests do not prove CPL3
   denial/recovery, USER address-space safety, SMP shootdown or reentrancy.

Full B19 remains incomplete. No TSS, CPL3, Phase 12, general ELF loader or
production syscall implementation was started. Keep the existing branch and
all unrelated modifications, historical/failed evidence, `d1/` and the B13
backup. The continuation is uncommitted; no push/tag/merge/history rewrite or
Proxmox deployment is authorized by this checkpoint.
