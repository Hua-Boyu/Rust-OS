# Phase 11A.2 physical authority plan — PARTIAL, no USER publication

## New bounded prerequisite — runtime payload pins, not this full ledger

`docs/PHASE11A2_STRUCTURE_AUTHORITY_HANDOVER.md` is the current status/evidence pointer. A second allocator-domain bitmap `structure_pins` (8,192 bytes) now marks frames installed as paging structures; free and payload mapping refuse them, and release/rollback sites clear pins with their frees. This is shadow metadata mirroring `pm.tables`, allocator-wide and not per-map accounting.
Allocator-wide runtime payload pins, domain-bound map/unmap and live-reset
refusal are implemented with an 8,192-byte bitmap, not the proposed dense
generation ledger. Stale numeric release and page-structure role/CPU lifetime
authority remain open. The design below remains a broader plan, not implemented
or newly budget-approved. No TSS/CPL3 may rely on the partial pins alone.

## Scope

This plan is not an implementation or approval of B19. Preserve the published
boot map, supervisor identity aliases and permanent boot reservations. Do not
start exception recovery, TSS or CPL3 until the complete ownership boundary is
reviewed. Raw physical addresses are observations, not capabilities.

## Selected model and staged migration

Use a bounded allocator-private authority ledger with nonduplicable allocation
handles. Separate allocator availability, reservation denial, allocation class,
mapping references and CPU pins. Do not infer allocation from `!is_free`.

1. **Reservation prerequisite:** expose an allocation-state predicate only to
   memory internals. Require initialized, aligned, nonzero, managed, complete
   usable coverage, no competing reservation, and current allocation. Growth
   requires its explicit live growth claim. This closes reserved/unmanaged raw
   mapping admission, but is not a capability boundary. It adds no backing.
2. **Authority handles:** issue opaque, non-Clone allocation tokens with allocator
   epoch and nonwrapping allocation identity, physical address and class. Validate
   exact ledger identity on every operation. Retire exhausted identity space;
   reinitialization must refuse while resources/CPU pins remain. Restrict raw
   numeric allocation/free authority to audited bootstrap internals; never offer
   it as the safe process API. A stale numeric address cannot identify an owner.
3. **Mapping transaction:** validate virtual range, permission, allocator identity,
   token identity/class, map identity and destination before changing state. Claim
   table backing separately from payload. Record an exclusive mapping reservation
   in the allocator before publishing a PTE. On any failure release only the
   transaction's reservations and newly allocated tables, never caller payload.
4. **Lifetime:** unmap must hold matching map then allocator authority; clear PTE,
   invalidate translation, then release that mapping reference. An inherited boot
   alias must never release a runtime reference. Ordinary free refuses live map,
   table, heap or CPU references. A borrowed mapping never frees backing. Explicit
   shared references require checked bounded counts; until implemented refuse
   shared mapping rather than silently borrowing an exclusive token.
5. **Publication/CPU pin:** keep the boot map permanently pinned. A future active
   address-space guard pins directory, tables, payload and all kernel/user/IRQ/TSS
   stacks. Teardown requires a kernel-owned continuation and restored CR3/stack,
   then translation invalidation, then reference/token release. Inactive teardown
   releases only owned resources; permanent and borrowed backing remain.

## Boundedness and lock rules

No unbounded heap ledger. Choose measured static or pre-reserved fixed-capacity
metadata after independently reviewing the allocation/frame budget. Avoid large
by-value allocator temporaries on the 16 KiB bootstrap stack. The existing bitmap
covers 65,536 frames. A complete per-frame u64 identity costs 524,288 bytes before
class/refcount storage; this is a design cost, not allocated storage. A bounded
live-record table is an alternative with explicit admission failure. Do not add
that storage without reviewing actual emitted stack frames and minimum-RAM boot.

Preserve heap -> map -> frame order. Allocate all backing before map/frame guards;
destroy it after both unlock. No arbitrary callbacks or IRQ entry into these
owners. All address/range/count/identity calculations are checked before
publication. No deferred reclamation queue is needed while USER and dynamic
address-space destruction are refused; future teardown must define it explicitly.

## Compatibility fixtures and oracles

Existing host fixtures directly map unclaimed growth/reserved numeric addresses.
Do not weaken them or permit reserved ownership to keep them green. Give positive
mapping fixtures an explicit allocation/eligible growth claim while preserving
their permission/table-lifetime assertions. Boot identity construction remains a
borrowed supervisor mapping operation and does not acquire payload ownership.

Required RED/GREEN families include reserved/null/invalid/table alias, duplicate
exclusive/cross-map, mapped-free refusal, borrowed/shared lifetime, stale release,
per-stage failures, partial rollback, owned-only teardown, active CPU pins,
exhaustion/recovery and boot-alias preservation. Host serial/parallel results are
not real CPU proof. Run sequential local 128/512 MiB guests and the complete
source-frozen official acceptance after each reviewed production checkpoint.

## Exact stop condition

The first reservation predicate is deliberately only a prerequisite. It does not
solve free-while-mapped, cross-PageMap or stale release. Keep those BLOCKED and
preserve failing experimental evidence rather than claim full B19. Existing
exception ABI edits also remain unapproved until actual CPU-frame probes and
emitted assembly verify the contract. No TSS or user-mode execution is authorized
by inherited supervisor acceptance alone.
