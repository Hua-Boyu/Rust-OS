# Phase12 — design kickoff01

PHASE:12/DESIGN
STATUS: DESIGN_PROPOSAL_READY — independent design review pending; NO implementation.
BRANCH: maintenance/phase10
F5_ACCEPTED_HEAD: d9cebe28eb5139b6b614b7000688857361e2afc4
F5_CLOSEOUT_RECEIPT: ../phase11f5_cpl3_proof/closeout_commit_receipt_10.json
ROADMAP_SCOPE: current protected MODIFIED README:299,467–479 proposes Processes/Preemptive Multitasking; absent committed HEAD; requires maintainer confirmation before implementation.
SOURCE_INVENTORY: source_inventory.json —30 selected raw-bound code/doc inputs,69 Rust files in bounded definition search; no scheduler type/function definitions found. Not an absolute proof about arbitrary dynamic/assembly behavior.
PROPOSAL: design.md — P12-A host-only finite policy model/tests is smallest recommended next authorization. Runtime B/C remain blocked pending their own ABI/stack/lifetime/preemption designs.
TASK_LIFETIME: proposed two workers+idle, no reuse/reclaim; logical retirement is not CPU resource release.
TIMER_IRQ: actual PIT/ticks+EOI only; early STI, opaque48byte IRQ frame, comment/control-word qualification and non-preempt-safe shared ownership are explicit risks.
F1_F5_COMPATIBILITY: keep68byte F2 fatal ABI, fixed F3 TSS/stacks, F4 finite arena/leases and F5 IF0/PIC-masked terminal behavior unchanged. No resumable user task claim.
HARDWARE_RED_GREEN: DESIGN SPECIFICATION ONLY; no Phase12 hardware, build, host tests or canonical run executed.
MEMORY_BOUNDS: proposed A metadata<=1024bytes/zero internal allocation; B stack subtotal32KiB physical/40KiB virtual excludes other costs; neither implemented nor measured/allocated.
DESIGN_REVIEW: PENDING separate reviewer and immutable review_inputs_01.json
SOURCE_CHANGES: NONE. Only files under test_results/phase12_design created after F5 accepted closeout.
PROTECTED_WORKTREE: README/.gitignore/F4 annotated report/root reviews/d1/init doc/backup preserved; F2 raw unchanged despite Git-presentation M.
CURRENT_BLOCKER: independent design assessment and future explicit implementation authorization; runtime blockers in risks.md.
NEXT_AUTHORIZATION_BOUNDARY: authorize only P12-A host-only policy model/test scope after confirming roadmap/cap/no-reuse semantics. No production scheduler, IRQ/asm/TSS/allocator change, new acceptance gate, syscall, loader, recovery, deployment, real hardware, Proxmox or push.
