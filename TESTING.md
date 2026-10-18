# TESTING

## Current structure-lifetime and owner-observation regressions — PARTIAL

Five `structure_lifetime_tests` exercise actual reused structure addresses across
32 cycles, revoked operations/CR3 refusal, publication/activation retention and
early/late multi-table role-fault refusal with exact capacity/role restoration.
Cleanup, activation and role admission were observed RED before their fixes.
Five B26 detector controls now prove allocation/destruction observation under
PAGE_MAP-only and FRAME_ALLOC-only guards, plus correct unlocked-attempt counting.
One additional real rejection-path regression and existing per-reserve/refusal/
validation regressions enforce no heap operations under either guard. Host mirrors
still require disclosed backing-layout filtering on partial-build paths.

Main host 305 passed/0 failed/2 existing ignores and full B26 78/0 pass in serial
and parallel full-driver runs; harness 53 and final reader 17 tests pass. Exact source-frozen final
counts, guest/ISO identities and read-back are maintained in `docs/PHASE11_HANDOVER.md`.
The runner retains all 59 inherited gates and adds one exact-five lifetime gate;
its existing B26 gate also requires all five source-linked detector controls.
One-short/extra/duplicate/substituted/mismatched evidence is rejected, not accepted
through a broad suite total. The raw stale-numeric probe is still 2 PASS/1 intentional
FAIL, never a release success. No CPL3 or recoverable exception proof is claimed.
Subsequent sections are historical checkpoint records.

The canonical frozen run `run_20261018T054817_823884Z` completed PASS60/60,
actual exit0; `final_closeout_retry.json` checks143 inputs and ISO/kernel/archive
identity,159 nested reports/280 cleanup assertions and no QEMU. The first offline
reader failure and exact-silent-format RED/GREEN remain preserved. Only exact
successful format commands may have empty logs; all other log checks remain.

## Latest payload-pin prerequisite and isolated-child credibility

Main host300/0/2 existing ignores and B26-root67/0 pass serially/parallel;
acceptance contracts48 and closeout contracts8 pass. Four repaired isolation
filters each run one actual child rather than silently selecting zero tests.
The retained blocker probe is now2 PASS/1 intentional FAIL (stale numeric release).
Exact guest acceptance, source/artifact checks and independent-review limits:
`docs/PHASE11A2_MAPPING_PINS_HANDOVER.md` (supersedes current-status text below).

## Latest Phase 11A.2 table-access tests

Five `runtime_table_access_tests` cover candidate alias refusal and retry; actual
removed-alias RED/GREEN logs are retained. Main host290/0/2 ignored and B26-root57/0
pass serially/parallel. These host checks are not real CPU alias-refusal proof.
Current exact acceptance status: `docs/PHASE11A2_TABLE_ACCESS_HANDOVER.md`.

## Phase 11A.2 reservation prerequisite — bounded, not B19 completion

The reserved/uncovered admission test was observed RED (actual exit101), then
GREEN. Its independent byte-span fixture covers boot/bump, one-byte explicit
pins, competing firmware, VGA and uncovered backing while preserving boot aliases.
Three inherited positive host fixtures now acquire valid payload/growth backing;
none of their permission or table-identity assertions were removed.
The canonical runner requires all eight registry/reservation test identities in
one new gate, preserving all56 inherited gates. Harness negative tests refuse
missing/empty/substituted evidence. Current exact results, source hashes and
accepted run are in `docs/PHASE11_HANDOVER.md`.
Standalone `test_results/phase11a2_continuation/ownership_blocker_probe.rs`
reproduces three unresolved B19 failures against production modules. Those RED
probes are not passing release tests, not ignored successes and not CPL3 proof.

## Historical recovery tests — registry repair uncommitted at entry

See `docs/PHASE11A2_REGISTRY_HANDOVER.md` for current commands and status.
Two specific regressions were observed RED at exit101: locked registry backing
allocation and boot-identity unmap clearing a live runtime reference. Both are
GREEN. Main host284/0/2 ignored and B26-root51/0 pass serially/parallel; focused
paging and eight ELF/GRUB128/512MiB growth scenarios pass. The unlocked backing
allocation budget is explicitly three, with independent refusal tests at each
reserve. Locked allocation/destruction and diagnostic fallback remain forbidden.
Fresh inherited prerequisite acceptance PASS56/56, actual runner exit0; closeout
verifies139 frozen source/build inputs,159 nested reports,280 cleanup assertions,
ISO kernel/archive identity and no QEMU remains. Scoped review has no new repair
blockers, with a deferred lock-observability gap. No full ownership/CPL3 claim.
Exact paths are in the registry handover; results below are historical checkpoints.

## Current Phase 11A — PARTIAL prerequisite tests

Evidence root: `test_results/phase11a_ownership/`. Owned snapshot API RED
exit101 then GREEN1/1; three GDT field-decode tests RED access-byte corruption
then GREEN3/3. Host273 passed/0 failed/2 ignored, parallel and serial; B26 full
crate37 pass; acceptance harness39 pass (RED eight failed assertions retained).
Two mandatory exact-identity gates extend the inherited54 to56; this does not
add CPL3 acceptance. Focused paging128/512 passes, and each RAMFS/OOM/growth
workload passes103 checks, including1536 writable-supervisor identity pages.
The first relative output-path paging invocation failed in the harness; the
absolute-path retry and original failure are retained, not conflated.
Current canonical acceptance and independent closeout paths are in A–K handover.

Current canonical result: **PASS56/56**, actual exit0, at
`test_results/phase11a_ownership/acceptance_20261016T234702Z_x057jmpa/acceptance.json`.
Independent closeout PASS136 frozen inputs/159 nested reports; exact previous
gate multiset retained, production kernel/archive extracted and cleanup checked.
All56 initramfs scenarios/3379 checks and9071 crash models reran. No CPL3 proof.

### Historical permission-only acceptance (not the changed candidate)

Recorded TDD: effective permission diagnostic RED (PDE absent/PTE present),
unowned USER map RED, nonpresent map RED, each followed by GREEN. Five required
tests cover all 64 flag pairs, 128/512 MiB supervisor inventories, zero mutation
on refused requests and preserved existing entries. Host serial/parallel:
**270 passed, zero failed, two ignored**. Acceptance harness: **37 passed**.
Logs: `test_results/phase11/`; this is host coverage, NOT CPL3 CPU proof.

Canonical `python -B scripts/phase6_verify.py` now mandates the exact five-test
permission gate alongside ALL inherited 53 gates. Report/artifact labels are
`11A-prerequisite` / `rosti_phase11a_prerequisite_*`, with release-ready false.
Full inherited prerequisite acceptance **PASS54/54**, actual exit0:
`test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json`.
Fresh56/56 initramfs scenarios/3379 checks,9071 crash models,44 boot-metadata
scenarios and all inherited ELF/GRUB128/512MiB gates passed. Independent
closeout matched135 source inputs, read159 nested reports and independently
extracted kernel/archive; final QEMU inventory empty. See `final_verification.json`.
Keep frozen source, nonblocking OS lock and sequential guests in future runs.
Final Phase11 CPU scenarios in `docs/PHASE11_DESIGN.md` remain unimplemented.
No gate was removed. Source/fixture membership and exact nested counts remain
mandatory; this passing regression run is not a CPL3 isolation oracle.

## Phase 10B COMPLETE — local acceptance verified

Source checkpoint: `449ed434ed5dbf1518b99821178a5fcd1d343b75` on `maintenance/phase10`.
Full acceptance: **PASS 53/53 gates**, invocation-owned
**56/56 initramfs scenarios, 3379/3379 matrix checks**.
Evidence: `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json`;
independent closeout: `test_results/phase10b/final_verification.json`.
All 134 source/build inputs were independently rediscovered and hash-matched.
Scoped independent review: no blocking findings (`test_results/phase10b/independent_scoped_review_20261016T111204Z_f632dad1df.json`).

Trusted complete-byte SHA-256 verification precedes parse/publication at read-only
`/system`. The kernel is the trust anchor, not the module. Real GRUB and injected
ELF recovery, allocator exhaustion, mount failure and reboot are covered at
128/512 MiB. No archive code is executed; RAMFS recovery is independently owned.
Host serial/parallel: **265 passed, zero failed, two ignored** each. Inherited
B11/B13/B18/B26, CPU faults/paging, keyboard/VGA, growth/OOM, ATA/RostiFS and all
9,071 modeled crash cases remain covered. Old failures below are historical.

Accepted ISO: `dist\rosti_phase10b_20261016T120546Z.iso` (11096064 bytes), SHA256
`117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8`. Independently extracted production kernel SHA256:
`f292cd2e406487ead05a2b9008e0cf6bf39d145b122f7ebac160ba4d1c53386f`. Fixture features are excluded.
No local QEMU remains. Historical Phase 9.6 ISO is unchanged.

No Phase 10 deployment, VM/storage mutation, Phase 11, tag or history rewrite.
Fresh read-only inspection shows VM 103 running Phase 9.6 ISO, 512 MiB/one vCPU,
SeaBIOS/pc, no data disk; stale Phase 7 references below are historical.
Commit/push of completed Phase 10B is explicitly authorized. Unrelated `d1/`
and `scripts/b13_boot_fixture.py.backup` stay excluded and preserved.

Limits: trusted-loader/single-owner ring-0 assumptions; no hardware secure boot
or hostile-userspace isolation. Runtime heap/stack high-water is **unknown**.
The 546,228-byte import capacity bound excludes allocator overhead/fragmentation
and is not a measured peak. Guest malformed/truncated images prove digest
rejection; authenticated structural-parser rejection is covered on the host.
See `docs/PHASE10_INITRAMFS.md` for exact contracts and retained failures.

### Reproducible commands and completeness

From `C:/Users/iamsv/Documents/Rust-OS`, run
`python -B scripts/phase6_verify.py` in a notified background terminal. Freeze
source/scripts/assets; run no competing QEMU. Exact mandatory Phase 10 rows are
14 cases × ELF/ISO × 128/512 MiB, checked with `phase10_evidence` and all owned
child reports. The acceptance runner's own matrix, not the separately passing
standalone run, supplies release evidence. All 159 nested reports were
independently read; 200 explicit cleanup assertions passed.
Exactly 10/10 ordinary boots per RAM size passed. Mandatory RAMFS/ATA/RostiFS
aggregates contain 103/98/168 checks each at all four boot/RAM configurations.

Run host Cargo outside the kernel configuration tree:
`cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml`.
Add `-- --test-threads=1` for the separately verified serial run. Host-only
contract suites exercise missing/short/failed matrices, injection cleanup and
fixture exclusion; these cannot substitute for privileged guest execution.

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

## Phase 9.6 safety acceptance (current)

Canonical full command from the repository root:
`python -B scripts/phase6_verify.py` (optional `--output-dir <evidence-parent>`).
Run it in the supported notified background terminal. Freeze all source/build
inputs until the final report exits PASS; never run another QEMU beside it.
Evidence now lives under `test_results/phase9_6/acceptance_<UTC>_<unique>/`.

In addition to inherited filesystem, paging/fault, keyboard/VGA, persistence,
corruption, recovery and growth/OOM gates, acceptance requires B11 frame-policy,
B18 independent wire-parser and B26 lock/refusal/rollback host families; B13
source, emitted-code and privileged handoff fixtures; and all 44 metadata
ELF/GRUB x 128/512 MiB scenarios. Rejected scenarios attach exclusively-owned
media, exercise write denial, RAMFS lifecycle and bounded bootstrap OOM, and
require whole-image hashes to match after verified process exit. Accepted modules
have their payload hash and supervisor identity PTEs checked across real growth.

Focused host commands, from C:/Users/iamsv (outside kernel Cargo config):

```bash
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_b26/Cargo.toml b26_ -- --test-threads=1
```

For a separately built production kernel, a focused guest command is:
`python -B scripts/boot_metadata_test.py --boot both --ram 128 512 --output-dir C:/Users/iamsv/Documents/Rust-OS/test_results/phase9_6/manual_NEW`.
The harness never builds/replaces the production kernel or accepted ISO. Host
contracts: `python -B scripts/test_boot_metadata_harness.py`. B13 build/order is
documented in `scripts/b13_fixture/README.md`. No live Proxmox harness is in scope.

The safety report records final counts, media hashes, source freeze, footprint,
review and retained failures. A RUNNING/partial report is never release evidence.
Historical Phase 9.5C sections below do not override the current release index.

## Phase 9.5C final maintenance

From C:/Users/iamsv, outside kernel Cargo config:

```bash
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test write_preservation
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test write_preservation measured_preservation_workloads -- --ignored --exact --nocapture
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml maintenance_measurements::measured_frame_scan_states -- --ignored --exact --nocapture
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml maintenance_measurements::measured_heap_capacity_loss -- --ignored --exact --nocapture
```

Run timing probes separately. The write target has three required ordinary
regressions and one ignored benchmark; two new acceptance-runner regressions
require its invocation and complete totals. Full acceptance now has 39 gates;
all prior gates and modeled crash cases remain. Frame/heap investigations are
ignored observations, not claims of allocator fixes or guest/TLB measurements.
Use the notified background procedure for `python -B scripts/phase6_verify.py`;
no competing QEMU or source changes. Latest release evidence and limitations:
docs/PHASE9_5C_RESULTS.md, with c02_* and c04_c05_investigation.json under
test_results/phase9_5. Older campaign counts below remain historical.

## Phase 9.5B controlled experiments

From C:/Users/iamsv (outside kernel Cargo configuration):

```bash
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test read_performance
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test read_performance measured_read_workloads -- --ignored --exact --nocapture
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test read_performance measured_mount_info_workloads -- --ignored --exact --nocapture
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml perf_baseline_records_latencies -- --exact --nocapture
```

Four read regressions cover exact bytes/tail sentinels, EOF/empty/usize::MAX,
intersecting-sector counts, changed geometry rejected before I/O and all 17
failure positions across partial/full/partial reads with recovery. Existing cat
tests preserve output/rights/shared offsets/cleanup while retargeting their
injection indices to the new transfer schedule. The ignored timing fixture is
not a correctness test: nine fixed 2,000-read samples per size, 100 warm-up reads,
counted RAM BlockDevice, host Instant, no physical/guest throughput claim.

C03 adds three default-core occupancy regressions: metadata-bounded empty work,
all 128 interleaved extents, and an independent set-union oracle over 320 internal
inventory models. NoIo panics on reads/writes/flushes. Work-count hooks are cfg(test)
only and per-thread, not production instrumentation. The separate ignored host
diagnostic fixture has nine samples of three queries for each 128/1024/65536-block
capacity and empty/fragmented state; fixed 512 KiB backing covers all touched
metadata/data. It models capacity for pure computation, not full-volume I/O.
Setup/format/create/delete times are excluded; expected union counts and zero I/O
are asserted. Invoke one exact named timing filter at a time: running all ignored
tests with default test threading would run competing measurements.
The unchanged original QEMU workload remains a regression replay, not an isolated
guest diagnostic benchmark. C03 evidence is in c03_measurements.json and
docs/PHASE9_5_C03_RESULTS.md; prior optimization reports remain historical.

Full acceptance now has an additional mandatory four-test read gate (38 gates
when complete); mocked missing invocation/incomplete totals cannot publish an ISO.
Run python -B scripts/phase6_verify.py as a background job. Never overlap acceptance
with QEMU benchmarks or alter source/build inputs while it runs. All original gates
and exact 128/512 MiB ELF/GRUB matrix totals remain required.

The unchanged phase9_5_bench.py was replayed B/C/B/C, three fresh guests per RAM
size per round. Raw evidence and median/min/max/sample counts are in
test_results/phase9_5/optimization_baseline.json and optimization_results.json.
Host command timings include pacing/polling; guest execution, isolated disk/serial,
IRQ latency and peak stack remain unavailable. Full suite coverage/deferrals are
explicit in docs/PHASE9_5_OPTIMIZATION_RESULTS.md; no invented future-component tests.

## Phase 9.5 maintenance verification

The retained entry point `python -B scripts/phase6_verify.py` now writes
`test_results/phase9_5/acceptance_<UTC>_<unique>/acceptance.json` and publishes
`dist/rosti_phase9_5_<UTC>.iso` only after all inherited gates plus the new
benchmark-contract gate pass. Exact ten-row boot matrices and the mandatory
aggregate report for each fault/paging/RAMFS/ATA/RostiFS configuration are
required; missing status, missing/empty/false checks and inconsistent declared
counts fail before publication. Source/build freeze rediscovery is retained.

Host commands still run from `C:/Users/iamsv`, outside the kernel Cargo config;
the independent portable core and host-tools suites are unchanged. New Rust
tests cover bit clearing, descriptor retirement/rollback/counter saturation,
portable-core cat read counts, chunk boundaries, permission/shared offsets and
first/later read-error cleanup. Existing warnings are not silently removed by
unrelated changes. Full acceptance must finish as a background job with its
final report; never overlap it with QEMU benchmarks or change build inputs.

Measurement command (from repository, choose a fresh evidence filename):

```bash
python -B scripts/test_phase9_5_bench.py
python -B scripts/phase9_5_bench.py --output test_results/phase9_5/new_measurement.json --iso dist/rosti.iso
```

The benchmark creates only new test-owned images and reuses canonical QMP/
serial/VGA boundaries. It runs three independent guests at each RAM size;
host perf_counter_ns observations include emulation, input pacing and serial
polling, not isolated guest CPU/physical disk performance. No peak stack or
mount-only timing claim. Final counts/hashes are in HANDOVER.md; earlier
milestone sections below are historical and do not override this section.

## Phase 9 acceptance and reproducible persistence tests

`python -B scripts/phase6_verify.py` now reports Phase 9 and writes a unique
`test_results/phase9/acceptance_<UTC>_<unique>/acceptance.json`. Run it as a
bounded background job with completion notification. It retains all Phase 8
regressions and adds portable-core formatting/tests, host-tool safety tests,
production feature exclusion and RostiFS persistence on ELF/GRUB at 128/512 MiB.
Only a complete PASS report, unchanged source/build inputs and valid all-true
harness evidence permit publication of `dist/rosti_phase9_<UTC>.iso`.

Commands (host Cargo must execute from outside the kernel config tree):

```bash
bash scripts/run_tests.sh
cd "$HOME"
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml -- --nocapture
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test host_tools
```

From the repository, sequentially:

```bash
python -B scripts/test_rostifs_harness.py
python -B scripts/rostifs_test.py --ram 128 --output-dir test_results/phase9/manual
python -B scripts/rostifs_test.py --ram 512 --output-dir test_results/phase9/manual
python -B scripts/rostifs_test.py --iso dist/rosti.iso --ram 128 --output-dir test_results/phase9/manual
python -B scripts/rostifs_test.py --iso dist/rosti.iso --ram 512 --output-dir test_results/phase9/manual
```

The RostiFS harness creates exclusive new `.img` files in a unique `dist/`
subdirectory; no arbitrary existing disk path or live-Proxmox mode is accepted.
The formatter receives an explicit `--test-owned-image` path and executes from
the user's home. Five separate owned QEMU processes prove:

1. Boot/mount, nested creation, overwrite, exact read/append, descriptor closure,
   unchanged heap/growth counters, raw-write denial and **guest-requested reboot**
   followed by read-only reopen/readback.
2. A **new emulator process** reads the existing directory/file before any
   mutation, then deletes the file and removes empty directories.
3. Another new process proves deletion persisted; the complete disk hash must
   remain unchanged during this verification-only boot.
4. Corrupting both root headers rejects the mount while the independent RAMFS
   recovery shell can create/read/delete files; the corrupt disk stays unchanged.
5. Unowned media remains byte-for-byte unchanged and the recovery shell works.

After the write process exits, real `rostifsck` and `rostifs-inspect` subprocesses
validate the guest-written image and list its nested file without changing its
hash. Serial logs, QMP attachment, command boundaries, process cleanup, image
hashes and machine-readable reports are retained. Timeouts clean up only the
runner's own QEMU process; never globally kill emulators. Do not run another
QEMU concurrently with the existing boot runner's global orphan check.

Host results verified during development and repeated by acceptance:
**132 kernel tests**, **20 portable-core tests**, **4 host-tool integration tests**;
Python media-reader **4**, acceptance-runner **6**, RostiFS-harness **16**.
Crash suites passed **2,639** rejected/torn/write/flush faults, **2,328** crash
cuts with reordered pending-sector subsets, and **4,104** root-sector prefix
tears. These are trace-derived cases inside tests, not separate test binaries.
Tests compare complete exact old/new trees and bytes; include full/fragmented
volumes, corruption with recomputed CRCs, generation retirement, binary data,
names/paths, repeated remounts, deterministic modeled operations and reuse.

Successful flush means all preceding writes become durably ordered in the
documented simulation model. Subset sampling is not every possible permutation;
CRC collision, dishonest disk firmware and physical power interruption are not
proved. See FORMAT.md. The ATA/QEMU protocol is tested, but no physical
power-loss safety claim follows.

The completed release matrix, exact ISO/hash and failed-development evidence
are recorded in HANDOVER.md and the Phase 9 acceptance report. Archived earlier
milestone results below are not current release evidence.

## Phase 8 acceptance protocol

Run `python -B scripts/phase6_verify.py` from the canonical repository.
The retained filename now reports Phase 8 and preserves a versioned
`dist/rosti_phase8_<UTC>.iso` only after the local gates pass. Source and script
hashes must remain stable during the run. Do not run other QEMU instances beside
the global orphan-checking boot harness.

The block matrix uses `scripts/block_test.py --ram 128|512`, optionally
`--iso dist/rosti.iso`, with a unique `--output-dir`. It must prove device
capacity, full-sector integrity, checked bounds, missing-device behavior,
refusal of unmarked media and persistence after guest reboot and full QEMU
process restart. New owned raw images live under `dist/`; serial/QMP reports
live under `test_results/phase8/`. No Proxmox disks are part of this matrix.

Host scripted-bus tests cover failures and protocol sequencing; only the real
QEMU disk tests prove privileged I/O and persistence. Existing filesystem,
descriptor, heap/OOM, paging, keyboard and VGA gates remain required. RAM files
remain volatile even when block tests pass.

Phase 8 measured results: completed
`test_results/phase8/acceptance_20261013T091203Z_kq161don/acceptance.json`,
**27/27 gates PASS**, Rust **117/117**, Python media readers **4/4** and
acceptance regressions **5/5**. Block integration is **98/98** for each
ELF/ISO + 128/512 MiB combination; filesystem/descriptor/growth/OOM is
**102/102** across 38 commands for each combination. Independent boots are
10/10 per RAM size, paging 20/20, CPU read/write faults 2/2 each, ISO paging
2/2 and VGA editing 13/13 per ELF/ISO path. Kernel/host fmt, production build,
ELF 8/8, keyboard and GRUB boot passed. Source freeze and artifact hashes were
independently reread after completion; no emulator was left running.

Accepted ISO: `dist/rosti_phase8_20261013T091203Z.iso`, SHA256
`5ca54fe8eff24743a8935cbfd8de8f59808bd3ec14f85b23b65c34c3fd0dc6da`.
The interrupted foreground run's RUNNING report is not acceptance; use the
completed background run above. HANDOVER.md records memory counters and
remaining limits. Prior results below are archived checkpoints.


## Verified Phase 7 acceptance (previous checkpoint)

Evidence: `test_results/phase7/acceptance_20261012T181123Z_ovwvkk1g/acceptance.json` (the run whose ISO was deployed to VM 103), `test_results/phase7/acceptance_20261012T231050Z_afsptz17/acceptance.json` (final re-run against the exact committed source; the only source delta was a comment in src/fd.rs, no binary behavior change) and
`test_results/phase7/live_vm103/` (report.json + serial.txt). Phase 6 evidence
(`test_results/phase6/...`) remains the verified prior checkpoint; earlier
sections below describe historical checkpoints.

| Gate | Final result |
|---|---|
| Kernel/host formatting, production build | PASS |
| Rust host tests | 93 PASS / 0 FAIL (15 new descriptor tests) |
| Python QMP-reader regressions | 4 PASS / 0 FAIL |
| ELF contract | 8 PASS / 0 FAIL |
| Independent ELF boots | 10/10 at 128 MiB + 10/10 at 512 MiB |
| Paging stability | 20/20 (10 at each RAM size) |
| CPU read/null-write fault fixtures | 4/4 (both RAM sizes) |
| Keyboard integration | PASS, all stages |
| Actual VGA editing | 13/13 ELF + 13/13 ISO at 512 MiB |
| Filesystem/growth/OOM + descriptor integration | 102/102 each: ELF 128/512 and ISO 128/512 MiB, 38 commands |
| GRUB ISO build/boot + ISO paging | PASS; paging 2/2 RAM configurations |
| Local acceptance pipeline | 21/21 gates |
| VM 103 live filesystem/shell/stress + descriptors | 104/104 across 38 dispatched commands |

Descriptor-specific live/QEMU checks (all PASS at every configuration):
`mem` exposes descriptor counters; file commands dispatch through the
descriptor layer, close cleanly, and leave only the reserved console
descriptors open; `fdlist` shows fd 0 console-in, fd 1/2 console-out; VGA
prompt survives `fdlist`. Host tests cover allocation, reuse, generation
validation, stale handles, invalid indexes, double close, exhaustion,
open/close, read/write offsets, seek boundaries, EOF, shared offsets after
duplication, refcounts, read-only restrictions, attenuation, escalation
rejection, deletion while open, directory type rules, offset overflow, OOM
handling, leak-free open/close cycles and the static-table size budget.

`python -B scripts/phase6_verify.py` (retained filename; it now reports phase 7
and writes `test_results/phase7/`) is the fail-closed local runner. It snapshots
source hashes and refuses changed source during acceptance, restores production
after fault fixtures, preserves the old ISO, and creates a versioned artifact.

A live-verifier compatibility failure was reproduced from the actual QMP report:
Proxmox wraps its media filename in a throttle/raw/file JSON descriptor. The
reader checks the exact file leaf on ide2, not a substring. The live run passes
the full runtime path as `--expected-iso`; no assertion was weakened.

Reproduce individual filesystem checks:
```bash
python -B scripts/fs_test.py --ram 128 --stress
python -B scripts/fs_test.py --ram 512 --stress
python -B scripts/fs_test.py --iso dist/rosti_phase7_20261012T181123Z.iso --ram 128 --stress
python -B scripts/fs_test.py --iso dist/rosti_phase7_20261012T181123Z.iso --ram 512 --stress
python -B scripts/test_fs_harness.py
```
The harness requires completed next-prompt boundaries, rejects echo-only file
read/stat evidence, captures VGA cells, compares exact heap use before/after
deletion, and exercises quota plus actual global-allocator OOM. It verifies
legacy help/version/CPU/timer/echo/clear/Backspace and overlong-write rejection.

Live growth is now verified, not merely host-tested: 4,194,304 file bytes read
back; 1,536 writable supervisor growth pages inspected; heap capacity
1,048,576 -> 7,340,032 bytes; four intentional allocation failures; heap used
8,232 -> 8,232 bytes after cleanup, payload 0 and root-only metadata. The
fixture runs once from a fresh boot for a new-growth assertion. Growth pages
stay mapped. Ring-overflow recovery is host-tested; upstream controller loss
is not claimed detectable.

Phase 7 ISO: `rosti_phase7_20261012T181123Z.iso`; SHA256
`4c1e337d1362d827248ad0e3ee13f8c67bb29cdff3a1a460d1cd1d5e97b62bb4`
(local == remote). Phase 6 rollback ISO remains
`rosti_phase6_20261012T152259Z.iso`, SHA256
`8b3a4d4dbb0f245a2b969e3aed7d973cdf46a2b6e5da07f0a189da23c44472cb`.


## Historical Phase 5 acceptance (2026-10-12)

- Kernel and host formatting PASS; production build PASS with warnings only.
- Host tests: **59/59** (`bash scripts/run_tests.sh`), including the Phase 5
  additions: runtime map/unmap/translate, duplicate-mapping and unaligned
  rejection, permission inspection, TLB-invalidation counters, heap
  alloc/free/reuse, alignment and fragmentation accounting, block coalescing,
  out-of-memory behaviour, invalid-dealloc rejection, growth-window claim and
  on-demand mapping, plus a recorded performance baseline.
- QEMU: boot harness 10/10; paging stability 10 runs each at 128 and 512 MiB;
  CPU read-fault and null-write fault fixtures pass at both RAM sizes with the
  extended diagnostics (`fetch=` field now part of the expected fault line).
- Keyboard integration PASS; VGA editing 13 checks on ELF and 13 on ISO.
- ISO built, boots, SHA256 `5b8875f9e8b848a346ef22a93eec689688a5cf55ec0c4e765209a8f83ec9015f`;
  deployment 25/25 gates; live VM 103 20/20 pipeline checks.
- Phase 5 live shell verification (`scripts/live_phase5_check.py`, run on the
  Proxmox host): **13/13 PASS** — `help`, `version`, `uptime`, `mem` frame/
  paging/heap/fault diagnostics, and a keyboard-edit round trip. Hardware
  registers read back live: CR0 = `80010011` (PG and WP set), CR3 = `00001000`,
  null PTE absent. Evidence: `test_results/phase5/live_vm103_report.json`.
- Performance baseline (host, isolated instances, two runs): frame alloc
  ~2.4-2.6 µs/op, frame free ~10 ns, map ~275-300 ns, unmap ~260-290 ns, heap
  alloc ~1.9-2.0 µs, heap free ~1.5-1.7 µs; checkerboard fragmentation 251 free
  blocks. Recorded in `test_results/phase5/perf_baseline.json`; no optimization
  applied.

Phase 5 growth path is verified in host tests; the live VM reported
`Growth pages: 0` because the workload never exceeded the initial 1 MiB region,
so live heap growth was not exercised on VM 103.

## Phase 4 acceptance (2026-10-12)

- Kernel/host formatting PASS; production build PASS with compiler warnings.
- Host tests: 49/49; ELF validation: 8/8; standard boot runner: 10/10.
- Paging stability: 10 runs each at 128 and 512 MiB, all with paging active.
- CPU fault fixtures: unmapped read (code 0, CR2 `0xfffff000`) and null write
  (code 2, CR2 zero) at both RAM sizes; correct diagnostics and fatal halt.
- Keyboard integration PASS; VGA editing: 13 checks each on ELF and ISO.
- ISO boot and paging at both RAM sizes PASS. Fault-test binaries are rejected
  by the ISO builder; production is rebuilt without features before packaging.
- Deployment: 25/25 gates; VM 103 live checks: 20/20, including CR0.PG,
  CR3, absent null PTE, `mem` output and Backspace. Remote/local hashes match.
- Acceptance: `test_results/phase4/acceptance.json`; complete gate log:
  `test_results/phase4/deployment_pipeline.log`; live details:
  `test_results/proxmox/phase4_live_report.json`.
- Exact reproduction commands and remaining limits are in HANDOVER.md.

## Deterministic QEMU boot test

`scripts/boot_test.py` is the single boot-test runner (the old bash probe is a
thin wrapper around it). It is deterministic and bounded:

- Runs `qemu-system-i386.exe -kernel target/target/debug/kernel` headless with
  `-serial file:` per-run output under `test_results/run_NN/` (unique dir per
  run), plus a QEMU debug log (`-d int,guest_errors`).
- Strict end-to-end timeout (default 20 s, configurable); kills **only** the
  QEMU process it started; verifies no orphaned `qemu-system-i386.exe` remains.
- PASS requires both markers, in order:
  - `ROSTI: entered kernel_main`
  - `ROSTI: boot complete`
- FAIL is classified as `KERNEL_FAULT` (triple fault, reboot loop, kernel
  entered but init incomplete) vs `HARNESS_FAIL` (QEMU launch failure, output
  capture failure). Failed runs keep their logs in the run directory.
- Results CSV: `test_results/boot_results.csv` (run, status, class, markers,
  exit, elapsed, dir).

```
python scripts/boot_test.py --runs 10 --timeout 15
bash scripts/stability_probe.sh 10
```

## Verified results (2026-10-09)

Before the ISR fix, 10-run probes were 7/10–8/10 with intermittent
`KERNEL_FAULT (init incomplete)`. QEMU int-trace evidence (`Servicing hardware
INT=0x21` during init) showed the keyboard ISR fired while the main path held
the VGA writer SpinMutex; the ISR's `println!` re-locked the non-reentrant
mutex → deadlock. Fix: ISRs use the lockfree serial writer only.

After the fix: **10/10 consecutive independent boots PASS** (both markers, in
order), no orphaned processes. Evidence: `test_results/boot_results.csv`.

## ISO boot test

`scripts/build-proxmox-iso.py` validates the ELF/multiboot contract, builds
`dist/rosti.iso` via WSL `grub-mkrescue` (i386-pc, BIOS), then boots the ISO
in QEMU as a virtual CD-ROM and requires both markers. Verified PASS — serial
output from the ISO path:

```
ROSTI: entered kernel_main
keyboard input
kb scancode: 97
ROSTI: boot complete
dummy handler!
```

(The `dummy handler!` line is a real interrupt reaching the IDT through GRUB's
multiboot handoff — proof the interrupt path works from the ISO boot path.)

## Historical host unit tests

`bash scripts/run_tests.sh` — 18 tests (must run from outside the project dir;
the kernel's `.cargo/config.toml` forces build-std which breaks the host test
harness). Covers: bit manipulation, IDT gate encoding, GDT descriptor encoding,
align_up, bump allocator arithmetic + boundary rejection, port allocator,
spinlock, variable-length mmap parsing (standard/variable/truncated entries),
usable-block selection. All 18 pass.

## Earlier Backspace-only verification (2026-10-12)

```
cargo build --target target.json
bash scripts/run_tests.sh
python scripts/keyboard_test.py
python scripts/backspace_test.py
python scripts/build-proxmox-iso.py
python scripts/backspace_test.py --iso dist/rosti.iso
```

- Build succeeds with existing compiler warnings; host tests: 38 passed.
- Keyboard integration passes. Backspace regression: 13 VGA/serial checks
  pass for both the ELF and GRUB ISO at 512 MiB (matching VM 103).
- Regression checks erased cells, replacement, wrapped-line deletion,
  prompt protection, whitespace-only dispatch, and edited command output.
  VGA capture is validated against the real boot prompt before assertions;
  it is not inferred from serial command output.
- Ten independent 128 MiB boots pass, with evidence preserved separately:
  `test_results/backspace/stability_20261012_155425/boot_results.csv`.
- Final display evidence: `test_results/backspace/20261012_155351/report.json`.
- Proxmox VM 103 was updated and live-verified: all 16 VGA/serial/boot checks
  passed using `scripts/verify_proxmox_backspace.py` on the Proxmox host.
  Evidence: `test_results/proxmox/backspace_verified.json`. The VM is running
  the checksum-verified ISO and was left at a clean shell prompt.
- At this earlier checkpoint, paging enabled only at 128 MiB. Phase 4 fixes
  now enable it at 512 MiB as well; see current acceptance above.

## Other test limitations

- QEMU must be terminated by the harness (kernel idles in `hlt` after boot);
  "PASS" means markers captured before the bounded timeout, not a clean exit.
- The serial `file:` chardev flushes per byte (verified empirically); a
  `pipe:` chardev variant lost output on SIGTERM and was abandoned.
- Interrupts are enabled during init, so a stray hardware interrupt can execute
  an ISR mid-println; this is exactly the class of bug the ISR fix addresses.
