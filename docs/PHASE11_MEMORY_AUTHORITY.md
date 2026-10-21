## Current — F3 GDT/TSS/privileged stacks ACCEPTED (2026-10-22)

F3 IS ACCEPTED: canonical 70/70 exit 0 at test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json
(sha 2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b); source frozen at
full_source_freeze_05.json (179 pins); candidate review05 APPROVE/0 (50501d79c4421a3698c9f8620a9867f70e5edf5eee3adcfbed118fc1cce0c777);
final readback01 APPROVE/0 (a22a2e437caafaa701bfaba0072066ec0fd75a7074241e37acacf958d14f3cb2).
Hardware 18/18 FULL_RING0_GREEN (1056 pins); host 366/0/2; B26 134/0/0; F2 8/8; F1 10/10.
Stack bound 2578/16384/13806 (conditional one-nested-NMI). F3-scope correction only (F1/F2 contracts untouched).
No CPL3, no USER mappings, no push. Next: F4 requires fresh authorization. See STATE.md + FINAL_REPORT.md.

## Latest F2 continuation — canonical 68/68 PASS exit0; final readback APPROVE — F2 ACCEPTED

Current authority: `test_results/phase11f2_exception_abi/STATE.md` and `FINAL_REPORT.md`.
The baseline gate is resolved as independently approved provenance-only ClassB
plus explicit operator authorization of the disclosed current baseline. Exact old
capture-script bytes differ only by one trailing blank LF; historical final F1
readback remains missing, not fabricated or replaced with a partial checkpoint.
Approved fixed68-byte exception ABI is implemented with preserved registers and
selectors, kernel DS/ES/FS/GS normalization, CLI/CLD, aligned nonreturning Rust
entry, hardware-error handling, no same-ring tail access and frame-independent
unsupported21/29/30 handling. Fatal22-function emitted closure has no allocation,
lock, panic/unwind or indirect-call edges. Ordinary-stack #DF limits remain.
Fresh host359/0/2 and B26127/0/0 pass serial/parallel with exact identity readback;
F2 Ring0 hardware8/8 and F1 retained-owner10/10 pass at128/512MiB. Candidate review
APPROVE/zero blockers, raw73ae98d5fc353da6dc6c57a78a3d10c67493150f26cc96eb3c56ee8df90b3565.
One canonical68-gate acceptance COMPLETED: sessionproc_d24a68e23079 actual exit0,
explicit PASS 68/68 at `canonical_acceptance_01/acceptance_20261020T225049Z_p25gcqvh/acceptance.json`
(sha256 c619ffe5c99de75701528b836e1ba1eeeb904720d279b3e6392050852359f0a9);165 source/build
inputs frozen and rechecked stable after scoped source commit e99d82f. Parent offline
reader02 PASS (f2_parent_canonical_readback_04) resolves CU01-CU03 of closeout_utility_review_01;
reader01/review01/readback01 remain preserved. Independent final canonical readback
COMPLETED: APPROVE, zero blockers, nine check groups PASS with exact path+SHA256
evidence (`reviews/final_canonical_readback_01.json`, sha256
36c7668e3813118b765b349b28ef21d3ffe7a7f61463ef5fd8776a595204f6c1). F2 IS ACCEPTED.
No source edits,
competing builds/QEMU or second acceptance; never unlink the OS-held lockfile.
No F3-F5/TSS/USER/CPL3/deployment/push.

## F3 GDT/TSS/privileged stacks — IN PROGRESS, NOT ACCEPTED (2026-10-21)

Read `test_results/phase11f3_gdt_tss/STATE.md` and `FINAL_REPORT.md` first. Design review
APPROVE/zero blockers is design-only. Candidate implements static 5-entry GDT (null/code08/data10/
normalTSS18/emergencyTSS20), two 104-byte TSS contexts, ltr ordering, retained-owner privileged-stack
transaction (transition/emergency 4+4 pages with unmapped guards), #DF task gate to emergency TSS.
Actual evidence: runtime_red_01 (TR=0), hardware_green_02 MINIMAL 10/10 CPU-backed, host 366/0/2 +
B26 134/0/0 exact membership, F2 preservation 8/8 and F1 preservation 10/10 fresh PASS.
Supplemental #SS/NMI now8/8 GREEN with508 raw assertions and standalone pin validation
(supplemental/prepared_20261021T142053Z). Earlier kernel-livelock claim withdrawn: harness
awaited unreachable assembly f2_terminal after divergent f2_fatal. Candidate review01
remains REJECT2; full18 canonical integration/run, refreshed production build/ELF,
renewed review and acceptance remain. F3 NOT accepted; no CPL3, no USER mappings,
no push. The 12-frame F1 ceiling is unchanged (8 new frames +
inherited 2 + future 2). Historical F2/F1 blocks below remain unchanged checkpoints.

The complete earlier document below is preserved historical authority, superseded
only by this latest bounded F2 status; it is not a new F1 redesign authorization.

# Physical-memory authority — Phase 11A.2 partial inventory

## F2 current checkpoint — PARTIAL / prerequisite evidence STOP (2026-10-20)

No memory-owner, production exception, test or acceptance-harness changes.
`test_results/phase11f2_exception_abi/FINAL_REPORT.md` records a genuine Ring-0
QEMU selector-normalization runtime RED and independently approved bounded
exception-prefix design, not an implementation. F1 runtime source and emitted
kernel match accepted identities; no F1 regression/reopening. Historical66-gate
PASS is verified, but full accepted-input identity differs for one capture-test
script and a matching final independent acceptance readback was not recovered.
Baseline-disposition clarification timed out; production-edit gate remains
closed. No F2 acceptance, recoverable-user ABI, TSS/ESP0, USER publication or
CPL3 claim. Same-ring frames must not reference nonexistent oldSS/ESP; #DF
savedCS/EIP are undefined and robust stack-failure containment remains an F3
emergency-strategy dependency. Current details supersede historical claims below.

## F1 v2 current checkpoint — ACCEPTED (66-gate canonical acceptance, 2026-10-20)

Task evidence: `test_results/phase11f1_retained_owner/` (STATE.md, FINAL_REPORT.md,
evidence_manifest.json, f1_candidate_review_01.json, f1_acceptance_01/). F1V2-B3 is
CLOSED: Option B capture — QEMU `-control` stop at guest `.set` checkpoint symbols;
host reads actual CR3 and exact page-table bytes while the vCPU is stopped; capture
acknowledged before resume; timeout/missing-ack fails closed (scripts/test_f1_capture.py
14/0). Independent design APPROVE/0 (b3_design_revision_review_02.json); independent
candidate review APPROVE/0 (f1_candidate_review_01.json). Live runtime RED preserved
(b3_real_guard_red_01, exit 101). Implementation: one-shot preparation, fixed
manifest, bounded acquisition (2 frames within the 12-frame/49152-byte policy cap),
owned FrameLease slots, failure-stage codes 1-6, irreversible seal gating release/unmap/
CR3 publication, nonallocating nonreturning terminal path, no USER/TSS/CPL3/IRET.
Fresh host 352/0/2, B26 127/0/0, focused 9/0 exact identities, guest matrix f1_guest_02
10/10 PASS at 128/512 MiB with pre-probe/pre-seal table-byte captures, canonical
acceptance f1_acceptance_01 66/66 PASS (acceptance.json sha256 4cd36eb2...).
Lock dist/.phase6_acceptance.lock preserved. No F2-F5, no CPL3, no push/deployment.

Concrete proposal and complete verdicts reside in
`test_results/phase11f1_retained_owner/`. Operator declarations were explicitly
SOLE_WRITER=YES, CEILING=YES, CONTINUE=YES; implementation continuation required
independent APPROVE with zero blockers and was NOT reached.

Combined review accepted a finite policy inventory: payload1/sentinel1 to acquire
through existing allocate_owned into two fixed static Option<FrameLease> slots;
future user1/transition4/emergency4/arena-table1 NotAcquired, total12 policy frames.
Existing directory/tables/backing/aliases/descriptors retain established ownership;
no new F1 mapping, table, USER leaf, TSS or stack mechanism. Proposed owner-family
and future-descriptor static envelopes are separately finite, not emitted-size or
stack-sufficiency proof. Global irreversible Sealed/Terminal guard, actual CPU
CR3/mode validation and divergent CLI/unlock/bounded serial/HLT remain design,
not implementation. Initial reviewed design bytes and original pins are preserved.

Initial combined REJECT/2 led to ONE permitted revision selecting isolated
real-source guest build/injection, valid separately rooted alternate map and
post-unlock real helper probes. Final revision review is REJECT/BLOCKERS1:
F1V2-B3 requires a selected ordered exact pre-seal/pre-probe guest table-image
capture mechanism. Terminal-only QMP reads or checksums cannot prove prior bytes.
All162 reviewed raw pins matched at resolution readback; this handover insertion
is later documentation, not retroactive extension of those reviewed bytes.
No third redesign or production-source/test edits in this session.

Fresh unchanged-baseline host343/0/2 and B26116/0/0 pass serial/parallel with
exact345/116 identities; production build/fmt/ELF pass. All150 canonical inputs
unchanged. No live-crate RED, F1 GREEN, guest, candidate review or canonical
acceptance; no Ring-3 readiness. Further capture design/review requires fresh
authorization. No F2-F5/general teardown/deployment/push/Symposium setup.
Historical checkpoint blocks and approved B19 section below remain unchanged.

## Phase 11 F1 retained-owner attempt — PARTIAL / DESIGN STOP

Task evidence: `test_results/phase11f1_retained_owner/STATE.md` and
`FINAL_REPORT.md`. Implementation was authorized for F1 only, but no production
owner or seal was implemented. Two independently reviewed isolated baseline
runtime probes fail at the intended assertions: structure retention still permits
owned unmap and release of an unpublished, unpinned owned frame. Each executes one
test with Cargo exit 101; the ordinary map/unmap/release characterization passes.
These are missing-policy REDs, not regressions in the accepted B19 API contract.
The live kernel and host/B26 source and inherited acceptance families are unchanged.

Fresh unchanged-baseline host tests pass 343/0/2 and B26 116/0, each serial and
parallel, with exact identity/list readback; baseline production build and ELF
validation pass. No F1 GREEN, guest evidence or canonical acceptance was obtained.
Historical 65-gate acceptance is not reused as F1 acceptance.

Independent boundary review rejects full F1 completion: the draft does not yet
close the manifest, joint irreversible seal/alternate CR3 activation boundary,
or dedicated nonreturning terminal invocation. A separate budget review recommends
a conditional 12-frame policy ceiling (not stack sufficiency or implementation
approval); fixed metadata/descriptor/diagnostic shapes and concrete integration
still require a revised reviewed design. Do not invent headroom, temporarily
unseal for F3/F4, or call two retained frames a complete future-resource manifest.
Resume F1 design/RED-first work from the task STATE. No F2-F5, USER/TSS/CPL3,
general teardown, deployment or push. Accepted checkpoints below remain historical.

## Phase 11 B19 same-slot unmap authority — BOUNDED VERIFIED

Runtime unmap now requires `PageMap::unmap_owned(fa, linear, &FrameLease)`: the
borrowed lease is authenticated against the live allocator domain, nonzero
allocation identity and current generation before any PTE clear; refusal retains
the mapping, pins and allocator state. The numeric `PageMap::unmap` adapter and
the shared `unmap_authorized` core are cfg(test)/private respectively; the
production-cfg probe `scripts/unmap_api_probe.rs` compiles only the lease entry
point and rejects numeric/private-core calls. A stale lease cannot remove a
replacement mapping at the same slot; foreign-domain and stale-generation leases
refuse without mutation. No mapping token, generation table or new metadata was
introduced; per-PageMap binding is by construction (the operation mutates only
the PageMap instance receiving the call).

Fresh focused3/0, host343/0/2 and B26full116/0 serial/parallel, harness62,
production/fmt and focused128/512 paging pass with exact identity readback;
inherited test identities preserved. Runtime RED preserved:
`unmap_authority_red_02` Case A FAILED against baseline 04e4b31 before the fix.
Independent design and candidate reviews APPROVE with zero blockers. Canonical
acceptance 65/65 PASS exit0 (acceptance_20261019T161350Z_fo8p107g) with
independent final readback PASS; local commits ab2b501 + docs checkpoint.
Case7 unmap semantics below are inherited history. Per-PageMap ownership
transfer, general teardown, CPU/CR3 lifetime and exception continuation remain
open; no shared/COW/USER/TSS/CPL3/Phase12 claim.

## Phase 11 B19 numeric-map authority — candidate, acceptance pending

Ordinary runtime publication now uses `PageMap::map_owned(fa, virtual,
&FrameLease, perms)`. The borrowed token is authenticated against initialized
allocator/domain, aligned nonzero managed ordinary backing, current nonzero
allocation identity and live allocation eligibility. A Rust reference alone is
not authority. Validation precedes table/PTE access; refusal retains the lease.
Existing runtime and structure pins, permission/null/alias checks and rollback
remain in the paging-private `map_authorized` core. No lease reference is stored;
runtime pins continue protecting backing after the temporary borrow ends.

The only production runtime numeric caller, `memory::heap_grow_frame`, now uses
slot-only `map_growth_claim`: exact live growth-window identity backing and fixed
supervisor permissions. It cannot choose ordinary payload backing. The old `map`
adapter exists only under cfg(test) for explicitly privileged legacy fixtures.
Crate visibility is not the security argument: semantic authority checks and a
production-cfg compile oracle close the ordinary accessible numeric interface.
Paging descendants remain trusted; existing fixture descendants are cfg(test).

Explicit audited exceptions remain: bootstrap borrowed supervisor identity builder,
structure allocation/inventory and exact growth claims. The builder is trusted
bootstrap policy, not a newly runtime-enforced bootstrap capability; borrowed
aliases confer no payload ownership. Raw allocator primitives remain trusted.
Current caller/design inventory: `test_results/phase11b19_numeric_map/`.

Fresh focused9/0, host340/0/2 serial/parallel and B26full113/0 serial/parallel,
harness59, production/fmt and focused128/512 paging pass. Independent design
and source reviews APPROVE_BOUNDED with zero blockers. Canonical acceptance
64/64 PASS (acceptance_20261019T133256Z_skpr6lcf) with independent final
readback PASS; local commits 4ab6c82/571d3ff. No new ledger/lock/backing
allocation. No full B19/teardown/CPU lifetime/sharing/USER/TSS/CPL3/Phase12
approval. The case7 results below are inherited history.

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

## B19 Closure and First Ring-3 Smoke Entry Criteria

Design checkpoint against `98da93b6dd4b6fb276c9cf27887571c6baea4499`
(source predecessor `ab2b501`). This section supersedes historical statements
above only for the **proposed first-smoke prerequisite set**, not for general
ownership closure. No implementation or CPL3 execution occurred in this session.
Review and byte identities: `test_results/phase11b19_closure_design/`.

### A. Focused ownership authority map

Current source inspection; test names below are existing **host** declarations,
not newly executed tests. Accepted predecessor evidence is separately identified.

| Operation | Authority required | Enforcement source | Existing test | Status |
|---|---|---|---|---|
| Allocate: `allocate_owned` | Exclusive initialized allocator with eligible capacity; issues private domain/address/allocation identity lease | `src/memory/frame.rs:410`, stamped allocation commit at `src/memory/frame.rs:387`, live oracle at `src/memory/frame.rs:425` | `generation_safe_repeated_allocate_release_cycles_keep_state`, `src/memory/generation_ownership_tests.rs:151` | Implemented ordinary authority; not a CPU-lifetime token |
| Release: `release_frame` | Consumed lease with matching live domain/id; no runtime or structure pin | `src/memory/frame.rs:508`, identity refusal at `src/memory/frame.rs:517`, pin refusals at `src/memory/frame.rs:457` | `generation_safe_stale_lease_cannot_release_reused_frame`, `src/memory/generation_ownership_tests.rs:48`; mapped refusal at `src/memory/generation_ownership_tests.rs:114` | Implemented; refusal consumes the passed lease value, not a retry-capable error return |
| Map: `map_owned(fa, linear, &FrameLease, perms)` | Matching map/allocator domain and live borrowed lease; eligible unpinned payload, valid vacant supervisor slot | `src/memory/paging.rs:310`, `src/memory/paging.rs:373`, `src/memory/paging.rs:404`, pin-before-PTE at `src/memory/paging.rs:470` | `numeric_map_live_lease_borrow_pins_until_unmap`, `src/memory/numeric_map_authority_tests.rs:135`; production API oracle at `src/memory/numeric_map_authority_tests.rs:6` | Implemented supervisor-only; **does not publish USER** |
| Unmap: `unmap_owned(fa, linear, &FrameLease)` | Matching live lease plus exact PTE payload match, local map authority and structural/boot exclusions | `src/memory/paging.rs:484`, payload comparison at `src/memory/paging.rs:568`, clear/invalidate/unpin at `src/memory/paging.rs:572` | `unmap_authority_stale_lease_cannot_unmap_replacement_mapping`, `src/memory/unmap_authority_tests.rs:74`; foreign/stale at `src/memory/unmap_authority_tests.rs:102`; production API at `src/memory/unmap_authority_tests.rs:8` | Implemented ordinary boundary; not general teardown |

Specialized paths and bypass scope:

- **Exact growth:** `claim_growth_frame`, `src/memory/frame.rs:534`, refuses
  noneligible/competing claims at `src/memory/frame.rs:546`;
  `map_growth_claim`, `src/memory/paging.rs:326`, binds identity slot and fixed
  supervisor permissions. Production owner order/failed-publication rollback is
  `src/memory/mod.rs:302`. Not a user allocation path; retain heap mappings.
- **Structure ownership:** runtime install pins its table after writable supervisor
  identity-access validation (`src/memory/paging.rs:439`,
  `src/memory/paging.rs:452`). Unpublished cleanup preflights the complete private
  inventory, refuses retained/live-payload maps, then revokes it
  (`src/memory/paging.rs:182`). Existing host declarations:
  `structure_cleanup_cpu_activated_map_cannot_release_structures`
  (`src/memory/structure_lifetime_tests.rs:67`) and
  `structure_cleanup_publication_and_cr3_reload_retain_backing`
  (`src/memory/structure_lifetime_tests.rs:117`). Not inactive published teardown.
- **Borrowed bootstrap aliases:** known inventory contract is supervisor
  translation without runtime payload ownership (historical inventory above).
  Builder call/publication inspected at `src/memory/mod.rs:202` and
  `src/memory/mod.rs:228`; full builder reservation/alias construction and every
  rollback branch NOT VERIFIED in this bounded inspection. Do not reclassify
  these privileged paths as independently proved safe. Before USER admission,
  require a complete effective-permission audit of the resulting active map.
- **Trusted numeric operations:** allocator `allocate`/`free` remain crate-private
  (`src/memory/frame.rs:401`, `src/memory/frame.rs:500`); they are not capabilities.
  Map/unmap numeric adapters are test-only (`src/memory/paging.rs:339`,
  `src/memory/paging.rs:500`); cores private (`src/memory/paging.rs:362`,
  `src/memory/paging.rs:513`). No user-facing allocator/map/free operation is
  proposed. Full crate-wide privileged caller audit NOT VERIFIED; slice 1 must
  enumerate all reachable smoke mutation/release paths before sealing.
- **CR3 publication/retention:** private owner serializes publication
  (`src/memory/mod.rs:193`); retention is irreversible
  (`src/memory/paging.rs:224`) and precedes both inspected CR3-writing helpers
  (`src/memory/paging.rs:691`, `src/memory/paging.rs:898`). This protects their
  structure release set, **not** arbitrary stack/payload unmapping. The smoke
  needs an additional enforced no-unmap/no-release lifecycle policy.

Predecessor evidence: `test_results/phase11b19_unmap_authority/FINAL_REPORT.md:39`
lists the exact-three host identities; `:44` records host 343 passed/2 ignored,
B26 116 passed and canonical 65/65 PASS. Its `acceptance_readback.json` reports
PASS/exit 0. This session compared all 150 recorded source/build hashes with live
bytes (all match), checked the acceptance JSON digest and 65 gate rows; it did
not rerun acceptance or independently replay every nested report. Review pins
are in predecessor `candidate_review.md:57`. These are **accepted historical
host/guest results**, not CPL3 proof or a fresh guest run.

### B. Remaining B19 gap matrix

All new mechanisms/oracles in this table are [PROPOSAL]. Required evidence means
future evidence, not results obtained here. Dependencies refer to slices F1–F5.

| Gap / source evidence | Why it matters | Classification | Minimum implementation or enforced policy | Proposed RED oracle | Necessary host / guest evidence | Exit criterion; dependencies |
|---|---|---|---|---|---|---|
| Active map/table/stack/payload lifetime: retained flag protects structure cleanup only (`src/memory/paging.rs:185`, `src/memory/paging.rs:224`) | Unmap can invalidate CPU/TSS backing even if free pins work | SMOKE-REQUIRED | One immutable sealed smoke resource set on existing CR3; no unmap, free, map replacement, reset, second launch or CR3 switch after seal; retain metadata too | Attempt each forbidden operation in armed/entered/terminal states; state/capacity unchanged | Host state-machine/authority tests; QEMU CR3/stack/PTE identity before entry and at terminal capture | No reachable reclamation or backing mutation; F1, F4, F5 |
| Published-map teardown (`src/memory/paging.rs:182` is unpublished-only) | Reclaiming active structures is unsafe | POLICY-DEFERRABLE | No published teardown entry in smoke; retain until emulator termination/reboot, including failed partial preparation | Launch retry/cleanup request after any acquired resource or seal refuses without release | Host monotonic lifecycle and bounded-failure tests; guest terminal cannot resume shell/relaunch | Option A restriction enforced, not a comment; F1 |
| Per-map transfer and shared references (`src/memory/paging.rs:404`, `src/memory/paging.rs:419`) | A release owner must not outlive hidden aliases | POLICY-DEFERRABLE | One existing map, one retained owner, exclusive ordinary leases; no ownership transfer/shared/COW/user alias API | Second alias/foreign authority/transfer refused without mutation | Preserve accepted host tests; audit user PTE inventory in guest | No second runtime reference or hidden release path; F1, F4 |
| USER range/publication (`src/memory/paging.rs:373`, `src/memory/paging.rs:396`) | Current ordinary API rejects USER and proposed high arena | SMOKE-REQUIRED | Narrow private owned arena transaction; validate both PDE/PTE, kernel supervisor invariants, bounds and table accessibility; do not relax ordinary map API | Unowned/foreign/stale/reserved/structure/occupied/overflow/user-kernel elevation and per-stage failure probes | Host exact-state refusals/rollback or bounded terminal retention; QEMU actual allowed user access plus denied supervisor/guard/code-write cases | Only intended user leaves reachable, no kernel directory elevation; F1 -> F4 |
| Exception normalization and CPU frame contract (`src/interrupt.rs:188`, `src/interrupt.rs:303`, `src/interrupt.rs:313`) | Misdecoded CS/error/ESP can turn a kernel fault into false PASS or corrupt stack | SMOKE-REQUIRED | Explicit reviewed 32-bit entry contract, origin check, segment/DF/alignment handling and terminal user-fault capture; fatal kernel exceptions | Real no-error/#GP/#PF fixtures with known frame/register/stack sentinels; wrong-origin capture must fail | Host layout/decode + emitted i686 disassembly; QEMU CPU frames, not synthetic host structs | F2 verified, including C's architectural blocker, before F5 |
| Static GDT/TSS/SS0/ESP0/transition stack (installed entries at `src/gdt.rs:130` and `src/gdt.rs:155`) | User fault requires a valid privileged stack switch | SMOKE-REQUIRED | Stable kernel/user descriptors and 32-bit TSS; loaded TR, denied I/O, separate bounded supervisor guarded stack, all retained | Bad selectors, SS0/ESP0 bounds, user access to stack/TSS and unready TR refuse before entry; CPU transition captures correct stack | Host descriptor/bound tests + disassembly; QEMU STR, saved SS/ESP and handler stack range | No dependency on user stack for trusted entry; F1, F2 -> F3 |
| Double fault/NMI/async entry (`src/interrupt.rs:269`, fatal loop `src/interrupt.rs:533`) | CLI does not contain all exceptional entries; failed entry can triple-fault | SMOKE-REQUIRED | Review every reachable vector under pinned CPU feature model; bounded emergency fatal path and independent stack if required; no recovery claim | Bad transition/guard-overflow and double-fault injection must fail terminally, never PASS/reset | Host gate/state checks; QEMU diagnostic/no-reset proof and exact CPU config | Proven containment or STOP; F2, F3, F5 |
| Recoverable continuation after user fault (current #GP/#PF halt at `src/interrupt.rs:381`, `src/interrupt.rs:337`) | Ordinary Rust return cannot cross privilege boundary | POLICY-DEFERRABLE | Handler records result then nonreturning Ring-0 CLI/HLT; no IRET to faulting user or fabricated Rust continuation | Unexpected return/relaunch/shell marker after terminal event is FAIL | Host no-resume state; QEMU stable terminal state under bounded observation | Only terminal return to privilege, not recoverable launch return; F2, F5 |
| Processes, scheduling, general ELF/syscall ABI, SMP lifetime | Not reachable in dedicated one-payload boot fixture; implementation audit still required | LATER-PHASE | Do not expose these interfaces or enable APs in the smoke | Build/entry-path audit rejects accidental general loader/syscall/scheduler or multiple-CPU dependency | Host scope review; QEMU single-vCPU command identity | Separate future authorization; no prerequisite slice |

Case-list limitation: current `docs/PHASE11A2_OWNERSHIP_PLAN.md:45` has five
staged migrations and `:103` an unnumbered oracle-family list, not a numbered
15-case inventory. The requested historical 15-case correspondence is NOT
VERIFIED; this matrix must not be advertised as a 15/15 closure. Accepted null,
lease, pin, sharing-refusal, numeric-map and unmap work stays closed absent a
demonstrated regression. Preserve their gates, do not manufacture new slices.

### C. Teardown and CPU-lifetime decision

| Option | What it would require | Decision |
|---|---|---|
| A — no runtime teardown | Enforced one-shot retained resource set, same CR3, bounded preparation and terminal Ring-0 path | [PROPOSAL] minimum recommendation, conditional on F1–F5 evidence |
| B — inactive-map teardown | Prove withdrawal of every CPU/stack/interrupt/TSS/software reference, switch to independent continuation, invalidate then reclaim | Defer; no second map or continuation is needed for first entry |
| C — full lifetime-aware teardown | General address-space/alias/CPU lifetime protocol and reclamation failure handling | Defer; adds risk without enabling this terminal smoke |

Yes: one trusted payload only, no process creation/destruction. Prefer adding a
small USER arena to the **existing retained map**, not constructing/switching a
second CR3. Isolation is CPL3 versus supervisor pages, not process-versus-process
isolation. No user-accessible kernel aliases may be introduced.

[PROPOSAL] `unstarted -> preparing -> sealed -> entered -> terminal` is monotonic,
with any preparation failure also terminal. Latch before acquiring resources;
reject a second attempt even after OOM. The sealed owner retains all payload
leases and allocation backing, runtime pins, paging structures, kernel boot
stack, transition/emergency stacks, GDT/IDT/TSS and metadata. Expose no owner
references or release/permission mutation callbacks. No heap/map/frame guards
survive entry; preserve heap -> map -> frame ordering during preparation. IRQ
owners remain prohibited. Runtime pins prevent backing free, **not unmap**;
structure retention prevents inspected cleanup, **not all raw privileged misuse**.
Both must be paired with the no-mutation sealed owner and reachable-path audit.

After the payload's expected protection fault the CPU enters Ring 0, a dedicated
verified handler captures the result without locks/heap, emits one terminal
record, then CLI/HLT forever on retained privileged backing. Unexpected faults
also terminate but emit FAIL. A spinning payload times out externally and fails.
There is no ordinary Rust return, no resumed shell, no user retry and no runtime
cleanup. External controlled reset/termination ends the retained lifecycle; a
reset or triple fault before a verified terminal record is not successful cleanup.
Kernel resumption/recovery is **not approved by this policy**.

Retained capacity must be an admission bound, not an unmeasured leak claim:
F1 must declare a fixed manifest of code pages, user-stack pages, transition and
emergency-stack backing, new tables, descriptors and metadata; count existing
retained backing separately from incremental allocations. F4 must calculate
checked page/structure counts from actual selected ranges and report actual
frame identities/capacity deltas, including partially prepared failure states.
Every fallible stage has a fixed maximum and no retry loop or deferred queue.
Use at most that one manifest per boot; a capacity/range/conflict refusal is
terminal, not a reason to allocate elsewhere indefinitely. No byte/high-water
estimate is asserted here; emitted stack use plus exception headroom and
minimum-RAM measurements remain F3/F5 entry gates. Until these bounds exist,
pinning is a recommendation, not proof that the first smoke is safe.

### D. Exception and privilege-transition prerequisites

No authoritative Intel reference was already available in the inspected local
project references. A bounded tracked Intel/PDF filename search found none; this
does not prove no such reference exists elsewhere. No open-ended web search was
performed. Architectural assertions below remain [ASSUMPTION] — ARCHITECTURAL
VERIFICATION REQUIRED, not validated by matching source and host tests.

| Property | Implemented/source-inspected state | Required before smoke |
|---|---|---|
| Error/no-error frames | Classifier says only 8/10/11/12/13/14/17 (`src/memory/paging.rs:125`); IDT offset installs those (`src/interrupt.rs:267`). Packed error frame places error before EIP/CS/flags (`src/interrupt.rs:303`); opaque no-error frame is 48 bytes (`src/interrupt.rs:188`) | Verify architecture and emitted compiler ABI independently; replace/normalize unsafe contract rather than treating comments as proof |
| Newer exception vectors | 21, 29 and 30 all return false from classifier; generic handler calls 17–31 reserved (`src/interrupt.rs:514`) | [ASSUMPTION] #CP(21), #VC(29), #SX(30) may have error codes on supporting configurations. Pin exact QEMU CPU/features/vendor and either prove those vectors unreachable or provide correct entry shapes; no universal correctness claim from current seven-vector test |
| Origin | `fault_ring_from_saved_cs` masks `cs & 3` (`src/memory/paging.rs:139`); #GP prints it (`src/interrupt.rs:373`) | QEMU saved CS must match CPL3 descriptor and known payload PC; never use PF user bit alone or a user-supplied marker |
| CS/SS/ESP | Current error structs omit old SS/ESP (`src/interrupt.rs:291`, `src/interrupt.rs:303`) | [ASSUMPTION] same-level and privilege-changing frames differ; capture correct tail only after trusted origin validation, prove TSS stack switch and exact old user SS/ESP in QEMU |
| GPR preservation | Handlers use compiler `extern "x86-interrupt"` (`src/interrupt.rs:313`, `src/interrupt.rs:385`) | NOT VERIFIED from emitted code. Explicit save contract must precede Rust/formatting; terminal handler must preserve evidence, returning Ring-0 IRQs must restore interrupted GPRs |
| Segments | GDT boot reload sets kernel DS/ES/FS/SS/GS (`src/gdt.rs:174`); this is not interrupt-entry normalization | Save/capture incoming selectors, load trusted kernel segments before Rust memory access; restore on every returning path; QEMU hostile/zero user segment fixtures |
| Stack alignment | No explicit alignment shim established in inspected entry source | NOT VERIFIED; emitted i686 call alignment and real stack sentinels required, retain original CPU frame pointer across alignment |
| Direction flag | No explicit CLD established in inspected entry source | NOT VERIFIED; sanitize before Rust and prove with user STD fixture; preserve required flags on returning paths |
| IRET | Compiler-generated interrupt restoration not inspected; no CPL3 entry mechanism verified | [ASSUMPTION] reviewed IRETD frame for first entry includes EIP/CS/EFLAGS/user ESP/SS. Actual QEMU execution is mandatory; reject invalid selectors/flags/stack before entry. No user IRET-return after the terminal fault is needed |
| Double fault | Vector 8 is an error-handler offset on ordinary entry (`src/interrupt.rs:269`, macro at `src/interrupt.rs:427`) | No emergency-stack/task-gate guarantee verified. F2/F3 must establish fatal containment including entry failure, NMI and stack exhaustion, or stop |
| TSS/SS0/ESP0 | Inspected installed GDT has null/code/data only (`src/gdt.rs:130`, `src/gdt.rs:151`); boot descriptors leak for retention (`src/gdt.rs:155`) | Static retained 32-bit TSS/descriptor and loaded TR, supervisor stack/guard, I/O denial; system-wide absence of alternate TSS code is NOT VERIFIED by a text search |
| Kernel continuation | Current PF/GP handlers halt, no recovery (`src/interrupt.rs:337`, `src/interrupt.rs:381`) | Terminal fault path only. Recoverable return requires a later nonlocal assembly/compiler ABI and no skipped Rust owners; excluded here |

Existing host oracle declarations `phase11a2_error_code_vectors_are_classified`
(`src/memory/phase11a2_abi_tests.rs:7`) and
`phase11a2_fault_origin_reads_saved_cs_ring`
(`src/memory/phase11a2_abi_tests.rs:43`) verify the chosen model only. Historical
Ring-0 faults cannot prove privilege-changing SS/ESP, entry alignment, GPR/segment
restoration, TSS switching, IRETD, CPL3 permission denial or double-fault isolation.
F2 must resolve the architectural assumptions with a pinned authoritative reference
and CPU model before entry approval; unavailable reference means STOP, not waiver.

### E. First Ring-3 smoke definition

[PROPOSAL] dedicated test-only controlled boot path, production default unchanged;
one fixed reviewed i386 instruction blob with entry offset/length pinned to its
fixture identity. No ELF, filesystem loader, scheduler, production syscall ABI or
new process abstraction. User code never writes serial directly.

- **Address range:** candidate arena `0x40000000..0x40400000`, inherited design
  proposal only, not a current mapping. Reject the whole launch if actual active
  map/reservations conflict; do not silently relocate or elevate an identity PDE.
  Code starts at arena base; fixed manifest places a user stack below arena end
  with a nonpresent page immediately below it. Final stack page count/top and
  transition/emergency stack ranges must be explicit in F1/F3, not guessed here.
- **Permissions:** code USER/present/read-only; user stack USER/present/writable;
  all other arena leaves absent. Audit effective PDE **and** PTE rights. All
  identity aliases, kernel/heap/MMIO/boot metadata, tables, GDT/IDT/TSS and privileged
  stacks stay supervisor. Any new USER PDE may cover only the audited arena;
  unused PTEs remain absent. Zero every new user frame before copying payload;
  never expose allocator residue. Non-PAE NX is unavailable in current permission
  representation (`src/memory/paging.rs:596`); no NX or hostile W^X claim.
- **Entry environment:** same CR3; one vCPU; no AP or concurrent mutation.
  Proposed kernel CS/DS `0x08/0x10`, user CS/DS `0x1b/0x23`, TSS `0x28` require
  descriptor/type/limit verification. TSS SS0/ESP0 point to retained supervisor
  guarded transition stack; I/O permissions deny user I/O. Sanitize IOPL=0,
  VM/NT/TF/DF cleared, reserved flags canonical, IF=0 deliberately for this bounded
  payload. Mask external IRQs for smoke; NMI/DF remain explicit obligations.
  Validate CR0/CR4 paging mode and WP, descriptors, TR, all mappings/stacks and
  CPU feature contract before the nonreturning assembly IRETD launch.
- **Observable payload:** read CS into a designated saved register, perform one
  known user-stack store/load with a fixed sentinel, then attempt a write to a
  dedicated **supervisor-only sentinel page** at a known virtual address, not
  arbitrary live kernel data. Its expected #PF is the completion event. Capture
  payload PC, saved CS/SS/ESP, flags, sentinel registers, CR2/error, current CR3 and
  handler-stack bounds before clobbering them. Verify the supervisor sentinel is
  unchanged. Successful write or ordinary RET is never a success path.
- **Output:** kernel emits `R3SMOKE PREPARED` with fixture/source/CPU/resource
  identity. Only after validating the expected saved frame, exact faulting opcode
  PC/CR2, CPL3 selectors, flags and sentinel does it emit
  `R3SMOKE PASS cpl=3 event=supervisor-write-denied terminal=halt` followed by
  `R3SMOKE TERMINAL`. Any other exception/origin/state emits `R3SMOKE FAIL` and
  terminal halt; malformed entry must never be reclassified as user completion.
  A host timeout, triple-fault/reset, missing record, extra PASS, changed sentinel,
  unexpected mapping/resource count or later shell/launch marker is FAIL.
- **Lifecycle:** terminal Ring-0 CLI/HLT on retained privileged stack, all acquired
  memory remains held until external termination/reboot. No runtime cleanup and
  no in-guest reboot dependency. Host verifies halt/no reset under bounded
  observation and confirms owned QEMU termination separately.
- **Exact evidence gate:** identical pinned fixture and input manifest on local
  QEMU at 128/512 MiB, ELF and GRUB ISO paths, fresh boot per invocation. Require
  exactly one validated PASS/TERMINAL pair and matching prepared identity per
  positive invocation; preserve raw serial and CPU/handler captures. Separate
  fresh-boot negative variants must demonstrate user-code write denial, user
  guard denial, invalid-entry refusal, wrong-origin failure, STD/segment handling
  and DF containment. These variants are future isolation prerequisites, not
  additional user processes in the positive smoke. Host tests cannot replace them.

Three distinct outcomes: **first CPL3 entry** is established by the CPU-captured
origin/stack and executed user sentinel; **terminal user-to-kernel fault entry**
establishes isolation but not recoverable return; **recoverable Ring-0 continuation**
and **general process execution** remain later work. Phase 11 first-smoke exit is
F1–F5 reviewed and accepted with these evidence gates; it is not full Phase 11
completion or general B19 closure. No smoke has executed at this checkpoint.

### F. Ordered implementation path — five bounded slices

All slices are [PROPOSAL], require separate implementation authorization and
independent source/ABI review before their production checkpoint is accepted.
No code changes are authorized by this document. Preserve the inherited 65 gate
identities/multiplicities; discover actual test declarations before adding exact
nonshrinking prerequisite families. Never guess a future aggregate gate total.
No canonical acceptance in this docs-only session. Future checkpoints follow the
ownership plan's frozen-source official acceptance rule
(`docs/PHASE11A2_OWNERSHIP_PLAN.md:103`); focused evidence is not a substitute.
Do not add a separate acceptance cycle solely for optional deferred maintenance.

| Slice / prerequisite | Exact problem and smallest intended scope | RED -> expected GREEN | Host verification | QEMU verification | Independent review; acceptance identity/gate; stop condition |
|---|---|---|---|---|---|
| **F1 — bounded one-shot retained owner**; accepted baseline | Private smoke state/resource manifest near memory owner; enumerate all reachable privileged mutation/release paths. Latch first attempt, cap every resource/failure path, seal no-unmap/no-free/no-reset/no-second-launch. No general CPU-pin ledger | Forbidden operations after seal, retry after partial OOM and over-cap acquisition fail against baseline -> exact nonmutating refusals and fixed retained inventory | Exact state transitions, each acquisition failure, allocator/structure/payload accounting and emitted static/stack budget; preserve accepted authority families | Ring-0 fixture confirms same CR3, capped prepare failure, no retry/cleanup; CPL3 disabled | Review lifetime/bypass audit. Proposed exact lifecycle family inside inherited gate set plus necessary new gate; stop if any mutation/reclaim path escapes seal or bound unknown |
| **F2 — verified exception entry/fatal contract**; F1 resource policy, pinned architectural reference/CPU model | `interrupt.rs` plus minimal assembly entry and frame/decode tests; normalize error/no-error, save GPRs/selectors, CLD, align calls, origin validation, kernel fatal/DF/NMI containment contract. Not process continuation | Known CPU #GP/#PF/no-error frames and preservation controls expose wrong decode/ABI -> exact captured frame and terminal diagnostics; returning Ring-0 IRQ preservation proved | Host layout/offset/origin/error-vector cases; emitted target disassembly and all returning paths; feature-specific 21/29/30 contract | Real Ring-0 error/no-error faults, GPR/DF/segment/alignment checks, fatal failure controls; later CPL3-tail proof reserved for F5 | Independent architectural/ABI review including emergency entry dependency. Preserve existing fault gates; extend exact fixtures without weakening fatal expectations. Stop on missing architecture authority, ambiguous compiler ABI or uncontained vector; no USER |
| **F3 — static GDT/TSS and guarded privileged stacks**; F1, F2 entry contract | `gdt.rs`, minimal stable TSS/descriptor/TR setup and fixed stack backing; emergency DF mechanism only if F2 requires. No task scheduling or general context switch | Invalid descriptor/TR/SS0/ESP0/stack bounds or resource failure -> refused launch, valid retained descriptors and stack identity | Wire descriptor/TSS layout, selectors/I/O denial, lifetime/range guards; target stack-frame/headroom evidence and bounded capacity | Read TR/descriptor state; Ring-0 guard and emergency-entry fault fixtures; real CPL3 stack switch deferred explicitly to F5 | Independent TSS/DF/stack review; exact descriptor/stack prerequisite family and guest identities. Stop if stack budget/DF fallback unresolved or claimed stack switch lacks F5 proof |
| **F4 — narrow owned USER arena transaction**; F1; F2/F3 before arming entry | Memory-private arena builder on existing PageMap; checked owned frame leases, zero/copy before USER publication, USER-only PDE region, supervisor aliases, guards, seal. Keep ordinary `map_owned` supervisor refusal intact | All gap-matrix invalid authorities/conflicts/stage failures and permission-elevation controls -> exact refusal plus fixed rollback-before-publication or bounded terminal retention; success exact user leaf set | PDE/PTE effective rights, overflow/conflict/zeroing/table accessibility, no lock allocation/destruction, complete resource manifest and no reachable bypass | Ring-0 audit of active tables/CR3 and supervisor aliases at both RAM sizes; CPU CPL3 denial deferred to F5 | Independent ownership/permission/transaction review; preserve all accepted authority identities, exact arena refusal family. Stop if kernel PDE elevation, residual user bytes, unbounded failure retention or ordinary API weakening required |
| **F5 — terminal first CPL3 smoke and isolation proof**; F1–F4 GREEN/reviewed, no unresolved hardware assumption | Minimal nonreturning IRETD shim, fixed payload/negative variants, trusted terminal handler and focused local harness; no syscall/ELF/shell continuation | Disabled/malformed entry, wrong-origin/PC/fault markers and deliberate missing denial evidence -> harness FAIL; valid E fixture -> exactly validated terminal PASS | Frame construction/selector/flags bounds, harness missing/extra/substituted/timeout/reset controls; emitted entry/handler assembly; inherited suites | E's ELF/ISO x 128/512 positive matrix plus fresh-boot negative CPU fixtures; actual CPL, TSS SS/ESP, denied accesses, terminal state and owned cleanup | Independent final source+guest identity readback. Add exact mandatory terminal/isolation gate(s) while preserving inherited multiset, frozen inputs and acceptance lock. Stop on any missing CPU evidence, review blocker or reset; do not add recovery to rescue smoke |

The five-slice bound is conditional on closing F2/F3 as bounded entry work. If
authoritative ABI review shows the emergency-stack/DF path or ownership seal
requires more than six independently implementable slices, report that blocker
and revise the estimate; do not hide an incompatible context-switch subsystem
inside F2/F3. Do not split accepted FrameLease/pin/VPZ/map/unmap work again.
Stop splitting B19 once every first-smoke prerequisite is enforced or safely
excluded by the reviewed policy. General published teardown, per-map transfer,
shared/COW ownership, repeated launch, shell recovery, ELF/syscalls and scheduling
remain deferred, not prerequisites to satisfy a superficial 100% checklist.
