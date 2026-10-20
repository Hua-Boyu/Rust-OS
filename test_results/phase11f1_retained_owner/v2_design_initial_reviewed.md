# F1 v2 — finite one-shot retention and terminal Ring-0 invocation

STATUS: PROPOSED FOR COMBINED INDEPENDENT REVIEW. No production changes yet.
Source checkpoint: actual maintenance/phase10 HEAD 649aaf1dccd2f18091d0d2f0f81661e11d005d97; raw inputs in v2_recovery.json and the review's own independently computed manifest. This is not implementation approval.

## 1. Authority, scope and interpretation

Current-session supported clarification returned SOLE_WRITER=YES, CEILING=YES, CONTINUE=YES. CEILING approves only 12 incremental frames / 49,152 bytes as policy, not capacity, availability, stack sufficiency or CPU readiness. The operator conditionally authorizes implementation only after the combined independent review approves with zero blockers and source remains owned/stable.

F1 does not acquire/install future stacks, tables, descriptors or USER leaves. It establishes a finite admission contract, acquires at most two ordinary frames, freezes the cooperating kernel's memory mutation APIs and ends in Ring 0. No F2–F5, TSS, IRET, CPL3, process, general teardown or new CR3-switch implementation. Supervisor raw pointers/asm in arbitrary malicious Ring 0, DMA/firmware and SMP are outside this cooperative single-vCPU contract. New trusted mutation call paths must be reviewed, not granted implicit authority.

Existing v1 smoke mutex, latch and whole-domain freeze are PROPOSALS ONLY. Source has FRAME_ALLOC/PAGE_MAP SpinMutex owners and PAGING_ENABLED AtomicBool, but no F1 owner/latch/seal. Do not confuse PageMap.retained (structure lifetime) with mutation sealing. Do not change retain_for_publication to freeze ordinary boot behavior.

## 2. Concrete finite inventory

A fixed six-class immutable policy manifest; no Vec, dynamic bitmap, queue, dynamic capture strings or allocator redesign. Frame unit is existing frame::FRAME_SIZE = 4096. Total class maxima checked to equal 12; F1 successful ordinary acquisitions checked to be <=2 and a subset of 12, not additional capacity.

| Class | Policy maximum incremental frames | F1 actual state/authority |
|---|---:|---|
| Fixed future payload | 1 | One allocate_owned; immediately move lease into payload: Option<FrameLease> |
| Dedicated supervisor sentinel | 1 | One allocate_owned; immediately move lease into sentinel: Option<FrameLease> |
| Future user stack | 1 | NotAcquired; no lease/mapping/pointer in F1 |
| Future transition stack | 4 | NotAcquired; no lease/mapping/pointer in F1 |
| Future emergency backing, total | 4 | NotAcquired; no lease/mapping/pointer in F1 |
| Future arena table | 1 | NotAcquired; no table allocation in F1 |
| New directory | 0 | Existing PageMap owns its raw allocated structure directory, structure-pinned and retained; record directory/domain scalars, do not duplicate release authority |
| Existing tables/map backing | 0 incremental | Existing PageMap.tables, boot_pins and payload_bitmap remain in published PAGE_MAP; record table count/window/mapped count, not a second inventory owner |
| Bootstrap aliases | 0 owned | Borrowed supervisor identity mappings, not newly owned frames; validate each acquired complete page; no payload writes or new aliases |
| Existing boot stack | 0 incremental | src/boot.s retains 16 KiB kernel-BSS storage; not reusable transition/emergency capacity |
| Existing GDT/IDT/boot/heap/frame ledger | 0 incremental | Retain established supervisor ownership/backing; no replacement/destruction in terminal invocation |
| Future descriptor/TSS backing | 0 F1; <=4096 static bytes policy | NotInstalled; one future fixed retained set, inclusive of any emergency descriptors/context bytes. This is a reject-on-overflow storage envelope, NOT a selected TSS wire layout or mechanism. F2/F3 must reject/re-review if incompatible. No heap descriptor allocation may be added under this policy |
| F1 owner/latch/manifest/diagnostics | <=4096 total static bytes policy | Enumerated below; actual target size MUST be measured. No additional retained dynamic metadata |
| Future virtual guards | 0 physical | Exactly one lower absent-page reservation for each of user/transition/emergency classes; no present guard or range installed in F1. If later mechanism needs more contexts/guards it requires review |

Future source revisions may extend Preparing on a fresh boot only. User arena policy remains 0x40000000..0x40400000; payload candidate base, one-page user stack candidate 0x403ff000..0x40400000, lower guard 0x403fe000..0x403ff000. Privileged ranges remain NotSelected/NotAcquired in F1 and cannot become Ready. Their later selection must use already retained tables outside the arena and prove guards/alignment/aliases; another required table rejects the one-new-table policy. No F1 claim of feasible complete future layout or stack adequacy. Static incremental envelope <=8192 bytes (4096 owner family + 4096 future descriptors), separate from 49,152 frame bytes. These metadata byte envelopes are proposed review policy, not additional operator-approved physical frame acquisitions or measurements.

### Exact proposed F1 storage shape

There is no existing duplicate retained-owner type to reuse. Add ONE private const-initialized owner in memory's authority subtree using existing SpinMutex, not a parallel allocator or PageMap. Fields:
- payload: Option<FrameLease>, sentinel: Option<FrameLease> (only actual owning slots);
- directory: u64, allocator_domain: u32, window_end: u64;
- table_count: usize, mapped_count: usize;
- capacity_before and capacity_after: each three usize scalars (free, allocated, reserved);
- future_ranges: [[u32; 4]; 3] (base/top/lower-guard/status), all zero/NotSelected in F1;
- capture: [u32; 16], fixed fields: outcome, successful acquisitions, directory low32, domain, CR0, CR3, CR4, CS, payload addr, sentinel addr, free-before, allocated-before, free-after, allocated-after, refusal mask, terminal state.
One private AtomicU8 state lives beside owner. Immutable class manifest uses six fixed records of two u8 counts (policy max, F1 max); roles defined by fixed index, no String. Readiness is never true in F1 (no readiness transition/API). Capture is not an architecture exception frame and contains no invented hardware TSS fields. Assert target size_of owner+mutex+atomic+manifest <=4096 at compile time; obtain actual symbol/type/section evidence, not a guessed byte count. At most scalar capture is copied to the stack; no by-value FrameAllocator/PageMap or owner construction on boot stack.

## 3. State and one attempt

Proposed singleton state values: Dormant=0, Preparing=1, Sealed=2, Terminal=3. No reset/unseal API, no exported owner, constructor, callbacks, guards or leases. Production's only invocation returns !. Admission performs compare_exchange(Dormant, Preparing, AcqRel, Acquire) BEFORE taking smoke/PAGE_MAP/FRAME_ALLOC guards or fallible work. Failure refuses admission without changing any resource/diagnostic state or reacquiring smoke owner. It does not set Terminal out from under an in-progress owner. Production nonreentry is a prerequisite; tests may call the scalar admission core again to verify refusal.

Every valid first attempt ends Sealed->Terminal on success or Preparing->Terminal on failure. Both Sealed and Terminal mean GLOBAL MEMORY MUTATION DENIED. Dormant/Preparing preserve normal operations within the serialization contract. No externally callable prepare-returning-Result production API; internal scalar result is handled inside the nonreturning wrapper. A failed preflight may have zero acquisitions and still permanently closes mutation authority and consumes the attempt. No cleanup/rollback claim: bounded terminal retention of all acquired resources is the sole failure policy.

## 4. Joint seal and lock proof

Only dedicated main-context invocation may acquire the new smoke owner. IRQ/NMI/fatal paths do not acquire smoke/map/frame/heap owners or invoke preparation. Existing SpinMutex is Acquire/Release, nonrecursive and not IRQ-disabling (src/utils/mutex.rs:35-66). Before admission invocation executes CLI, never restores IF or returns. Controlled invocation is placed after existing IDT and successful enable_paging in kernel_main, before PS2/timer/storage/shell work (src/main.rs:201-211). One vCPU; no AP startup/concurrent producer. Existing heap->PAGE_MAP->FRAME_ALLOC order remains; the invocation takes smoke->PAGE_MAP->FRAME_ALLOC, never heap. No existing path takes smoke. No allocation, formatting, callback, Vec destruction or heap guard is permitted under these guards.

Hold PAGE_MAP then FRAME_ALLOC continuously across acquisition, validation, capture and final state publication, inside smoke owner. Store each returned FrameLease directly in its fixed static slot before any alias check or next fallible operation. Verify actual paging state and software identity before first allocation; validate complete-frame alias and live domain/id/ordinary role after each acquisition. Alias failure retains that lease and stops, never searches another candidate. Check distinct frames and no runtime/structure pins. Existing inherited supervisor alias is not a runtime payload mapping/pin.

Commit writes fixed owner fields/capture first, then stores Sealed with Release while both existing owners are held. No per-map/per-allocator seals are needed: a single global irreversible state gates every inventoried mutation, including other instances/alternate maps. Every mutation gate loads state Acquire and refuses >=Sealed. This latch orders publication/refusal, NOT general lockless access to non-atomic owner fields; readers needing owner fields still take the smoke mutex. No raw unsynchronized metadata reads. PAGE_MAP/FRAME_ALLOC locks serialize old operations before publication; CLI + one CPU + no memory-owner IRQ/fatal reentry exclude concurrent CR3/core/raw pin mutation. Atomic Boolean alone would NOT establish this. General concurrent/SMP callers would invalidate the design and require STOP, not stronger ordering as a substitute.

On failure write bounded capture, publish Terminal with Release while the same available owner guards are held, retain all leases and return only a scalar to wrapper scope; release frame, map, smoke in reverse order. Missing PAGE_MAP still closes the global gate under the owner sequence with zero acquisitions; failed hardware identity never labels successful Sealed. On success release the same guards, then publish Terminal before terminal output. No new mutation window exists because Sealed already refuses. Leaves only consult the atomic; NEVER reacquire smoke owner.

### Bounded mutation guard matrix

Gate G = shared acquire-load state < Sealed. Refusal is before diagnostics as well as ownership/backing changes: false/None/static Err, unchanged counters, IDs, bitmaps, pin sets and tables. Existing pre-F1 invalid-input diagnostic behavior stays unchanged. All production transaction entry points AND raw common cores below check G. Default ordinary operations must not accidentally seal.

| Boundary | Actual file/function | Affected resource/precondition | Guard before mutation | Existing lock | Reentry | Failure and oracle |
|---|---|---|---|---|---|---|
| Reset | frame.rs:201 init, :323 init_with_reservations | domain/ledger/inventory; G + existing live/reset checks | first instruction before issue_domain, malformed-reservation reset, dbg, bitmap/stat writes | FRAME_ALLOC in global calls; exclusive &mut in local tests | none | false; exact full allocator snapshot incl issuer/reset flags |
| Ordinary allocation | frame.rs:378 allocate_stamped; :366 issue_allocation_id | free/ever/id/counters; G | common core before scan/ID issuance; private ID helper guarded too | FRAME_ALLOC | none | None; next_id, identities/counters unchanged; raw and owned wrappers |
| Release | frame.rs:445 release_by_address, :508 release_frame, :500 free | ordinary/growth backing; G + existing authority | first line of release_frame before reject counters AND common core | FRAME_ALLOC | none | false; retain legitimate lease; test-only duplicate consumed by negative oracle |
| Growth claim | frame.rs:534 claim_growth_frame; mod.rs:302 heap_grow_frame | growth reservation/map; G before complete claim transaction | wrapper before claim and common claim first line | HEAP->PAGE_MAP->FRAME_ALLOC | heap cannot enter smoke | None; exact claimed/reserved/free/PTE snapshot; no rollback on denied claim |
| Pins | frame.rs:608 set_runtime_pin, :618 set_structure_pin | both set and clear; G and enclosing transaction preflight | entry before bitmap write; change to bool success/refusal, preserve existing address preconditions | FRAME_ALLOC | none | false; every enclosing production transaction checks G before FIRST mutation, so pin refusal cannot leave preceding backing changes |
| Map | paging.rs:310 map_owned, :326 map_growth_claim, :362 map_authorized; test numeric :340 | directory/PTE/PDE/registry/pins; G + original authority | wrappers before reject counters; common core before validation/counters/table allocate/zero/pin/PTE | PAGE_MAP->FRAME_ALLOC | no callbacks/heap in production | false; full table/pin/stat snapshot; foreign and same-domain alternate map cases |
| Unmap | paging.rs:484 unmap_owned, :513 unmap_authorized; test numeric :501 | PTE/TLB/payload pin; G | wrappers/core first line before diagnostics and PTE clear | PAGE_MAP->FRAME_ALLOC | none | false; retained owned mapping unchanged including exact lease/slot |
| Unpublished cleanup | paging.rs:182 release_unpublished_frames | structure pins/inventory/revocation; G + existing complete role preflight | before role changes, free, metadata clear | PAGE_MAP->FRAME_ALLOC | no backing drop | false; old/unpublished alternate map unchanged |
| Bootstrap construction | paging.rs:745 build_identity_map_with_backing_in_place | directory/table zero/write/allocation/pins; G | entry before any allocation/zeroing; host adapters check before backing allocation too | PAGE_MAP->FRAME_ALLOC; backing reserved beforehand | host mirror separately allocates | None; supplied backing stays owned and unchanged, no pin or free changes |
| Publish boot map | mod.rs:165 prepare; paging.rs:224 retain_for_publication | map owner/retained flag/backing; G | prepare entry before dbg/reserve; recheck under map/frame; retain entry before metadata | PAGE_MAP, then FRAME_ALLOC as existing | no smoke lock | static Err/false; no reserve/owner replacement after freeze |
| CR3/CR0 write | paging.rs:691 flush_tlb, :898 enable_paging; mod.rs:245 enable_paging | actual CR3/CR0, retained/enabled stats, PAGING_ENABLED; G | every helper entry before retain, asm or enabled flag. wrapper bool succeeds only if helper did | PAGE_MAP in public wrapper; internal exclusive &mut + single-CPU contract | none | false, actual registers/model and metadata unchanged even for fresh alternate map |
| Raw table helpers | paging.rs:661 write_entry, :841 zero_table, :681 invalidate_page | physical backing/TLB | keep private; reachable transaction gates dominate all calls; optionally defensive gate only if complete caller preflight still exists | enclosing same map/frame transaction | no callbacks | not a stand-alone authorization API; test guarded transaction on valid input proves no writes |
| Heap allocator | allocator.rs:240-283 alloc_inner, :308-317 GlobalAlloc | existing heap mutation/growth | growth path gates above; sealed invocation never calls allocator/deallocator | HEAP->PAGE_MAP->FRAME_ALLOC | no smoke callback | normal already-mapped heap is NOT globally immutable; terminal path cannot resume it |

Pin bool results must not be ignored as an error recovery strategy. Production callers preflight G before *any* table/backing/accounting change and cannot see G change mid-transaction under the stated serialization. Pin commit refusal is therefore impossible after that preflight, except violated invariants; do not continue publication after a false result. Before changing signatures inspect all callers; if an actually reachable mid-transaction refusal requires rollback/new authority, return to review, do not improvise. Invalid-address direct pin calls are not admitted; add checked frame-index refusal to avoid panic if tests use bad inputs.

No whole-value replacement of private FRAME_ALLOC/PAGE_MAP/smoke owner after publication. No exported mutable references. Test-only local fixtures/duplicates do not become production reset/bypass mechanisms.

## 5. Hardware CR3 and alternate-map exclusion

The software directory/domain and the two enabled booleans are observations, not CPU state. Existing flush_tlb actually writes PageMap.directory into CR3, not a read/write of whatever CR3 is currently active; it can switch maps. Existing enable_paging writes CR3, CR0.PG and CR0.WP. Both require global exclusion, even for an unsealed alternative PageMap with a different domain. Reconnaissance found these two real CR3 writer sites; repeat search before implementation review.

Add a private read-only architecture observation of CR0, CR3, CR4 and CS (inline asm using actual i686 conventions). This is NOT a CR3 switch API. Read after CLI, under retained map/frame locks. Require CR0.PG=1, CR0.WP=1, CR4.PAE=0, CR4.PSE=0 for the implemented non-PAE 4 KiB model; require CR3 page-directory base exactly equals the live software directory, expected aligned low control bits (PWT/PCD zero under current enable path), current CS ring=0, software PAGING_ENABLED and pm.stats.enabled true, allocator domain equals map domain and structures retained. Read immediately before final seal again; mismatch terminally refuses while retaining acquired slots. No hardware claim from cfg(test) stub (existing paging_enabled returns false on host).

Host oracle uses an explicit cfg(test)-only CPU-state record and CR3 writer observation counter behind the same guarded writer entry points; reject malformed paging/identity modes and alternate-map enable/reload, require zero additional modeled writes after Sealed/Terminal. No fake production hardware module, no reset of production singleton. Host proof is model-only.

Guest must read actual registers before attempt, immediately pre-seal and post-refusal; verify identical CR3, expected CR0/CR4/CPL, retained directory/pins and <=2 frame delta. An alternate map for negative activation must be prebuilt before invoking F1 under exclusively owned guest fixture storage, NEVER built after seal. Its additional fixture structures are counted separately, not hidden in F1's two acquisitions. Prefer a test-only revoked or different-directory descriptor without actual activation; call real guarded activation/reload helper after seal and verify zero CPU register change. No new switch implementation. If constructing an alternate valid map cannot be safely rooted through existing fixture pattern without more production authority, stop/review rather than expose a map handle.

## 6. Explicit nonreturning terminal contract

Proposed production-reachable memory::run_retained_owner() -> ! has no return value/continuation callback. Default boot does not call it; a disposable local Ring-0 fixture injects a call at the inspected main.rs post-paging/pre-PS2 anchor. Its body is production policy, not a host mirror. No Cargo feature enables F2–F5 or changes default ordinary boot. Fixture must pin staged sources and show the only fixture entry change; extend existing scripts/boot_metadata_test.py owned-stage pattern, not copy a historical relocated host RED.

Exact operation: CLI -> first admission -> lock/acquire/validate -> Sealed or failure Terminal -> release ALL guards -> Sealed->Terminal if needed -> bounded lockfree diagnostic -> `loop { asm!("cli", "hlt", options(nomem, nostack)); }`. CLI repeats after wake; no STI, RET, shell, reboot, retry, cleanup, allocator call or backing drop. No guard lives in divergent halt scope. Nonreturning type is required at public wrapper and halt leaf; internal scalar preparation can return only to this wrapper after unlocking. Failures retain acquired slots and cannot escape to ordinary caller. IRQs were disabled before acquisition; CLI does not claim NMI/DF containment or future CPL3 entry correctness. Existing IDT fatal behavior remains, faults/reset before validated F1 terminal marker are test FAIL.

Use io::serial::puts/putc directly with static text and a fixed digit loop for scalars (serial.rs:28-43 bounds each byte to 100000 polling iterations). No allocation, format!, heap-backed string, VGA/port manager lock, or unbounded capture. At most 16 u32 scalars rendered as fixed 8-hex digits, with a fixed <512-byte terminal record bound; no strings from unbounded inputs. A UART timeout may omit bytes and causes harness FAIL, never kernel success inferred from missing output.

CURRENT fixture recognition: scripts/paging_test.py:43 expects `page fault:` for fault fixtures or `rosti>` for normal boot; :51-69 requires existing boot/paging conditions; :74-76 kills and waits owned QEMU. There is NO current F1 marker or debug-exit convention. This design PROPOSES `F1OWNER PASS cpl=0 terminal=halt` and `F1OWNER TERMINAL`, or `F1OWNER FAIL reason=<fixed-code> terminal=halt` and terminal marker. Acceptance does not yet recognize them. Extend the existing owned-stage guest machinery with an explicit F1 scenario/parser and fail-closed controls; do not pass F1 by normal boot marker or invent existing runner support. QEMU remains alive/halted until harness captures bounded observation and explicitly terminates/waits its own process; guest emits no isa-debug-exit. Host runner success exit0 requires validated record, QMP CPU-state/halt observation, no reset/triple fault/post-terminal shell/retry, and cleanup; timeout/process exit without record is FAIL.

## 7. Failure-stage policy

| Stage | Resources and action |
|---|---|
| Before first acquisition | Zero leases. Attempt permanently consumed. Missing map/hardware/mode prerequisite -> Terminal mutation gate, unlock, FAIL/halt |
| First allocation fails | Zero leases; no second allocate call, no search/retry; Terminal and halt |
| First acquisition/alias or second-allocation failure | payload slot retains exact current domain/id frame; sentinel None; no rollback/release; Terminal and halt |
| Second acquired/later validation failure | Both fixed slots populated before check; <=2 frames, exact identities retained; Terminal and halt |
| Fully acquired unsealed | Never returns or silently publishes; final identity validation -> either Sealed or Terminal, same locks continuously held |
| Sealed | Deny map/unmap/init/allocation/free/pin/growth/publication/CR3 helpers, no diagnostic-accounting mutation in refusal, no unseal |
| Terminal | Same mutation denial, no fresh owner/admission/reset/retry/cleanup, nonreturning halt |
| Future CPU publication | Deferred. No Ready/Entered state or CPL3 path in F1; later source version must acquire and validate everything within one pre-seal Preparing interval on a fresh boot |

## 8. Live RED first and candidate proof obligations

The FIRST production-affecting source diff is a new cfg(test) runtime oracle in live paging.rs descendant test module, rooted by existing tests_kernel inclusion of real memory source. It uses the inspected generation_ownership_tests.rs fixture and legitimate leases. Until F1 exists, a clearly labeled test-only adapter calls existing retain_for_publication only; the assertion tests denied release of an unpublished ordinary lease (use duplicate_for_test for attempted consumed token) and exact live identity/counters. Baseline must successfully compile and run EXACTLY ONE test, failing explicit `F1 missing joint seal` assertion. No fake approved production state. Record before/after scalars and source hashes. After runtime RED, replace ONLY test adapter with real reviewed private seal/preparation path; keep denial and exact-state assertions. retain-only cannot count as candidate seal. Preserve the actual RED raw bytes/hashes and expected Cargo status separately from GREEN. Never rerun historical relocated fixture.

Proposed exact module family `retained_owner_tests` (final list must be discovered from declarations and --list, not assumed by runner):
- one_shot_admission_refuses_second_attempt;
- partial_first_acquisition_failure_retains_zero;
- partial_second_acquisition_failure_retains_exact_payload;
- alias_refusal_retains_acquired_identity;
- sealed_owned_release_preserves_exact_inventory;
- sealed_owned_unmap_preserves_exact_mapping;
- sealed_mutation_matrix_preserves_all_guards (valid inputs exercise raw/owned allocation/release/reset/growth/pins/map/unmap/build/cleanup/publication);
- alternate_cr3_activation_and_reload_refused;
- terminal_refuses_preparation_and_mutations;
- ordinary_unsealed_mapping_and_release_preserved.
Additional final-mode mismatch and two-acquisition identity tests required if not covered by the above parameter cases. No security ignore. A global singleton cannot be reset for other tests: each irreversible case must self-spawn its exact test identity in a fresh libtest process, using existing independently rooted child patterns, with exact-one summary/status checks. Parent full-suite process remains Dormant. B26 includes real source and must preserve detector behavior; instrument smoke lock too for forbidden allocations if needed without changing test counts silently.

Freeze/refusal snapshots include every allocator statistic and exact lease validity, IDs/next-ID/domain via narrow test descendants, free/covered/ever/growth/runtime/structure bitmaps; PageMap directory/domain/retained/window/tables/payload/boot pins and all PDE/PTE software entries/statistics. Host MIRROR is per-thread; never use it for hardware evidence. Hardware A/D bits are allowed CPU effects, not a software write failure. Guest compare structural/permission bits with this distinction.

Guest 128/512 fresh boots: success, deterministic first-denial, second-denial and identity/alias refusal scenarios with fixed test-only denial selectors before actual acquisition calls (zero denial effect in production). Assert exact 0/1/2 deltas and identities, one-shot refusal, mutation gate, CR3 stability, CPL0, exact bounded terminal marker, no resumed shell/reset, actual halted CPU and owned cleanup. Positive F1 owner itself maps nothing; a preexisting runtime mapping/alternate-map probe fixture must remain test-only and separately accounted. No claim that normal paging_test alone proves F1. Any required unsafe fixture authority not covered by this design returns to review.

## 9. Verification and evidence gates

Native terminal is Git Bash 5.3.15 with Windows cargo host x86_64-pc-windows-msvc. execute_code subprocess bash unexpectedly resolves WSL; do NOT use it for Cargo. Host child cwd C:/Users/iamsv, explicit tests_kernel/Cargo.toml or actual B26 manifest. Existing run_step.py interface verified: name cwd expected_exit command...; pass argv tokens, not one shell command. Use unique F1-root names, expected runtime RED actual101 only after assertion evidence, GREEN0; compare declarations and --list exact identities, ignored policy and actual >=1 summary. Compilation failure is never runtime RED.

After GREEN: predecessor exact authority families, full host and B26 serial/default-parallel, production fmt/build and ELF validation, focused Ring-0 guests at both RAM sizes, fixed inventory/counter proof, actual .data/.bss/allocated-section sum/span delta bound to baseline and candidate ELF hashes. Baseline_memory.json is historical emitted evidence only; rebuild baseline before source changes if needed and pin build inputs/toolchain. Inspect actual target symbol sizes and preparation/callees assembly frames. Runtime aggregate stack high-water remains UNKNOWN unless directly measured; prologue size is not high-water and 12 frames is not stack proof. No claim of minimum-RAM safety from arithmetic alone.

ONE independent candidate read-only source review after stable verification, complete raw+Git-normalized hash-pinned verdict, no source changes afterward. Extend existing phase6_verify.py identity gate machinery only; recover inherited gate multiset from actual accepted manifest, preserve all identities, add narrowly scoped exact F1 family/guest gate(s) as needed with missing/zero/duplicate/impostor/substitution/incomplete/extra negative controls. Do not hardcode a new total or introduce a second verification framework.

Freeze canonical inputs then ONE canonical acceptance via supported terminal background=true notify=true; inspect real CLI first, no polls/second build/QEMU/source edits or unlink of dist/.phase6_acceptance.lock. Await actual completion, exit0, explicit PASS, exact gate membership, nested reports and production artifact identities; independently read back. If any design blocker occurs during implementation STOP, no improvisation. Source review changes invalidate affected coverage. Local scoped commits only for reviewed/verified milestones, no push or deployment.

SYMPOSIUM_STATUS=NOT_REQUIRED_FOR_F1. No tooling/config/index repairs or installations.
