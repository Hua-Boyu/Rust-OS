# F5 continuation04 — recovery and conformance prerequisite

STATUS=PARTIAL. This is a recovery record, not candidate acceptance or final closeout.

## Verified recovery

- Repository `C:/Users/iamsv/Documents/Rust-OS`, branch `maintenance/phase10`, HEAD `c8b73654dd5f7f64c3c7872254b2b730ad2151f4`.
- `git merge-base --is-ancestor c1b28b2 HEAD` exited 0. `git diff --check` exited 0 (newline warnings retained; no normalization performed).
- Accepted F4 canonical report is still raw SHA-256 `3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4`, explicit PASS, 72 gate rows, every row PASS/exit0. This is historical acceptance, not fresh F5 execution.
- Current canonical source inventory has 196 paths: all 187 accepted paths plus nine F5 paths. Seven inherited paths have different raw hashes, including `src/exception_entry.s`. See `f4_to_current_source_delta_04.json`.
- Current source inventory matched its recovery snapshot after read-only investigation. This is NOT the final candidate freeze: unfinished harness inputs and transitive task-local helpers remain unintegrated.
- Native process observations found no Cargo/rustc/link/QEMU builder. Hermes gateway/dashboard/serve processes are infrastructure. Unattributed Python runners remain UNKNOWN, not established conflicting writers. No foreign process killed. No acceptance lock unlinked.

## First prerequisite: failure-policy correction

`src/gdt_tss.rs:234-307` now delegates inherited `install` to `install_policy::<false>` and new F5-only `install_f5` to `install_policy::<true>`. Only the true specialization returns false for an explicit post-publication validation discrepancy. `src/f5_runtime.rs:112-117` catches this and diverges through `f5_unsupported`, latch claim, fixed FAIL record/reporter, terminal STATE publication and bounded UART/halt.

The parent's read-only reconstruction of the false specialization equals the accepted installer source after removing precisely the new wrappers/branch. This is source diagnosis, not emitted or hardware proof. Inherited callers at `src/memory/retained_owner.rs:482,618` still call `install`; only F5 calls `install_f5`.

Independent conformance reviewer: `deleg_f5055100`, `sa-0-73368eb4`; dispatched read-only against `failure_policy_conformance_inputs_01.json`. Expected verdict path `reviews/failure_policy_conformance_01.json`. Dispatch is not approval. All nine required review areas and current hashes must be read back before proceeding. The inherited #DF emergency terminal and explicitly reviewed nested latch refusal must not be silently reinterpreted.

## Additional concrete entry-conformance issues

1. Accepted F4/design03 raw `src/exception_entry.s` pin is `a43dd7a8bb0db3bce288237d89705b2be4ef95723fa28de78fb1e87708423c60`. Current raw pin is `e375278f78c458a6ebed3e4fd2256f45d6c1b5e50a6e09654ba730fb8fe887e6`. The accepted Git blob is LF; the current file is CRLF. An in-memory CRLF diagnostic equals the accepted blob, but raw identity is FALSE. No file bytes have been changed to hide this mismatch.
2. Design03 sections1 and6 and review03 checklist point10 require source-shared parameterized stub/common normalizers. Current `src/f5_exception_entry.s` contains separate F5 macro/normalizer bodies. Read-only symbol substitution demonstrates matching source instruction algorithms, NOT literal shared source, emitted equality, or permission to amend the design. This finding was sent to the independent reviewer for explicit disposition. Do not treat a failure-policy-only approval as approval of this separate structural difference.

## Harness contract recovered, not executed

`harness_contract_01.json` records exact approved 14 Rust identities, four new gate names, 72 predecessor identities/hash, six fixture identities at both RAM values, ASCII `--scenario` grammar, timeout constraints and negative-control obligations. The four owner identities have the complete prefix `memory::paging::f5_cpl3_owner_tests::`, as explicitly approved in design03 section8A.

Source declarations match exactly those 14 names (`identity_source_readback_04.json`). This is NOT actual libtest `--list` output or execution. The four new scripts are absent; the current runner has no F5 gate names. No valid harness RED/GREEN has been claimed.

## Not run or accepted this continuation

No Cargo build, host/B26 execution, QEMU, LNK1104 reproduction, final source freeze, full emitted audit, candidate review, canonical acceptance, final canonical readback, staging or commit. Earlier component successes and failures remain historical. Outstanding F4 47/48 and LNK1104 are not waived. No F5 acceptance claim; no Phase12, push, deployment or real hardware.

## Safe continuation

First receive the independent review and verify its complete scope, verdict and all raw pins. Resolve any entry-design contradiction explicitly before modifying source or integrating the harness. If an architectural amendment is necessary, preserve code/evidence and obtain required fresh authorization and independent amendment approval; do not silently call duplicate source a shared macro. CWD for all repository work: `C:/Users/iamsv/Documents/Rust-OS`.
