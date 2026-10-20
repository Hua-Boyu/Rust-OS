# Phase 11 F1 retained owner — truthful partial checkpoint

STATUS: PARTIAL / DESIGN STOP. F1 IS NOT IMPLEMENTED OR COMPLETE.

## Git / preservation / scope

Initial HEAD: `b765abcc1350323357accf3623aec42a6185494c`, branch `maintenance/phase10` (matches requested checkpoint).
Final HEAD/local checkpoint: `649aaf1dccd2f18091d0d2f0f81661e11d005d97`, `docs(phase11): checkpoint F1 design blockers and baseline runtime RED`, direct child of initial HEAD. One local partial documentation/evidence commit; no push.

Inherited changes: modified README.md; untracked d1/, docs/ROSTI_INIT_ARCHITECTURE.md and scripts/b13_boot_fixture.py.backup. None is edited or staged by this task. Initial raw hash snapshot covers tracked files and protected files; useful predecessor recovery followed by rehash found no drift. No competing source writer was identified; other Hermes infrastructure/kernel runners and a historical read-only acceptance watcher were not treated as writers or killed. Stable hashes do not independently prove exclusivity.

Authorized scope was F1 only. No F2-F5, USER publication, TSS/ESP0, CPL3, IRET, syscall/ELF/scheduler/process management, general teardown, remote/Proxmox/VM103, persistent-disk/boot-media/ISO deployment or push operations were performed. No acceptance lock was unlinked. Local production build was baseline-only; no ISO was built.

## Exact deliverable and design outcome

- Read approved B19 closure A–F section and predecessor final report, decisions, STATE and full independent design review.
- Audited private memory owners and real release/map/unmap/growth/structure/publication/CR3 boundaries. Current structure retention does not freeze payload mutation.
- Wrote provisional design.md and obtained two complete independent source-hash-pinned verdicts.
- Wrote and actually executed an independently approved isolated baseline host fixture exposing two missing retention-policy boundaries, with a passing ordinary-use characterization control.
- Ran unchanged baseline full host/B26 serial/parallel and production format/build/ELF checks, preserving actual logs and exact libtest identity readback.
- Updated only the four required current-checkpoint documentation pointers, keeping historical accepted sections intact and original newline conventions.

No private production smoke owner, attempt latch, joint seal, allocation recipe, terminal wrapper or candidate enforcement was implemented. Live src/, tests_kernel/, tests_b26/, Cargo and acceptance source inputs are unchanged. Consequently the proposed `Uninitialized -> Preparing -> Sealed -> Terminal` transitions are NOT runtime implementation claims. Tests A/B/E/F for a real one-shot owner are NOT implemented; C/D have baseline missing-policy RED evidence only, not candidate GREEN.

## Resource policy and design blockers

The first provisional draft proposed two actual ordinary acquisitions (one future payload, one dedicated supervisor sentinel), fixed lease slots, same directory/domain and no new mapping. At most two frames / 8192 bytes is a proposed acquisition bound, NOT an approved full future smoke inventory.

Boundary review `independent_boundary_review.json` rejects full F1 design completion and approves only the limited baseline probe/partial outline. It requires concrete finite future inventory, jointly serialized irreversible guards at real mutation boundaries, a dominating gate for alternate-map CR3 activation and a nonreturning invocation that cannot resume the shell/heap path.

Budget review `independent_budget_review.json` conditionally recommends a possible 12-frame / 49152-byte incremental policy ceiling: payload1, user stack1, transition4, emergency4, sentinel1, arena table1. Existing 16 KiB bootstrap storage motivates a ceiling, not sufficient transition/emergency headroom. The recommendation does not approve implementation, architecture, selected ranges, fixed metadata/descriptor/diagnostic shapes or actual stack adequacy. Future guarded supervisor ranges must fit existing tables; additional tables/contexts reject the candidate or need new review. The two initial frames are a subset of twelve, not additional capacity. Guards are absent virtual slots, not allocated physical frames. No ceiling was silently installed or attributed to the old approved plan.

Actual added production resources: zero frames, zero mappings, zero production owner metadata, zero production static/BSS delta, because production/build source is unchanged. Host probe allocations are per-instance test storage, not retained guest resources. A real F1 owner size, emitted preparation frame budget and minimum-RAM capacity deltas remain unmeasured. Caller/IRQ/NMI/DF stack high-water is UNKNOWN; no inference from type sizes or bootstrap success.

## Enforcement and bypass audit

Source inventory and full reviewer audit identify:
- Frame initialization and malformed-reservation reset; common stamped ordinary allocation; raw and owned release; exact growth claims; runtime/structure pin setters.
- Map/unmap common cores and early owned wrappers; no same-domain alternate-map escape.
- Bootstrap raw table construction and rollback; unpublished structure cleanup; publication metadata.
- Both CR3/CR0-writing helpers and their owner wrapper, including activation of a different fresh map after seal.
- Private raw table writes/zeroing/invalidation whose callers must be dominated by the final seal.

Existing HEAP -> PAGE_MAP -> FRAME_ALLOC order must be preserved. An independent singleton latch must refuse retry before owner locking; leaf checks cannot reacquire a smoke mutex. All acquired leases must reach retained fixed slots before fallible post-acquisition alias checks. A future joint seal must check actual active CR3, not only software directory/enabled observations. Pin no-ops cannot let enclosing transactions continue to backing mutation. Sealed/failure wrappers must drop guards and use lockfree diagnostics then halt, never return into shell/reboot/heap work. There is no proof of these mechanisms in current production source. Arbitrary trusted Ring-0 raw writes are not claimed to be hardware-isolated.

## Runtime RED / control evidence

Isolated fixture root: `fixtures/host_snapshot/Cargo.toml`. Copied host root, memory module and paging source differ only by crate/dependency/module path relocation and an added cfg(test) module; production function bodies are unchanged modulo source newline normalization. FrameLease/allocator and remaining modules are actual original source, not a synthesized mirror. fixture_manifest.json pins originals and initial/current fixture revisions. Live module lists and ignored policy are unchanged.

Exact executed identities (prefix `memory::paging::retained_owner_baseline_tests::`):

| Identity suffix | Actual result | Actual Cargo exit |
|---|---|---|
| f1_baseline_characterization_ordinary_map_unmap_release_remain_valid | 1 passed,0 failed,0 ignored | 0 |
| f1_missing_policy_baseline_retained_map_still_allows_owned_unmap | 0 passed,1 failed,0 ignored, intended missing-policy assertion | 101 |
| f1_missing_policy_baseline_retained_map_still_allows_unpublished_owned_release | 0 passed,1 failed,0 ignored, intended missing-policy assertion | 101 |

`baseline_probe_readback.json` compares all three exact identities to actual --list and requires one runtime execution per command. The evidence wrapper returns zero for expected Cargo101; that wrapper status is NOT a passing Rust test. No assertion was weakened to obtain GREEN. Snapshots cover complete PDE/PTE inventories, pins, payload registry, PageMap state, capacity/diagnostics and current lease/free state. On baseline the forbidden operation succeeds, so each probe reaches its expected bool-assertion failure before the unchanged-state assertion; unchanged-state success is NOT claimed.

Preserved failed setup attempt: baseline_probe_control_01 failed compilation E0507 (PagingStats is not Copy), zero executed tests. Corrected only a scoped read-only stats borrow in the snapshot helper. This is NOT runtime RED. Runtime control/RED evidence is from *_02. Production/probe formatting checks pass exit0.

## Fresh unchanged-baseline verification

| Suite | Serial | Default parallel | Exact identity membership |
|---|---|---|---|
| Kernel host | 343 passed,0 failed,2 ignored,exit0 | same | all345 --list identities match |
| Independently rooted B26 | 116 passed,0 failed,0 ignored,exit0 | same | all116 --list identities match |

Host ignored identities remain maintenance_measurements::measured_frame_scan_states and maintenance_measurements::measured_heap_capacity_loss. No new ignored security tests were introduced. baseline_identity_readback.json records membership and actual statuses; zero selected tests cannot satisfy it.

Production baseline cargo build PASS exit0 with existing warnings; validate_elf PASS exit0. No candidate build exists. Baseline emitted ELF SHA256 `1304df61d0649a21eb091e71e45c37d34ed7e574e448f42cde6608be89501c2a`; file6317300 bytes, .data371964 bytes, .bss1137676 bytes, allocated-section sum2254854 bytes, allocated address span2264076 bytes. These actual baseline measurements in baseline_memory.json are NOT F1 implementation deltas or runtime peak memory. Bootstrap assembly reserves16384 bytes; cumulative stack high-water is unknown.

Guest results: NOT RUN. No Ring-0 F1 fixture was implemented. No 128/512 MiB F1 behavior, real active-CR3 preservation or terminal lifecycle guarantee is established. No owned QEMU was launched by this task.

## Reviews / acceptance / commit policy

Complete boundary and budget artifacts were read; their original source pins were preserved, never rewritten as approval of changed bytes. Boundary verdict is REJECT_FULL_F1_COMPLETION_APPROVE_ONLY_BOUNDED_PARTIAL_DESIGN. Budget verdict is CONDITIONAL_POLICY_CAP_RECOMMENDATION_NOT_IMPLEMENTATION_OR_ENTRY_APPROVAL. Neither is candidate source approval.

Actual predecessor acceptance manifest digest matches its readback; its inherited multiset has65 gates and150 source/build hashes match the baseline. This is provenance only. No mandatory gate identities were added/removed, no canonical runner was launched and no historical 65/65 result is reused. Canonical acceptance is NOT ELIGIBLE until implementation, focused/full/guest verification, review and freeze prerequisites are met.

The local commit records only the independently reviewed partial documentation/probe-evidence milestone, not an accepted F1 implementation. It contains exactly 48 reviewed scoped files, including the supplemental scope verdict; no binaries, ISOs, user files, protected work or generated target directories. The index is empty after commit and Git status is exactly the initial unrelated README/d1/init-document/backup status. Independent post-commit verdict authority is `final_readback.json`; this report does not substitute for that saved verdict. STATE/FINAL_REPORT/evidence_manifest remain live task-local closeout records, not self-referential committed files.

Pre-commit readback `checkpoint_review.json` approved the exact documentation and
isolated baseline-evidence blobs only, with zero partial-checkpoint blockers; it
explicitly rejects any F1 implementation/completion inference. Default staged
whitespace checking then rejected five raw logs for blank lines at EOF. Their
bytes were NOT edited and whitespace checks were NOT weakened: only those five
task-owned logs were unstaged and remain locally preserved/hash-pinned. JSON
summaries remain in scope. Excluded raw logs are baseline_b26_parallel_01.log,
baseline_b26_serial_01.log, baseline_host_parallel_01.log,
baseline_host_serial_01.log and baseline_probe_control_02.log. Supplemental
`checkpoint_scope_review.json` approved the exact reduced 47 blobs plus its own
immutable verdict before commit; the original checkpoint_paths.json remains an
immutable record of the earlier proposal. Default staged/working diff checks
passed, all 51 original approved raw working hashes stayed unchanged and the
staged security scan found no credential/private-key matches. The five raw logs
remain local and are deliberately absent from the commit; no observation bytes
or whitespace configuration were changed to pass checks.

## Remaining F1 / F2 prerequisite / next action

Remaining F1: concrete finite manifest and actual metadata shape; singleton one-shot owner; checked bounded acquisitions and every real failure stage; joint fail-before-side-effect seal; alternate-map CR3 gate; nonreturning terminal path; A–F candidate runtime GREEN; relevant predecessor/full/B26/production/QEMU128/512 verification; exact-family negative controls; independent source approval; source-frozen canonical acceptance and independent final readback. Two isolated REDs do not close any of these implementation obligations.

F2 prerequisite status: BLOCKED by incomplete F1; architectural/entry/emergency obligations remain unresolved and outside this session. No Ring-3 readiness claim.

Next exact command (repository root):
`git status --short && git branch --show-current && git rev-parse HEAD && git diff --check`
Then read the live STATE and complete reviews; revise the concrete F1 manifest/joint-seal/terminal design and obtain independent approval before production edits. Preserve baseline runtime RED artifacts. Later slices may extend Preparing only in a fresh authorized source revision/boot; there is no runtime unseal or second attempt.
