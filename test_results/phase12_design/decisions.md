# Phase12 design decisions01

D1 — Scope discovery: current protected working README:299,467–479 is scheduler/process/preemptive-oriented, but is an uncommitted proposed roadmap. Committed historical docs do not assign the same phase plan. Treat scope as a proposal requiring maintainer confirmation, not accepted numbering. Do not modify or commit protected README/init design.

D2 — Honor the completed prerequisite: F5 accepted at `d9cebe28eb5139b6b614b7000688857361e2afc4` after real canonical76/76 exit0, complete independent candidate/final approvals and verified source/evidence/marker commits. Raw evidence, protected worktree and limitations remain immutable. This kickoff begins only after that closeout; no claim that all broad Phase11 requirements are finished.

D3 — Recommend host-only P12-A policy/model tests as the smallest next implementation authorization. Two proposed kernel-probe workers plus idle, fixed queue, no heap/callbacks/real contexts, no reuse or physical reclamation. These are proposed logical bounds, not implementation or measured footprint. A is not a scheduler running on the CPU.

D4 — Reject immediate schedule() inside timer ISR. Real source has only tick+EOI, early STI, an opaque48byte frame and no preempt-safe SpinMutex or global unique-borrow sharing model. These are runtime design blockers; no accepted source is “fixed” in this design-only task.

D5 — Separate ABIs and ownership. Fatal68byte F2 remains unchanged; future cooperative/returning IRQ contexts need their own verified ABI. Do not generalize F3 fixed TSS, share/replace its emergency stack, grow/reset F1 seal policy or treat F4’s shared arena as per-process isolation. F5 remains divergent IF0/PIC-masked terminal CPL3.

D6 — Recoverable user execution is NOT needed by host-only A or the narrow future kernel-only probes. It IS required before the full roadmap’s isolated preemptible user processes, safe termination/reuse and user fault continuation; F5 does not provide it. Syscalls/ELF/init/SMP remain later separate designs and authorizations.

D7 — Hardware RED/GREEN is a future specification, not a result. Require actual pinned baseline observation showing no switch/lost preservation and strict-reader refusal, then real switched stacks/GPRs/flags/counters/retirement on128/512MiB. Missing code/import/transport cannot be logical RED. No fixture/CLI, gate count or passed test is invented today.

D8 — No current acceptance changes: preserve exact76, existing readers, all timeouts and mocks’1049 scope. Future source-changing stages require separate authorization, exact test membership/freeze and applicable inherited hardware plus independent review; do not reuse current F5 acceptance as approval of new code.

D9 — Independent design review: use a separate read-only reviewer bound to design/risks/decisions/source_inventory, an immutable STATE context snapshot, F5 receipt and actual raw source inputs. The live STATE can later report a verdict but must not substitute for the immutable reviewed context. Reviewer verdict is not implementation authorization.
