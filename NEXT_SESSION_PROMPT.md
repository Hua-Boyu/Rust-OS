# Rosti OS — standalone Phase 11 continuation prompt

## Current task and safety boundary

Work only in `C:/Users/iamsv/Documents/Rust-OS`, existing branch
`maintenance/phase10`. Initial Phase11 HEAD was
`def677fac8ca662e45ad4fb40c9ddd18bfe86bd8`; verify actual HEAD/status/log, never
reset or infer HEAD from this text. Keep unrelated `d1/` and
`scripts/b13_boot_fixture.py.backup`. No new branch needed without concrete
isolation grounds. No push, tag/history rewrite, Phase12 or Proxmox mutation.

Phase11 is **IN PROGRESS / NOT A RELEASE**. Only 11A's initial permission
prerequisite is implemented: effective PDE+PTE diagnostics, fail-closed unowned
USER/nonpresent map requests. Five mandatory host tests include all 64 P/RW/US
combinations and supervisor identity-map inventories at 128/512 MiB. No real
CPL3, TSS, user stack, controlled continuation, syscall or guest ELF loader yet.
No hardware NX in non-PAE paging; do not claim W^X or CPU isolation from a host
model. Keep all existing kernel/boot/heap/table/MMIO aliases supervisor-only.

Verified implementation commit is `d6d04c5dececf0dbf78c27e2e71760a2084786d4`;
the following documentation/evidence commit changes no frozen executable input.
Last verified action: canonical runner **PASS 54/54**, actual process exit0;
independent closeout PASS before/after implementation commit. All135 source
inputs rediscovered/hash-matched;159 nested reports checked; no local QEMU.
Host **270/0/2 ignored** parallel/serial, harness **37 passed**, explicit
RED/GREEN logs under `test_results/phase11/`. Fresh inherited56/56 initramfs
scenarios,3379 checks,9071 modeled crash cases passed at128/512MiB ELF/GRUB.
Exact report `test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json`;
closeout `test_results/phase11/final_verification.json`. Its label is
`11A-prerequisite` with `phase11_release_ready=false`, not full Phase11 proof.
The independent four-file diff review has no blockers; optional additional
exact-five negative fixtures were deferred, not applied during the source freeze.

ISO `dist/rosti_phase11a_prerequisite_20261016T154710Z.iso` SHA256
`fa309a4ecc5b97d98ee07891597e5cffe4bf45058709ed91c8936a2fe62992a9`;
independently extracted kernel SHA256
`c813429de80aa5c0d9782fcd1de76bde95566887f1f76caaf36bc85662844f4b`.
Archive identical to Phase10B; accepted baseline ISO unchanged. Loaded sections
+720 bytes, static span unchanged; runtime peaks and meaningful timings unknown.
In future runs, no competing builds/QEMU or source changes while the canonical
runner owns `dist/.phase6_acceptance.lock`. Never unlink the lock file; handle
closure releases it. Preserve failed/incomplete evidence.

Next exact command: `git status --short`.
Then `git branch --show-current`, `git rev-parse HEAD`, `git log -5 --oneline`.
If another acceptance run is active, discover its owner and continue it rather
than launching a competing runner. The checkpoint run above has exited0.
Read `docs/PHASE11_HANDOVER.md` (A–K), `docs/PHASE11_DESIGN.md`,
`docs/PHASE11_TOOLS.md` and current opening sections of all seven standard docs.
Load skills rosti-kernel-development, systematic-debugging,
test-driven-development, bare-metal-kernel-qemu-testing,
requesting-code-review and git-release-checkpoint.

Next implementation after a passing prerequisite checkpoint: close retained
static PageMap aliases with scoped/snapshot APIs and explicit mutation ownership
before adding owned user mappings. Inspect every caller in memory/mod.rs,
boot_copy.rs, fs_stress.rs and tests. Preserve heap -> frame lock ordering;
neither allocate nor destroy heap backing under frame guards. Then proceed in
PHASE11_DESIGN's dependency order through correct GDT/TSS/error-code entry ABI,
single-context IRET/continuation and real CPU denial/recovery at both RAM sizes.
Only after 11A passes may 11B synthetic execution, 11C syscalls, 11D bounded
ELF32 and 11E lifecycle begin. Do not treat an old Rust stack as an IRET target.

Use RED/GREEN for each slice and independent read-only review. Host command
from `C:/Users/iamsv` (outside kernel config):
`cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml`.
Production `cargo build` from repo; full acceptance
`python -B scripts/phase6_verify.py` as a notified background process, exclusively.
Extend mandatory gates here, never hide Phase11 evidence in an optional runner.
All inherited53 gates,56 initramfs scenarios,3379 checks and9071 crash models
were freshly rerun at this checkpoint and must not be weakened in future work.

No remote API/SSH action was performed in this Phase11 session. Historical VM103
was 512 MiB/one vCPU/SeaBIOS, Phase9.6 ISO, no persistent data disk; do not assert
fresh remote state or run live harnesses (they reset the VM). Preserve accepted
media, RostiFS format1/COW/CRC/flush, `/system` trust/read-only integrity,
generational/attenuated descriptors and independent RAMFS recovery.

At each verified checkpoint update all seven docs and Phase11 A–K handover,
retain exact source/artifact hashes and review scope, commit scoped reviewed
passing changes only. Report partial status honestly. Full Phase11 is NOT READY
until every requested 11A–11F guest, cleanup, isolation and review gate passes.

---

## Historical post-Phase10B continuation prompt (superseded)

Work in `C:/Users/iamsv/Documents/Rust-OS` on `maintenance/phase10`.
The completed Phase 10B source checkpoint is `449ed434ed5dbf1518b99821178a5fcd1d343b75`; the following
documentation/evidence commit records its accepted results. Inspect actual HEAD,
branch, status and recent log before doing anything. Do not reset a dirty tree.

## Verified checkpoint

- Full source-frozen acceptance PASS 53/53:
  `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json`.
- Exact invocation-owned initramfs matrix: 56/56 scenarios,
  3379/3379 aggregate checks; all child cleanup verified.
- All 134 source/build inputs independently rediscovered/hash-matched; no local
  QEMU remains. Kernel host serial/parallel 265 passed, 0 failed, 2 ignored each.
- B11/B13/B18/B26, 44 metadata scenarios, CPU faults, paging, keyboard/VGA,
  growth/OOM, ATA/RostiFS and all 9,071 modeled crash cases retained.
- Trusted complete-byte SHA256 precedes parse and read-only `/system`
  publication. RAMFS recovery survives absence/digest rejection/oversize,
  collision, failed mount, allocator exhaustion and reboot at 128/512 MiB
  through ELF and real GRUB. No archive code is executed.
- ISO `dist\rosti_phase10b_20261016T120546Z.iso`, 11096064 bytes,
  SHA256 `117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8`.
- Independently extracted production kernel SHA256
  `f292cd2e406487ead05a2b9008e0cf6bf39d145b122f7ebac160ba4d1c53386f`.
- Independently extracted complete system archive SHA256
  `8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7`.
- Final verification/resource/review evidence is under `test_results/phase10b/`.
  Review `test_results/phase10b/independent_scoped_review_20261016T111204Z_f632dad1df.json` has no blocking findings in its bounded scope.

## Read first

Load Hermes skills `rosti-kernel-development`, `systematic-debugging`,
`bare-metal-kernel-qemu-testing`, `test-driven-development`,
`requesting-code-review`, `git-release-checkpoint`; read AGENTS.md if present,
HANDOVER.md, ARCHITECTURE.md, TESTING.md, BUGFIXES.md, README.md, PROXMOX.md,
docs/PHASE10_INITRAMFS.md and the earlier safety-audit documents.
Current top sections supersede historical partial-phase and Phase 7 VM claims.

## Environment and safe verification

Windows Git Bash; native programs require `C:/Users/...` paths. Kernel is
nightly Rust custom i686 no_std/core+alloc; host Cargo must run outside the
kernel tree, e.g. from `C:/Users/iamsv`:

```text
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml
```

The full runner from repository root is
`python -B scripts/phase6_verify.py`; use a notified background terminal, no
source edits or competing QEMU until completion. Preserve every failed and
incomplete run. Re-enumerate source/build inputs, validate exact mandatory
reports and independently extract the ISO kernel before publishing artifacts.
Never replace runtime evidence with host models or sum nested totals twice.

### Final reproducibility and exclusive-execution closure

The RAMFS baseline-root listing legitimately adds one `VGA prompt after ls` row:
all four complete workloads now have exactly 103 checks, with zero inherited
checks removed. RED/GREEN regressions accept 103 and reject both 102 and 104
before publication. The full runner retains exact ATA/RostiFS counts 98/168.

`system/** -text` in `.gitattributes` preserves trusted asset bytes under Windows
`core.autocrlf=true`; a fresh staged-index checkout reproduced the exact archive
and pinned digest. No asset normalization or trust-anchor change was made.
Attributes are now included among the 134 frozen inputs. This proves narrow
asset-byte reproducibility, not cross-configuration raw hashes for every source.

Two independently launched pipelines overlapped before the guard existed; both
were stopped only through verified task-owned runner trees and preserved as
ABORTED (original reports retained alongside interruption evidence). The final
accepted run is exactly `acceptance_20261016T120546Z_psboeekn`, not whichever
report sorts last. The desktop worker won the new lock; the completion agent
adopted its matching frozen run, and its own contender correctly exited 2.

The runner now holds a nonblocking OS lock at `dist/.phase6_acceptance.lock`
from before report creation/builds through final production restoration. Never
unlink that file to clear a PID: OS handle lifetime releases ownership on exit.
Real Windows and WSL POSIX tests cover contention, normal release and forced
owner exit; all 35 acceptance-harness host tests pass. A live canonical contender
created no report and started no work. Native Windows venv redirectors are only
wrappers, so forced-owner tests use the actual base interpreter. This guard
coordinates cooperating runners on each OS; it is not a general barrier to
manual builds, standalone QEMU or mixed-runtime/remote work.

`independent_lock_followup_review.json` records a separate no-blocker excerpt
review of the final guard/count/attribute changes. Its scope and supplied-test
premises are explicit; the actual contextmanager decorator was also checked.
`exclusive_runner_exit.json` records exit 0 through a captured Windows process
HANDLE. `exclusive_process_watchdog.json` records sampled QEMU ancestry; no
unowned guest was observed. Sampling is not continuous absence proof.
All evidence paths above are beneath `test_results/phase10b/`.

## Safety and scope

- Await the user's next objective. Do NOT automatically start Phase 11, deploy,
  tag, merge/rebase or rewrite history. The previous commit/push permission
  covered completed Phase 10B only, not new work.
- Preserve unrelated `d1/`, `scripts/b13_boot_fixture.py.backup`, accepted ISOs,
  failures and rollback media. No credentials/caches/raw images/binary ISOs in Git.
- Fresh read-only Proxmox GETs showed pve VM 103 running, 512 MiB/one vCPU,
  SeaBIOS/pc, no data disk, Phase 9.6 ISO on ide2. No Phase 10 deployment,
  upload, reset, VM/storage mutation or physical-disk operation is authorized.
- Keep permanent module/metadata/page-structure pins, reservation precedence,
  exact growth-slot rollback, heap -> frame lock order and bounded recovery.
- Retain descriptor attenuation, opaque generations, semantic file/.. denial,
  RostiFS v1/COW/CRC/flush contracts and every modeled crash case.
- Trust assumes a trusted kernel/loader and single-owner ring-0 execution, not
  hardware secure boot or hostile-userspace isolation. Runtime heap/stack
  high-water is unknown; 546,228 bytes is a capacity bound excluding allocator
  overhead, not a measured peak. Timing is 100 Hz PIT granularity.
- Guest malformed/truncated cases prove digest rejection; authenticated parser
  rejection is host coverage. Optional review suggestion S1 (final guest content
  reread after mutation denial) was deferred without disturbing the freeze.
- Broader B19/public-API/exception/stack safety findings are not blanket-resolved.

For any authorized next change: establish a failing tight test, apply minimal
fix, retain RED/GREEN evidence, obtain independent review, rerun affected/full
acceptance, refresh all seven project docs and review task-owned staged files.
