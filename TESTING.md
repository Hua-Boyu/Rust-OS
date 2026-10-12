# TESTING

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

## Host unit tests

`bash scripts/run_tests.sh` — 18 tests (must run from outside the project dir;
the kernel's `.cargo/config.toml` forces build-std which breaks the host test
harness). Covers: bit manipulation, IDT gate encoding, GDT descriptor encoding,
align_up, bump allocator arithmetic + boundary rejection, port allocator,
spinlock, variable-length mmap parsing (standard/variable/truncated entries),
usable-block selection. All 18 pass.

## Shell display regression verification (2026-10-12)

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
- Proxmox VM 103 has not been updated or live-verified: SSH authentication
  is denied and the deployment environment credentials are unset.
- Paging enables in the 128 MiB tests. At 512 MiB, the existing managed-window
  limit causes required-region validation to leave paging disabled safely.

## Other test limitations

- QEMU must be terminated by the harness (kernel idles in `hlt` after boot);
  "PASS" means markers captured before the bounded timeout, not a clean exit.
- The serial `file:` chardev flushes per byte (verified empirically); a
  `pipe:` chardev variant lost output on SIGTERM and was abandoned.
- Interrupts are enabled during init, so a stray hardware interrupt can execute
  an ISR mid-println; this is exactly the class of bug the ISR fix addresses.
