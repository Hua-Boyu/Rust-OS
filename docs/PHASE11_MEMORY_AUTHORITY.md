# Physical-memory authority — Phase 11A.2 partial inventory

## Phase 11 B19 case 7 — exclusive shared-mapping refusal characterization

Current policy remains **one exclusive runtime mapping per live payload frame**,
allocator-wide across PageMaps. Unsupported sharing fails closed; no refcount or
new allocator metadata is introduced. Borrowed supervisor boot identity aliases
are translations, not runtime ownership. Rejected maps retain the caller lease,
do not publish a PTE/acquire backing or pins, and increment only map_rejects.
Successful unmap clears the PTE/invalidate before releasing its matching pin;
it does not release the caller's allocation or reclaim empty runtime tables.

Three CHARACTERIZATION tests in mapping_pin_tests exercise same/cross-map
refusal, real table-exhaustion rollback followed by valid retry, and retained
FrameLease A->unmap->B with absent-old-slot/foreign-domain unmap refusal. Owned
snapshots check every allocator diagnostic, all global runtime/structure pins,
the local payload bitmap, all installed PDE/PTE entries and map/TLB counters.
Final unpublished-fixture cleanup restores baseline capacity and diagnostics;
this is not general PageMap/CPU teardown. Ordinary leases cannot originate in
the reserved growth window under init/allocate_stamped; optional D is NOT REACHABLE.

Host331/0/2 and independently rooted B26full104/0 pass serial/parallel; exact11
runtime-pin identities and acceptance-harness56 pass; production/focused128/512
paging pass. Independent candidate review APPROVES the bounded characterization;
fresh canonical acceptance completed exit0/PASS63/63. Offline readback verifies
146 frozen inputs, production ISO/kernel/archive identity and no QEMU. Independent
final readback APPROVES the bounded checkpoint. Local commit identities and exact state:
`test_results/phase11b19_shared_mapping/STATE.md` and its continuation directory.

Numeric map admission still does not authenticate lease ownership or arbitrary
same-slot replacement/unmap generations. CPU/CR3 lifetime, general teardown,
shared ownership/COW, USER/TSS/CPL3 and Phase12 remain deferred/blocked. No
production memory implementation changed in case7. Historical inventory follows.

## Phase 11A.3 generation-safe release checkpoint

Ordinary allocation now stamps a bounded u32 allocation identity; public
`allocate_owned` returns a private-field non-Copy/non-Clone `FrameLease` and
`release_frame` consumes that proof. Checked exhaustion is permanent across init.
Identity/domain validation precedes the single shared raw/lease release helper,
including runtime and structure pin refusals. Successful raw free clears identity.
Growth claims remain exact-address reserved operations with no ordinary identity.
Production FRAME_ALLOC is private; diagnostics copy `frame_stats()` and unlock.

The audited raw structure/growth paths below remain trusted kernel internals,
not arbitrary stale-number safety. Borrowed identity mappings grant no release
authority; publication/CPU retention and heap -> map -> frame order are unchanged.
Full B19, USER and general teardown remain blocked. Current verification and
caller classifications: `PHASE11A3_GENERATION_HANDOVER.md` and task-local
`test_results/phase11a3_generation_ownership/caller_audit.md` (repository root).
The earlier inventory below is retained as predecessor evidence where it says
generation-safe leases are not yet implemented.

Source-derived inventory, not a claim of complete B19. Symbol names are stable
anchors; historical initial-source call analysis is retained in
`test_results/phase11a2_structure_lifetime/physical_authority_inventory_readonly.md`.

## Ownership categories

1. **Permanent reservations:** null, kernel/boot stack, VGA, boot metadata/modules,
   bootstrap heap and firmware exclusions. Inventory type-2 entries and allocator
   coverage/denial bits exclude backing; permanent boot spans also constrain unmap.
2. **Kernel runtime payload:** exact growth claims used by the heap, plus ordinary
   allocated payloads in host fixtures. Runtime PTEs own exclusive mapping pins;
   the caller, not PageMap, retains payload release responsibility.
3. **Paging structures:** directory and nonzero `PageMap.tables` entries own
   allocator structure pins. No production table-sharing or ownership-transfer API
   exists. Another map's *borrowed identity alias* is not structure ownership.
4. **Borrowed supervisor mappings:** boot identity entries, without runtime bit9,
   convey translation only. Removing such an alias never releases a runtime pin
   or physical backing. Do not confuse broad identity coverage with lifetime pins.
5. **Explicit sharing:** not implemented. A second runtime mapping of an already
   pinned payload fails closed, including across maps. There is no shared refcount.
6. **Future process-private frames:** not implemented. Numeric allocation/map APIs
   remain trusted-kernel internals, not safe process authority. USER publication,
   TSS/CPL3 and general address-space destruction remain blocked.

## Operation inventory

`F` = exclusive allocator borrow (global FRAME_ALLOC in production);
`M` = private PAGE_MAP owner; production order is **heap -> M -> F**.
No IRQ may acquire these owners. No production heap reserve, backing destruction,
allocating formatting or arbitrary callback may occur while M or F is held.

| Source operation | Caller/subsystem; action/category | Preconditions and failure/rollback | Ownership/locks; regression anchors |
|---|---|---|---|
| `frame.rs: FrameAllocator::init`, `init_with_reservations` | `memory::prepare`; establish permanent exclusions/domain | Refuse live allocations and exhausted nonwrapping domain issuer before mutation; explicit malformed reservation refusal | M -> F; `domain_tests`, B11 reservation/union tests |
| `frame.rs: allocate` | Production identity builder and missing-table `PageMap::map`; allocate structure candidates | Initialized free pool; None on exhaustion, no partial claim | F; host exhaustion and B26 partial-build tests |
| `frame.rs: claim_growth_frame` | `memory::heap_grow_frame` <- `allocator::alloc_inner`; acquire kernel payload | Exact aligned usable unclaimed growth slot, no competing reservation; None nonmutating | Heap -> M -> F; B11 growth and `growth_tests::b26_growth_failure_does_not_consume_reserved_frame` |
| `frame.rs: free` | Builder exhaustion, table-access refusal, unpublished cleanup, rejected growth publication | Reject live payload/structure pins, invalid/never-issued/double frees; ordinary success restores free pool, growth success restores growth reservation | F; pin tests. **Stale unpinned numeric ABA still reproducibly unsafe** |
| `frame.rs: is_live_allocation`, `runtime_pinned`, `structure_pinned`, setters | Memory-private map/unmap/install/rollback/cleanup; validate or commit role | Managed live allocation is not a generation or caller identity. Setters require prior validation and same exclusive allocator borrow; no heap/failure | F; mapping-pin/domain/structure-lifetime tests |
| `paging.rs: build_identity_map_with_backing_in_place` | Sole production caller `prepare`; own directory/tables, borrow identity payload | Exact zero backing/domain/window preflight; partial exhaustion unpins/frees only new structures and zeroes slots; retains caller Vecs on failure, moves on success | M -> F; B26 backing/refusal/exhaustion tests. Allocating builder adapters are host-only/unlocked |
| `paging.rs: PageMap::map` | Production heap growth; exclusive runtime payload reference, optional new structure | Domain/live/role/permission/alias/destination checks before pin/PTE commit. New table needs writable supervisor identity access; refused candidate freed before pin. Caller payload never freed on failure | M -> F; ownership, runtime-table-access and mapping-pin tests |
| `paging.rs: PageMap::unmap` | Host/diagnostic internal API; release mapping reference, not payload | Match domain and local/global runtime pins; permanent/local structure aliases refused. Clear PTE -> local INVLPG -> release runtime pins; no empty-table reclamation | M -> F if used globally; boot-alias and inconsistent-mirror tests. Inactive-map/SMP mutation not established |
| `paging.rs: release_unpublished_frames` | Sole production use: `prepare` validation failure; release structures only | Mutable, bool result. Refuse retained/released/wrong-domain/live-payload/inconsistent-role map before mutation. Success unpins/frees owned structures and revokes local addresses/domain. Repeated calls reject without allocator mutation; Vec storage survives for unlocked destruction | M -> F; five `structure_lifetime_tests`, B26 validation failure. No general teardown |
| `paging.rs: retain_for_publication`, `enable_paging`, `flush_tlb` | `prepare` publication and memory enable wrapper; retain structures across exposure/CR3 | Irreversible retention before publication or CR3 write; released map rejected. Enable updates per-map enabled diagnostic. No inverse until reviewed CPU teardown | M in production; lifetime activation/publication/reload tests; actual paging guests at 128/512 MiB |
| `memory/mod.rs: page_directory`, `page_snapshot`, `mapped_pages`, `pinned_identity_span` | Boot, shell, boot-copy, fsstress; observe/validate borrowed mappings | Copy scalars only; no guard/reference escapes. End validation borrow before heap/module copy allocation | M only; snapshot/module-access tests. Raw observed address is **not** release authority |
| `paging.rs: PageMap::entry`, `translate`, `permissions`, `directory`, `stats`, `window_end` | Builder validation, runtime table-access checks and isolated host fixtures; observation only | Valid exclusive map owner/shared borrow, never a lifetime lease. Missing/revoked translations return None; revoked directory/window and live table/mapping counts are zero. Historical operation counters remain diagnostic. `stats` borrow stays within the owning scope | M for the global map, ordinary scoped borrows for isolated maps; permission/table-access and revoked-map tests. No allocation or backing release |
| `main.rs`, `shell.rs`: FRAME_ALLOC stats reads | Boot/shell diagnostics, no allocation/free authority used | Copy statistics, drop guard before formatting | F only; retain no-heap-under-owner invariant |

## Structure owner versus references

The private directory/table inventory is the exclusive release set; the global
bitmap is a **role exclusion**, not an owner ID or reference counter. Revocation
closes stale *PageMap cleanup* after address reuse, not arbitrary stale numeric
`free`. Rust moves transfer the one private inventory; PageMap has no Clone/Copy.
Dropping an unreleased unpublished map leaks frames; no automatic Drop reclamation
runs under an unknown lock. Borrowed identity aliases in other maps do not justify
reclaiming backing used by an active CPU. Production still has only one permanently
published kernel map; arbitrary map switching/sharing remains unsupported.

## Teardown contract and stop boundary

Implemented cleanup applies only to never-published, never-CPU-loaded maps with
no runtime payload references. It either refuses without allocator mutation or
releases eligible structures once and revokes the map; backing is dropped unlocked.
Published/CPU-loaded boot structures are retained until reboot. This conservative
single-core policy is not a dynamic address-space lifetime protocol.

Future general teardown must: stop new references; withdraw published mappings;
resume on a kernel-owned CR3/stack/interrupt continuation; invalidate translations;
release mapping references; free only private payload leases; release structures
only after the last CPU/reference; then return ownership metadata. Borrowed and
permanent supervisor backing stays intact. Define explicit repeated-call refusal
or idempotence and complete failure rollback before exposing that API. SMP additionally
requires inter-processor TLB shootdown and concurrent map/CPU lifetime protection.
Neither SMP nor general teardown is implemented here.
