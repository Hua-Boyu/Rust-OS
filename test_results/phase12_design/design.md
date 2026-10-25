# Phase12 design01 — bounded scheduler foundations, not implementation

STATUS: DESIGN PROPOSAL; runtime/preemptive scheduler NOT implemented or authorized.
F5 prerequisite: ACCEPTED and locally committed at `d9cebe28eb5139b6b614b7000688857361e2afc4`.
Authoritative raw discovery: source_inventory.json. Proposed future symbols/paths/cases below do not exist yet and are not passed tests.

## 1. Actual roadmap and authority

The CURRENT WORKING README.md:299 and467–479 explicitly plans “Phase12 — Processes and Preemptive Multitasking”: process/thread structures, context save/restore, ready queue/round-robin, timer preemption, blocked/sleeping/terminated states, idle task, TSS stack updates, safe termination, isolated processes and repeated creation. However README is a protected unrelated MODIFIED file; this new phase assignment is absent from its committed HEAD version. README:463–465 also calls these planning targets subject to confirmation. Therefore this is a source-grounded scheduling-oriented proposal, NOT a claim that the whole roadmap is accepted policy or that Phase11 as a whole is complete. Confirm numbering/runtime scope with the maintainer before implementation. Leave README untouched and unstaged.

The protected UNTRACKED docs/ROSTI_INIT_ARCHITECTURE.md:531–568 is older contextual design, explicitly not implementation authority. Its “no assigned complete scheduler/init subphase” is not used to override the newer working README or the current user’s explicit design-only authorization. Committed docs/PHASE11_DESIGN.md:305–325 describes broader privilege/loader/lifecycle work; F5 proves only a curated terminal CPL3 slice. No automatic syscall/ELF/init progression follows.

## 2. Source-derived baseline

- src/main.rs:11–38 declares no task/scheduler module. The bounded definition search of69 src/**/*.rs files found no Task/Thread/Process/Scheduler type or schedule/context_switch/switch_context/yield_now function. This is a bounded source inventory, not a proof about all possible dynamically generated code. F3’s hardware double-fault task switch is not a runnable-task scheduler.
- Ordinary kernel execution is one boot/main loop, polling shell then HLT (src/main.rs:480–491). It retains sole FILESYSTEM/DESCRIPTORS mutable borrows across the loop (267–284). Spawning another VFS caller would invalidate this ownership argument.
- PIT nominal100Hz/divisor math and a relaxed wrapping AtomicU32 tick counter exist (src/timer.rs:7–47). IRQ0 increments only and acknowledges the master PIC (src/interrupt.rs:332–337); it does not select tasks. The handler’s compiler-specific InterruptStackFrame is opaque `_unimplemented:[u8;48]` (206–217), NOT a validated resumable register image.
- IDT load already executes STI (src/interrupt.rs:140–145), before timer::init in ordinary boot (main.rs:207–234). A future scheduler must remain unarmed until every context/queue/stack is published; early IRQs must still take the existing count+EOI path.
- SpinMutex only spins/releases an AtomicBool (src/utils/mutex.rs:35–46,63–66); no IRQ masking, owner or preempt-disable count. Preempting a holder then running a waiter can deadlock one CPU. Memory lock order is heap -> PAGE_MAP -> FRAME_ALLOC, and IRQs must not take these locks (src/memory/mod.rs:58–61).
- F2 ExceptionFrame is exactly68bytes, fatal-only, explicitly NOT a return ABI (src/exception_abi.rs:1–2,21–65). Neither this prefix nor the opaque compiler IRQ argument may be reused as a context-switch layout. Same-ring CPU frames do not magically contain an old SS/ESP tail.
- F3 owns fixed16KiB transition and emergency stacks with guards (src/memory/privileged.rs:7–12,105–106). normal_state fixes ESP0=TRANSITION_TOP/SS0=0x10; the installer is one-shot, refuses existing TR/retry, and full byte comparisons enforce its contract (src/gdt_tss.rs:163–201,231–307). This is not a per-thread TSS update API.
- F4 has one finite USER arena/shared CR3, retained frame leases and no teardown (src/memory/user_arena.rs:1–42; retained_owner.rs:1–34,60–80). A second isolated process is not an extra index in this arena. FrameLease address/id/domain authentication is not by itself running-task/CPU-stack lifetime authority (frame.rs:421–451).
- F5’s run is divergent, CLI and one-shot; it masks both PICs and IRETDs with flags2/IF0 (src/f5_runtime.rs:83–117,157–194). Its trusted bridge ends CLI/HLT (f5_bridge.s:201–206). Its219byte conditional static stack bound is not runtime high-water or a preemptible-task bound. Never turn this path into a resumable task or reset its latch/leases.
- target.json:14,21 uses -sse,-sse2,-mmx,+soft-float / softfloat. This constrains generated kernel code; it does not deny arbitrary user x87/SIMD instructions. src/cpu.rs queries vendor leaf0, not a scheduler extended-state admission profile.

## 3. Recommendation and explicit staging

**Smallest next implementation request: P12-A, a HOST-ONLY finite scheduling-policy model and adversarial tests, with NO production kernel module, assembly, interrupt, TSS, allocator or acceptance-runner changes.** No such code is written in this kickoff. This separates queue/lifetime policy from presently unproved switching/IRQ/lifetime machinery. It advances one foundation of the planned preemptive phase, not “Phase12 complete.”

Proposed stages, each separately authorized/reviewed:

| Stage | Narrow output | Must not infer |
|---|---|---|
| P12-A | Pure host finite policy model, exhaustive state/queue refusal and bound tests | No executed context switch, timer preemption, resource release or user process |
| P12-B | Dedicated one-shot Ring0 two-worker cooperative switch proof, shared kernel CR3, separate reviewed entry/owned-stack ABI | Not production scheduling, not preemptive, no Ring3/recovery |
| P12-C | Separately reviewed explicit IRQ save/restore + bounded reschedule/preempt-disable protocol for closed kernel probes | No compiler-frame casts or general VFS safety; no user isolation claim |
| Later | Blocking/sleeping, bounded retirement/reuse, per-task TSS/CPU lifetimes, isolated recoverable user contexts and repeated cleanup | Requires additional Phase11/runtime prerequisites and explicit authorization; not covered by F5 |

P12-B/C are design directions with blockers below, NOT implementation-ready authorizations. Do not fabricate a runtime scaffold just to satisfy a phase number.

## 4. Proposed P12-A model: identity, queue, lifetime

Initial proposed cap: two kernel-probe workers plus one separate idle identity (three logical contexts); fixed ready queue capacity two. This is a deliberately tiny reviewable model, not a performance or system limit. All transitions take exclusive model ownership; no callbacks, heap allocations, kernel references, raw context pointers, atomics or real interrupts inside the policy core. Proposed static metadata budget<=1024bytes is a future compile-time/test assertion, NOT a measured current layout.

Worker lifetime: UNUSED -> READY -> RUNNING -> READY on explicit yield; RUNNING -> RETIRED on explicit completion. No task-ID reuse, respawn, reclaim, wake/sleep, kill or forced stop in A. Retired slots stay consumed until model reset between independently fresh tests. Idle is never enqueued and always selected when no runnable worker exists. There is exactly one current context including idle, at most one running worker, and no duplicate queue identity.

Round-robin: yielding running worker is placed once at the tail; next eligible worker is removed from the head. Empty selection chooses idle. Unknown/out-of-range IDs, duplicate enqueue, invalid state transition, over-cap admission, retired reuse and any “resume F5/CPL3” request refuse without mutating policy state. An inhibited reschedule request only latches a pending decision; it cannot change current identity/queue. Proposed nested inhibit accounting must be checked for underflow/overflow, not wrap. All work is bounded by the three-slot/two-queue cap.

These are logical policy states only: RETIRED does NOT prove a frame was released, an IRQ frame detached or a CPU stopped referencing a stack. Real task identity/generation reuse remains a future anti-ABA protocol. Keep process/address-space/grant objects out of A: the full roadmap needs them later, but one finite kernel-probe model does not implement them.

## 5. Context switch and kernel-stack ownership obligations before B

A cooperative switch requires a NEW explicit reviewed call/return ABI: exact saved registers, stack/return-PC/flags, segment constraints, pre-call alignment, DF policy and bootstrap/retirement trampolines. Decide and test callee-saved vs caller-saved rules against actual linked instructions. Do not call arbitrary saved PCs, cast ExceptionFrame or opaque48byte IRQ storage, copy the old F5 frame as a task context, or return an asm stack change through an ordinary Rust ISR epilogue.

Each real runnable context must own distinct mapped supervisor stack backing and an unmapped guard; prove guard/stack addresses, owner identity, live CPU/saved-frame references and release authority. Never borrow the F3 transition/DF stacks as worker stacks, expand the F1 fixed manifest silently or release a currently executing/suspended/IRQ-referenced stack. B should retain all admitted probe stacks until terminal fixture halt; it does not claim general teardown. A separately reviewed CPU-stack ownership protocol and full budget are prerequisites even for B. Any needed new owner/domain/API is a design amendment, not permission to weaken existing release guards.

Conditional B sizing candidate only: two new16KiB worker stacks =32768physical bytes/eight4KiB frames; two guard pages add no physical backing and give40960virtual bytes. Page tables, context metadata, instrumentation and existing boot/F3 stacks are EXCLUDED from this subtotal. No virtual range is assigned and no memory is allocated here. Complete the map/allocator/CPU-retention inventory and emitted stack bound before admitting hardware. The existing boot stack is16KiB (boot.s:18–23); it is not an unlimited scheduler stack.

A hardware worker that finishes must reach a kernel-owned validated retirement trampoline, never fall off an arbitrary task entry or resume ordinary boot with retained mutable VFS aliases. Initial probes must not call filesystem/storage/heap/VGA/shared locks or expose arbitrary functions; source main.rs:267–284 remains single-owner.

## 6. Timer, IRQ and preemption obligations before C

Do NOT add schedule() to isr_timer_handler. Current IRQ ABI is opaque and its compiler epilogue is not a portable switched-stack return contract. Review a complete explicit saved CPU/GPR/segment/flags image and restore/IRET closure separately, including same-ring vs privilege transitions, nested IRQ/NMI/#DF, EOI exactly once and published scheduler readiness. All interrupts before ARMED must preserve existing counter+EOI behavior. ISR code stays allocation-free, nonblocking and free of FS/storage/mutex-backed VGA formatting.

Every runtime path capable of holding a shared guard/unique borrow needs an interrupt/preemption safety policy before arbitrary preemption; merely checking SpinMutex::is_locked races with acquisition/publication and does not transfer ownership. Do not hold scheduler ownership while allocating, invoking tasks or performing I/O. Preserve lock ordering and prove inhibit nesting overflow/underflow/failure paths. A pending request is not permission to switch while unsafe.

PIT qualification remains open: source comments say “mode1 (rate generator)” but control word0x36 has mode bits3. This arithmetic observation is NOT a hardware qualification or a timing-policy fix; pin an authoritative device/profile reference and verify the actual waveform/interrupt cadence before relying on preemption. U32 relaxed ticks wrap and are not a memory-publication barrier. Sleep/deadline wrap horizons, accounting and interrupt storms are deferred out of A; later timer work must specify them, not assume infinite monotonic ticks.

Extended x87/MMX/SSE state needs explicit eager-save/restore or supported denial/initialization policy before general user tasks. Soft-float flags alone are not CPU enforcement. Do not implement lazy #NM recovery through the fatal F2 path. SMP/APIC/per-CPU TSS and cross-CPU retirement are explicitly out of scope.

## 7. F1–F5 compatibility and recoverability boundary

| Existing contract | Preservation rule / missing capability |
|---|---|
| F1 one-shot retained ownership | Do not reset/retry/seal-bypass or reclaim active task stacks via stamped-address authority alone. A policy model creates zero real leases. |
| F2 mandatory68byte fatal ABI | Keep source/raw pin and fatal semantics. Design any returning IRQ ABI separately; CPU fault recovery is not a scheduler return. |
| F3 fixed GDT/TSS/guarded stacks | Keep current fixed ESP0/SS0/DF task gate/readbacks. Future per-task ESP0 switching changes assumptions and needs separately authorized design + real hardware proof, not relaxed validators. |
| F4 USER arena/shared CR3 | No per-process isolation, second arena, aliases, teardown or lease release is inferred. User scheduling needs separate address-space/CPU lifetime ownership. |
| F5 terminal CPL3 | IF0/PIC-masked CLI/HLT and fixed return policy remain untouched. Neither A nor the proposed kernel-only B/C requires recoverable user execution. Full isolated user multitasking DOES require a new reviewed recoverable user/IRQ/return and lifecycle design; F5 does not supply it. |

This kickoff does not mark broad Phase11 loader/syscall/recovery milestones complete. A future source-changing implementation must revalidate applicable inherited evidence; current F5 approval is exact frozen-history evidence, not approval for future code.

## 8. Proposed RED/GREEN and evidence plan — NOT EXECUTED

A host categories: empty/idle; deterministic FIFO round-robin; exactly-one-current; duplicate enqueue refusal; unknown/out-of-range IDs; retired/no-reuse; capacity exhaustion; invalid lifecycle edges; nested inhibit overflow/underflow; no switch while inhibited/pending drain; rejection of user/F5 resume requests; zero allocation/fixed work and nonmutating refusals. These are proposed categories, not installed test identities/counts. Establish exact identities only from actual future test declarations/--list, serial+parallel execution and negative controls.

Minimal later B hardware target: one closed two-worker yield/retirement sequence at each128/512MiB on pinned single-vCPU/qemu32, with two distinct owned guarded kernel stacks, worker-private GPR/flags/stack sentinels, exact alternating event order, independent counters, final idle/terminal state, source/default-ELF identity and actual process exits. Tests must observe actual CPU state/captures, not trust a serial “PASS.” Capture complete linked call/tail closure, entry/retirement origins, reserved memory ledger and owned QEMU cleanup. No general user payload, syscall, storage or production scheduling.

Planned logical RED must execute a valid real baseline fixture which records that the required stack/context change did not occur (or a deliberately incorrect save path loses a sentinel) and the real strict reader refuses it. Missing fixture/import/build/transport errors are environmental, not logical RED. No B fixture or command exists now: freeze/review its exact CLI/source/oracles BEFORE any future run. GREEN requires real switched stacks/register preservation/event progression and honest terminal cleanup on both RAM sizes. Never credit a synthetic host policy PASS as hardware switching.

Reader negative controls must reject zero/missing/duplicate/substituted cases, forged source/ELF, stale/reused task IDs, duplicate queue entries, wrong stack bounds/guard permissions, register loss, invalid return origin/flags, missing/incomplete captures, unexpected fault/relaunch/shell continuation and unfinished QEMU cleanup. Deliberate guard faults are terminal fault tests, not task recovery. C additionally requires real timer-driven switching/EOI/interrupt-frame restoration and withheld-preemption tests while locks/borrow regions are live; cooperative yielding cannot stand in for preemption evidence.

## 9. Future acceptance integration and resource admission

Current76 exact identities, authenticated F4 predecessor, source freeze, reviewers and canonical artifacts remain immutable. No gate, timeout or validator is edited now. Future authorized A declares host identities/observed counts and adversarial controls before an independently reviewed gate/contract extension. Only then decide actual additional gate names/counts; do not invent a “76+N PASS.” Maintain real F1–F5 readers, full host/B26 and relevant hardware preservation, ELF/ISO/raw source bindings, no zero-test PASS, one owned verification stream, independent candidate/final readback and actual runner exits. The approved1049second limit remains mock-only; growth does not authorize another timeout change.

A new runtime/ABI/TSS/failure-policy change needs explicit authorization, source freeze, hardware RED/GREEN and design review. Memory admission uses actual workload/current availability and owned-process cleanup, not a universal4GB threshold. No heavy run was started for this design under the observed host pressure. No runtime timing, context-switch cost, memory peak or stack high-water is measured/claimed here.

## 10. Implementation authorization boundary

Recommended next request, not enacted: authorize ONLY P12-A host-only finite policy model/tests under the existing host harness; confirm the proposed two-worker/idle/no-reuse cap and non-runtime scope. Inspect actual manifests/import conventions before selecting concrete new source files; add no crate, kernel module, asm, IRQ/TSS/allocator change or acceptance gate without separate authorization/review. Run exact new host RED/GREEN and inherited host contracts when authorized. Runtime B/C, recoverable CPL3, processes/syscalls/ELF/init, resource teardown, deployment/real hardware/Proxmox and push remain outside this kickoff.
