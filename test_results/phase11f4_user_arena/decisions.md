# F4 decisions — design checkpoint

## D13 — Authorized F4-private serial correction continuation

The user explicitly authorized an F4-private terminal serial replacement in retained_owner.rs only. Recovery02 verified checkpoint01 (187 source/29 artifact pins) and both historical ELF hashes. Every one of the failed-attempt 30 forbidden functions and seven unresolved edges has a shortest path through shared serial::puts; individual chains are retained in correction_recovery_02.json. Original atomic-dispatch paths remain historical RED, not runtime-panic claims. Neither historical correction directory nor any review is relabeled or overwritten.

Keep the existing inline state store: AtomicU8::as_ptr exposes live interior storage without creating a non-atomic Rust reference/access. The asm store is one x86 atomic byte MOV, with default compiler read/write memory effects (no pure/nomem/readonly), preserving preceding owner writes before Terminal publication. x86 store ordering supplies the hardware Release ordering; Acquire observers remain unchanged. This argument includes compiler/atomic interaction, not byte nontearing alone. The admitted wrapper disables interrupts before entry, is single-vCPU and forbids IRQ/NMI owner reentry. No new concurrent observer or mixed-size access is introduced. This is an engineering justification pending independent candidate review, not approval.

Continuation approach1 (overall correction approach2): replace only the F4 shared puts call with a fixed 34-byte private emitter. PASS/FAIL bytes and f4_arena_terminal CLI/HLT marker are unchanged. serial.rs:28–38 establishes byte-wide COM1 THR0x3f8, LSR0x3fd, THRE0x20, at most100000 polls per byte and drop-on-timeout. The private asm preserves that protocol and bound (34 bytes), not an unbounded wait. Static typed arrays ensure readable provenance; asm advances only within the array or once to an undereferenced one-past pointer. It declares EAX/ECX/EDX plus pointer/count outputs and flag clobbers; nostack applies to the asm, not the emitted helper prologue. No DF dependency, calls, locking, formatting, allocation, Rust indexing or unchecked Rust arithmetic. Default memory effects retain ordering; no IO initialization/control changes.

Exact accepted-build audit correction_green_02: compiler/build exit0, driver0, ELF db361522ac20f8d46bd033958aac5747b1fe0e61aaad13350247e50b3f3ba892. Conservative closure GREEN:4 blocks/11 edges/0 forbidden/0 unresolved. Remaining blocks are terminal, marker, private emitter and trivial AtomicU8::as_ptr. State store emitted MOV byte immediate3; helper emitted finite direct loops and RET with preserved callee-saved registers. All seven former unresolved edges disappear with shared serial dependency removal. This permits a new freeze/revalidation, NOT acceptance. Shared serial/VGA and accepted F1/F2/F3 remain untouched. No build-profile/target/linker change made in this continuation.

## D01 — Preserve accepted baseline

Actual HEAD d81672c4b314f0388e10e4c8dc9466b35ea89ce7 on maintenance/phase10. F3/F2 source ancestry verified. All179 accepted F3 raw source/build pins match, not merely a documentation-HEAD inference. Canonical F3 acceptance hash recomputed as2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b; rows/totals70/70/70. These are inherited artifacts, NOT fresh F4 execution. Historical F1 final independent-readback gap remains disclosed.

## D02 — No production changes before independent review

Supported delegate_task interface provides separate contexts. One read-only reconnaissance context and one separate mandatory design reviewer are dispatched. Reconnaissance is not approval. Parent must read the complete stored verdict and independently compare every pin. No production source/test/harness edit or QEMU fixture has been made.

## D03 — Do not increase the twelve-frame ceiling

Accepted F1 policy has payload1,sentinel1,userstack1,transition4,emergency4,arena table1. F4 proposes two USER leaves by reusing the existing payload for code/embedded RO data and acquiring only the already-budgeted userstack/table. No independent RW-data page. Existing F3 GDT has no USER selector; F4 neither changes it nor claims F5 entry readiness.

## D04 — Failure semantics require explicit independent resolution

Accepted F1 v2_design.md:52 forbids releasing even unpublished acquisitions and retry. Current F4 request also asks for rollback of unpublished resources/capacity restoration. Revision01 explicitly distinguishes pure preflight refusal (unchanged ownership/capacity/map) from admitted acquisition failure (bounded terminal retention, no USER PDE publication, no capacity-restoration claim). It requests independent judgment rather than silently changing F1 or asserting both contradictory behaviors. If the requirement cannot be satisfied within accepted lifecycle, checkpoint DESIGN-STOP and seek a precise operator disposition; never self-waive.

## D05 — Architectural source and limits

Retained Intel SDM vol3 revision093 PDF raw SHA25677919be320f35da2782771ef2cb65a868cf68e62c8f8279f2ca61199cb70d1f8. New targeted extraction intel_paging_extract_01.txt (PDF114,117,119–122,146–148,150), raw SHA2569806b6a17d4df64f323acd4821592bd932874aaea5a7e73dd47906e07d14658a. This edition paging chapter5, not historical chapter4. It confirms non-PAE1024-entry structures, both-level U/S/RW, WP effects, lack of non-PAE NX, and SMEP/SMAP caveats. Raw CR0/CR3/CR4/CPUID still NOT freshly observed. No CPL3 run or F5 proof.

## D06 — Process safety classification

Managed process-list operation returned no tracked background jobs. Native psutil snapshot found no Cargo/rustc/QEMU. Hermes desktop/serve/gateway/dashboard, MCP services and Strata server are infrastructure, not evidence of conflicting writers. Existing Python kernel sessions are not presumed writers from cwd alone; do not kill. Parent launched no production writer; delegates instructed read-only except their own verdict file. Two read-separated source/protected-file snapshots had no drift. This is bounded observational safety, not proof of exclusive ownership. Do not unlink dist/.phase6_acceptance.lock.

## D07 — Toolchain and host execution boundary

Verified cargo1.101.0-nightly(f3865b2a4), rustc1.101.0-nightly(1d81eb4ad), host x86_64-pc-windows-msvc. CARGO_BUILD_TARGET/CARGO_HOME unset. No home-level cargo configuration found. Repository config selects target.json and build-std; no host Cargo test launched inside repository. Established recorder run_step.py schema inspected; its artifact directory is historical, so any F4 recorder must retain new evidence under F4 root. QEMU not on PATH is not unavailability: existing helper pins C:/Program Files/qemu/qemu-system-i386.exe; test that exact binary before any guest execution.

## D08 — Independent REJECT, scoped user disposition, revised design

Review01 REJECT2 rawabfa725eb85267ea32ec026a3a345c5dd2cd9aae0dc1cd5bd55d4811aa90678b is immutable. Parent read all827 lines and rehashed196 pins with no mismatch. B1 required operator disposition for failure policy; user selected exactly "Authorize bounded terminal retention; revise design and obtain fresh independent approval". Stored in operator_disposition_01.json. This supersedes only current F4 unpublished-allocation rollback/restoration, not F1 or any other gate. Original design rawb35761f661030178c88fa5f2a6c976b7ae7a529a9f1fa472474af8fbc86f4864 preserved revision_01_reviewed. Revision02 is substantive design correction1/2: SMAP0 admission/evidence, AC/SMEP+guarded CPUID7, successful stack read/write control, exact RO-store PF oracle, explicit volatile publication/release compiler fence, honest all-layout preseeded MIRROR B26 design. New independent review02 required; no implementation yet.

Fresh PREIMPLEMENTATION baseline tests are corroboration only: host366 passed/0 failed/2 exact inherited ignored; B26134/0/0, list and serial subprocesses exit0 each, exact list-vs-execution membership. No F4 test claimed or canonical acceptance launched.

## D09 — Reviewed design implemented only after meaningful hardware RED

Design review02 APPROVE0 and parent_design_readback_02.json bind the revised design and201 baseline review pins. Runtime RED runtime_red_01/report.json built successfully and actually observed PDE256=0 at CPL0; explicit required-P/U assertion failed, driver1. Its original evidence remains immutable. Production now adds only the finite arena and retained-owner extension plus linker KEEP; ordinary kernel_main does not invoke it. Ready-only hardware_ready_01 ran128/512 MiB with actual table/CPU readback and owned cleanup. MINIMAL_RING0_GREEN is not full F4 hardware verification, F5 isolation proof or acceptance.

## D10 — Preserve host fixture failures; fix storage, not kernel ceilings

Delegated test files arrived with raw hashes c96e897dc597676a2e4c4d3d082c83c487da704aa21149fc3a83b3eefdb26ba2 (12 host declarations) and95137b995d067b8438b10a94ed016fa8f56767c92627120f48c48e5df5fb4b18 (3 B26 controls). Parent checked raw hashes before formatting/registration as sibling paging modules; B26 module is feature-gated. Focused host green_01 compiled/executed12 but foreign/stale fixture overflowed its libtest stack:11 passed/1 failed, actual Cargo101. B26 green_01 compiled/executed3; all3 overflowed their fixture stacks, Cargo101. These are preserved genuine host fixture failures, not the required hardware RED or proof of a kernel fault.

Controlled RUST_MIN_STACK=8388608 diagnoses succeeded (exact foreign1/1, B263/3), without source changes. This is host-only diagnostic environment, not a reviewed kernel stack increase. Root cause is large by-value FrameAllocator/debug construction/move storage in new fixtures: target DWARF shows allocator311528 bytes; host representation can differ. Parent removed second allocator construction from the main libtest thread by constructing boxed foreign allocator on a helper thread, retaining real live foreign authority. Parent changed B26 installation to a mutable reference plus mem::swap into actual FRAME_ALLOC, avoiding a redundant by-value transfer. WATCH still covers all layouts under real owner/map/frame locks; mirror preseed/backing identity assertions remain intact. No detector exemptions, kernel source fixes or resource ceiling changes. Default-stack focused green_02 actual host12/12 and B263/3 passed exit0. This is one coherent fixture-storage correction class; full regression and independent candidate coverage still mandatory.

## D11 — Recorder membership bug is not runtime RED

First full-regression recorder attempt exited1 before Cargo because its design-name regex excluded digit3 in cr3. Original empty-output directory plus startup_failure.json preserve actual process/session/command/classification. Corrected only identity parser to accept digits; new unique host_matrix_02 is recorded through run_command.py. No test weakened or skipped. Require exact baseline+F4 listing and serial/parallel passed+ignored multisets, nonzero summaries, raw log hashes and before/after canonical source snapshot stability before claiming regression PASS. Canonical acceptance has not been launched.

## D12 — Full component regressions and bounded emitted observations

host_matrix_02/report.json actual PASS, recorder/process0, all six Cargo invocations0: host380 exact listed =378 passed+2 inherited ignored in both serial/parallel; B26149 exact listed/passed in both modes,0 failed/ignored. Counter comparison preserves every baseline identity and adds exactly12 shared tests plus3 B26-only controls. All six raw log hashes rechecked; canonical187 input snapshot was stable over this component run. Later authorized Python harness changes require downstream freeze/revalidation; this is not canonical acceptance.

Production cargo fmt -- --check, cargo build --locked and validate_elf.py each exited0 (commands/f4_production_{fmt,build,elf}_01.json). production_audit_02 binds ELF SHA256241ecb209f9a2687daa430d5ff0f0e2596937eb829f7d080fb868122cd0bb516, target DWARF and29 selected emitted F4 functions. Conservative owner-family type envelope485 bytes (OWNER mutex472 + STATE1 + const MANIFEST12); descriptor family272, each within reviewed4096 bound. MANIFEST is a const, not a guaranteed emitted static symbol. Original production_audit_01 FAIL/exit1 for that reader assumption is retained; corrected reader derives pair size2 from exact ELF DWARF and count6 from pinned Rust source. No resource limit or kernel change. Emitted push/sub/call observations are NOT a cumulative stack bound or measured runtime high-water; additional review remains mandatory.

