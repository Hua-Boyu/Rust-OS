# Bounded caller authority audit

Scope: source searches for frame allocate/free/lease/growth ownership entries in src/, tests_kernel/src/, tests_b26/src/. PortAllocator/FD operations with the same method names are excluded by symbol/type inspection. This is not a full-kernel audit or full B19 approval.

| Entry/caller | Classification | Safety boundary / migration |
|---|---|---|
| FrameAllocator::allocate_owned / release_frame | Lease API | Private address/id/domain; checked issuer; consume by value; shared release refusal/accounting, including runtime and structure pins. No Drop auto-free. A refused consuming release leaks its authority rather than freeing backing; callers should end pins first. |
| paging::build_identity_map_with_backing_in_place ordinary directory/table allocation and exhaustion rollback | Audited internal raw | Exclusively borrowed allocator; fresh candidates; structures installed with pins. Failure unpins only owned candidates before raw free. Identity stamping/exhaustion now shared with leased allocation. No external stale numeric cleanup inventory remains after successful unpublished release. |
| PageMap::map optional table allocation/accessibility rollback | Audited internal raw | Domain check and live payload admission first; fresh candidate freed only before structure installation if identity access refused. PTE publication follows all fallible operations. Caller payload is never freed on refusal. |
| PageMap::release_unpublished_frames | Audited internal raw | Retained/payload/wrong-domain refusal; preflight complete private structure set; exclusive allocator borrow; clear pins/free then revoke inventory. Published and CPU-loaded structures retained until reboot. |
| memory::prepare | Borrowed/permanent mapping + audited raw structure builder | Boot/kernel/stack spans reserved; preallocated backing; map->frame ordering; builder/failure cleanup as above. No large runtime FrameAllocator construction. |
| memory::heap_grow_frame -> allocator::alloc_inner | Existing growth operation | Exact reserved claim, ordinary ledger identity remains zero, mapping pin protects retained heap payload. Rejected map restores growth-only reservation under same map->frame owners. Not converted to ordinary leases. |
| main::prepare-memory diagnostics and shell mem | Migrated read-only | Production FRAME_ALLOC private; frame_stats() copies Option<FrameStats> under one guard, no formatting under owner. Test-only owner visibility remains crate-private for independently rooted detector fixtures. |
| replace_growth_with_test_conflict | Test-only operation | cfg(test), unmap old growth backing before release; raw payload conflict stays test-owned. |
| B11, B18, B26, ownership/pin/structure tests and maintenance measurements | Test-only operation | Raw APIs remain crate-private so real-module fixtures retain intentional refusal and rollback probes. Negative lease duplication exists only under cfg(test). |
| boot identity payload mappings | Borrowed/permanent mapping | Translate only; never conveys payload release authority. |
| USER/private processes/shared references/general teardown | Deferred, not implemented | No production ordinary payload release caller exists outside audited structure paths. No USER/TSS/CPL3/ELF/syscalls/scheduler added. Future process-owned APIs must use leases; numeric map itself remains trusted memory-internal authority, not complete capability admission. |

Raw methods are pub(crate), as approved; this is an audited kernel boundary, not a type-system ban on all crate-internal numeric misuse. Raw-numeric historical ABA remains a valid old-API blocker probe and is not relabeled GREEN. The migrated lease probes establish stale-token refusal, not arbitrary-number safety.

No new lock edge: HEAP -> PAGE_MAP -> FRAME_ALLOC. No new allocation, backing drop, callback or IRQ entry under these owners. Existing ignored-free-result cleanup paths were reviewed for their exclusive preflight/fresh-candidate invariants; unrelated diagnostic/backlog rewrites were not performed.
