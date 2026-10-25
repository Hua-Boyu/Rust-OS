# F5 design preflight — DESIGN-STOP

Status: incomplete, not approved, no production implementation authorized by this document.

CURRENT SUPPLEMENT: The user subsequently authorized the narrow GDT extension and required reviews/revalidation; see authorization_01.md. The scope request below is historical and resolved. Full design remains incomplete. Independent prerequisite review confirmed the source mismatch; subsequent design-drafting delegation failed with provider HTTP429 daily token limit. No full-scope design approval exists. A proposed F5-only extended GDT must preserve original F3Context/TSS storage, existing TSS selectors and stack layouts, and retain inherited F3/F4 fixture behavior. This paragraph does not approve that proposal.

## Blocking prerequisite F5-GDT-01

The supplied baseline says F3 installed user descriptors. Actual accepted source does not:

- `src/gdt_tss.rs:15-16`: F3Context contains `entries: [u64; 5]`.
- `src/gdt_tss.rs:253-268`: installs null, kernel code, kernel data, normal TSS and emergency TSS; GDTR limit is 39.
- `src/gdt_tss.rs:213-222`: readback requires that exact limit and descriptor inventory.
- `src/memory/privileged.rs:5-6`: kernel descriptor bytes are `0x00cf_9900_0000_ffff` and `0x00cf_9300_0000_ffff` (access bytes 0x99/0x93, DPL0).
- `src/gdt.rs:156-158`: early GDT is only three entries, likewise no DPL3 descriptor.
- Read-only `git show fd4b49d:src/gdt_tss.rs` confirms the accepted F3 source has the same five-entry layout and limit. This is not a new worktree regression.

No valid accepted user CS/SS selectors can be specified. Selectors 0x2b/0x33 would address entries beyond the installed GDTR limit; assigning RPL3 to a DPL0 kernel code selector cannot permit an outer-privilege IRET. Repurposing a TSS slot would break the accepted F3 contract. Loading a replacement GDT or introducing an LDT would change protected descriptor configuration or add unreviewed architecture, not resolve the stated prerequisite within scope.

Fresh authorization is required for a narrowly scoped descriptor-table extension and corresponding F3 compatibility/revalidation review before completing F5 design. No such change has been made or assumed approved.

## Source-derived facts retained for a future authorized design

- Normal TSS: `src/gdt_tss.rs:163-167`, ESP0=TRANSITION_TOP, SS0=0x10; `src/memory/privileged.rs:8-9` defines transition range 0x07c01000..0x07c05000.
- Normal TR selector is 0x18 (`src/gdt_tss.rs:280-281`). TSS I/O-map offset is 104 and descriptor limit 103 (`src/memory/privileged.rs:77,82-86`). This is the source policy for denying CPL3 I/O; no F5 hardware observation exists.
- F2 assembly pushes normalized vector/error, PUSHAD, then four selector words. Its mandatory prefix remains 68 bytes: saved EIP at 56, CS at 60, EFLAGS at 64 (`src/exception_abi.rs:61-65`). For a valid privilege-changing 32-bit exception, CPU old ESP/SS follow at 68/72. They must never be dereferenced on a same-ring exception; a future design must first validate origin and actual transition-stack frame bounds. No optional-tail production access has been added.
- F4 installation copies fixed PREFIX and DATA into owned physical code memory before publication (`src/memory/user_arena.rs:202-205`). Its current payload must not be changed after sealing. A future F5 payload-copy mechanism needs explicit review while preserving F4 policy and twelve-frame ceiling.

## Deferred requirements, not established results

A through E remain required in separate one-shot boots: known user instruction exception; RO USER write #PF with exact error bits and CR2; verified supervisor read #PF; privileged instruction #GP(0); denied port I/O #GP(0). F remains subject to independent complete design review. Exact payload bytes, valid entry selectors, entry frame, scenario identities, stack bounds, reporting closure, RED/GREEN oracles, source-freeze membership and new gate multiset are not approved or finalized.

No acceptance gates were added; no new total is asserted. Complete design/candidate/final review, hardware RED/GREEN, full revalidation and canonical acceptance remain blocked. A prerequisite-only independent review cannot substitute for complete design approval.

## Non-claims

No CPL3 entry, isolation observation, F5 stack bound, NX/W^X enforcement, scheduler, syscalls, recovery, teardown, arbitrary nested-fault survival or real-hardware compatibility is claimed. F1-F4 accepted source and historical evidence remain unchanged.
