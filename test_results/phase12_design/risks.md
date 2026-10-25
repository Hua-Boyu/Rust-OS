# Phase12 risk ledger01

All entries are design observations, not newly reproduced runtime failures. P12-A is only a proposed host policy model; runtime blockers do not imply accepted F5 is defective. Sources and exact hashes: source_inventory.json.

| ID | Risk and source | Impact / blocked stage | Required disposition |
|---|---|---|---|
| R01 | Phase12 roadmap assignment exists only in protected MODIFIED README:467–479, absent committed HEAD | Scope/numbering not accepted policy | Maintainer confirmation before implementation; preserve README/untracked init design untouched |
| R02 | IRQ frame `_unimplemented:[u8;48]`, interrupt.rs:206–217 | BLOCK C: not resumable ABI | Explicit independently reviewed saved-context/restore/IRET contract, emitted proof and actual CPU captures; never cast F2 prefix |
| R03 | SpinMutex has no preempt/IRQ inhibit, mutex.rs:35–46 | BLOCK arbitrary preemption: lock-holder/waiter deadlock | Audit all guards/unique borrows and design bounded preempt-disable/interrupt policy; no is_locked shortcut |
| R04 | IDT load STI before scheduler/PIT initialization, interrupt.rs:140–145/main.rs:207–234 | BLOCK C boot publication | Unarmed counter+EOI fast path until all queue/stack/context publication prerequisites hold |
| R05 | No runnable-task stack/CPU-retirement authority found; FrameLease ledger != CPU ownership | BLOCK B/runtime cleanup | Separate reviewed owner/domain/manifest with active/suspended/IRQ-frame pins; retain initial probe stacks until terminal halt; never free a live stack |
| R06 | F3 normal_state fixed ESP0/SS0, one-shot install and104byte comparisons | BLOCK per-task user transitions | New authorized TSS/context policy and hardware tests, preserve original F3 profile and DF mechanism; do not weaken validators or reuse emergency stack |
| R07 | F4 single arena/shared CR3/no teardown and F1 global seal | BLOCK isolated processes/repeated user launch | New address-space/CPU lifetime and release model; no global-owner reset or arbitrary second mapping |
| R08 | F5 PIC masks/IF0/CLI-HLT and conditional219byte bound | BLOCK “resume existing F5 task” | Preserve exact terminal profile; separate recoverable user/IRQ design. Preemptible stacks require new proofs;219 is not high-water |
| R09 | kernel_main retains exclusive FS/descriptor borrows; main.rs:267–284 | BLOCK concurrent shell/VFS/device tasks | Initial kernel probes cannot access these owners; separately review serialized service/access design before sharing |
| R10 | PIT comment vs0x36 mode bits, timer.rs:1,29 | BLOCK timing-dependent C assumptions, not A | Authoritative device/profile qualification and real cadence/EOI checks; no timer implementation change in this design |
| R11 | relaxed AtomicU32 tick wrap and coarse100Hz | BLOCK sleeping/deadline/CPU-time claims | Explicit bounded wrap-safe horizon/publication protocol and measured timing; A does not implement clocks/sleep |
| R12 | target soft-float does not constrain arbitrary user FP; cpu.rs vendor-only | BLOCK general user contexts | Eager FP-state lifecycle or reviewed enforcement/profile; no lazy recovery through fatal F2 |
| R13 | task ID reuse/forced-stop/reclaim not specified by F5 | BLOCK repeated creation/general termination | A uses no-reuse finite slots. Later anti-ABA generation exhaustion, stopped-frame ownership and acknowledged reclaim proof |
| R14 | opaque compiler IRQ prologue, stack alignment/DF, nested NMI/#DF | BLOCK B/C ABI publication | Separate emitted closure/stack bounds and independent architecture review; unexpected exceptions remain fatal, not rescheduled |
| R15 | stack subtotal32KiB physical/40KiB virtual excludes metadata/tables | BLOCK B admission until complete budget | Inventory actual resources/guards/ownership before allocating; no fixed address assigned, no measured usage claimed |
| R16 | host free memory later~665–705MB | Heavy verification admission risk | No new heavy job in this design; bounded read-only discovery only. Re-measure/release owned allocations before future workload; no foreign kills/cache/service/pagefile changes |
| R17 | broad Phase11 runtime/lifecycle remains deferred despite F5 accepted | Scope inflation into userspace/init | Explicitly keep host policy/kernel probes separate from recoverable user execution/syscalls/ELF/init; accepted F5 is bounded terminal proof only |
| R18 | existing76gate identity/1049mock-only timing | Acceptance drift | No runner changes now; separately reviewed future identity contract and real readers, no count fabrication or deadline broadening |
| R19 | single-vCPU/PIC/IF assumptions | BLOCK SMP/APIC generalization | No AP bringup, per-CPU migration or cross-CPU reclamation; separate future architecture |

Open design choices for maintainer: confirm A cap and no-reuse policy; decide whether runtime B is a useful independent one-shot prerequisite; choose/approve exact ABI and CPU-stack lifetime approach before B; qualify PIT/profile and preemption/lock policy before C. None is permission to start code now.
