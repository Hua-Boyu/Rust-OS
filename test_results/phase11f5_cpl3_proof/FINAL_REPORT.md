# Phase 11 F5 — final closeout

STATUS: CANONICAL PASS76/76 + FINAL INDEPENDENT APPROVE/0/COMPLETE20. Source commit verified; final reports/evidence commit and acceptance-marker verification remain pending. Phase12 NOT STARTED.

## Repository and authority

Initial HEAD `c8b73654dd5f7f64c3c7872254b2b730ad2151f4`, branch `maintenance/phase10`; accepted F4 source `c1b28b2` is an ancestor (actual exit0). Final source and closeout commit identities are recorded in `closeout_commit_receipt_10.json`, produced after commit verification to avoid a self-referential commit hash. All protected unrelated initial dirty files remain byte-identical; `cleanup_recovery_10.json` classifies the actual worktree and `canonical_parent_readback_10.json` rechecks protected hashes. README, .gitignore, annotated F4 report, d1/, root reviews/, docs/ROSTI_INIT_ARCHITECTURE.md, backup and accepted ISOs are not staged. No reset/stash/push/merge/rebase/history rewrite/deployment/Proxmox mutation.

Approved Design03, failure-policy conformance and entry amendment remain separate authenticated authority. Their original verdicts and pins, historical Design01/02 REJECTs and candidate01 REJECT are preserved. Amendment permits complete-file lexical derivation instead of literal source-sharing; F2's accepted 68-byte prefix remains raw-byte pinned. F5-only GDT extension is authorized separately and does not repurpose accepted TSS slots. This session used post-design substantive correction cycle1 of maximum2; no scope/budget reset.

## F1 defect and correction

Historical candidate01 raw `61249755be254e804be5192bcb1bb535026602fd691ccf5aa60a5288392cd0e6` REJECT/one blocker/complete_scope=false remains immutable. Historical v09 matrix PASS lacked stage_removed, retained dist/phase11f1_guest_dj2v09oc, and real reader refused F1 aggregate state/preservation/cleanup. QEMU exits were never staging cleanup. Historical refusal/report/stage are unchanged.

The only new producer correction is scripts/f1_retained_guest.py (current raw `83f72d9d0d3fad6365fed1411e3376e86f0b81bb59e65bba8b8af57536f7796d`). scripts/f1_evidence.py remains unchanged `71a1e79caee9b437b04ee86ece31f319601453d39b1170f364eb79816d104d4c`. Bounded actual consumer closure is f1_dependency_inventory_10.json: no actual component/canonical consumer requires live disposable staging after completion. Original-stage command paths are provenance identities, not live dependencies. Reader also requires retained build_CASE/kernel.elf, fixture_RAM.elf and build.kernel_sha256; those exact bytes are now retained and checked outside staging.

OwnedStage binds current mkdtemp creation, PID, exact original path, expected dist root/prefix, device and inode. Before removal, canonical containment, unchanged identity, and no symlink/junction/reparse ancestor or descendant are mandatory. Arbitrary caller paths are never adopted. Exact ten matrix cases, actual child exits, source/default ELF preservation and retained build/fixture/report bytes must succeed before deletion. matrix_complete.json is durably written before cleanup; the exclusive-create save API writes the final report only once. Actual absence after removal is checked. Cleanup/matrix errors fail closed and preserve diagnostic stage; PASS omits contradictory stage_retained. No historical stage was deleted.

Meaningful logical RED: f1_cleanup_red_10.log ran the real workflow with only CPU/build transport mocked and failed the missing-cleanup assertion, not an import error. Initial save-authoring failure is separately preserved, not counted as kernel RED. Final15 cleanup controls (including real Windows junction and replaced-inode refusal),7 parent-reader controls and7 real-composition mutations PASS. Coverage rejects outside root, invalid prefix, unowned/replaced/reparse stage, removal failure/no-op, false/missing cleanup, matrix FAIL/relabel/unauthorized deletion, missing child/scenario and source/default ELF mismatch. Frozen v10 real producer→reader passed ten hardware cases and142 snapshots with actual stage absence.

Fresh canonical aggregate `test_results/f5acc/r01/acceptance_20261025T060216Z_7g_gea5o/f5_retained_prerequisite/f1_retained_1j60gf42/report.json` raw `34edd88fd277fcf4bf4b20063d49bfb9ab196efe47c424922bdcd298ffa945a6` passed the unchanged real F1 reader again in parent after runner exit. It has truthful stage_removed=true; phase11f1_guest_5817wu15 is absent, creator48068/device/inode creation record retained. Historical stage inventory:19 untouched directories, approximate logical size NOT_MEASURED (bounded directory inventory rather than unbounded recursion).

## Source freeze and full component verification

New full freeze10:262 enumerated raw inputs, raw `56d4e87dc235c52218e80d6a4f0c9d0380cf10d8f98e271d3b3f83c90917bb25`. Canonical collector independently enumerates234inputs; full freeze contains all of them plus reviewed timing/authority/predecessor dependencies. Actual full stream20steps exit0, source-before=source-after, no remaining owned QEMU. Frozen report test_results/f5p01/v10/report.json raw `dc7d0f4707c2c17e3f2bea4eff549907549d20f500c9a769aaa6f76fca669fec`. Parent readback invokes unchanged real F1/F2/F3/F4/F5 readers, hashes68882 retained artifacts and binds the exact production ELF. All262/234pins were rechecked after canonical completion. No production validator or shared canonical runner was edited for this correction.

Kernel/host formatting, production build, ELF contract, raw F2 pin, F2/F5 derivation, negative controls, entry/two terminal aliases, full emitted closure, harness controls, cleanup/readback controls/composition, serial+parallel+list host/B26, all guest matrices, complete95-test mock, fresh adapted predecessor72, artifact/source readback all actually ran. Host serial+parallel392passed/0failed/two inherited ignored, exact394list; B26serial+parallel149passed/0failed/0ignored and149list; exact14focused F5 tests. These are independently enumerated identities, not regex totals or zero-test success. Cargo host children use C:/Users/iamsv and absolute manifest, avoiding bare-metal parent config. Component summary and raw logs are in v10 and verification_readback_summary_10.json.

F1/F2/F3/F4/F5 hardware10/8/18/12/12 at128/512MiB passed with actual child completion and real readers. Production source F2 raw `a43dd7a8bb0db3bce288237d89705b2be4ef95723fa28de78fb1e87708423c60` is byte-identical to HEAD; no same-ring privilege-tail invention. F3 GDT/TSS/privileged stack and F4 USER-arena/retained-lease policy are preserved.

## Privilege, ownership and raw CPU evidence

F5 uses seven GDT entries/GDTR limit55; original slots0..4 including normal/emergency TSS descriptors are copied verbatim. No second LTR. User CS0x2b/SS0x33, normal TR0x18, kernel CS0x08/SS0x10 and TSS ESP0=0x07c05000/SS0=0x10. Entry IRETD flags0x2, IF/IOPL clear; actual pre-fault flags and saved RF are validated exactly. Raw saved flags0x10446 include RF for fault-class exceptions, not arbitrary masking. Saved ESP0x40400000, CS/SS selectors and CPL3 observations agree with CPU frames. Kernel-owned record magic0x46354350, scenario/success, permission/page-table/default-memory sentinels and raw stopped-guest captures corroborate the oracles.

F4 arena0x40000000..0x40400000 retains owned RO USER code/data, RW USER stack, absent holes/guards and12retainedframes, with effective PDE/PTE checks and PDE-last publication. No public ownership/free/unmap/retry/teardown path is added. Default F4 image remains unchanged. All terminal outcomes remain one-shot/nonresumable.

Twelve frozen raw cases below are corroborated by canonical's own fresh12-row matrix (not substituted for it). Full byte/hash detail in verified_matrix_summary_10.json and nested canonical reports.

| Scenario | MiB | Vector | Error | Saved EIP | CS/SS | Saved EFLAGS | CR2 | Result |
|---|---:|---:|---:|---|---|---|---|---|
| f5_cpl3_A_entry | 128 | 6 | 0 | 0x4000010c | 0x2b/0x33 | 0x10446 | 0x0 | PASS |
| f5_cpl3_A_entry | 512 | 6 | 0 | 0x4000010c | 0x2b/0x33 | 0x10446 | 0x0 | PASS |
| f5_cpl3_B_ro_write | 128 | 14 | 7 | 0x4000014c | 0x2b/0x33 | 0x10446 | 0x40000800 | PASS |
| f5_cpl3_B_ro_write | 512 | 14 | 7 | 0x4000014c | 0x2b/0x33 | 0x10446 | 0x40000800 | PASS |
| f5_cpl3_C_supervisor_read | 128 | 14 | 5 | 0x4000018c | 0x2b/0x33 | 0x10446 | 0x7c01000 | PASS |
| f5_cpl3_C_supervisor_read | 512 | 14 | 5 | 0x4000018c | 0x2b/0x33 | 0x10446 | 0x7c01000 | PASS |
| f5_cpl3_D_hlt | 128 | 13 | 0 | 0x400001cc | 0x2b/0x33 | 0x10446 | 0x0 | PASS |
| f5_cpl3_D_hlt | 512 | 13 | 0 | 0x400001cc | 0x2b/0x33 | 0x10446 | 0x0 | PASS |
| f5_cpl3_E_io_denied | 128 | 13 | 0 | 0x4000020c | 0x2b/0x33 | 0x10446 | 0x0 | PASS |
| f5_cpl3_E_io_denied | 512 | 13 | 0 | 0x4000020c | 0x2b/0x33 | 0x10446 | 0x0 | PASS |
| f5_cpl3_F_guard_read | 128 | 14 | 4 | 0x4000024c | 0x2b/0x33 | 0x10446 | 0x403fe000 | PASS |
| f5_cpl3_F_guard_read | 512 | 14 | 4 | 0x4000024c | 0x2b/0x33 | 0x10446 | 0x403fe000 | PASS |

## Emitted closure and bounds

Exact final linked production ELF `981f373a7a6530cbcc861261947b9aaa71f69661cb4e2a100b73901c4a1854e4`. Complete call/tail/conditional/fallthrough closure, both terminal aliases, literal bytes/asm effects, no forbidden lock/allocator/panic/VGA paths and no unsupported unresolved indirect edge were verified on this ELF, not source comments. F2 prefix and full entry derivation are separately checked. Concrete audited combined static path200bytes; conservative reviewed conditional first-entry104+additional one-nested115=219bytes remains within512. These are conditional static contributions, NOT runtime stack high-water or unlimited nesting. Preserve separate accepted F3 conditional emergency-stack proof (one-nested-NMI2578/16384); no broadened guarantee.

## Adapted predecessor and timing

Fresh adapted r03 actually PASS72/72/exit0 including first48inherited gates; original r02 remains historical. Acceptance raw4a5440fc52bee8b718b9878bfa8f840d6d6dfd444c1c5b7dc5818bba724f3e8c. Exact F5-owned entrypoint run_f4_regression_06_01.py and runner_provenance.json bind accepted runner5f7a8800aa387ad2c4bb406ebd5051621923b1267f3827060a839daf36687f4d and derived runnerd414a91799f7ef486c6ff3a5fcf529a6bf643772240857a1ffdc2f3063fc9e9a. The derived blob changes only approved mock900→1049; adapter preserves every204oldpin byte-identically and uses complete234livecollector for fixtures and reader equality. No undocumented wrapper/validator bypass. Fresh run justified by changed F1 dependency; unchanged historical review was not rerun for session continuity alone.

F3 short isolated build-output remedy remains authorized; LNK1104's historical261-character operand supports a path-length hypothesis, not retrospective causal proof. No compiler target/linker/profile/global timeout changed. R2 remains selected;95real tests/zero skips/no caching/pin_tree bypass. Historical full W839.047s establishes ceil(1.25W)=1049; preserved qualification720.75s and v09722.39s; v10suite810.776s/wall811.078s. Canonical's own full95-test gate exit0 (suite818.243s, no skips) under1049 is retained in gate30 raw log.1049 applies only to mock gate, not whole-run orchestration. No performance restart/sharding/profiling.

## Canonical76 and independent review

One genuine canonical launch under test_results/f5acc/r01 after comprehensive candidate02 APPROVE/zero blockers/complete scope and source/resource admission. Review raw1c3005b47e2cf455159bd44aedd2172822aef89fa7f41e894ac552dc313da420. Original review pinned mutable STATE context before a progress prepend; parent correctly refused that drift. Separate independent disposition raw632eef747ffeeeb44a528cd244fc00cee5ac139d6b7537cf2c470e1f767978f2 maps only historical STATE to exact immutable snapshot; original review/pin/refusal and both snapshots unchanged. It is NOT a substitute candidate review or source/authority waiver. Parent composed readback verifies every noncontext pin and actual production admission.

Managed sessionproc_3baf9028ef08/launcher13144 actually completed exit0/reasonexited; observed completion record canonical_completion_10.json. Explicit final PASS76/76, exact72inherited+fourF5multiset, allgateexit0, nonzero exact host execution, freshF1cleanup, full nested CPU matrices and packaged ISO evidence. Acceptance `test_results/f5acc/r01/acceptance_20261025T060216Z_7g_gea5o/acceptance.json` raw `21247dcb786d68afaf588971561858488f108d12414e89c6b1dfadb5d3a06074`. F4 predecessor acceptance binding3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4. Legacy phase11_release_ready=false remains truthful: F5 is a bounded milestone, not general userland release readiness.

ISO `dist\rosti_phase11a_prerequisite_20261025T060216Z.iso` raw `5a671de6494ee541dcbfda9bf57adcd4754c45b395d01c7b7d8767bcf82de6fb`, 11782144 bytes; packaged kernel digest equals exact production ELF. Independent final readback must inspect actual namespace/extract payload, not infer ISO identity from local ELF path. Parent post-exit real F1–F5 readers and all68013distinct canonical-returned raw artifact pins were rechecked with no drift (canonical_parent_readers_F2_F5_10.json, canonical_parent_artifact_readback_10.json). Parent independently inspected Rock Ridge and extracted exact kernel payload (canonical_parent_iso_readback_10.json). Final review verdict/hash/findings and postcommit receipt are appended only after actual completion.

## Resources and cleanup

The frozen full stream admitted4053094400bytes available but mid-predecessor available635236352bytes was severe pressure (resource_observation_10.json), not a safe-margin or peak claim. Initial severe570–810MB pressure later blocked canonical launch after owned jobs/recovery. No foreign/infrastructure process, browser, service, cache or pagefile was modified. User freed unused apps; fresh admission2151047168bytes available plus127052918784commitheadroom, configured512MiBguest and observed296730624interpreterreserve left1317445632bytes OS/wrapper/compile margin. Not a joint peak guarantee or fabricated4GiB threshold. Runner/background path intentionally has no whole-run deadline; per-gate deadlines unchanged. Notification/blocking waits were used, no competing build/QEMU/mock stream, no lock unlink. One foreground OS-wait transport exceeded420s; this did not host or kill the canonical background runner and is not a canonical timeout. Final native snapshot contains no cargo/rustc/link/QEMU; unrelated unknown hub and Hermes/Strata infrastructure remain untouched.

## Limits and Phase12 boundary

Historical F1 final-readback gap remains historical; today's fresh producer/readback is not retroactive review. All historical REJECTs/failures/raw artifacts are preserved. Non-PAE no NX means no hardware NX/W^X guarantee, no arbitrary malicious-userland isolation. No scheduler, syscalls, ELF loader, resumable/recoverable user execution, general teardown/capacity restoration, deployment or real-hardware claim. Bounded terminal retention and explicitly conditioned nested-fault proof only.

Phase12 design-only discovery activates only after actual independent final APPROVE, complete closeout and scoped local commits. Consult actual roadmap rather than assuming scheduler scope. F5 terminal CPL3 proof is not resumable task support. No Phase12 production implementation authorized.

## Exact predecessor invocation

Actual argv from the frozen stream:

```json
[
  "C:\\Users\\iamsv\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe",
  "-B",
  "C:\\Users\\iamsv\\Documents\\Rust-OS\\test_results\\phase11f5_cpl3_proof\\run_f4_regression_06_01.py",
  "--output-dir",
  "C:\\Users\\iamsv\\Documents\\Rust-OS\\test_results\\f5r\\r03"
]
```

CWD `C:\Users\iamsv\Documents\Rust-OS`; actual exit0; elapsed3720.4220000000205seconds; outer predecessor-only timeout14400seconds; log SHA256`19d1fb11a27fe48a9152a6d1a0971f39e847cb6a670f22b40cc596a10900bcb4`. Wrapper rawSHA256`e4571654a5c8fc3d266e1a92727c06b372c8bff81d456b6863de7990007125a6`. r03 provenance expands204→234inputs without dropping any predecessor pin. Full original/derived/canonical hashes and every added path are in runner_provenance.json. This is an adapted regression, not unmodified historical-runner execution.

## Exact host identity index

`test_results/f5p01/v10/host/report.json` rawSHA256`82303261e0e99e488dd802672152655fdaa20515216da61f6291e36b135ff5a4` retains all394host and149B26 identities for serial/parallel/list with actual command/CWD/exit/loghashes, plus all14focused F5 identities. The only ignored host names are `maintenance_measurements::measured_frame_scan_states` and `maintenance_measurements::measured_heap_capacity_loss`; B26 and focusedF5 ignore none. No zero-test success is accepted. The four new canonical gate identities are:

- Phase 11 F5 CPL3 host and fixture contracts
- Phase 11 F5 CPL3 exact ELF terminal closure
- Phase 11 F5 CPL3 one-shot hardware matrix
- Phase 11 F5 retained prerequisite hardware preservation

## Additional explicit proof limits

Stage cleanup is current-process tracked within a cooperative local namespace, not an atomic guarantee against a hostile actor concurrently replacing regular directories. Actual original-stage identity, full no-reparse traversal, safe stdlib deletion behavior and post-removal absence were established; no arbitrary caller path is adopted. QEMU qemu32/single-vCPU/IF0/admitted-profile captures and bounded terminal observations do not establish universal Intel/AMD or infinite-execution proof. Private UART finite100000polls-per-byte/drop-on-timeout is not a wall-clock guarantee. Unknown host Python/Node tasks were not classified as safe writers or terminated; empty final build/QEMU snapshot is a bounded observation distinct from each recorded owned exit.

## Completed independent final readback and source commit

Independent separate-context final readback01 APPROVE/zero blockers/complete20areas, rawSHA256`543db6fabab5eff983bf3711db56c0cb20d894cc50bb92bb2616f2a401e5ebe0`,57,503,970bytes. It directly observed managed canonical exit0, re-executed actual F1–F5 readers on both frozen and canonical streams, regenerated emitted audits and entry derivation, independently decoded actual F2/F5 frames and F3/F4 publication/emergency records, checked full394/149host membership and19canonical Rust families, hashed68882component artifacts and all73361canonical nested files, checked68013returned pins, exactISO payloads, officialB13host/CSV schemas, OS-lock release, resource/provenance/cleanup and protected bytes. Transport/serialization/log-section authoring failures are explicitly recorded and resolved; no production reader was changed. Parent final_review_parent_readback_10.json rechecks actual verdict/fullscope/20PASSareas, manifest19pins, freeze262/current234pins and original complete candidate02.

Actual source-final HEAD`14f40f194c574610cdceef41e972ff814f9e815a` (initial`c8b73654dd5f7f64c3c7872254b2b730ad2151f4`). Source commit exited0 and contains exactly55inspected source/test/harness paths; every committed Git blob equals its independently reviewed raw SHA256. Ordinary clean filters would alter three CRLF input blobs, so explicit raw hash-object/update-index staging preserved their bytes without changing attributes/config. Default non-CRLF staged whitespace check0; scoped cr-at-eol immutable-input check0. Initial ordinary git diff--check2 was authenticated CRLF presentation, not silently normalized. F2 source remains accepted/HEAD/working raw-identical while Git retains a presentation-only M; do not normalize or stage a fake ABI change. All seven protected unrelated path hashes remain unchanged. Reports/evidence are the next scoped commit; final accepted status is gated on real postcommit verification. The actual FINAL closeout HEAD and exact commit chain will be in closeout_commit_receipt_10.json, written after commits to avoid a self-referential Git hash.

Accepted F4 ISO`dist/rosti_phase11a_prerequisite_20261023T032857Z.iso` is still raw2ceb19010a4cb52c224600db755e666de87d3c67aea7db41575a1d3c324f7c84; the preserved immediately preceding ISO remains raweb97312fbcffde04d1cc5982ec2bb2a698fbc47a1c7181ef065edaec589c52ea. No ISO/raw VGA/build cache is committed. Large binary evidence stays local and is exactly indexed; sanitized reports/manifests/logs and required source baseline ELF are explicitly scoped.

Final-readback pressure later measured665792512availablebytes; owned completed parent allocations were safely released (postrelease705536000available, parentRSS127856640). No new heavy run is needed or admitted; only sequential bounded file/Git documentation work. This later pressure does not retroactively replace the real canonical admission or actual successful exit. No foreign task/cache/service/pagefile change occurred.

## Documentation-only authoring diagnostics before evidence commit

The new live STATE checkpoint initially mistyped three long artifact hashes; the pre-staging audit caught them and replaced them from the actual canonical completion record, final independent readback and independently extracted ISO payload. The exact uncommitted mistaken text is retained as STATE_authoring_transcription_snapshot_10.md, explicitly NOT proof authority. The actual canonical SHA is `21247dcb786d68afaf588971561858488f108d12414e89c6b1dfadb5d3a06074`, production ELF `981f373a7a6530cbcc861261947b9aaa71f69661cb4e2a100b73901c4a1854e4`, ISO `5a671de6494ee541dcbfda9bf57adcd4754c45b395d01c7b7d8767bcf82de6fb`. No frozen source, strict reader, approved review, canonical artifact or immutable reviewed context changed; no new substantive source correction or acceptance rerun occurred. Internal convenience-parser/schema errors (list-vs-mapping/elapsed-vs-wall/count-key/step-name) are retained in closeout_parent_authoring_diagnostics_10.json and were not treated as kernel REDs or successful verification. Exact mock suite time comes from the actual v10 log ('95', '810.776'), while actual driver process wall_seconds=811.0779999999795; predecessor parent wall_seconds=3720.4220000000205.

The uncommitted live-checkpoint mock-time transcription was also corrected: actual v10 suite810.776s, actual parent wall811.0779999999795s; canonical suite818.243s. The existing full report and immutable logs already recorded the correct values. This is document authoring, not a new source or timing-policy change.
