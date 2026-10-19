## Rosti OS — Phase 11 Handover

## Current — Phase 11 B19 same-slot unmap authority checkpoint, BOUNDED VERIFIED

### A. Status
VERIFIED bounded checkpoint: lease-authenticated runtime unmap with live
allocator domain/identity/generation validation before any PTE clear; numeric
unmap adapter is cfg(test)-only. Canonical acceptance 65/65 PASS with
independent final readback PASS. Local commits ab2b501 + docs checkpoint on
maintenance/phase10 (starting HEAD 04e4b31).
### B. Git and preservation
Starting HEAD 04e4b312e334670f220a70bda535e2b660d6ee8b, maintenance/phase10.
Two raw-hash snapshots matched before edits; no competing writer observed.
README/d1/backup/init document untouched. No remote/deployment/history rewrite/push.
### C. Authority boundary
`unmap_owned(fa, linear, &FrameLease)` authenticates the borrowed lease against
the live allocator domain, nonzero allocation identity and current generation
before clearing the PTE; refusal retains mapping, pins, and allocator state.
`unmap_authorized` is paging-private; numeric `unmap` exists only under cfg(test).
Per-PageMap binding is by construction: the operation mutates only the PageMap
instance receiving the call; no cross-PageMap authority can reach another map.
No mapping token or generation table introduced.
### D. RED and tests
Runtime RED preserved: unmap_authority_red_02 Case A (stale lease removing
replacement mapping) FAILED against baseline 04e4b31 before the fix; GREEN after.
Three exact identities: stale-lease replacement refusal, stale-generation/
foreign-domain refusal without mutation, production-API compile oracle rejecting
numeric and private-core calls (probe scripts/unmap_api_probe.rs compiles only
the lease entry point under production cfg).
### E. Environment and evidence
Windows11/Git Bash, host Cargo child CWD C:/Users/iamsv, nightly MSVC host.
Evidence: `test_results/phase11b19_unmap_authority/STATE.md` and FINAL_REPORT.md.
Existing positional run_step recorder retained; all failed runs preserved.
### F. Fresh verification
Focused3, host343/0/2 and independently rooted B26full116/0 both serial/parallel;
exact full membership preserves every predecessor identity plus the three new
identities. Harness62, production and format pass. Focused production paging
128/512 pass; not a guest ordinary-lease proof.
### G. Resources and locks
No new persistent metadata/lock/reserve; lease metadata inspected during
admission/unmap only, never stored. HEAP -> PAGE_MAP -> FRAME_ALLOC unchanged;
guards released in reverse order; refusal paths preserve caller ownership.
### H. Review and acceptance
Independent design review and independent candidate review both APPROVE with
zero blockers (artifacts in the task root). Exact-three canonical prerequisite
gate; canonical acceptance 65/65 PASS exit0 (acceptance_20261019T161350Z_fo8p107g);
readback_acceptance.py PASS with inherited64+1 Counter equality, ISO/kernel/
archive identity, zero QEMU.
### I. Failures and recovery
Fixture compile errors (assert typo, lease moved before borrow) fixed with the
established duplicate_for_test test-only pattern; red_01/red_02 preserved.
Harness RED3/15 -> GREEN62 across three gate-count corrections. No production
workaround.
### J. Deferred
Per-PageMap ownership transfer beyond this boundary, general teardown, CPU/CR3
lifetime, exception continuation; no shared/COW/USER/TSS/CPL3/Phase12/ELF/
syscalls/init.
### K. Exact continuation
Read task STATE and complete reviews. Next command from repository root:
`git status --short`. Do not start acceptance until review blockers resolve and
source/build inputs are frozen. Never unlink dist/.phase6_acceptance.lock.
The following current-status blocks are historical predecessors.

## Current — Phase 11 B19 numeric-map authority checkpoint, BOUNDED VERIFIED

### A. Status
VERIFIED bounded checkpoint: live lease-authenticated ordinary admission, checked
exact growth specialization and paging-private numeric core. Canonical acceptance
64/64 PASS with independent final readback PASS. Local commits 4ab6c82/571d3ff.
### B. Git and preservation
Starting HEAD ff19f948718c780ec6dbf0e3b852ef562bebb673, maintenance/phase10.
Current user affirmed sole writer; raw drift checks match. README/d1/backup/init
document are untouched. No remote/deployment/history rewrite/push. No commit yet.
### C. Authority boundary
`map_owned` borrows, checks allocator/map/lease domain plus live nonzero generation
and ordinary eligibility, then preserves all existing role/pin/permission checks.
`map_growth_claim(fa, slot)` fixes physical==virtual growth and supervisor perms.
Legacy numeric map exists only under cfg(test). Audited bootstrap borrowed aliases
and structure ownership remain privileged exceptions, not ordinary payload leases.
### D. RED and tests
Production-cfg numeric-only call compiled0 when rejection was expected (API RED).
Missing proposed methods produced Cargo101/16 exact E0599, zero runtime tests.
New nine identities cover borrowed lifecycle, stale/raw-reused identity, matching-
address foreign domain, refusal/exhaustion/pins and semantic growth restrictions;
production metadata controls reject absent map/private core/numeric-as-lease.
### E. Environment and evidence
Windows11/Git Bash, host Cargo child CWD C:/Users/iamsv, nightly MSVC host.
Evidence: `test_results/phase11b19_numeric_map/STATE.md` and FINAL_REPORT.md.
Existing positional run_step recorder retained; all failed runs preserved.
### F. Fresh verification
Focused9, host340/0/2 and independently rooted B26full113/0 both serial/parallel;
exact full membership preserves every predecessor identity. Harness59, production
and format pass. Focused production paging128/512 pass; not guest ordinary-lease proof.
### G. Resources and locks
No new persistent metadata/lock/reserve. ELF sections +320 bytes (.text+304,
.data+16), file+588, BSS/static span unchanged versus accepted case7 ISO kernel.
Measured direct ESP subtract: growth wrapper72, core224, heap growth108, prepare1304;
not cumulative caller/IRQ high-water. Ordinary API is production dead-stripped
until it has a caller. HEAP -> PAGE_MAP -> FRAME_ALLOC unchanged.
### H. Review and acceptance
Independent design APPROVE_BOUNDED_DESIGN and source review APPROVE_BOUNDED,
both zero blockers. Exact-nine canonical prerequisite gate; canonical acceptance
64/64 PASS exit0 (acceptance_20261019T133256Z_skpr6lcf); readback_acceptance.py
PASS with inherited63+1 Counter equality, ISO/kernel/archive identity, zero QEMU.
### I. Failures and recovery
First focused run overflowed the Windows test thread from two large by-value
allocator fixture returns. Larger-stack diagnostic passed; direct second-owner
initialization fixed the fixture and default-stack full suites pass. No production
stack workaround or enlarged global stack setting. Harness RED3/15 -> GREEN59.
### J. Deferred
Same-slot unmap/replacement generation, complete per-map transfer, shared/COW,
general teardown and CPU/CR3 lifetime; no USER/TSS/ESP0/CPL3/Phase12/ELF/syscalls/init.
### K. Exact continuation
Read task STATE and complete review. Next command from repository root:
`git status --short`. Do not start acceptance until review blockers resolve and
148 source/build inputs are frozen. Never unlink dist/.phase6_acceptance.lock.
The following current-status blocks are historical predecessors.

## Current — Phase 11 B19 case 7 characterization checkpoint, PARTIAL

Starting HEAD917995471bbb57524c6edddbc243d3982c973556, maintenance/phase10.
The operator explicitly affirmed sole-writer ownership; two raw-hash snapshots
matched and no contradictory live writer was identified. Preserve inherited
README.md edits, d1/, script backup and the separate init architecture document.

IMPLEMENTED: three CHARACTERIZATION tests, no production correction/refcounts.
A: same-map and cross-map duplicate refusal with exact allocator/pin/PDE/PTE/
map/TLB snapshots. B: actual table exhaustion, retained-lease valid retry and
complete final cleanup. C: A-unmap-B lifecycle; old absent slot and foreign
allocator cannot remove B; correct unmap permits exactly one lease release.
D: NOT REACHABLE through ordinary allocation in the reserved growth window.

TESTED: focused11/0/0; host331/0/2 existing ignores and B26full104/0/0, each
serial/parallel with exact libtest-list membership; harness56; production build;
focused paging128/512 MiB. Existing mandatory phase11_runtime_pins family now
requires all eleven exact identities; all inherited63 gate names remain.
Clef recommended extend_existing (p0.9725), advisory only. Harness01 failed due
old prefix-only declaration discovery; corrected harness02 passes, failure kept.
No runtime kernel RED was reproduced/manufactured; no production GREEN claimed.

VERIFICATION STATUS: independent candidate APPROVAL, no blocking findings.
Fresh source-frozen canonical acceptance completed actual exit0/PASS63/63:
`acceptance/acceptance_20261019T110519Z_v70j7rsk/acceptance.json` under the
continuation root below. Offline readback PASS:146 rediscovered source/build
inputs,159 nested reports,280 true cleanup-field assertions, exact inherited63
gate membership and eleven runtime-pin identities, ISO/kernel/archive identity
and no remaining QEMU. Counts of reports/cleanup fields are not distinct guest
totals or complete process history. Independent final readback APPROVES this
bounded checkpoint; local commit identities are recorded in task STATE. Full evidence:
`test_results/phase11b19_shared_mapping/continuation_20261019T105410Z/`;
current HEAD/status/next exact command: task STATE.md. The A–K handover below is
retained unchanged as historical organization, not current completion authority.

DEFERRED/BLOCKED: numeric map/lease caller authority and arbitrary same-slot
replacement generations, complete per-map transfer, shared ownership, general
teardown and CPU/CR3 lifetime. No USER/TSS/ESP0/CPL3/Phase12/syscalls/ELF/init,
push, remote changes, deployment, boot-media changes or physical-disk access.
Next planned slice is numeric-map authority only after this checkpoint closes;
do not start it automatically. Following checkpoint results are historical.

## Current — Phase 11B19 virtual-page-zero admission checkpoint, PARTIAL

The bounded fail-closed admission refusal is implemented: PageMap::map rejects
ordinary payload mapping at linear==0 (counted map_rejects, side-effect-free),
preserving the faulting-null boot invariant; no production path maps virtual
zero (growth slots start 0x800_000). Three focused oracles (vpz_*) added.
Host328/0/2 and B26 full101/0 pass serial/parallel; production build and
sequential128/512 paging PASS. Fresh canonical acceptance completed actual
exit0/PASS63/63 bound to reviewed bytes (paging.rs b5b9960c…, vpz tests
22d84687…); never apply historical63/63-at-ba67987 to this tree. Independent
review: BOUNDED_APPROVAL, zero blockers, hashes matched. Local commit
1aa2e77125a9b69a642e6da53d39294517da7484. Full B19 remains PARTIAL: shared
mapping, per-map ownership transfer, CPU/CR3 teardown lifetime still open.
Evidence root: `test_results/phase11b19_vpz_admission/` (STATE.md, FINAL_REPORT.md).
No complete B19, USER, TSS/CPL3, Phase12, general teardown or deployment approval.
Following current-status sections are historical predecessors.

## Historical current — Phase 11A.3 generation-safe lease checkpoint, PARTIAL

The bounded ordinary-frame ledger and move-only release API are implemented;
audited raw structure and growth operations remain separate. All seven design
corrections are reconciled by a byte-scoped independent bounded approval with no
blockers. Host325/0/2 and B26 full98/0 pass serial/parallel; exact generation
families8/6/6, harness56, production build and sequential128/512 paging pass.
Fresh canonical acceptance completed actual exit0/PASS63/63; never apply historical60/60
to this changed tree. Final readback, source/artifact identities and exact next
command: `PHASE11A3_GENERATION_HANDOVER.md` and task-local `STATE.md`.
No complete B19, USER, TSS/CPL3, Phase12, general teardown or deployment approval.
Following current-status sections are historical predecessors.

## Current — structure cleanup lifetime and owner observability (PARTIAL)

Starting HEAD `6008ea6083ec8e0dcfc703878abacc362d5bca6b`; verified implementation
`38b98b4658cfe118eb31e5faa1b600613750c71e`, `maintenance/phase10`. The following
documentation checkpoint records the results; obtain actual HEAD from Git.
The previous structure-role checkpoint was independently reverified with 59 gates,
141 source inputs, host300/0/2 and B26 full67/0, production/ISO identity and cleanup.
New task evidence is `test_results/phase11a2_structure_lifetime/`.

IMPLEMENTED: cleanup preflights its whole private structure release set, refuses
retained/wrong-domain/live-payload/inconsistent-role maps, releases structures once
and revokes numeric authority without dropping Vecs under guards. `prepare` seals
before exposure; both CR3 writers seal before CPU publication. Retention has no
inverse. B26 observation and unlocked-attempt classification share a map-or-frame
owner predicate, with five separately mandatory detector controls.

TESTED: three primary RED failures became GREEN; five lifetime identities cover
32 actual reuse cycles and four early/late role faults across multiple tables.
Host305/0/2 and full B26 78/0 pass serial/parallel; harness53 and final readback
contracts17 pass; focused128/512 paging and eight ELF/GRUB growth cases pass.
VERIFIED: `final_source_review.json` approves the exact11-file source scope, no
blockers, not full B19. Old reviewer hashes/evidence stay unchanged.

VERIFIED PASS, actual exit 0: sequential frozen driver
`test_results/phase11a2_registry/run_20261018T054817_823884Z/verification.json`.
Canonical invocation: `acceptance/acceptance_20261018T054947Z_n_dqyuzm/acceptance.json`
under that run. PASS60/60 preserves all59 inherited gates plus the exact-five
lifetime prerequisite; B26's existing gate now requires all five detector controls.
`final_closeout_retry.json` independently verifies143 rediscovered raw-byte inputs,
159 nested reports,280 true cleanup assertions, exact guest matrices, production
ISO extraction, unchanged trusted archive and no QEMU. Cardinalities do not count
distinct guests or establish complete historical process identity.

The first reader failure `final_closeout.json` is preserved: silent successful
format commands legitimately have empty logs. The reader now binds only those two
exceptions to exact argv/cwd/integer-zero exit; all other logs stay nonempty.
RED/GREEN and17 contracts include wrong command/cwd/exit, empty nonformat and
independently reset stale/empty-log subcases. No accepted source input changed and
no full campaign was repeated. Historical reviewer pins remain immutable.

ISO: `dist/rosti_phase11a_prerequisite_20261018T054947Z.iso`, SHA256
`528ba288950d87059750f4ad37a8b94005af8eecc0c97567f0b2456f683cf04d`.
Kernel SHA256 `8b43ae2ee1d20e40bd1754e031202a1d0085ae21de8bb6162edbea671c2ba9b9`.
Acceptance JSON SHA256 `92397a24de25643054dc5d199dcafa3983494eb9e5b04f2dea0790ed91833109`.
Resource delta versus preceding structure-role ISO: allocated/initialized sections
+1,280 bytes, of which .data+4; BSS/static address span unchanged, ELF file+4,784.
No new backing reserve or allocator bitmap. Selected explicit ESP subtraction:
cleanup104, retain8, prepare1304, enable20 bytes; not cumulative call/IRQ high-water.
Runtime heap/stack peaks remain unknown. Evidence: `direct_stack_final.json`.
Never unlink the acceptance lock or reuse these results for changed source.

BLOCKED: raw stale numeric release (new real-module probe2 PASS/1 intentional FAIL),
complete per-map/shared references, general teardown and full CPU context lifetime.
Current policy retains active boot structures until reboot; no SMP work. #GP now
uses CpuErrorFrame and #PF its error frame; real GPR/segments/DF/alignment/IRET and
recoverable user-fault behavior remain unproven. TSS/ESP0/CPL3 NOT implemented.
Next exact implementation: generation-safe allocation/release authority plus raw
bypass audit, not USER mappings. Contract/inventory: `PHASE11_MEMORY_AUTHORITY.md`.
Graphify installed/Rust-supported but skipped as direct source search was cheaper;
details in `PHASE11_TOOLS.md`. No remote action or Phase12; preserve unrelated files.

## Historical checkpoint sections — superseded for current status

## CURRENT — Phase 11A.2 reservation checkpoint committed + exception-ABI entry conventions tested / NOT A RELEASE

### A. Current status
- IMPLEMENTED: fallible registry backing/rollback and runtime PTE bit9 repair,
  locally checkpointed at `4bfbe60`; allocator-state admission rejects reserved/uncovered
  runtime payloads before table allocation, locally checkpointed at `8f02162` (HEAD).
- IMPLEMENTED/TESTED: exception-entry conventions — `#AC(17)` routed through the
  error-code `CpuErrorFrame` shape; `CPU_ERROR_CODE_VECTORS` oracle `{8,10,11,12,13,14,17}`
  corrected with accurate Intel Vol. 2 table-12 comments; four ABI oracle tests pass;
  mandatory `phase11_exception_abi` gate family added to acceptance (57→58 gates).
- BLOCKED: complete B19. Three executed real-module probes fail for mapped free,
  cross-PageMap duplicate authority and stale numeric release. This is a verified
  partial improvement, not a safe process-memory foundation.
- TSS and CPL3 remain DEFERRED; no user execution occurred. Exception entry
  *shape* is tested; recoverable #GP/user-fault continuation remains unproven.

### B. Git and preservation
- Branch `maintenance/phase10`; initial HEAD
  `48e76dfa096397824bc11dee137ea6287c5068f2`.
- Initial worktree:13 tracked modifications and6 untracked entries. No reset,
  stash, branch creation, merge, rebase, tag, push or history rewrite.
- Registry-only checkpoint `4bfbe60a1d66152d9a8210d0bb37bd49ad082db9`, seven
  source/test files. Index-only staging excluded inherited paging ABI helpers and
  the ABI test module; working bytes were preserved. `src/interrupt.rs` and
  `src/memory/phase11a2_abi_tests.rs` remain outside reviewed commit scope.
- Do not confuse committed registry-only source with accepted mixed-tree inputs.
  The exact acceptance tree is defined by its complete byte-hash manifest.
- Unrelated `d1/`, script backup, historical ISOs and failure evidence preserved.

### C. Architecture and authority
- `FrameAllocator::is_live_allocation` is memory-private, allocation-free, and
  checks initialized/aligned/nonzero/managed, complete coverage, competing-denial,
  allocation history/current free state and live growth claim. This grants no
  nonduplicable caller capability. Raw numeric APIs still require trusted callers.
- Boot identity aliases remain borrowed supervisor mappings; runtime admission
  does not transfer their reserved backing. Existing USER/nonpresent refusal,
  null/free/self-table/local-duplicate checks and bit9 lifetime distinction remain.
- Heap -> map -> frame; no allocation/backing destruction/callback under prohibited
  owners. No IRQ enters these owners. This slice adds no lock or backing reserve.
- Cross-map table roles, active CR3/heap/stack/IRQ pins, shared mapping reference
  lifetime, revocable teardown and generational release remain unimplemented.
- The null check concerns physical frame0. Raw numeric map still lacks a distinct
  virtual-page0 publication refusal; close that boundary before any owned USER API.
- Page-table identity accessibility is a separate prerequisite: a table's physical
  address must be writable through the active kernel mapping before entry writes.

### D. Implementation and RED/GREEN evidence
- Reservation RED exit101 at boot-info frame0x20000; GREEN1/1. Independent span
  fixture also covers bump, one-byte explicit pin, firmware overlap, VGA/uncovered.
- Three positive fixtures acquired legitimate payload/growth backing; all existing
  permission/table-identity assertions remain. The intermediate282/3/2 host failure
  identifying those fixtures is preserved as `host_fixture_audit.log`.
- Mandatory registry/reservation family8 adds one gate to inherited56; harness
  RED five failed assertions, GREEN41 tests. No predecessor gate removed.
- Real-production-module blocker probe: actual0 passed/3 failed/0 ignored, exit101.
  These remain blockers; they are NOT counted as passing regression acceptance.

### E. Tools and reproducibility
- Existing nightly Rust/native Windows Git Bash/QEMU/WSL tooling reused; no install.
- Actual command driver: `python -B test_results/phase11a2_registry/verify_registry.py --full-acceptance`,
  notified background; current run `run_20261017T162309_113081Z` beneath that root.
- Exact command/cwd/timestamps/statuses/logs are retained in `verification.json`
  and `test_results/phase11a2_continuation/*_red.json`, `*_green.json`.
- Never unlink `dist/.phase6_acceptance.lock`; no competing QEMU/build/source edits
  during official acceptance. Final read-back utility is
  `test_results/phase11a2_continuation/verify_closeout.py`.

### F. Verification status
- Recovery closeout independently matched139 accepted inputs/eight review hashes,
  retained56/56 PASS,159 nested reports,280 cleanup assertions and ISO contents.
- Reservation tree: host285/0/2 ignored and B26-root52/0, each serial and parallel;
  focused sequential paging128/512 passed.
- Exception-ABI tree (current): host285/0/2 ignored and B26-root52/0, each serial
  and parallel; production build exit0; four `phase11a2_abi_tests` identities pass
  serially; harness43 passed (two new ABI oracle tests).
- Current canonical full run `run_20261017T175909_983725Z` completed **58/58 PASS,
  actual runner exit 0**, including the new mandatory `phase11_exception_abi` gate;
  `verification.json` records registry verification PASS. Closeout verifier updated
  57→58 and binding validated; final closeout read-back pending the independent
  exception-ABI review.

### G. Resource accounting
- Registry backing remains8,192 bytes/map; table slots8,192 bytes/map plus pin
  capacity. Reservation predicate adds zero storage fields/backing allocations.
- No TSS, process payload, user/transition stack or dynamic address-space storage.
- `focused_memory.json` independently checks all8 ELF/GRUB128/512 cases: retained
  heap16,536 bytes without module /16,568 with module is unchanged after growth;
  capacity1,048,576 ->7,340,032 bytes, growth0 ->1,536 pages. Module bytes match
  before/after, and every owned guest exited. These are not peak measurements.
- Proposed dense generation/binding ledger costs512KiB, NOT allocated or implemented;
  stack-safe static initialization and minimum-RAM/linker-bound review are required.
- Runtime heap/stack peaks and transition timing remain unknown. Final section
  accounting belongs to the exact production kernel after the runner restores it.

### H. Review and limitations
- `recovery_review.json` approves only registry static scope, rejects exception
  checkpoint and full B19. Existing map-lock allocator-observability gap remains.
- Exception findings: #AC17 omitted, incorrect selector-error oracle comments,
  unproven one-aggregate x86-interrupt ABI/real frame offsets, no segment/GPR/DF/
  alignment/IRET/user-return proof. Preserved source is not approved functionality.
- `reservation_review.json` approves the bounded reservation/harness checkpoint
  with no in-scope blockers; all30 reviewed source/evidence hashes independently
  match. It expressly rejects complete B19, exception ABI, USER, TSS and CPL3.
- Optional exact-eight malformed-summary variants and fuller rejection-counter
  assertions remain nonblocking review suggestions, not changes to frozen inputs.
- Separate evidence-tool review found weak focused-row/digest checks, broad B13
  schema exemptions, summary/run binding and Python optimization hazards. Evidence
  helpers (not frozen inputs) were hardened with4 RED/GREEN host tests: exact
  focused identity/count/all-true rows/digests, exact B13 child equality, driver/
  closeout/ISO/source binding and refusal of optimized Python. Historical gate
  oracle is byte-hash pinned. Cleanup280 remains repeated true assertions, not
  distinct guests; the official invocation-owned checks remain mandatory.

### I. Deployment and inherited guarantees
- No Proxmox API/SSH action or remote Git operation; no VM103/config/media/disk/
  storage changes. Remote state is not freshly inspected. Local disposable guests only.
- Trusted `/system`, SHA256, RAMFS recovery, GRUB/Multiboot/B13 and filesystem
  format/COW/CRC/flush/capabilities are unchanged. The full inherited acceptance
  must retain all56 initramfs scenarios and all9,071 modeled crash cases.

### J. Exact next bounded task
- Use retained RED mapped-free/cross-map/stale-release probes to implement the
  allocator-domain authority model in `docs/PHASE11A2_OWNERSHIP_PLAN.md` and
  `ownership_design_review.md`: nonduplicable generational leases, structure roles,
  map binding, mapped/CPU pins, reversible unpublished lifecycle, private numeric
  mutation routes. Review storage/stack budget before choosing dense metadata.
- Migrate the B26 growth conflict fixture that deliberately frees a live mapping;
  preserve its unrelated-PTE rollback oracle with separately owned backing.
- Complete all15 required ownership cases, serial/parallel host, sequential local
  128/512 guests, mandatory full frozen acceptance and independent review.
- Only then repair real exception entry ABI/probes; no TSS or USER/CPL3 yet.

### K. Release decision
- NOT READY. B19 remains PARTIAL, exception ABI BLOCKED, TSS/CPL3 DEFERRED.
- No Phase11 completion, Phase12, general ELF loader, production syscall or scheduler.
- A later scoped documentation commit records final actual results; resolve exact
  final HEAD with Git rather than attempting a self-referential embedded hash.

---

## Historical predecessor handover (superseded by current A–K above)

### Latest working-tree continuation — registry backing repair

The uncommitted Phase 11A.2 tree supersedes the implementation inventory below.
Read `docs/PHASE11A2_REGISTRY_HANDOVER.md` for exact current state, commands,
evidence and remaining ownership blockers. The registry backing is now reserved
fallibly before ownership locks, and runtime PTE references are distinguished
from boot identity aliases. Host284/0/2 ignored and B26-root51/0 pass in parallel
and serially; focused paging and eight ELF/GRUB growth scenarios pass.
Fresh inherited prerequisite acceptance PASS56/56, runner exit0; read-only
closeout verifies139 frozen inputs/159 nested reports/280 cleanup assertions
and eight reviewed hashes. Exact paths are in the linked registry handover.
No full B19, TSS or CPL3 claim; one nonblocking lock-observability review gap
is deferred. The historical acceptance below is not this changed tree's run.

The A–K sections below describe the previous committed checkpoint.

### A. Current status
- Overall status: **Phase 11A PARTIAL; NOT A RELEASE; CPL3 DISABLED**.
- Completed continuation: private PageMap synchronization/scalar snapshots and GDT nonzero-base encoder repair. These follow the accepted effective-permission prerequisite; they do not complete physical-frame/mapping lifetime ownership.
- Current acceptance: PASS56/56, notified runner exit0; independent closeout PASS136 frozen inputs/159 nested reports/280 all-true cleanup assertions. Exact run: `test_results/phase11a_ownership/acceptance_20261016T234702Z_x057jmpa/acceptance.json`.
- Next exact command: `git status --short`. Then implement bounded frame/table/payload ownership and null/reserved/alias rejection through RED/GREEN tests before any USER publication. Correct the exception ABI before TSS/CPL3.
- BLOCKED: user mappings, #GP/error-code recovery, TSS/guarded transition stack, user IRET/kernel continuation and all CPL3 isolation criteria. No ELF/syscalls/scheduler/Phase12 started.

### B. Git state
- Branch: `maintenance/phase10`.
- Initial continuation HEAD: `c347a9c4375fe86dfb0a81d675b7b4603662d21c` (verified exact match). Earlier Phase11 initial HEAD was `def677fac8ca662e45ad4fb40c9ddd18bfe86bd8`.
- Accepted implementation/test HEAD: `9a2f334761ab2350e42c6bfdb94fbbc86e63ae3a`. The final documentation/evidence commit follows it; resolve that commit with `git rev-parse HEAD` rather than pretending a commit can embed its own hash.
- Working-tree status at recovery: only untracked `d1/` and `scripts/b13_boot_fixture.py.backup`; neither altered. At implementation commit: only task documentation remained modified/untracked in addition to those unrelated paths. Final documentation checkpoint should leave only the two unrelated paths untracked.
- Branching decision and justification: stay on existing maintenance branch. No incompatible implementation or independent writer identified; two delegated audits are read-only. Local upstream policy is known, remote protection unknown. No push requested. Accepted source/artifacts provide rollback; another branch offers no concrete isolation.
- New commits: `2510838` private PageMap owner/scalar queries; `37929fb` GDT encoder and independent fixtures; `9a2f334` two mandatory acceptance gates/exact identities. A final scoped documentation/evidence commit follows verified acceptance. Earlier `d6d04c5`, `fa4eb79`, `c347a9c` remain unchanged historical checkpoints.
- Upstream relationship: continuation began three commits ahead of origin, with no tracked changes. No push, branch creation, merge, rebase, tag or history rewrite; verify current ahead/behind counts when resuming.
- Unrelated files preserved: both paths above; accepted media/evidence retained.

### C. Architecture
- Current privilege model: single-owner Ring0, no user execution.
- GDT selectors: CS 0x08, DS 0x10; no user descriptors.
- TSS and stack model: no TSS; existing 16 KiB bootstrap stack unchanged.
- Paging/user-supervisor boundary: non-PAE 4 KiB PDEs/PTEs supervisor; growth supervisor, null absent at boot. Effective PDE/PTE permissions and unsupported-request refusals are preserved unchanged. PAGE_MAP now has a private mutex owner; only copied snapshots/scalars escape. No public callback/guard/reference into the global map. Growth order is heap -> map -> frame; no IRQ may acquire these locks. Backing reserves/destruction are unlocked.
- Physical ownership remains unresolved: numeric allocator/map/free authority is still trusted-kernel-only, with no bounded user-frame ledger, null/reserved alias rejection or active-CPU teardown contract. A snapshot is not a pin. No NX, W^X or hostile-userspace isolation claim.
- GDT encoding: low base word masked before insertion; existing selectors and three descriptor values unchanged. Available-TSS type fields are host-tested, not a loaded TSS. Exception ABI is unchanged/defective; no generic recoverable trap is invented.
- Syscall ABI version: none active; v1 proposal in PHASE11_DESIGN.md.
- Process ownership rules: not implemented; shell owns descriptor/VFS context.
- ELF32 supported subset: no guest loader; strict ET_EXEC i386 plan proposed only.
- Known unsupported features: all Phase11 execution; no multitasking/SMP/dynamic linker.

### D. Implementation inventory
- Continuation files: `src/memory/mod.rs`, `boot_copy.rs`, `review_r1_tests.rs`, `src/fs_stress.rs`, `tests_kernel/src/lib.rs`, four scalar-query caller updates in `tests_b26/src/`; `src/gdt.rs`, new `src/phase11_gdt_tests.rs`; canonical runner and acceptance-harness tests. Frame allocator, raw paging implementation, boot assembly and interrupt wrappers are unchanged.
- New mandatory gates: exact snapshot-growth identity1/1 and GDT identities3/3, preserving all54 predecessor gates. Host273/0/2 ignored parallel+serial; B26 complete crate37 pass; harness39 pass. Further full Phase11 work remains absent.
- Current selected evidence root: `test_results/phase11a_ownership/` with command/status records, RED/GREEN summaries/hashes, focused reports, review/identity verification, tools, resources, notified exit, canonical report and final closeout. Raw logs/media retained locally, excluded from Git. Inventory below is historical 11A.0 evidence.
- 11A prerequisite: `src/memory/paging.rs` effective two-level permissions and early refused unsupported requests; `src/memory/phase11_permission_tests.rs` five host tests. `scripts/phase6_verify.py` mandates the exact identities, `scripts/test_acceptance_harness.py` rejects missing evidence and labels prerequisite-only. Three intended RED/GREEN behavior cycles retained. Fresh broad host parallel/serial 270 passed, 0 failed, 2 ignored; harness37 passed. Full inherited regression acceptance PASS 54/54; no CPL3 proof.
- 11B/C/D/E: not implemented or tested.
- 11F: full Phase11 acceptance NOT implemented. Canonical runner preserves every inherited gate plus the permission prerequisite, explicitly reports `phase=11A-prerequisite` and `phase11_release_ready=false`. Future CPU/ELF/syscall/lifecycle matrices must be mandatory, not optional.
- Documentation changed: `HANDOVER.md`, `NEXT_SESSION_PROMPT.md`, `ARCHITECTURE.md`, `TESTING.md`, `BUGFIXES.md`, `PROXMOX.md`, `README.md`, `docs/PHASE11_HANDOVER.md`, `docs/PHASE11_DESIGN.md`, `docs/PHASE11_TOOLS.md`.
- Selected committed evidence beneath `test_results/phase11/`: `discover_tools.py`, `tools.json`, `auxiliary_tools.json`, `focused_commands.json`, `recovery_baseline.json`, `verify_checkpoint.py`, `final_verification.json`, `resource_sections.json`, `runner_exit.json`, `sanitized_test_results.json`, `evidence_manifest.json`, `independent_permission_review.json`, `review_identity_verification.json`, `static_scan.json`, `staged_source_scan.json`, and `acceptance_20261016T154710Z_q3u90_53/acceptance.json`. All other raw logs/guest captures and media remain local and excluded; nothing unrelated was staged.

### E. Tool manifest
- Current invocations: `docs/PHASE11_TOOLS.md`, `test_results/phase11a_ownership/tools.json`, `commands.json`, `focused.json`, `focused_retry.json`, `runner_exit.json`. No optional installations. Current canonical command: `python -B scripts/phase6_verify.py --output-dir C:/Users/iamsv/Documents/Rust-OS/test_results/phase11a_ownership`, notified background, exit0.
- Current read-only closeout: `python -B test_results/phase11a_ownership/verify_checkpoint.py test_results/phase11a_ownership/acceptance_20261016T234702Z_x057jmpa/acceptance.json`, exit0. Old commands below remain historical results, not this candidate's acceptance.
- Exact discovery command, executable paths, versions, statuses and output: `test_results/phase11/discover_tools.py`, `test_results/phase11/tools.json`; human-readable manifest `docs/PHASE11_TOOLS.md`.
- Tool probes completed; no optional tools installed. Miri/Kani/cargo-fuzz/llvm-objdump unavailable via probed interfaces. No assertion these tools support the custom target.
- Host test command: Cargo nightly outside repository config; exit 0, `baseline_host.log`, `host_green_parallel.log`, `host_green_serial.log`. Canonical run command `python -B scripts/phase6_verify.py` exited 0 (`runner_exit.json` and invocation gate logs). Read-only closeout command `python -B test_results/phase11/verify_checkpoint.py test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json` exited 0 before and after implementation commit.
- Versions: Rust 1.101.0-nightly (1d81eb4ad), Cargo 1.101.0-nightly (f3865b2a4), rustfmt1.11.0-nightly, LLD23.1.3, GNU binutils2.42, GRUB2.12-1ubuntu7.3, QEMU10.2.0, Python3.11.15, Git2.55.0.windows.3, coreutils8.32, GDB15.1, Clippy0.1.101. Full paths/commands/statuses in PHASE11_TOOLS.md/tools.json; version probes are not whole-kernel analysis. Existing host warnings remain; no broad lint cleanup was attempted.

### F. Verification matrix
- Current host273 passed/0 failed/2 ignored, parallel+serial. Previous unchanged265 and permission-only270 counts remain historical; no test was removed. Three new descriptor tests independently decode wire bytes across base/limit/access/DPL/presence/type/flag boundaries.
- Snapshot API RED was a missing-function compile refusal (exit101), then GREEN1/1. GDT RED reproduced access0x9b instead of0x89 for base0x12345678, then GREEN3/3. Harness RED eight failed assertions in39 tests, GREEN39/39. Raw RED logs and the initial failed paging invocation are retained.
- Focused QEMU: sequential128/512MiB paging PASS; RAMFS/growth/OOM PASS103 checks each,1536 writable-supervisor identity growth pages, shell functional and both owned-QEMU exits true. Relative `--output-dir` first caused a harness pathlib error after128MiB capture; absolute-path retry passed. No kernel fix/assertion weakening was needed.
- Current full inherited acceptance PASS56/56, actual exit0: `test_results/phase11a_ownership/acceptance_20261016T234702Z_x057jmpa/acceptance.json`. Exact inherited gate multiset retained plus two mandatory new identities. Independent `final_verification.json`:136 inputs rediscovered/hash-matched,159 nested reports,280 all-true cleanup assertions (includes repeated aggregate/child assertions, not280 guests), final QEMU inventory empty.
- Inherited matrix retained:56/56 initramfs scenarios/3379 checks,44 boot-metadata scenarios,10 boots each RAM size, paging/fatal ring0 PF tests and all ELF/GRUB RAMFS/ATA/RostiFS tests,9071 modeled crash cases. **CPL3 scenarios remain zero**.
- Current ISO `dist/rosti_phase11a_prerequisite_20261016T234702Z.iso`,11098112 bytes, SHA256 `874c1d93e9fcd91bd451263060298755a28d7df9571d4cde4778f7aa554ba485`; independently extracted production kernel `a99124ecffc74d94a97fe9c4ad762b1353bb6e8d7f78c46793ae9ac698afab11`. Archive remains `8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7`. Both previous versioned prerequisite and accepted Phase10B ISO hashes verified unchanged.
- Current independent bounded review: `test_results/phase11a_ownership/independent_review.json`, passed=true/no blocking regressions;29 raw file hashes matched after code commits. Reviews complete relevant files plus explicitly listed partial call paths, **not the whole kernel**. Numeric-frame ownership/exception ABI/TSS/CPL3 remain NOT APPROVED. Optional map-lock allocator instrumentation/recheck and stronger harness-negative fixtures deferred; no source changes during freeze.
- Historical permission-only verification follows; it is not acceptance of this changed candidate.
- Guest test count/RAM configurations: Phase11 CPL3 scenarios zero (not implemented). Fresh inherited tests: 56/56 initramfs scenarios and 3379/3379 associated checks; 44 boot-metadata scenarios; B13 four fixture/production guests; normal boots10/10 per RAM size; paging20 ELF and2 ISO; CPU read/write faults2+2; complete RAMFS103/ATA98/RostiFS168 check aggregates at ELF/GRUB x128/512 MiB. Do not sum nested reports as distinct tests.
- Positive/negative/fault/cleanup scenarios: inherited trusted/rejected module, malformed metadata, OOM/growth, mount/recovery/readonly, keyboard/VGA and persistent reboot/restart scenarios passed. All9071 modeled RostiFS crash cases reran (2639 rejected/torn/flush,2328 reordered,4104 root-prefix). Real Phase11 user fault/ELF/syscall cases remain required and unexecuted.
- Exact new acceptance: `test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json` PASS54/54, real process exit0. Independent closeout `test_results/phase11/final_verification.json` re-reads159 nested reports and280 explicit cleanup booleans (includes aggregate/child repetition, NOT280 distinct guests).
- Exact historical acceptance: `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json` records PASS 53/53, 56 initramfs scenarios / 3379 associated checks. Its SHA256 `e0d1ee24cd74692ba99382347d11e1ec59d3a560fe9aec55c6c8831d33791d4f` was read locally.
- Frozen source hashes:135 inputs independently rediscovered and byte-hash matched before/after implementation commit. Review's four raw source hashes matched separately. Selected sanitized results/evidence manifest are committed; raw logs/media remain unchanged locally, not rewritten to satisfy Git whitespace.
- ISO: `dist/rosti_phase11a_prerequisite_20261016T154710Z.iso`,11098112 bytes, SHA256 `fa309a4ecc5b97d98ee07891597e5cffe4bf45058709ed91c8936a2fe62992a9`. Independently extracted kernel SHA256 `c813429de80aa5c0d9782fcd1de76bde95566887f1f76caaf36bc85662844f4b`. System archive SHA256 `8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7`, identical to baseline archive.
- QEMU cleanup: final local process-name inventory empty; every inspected cleanup assertion true. This is not a continuous absence proof or remote-state assertion. The sole canonical runner owned the nonblocking lock; lockfile was never unlinked.
- Independent review: two read-only architecture audits confirmed B19/trap/ownership blockers. Narrow implemented four-file diff review passed with no security/logic blockers: `test_results/phase11/independent_permission_review.json`. Parent independently matched all four reviewed raw source hashes (`review_identity_verification.json`). Optional broader exact-five harness-negative fixtures deferred during freeze. Not formal verification or full Phase11 review.

### G. Resource accounting
- Current versus independently extracted previous permission-only ISO: allocated/initialized sections +356 bytes, ELF file +1072 bytes, static span unchanged. `.text`+416,`.data`-60,`.bss` unchanged; exact tables in current `resource_sections.json`. These are section totals, not object sizes or measured peaks.
- No new page tables, user payload, TSS or stack reservations; GDT24 wire bytes/IDT2048 wire bytes and existing16KiB boot stack unchanged. No added production heap allocation calls in this slice. Focused ELF retained heap8416 bytes before/after stress, capacity1048576 ->7340032, growth0 ->1536; `focused_memory.json`. This is retained/capacity accounting, not peak usage. Frame reservation/rollback tests pass; no new process ledger exists.
- Peak heap/stack and user/fault/transition overhead remain unmeasured/null. Prior 11A.0 deltas below compare against Phase10B, not against this continuation.
- Loaded binary changes: independently extracted baseline/candidate SHF_ALLOC1958406 ->1959126 (+720); initialized820730 ->821450 (+720); ELF file5970396 ->5972404 (+2008); static address span1969164 unchanged. `.text`+704,`.data`+16,`.bss` unchanged. `.data` growth is section accounting, not a measured process-metadata high-water. Evidence `resource_sections.json`.
- Page/frame reservations: no new process reservations. Existing GDT three descriptors/24 wire bytes unchanged; TSS/user/transition stacks absent (zero added storage, not implemented features). Existing16KiB bootstrap stack unchanged. Permission diagnostics/refusals add no heap allocations; total runtime heap/stack peaks unmeasured.
- Measured timing: no valid CPL3/syscall/process/boot-to-shell delta measurement; these fields remain null. Boot harness elapsed values include timeout and must not be represented as boot latency.
- Unknown/deferred: runtime stack/heap peaks, loader temporary allocation, transition/syscall costs, process create/cleanup timing and restoration after actual user faults.

### H. Safety and compatibility
- Existing Phase10B inherited regression gates reran successfully; this does not establish new hostile-userspace safety. No B13 entry/exception/GDT assembly was changed.
- RostiFS format1, trusted `/system`, capability checks and independent RAMFS recovery unchanged and covered by inherited regressions. Independently extracted archive bytes equal baseline; accepted baseline ISO still hashes exactly as before.
- No user execution allowed before effective permissions, ownership and exception/continuation safety pass real guests.
- Known trust limitations: loader/kernel trusted, single CPU; no secure boot/NX, numeric-frame authority and legacy exception ABI blockers. Retained global PageMap references are removed, not a substitute for full ownership or IRQ-safe concurrency.
- Unresolved findings: see PHASE11_DESIGN.md; Phase11 release blocked.
- Historical initial-HEAD audits remain under `test_results/phase11/initial_*_audit.md`; their nonzero-base GDT defect is now fixed/tested by37929fb. Their physical ownership, FPU/SIMD/cancellation, error-code trap and cross-context confinement obligations remain unresolved. Current acceptance is the56-gate run above; the older54-gate report applies only to its own source/artifact.

### I. Environment and deployment
- Local Windows Git Bash/native Rust/QEMU and WSL GNU tools only.
- Proxmox inspection not performed this session. Historical VM103 inventory is not a fresh read.
- Explicit remote mutation/deployment status: none; no upload/reboot/reset/disk changes.
- Existing rollback artifacts retained; accepted versioned Phase10B ISO hash reverified. Canonical runner preserved the regular ISO before task-owned packaging; no accepted versioned media was replaced/deleted. New ISO is a prerequisite artifact, not deployable Phase11 acceptance.

### J. Resume instructions
- Exact next task: finish B19 physical/table/payload ownership, not repeat the completed reference/GDT repairs. Start RED tests for null/free/reserved/page-table aliases, stale ownership release and per-stage allocation rollback. Encapsulate numeric global authority; implement a bounded private ledger or nonduplicable tokens, borrowed supervisor mappings versus owned private mappings, publication/active-CPU pins/teardown. Preserve exact growth slots, reservation precedence and heap -> map -> frame order. Then correct explicit error/no-error exception entry ABI before adding TSS or user IRET.
- Files to read: PHASE11_DESIGN.md, PHASE11_TOOLS.md, this handover, standard project docs, paging.rs/mod.rs, interrupt.rs/gdt.rs and B19 audit.
- Test command outside repo: `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml`.
- Expected checkpoint: host273/0/2 ignored, mandatory permission5/snapshot1/GDT3, harness39, canonical prerequisite56/56,136 frozen inputs. No CPL3 coverage. Record added tests explicitly; never shrink inherited identities/counts.
- Failure behavior: preserve failed evidence, repair root cause, never claim partial/refusal evidence is CPL3 success.
- Must not change: B13 entry, accepted rollback media, unrelated files, RostiFS format, lockfile ownership contract; no push/deploy/Phase12.

### K. Final release decision
- NOT READY.
- Acceptance evidence: current partial-prerequisite PASS56/56, runner exit0 and independent closeout PASS; **not full Phase11A/Phase11 acceptance**, release-ready false.
- Review status: map-alias/GDT diff approved within recorded scope; complete ownership, exception ABI, TSS and user-transition safety remain blockers. No whole-kernel approval claimed.
- Source identity: `9a2f334761ab2350e42c6bfdb94fbbc86e63ae3a` and136 frozen input hashes; final documentation follows without executable-input changes. Re-run closeout after the documentation commit.
- Artifact identity: current ISO/kernel/archive hashes in sectionF, independently extracted; rollback media unchanged. Not a Ring3 release artifact; no deployment authorization.
- Remaining blockers: complete 11A through 11F with independent review and mandatory real guest evidence.
