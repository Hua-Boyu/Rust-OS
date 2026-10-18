# Phase 11A.2 — Structure-Role Authority for Page-Table Frames (bounded slice)

Status: verified partial checkpoint. Full acceptance `run_20261018T042214_125238Z`
completed with 59/59 gates PASS; independent read-back
`verify_structure_authority_checkpoint.py` into
`structure_authority_closeout.json` reported PASS, exit 0.

## What this slice adds

A second allocator-domain bitmap, `structure_pins`, marking frames installed as
paging structures (directory or table entries) by a PageMap of the current
domain. This is shadow metadata mirroring `pm.tables`; the set/clear discipline
at install and release sites is the invariant.

Authority rules now enforced:

- `free()` refuses structure-pinned frames (`invalid_frees` recorded).
- `map()` payload admission refuses structure-pinned frames.
- Pins are set only after installation, never at raw allocate sites, so the
  accessibility rollback frees in `map()` (before any pin) still succeed.
- `release_unpublished_frames` clears structure pins in the same call as its
  frees; the `build_identity_map_with_backing_in_place` exhaustion rollback
  clears pins before freeing tables and the directory.
- `init()` zeroes `structure_pins` exactly like `runtime_pins`, so
  preserve-or-reject stays consistent with the allocated-frames guard.
- The domain-reset test now asserts the structure bitmap is preserved
  non-mutating across both reset entries.

## Evidence

- The two deliberately RED role-authority probes in
  `remaining_structure_authority_probe.rs` turned GREEN (57/0/0 standalone
  probe run): `remaining_live_page_directory_release_must_be_refused` and
  `remaining_foreign_page_directory_as_payload_must_be_refused` now pass
  exactly on the intended authority.
- Host totals unchanged: 300/0/2 serial and parallel; B26 67/0/0 serial and
  parallel; production build pass.
- Full acceptance 59/59 with the predecessor gate multiset unchanged — this
  slice adds no acceptance gate; the authority is evidenced by the standalone
  probe binary plus unchanged host regressions.
- Read-back verified: 141 frozen inputs, ISO/kernel identity, 56-scenario
  matrix, 159 nested reports, 280 cleanup assertions, no QEMU remaining,
  focused boot reports bound to the harness invocation.
- Resource delta: static span +8,192 bytes = exactly the 8 KiB bitmap.

## Independent review

`structure_authority_design_review.json` (read-only design review): verdict
`proceed_with_required_ordering` with three encoded ordering requirements —
pin-at-install only, `release_unpublished_frames` clears pins with its frees,
`init()` zeroes the bitmap — all implemented as above. It confirmed no accepted
test regresses and the two RED probes turn green exactly on the intended
authority. It approved only this bounded slice.

## Still open (unchanged boundaries)

- The bitmap is allocator-wide, not per-map: multiple simultaneously live
  PageMaps are supported only while clearing stays per-map under the domain
  guard; no per-map accounting or leak detection if a PageMap is dropped
  without release.
- Stale numeric ABA release, general teardown, complete active CPU/table
  lifetime pinning, and page-table structure lifetime beyond installed
  entries remain unresolved.
- Full B19 not complete. TSS and CPL3 not started. Phase 12 untouched.
- Call-frame/stack high-water for the new bitmap accessors remains
  unverified on target.
