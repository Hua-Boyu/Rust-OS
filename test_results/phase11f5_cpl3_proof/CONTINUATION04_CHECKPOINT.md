# F5 continuation04 checkpoint — review-only scope complete

STATUS=PARTIAL — F5 IS NOT ACCEPTED

This is not FINAL_REPORT.md or an acceptance closeout. Existing F5 implementation is preserved uncommitted. No source/harness edit, byte restoration, build, QEMU, candidate review, canonical acceptance or commit occurred in this continuation.

## Initial and final Git/provenance

Repository/CWD: `C:/Users/iamsv/Documents/Rust-OS`.
Branch: `maintenance/phase10`.
Initial and final HEAD: `c8b73654dd5f7f64c3c7872254b2b730ad2151f4`.
`git merge-base --is-ancestor c1b28b2 HEAD`: exit0.
`git diff --check`: exit0, newline warnings preserved without normalization.
Index: no staged paths. Dirty source and unrelated work remain preserved; no reset, stash, rebase or broad staging.
Actual status/commands/exits are in `continuation04_source_stability_01.json`.

Accepted F4 canonical report remains explicit PASS72/72, all rows PASS/exit0, raw SHA256 `3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4`. This is verified historical provenance, not a fresh regression.

## Independent failure-policy conformance — resolved

`reviews/failure_policy_conformance_01.json`
SHA256 `efc9c0c77c344bb50c8abc2fcda7826833808692178c2af179ef765a7e14bf97`.
Verdict APPROVE, zero correction-scope blockers, all9 mandatory areas, classification **A_IMPLEMENTS_EXISTING_POLICY**.
Parent `failure_policy_conformance_01_readback.json` verifies all23 reviewed raw hashes/sizes and complete review scope.

The existing const-true F5 installer adapter returns a detected post-publication discrepancy only to the nonreturning F5 wrapper, which claims the latch, records FAIL, publishes terminal STATE and invokes bounded kernel-owned UART/halt. Inherited const-false F3/F4 installer behavior remains source-equivalent to accepted source. No failure-policy amendment, retry, rollback, resource expansion or new exemption was approved. Nested latch refusal and inherited #DF retain their explicit design exclusions; incomplete record/state/output cannot count as success.

This is source-level conformance only, not an emitted closure or complete candidate review.

## Newly authorized entry-design amendment — design review complete

Investigation found that design03's literal source-shared macro requirement was not met: current F2 and F5 files separately define matching normalizer bodies. Equal source algorithms or matching emitted instructions do not retroactively meet that structural requirement.

The user explicitly selected **“Authorize the scoped amendment review only”** in clarification; exact question/response is retained in `entry_design_amendment_inputs_01.json`. Production/harness mutation, source restoration and implementation resumption were not granted by that selection.

Proposal: `entry_design_amendment_01.md`
SHA256 `9071c193419cd08f225f663bfeadebf10cefcd5b344ce2f2fae1b30a563c69c2`.
Independent review: `reviews/entry_design_amendment_review_01.json`
SHA256 `4ceb888d1bdbaa72c84b11fec654f9bce2aea0c6883ff9b32f371487941a3ec7`.
Verdict **APPROVE, zero amendment blockers, all14 areas**.
Parent `entry_design_amendment_review_01_readback.json` verifies all24 reviewed raw hashes/sizes and complete scope.

The approved alternative is a **mechanically constrained separate expansion**, not literal shared source. It requires:

- Exact accepted F2 raw pin before parsing.
- Mandatory complete-file ordered lexical derivation through a closed identifier dictionary, preserving every instruction/directive/vector/ABI assertion/table entry.
- Rejection of unknown aliases, mutations, missing/duplicate paths, stale pins and optimized assert-dependent evidence.
- Separate exact linked proof of BOTH F5 terminal aliases, because their approved mapping to F2 is non-bijective.
- All prior emitted/unsafe/privilege/failure/resource/host/hardware/gate requirements unchanged.

The independent reviewer ran read-only in-memory derivation/mutation probes; these are design feasibility evidence, NOT an implemented validator or harness GREEN. The reviewer explicitly grants no implementation/source restoration/build/guest authority and no candidate approval.

## Remaining concrete raw-source blocker

`src/exception_entry.s` accepted raw SHA256:
`a43dd7a8bb0db3bce288237d89705b2be4ef95723fa28de78fb1e87708423c60`.
Current raw SHA256:
`e375278f78c458a6ebed3e4fd2256f45d6c1b5e50a6e09654ba730fb8fe887e6`.

Accepted F4 canonical, nested source freeze, design03 inputs and Git HEAD blob agree on the first hash. Live CRLF bytes differ from accepted LF bytes. In-memory newline diagnosis equals the accepted content but does not establish raw identity. No file was normalized, repinned or restored.

`raw_f2_preservation_check_04.json` records the exact absolute Python command/argv and CWD above. Actual child exit1, elapsed0.125s, explicit `RAW_F2_PRESERVATION=FAIL`, expected/actual full hashes. It is a real raw-baseline diagnostic, NOT F5 harness RED or a hardware failure.

Applying/restoring any source is outside the completed review-only step. Once explicitly authorized to resume implementation, restoration must use exact accepted bytes and a new raw freeze; no historical review pin may be replaced to hide the change.

## Recovered contracts, not fresh test results

- `harness_contract_01.json`: exact14 F5 host identities, full `memory::paging::f5_cpl3_owner_tests::` ancestry, four new gate names, all72 predecessor identities/hash, canonical ASCII scenario grammar, six fixture identities at128/512 MiB, timeouts and negative-control obligations.
- `identity_source_readback_04.json`: all14 source test declarations match the approved set. No actual binary --list or current host execution was performed here.
- `continuation04_source_before_01.json` and `continuation04_source_stability_01.json`: all196 independently enumerated current source/build paths have identical raw bytes before/after review work. This is a recovery snapshot, NOT a final candidate freeze. All187 accepted paths remain present plus9 F5 paths; exact delta is retained.
- Four required F5 scripts and their canonical integration remain unfinished. No legitimate harness RED/GREEN has been claimed. Expected76 is not an accepted gate result.
- Historical design REJECT01/02 and proposal01/02 raw hashes were reverified unchanged in `historical_reject_integrity_04.json`.

## LNK1104 and process disposition

No isolated reproduction or full F4 regression was attempted before clearing design/authority prerequisites. Historical failing linker operand in the fourth regression is261 characters, and the .rlib currently exists (1550208 bytes). This supports a path-length hypothesis; it does not establish a lock race, antivirus issue or precise cause. The failed gate remains failed/unresolved. See `lnk1104_historical_diagnosis_04.json` for exact log/path/hash.

Managed process listing was empty at recovery. Native observations found no Cargo/rustc/link/QEMU builder; known Hermes services are infrastructure and unattributed Python contexts remain UNKNOWN rather than invented writers. Both independent reviewers used read-only separate contexts and created only their verdict files. No foreign process was killed and `dist/.phase6_acceptance.lock` was never unlinked.

## Unverified requirements and next safe action

Still required: explicit authority to apply the approved amendment/resume implementation; exact F2 raw preservation; complete four-script harness and meaningful RED/GREEN; installed source-derivation/negative-control validator; exact76 gate contract; final full input freeze; actual focused/full host/B26 list/serial/parallel and ignored membership; production format/build/ELF/payload/full emitted closure; bounded isolated LNK1104/F4 resolution; fresh F1-F4 preservation and complete12-row F5 matrix; isolated timeout calibration; no-drift/artifact identity; complete independent candidate approval; one notification-driven canonical acceptance; independent final canonical readback; only then final report/handovers/scoped commits.

Next safe read-only command: `git status --short`.
CWD: `C:/Users/iamsv/Documents/Rust-OS`.
Do not restore or modify source under the review-only authorization. First obtain explicit implementation/resumption authority referencing the approved amendment and unchanged original acceptance scope.

No Phase12, push, deployment, real hardware, scheduler, syscalls, recovery, NX/W^X or arbitrary-program-containment claim. F1 historical final-readback gap and F3 conditional emergency-stack limitation remain disclosed. There is no F5 candidate APPROVE, canonical PASS or final-readback APPROVE.
