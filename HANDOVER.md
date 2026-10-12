# Rosti OS — Technical Handover (Phase 5 verified checkpoint)

Date: 2026-10-12. Status: Phase 5 virtual memory management, dynamic kernel heap and memory-safety diagnostics verified locally and on Proxmox VM 103. Evidence: `test_results/phase5/live_vm103_report.json`, `test_results/proxmox/deploy_report.json`, `test_results/phase5/perf_baseline.json`.

## A. Project overview

Rosti is a hobby/learning bare-metal operating system kernel written in Rust, targeting i686 (32-bit x86). Goal: reimplement OS fundamentals from scratch with no external crates beyond `core` and `alloc`. Current maturity: a **bootable interactive kernel** — it boots via GRUB multiboot, initializes core hardware structures, accepts PS/2 keyboard input through the IDT, runs a minimal command shell, and is deployed to a Proxmox VM for live serial-console testing. It is NOT a usable OS: no filesystem, no scheduler, no user mode, no networking.

- Language: Rust (nightly), `no_std`/`no_main` for kernel code, custom JSON target.
- Target platform: i686 bare metal, SeaBIOS + GRUB (Multiboot v1). UEFI/OVMF unsupported.
- Repo: `C:\Users\iamsv\Documents\Rust-OS` (canonical since 2026-10-11 migration; formerly `C:\Users\iamsv\Documents\rosti`, preserved as rollback source), branch `main`.

## B. Development environment

- Windows 11 host (EVO-X1); shell commands run through git-bash.
- Rust nightly toolchain pinned in `rust-toolchain.toml`; host tests use `cargo +nightly`.
- Custom target `target.json` (i686-unknown-linux-gnu-style bare-metal ELF, PIC disabled, single PT_LOAD); `.cargo/config.toml` forces `build-std` for core/alloc.
- QEMU: `C:\Program Files\qemu\qemu-system-i386.exe`, invoked headless (`-display none -no-reboot -serial file:... -D ...`).
- WSL dependency: `grub-mkrescue` lives in WSL; ISO staging tree is shared via the project's `dist/stage` (reachable from WSL as `/mnt/c/Users/iamsv/Documents/Rust-OS/dist/stage`).
- Host tests must run from OUTSIDE the project directory (the kernel's `.cargo/config.toml` breaks the host test harness — see `scripts/run_tests.sh`).

## C. Repository architecture

- `src/main.rs` — entry + panic handler; serial → VGA → bounded bootstrap heap → mmap/boot-region capture → frame allocator/page-table validation → GDT/IDT → paging enable → PS/2/PIT → shell (`hlt` idle).
- `src/boot.s` — `_start`: 16 KiB stack, pushes multiboot magic + info pointer, calls `kernel_main`.
- `src/multiboot.rs` — BootInfo layout; bounds-checked, variable-entry-size mmap parser; allocation-free `find_usable_block`.
- `src/allocator.rs` — `SpinMutex<BumpAlloc>` over a page-aligned 1 MiB bootstrap heap inside the kernel's BSS; checked alignment/size arithmetic; resets when no live allocations remain. It no longer claims all remaining RAM or stretches a selected mmap segment across holes.
- `src/memory/frame.rs` — static bitmap allocator below 256 MiB; complete usable pages only, reserved/ACPI entries override usable overlaps, kernel/heap/VGA/boot metadata protected, unaligned/unallocated/reserved/double frees rejected, exhaustion returns None.
- `src/memory/paging.rs` — zero-initialized 4 KiB page tables, identity mapping independent of the frame-allocation cap, null page absent, required-region validation including partial tail pages, rollback of frames on build exhaustion. CR3 loaded then CR0.PG enabled only after IDT setup.
- `src/gdt.rs` — null/code/data descriptors (OR-based access byte, correct lgdt limit, segment reload).
- `src/interrupt.rs` — 256-entry IDT, PIC remap to 0x20/0x28, IRQ0/IRQ1 unmasked; keyboard/PIT ISRs and fatal page-fault diagnostics. Hardware-IRQ dummy handlers send EOI. **ISRs use only the lockfree serial writer**, never mutex-backed VGA output.
- `src/kbd.rs` — PS/2 scan-code set 1 decoder, QWERTY layout table, interrupt-safe ring-buffer event queue.
- `src/timer.rs` — PIT at 100 Hz, tick counter, uptime.
- `src/io/ports.rs` — 64 KiB port allocator with RAII `Port`; lockfree in/out for ISR context.
- `src/io/serial.rs` — COM1 16550 polled writer (debug channel, observable via QEMU `-serial file:`).
- `src/io/vga.rs` — 80x25 text writer behind SpinMutex (main path only).
- `src/shell.rs` — command dispatch loop reading from the keyboard queue: `help clear version mem cpu uptime echo reboot`.
- `src/cpu.rs` — CPUID vendor/family/model identification.
- `src/reboot.rs` — keyboard-controller reboot triple-fault mechanism.
- `src/utils/` — bit-manipulation trait, SpinMutex.
- `scripts/` — host/boot/keyboard/ELF/ISO runners plus `paging_test.py` (RAM-size matrix and fatal CPU-fault fixtures), `backspace_test.py` (actual VGA cells), `verify_proxmox_backspace.py --require-paging` (live registers, PTE and shell checks), and the 25-gate `deploy-proxmox.py` pipeline. SSH credentials come from environment only and use binary stdin, not argv.
- `tests_kernel/` — host-side unit tests for pure algorithms only (privileged asm cfg-gated out).
- `test_results/` — sanitized evidence: `boot_results.csv`, per-run serial captures, `proxmox/deploy_report.json`, `proxmox/boot_103_run01.log`. Raw QEMU debug logs are gitignored.
- `dist/` — ISO artifacts (gitignored, kept locally): `rosti.iso` (current release), `rosti_rollback.iso` (rollback), `dist/stage/` (grub staging tree).

## D. Boot architecture

BIOS → GRUB or QEMU ELF loader → Multiboot v1 → `boot.s::_start` → serial/VGA → bootstrap heap → memory map and boot reservations → physical frames/page tables → mapping validation → GDT/IDT/PIC → CR3 and CR0.PG → PS/2/PIT → shell.

Boot markers (harness PASS criteria, in order):
```
ROSTI: entered kernel_main
ROSTI: boot complete
```
Live ISO-path evidence of a real interrupt reaching the IDT: `keyboard input` / `kb scancode: 97` / `dummy handler!`.

## E. Implemented features (with verification status)

| Feature | Status |
|---|---|
| Multiboot v1 ELF contract | Implemented + validated (`validate_elf.py`, 8/8 PASS) |
| GDT / IDT / PIC init | Implemented, host-tested + boot-verified |
| COM1 serial console | Implemented, verified in QEMU and on VM 103 |
| VGA text console | Implemented, boot-verified |
| PS/2 keyboard + scan-code decode | Implemented, host-tested + verified live on VM 103 (scancode 97 via IDT) |
| Interrupt-safe keyboard event queue | Implemented, host-tested (ring buffer tests) |
| PIT timer / uptime | Implemented, verified live (`uptime` on VM 103) |
| Kernel shell | Implemented, verified live on VM 103 |
| Multiboot memory-map parsing | Implemented, host-tested (bounds, variable sizes, type filtering) |
| Bump allocator | Implemented, host-tested (arithmetic + boundary rejection) |
| CPU identification (CPUID) | Implemented, present in shell `cpu` command |
| Reboot mechanism | Implemented (not exercised destructively on VM 103) |
| Idle via `hlt` | Implemented, verified |
| Physical frame allocator | Implemented; reservation, release/bounds, overlap and exhaustion regressions pass; Phase 5 adds growth-window frame claims with consistent reserved→allocated accounting |
| Identity paging / null guard | Active at 128 and 512 MiB, including VM 103; CR0.PG/CR3 and absent null PTE inspected live |
| Fatal page-fault diagnostics | CPU unmapped-read and null-write faults verified locally at both RAM sizes; error code/CR2 checked; extended to report the instruction-fetch bit; last-fault record exposed via shell `mem` |
| Runtime page mapping (Phase 5) | map/unmap/translate/permissions with conflict, alignment and range rejection; per-page TLB invalidation counters; host-tested |
| Explicit page permissions (Phase 5) | present/writable/user per entry; CR0.WP set live (`CR0=80010011`) so read-only pages fault supervisor writes; NX NOT claimed (unsupported in 32-bit single-directory paging) |
| Dynamic kernel heap (Phase 5) | `KernelHeap` first-fit reclaiming free list with coalescing, alignment-waste tracking, OOM counted without panic, invalid-dealloc rejection; initial region = 1 MiB bootstrap heap, grows one growth-window page at a time; host-tested, live `mem` reports heap stats |
| Shell `mem` diagnostics (Phase 5) | frame stats, paging state, page directory, mapped pages, heap capacity/used/free/failed/live/invalid/blocks/waste/growth, page-fault count and last fault; verified live on VM 103 |

Available shell commands: `help`, `clear`, `version`, `mem`, `cpu`, `uptime`, `echo`, `reboot`. The Phase 4 live verifier exercises `mem`, `clear`, `echo` and Backspace; earlier verification also covered `help`, `version` and `uptime`. Reboot is not destructively tested on VM 103.

## F. Testing — exact commands and latest results

```bash
cargo fmt --check                                              # PASS (2026-10-10)
cargo build                                                  # PASS (9 warnings, no errors)
bash scripts/run_tests.sh                                    # 27/27 PASS (run from $HOME, not project dir)
python scripts/validate_elf.py target/target/debug/kernel    # 8/8 PASS
python scripts/boot_test.py --runs 10 --timeout 15           # 10/10 PASS (evidence: test_results/boot_results.csv)
python scripts/keyboard_test.py                              # PASS (all stages)
python scripts/build-proxmox-iso.py                          # builds dist/rosti.iso + boots it in QEMU; PASS
```

The commands and counts above describe the historical v0.1.0 checkpoint. Current Phase 4 results (2026-10-12): kernel and host fmt PASS; production build PASS with compiler warnings; 49/49 host tests; ELF 8/8; standard boot harness 10/10; paging stability 10 runs each at 128/512 MiB; four CPU-fault cases; keyboard PASS; ELF and ISO VGA editing 13 checks each; ISO paging at both RAM sizes PASS; full deployment 25/25 gates and live VM checks 20/20 PASS.

Current reproduction:
```
cargo fmt --check
cargo +nightly fmt --manifest-path tests_kernel/Cargo.toml --check
bash scripts/run_tests.sh
cargo build --target target.json --features paging-fault-test
python scripts/paging_test.py --fault
cargo build --target target.json --features paging-write-fault-test
python scripts/paging_test.py --write-fault
cargo build --target target.json
python scripts/validate_elf.py target/target/debug/kernel
python scripts/boot_test.py --runs 10 --timeout 3 --output-dir test_results/phase5/new_boot_run
python scripts/paging_test.py --runs 10
python scripts/keyboard_test.py
python scripts/backspace_test.py
python scripts/build-proxmox-iso.py
python scripts/paging_test.py --iso dist/rosti.iso
python scripts/backspace_test.py --iso dist/rosti.iso
python scripts/live_phase5_check.py   # run on the Proxmox host via SSH
```
Phase 5 results (2026-10-12): fmt PASS; production build PASS (warnings only); host tests 59/59; ELF 8/8; boot harness 10/10; paging stability 10 runs each at 128/512 MiB; read-fault and null-write fault fixtures pass at both sizes with the extended `fetch=` diagnostics; keyboard PASS; VGA editing 13 checks ELF + 13 ISO; ISO boot PASS; deployment 25/25 gates; live VM 103 20/20 pipeline checks + 13/13 Phase 5 shell checks (`scripts/live_phase5_check.py`). Performance baseline recorded in `test_results/phase5/perf_baseline.json`.
Fault-test features deliberately halt the guest. NEVER deploy those builds; the ISO builder refuses them. Rebuild without features before creating an ISO. Deployment reruns all gates: `python scripts/deploy-proxmox.py` with `PVE_ROOT_PASSWORD` supplied privately in the process environment.

Evidence paths: `test_results/boot_results.csv`, `test_results/iso_boot/serial.txt`, `test_results/keyboard/`, `test_results/proxmox/deploy_report.json`, `test_results/proxmox/boot_103_run01.log`.

## G. Proxmox deployment

- Node `pve`, VM **103** (`rosti-dev`) — preserve it; do not create duplicates.
- Config: i440fx, SeaBIOS, 1 core, 512 MiB, `serial0: socket`, boot from IDE CD-ROM.
- Deployed ISO: `rosti_20261012T125244Z.iso`, SHA256 `5b8875f9e8b848a346ef22a93eec689688a5cf55ec0c4e765209a8f83ec9015f` (remote == local, checked before attachment and after live verification). Prior versioned ISOs remain available.
- Rollback ISO retained locally: `dist/rosti_rollback.iso` (SHA256 `0fffc984895e74739b51c98c2d209a6d7b2f6499fb0e2b4b7524d022d241e0d0`).
- Serial console verified via `/var/run/qemu-server/103.serial0`; interactive input via `qm sendkey 103 <key>`.
- Pipeline: `scripts/deploy-proxmox.py` — 25 gates, stops on failure, VM 103 only. `PVE_ROOT_PASSWORD` enables SSH/scp/pvesh; an API token is not needed for that path. Secrets use binary stdin and are never committed. Current evidence: `test_results/proxmox/deploy_report.json`, `phase4_live_report.json`, `test_results/phase5/live_vm103_report.json`. VM is running, CR0=`80010011` (PG+WP), CR3=`00001000`, null PTE absent, shell `mem` reports paging enabled, heap stats and fault count, Backspace works.
- Rollback strategy: keep the previous verified ISO; if a new ISO fails, reattach the rollback ISO to VM 103.

## H. Resource requirements

- VM 103 allocation: 512 MiB RAM, 1 core — this is allocation, NOT kernel consumption.
- ISO includes GRUB and the debug kernel; sizes change across builds, so inspect the current artifact rather than using historical size numbers.
- Bootstrap heap is 1 MiB inside the kernel's BSS; no runtime RSS figure is claimed. Paging and boot tests pass with both 128 and 512 MiB guest RAM.
- Idle CPU: kernel idles in `hlt` after boot (near-zero, not independently metered on VM 103).

## I. Known bugs and limitations

Confirmed open issues (from BUGFIXES.md and source audit):
- Vector 14 has verified fatal diagnostics; other error-code exception handlers still need hardening. This is not a general exception recovery subsystem.
- PS/2 handling is a minimal enable stub: no command-write timeout handling, no ACK byte checking.
- SpinMutex is not interrupt-safe (no reentrancy guard); safe only because ISRs avoid mutex-backed writers — must be hardened before general use.
- Hardware-facing unsafe code needs continuing review as subsystems grow; no current block-count claim is made.
- QEMU "PASS" means markers captured before harness timeout (kernel never exits cleanly from `hlt` idle).
- Physical frame allocation is capped at 256 MiB; identity mappings can cover RAM above that cap. No user address spaces, demand paging, swapping or user isolation; boot mappings are supervisor/writable, runtime `PagePerms` support read-only and user bits, and CR0.WP is set so read-only pages fault supervisor writes. Boot strings/config buffers conservatively reserve 4 KiB; arbitrarily long boot strings are outside current support.
- Phase 5 heap: `KernelHeap` is the global allocator (reclaiming, coalescing, OOM-safe); `BumpAlloc` remains for early boot. Heap growth is verified in host tests but was not exercised on VM 103 (live workload stayed under the initial 1 MiB region). NX is not supported in 32-bit single-directory paging and is not claimed.

Missing OS subsystems: filesystem, persistent block storage, process virtual-memory management, scheduler/multitasking, user-mode processes, syscall interface, ELF executable loader, networking, package management, USB and user-program security isolation.

## J. Development priorities (proposed, not completed)

Dependency-aware roadmap:
1. **Phase 4 — completed**: frame allocator, boot reservations, identity paging, fatal fault tests, regression/deployment evidence.
2. **Phase 5 — completed (2026-10-12)**: runtime page map/unmap/translate with permissions and TLB invalidation, growth-window on-demand mapping, dynamic reclaiming `KernelHeap`, extended page-fault diagnostics, shell `mem` diagnostics, performance baseline recorded for a later optimization pass.
3. Phase 6 — RAM filesystem + basic VFS (depends on the Phase 5 heap and paging).
4. Phase 7 — Persistent block storage (ATA/IDE driver).
5. Phase 8 — Task scheduling and context switching (depends on paging).
6. Phase 9 — User-mode execution (ring 3) + syscall interface (depends on per-process address spaces, which the Phase 5 runtime mapping API makes possible).
7. Phase 10 — ELF executable loading.
8. Phase 11 — Networking and expanded device support.

## K. Safe operating boundaries

- Preserve VM 103; never create duplicate VMs; never modify unrelated VMs.
- Preserve rollback ISOs; never overwrite the deployed verified release without a checksum record.
- Never expose credentials; scripts read them from environment variables only; never commit `.pve_auth`, `$AUTH`, `.env`, keys, or tickets.
- Never alter unrelated services on n100 or pve.
- Preserve test evidence; keep development reproducible (deterministic harnesses, pinned toolchain).

## L. Git checkpoint

Branch `main`. The Phase 5 completion commit is titled `feat(memory): implement Phase 5 virtual memory and dynamic kernel heap`; resolve its hash with `git log -1 --oneline` rather than relying on a self-referential hash in this document. The Phase 4 baseline commit is `46af27e`. Historical local tag `v0.1.0` remains the older baseline.
