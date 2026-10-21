# ROSTI PHASE 11 — F3 GDT/TSS/PRIVILEGED STACKS — FINAL REPORT

STATUS: **F3 ACCEPTED** — canonical 70/70 acceptance exit 0, independent candidate review APPROVE/0 blockers, independent final canonical readback APPROVE/0 blockers.

## 1. Git identity and worktree

- Branch: `maintenance/phase10`. HEAD: `8428cce8f1a3bf2200d6bac10ed26f03cf9bed22` (unchanged; no F3 commit at this checkpoint).
- F2 source commit `e99d82f` verified ancestor of HEAD.
- Protected unrelated work preserved byte-for-byte: modified `README.md`, untracked `d1/`, `docs/ROSTI_INIT_ARCHITECTURE.md`, `scripts/b13_boot_fixture.py.backup`. Never staged or normalized.
- `dist/.phase6_acceptance.lock` never unlinked.
- F3 source/evidence is frozen by SHA-256 pins (`full_source_freeze_05.json`, 179 inputs), not by a git commit.

## 2. What F3 provides and does not provide

**Provides (Ring 0 only):** a static 5-entry GDT (null / kernel code 0x08 DPL0 / kernel data 0x10 DPL0 / normal TSS 0x18 / emergency TSS 0x20); two 104-byte TSS contexts (limit 103, iomap base 104 ⇒ no I/O bitmap); `lgdt → segment reload → ltr` ordering with TR CPU readback before publication; a retained-owner privileged/emergency stack transaction with unmapped guard pages; a #DF task gate (vector 8 → emergency TSS selector 0x20) with an independent emergency stack.

**Does NOT provide:** CPL3 execution, USER mappings, IOPL, arbitrary-recursion survival, corrupt-GDT/TSS/CR3 recovery, or general teardown. No CPL3 code ran and no USER mapping exists (`hardware_cpl3=false` everywhere).

## 3. Verified GDT/TSS/privileged-stack behavior (hardware, 18/18)

- GDT ready-state wire bytes: `0000000000000000 ffff00000099cf00 ffff00000093cf00 6700d896298b0000 6700409729890000`; normal TSS busy 0x8b, emergency TSS available 0x89 before task switch (busy after).
- GDTR base 0x002996b0 (2725552), limit 0x27 (39); normal TR selector 0x18 base 0x002996d8 limit 0x67; emergency TSS base 0x00299740 limit 0x67.
- Transition guard 0x07c00000 unmapped, usable 0x07c01000..0x07c05000; emergency guard 0x07c05000 unmapped, usable 0x07c06000..0x07c0a000.
- Normal TSS ESP0 0x07c05000 / SS0 0x10; emergency TSS ESP0 0x07c0a000 / SS0 0x10.

## 4. Static stack bound (conditional)

- Bound **2,578 bytes** vs **16,384-byte** emergency stack → **13,806 bytes** headroom.
- Expression `2*(C + 103) + 4` with emitted conservative upper bound `C = 1,184`.
- **Conditional, one-nested-NMI case only.** NOT a measured runtime high-water mark; NOT proof of arbitrary-recursion survival or corrupt-stack recovery. `runtime_highwater=NOT_MEASURED`.
- Evidence: `stack_bound_parent_rerun_02.json`, `stack_bound_review_01.json` (BLOCKED, historical), `stack_bound_review_02.json` (PASS), `stack_bound_audit_02.py`. 80 input pins, 15 jump-table targets, 3 atomic tables resolved (`unresolved_indirect_edges=[]`).

## 5. Test totals (all freshly verified on the frozen revision05)

- Host: **368 listed / 366 passed / 2 inherited ignored** (serial = parallel, exact membership).
- B26: **134 passed / 0 failed / 0 ignored** (serial = parallel, exact membership).
- Production build / fmt / ELF: exit 0.
- F1 preservation: **10/10**; F2 preservation: **8/8**.
- F2 exception ABI host identity family: 7/7. F1 retained-owner host identity family: 9/9.
- F3 minimal Ring0 host identity family: 7/7 (5 `privileged::tests` + 2 `privileged_owner_tests`).
- F3 hardware: **18/18** (10 minimal + 8 supplemental), `FULL_RING0_GREEN`, `full_f3_acceptance=true`, `planned_only=[]`, `hardware_cpl3=false`, 1,056 byte pins.

## 6. Canonical acceptance (70 gates) — COMPLETED PASS

- Command: `python -B scripts/phase6_verify.py --output-dir C:/Users/iamsv/Documents/Rust-OS/test_results/f3acc`.
- Result: `test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json`.
- **overall=PASS; 70/70 gates; actual exit 0.** Gate multiset equals `f3_acceptance_contract_01.json` `expected_gate_multiset` exactly (70 unique gates, all counts 1).
- Source frozen at `full_source_freeze_05.json` (179 pins) — matches acceptance `source_sha256` exactly.
- Versioned ISO `dist/rosti_phase11a_prerequisite_20261021T173237Z.iso`, sha256 `bea601a5b6e29cc685d9f3b457d07eacffa1bcbfbafc9568661c05f503e8f3f6`, 11,558,912 bytes; kernel sha256 `ce0de173849002b888ea44da939d125615fcc3609dffd8397852d58266800d69`.
- acceptance.json sha256 `2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b`.

## 7. Correction history (three real F3 defects, fixed F3-scope)

The canonical acceptance surfaced three genuine F3 blockers; each was fixed within the previously approved F3 architecture. The accepted F1/F2 contracts (gate code and required-identity sets) were **never modified**.

1. **F1 filter pollution.** F3 placed its two owner tests at `memory::paging::retained_owner::privileged_tests`, so the frozen F1 gate's `--lib retained_owner` filter over-caught them (11 observed vs 9 required). Fix: relocated the tests to `memory::paging::privileged_owner_tests` (sibling module in `paging.rs`) with minimal `pub(super)` exposure of retained-owner internals (compile-time visibility only; no codegen/runtime change); updated the F3 gate's two required identities in `scripts/phase6_verify.py`.
2. **Mock-harness stale prefix.** `scripts/test_acceptance_harness.py` `declared_f3_names` hardcoded the old prefix. Fix: updated to `memory::paging::privileged_owner_tests::`.
3. **Harness timeout.** The F3 harness (80 tests ≈ 500 s) exceeded the `acceptance runner regressions` gate's 180 s default. Fix: raised that one gate's timeout to 900 s (a performance accommodation — the 80 checks are unchanged, not a weakening).

Additionally, two acceptance attempts hit a **Windows MAX_PATH** environment failure (the F3 fixture build's `link.exe` LNK1104 at 261–268-char paths, over the 260-char limit). This was an environment/infrastructure issue, not a source defect (the identical kernel compiled in the shallower pipeline dir). Fixed by running the acceptance with a short output dir (`test_results/f3acc`, F3 fixture path 244 chars). All three failed attempts (`canonical_acceptance_01/02/03`, `acc4`) are preserved as evidence.

Frozen source delta vs freeze_02 (5 files): `scripts/phase6_verify.py`, `src/memory/retained_owner.rs`, `src/memory/paging.rs`, `src/memory/privileged_owner_tests.rs`, `scripts/test_acceptance_harness.py`.

## 8. Reviews

- **Design review** (`reviews/design_review_01.json`): APPROVE/zero blockers (design-only).
- **Candidate review 01** (`reviews/candidate_review_01.json`): retained **REJECT/2 blockers**, byte-identical, sha256 `d9f1f8b88d06a36a0d1c982a4531067cbb52406c32147338576986b74250ab01`. Both blockers resolved: (1) full_f3_acceptance=false → now true with 18/18; (2) unproven kernel-livelock root cause → withdrawn in §10.
- **Supplemental observer review** (`reviews/supplemental_observer_review_01.json`): APPROVE for supplemental evidence only.
- **Candidate review 05** (`reviews/candidate_review_05.json`): **APPROVE/zero blockers**, full-file sha256 `50501d79c4421a3698c9f8620a9867f70e5edf5eee3adcfbed118fc1cce0c777`; 11/11 criteria PASS; independently re-verified by the parent (179-pin recompute + input-pin spot-check).
- **Final canonical readback 01** (`reviews/final_canonical_readback_01.json`): **APPROVE/zero blockers**, full-file sha256 `a22a2e437caafaa701bfaba0072066ec0fd75a7074241e37acacf958d14f3cb2`; 11/11 checks PASS; independently re-verified by the parent.

## 9. F2 ABI preservation

68-byte mandatory exception-entry prefix unchanged (`src/exception_abi.rs` FRAME_SIZE=68, VECTOR_OFFSET=48, `.if` hard errors in `src/exception_entry.s`); F2 freeze pins byte-identical. No CPL3 transition added.

## 10. Supplemental #SS/NMI scope and withdrawn claims

Supplemental Ring-0 #SS/NMI containment is limited to actually observed QEMU cases (QEMU 10.2 commit 0f12d445bd qemu32 emulation), not physical Intel/AMD proof, not mid-task-switch NMI. The earlier "genuine kernel RED / task-gate livelock" causal claims were **withdrawn**; the observed supplemental HARNESS_FAIL timeouts were a harness breakpoint after a non-returning fatal call, corrected without kernel changes.

## 11. Remaining limitations (disclosed)

- Static stack bound is conditional (one-nested-NMI), not a runtime high-water mark.
- QEMU qemu32 emulation only; no physical-CPU NMI-flag proof.
- Historical F1 final-readback gap remains missing (never fabricated).
- No CPL3/USER/IOPL proof (F4/F5 are future, unauthorized here).
- `candidate_review_01`'s decimal/hex equivalence note is not relied on (0x9629b000 ≠ 2725552; 2725552 = 0x002996b0).

## 12. Evidence locations

- Freeze: `test_results/phase11f3_gdt_tss/full_source_freeze_05.json`.
- Pipeline: `test_results/phase11f3_gdt_tss/revision05_pipeline.json`.
- Refresh: `test_results/phase11f3_gdt_tss/full_refresh_summary_05.json`.
- Hardware readback: `test_results/phase11f3_gdt_tss/full_hardware_readback_05.json`.
- Canonical acceptance: `test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json`.
- Reviews: `test_results/phase11f3_gdt_tss/reviews/{candidate_review_01,design_review_01,supplemental_observer_review_01,candidate_review_02,candidate_review_03,candidate_review_05,final_canonical_readback_01}.json`.
- Manifest: `test_results/phase11f3_gdt_tss/evidence_manifest.json`.

## 13. Next boundary

F4 (USER arena) requires fresh authorization. Not started here. No push, merge, tag, rebase, history rewrite, or deployment.
