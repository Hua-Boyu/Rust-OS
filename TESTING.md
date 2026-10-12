# TESTING

## Current Phase 7 acceptance

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
