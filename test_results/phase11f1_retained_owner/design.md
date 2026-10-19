# F1 retained one-shot owner — provisional implementation design

STATUS: PROPOSED; independent boundary/budget review pending. Not an implementation approval.
Baseline: maintenance/phase10, b765abcc1350323357accf3623aec42a6185494c.
Authoritative scope: docs/PHASE11_MEMORY_AUTHORITY.md B19 Closure A–F and independent design review in phase11b19_closure_design.

## Source-grounded boundary

The production FRAME_ALLOC and PAGE_MAP owners are private (memory/mod.rs:45–62). Their exported observations are copied scalars; no guard, callback or lease escapes. Boot preparation is once-only after publication (165–242). Growth at 302–315 is the sole existing production post-publication mapping writer discovered in src; it claims frames under PAGE_MAP -> FRAME_ALLOC. Main calls prepare at main.rs:101 and enables paging at :207. allocator.rs:272 can invoke growth from heap allocation.

FrameAllocator::release_frame authenticates domain/id then calls release_by_address (frame.rs:445–525); raw free shares that core. Runtime and structure pins prohibit release, but no retained-smoke policy exists. allocate_owned and raw allocate share allocate_stamped (378–418). Exact growth is separate (534–557). init (201 onward), pin setters, bootstrap construction and raw numeric operations must be included in final audit.

PageMap::retain_for_publication (paging.rs:224–229) prevents unpublished structure cleanup (182–219). It does NOT prohibit map_authorized (362–478) or unmap_authorized (513–584). map_owned/unmap_owned require live borrowed leases; no weakening of their existing authority is proposed. Runtime unmap clears PTE, invalidates and drops runtime pin. Both CR3 writers (flush_tlb :691, enable_paging :898) retain structures first but do not freeze mapping mutation. Bootstrap build :745–839 writes paging structures directly and invokes raw allocation and pin setters.

## Smallest candidate

Introduce one private const-initialized static owner near the existing memory owners. Production offers no constructor, reset, returned lease, mutable owner, callback or cleanup API. Test-only per-instance fixtures must not weaken production visibility. A singleton latch is claimed before any fallible preparation; Uninitialized -> Preparing -> Sealed -> Terminal, with all preparation errors -> Terminal. There is no Entered/CPL3 state in F1. At most one attempt per boot, including zero-acquisition errors. IRQ entry is prohibited; no owner held across formatting, heap allocation or destruction. Exact lock order and singleton storage integration require independent review before implementation.

Candidate whole-domain freeze: once resources are validated, irreversibly prohibit FrameAllocator allocation/release/init/growth and pin changes and PageMap map/unmap/structure cleanup/CR3-writing helpers. This avoids a new per-frame CPU-lifetime ledger. Existing normal production behavior is unchanged before explicit smoke preparation. Freeze must be checked before real backing or identity mutation, not just by an owner Boolean. Later F3/F4 may need an explicit build-before-final-seal integration; that is NOT implemented in F1. If a whole-domain freeze makes later slices incompatible, stop rather than add privileged unseal or bypass.

Existing raw physical writes and arbitrary privileged asm remain trusted unsafe kernel operations, not capabilities. The final audit must list every reachable production caller and show the dedicated smoke cannot invoke them after seal. General kernel memory integrity against arbitrary Ring-0 code is not claimed.

## Provisional bounded inventory and unresolved budget

No numeric future capacity was approved by the preceding design. Proposed F1 actual acquisition: one ordinary frame for future fixed payload and one for the dedicated supervisor sentinel, exactly two allocate_owned calls, no search/retry and no table publication. Each must have an effective writable supervisor identity alias in the current map before future use. Store move-only leases in fixed Option slots and retain directory/domain identity as scalars. Do not copy/zero payload bytes or claim USER/stack/TSS readiness.

One page is the minimum physical allocation unit (FRAME_SIZE = 4096). Proposed actual maximum is therefore two frames / 8192 bytes, subject to independent approval; this is NOT the total eventual smoke budget. Existing directory/tables/boot stack/descriptor/heap storage remain retained separately. No extra PageMap or payload bitmap is allocated. No Vec or dynamic metadata is introduced.

Inventory must explicitly describe payload, sentinel, page-directory identity, existing paging backing, supervisor aliases, future user stack, kernel transition/emergency stacks, guard reservations, descriptors and diagnostic storage. Future stack/table counts are not safely derivable from the prior plan: transition/emergency sizing depends on F2 entry containment and F3 emitted-stack evidence. Provisional unacquired/unready fields are not fake installed CPU state. Independent review must decide whether zero F1 acquisition for those classes is a valid slice bound, or whether F1 must stop pending an amended reviewed manifest. DO NOT invent a safe numerical stack limit merely to satisfy a checklist.

Memory evidence after an approved implementation must compare actual baseline/candidate ELF .data/.bss/allocated spans, owner symbols, emitted preparation frames and allocator capacity deltas at 128/512 MiB. Host type sizes alone are insufficient. Caller/IRQ high-water remains unknown until measured.

## Failure policy

Before acquisition: latch terminal on missing map/domain/alias prerequisite. After any acquisition: retain every acquired lease in its fixed slot and enter terminal failure, never publish USER and never retry. Proposed maximum failed retained capacity is two frames. No rollback guarantee is asserted where it has not been proved. After seal: refuse release/unmap/reset/reallocation/CR3 writes without changes to backing, generation, pins or accounting. Future CPU publication is not implemented and remains blocked; its terminal lifetime must use the same irreversible policy.

## RED-first and review prerequisites

First source edit must be a runtime test, compiled by the existing host cfg(test) module boundaries; not a nonexistent-API compiler error. A reviewed baseline seal adapter may be necessary to expose the missing policy without fabricating production state. Tests must prove singleton admission, real partial allocation exhaustion, exact sealed release/unmap refusal and unchanged pins/PTEs/identity/capacity, terminal retry/reset refusal and every genuine preparation error. Existing behavior should be labeled characterization where appropriate.

After focused GREEN: preserve exact libtest identities and inherited ignores, full host and independently rooted B26 serial/parallel, production formatting/build, explicit production-reachable Ring-0 fixture at 128/512 with unchanged CR3 and bounded failure/retry/refusal; no CPL3. Extend existing acceptance exact-family controls only if needed and preserve inherited multiset discovered from the actual accepted manifest. Independent candidate review and complete hash-pinned verdict precede one frozen canonical acceptance. No implementation, new test result, acceptance or completion is claimed by this draft.
