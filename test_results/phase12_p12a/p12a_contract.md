# P12-A executable contract v01 — proposed, NOT implementation approval

## Authority and exact baseline

User's P12-A continuation v4 authorizes only this host policy milestone. Approved
Phase12 design `test_results/phase12_design/design.md` raw SHA256
fe57e4a8ae8c3af541d545319946494c499e06c92cfec572610154aa95f0a880:
sections4/8 (lines41–49/83–85) supply two workers+separate idle, ready FIFO cap2,
UNUSED→READY→RUNNING→READY/RETIRED, no reuse/reclaim, checked inhibition,
coalesced pending reschedule and nonmutating refusals. Section3:28 prohibits
production module/assembly/IRQ/TSS/allocator/runner changes. Section9:95 leaves
A's exact acceptance contract for separately approved choice, not mandatory gates.
All39 review manifest pins and30 inventory inputs verified (preflight_01.json).
Design approval: APPROVE/zero blockers/complete16. Kickoff exists locally ignored,
not committed; no fabricated committed design claim.

F5 HEAD d9cebe28eb5139b6b614b7000688857361e2afc4 equals current HEAD/ancestor.
F5 canonical `test_results/f5acc/r01/acceptance_20261025T060216Z_7g_gea5o/acceptance.json`
raw21247dcb786d68afaf588971561858488f108d12414e89c6b1dfadb5d3a06074,
actual exit0, PASS76; full76 gate multiset stored in preflight_01.json.
Fresh initial host/B26 lists and serial executions are in test_results/p12a/b01/report.json.
Baseline production A and B built BEFORE source/tests, with cargo +nightly build,
repository CWD/default features/debug/target.json, no CARGO/RUST environment
variables; kernel-only cargo clean before each. Both raw ELF hashes are
981f373a7a6530cbcc861261947b9aaa71f69661cb4e2a100b73901c4a1854e4,
also identical to accepted F5. Git status unchanged. Compiler -vV retained.

## Proposed smallest safe choices requiring reviewer approval

These resolve options the design does not fix; none authorizes runtime use.

* Identifiers: u8 worker IDs1..=254;0 reserved idle/unused,255 reserved invalid.
  Any valid not-yet-admitted ID is UnknownId for lookup/completion. Two permanently
  consumed slots per Policy, not two possible numeric identities. Admission order
  fixes FIFO tie-breaking; no priority, quantum, ticks, deadlines or accounting counter.
* Public `State { Unused, Ready, Running, Retired }`, `Context { Idle, Worker(u8) }`,
  `TaskKind { KernelProbe, Cpl3, F5 }`. Only KernelProbe admission is supported;
  Cpl3/F5 refuse UnsupportedKind. These are labels, never execution capabilities.
* `Error { InvalidId, UnknownId, DuplicateId, RetiredId, Capacity, InvalidTransition,
  UnsupportedKind, Inhibited, InhibitOverflow, InhibitUnderflow }`.
* `Slot { pub id: u8, pub state: State }`; `Snapshot { pub slots: [Slot;2],
  pub queue: [u8;2], pub queue_len: u8, pub current: Context,
  pub inhibit_depth: u8, pub pending: bool }`. Snapshot/Slot/enums are Copy/Eq;
  returning them transfers no resources. Policy contains private Snapshot only;
  no externally mutable state, references, globals or callbacks.
* Public API `Policy::new() -> Self` (const), `snapshot(&self)->Snapshot`,
  `state(&self,id:u8)->Result<State,Error>`,
  `admit(&mut self,id:u8,kind:TaskKind)->Result<(),Error>`,
  `request_reschedule(&mut self)->Context`,
  `complete(&mut self,id:u8)->Result<Context,Error>`,
  `enter_inhibit(&mut self)->Result<(),Error>`,
  `leave_inhibit(&mut self)->Result<Context,Error>`.
  No public enqueue, reset, remove, release, resume or reuse API.
* New: both slots Unused/id0; queue=[0,0],len0;current Idle;depth0;pending false.
  Admission consumes first Unused slot, sets Ready, appends once, does NOT switch
  idle immediately. Current Idle with ready workers before an explicit request is
  intentional, not CPU-idle execution. No duplicates; unused queue tail always0.
* Reschedule at depth0: if a worker is current, mark it Ready and append once to
  FIFO tail; dequeue head if nonempty, mark it Running/current; otherwise Idle.
  One-worker yield selects itself. Idle is never queued or a worker Slot. Return
  only an abstract selection. No runnable worker starvation under repeated requests
  at depth0 (each selected at least once per2 decisions); no fairness claim while
  inhibited, without requests or for arbitrary future runtime behavior.
* Reschedule while inhibited: only pending=true; return unchanged current; no slot
  or queue mutation. Repeated pending requests coalesce. Depth is checked u8,
  max255. enter at255 returns InhibitOverflow unchanged. leave at0 returns
  InhibitUnderflow unchanged. Nonfinal leave changes depth only; final leave drains
  pending exactly once by clear+ordinary reschedule; no pending means no selection.
* Complete: only currently Running matching worker can become Retired; selection
  then dequeues next Ready or Idle, without requeuing retired worker. Completion
  while inhibited refuses; no logical retirement of a current inhibited worker.
  Retired slot/ID remains consumed forever in that instance; no physical release.
* Admission while inhibited also refuses (conservative proposed rule), avoiding
  queue edits in the inhibited regime. Otherwise admission allowed with worker
  already Running; existing current unchanged. Full two-slot policy refuses a
  third distinct valid ID, even if both retired. Fresh Policy construction is only
  independent model reset, not reuse of real kernel IDs/resources.
* Error precedence: validate numeric ID first. state: then UnknownId if absent.
  admit: UnsupportedKind; existing ID=>RetiredId if retired else DuplicateId;
  Inhibited; Capacity. complete: UnknownId; RetiredId; InvalidTransition unless
  Running and current matches; Inhibited. All Err returns preserve entire Snapshot.
  Enter/leave errors preserve Snapshot; no wrap/saturation ambiguity. No other
  counters; bounded queue arithmetic is exact, never wrapping.

## Invariants and implementation plan

At most2 consumed slots,2 Ready entries,one Running; current Worker iff exactly
one matching Running slot, otherwise Idle. Every Ready slot occurs once in active
queue, no other slot occurs there; queue tail zero. Occupied IDs distinct/valid,
Unused slot id0. Retired never Ready/Running/admitted again. pending implies
inhibit_depth>0; final leave always clears pending. All state instance-local.
Metadata `size_of::<Policy>() <=1024` bytes; no internal allocation. no_std
compatibility proved with standalone rustc --crate-type lib of policy source,
which begins #![no_std] only under a dedicated standalone crate wrapper (wrapper
uses #![no_std] and #[path] to exact source; source itself uses core/primitives).
No dependencies, unsafe, assembly, ports/register access, atomics, locks, panic!
or unreachable!, recursion, unbounded loops, panics-by-design or global state.
Only scans of2 slots; queue operations over2 cells. Tests may allocate/iterate
bounded finite traces; no production policy instrumentation or test-only semantics.
Private helpers may find slot, pop head, append tail and select after retirement.
Array indices derive solely from checked private invariants and fixed ranges;
review all arithmetic/index bounds, not merely compiler success.

## Placement and runtime classification

Class T design hypothesis: new src/p12a_policy.rs, included ONLY via
#[path="../../src/p12a_policy.rs"] pub mod p12a_policy in tests_kernel/src/lib.rs;
new tests_kernel/src/p12a_policy_tests.rs registered as sibling #[path] pub mod,
exactly matching F5 lib.rs:52–56. src/main.rs's production module graph and Cargo
bin-only manifest do not include the source; no production mod/use/reexport,
static/function pointer/assembly/runtime call/hook allowed. No manifest/features,
target/linker/profile/build-script/interrupt/boot/GDT/TSS/F4/F5 edits.

After GREEN rebuild using same command/environment/path/compiler and fresh
kernel crate, compare ELF with BOTH reproducible baselines; record module graph,
all p12a source references across src (including .s), tests_kernel, scripts and
Cargo manifests. Discover existing f3_full_guest.discover_objdump, use its actual
LLVM symbol tool/disassembler location to confirm no p12a symbols in production.
Record identical linked ELF. If mismatch, one bounded metadata/disassembly look,
then Class P unless independently reviewed alternative; do not apply T shortcut
from source alone. Contract must be revised/reviewed before Class P implementation
verification; full F1–F5 matrix10/8/18/12/12 at128/512MiB and emitted closure then
mandatory, not silently skipped. No concurrent heavy streams/review admission.

## Exact required tests —24, zero new ignored

All names have prefix p12a_policy_tests::. Each is an independent #[test].

1. p12a_policy_tests::empty_policy_selects_idle
2. p12a_policy_tests::admission_does_not_switch_idle
3. p12a_policy_tests::single_worker_repeated_yield
4. p12a_policy_tests::two_workers_fifo_round_robin
5. p12a_policy_tests::admission_order_breaks_ties
6. p12a_policy_tests::last_worker_completion_returns_idle
7. p12a_policy_tests::completion_selects_next_ready
8. p12a_policy_tests::retired_identity_never_reused
9. p12a_policy_tests::capacity_exhaustion_is_nonmutating
10. p12a_policy_tests::invalid_identifiers_are_nonmutating
11. p12a_policy_tests::unknown_identifiers_are_nonmutating
12. p12a_policy_tests::duplicate_admission_is_nonmutating
13. p12a_policy_tests::invalid_completion_is_nonmutating
14. p12a_policy_tests::unsupported_kinds_are_nonmutating
15. p12a_policy_tests::inhibit_latches_without_switching
16. p12a_policy_tests::nested_inhibit_drains_only_at_zero
17. p12a_policy_tests::inhibit_overflow_is_nonmutating
18. p12a_policy_tests::inhibit_underflow_is_nonmutating
19. p12a_policy_tests::inhibited_completion_and_admission_refuse
20. p12a_policy_tests::pending_requests_coalesce_once
21. p12a_policy_tests::fresh_instances_are_isolated
22. p12a_policy_tests::metadata_budget_and_bounded_trace
23. p12a_policy_tests::exhaustive_short_traces_preserve_invariants
24. p12a_policy_tests::deterministic_replay_and_no_starvation

Tests1–8 assert literal idle/FIFO/state traces;9–14 assert exact errors and full
snapshot equality on refusal;15–20 assert checked nesting255/underflow0, pending
coalescing and final drain;21–24 assert isolated instances,size bound,finite traces
and invariants plus deterministic/fair selection. Test23 exhaustively enumerates
all operation sequences of length4 over admit1,admit2,admit3,reschedule,complete1,
complete2,enter,leave; verifies invariants and every refusal's atomicity after each
step (4096 traces,16384 steps). Test24 replays a long fixed legal sequence on two
fresh models with identical snapshots and compares literal alternating IDs under
uninhibited requests, not only implementation-to-itself equivalence.

Logical RED plan: write all tests and register them before implementation; because
no baseline policy exists, create only the declared API with inert behavior as a
clearly labeled temporary red scaffold, preserving its exact raw source. It
compiles, lists exactly24 and executes, but admits no workers/doesn't select them.
Assert literal expected Ready/Worker/FIFO outcomes (e.g. admission test2 must fail
on slot Ready vs Unused). Compiler/import/CWD errors are environmental, not RED.
Then replace scaffold with minimal genuine implementation without changing tests.
The scaffold is test-first executable baseline, never frozen/reviewed as candidate.

## Filter and inherited identity isolation

Preflight narrows rg --lib scripts/tests_kernel and actual phase6 loops/fixtures.
Save filter_audit_01.json before approval with exact full proposed names, inherited
filters, evidence lines and membership comparisons. Inherited filters b11_,
b18_inventory_tests::, phase11_permission_tests::, phase11a2_ownership_tests::,
phase11a2_abi_tests::, mapping_pin_tests::, structure_lifetime_tests::,
numeric_map_authority_tests::, unmap_authority_tests::, generation_ownership_tests::,
generation_ledger_tests::, generation_boundary_tests::,
heap_growth_maps_one_page_on_demand, phase11_gdt_tests::, retained_owner,
exception_abi::tests::, ::f3_, f4_user_arena_tests::, f5_cpl3 must match NO new name
as substring/prefix. B26 is a separately rooted entire suite, not a colliding host
prefix; full host intentionally adds exactly24. Discover any other --lib literal
via AST/source search, including f*_evidence and mock harness; no assumptions from
counts. Compare fresh baseline394 full names (including exact2 ignored) and149 B26
with candidate list/serial/parallel; new host set = baseline plus exact24. No
inherited test/gate/required identities may shrink or be edited.

## Freeze, verification, preservation and acceptance decision

Option A: HOST-ONLY verified milestone, NO new canonical acceptance gates. No
canonical run/final canonical readback applies. No runner/validator edits. This
contract's candidate review is still mandatory and comprehensive, not metadata-only.
F5 PASS76 remains historical exact predecessor, not a fresh P12-A canonical claim.

Mock gate REQUIRED: phase6_verify.source_snapshot():450–490 enumerates both new
.rs files plus modified tests_kernel/src/lib.rs. Snapshot membership234→236 is
an expected observation to verify, not a fabricated pass. Run entire actual
scripts/test_acceptance_harness.py -v with unchanged1049s limit ONLY for that gate;
verify actual declarations/identities (historically95) and all ok/no skips/exit0.

Fresh frozen checks: focused24/serial/list, complete host serial+parallel+list,
B26 serial+parallel+list with exact membership and ignores, cargo nightly fmt
--check for kernel/host plus rustfmt --check on unreferenced policy; standalone
no_std compile; unchanged production build/ELF contract; source-level/module/symbol
isolation; F5 predecessor identity/gate multiset readback; source-before=after,
re-enumeration and protected hashes; parent artifact integrity readback. Freeze
includes actual canonical source snapshot, all policy/test/build/harness/wrapper
inputs, immutable design/contract/review/pins and baseline provenance, no assumed
pin count. No live mutable STATE pinned for reviews; use immutable snapshots.

Class T proven by A=B=AFTER + complete module/source/symbol proof permits skipping
fresh F1–F5 guest reruns and emitted-closure rerun: identical ELF means emitted
instructions/roots unchanged, accepted F5 full closure/history bound to same hash.
Explicitly list skipped matrices in final report, never call them fresh PASS.
Mock still runs because snapshot membership changes. If Class P applies this skip
is invalid. No hardware, QEMU, ISO packaging or canonical launch planned for T.

Parent read-only saved script rehashes freeze/all cited artifacts/reviewer inputs,
checks review self-digest convention (SHA256 canonical JSON excluding self_sha256),
F5 predecessor identity using preflight's authenticated F5 bindings, protected bytes,
no owned processes. Note F5 manifest's FINAL_REPORT artifact deliberately binds an
older historical_self_bound revision, NOT current report bytes; never falsely
compare current report against that old digest. Current report/manifest are pinned
raw in preflight plus accepted closeout receipt/HEAD provenance; preserve this
historical limitation explicitly. No fabricated self-hash of entire self-containing
file; record raw review digest externally as well as content self-digest.

Independent contract review covers all16 required areas, APPROVE0/complete before
source/tests; parent rehashes all inputs. Independent candidate review covers full
source/test delta and all evidence/provenance, APPROVE0/complete after frozen GREEN.
At most2 substantive contract revisions,2 source correction cycles,3 attempts per
defect. Preserve failures/REJECTs; no self-review. Scoped two local commits only
after approval; preserve raw Git blobs and protected work; no push/deployment.

## Historical limitations and future boundary

Historical F1 independent final canonical readback artifact was never produced;
no retroactive claim. F3 conditional one-nested-NMI static2578/16384B bound is not
measured high-water/unlimited recursion survival. F5 terminal CPL3-only/IF0/PIC
masked/nonresumable proof stays unchanged. No NX/W^X guarantee. No runnable tasks,
CPU stacks, runtime scheduler, preemption, timer/IRQ work, context switch, syscall,
loader, cleanup/reclaim, recoverable process or multiple executable CPL3 tasks.
P12-B requires its own bounded ABI/stack/lifetime design, prerequisite resolution,
independent design approval and fresh explicit user authorization. Stop after A.
