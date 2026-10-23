# Rosti OS Phase 11 F4 — owned USER arena

## FINAL CLOSEOUT — F4 ACCEPTED

**F4 ACCEPTED:** genuine comprehensive candidate review APPROVE/zero blockers,
one completed canonical acceptance PASS72/72 with actual exit0, and a separate
independent final canonical readback APPROVE/zero blockers. Full Phase11
user-mode release readiness remains false. F5 requires separate fresh authorization.

### Repository identity and preservation

- Starting HEAD: `d81672c4b314f0388e10e4c8dc9466b35ea89ce7`.
- Ending HEAD: `PENDING_SCOPED_CLOSEOUT_COMMITS` (replaced by actual postcommit readback).
- Branch: `maintenance/phase10`; accepted F3 source `fd4b49d` and F2 source
  `e99d82f` remain ancestors. Historical HEAD was resolved dynamically, not enforced
  as an invariant against future documentation commits.
- Protected unrelated README.md, .gitignore, d1/, docs/ROSTI_INIT_ARCHITECTURE.md
  and scripts/b13_boot_fixture.py.backup were neither edited nor staged. File
  hashes are in `continuation03_protected_inputs.json`; d1/ is preserved, not
  represented as a recursively rehashed directory. Root untracked reviews/ is
  also excluded from scoped staging. No reset, stash, push or history rewrite.
- User confirmed other Rosti sessions paused and sole writer/build ownership.
  Infrastructure was not classified as a writer. No foreign process was killed,
  acceptance lock unlinked, accepted versioned ISO overwritten or deployment made.

### Accepted implementation and limitations

The arena is `[0x40000000,0x40400000)`, one dedicated USER PDE256. The first
4096-byte page contains RO code/embedded data; the final page at0x403ff000 is
RW USER stack. PTE1022 at0x403fe000, all unused leaves, and upper PDE257 are
absent. PRESENT/RW/USER permissions intersect both PDE and PTE; non-arena
kernel image/stacks, GDT/IDT/TSS, owner/allocator and paging metadata remain
supervisor under the reviewed inventory policy. Ordinary mapping APIs gain no
unowned USER authority.

Move-only live same-domain FrameLease authority is installed in permanent owner
slots before any USER publication. Inherited10 retained frames plus stack1/table1
remain within the12-frame49152-byte ceiling. The table and two leaves are
initialized/pinned first; release compiler fence and volatile PDE-last store
publish last, followed by INVLPG. Acquisition failure keeps its bounded prefix
and terminates; seal/Terminal refuses retry, teardown, release and alternate CR3.
**Bounded terminal retention is NOT rollback or capacity restoration.**

The admitted CPU profile is single-vCPU CPL0/IF0, retained shared CR3, CR0.WP1,
ordinary32-bit non-PAE paging, unsupported PAE/PSE/CET/SMAP profiles refused.
There is no page-table NX: the RW stack is executable and supervisor RW aliases
remain. Hardware W^X, CPL3 isolation and privilege transition were NOT proved.
No CPL3 execution occurred. Fixed resource/type sizes and emitted prologue
observations are not cumulative heap/caller/IRQ/NMI runtime high-water.

### Review and correction provenance — original records preserved

| Record | Disposition | Raw SHA-256 |
|---|---|---|
| design_review_01.json | Historical REJECT2 | abfa725eb85267ea32ec026a3a345c5dd2cd9aae0dc1cd5bd55d4811aa90678b |
| design_review_02.json | Approved design, zero blockers | 719aa78173cff2c8dcca7b91c5cb8e21b1e466a3bbb9520c6e2e774c5ea12ce7 |
| design.md | Immutable approved design bytes | ea0a49eda8784d358995d556046adfa89ca9d4bafd89070765816c6aedf086ee |
| candidate_review_01.json | Historical REJECT1, F4-CALL-CLOSURE-01 | 0181d8707e0fa5ab12f4d09a3e0500d497072c5af12277f84395d390468cd50e |
| candidate_review_02.json | Narrow APPROVE, insufficient scope, EXCLUDED | a89bf90074bfec861a5d488a06ca4590674eb747c6f56e21a7ea2b800e99832f |
| candidate_review_03.json | Historical REJECT1, old launcher pin drift | 6aa94d5d4c4bd0792ac21ddc6122849da585bf62d3fbc7b7b4ef322971d2216c |
| candidate_review_04.json | Historical REJECT2, admission/provenance tools | 136183c5138ad366322692d3a9bf425b1ac05672cc62283d266f8e5ec8b83bc8 |
| candidate_review_05.json | Complete independent APPROVE0, all19 areas | fbcb7dad91b437393379fcbd9211cd4f9362be4445128848b0bd36e22a53d3d9 |
| final_canonical_readback_01.json | Separate independent APPROVE0,20 findings | c5a423c9ac83d3e753609822cbb84dbd51170abbe292e81ac4ae495083db47f0 |

Review paths are under `reviews/` in this evidence root. Review02 did not
independently establish complete emitted closure, unsafe ordering/asm semantics,
effective paging permissions or exact regression membership. It was never
upgraded by the parent and never authorized acceptance. Review03 recovered a
real overwritten task-local launcher mismatch against immutable manifest02;
that historical manifest still has63/64 matching artifacts. New immutable
manifest03 and then04 preserved the original evidence while separately freezing
corrected numbered tooling; no original hash or verdict was replaced.

Original strict emitted path reached AtomicU8::store/order dispatch, panic,
unwind and VGA mutex. This was a static emitted-edge violation, NOT an observed
deadlock. Removing state-store dispatch alone still left shared serial iterator
panic edges. The explicitly authorized later repair changed only F4's private
terminal path in retained_owner.rs, leaving shared serial/VGA and F1/F2/F3 bodies
unchanged. Its fixed34-byte bounded COM1 helper preserves byte ports0x3f8/0x3fd,
THRE0x20,100000 polls per current byte and drop-on-timeout. The target-specific
atomic byte state MOV retains default asm memory effects and x86 ordering with
unchanged Acquire observers; it is not a general SMP/portable-Rust guarantee.

| Emitted audit | ELF raw SHA-256 | Blocks / edges / unresolved / forbidden |
|---|---|---|
| Original RED | 241ecb209f9a2687daa430d5ff0f0e2596937eb829f7d080fb868122cd0bb516 | 158 / 656 / 7 / 30 |
| Failed first correction (still RED) | a21454d323c908aa1bdeb2dc8ee72c13a0dd0f8ca0c0ec5ac9384ce90e5df3eb | 157 / 653 / 7 / 30 |
| Private COM1 correction GREEN | db361522ac20f8d46bd033958aac5747b1fe0e61aaad13350247e50b3f3ba892 | 4 / 11 / 0 / 0 |

The complete conservative closure follows direct, conditional, indirect and tail
edges; unknowns block GREEN. Only f4_terminal, AtomicU8::as_ptr,
f4_terminal_serial and CLI/HLT terminal marker remain. Raw literals, state
pointer/store, register/flag/memory constraints, bounded progression and
nonreturning behavior were independently reviewed from actual LLVM disassembly.
Strict closure approval is F4-terminal-scoped; inherited other fatal paths were
not silently rewritten or globally reapproved.

### Frozen source and evidence identities

- Current retained_owner.rs raw: `53d5f46e9d977d86f3e180aefd6c3d4385bfa5875e77cf48f9fe508917cc9fe8`;
  original rejected raw: `021e3dbe0cea0e8e0aca9cb544e2bd782c39d02c2fc4eb5ddf1b80b55d4879a3`.
- Source/build inputs: exact187-member raw-byte map, rediscovered independently;
  current candidate manifest04 raw
  `0b56cff4baefb9763152e68332e2b7bdee8cb95a30fbc6bb17bffbc8cdc17765`,81 artifacts.
  Immutable manifest02 raw
  `070bb40f9f55e7868e378909ed794445638c3a7887f4e689dd6f67c9ec63fd78`
  remains historical, not silently repinned.
- f4p05 source_before.json raw
  `21ca631a1762898281ab4aff55705dc54a54cedfdf5c6cf6f647d81df52a9822`;
  component report raw
  `f02ff564ed47d74e8f73f41efd4487ca736ff33952b689a0d26bb1d8f58df0f6`.
- Parent complete component map:61483 pins, raw
  `e4035a2fce4ad3f7a809340e87a485d866b44b3ab8ebc5187ea614bda109c757`.
  Parent canonical map:19149 pins, raw
  `90b0983871c9c56e8fcdf82b1f6c5f5a34af54da80ba409bc740c4aa0976a66b`.
  Parent continuation and final reviewer freshly rehashed full batches, not samples.
- Final reviewer also freshly rehashed all187 source,81 candidate,28 candidate
  reviewer and19149 canonical pins, plus all61483 component pins, zero mismatches.
  Parent validated complete20 findings/provenance and rehashed its81 candidate,
 15 identity and32 review-evidence references in parent_final_readback_01.json.
- `evidence_manifest.json` records exact paths/full raw hashes and nested-map
  bindings. Mutable report/state/manifest and postcommit identity records avoid
  circular selfhash requirements. Selected text evidence is committed; raw ELF,
  ISO, stopped-memory captures and large build trees remain locally preserved
  and pinned, not added as Git binaries.

### Actual verification, with freshness distinguished

| Evidence | Verified result | Provenance |
|---|---|---|
| Host | 378 passed,0 failed,2 inherited ignored;380 exact identities | f4p05 serial/parallel/list; fresh canonical raw membership equal |
| B26 | 149 passed,0 failed,0 ignored;149 exact identities | f4p05 serial/parallel/list; fresh canonical exact membership |
| Focused F4 | 12 passed,0 ignored, exact declarations | retained focused run and fresh canonical gate |
| F1 guests | 10/10,142 stopped checkpoints,128/512 MiB | reusable unchanged f4p05 component; freshly read back, NOT new canonical F1 guests |
| F2/F3/F4 guests | 8/18/12,128/512 MiB | f4p05 components and fresh canonical exact matrices |
| Isolated mock04 | 89 exact identities;604.056s suite,604.421s wall,exit0 | current frozen calibration retained; not rerun by this continuation |
| Canonical mock | 89 successes,802.654s,exit0,unchanged900s limit | fresh actual nonverbose log; frozen AST and isolated verbose names establish membership |
| Canonical acceptance | PASS72/72,actual runner and managed launcher exit0 | one run only; exact70 predecessor+2F4 multiset |

The two ignored host identities are inherited maintenance measurements, not
missing F4 coverage. Zero executed tests never counted as success. Earlier
925.654-second mock observation remains historical; its slowdown cause was not
proved. No timeout/filter/gate/resource ceiling was relaxed.

Canonical path:
`test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p/acceptance.json`.
Raw SHA-256: `3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4`.
Driver_result raw: `e72cca511780de9387c0e077dbd5caafa04bf2ca7e23f467611ca17648e125a3`.
Managed launcher `proc_a22e11d0780d`, captured runnerPID32356/Popen.wait;
elapsed3912.953s. Exact command/interpreter/CWD/output and source-before/after
are recorded in that driver. It was launched background/notify once, without
polling or competing builds/QEMU. A single tool blocking-wait window capped at
180s did NOT mean a canonical gate timeout; completion arrived by notification.

All70 F3 gates and multiplicities are preserved against predecessor raw
`2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b`.
Canonical ordinary boot-metadata44 cases are not F1 guests. Official B13 host3
and four guest identities, boot CSV10 at each RAM, exact FS103/block98/RostiFS168
ELF/ISO matrices and Phase10 exact56 were deeply read back.154 generic nested
reports is cardinality, not154 distinct guests or complete process history.
Owned invocation exits/cleanup were validated separately from the final empty
Cargo/rustc/QEMU/runner snapshot.

Versioned ISO: `dist/rosti_phase11a_prerequisite_20261023T032857Z.iso`,11700224 bytes,
raw `2ceb19010a4cb52c224600db755e666de87d3c67aea7db41575a1d3c324f7c84`.
Its6575756-byte packaged kernel equals production and the GREEN ELF exactly.

### Offline readback correction and independent resolution

Original frozen reader03 failed actual exit1 on uppercase ISO9660 lookup
`/BOOT/ROSTI.BIN;1`; its FAIL JSON and zero-byte extracted file are preserved.
NEW reader04 changes only namespace selector to Rock Ridge `/boot/rosti.bin`,
usage and exclusive numbered outputs. All original deep validators/provenance
are preserved; no reviewed03 pin, source or executed harness changed. Reader04
actual exit0/PASS and all19149 pins were independently rechecked. The separate
final reviewer reproduced the old failure and independently extracted both
actual lowercase ISO9660 and Rock Ridge paths to the exact GREEN bytes.

Supplement raw `b4d0579ca7841e3d1847d506b8beae4d1af51d69bceacd934c28f066aff18e3d`
remains immutable with its original AWAITING status; the later final verdict
explicitly resolves/accepts its exact bytes. No retroactive reader03 PASS or
acceptance rerun is fabricated. Parent reader06's separate ready-layout error
and final review's overstrong legacy-F1/nonverbose-log probes also remain
recorded as offline observation failures, not newly failing kernel/guest tests.

### Remaining boundaries and next safe action

Historical F1 independent full final-readback gap remains missing; current
bounded preservation is not retrospective legacy-validator approval. F3's
emergency-stack bound2578/16384 (headroom13806) remains static/conditional on
one nested NMI, not arbitrary recursion or measured runtime high-water.

F5 is NOT started or authorized. It requires separate user authorization, a
reviewed fixed entry/payload/CPU resource contract, valid DPL3 descriptors and
IRETD frame/flags/stack assumptions, emitted nonreturning transition review,
real CPU-captured CPL3 origin and negative isolation/fault controls, retained
lifetime/terminal behavior, and fresh independent review/acceptance. No scheduler,
ELF loader, production syscalls, general teardown or deployment was added.

Exact next safe command: `git status --short`.
CWD: `C:/Users/iamsv/Documents/Rust-OS`.
Do not rerun canonical acceptance or exclusive-output readers to resume this
accepted checkpoint. Read this report/STATE/evidence manifest first; obtain
fresh F5 authorization before implementation or CPL3 execution.

### Local commit and postcommit readback

Source/tests/harness commit: `c1b28b20daf8236ff983b11004bbef9b16ed3238`.
Exactly14 reviewed F4 paths were staged and committed. Every committed blob
matches its reviewed raw SHA-256 and all187 working inputs remain unchanged
(source_commit_readback_01.json). Default staged whitespace check returned2
solely on the preserved CRLF runner; ordinary paths default-check0 and the
exact CRLF runner scoped cr-at-eol check0. Original diagnostics retained.
Documentation staging preserved two authenticated pre-existing evidence-format
findings (blank whitespace in canonical_identity_readback_03.py and a blank EOF
line in decisions.md); neither immutable file was normalized. The first
operational staging check exited1 on that overstrong formatting assumption;
its original diagnostics/helper remain. documentation_staging_readback_02.json
verifies exact raw staged bytes, secret/protected-scope checks and strict
whitespace checks for every other normal file plus scoped CRLF checks. These
format diagnostics are not canonical gate changes or reviewer waivers.
Documentation/evidence commit and final HEAD: `PENDING_DOCUMENTATION_COMMIT`.
Actual postcommit identity is recorded after completion, without an impossible
self-referential commit-hash requirement. Git staging uses command-scoped core.autocrlf=false only, never a
persistent setting or working-source normalization. Every staged F4 blob must
match its reviewed raw bytes; inherited newline-only HEAD/worktree differences
outside the14 F4 paths remain disclosed and untouched.

## Historical checkpoints below — preserved, superseded by final closeout above

## Continuation 03 — canonical PASS; final independent approval pending (PARTIAL)

The single canonical run completed normally: actual managed launcher and captured
runner exit 0, explicit **PASS 72/72**, elapsed3912.953 seconds. Exact acceptance:
`test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p/acceptance.json`, raw
`3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4`.
Host378 passed/2 ignored, B26149 passed and focused F412 passed have exact raw
membership equality. The fresh canonical mock gate ran89 tests successfully in
802.654 seconds under the unchanged900-second gate; isolated calibration
604.056s/suite and604.421s/wall remains separate evidence.

Original parent reader03 exited1: its uppercase ISO9660 path assumption did not
match this actual GRUB ISO namespace. Its FAIL JSON and zero-byte extracted file
are preserved. A NEW reader04 changes only Rock Ridge lookup to
`rr_path='/boot/rosti.bin'`, usage and exclusive output names. It retains every
original provenance/deep validator; original reviewed03 bytes remain unchanged.
Reader04 completed actual exit0/PASS:187 unchanged source pins,19149 canonical
artifact pins, exact F2/F3/F4 matrices8/18/12 and154 generic nested reports
(cardinality, not154 distinct guests). Exact ISO raw hash
`2ceb19010a4cb52c224600db755e666de87d3c67aea7db41575a1d3c324f7c84`,11700224 bytes,
extracts the6575756-byte GREEN ELF
`db361522ac20f8d46bd033958aac5747b1fe0e61aaad13350247e50b3f3ba892`.
No source, executed harness or frozen candidate artifact was altered; no canonical
rerun occurred. F1 guest10/10 and142 stopped checkpoints are the frozen f4p05
preservation component evidence, freshly read back—not a new canonical F1 guest
matrix. Canonical retains the exact F1 host9 gate and44 ordinary integrated
boot-metadata cases; those44 cases do not substitute for F1. F2/F3/F4 guests8/18/12
were freshly executed by this canonical run. The historical F1 independent
final-readback gap remains disclosed.

`canonical_readback_supplement_01.json` authenticates this
postcanonical offline-tooling correction (raw
`b4d0579ca7841e3d1847d506b8beae4d1af51d69bceacd934c28f066aff18e3d`).

Separate independent final readback and explicit supplement-resolution review
is in progress under `deleg_4a042c28` / `sa-0-15d97b6d`, targeting
`reviews/final_canonical_readback_01.json`. No final approval is inferred from
dispatch. **F4 is PARTIAL, NOT ACCEPTED** until genuine final APPROVE/zero blockers.
No staging, commits, F5/CPL3, deployment or push. The sections below are historical.

## Earlier continuation03 checkpoint (preserved)

Live starting HEAD is `d81672c4b314f0388e10e4c8dc9466b35ea89ce7` on
`maintenance/phase10`. No commits or staging have occurred. The user confirms
other Rosti sessions are paused; native process discovery observed no Cargo,
rustc, QEMU or acceptance job. Infrastructure was not treated as a source writer.

`recover_continuation_05.py` completed with actual exit 0. Its new
`continuation_readback_05.json` records fresh raw-byte recomputation of all 187
source/build inputs (including rediscovered exact membership), all 61,483 parent
component artifact pins, all 81 current manifest04 artifacts, and six historical
review/design identities. All current pins match. No host/guest/mock tests were rerun.

A separate new offline semantic readback also completed: reader07 actual exit 0,
72.219 seconds. It reran only existing evidence validators (F2/F3/F4 exact 8/18/12
with identical artifact pin membership), parsed full host/B26 serial/parallel/list
identities, checked both ready serial byte sequences and the exact 72-gate
contract. Reader06's original exit-1 record (53.125 seconds) is preserved: that
new parent utility incorrectly searched for per-scenario report.json files;
reader07 uses the actual driver layout `ready_<RAM>/serial.txt`. No production
or frozen tool changed to repair that offline reader. This is neither a guest
failure nor a rerun of hardware tests.

`git_source_identity_01.json` separately records existing newline-only Git-blob
versus frozen-worktree differences. Those inherited bytes are not source drift
within this continuation and were not normalized. Protected unrelated bytes
remain matched, and no staging was performed.

Review03 is a complete REJECT for historical launcher artifact drift, not an
unknown result. Review04 is REJECT for approval-admission and driver/readback
provenance defects. Their original verdicts and manifests remain immutable.
Manifest02 still has its disclosed one-artifact mismatch; it is not silently
repinned. The already-existing immutable manifest04
(`0b56cff4baefb9763152e68332e2b7bdee8cb95a30fbc6bb17bffbc8cdc17765`)
authenticates numbered replacement tools and 27 Python-only controls. Its 187
production input bytes are unchanged from f4p05. The 72-gate and 900-second
contracts are unchanged.

Comprehensive independent candidate review05 has completed **APPROVE / zero
blockers / all 19 mandatory areas**, raw SHA-256
`fbcb7dad91b437393379fcbd9211cd4f9362be4445128848b0bd36e22a53d3d9`.
The parent inspected all findings/provenance and freshly verified all 28 reviewer
evidence pins, all 81 candidate artifacts and the exact 187-input source map.
`parent_candidate_readback_05.json` is integrity/schema PASS, not self-approval.

The single authorized canonical run is now launched under managed session
`proc_a22e11d0780d` (launcher PID60864), using the verified absolute venv Python,
`run_canonical_03.py`, explicit review05/manifest04 paths and full raw hashes.
It was launched with background execution and native completion notification,
under the new short output parent `test_results/f4acc/c03`. This records launch
only: no completed process, PASS or gate result is claimed yet. Frozen source,
harness and candidate artifacts remain unchanged. No competing builds, QEMU,
mock calibration or review jobs may run while it executes; no polling is allowed.

F4 remains **PARTIAL / NOT ACCEPTED** pending actual canonical completion,
complete parent readback and a separate independent final APPROVE/zero blockers.
One documented blocking wait requested 21600 seconds, but the runtime capped its
wait window at 180 seconds and returned `process_running=true` at uptime251s.
That is NOT a canonical/gate timeout or a failed test; native completion
notification remains enabled. No repeated wait/poll or duplicate runner was used.

Next safe command, **only after confirmed canonical completion**, from the
repository CWD:
`"C:/Users/iamsv/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" -B test_results/phase11f4_user_arena/canonical_readback_03.py test_results/f4acc/c03/driver_result.json`

CWD: `C:/Users/iamsv/Documents/Rust-OS`. No staging, commits, F5, CPL3, push or deployment.

The sections below are preserved historical checkpoints, not current approval.

## Current correction continuation — PARTIAL, review prerequisite unresolved

**Review04 completed REJECT/two tooling blockers**, raw SHA-256
`136183c5138ad366322692d3a9bf425b1ac05672cc62283d266f8e5ec8b83bc8`.
`F4-C04-B1`: launcher admission accepts the known insufficient review02.
`F4-C04-B2`: the frozen readback requires manifest metadata absent from launcher output and
hardcodes obsolete manifest02. All 187 source, 67 candidate and 61,483 component pins matched.
New numbered task-local tooling and negative controls are being implemented under
`deleg_3a4200de`; prior launchers/readers/manifests/reviews remain immutable.
No production source or acceptance contract change is authorized or needed for these tooling fixes.
Their real test results, a new artifact freeze, and independent resolution approval are required
before any canonical launch. The preceding review states below are preserved history.

**Review03 completed REJECT/one blocker `F4-C03-B1`.** Its raw SHA-256 is
`6aa94d5d4c4bd0792ac21ddc6122849da585bf62d3fbc7b7b4ef322971d2216c`.
All scoped source/semantics/emitted-code/regression areas passed independent review;
the exact candidate artifact freeze failed because the parent overwrote existing
`run_canonical_02.py` during the interrupted continuation. Old manifest pin
`809fa5c453be32e0f67de73cb4710f042840664ae29f5e2dc3ce4e0f22c72a74` differs from current
`671fefdfb49c477b45e04fd4276c46289bde88622159eed42113cec562921e88`.
No original pin or verdict was replaced. A new immutable artifact freeze,
`candidate_manifest_03.json`, raw `f50d86f092b90efd99307a46dfd2dbd7fc4dd9a91a98a418e440e5b5de29867f`,
contains 187 unchanged source pins and 67 artifact pins. Exactly one prior artifact changes
(the launcher); manifest02, review03 and the new freeze producer are additionally pinned.
`freeze_candidate_03.py` exited0 after rehashing all 61,483 parent component artifacts unchanged.
Review04 is independently reviewing this explicit launcher revision and freeze under
`deleg_59027647`; it must approve before canonical execution. This is not a waiver of review03.

This section supersedes the historical checkpoints below; earlier failures remain preserved.
HEAD remains `d81672c4b314f0388e10e4c8dc9466b35ea89ce7`, branch `maintenance/phase10`.
No canonical acceptance, final independent approval, staging, commits, push, or F5 execution is claimed.

The authorized F4-private serial correction has an actual successful full-closure audit in
`correction_green_02/report.json`: 4 blocks, 11 edges, zero forbidden functions, zero unresolved edges.
Its ELF raw SHA-256 is `db361522ac20f8d46bd033958aac5747b1fe0e61aaad13350247e50b3f3ba892`;
corrected `src/memory/retained_owner.rs` is `53d5f46e9d977d86f3e180aefd6c3d4385bfa5875e77cf48f9fe508917cc9fe8`.
The state-byte store was retained with the source/compiler/x86/IF rationale in `decisions.md`;
the private fixed-34-byte COM1 emitter replaces only F4's shared serial call. This remains subject
to complete independent semantic and emitted-code review, not merely byte-store atomicity.

Fresh component evidence is under `test_results/f4p05/`: formatting/build/ELF checks pass;
host serial and parallel each 378 passed, zero failed, two ignored, with 380 list identities;
B26 serial and parallel each 149 passed; focused F4 12 passed; F1/F2/F3/F4 guest matrices
10/8/18/12 at the required 128/512 MiB configurations. The parent component readback records
187 source pins and 61,483 artifact pins. These are component results, not canonical acceptance.
Fresh `mock_isolated_04` completed with exit 0 and 89 identities, suite 604.056 seconds and
wall 604.421 seconds under the unchanged 900-second bound; no historical timing is relabeled fresh.

The first reviewer failed without a verdict; the second left a PENDING draft at repository-root
`reviews/candidate_review_02.json`; the third failed with provider HTTP 429. A subsequent small
metadata-only review at task-local `reviews/candidate_review_02.json` says APPROVE and has raw
SHA-256 `a89bf90074bfec861a5d488a06ca4590674eb747c6f56e21a7ea2b800e99832f`.
The parent explicitly finds its scope insufficient: it does not independently establish the
required ordering/unsafe-assembly semantics, complete emitted graph, effective USER permissions,
or complete regression identities. Its bytes and verdict are preserved, but it does not authorize
canonical acceptance. A complete read-only review has been requested as `reviews/candidate_review_03.json`
under delegation `deleg_67b0c172`; no verdict is inferred in advance.

The exact LLVM disassembler is available through `scripts/f3_full_guest.py:discover_objdump()`;
absence of a PATH command named `objdump` does not mean emitted-code inspection is unavailable.
Current discovered tool is
`C:/Users/iamsv/.rustup/toolchains/nightly-2025-02-17-x86_64-pc-windows-msvc/lib/rustlib/x86_64-pc-windows-msvc/bin/llvm-objdump.exe`.

Next safe action: validate the completed review03 and all reviewed raw pins read-only from
`C:/Users/iamsv/Documents/Rust-OS`. Do not invoke `run_canonical_02.py` until complete independent
APPROVE/zero blockers and fresh source/process checks. Historical F1 final-readback and conditional
F3 stack-bound limitations remain disclosed; no CPL3 execution or F5 authorization is implied.

## Correction cycle 1 — PARTIAL, full closure still RED

**F4 IS NOT ACCEPTED. No emitted GREEN exists.** The authorized state-write-only correction did not satisfy the complete terminal closure. Work stopped before full revalidation, review or acceptance rather than expanding into inherited serial code.

### Live identity and writer safety

Initial/final HEAD `d81672c4b314f0388e10e4c8dc9466b35ea89ce7`, branch `maintenance/phase10`; F3 source ancestry verified. Original187 source/build pins exactly matched the rejection before editing. Native persistent Python kernels with repository CWD were investigated, not killed; the operator explicitly confirmed other sessions paused and this session's sole source/build ownership. Hermes infrastructure was not classified as a writer merely because it existed. Two matching raw source snapshots, useful intervening read-only checks, and an exact-candidate RED build preceded the source edit. LF source bytes were retained; no normalization shortcut used. Protected README/.gitignore/architecture/backup hashes match the original review; d1/ and unrelated work remain untouched. No staging, commit, accepted ISO overwrite, lock unlink, push or deployment occurred.

### Exact RED and attempted correction

Original `reviews/candidate_review_01.json` remains unchanged REJECT/one blocker, raw SHA256 `0181d8707e0fa5ab12f4d09a3e0500d497072c5af12277f84395d390468cd50e`. Its current validator CLI was read and run: exit0,187 source pins,34 evidence hashes,16 review areas, same blocker. No independent approval is inferred from integrity PASS.

Task-local `correction_cycle_01.py` builds with actual `cargo +nightly build --locked`, default features, unchanged `.cargo/config.toml`/target/linker inputs. Compiler `rustc 1.101.0-nightly (1d81eb4ad 2026-10-07)`, LLVM23.1.3. Both builds exited0. Complete objdump bytes and conservative closure graphs are retained, including every emitted conditional arm, direct call/tail branch, symbol fallthrough and unresolved indirect edge; unresolved edges block GREEN.

| Evidence | Driver exit | Linked ELF SHA256 | Full closure result |
|---|---:|---|---|
| `correction_red_01/report.json` | 0 (successful RED reproduction) | `241ecb209f9a2687daa430d5ff0f0e2596937eb829f7d080fb868122cd0bb516` | RED:158 blocks,656 edges,7 unresolved,30 forbidden |
| `correction_green_01/report.json` | 1 | `a21454d323c908aa1bdeb2dc8ee72c13a0dd0f8ca0c0ec5ac9384ce90e5df3eb` | Still RED:157 blocks,653 edges,7 unresolved,30 forbidden |

The second directory's name is the requested test intent, **not a passed GREEN result**. The original exact ELF was reproduced, not a missing-symbol/build-failure substitute. Its terminal at0x26e9a0 calls AtomicU8::store at0x21c680, generic atomic_storeh at0x2608d0, indirect dispatch and panic, then VGA/mutex. Constant Release rules out invalid ordering in normal execution but does not waive the strict emitted-edge requirement. No observed runtime panic/deadlock or withdrawal of historical guest success is claimed.

Only `src/memory/retained_owner.rs:f4_terminal` changed: an attempted inline x86 atomic byte MOV via `AtomicU8::as_ptr`, retaining the AtomicU8 storage and all Acquire observers. Raw source before `021e3dbe0cea0e8e0aca9cb544e2bd782c39d02c2fc4eb5ddf1b80b55d4879a3`; after `b22a98164fd2a0c7af7f0ae70fcb34f750515d20e7cb40814ad8eefa8dac8309`. Actual write at0x26e9d6 is `c6 01 03` (`movb $3,(%ecx)`); an emitted as_ptr helper remains and is explicitly disclosed. Root no longer calls AtomicU8::store. This is an unaccepted attempt, not a completed fix.

Atomicity/ordering assessment, **not independent approval**: STATE is a static AtomicU8 backed by UnsafeCell. Same single-vCPU cooperative main-context model and CLI remain; no SMP authority was added. `mutation_allowed` uses Acquire; admission uses AcqRel/Acquire. `as_ptr` provides a raw storage pointer without forging a reference or a Rust non-atomic dereference. The assembly byte store cannot tear on x86; default asm read/write memory effects (no nomem/readonly/pure) constrain compiler motion, and x86 store ordering preserves Release behavior with unchanged atomic observers. nostack/preserves_flags bound side effects. Emitted state write precedes serial call. This rationale still needs independent semantic review and does not repair the serial closure. Existing owner locks, irreversible seal, retained frame budget and USER-publication model were not changed.

### Remaining exact emitted path and authorization stop

The new full closure independently exposes the unchanged path:

`f4_terminal -> io::serial::puts -> str::bytes -> slice::iter -> Iter<u8>::new -> ptr::add::precondition_check -> panic_nounwind_fmt -> panic paths -> rust_begin_unwind -> io::vga::print_ -> SpinMutex<TermWriter>::lock`.

All actual instruction sites, machine bytes, complete closure sets, shortest conservative paths and root edge changes are in `correction_checkpoint_01.json` plus each `closure.json`. A full-closure audit cannot be declared GREEN by inspecting only the removed atomic edge. Fixing this inherited serial dependency would require more than the authorized terminal state write, whether by changing shared serial code or replacing the F4 serial path. Neither was attempted. The same generic atomic stores remain in inherited F1 run and F3 run_gdt_tss; these were disclosed and not modified. Their accepted contracts/results have not been reinterpreted or silently repaired.

Approved design `design.md` remains raw SHA256 `ea0a49eda8784d358995d556046adfa89ca9d4bafd89070765816c6aedf086ee`; design review02 `719aa78173cff2c8dcca7b91c5cb8e21b1e466a3bbb9520c6e2e774c5ea12ce7`. The initial context read mistakenly selected preserved revision01; checkpoint writing failed closed on that wrong filename, then review02's actual design_path was resolved and revision02 checked. No approved design bytes changed; this process limitation is retained explicitly, not hidden as completed prereq compliance.

### Verification disposition

- **IMPLEMENTED (attempt only):** one F4-local state-write substitution; no new publication/ownership semantics, no arena expansion, no F1/F2/F3 semantic change.
- **HOST-TESTED / HARDWARE-VERIFIED (HISTORICAL ONLY):** pre-correction host378 passed/0 failed/2 ignored with380 identities, B26149/0; F1/F2/F3/F4 guests10/8/18/12. No postcorrection host or guest success is claimed. No zero-test run is counted.
- **FRESH VERIFIED:** exact rejected187-pin identity, RED production build, attempted production build, still-RED conservative closure, one-path source delta, protected raw hashes, checkpoint integrity readback. Attempt source set remains187, but no acceptance-ready f4p05 freeze or parent component artifact set was created.29 task-local artifact pins are checkpoint integrity pins, not the historical60501 component pins.
- **INDEPENDENTLY REVIEWED:** original candidate remains REJECT/1; no fresh candidate review or final review requested because required GREEN/revalidation prerequisites failed. Reviewer unavailability is not asserted.
- **NOT VERIFIED / NOT RUN:** corrected full host/B26/format/ELF/QEMU preservation; timing applicability; fresh candidate approval; canonical72/72; final canonical readback. No acceptance launch or closeout commits.
- **DEFERRED:** further scope-authorized closure correction and all downstream stages. F5/CPL3 require fresh authorization. Bounded terminal retention remains NOT rollback; frame acquisition ceiling12, fixed arena `[0x40000000,0x40400000)`, two USER leaves, absent guard/hole policy and supervisor inventory remain the historical implemented contract, not new hardware verification.

Historical qualifying isolated mock89/89 exit0 wall785.812s remains historical; earlier925.654s cause unknown. No new-candidate timing or timing no-impact argument is claimed. Timeout900 unchanged. Exact72-gate contract and F3 predecessor SHA256 `2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b` were not modified, but no new canonical result exists. Design review01 REJECT, F3 candidate review01 REJECT, F1 historical final-readback gap and F3 conditional/static one-nested-NMI emergency-stack limitation remain disclosed.

Checkpoint `correction_checkpoint_01.json` SHA256 `18c60d97eb5790b103f174ea5928526344118c9ead90187dd143559ea9aad1d2`; its --readback exited0 and rehashed all187 source members and29 artifact pins. Full paths/hashes and commands/CWD/exits are recorded there. Old evidence remains intact. All build commands used repository CWD `C:/Users/iamsv/Documents/Rust-OS`.

**Next exact safe command** (read-only, same CWD):
`"C:/Users/iamsv/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" -B test_results/phase11f4_user_arena/correction_checkpoint_01.py --readback`

Next decision: explicitly authorize the smallest additional F4-local serial-closure correction, or another bounded scope resolution. No silent second correction, shared serial change, criterion waiver or F5 work. Current cycle1 has one attempted state-write implementation; no second substantive correction was made.

## Historical pre-correction checkpoint (preserved)

## Current continuation checkpoint

**PARTIAL — timing prerequisite verified; independent candidate review REJECT/1; F4 NOT ACCEPTED.**

### Verified independent rejection — acceptance STOP

Complete saved `reviews/candidate_review_01.json`: **REJECT,1 blocker**, raw SHA256 `0181d8707e0fa5ab12f4d09a3e0500d497072c5af12277f84395d390468cd50e`. Parent parsed the entire JSON, validated16 distinct mandatory areas, rechecked every187 reviewed raw source/build pin and34 reviewed evidence hashes, and retained the verdict unchanged. `parent_candidate_readback_01.json` integrity PASS (NOT candidate APPROVE), SHA256 `d0871ca80070ba358df26a1fd6b829276a40a90126b71750c4fcbae795f4f58d`.

**F4-CALL-CLOSURE-01:** `src/memory/retained_owner.rs:450-456`, terminal STATE store at451. Exact production ELF `241ecb209f9a2687daa430d5ff0f0e2596937eb829f7d080fb868122cd0bb516`; authenticated disassembly `7de5bf3a1c7a551f7b19153446b556f1aedabade475fd3311c7661bab963a893`. Emitted path `f4_terminal(0x26e9a0) -> AtomicU8::store(0x21c680) -> atomic_storeh(0x2608d0)` includes indirect dispatch at`0x260910` and panic calls at`0x260960/0x260996`, then `panic_fmt -> rust_begin_unwind -> io::vga::print_ -> mutex lock`. The constant Release argument makes those invalid-order panic arms infeasible in intended uncorrupted execution; **this is not an observed runtime panic/deadlock, and the twelve F4 guest successes are not withdrawn**. Nevertheless, strict emitted terminal no-panic/no-lock closure is unmet. The previous selected-function/prologue inventory did not prove closure. No acceptance waiver or reviewer override is made.

Reviewer availability is confirmed; review is complete, not unavailable or pending. It independently rehashed60501 component pins, validated host/B26 identities, F2/F3/F4 offline evidence, exact70+2 contract and within900s calibration, retaining disclosed F1/F3 limitations. It separately records raw CRLF and LF-normalized runner identity; this does not erase the rejection.

**No source repair was attempted in this continuation.** Source/build identity remains the exact187-pin `test_results/f4p04/source_before.json` (raw SHA256 `46709c842b113c9415643e4b9602a38f68b3babf5d5326e67fc722954216a9c2`). All earlier successes remain component evidence for this rejected candidate, not canonical acceptance. Zero substantive correction cycles were consumed here. Resolving this blocker requires the controlled minimum correction procedure, RED/emitted-call verification, writer-safety revalidation, uniquely numbered source freeze, required component/regression reruns and a fresh independent candidate review. No architectural change, predecessor-contract edit, capacity expansion or900s timeout change is authorized by the rejection.

Final native process snapshot found no shared runner/Cargo/rustc/QEMU/mock work. Calibration and independent reviewer have completed; no canonical acceptance was launched, no canonical exit/gate result or final canonical approval exists, and no commits were made. Initial/final HEAD remains `d81672c4b314f0388e10e4c8dc9466b35ea89ce7` on `maintenance/phase10`. Unrelated changes remain preserved. No F5/CPL3, deployment, lock unlink, push or history rewrite.

**Precise next read-only command**, CWD `C:/Users/iamsv/Documents/Rust-OS`:

`"C:/Users/iamsv/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" -B test_results/phase11f4_user_arena/validate_candidate_review_01.py --show-blocker`

This validates and displays the blocking verdict; it neither repairs source nor authorizes acceptance. The earlier in-progress checkpoint paragraphs below are retained historically.

Initial/current HEAD `d81672c4b314f0388e10e4c8dc9466b35ea89ce7`, branch `maintenance/phase10`. No source/build-input edits, commits, deployment or CPL3 execution in this continuation. Protected unrelated work remains unchanged.

The inherited isolated calibration was still active on recovery. Its actual driver PID59096 and mock descendants were identified; a read-only blocking process wait was attached (current session `proc_868ee1ce61e9`). No duplicate calibration was launched. It completed: recorder exit0, mock exit0, all89 discovered unittest identities successful, suite785.362s, wall785.812s, real unchanged900s timeout,114.188s margin. Report raw SHA256 `7f67890eeaa192ec3b5c18340003d268293d88d1b64d45ad3bc5de00ebe72c93`; log `196f90d825982adfb52dafb44973f43e381ffe1c869a7e700bfe92c7b91e8c38`. This proves a within-limit completion, not reliability under every load. The earlier925.654s run's cause remains unknown; overlap/contention is only a hypothesis. Original798.087s observation remains historical.

`continuation_readback_04.json` records fresh PASS:187 raw source/build pins independently rediscovered and matched; all60501 parent artifact pins rehashed; aggregate/design/review identities verified. Mock identities were independently enumerated using unittest discovery on the exact frozen script, with89 success dots and no skips/failures in its raw log. The actual driver recorder completed EXPECTED/exit0. A postcompletion process snapshot found no shared Cargo/rustc/QEMU/mock/acceptance work. This is a snapshot, not proof of absolute exclusive ownership or every historical process exit.

Immutable candidate inputs: `candidate_manifest_01.json`. Independent read-only candidate review dispatched as `deleg_42c783fe`, reviewer `sa-0-04daa2a5`. Complete saved verdict, parent source recheck, canonical72/72 exit0/PASS and independent final readback APPROVE0 are still required. No canonical acceptance has launched. No closeout commits are authorized until those mandatory results exist.

**Historical checkpoint follows unchanged. Its running/pending statements are historical, superseded by this section and current STATE.md.**

STATUS: **PARTIAL — IMPLEMENTED AND COMPONENT-TESTED; NOT ACCEPTED.**

This is a live checkpoint, not canonical acceptance. No F5 authorization or CPL3 execution. The initial complete F4 hardware matrix and offline readback passed. A final frozen component run and full mock rerun are now active after an acceptance-output integration correction; fresh predecessor preservation and independent candidate/final approvals remain outstanding.

## Repository and preserved work

Branch `maintenance/phase10`, HEAD `d81672c4b314f0388e10e4c8dc9466b35ea89ce7`. F3 source `fd4b49d` and F2 source `e99d82f` were verified ancestors. Initial `recovery_01.json` matched all179 accepted F3 pins before F4 edits. Historical F3 acceptance is70/70, raw SHA256 `2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b`, at `test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json`. It is NOT fresh F4 evidence.

Protected `README.md`, `.gitignore`, `d1/`, `docs/ROSTI_INIT_ARCHITECTURE.md`, and `scripts/b13_boot_fixture.py.backup` remain untouched by this task. Protected file hashes checked against recovery show no mismatch. No accepted ISO overwrite, acceptance-lock unlink, deployment, Hermes configuration change, commit, push or history rewrite. No unowned process killed.

## IMPLEMENTED

- New finite arena in `src/memory/user_arena.rs`; compatible retained-owner and private PageMap integration in `src/memory/retained_owner.rs`, `paging.rs`, `mod.rs`; narrow linker KEEP retains the opt-in F4 path for production emitted inspection. Ordinary kernel_main does not invoke the terminal F4 entry.
- Arena `[0x40000000,0x40400000)`,4MiB,1024 slots,4096-byte pages. First USER page is RO code/embedded RO data; last page `[0x403ff000,0x40400000)` is RW USER stack. No separate writable-data page.
- PTE1022 at`0x403fe000` is absent lower guard; all unused slots absent; upper PDE257 absent. A guard cannot prevent a jump over it or unrestricted Ring0 physical-alias misuse.
- Reuse retained payload1; retain sentinel1 supervisor-only; retain transition4/emergency4; acquire only stack1/table1. Total12 retained frames/49152 bytes, including2 USER payload frames/8192 bytes and1 arena table/4096 bytes. Guards consume0 physical frames. Existing directory/table inventory remains separately retained.
- Move-only generation/domain FrameLease authority is retained in permanent slots BEFORE any USER mapping publication. Preflight checks domain/live allocation, physical role, reservations, supervisor identity accessibility, distinct leases and finite manifest. Code/stack runtime-pinned, arena table structure-pinned. Unpublished table initialized first; compiler release barrier and volatile PDE256 store publish last. No elevation of an existing supervisor PDE.
- Existing CR3, one admitted fresh Preparing path, irreversible seal/Terminal, no teardown/free/retry/transfer/recoverable exit. Failure after acquisition retains the exact bounded prefix. This is **bounded terminal retention, not rollback/capacity restoration**, explicitly authorized in `operator_disposition_01.json` and freshly independently design-reviewed.
- Pure helper preflight refusals are checked for unchanged ownership/capacity/page-table state. Host failure-stage cases cover retained prefixes10/11/12 with no prepublication USER PDE and no retry/release.

## Paging semantics and limitations

Ordinary32-bit non-PAE paging: effective PRESENT/RW/USER intersects PDE and PTE. Dedicated PDE256 is P/RW/U; first leaf P/U/RO; last leaf P/RW/U. Kernel/descriptor/allocator/owner/paging/emergency-stack mappings remain supervisor-only under the reviewed inventory policy. CR0.WP must be1; CR4.PAE/PSE/SMAP must be0. AC/SMEP and gated CPUID facts were captured in the initial full matrix. Software owned-marker0x200 is not the hardware accessed bit0x20; the writer's contrary summary wording is preserved but not adopted.

There is **no hardware page-table NX** in this mode. RW stack is executable; software code/noncode placement is NOT hardware-enforced W^X. Ring0 supervisor aliases can write the payload. Shared-CR3 cooperative sealed kernel authority is part of the lifetime restriction. Ring0 table inspection and WP faults cannot prove CPL3 isolation or a future privilege-stack switch.

## HOST-TESTED — actual execution

Focused `commands/f4_focused_green_02.json`:12 passed,0 failed,0 ignored, Cargo exit0. Exact dedicated identities:

- `memory::paging::f4_user_arena_tests::layout_preserves_fixed_ceiling`
- `memory::paging::f4_user_arena_tests::publishes_exact_two_owned_user_leaves`
- `memory::paging::f4_user_arena_tests::refuses_foreign_and_stale_leases`
- `memory::paging::f4_user_arena_tests::refuses_reserved_structure_and_duplicate_frames`
- `memory::paging::f4_user_arena_tests::refuses_occupied_directory_without_promotion`
- `memory::paging::f4_user_arena_tests::refuses_unaligned_outside_and_overflow_ranges`
- `memory::paging::f4_user_arena_tests::rejects_unexpected_user_supervisor_inventory`
- `memory::paging::f4_user_arena_tests::refuses_inaccessible_table_and_payload_aliases`
- `memory::paging::f4_user_arena_tests::preserves_state_on_preflight_refusal`
- `memory::paging::f4_user_arena_tests::retains_bounded_prefix_on_acquisition_failure`
- `memory::paging::f4_user_arena_tests::seal_blocks_unmap_release_retry_and_cr3_switch`
- `memory::paging::f4_user_arena_tests::effective_permissions_and_guards_match_contract`

Focused `commands/f4_b26_focused_green_02.json`:3 passed,0 failed,0 ignored, Cargo exit0:

- `memory::paging::f4_b26_tests::b26_f4_no_allocation_under_owner_map_frame_locks`
- `memory::paging::f4_b26_tests::b26_f4_no_destruction_under_owner_map_frame_locks`
- `memory::paging::f4_b26_tests::b26_f4_refusal_has_no_fallback`

Full component `host_matrix_02/report.json`, SHA256 `f9fa30b9e3a31fa49736640ff55eaaab9d8e2b027d33d20d3e078c9a37982475`: all6 Cargo processes exited0. Host listing380; serial and parallel each378 passed/0 failed/2 inherited ignored. B26 listing149; serial and parallel each149 passed/0 failed/0 ignored. Every baseline identity preserved, exact new12 host and15 B26 memberships, no duplicate/substitution; all six raw log hashes rechecked.187 canonical input pins stable during this component run. Later authorized harness changes require downstream freeze/revalidation; this is not final candidate or canonical evidence.

Exact inherited ignored tests remain `maintenance_measurements::measured_frame_scan_states` and `maintenance_measurements::measured_heap_capacity_loss`. All Cargo test children ran outside the repository at`C:/Users/iamsv`, with absolute manifests and explicit`x86_64-pc-windows-msvc` target.

### Preserved failures and bounded corrections

- Focused host green_01: actual Cargo101,11 passed/1 failed due foreign allocator host-thread stack overflow. B26 green_01: actual Cargo101,0 passed/3 failed due by-value fixture stack overflow.8MiB host-stack diagnostic runs succeeded; these are diagnosis, NOT kernel-stack/resource proof.
- Parent corrected host fixture storage only: boxed foreign allocator constructed on a helper thread; B26 mutable-reference/mem::swap transfer avoids redundant large by-value argument. Real leases, exact observations, all-layout WATCH and detector controls remain; no production/resource-ceiling change. Default-stack green_02 runs above passed.
- `host_matrix_01/startup_failure.json`: recorder exited1 before Cargo; design regex omitted digit3 in cr3. Preserved as infrastructure failure/zero tests, not runtime RED; parser corrected and unique matrix02 used.
- `production_audit_01/report.json` FAIL/exit1: reader wrongly expected a separately emitted MANIFEST const symbol. Preserved; reader02 derives tuple size from target DWARF and array length from pinned source. No kernel change.

## HARDWARE-VERIFIED — initial full matrix, final frozen rerun pending

`runtime_red_01/report.json`: successful disposable accepted-F3 baseline build0, actual driver1, RUNTIME_RED. Actual CPL0 CR3/raw directory showed PDE256=0, explicitly failing required P/U mask5. Source stable and owned cleanup verified. This is meaningful hardware RED, not compilation failure or timeout.

`hardware_ready_01/report.json`: MINIMAL_RING0_GREEN, build0/driver0, Ready128/512 MiB both PASS; raw directory/table/CPU/payload captures and owned kill/wait preserved. These are **2 preliminary Ready guests, not the reviewed12-case F4 matrix**. No full negative permission proof or complete hardware lease-ledger proof claimed from these two.

`hardware_matrix_01/report.json`: actual driver exit0, PASS12/12, no CPL3. Six scenarios ready/code_write/lower_guard/unused_hole/occupied_refusal/capacity_refusal each at128/512 MiB. Parent independently ran `f4_evidence.py`: PASS12 scenarios and12757 validated artifact pins in `commands/f4_hardware_offline_readback_01.json`. Exact target DWARF/lease/allocator-role ownership, prepublication ordering, full paging inventory, F3 descriptors, code/stack bytes, CPU positive stack write/read followed by code-RO #PF, guard/hole #PFs and bounded terminal refusals are covered by that validator. This was source-stable within the run, but the acceptance runner changed afterward. Retain it as corroboration, not final-source canonical acceptance.

Final frozen components completed PASS under short Windows-safe root `test_results/f4p04`, managed process `proc_830c0b450d51`, actual exit0. Formatting/build/ELF, full host/B26 and F1/F2/F3/F4 drivers all exited0; fresh scenario counts10/8/18/12. Parent independently rehashed60501 retained pins and reran F2/F3/F4 validators, with source-before=source-after=current187 independently enumerated inputs (`parent_components_readback_04.json`). Component aggregate SHA256 `e0c91675b815d55c4e9118f1eea562e9c2bc991c3bfd4cb34379c9a1a818114e`. F1's142 stopped checkpoints received bounded parent checks; the historical full F1 final-readback gap is NOT silently closed.

Acceptance integration: original full mock89/89 passed in798.087s, but parent source-grounded probe found direct-output driver vs child-output runner mismatch. Preserved contract RED and corrected focused GREEN; runner now passes explicit `f4_output/matrix`, and the mock writes directly to its actual argument. Full corrected mock02 passed89/89 in925.654s while component verification was also running. This exceeds the unchanged canonical900s gate; causation is unknown. Isolated calibration process `proc_3b0e739a75c7` now enforces the real900s bound using the verified absolute venv interpreter, with no competing agent build/QEMU/reviewer. No timeout alteration. `parent_integration_02.json` pins original notes and exact six authorized deviations from191 initial pins; all other initial pins unchanged. No canonical launch yet.

Infrastructure failure `test_results/f4p03/report.json` is preserved: nested bare python selected a different base interpreter lacking psutil/pycdlib, failing before any Cargo/QEMU launch. Absolute verified existing interpreter is used for04; no package install or source/oracle weakening.

## Production build and resource observations

`commands/f4_production_fmt_01.json`, `f4_production_build_01.json`, `f4_production_elf_01.json`: actual exit0 each for production formatting, locked build and ELF validation.

`production_audit_02/report.json`: exact production ELF SHA256 `241ecb209f9a2687daa430d5ff0f0e2596937eb829f7d080fb868122cd0bb516`; exact target DWARF, raw disassembly and29 selected F4 functions retained. OWNER mutex472 bytes + STATE1 + conservative MANIFEST type12 =485-byte family; unchanged F3 descriptor family272 bytes, both <=4096. Const MANIFEST may be folded rather than separately stored. No guessed repr(Rust) offsets.

These are target-size and emitted prologue/call observations, **not a cumulative F4 stack bound or measured runtime stack/heap high-water**. Initial128/512 full-matrix viability is observed, but final emitted call/lock/publication-order review remains outstanding. F3 emergency bound remains2578 bytes in16384 with13806 headroom, CONDITIONAL on the stated one-nested-NMI scenario; not unlimited recursion survival or newly measured high-water.

## INDEPENDENTLY REVIEWED

- Original design01 REJECT2 preserved at`reviews/design_review_01.json`, SHA256 `abfa725eb85267ea32ec026a3a345c5dd2cd9aae0dc1cd5bd55d4811aa90678b`.
- Original design bytes preserved`design_revision_01_reviewed.md`, SHA256 `b35761f661030178c88fa5f2a6c976b7ae7a529a9f1fa472474af8fbc86f4864`.
- Revised design02 SHA256 `ea0a49eda8784d358995d556046adfa89ca9d4bafd89070765816c6aedf086ee`; independent`reviews/design_review_02.json` APPROVE0, SHA256 `719aa78173cff2c8dcca7b91c5cb8e21b1e466a3bbb9520c6e2e774c5ea12ce7`. Parent read complete verdict and verified201 original review pins before implementation, recorded`reviews/parent_design_readback_02.json`. Design approval does not approve later implementation bytes.
- No independent candidate review or final canonical readback yet. Historical F3 candidate_review_01 REJECT remains unchanged, SHA256 `d9f1f8b88d06a36a0d1c982a4531067cbb52406c32147338576986b74250ab01`.
- Historical F1 independent final-readback gap remains disclosed.

## DEFERRED / NOT VERIFIED

Completion of current final-source component/mocked runs; fresh F1/F2/F3 preservation and F4 rerun; independent emitted stack/lock/publication audit and candidate approval; one canonical acceptance and fresh independent final readback. Reviewed gate contract is70 inherited+2 F4=72, verified against the pinned predecessor multiset in `integration_before_01/record.json`, **not an executed canonical result**. Canonical F4 acceptance has not launched. Keep the current source/build inputs frozen until both managed runs exit.

F2 mandatory68-byte exception ABI, F3 GDT/TSS/ESP0 and emergency policy are not intentionally altered. Source critical-byte checks and full fresh preservation must complete before acceptance. Current GDT has no user selectors; F4 does not assert a returning production user-entry API.

**No CPL3 execution. No F5 isolation proof. No production syscalls, ELF loader, scheduler, process system, broad address-space teardown, shared ownership or COW.**

## Next safe operation and evidence bindings

Parent must wait for task-owned guest-driver/evidence and acceptance-harness writers to finish; inspect exact changed bytes/API and run their real validation. No conflicting build/QEMU launch while an owned build is active. Then run the full F4 matrix, preserve any failure and classify before correction; refresh regressions and predecessor guests on stable inputs; freeze/review before canonical launch. See STATE.md for exact current handles/command; working directory`C:/Users/iamsv/Documents/Rust-OS`.

`evidence_manifest.json` binds completed checkpoint evidence with full raw hashes and exact paths, excluding its own hash. It is a checkpoint inventory, NOT a candidate source freeze; active unreviewed harness files are not approval evidence. This report's status must remain PARTIAL until every mandatory acceptance/readback predicate is actually satisfied.
