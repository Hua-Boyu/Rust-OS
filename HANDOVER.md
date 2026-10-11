# Rosti OS — Technical Handover (v0.1.0 checkpoint)

Date: 2026-10-10. Author: autonomous release session. Status: verified against the live repository, not from prior-session claims alone.

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

- `src/main.rs` — entry + panic handler; init sequence: serial → VGA → allocator → memory-map print/shell mem info → GDT → IDT → PS/2 enable → shell loop (idle via `hlt`).
- `src/boot.s` — `_start`: 16 KiB stack, pushes multiboot magic + info pointer, calls `kernel_main`.
- `src/multiboot.rs` — BootInfo layout; bounds-checked, variable-entry-size mmap parser; allocation-free `find_usable_block`.
- `src/allocator.rs` — `SpinMutex<BumpAlloc>` global allocator; reserves the kernel image region; dealloc resets when no live allocations.
- `src/gdt.rs` — null/code/data descriptors (OR-based access byte, correct lgdt limit, segment reload).
- `src/interrupt.rs` — 256-entry IDT, PIC remap to 0x20/0x28, fully unmasked; keyboard ISR; hardware-IRQ dummy handlers send EOI. **Rule: ISRs use only the lockfree serial writer** (VGA writer is behind a non-reentrant SpinMutex → deadlock, fixed and regression-tested).
- `src/kbd.rs` — PS/2 scan-code set 1 decoder, QWERTY layout table, interrupt-safe ring-buffer event queue.
- `src/timer.rs` — PIT at 100 Hz, tick counter, uptime.
- `src/io/ports.rs` — 64 KiB port allocator with RAII `Port`; lockfree in/out for ISR context.
- `src/io/serial.rs` — COM1 16550 polled writer (debug channel, observable via QEMU `-serial file:`).
- `src/io/vga.rs` — 80x25 text writer behind SpinMutex (main path only).
- `src/shell.rs` — command dispatch loop reading from the keyboard queue: `help clear version mem cpu uptime echo reboot`.
- `src/cpu.rs` — CPUID vendor/family/model identification.
- `src/reboot.rs` — keyboard-controller reboot triple-fault mechanism.
- `src/utils/` — bit-manipulation trait, SpinMutex.
- `scripts/` — `run_tests.sh` (host tests), `boot_test.py` (deterministic QEMU boot harness), `keyboard_test.py` (keyboard integration stages), `validate_elf.py` (multiboot ELF contract), `build-proxmox-iso.py` (ISO build + boot verify), `deploy-proxmox.py` (11-gate deployment pipeline, env-var credentials only), `sendkey_probe.py`, `stability_probe.sh`, `qemu_boot_test.sh`.
- `tests_kernel/` — host-side unit tests for pure algorithms only (privileged asm cfg-gated out).
- `test_results/` — sanitized evidence: `boot_results.csv`, per-run serial captures, `proxmox/deploy_report.json`, `proxmox/boot_103_run01.log`. Raw QEMU debug logs are gitignored.
- `dist/` — ISO artifacts (gitignored, kept locally): `rosti.iso` (current release), `rosti_rollback.iso` (rollback), `dist/stage/` (grub staging tree).

## D. Boot architecture

BIOS (SeaBIOS) → GRUB (i386-pc, from ISO) or QEMU ELF loader → Multiboot v1 handoff (`magic == 0x2BADB002`, info pointer in `%ebx`) → `boot.s::_start` → `kernel_main` → serial init → VGA → allocator init → GDT → IDT → PIC remap/unmask → PS/2 enable → shell.

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

Shell commands (all live-verified on VM 103 unless noted): `help`, `clear`, `version`, `mem`, `cpu`, `uptime`, `echo`, `reboot`. Live-tested on VM 103: `help`, `version`, `echo` (incl. Backspace edit), `uptime`.

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

Latest re-verification (2026-10-10, this checkpoint): fmt PASS, build PASS, 27/27 host tests, QEMU boot 1/1 PASS, keyboard integration PASS, ELF validation 8/8 PASS, GRUB ISO boot PASS. The current `dist/rosti.iso` SHA256 still matches the deployed release — no rebuild was needed.

Evidence paths: `test_results/boot_results.csv`, `test_results/iso_boot/serial.txt`, `test_results/keyboard/`, `test_results/proxmox/deploy_report.json`, `test_results/proxmox/boot_103_run01.log`.

## G. Proxmox deployment

- Node `pve`, VM **103** (`rosti-dev`) — preserve it; do not create duplicates.
- Config: i440fx, SeaBIOS, 1 core, 512 MiB, `serial0: socket`, boot from IDE CD-ROM.
- Deployed ISO: `rosti_20261010T154256Z.iso`, SHA256 `bbfa45f92211cef0a8aa587cc69adf3ba35342b05582db46e35e62d0d0afa8d5` (remote == local, verified).
- Rollback ISO retained locally: `dist/rosti_rollback.iso` (SHA256 `0fffc984895e74739b51c98c2d209a6d7b2f6499fb0e2b4b7524d022d241e0d0`).
- Serial console verified via `/var/run/qemu-server/103.serial0`; interactive input via `qm sendkey 103 <key>`.
- Pipeline: `scripts/deploy-proxmox.py` — 11 gates, stops on any failure, touches only VM 103. Credentials come ONLY from environment variables (`PVE_TOKEN_ID`, `PVE_TOKEN_SECRET`, `PVE_ROOT_PASSWORD`); never hardcode them. Auth artifacts (`.pve_auth`, `$AUTH`) are gitignored.
- Rollback strategy: keep the previous verified ISO; if a new ISO fails, reattach the rollback ISO to VM 103.

## H. Resource requirements

- VM 103 allocation: 512 MiB RAM, 1 core — this is allocation, NOT kernel consumption.
- ISO size: ~8.6 MB (8,622,080 bytes), mostly GRUB/GRUB-image overhead; kernel ELF ~3.5 MB debug build.
- Actual kernel memory footprint: bump allocator reserves the kernel image region within a usable mmap block; no measured runtime RSS figure exists yet. QEMU boot tests run with `-m 128` and succeed, so ≤128 MiB is demonstrated sufficient for boot; 512 MiB allocation is comfortable headroom, not a requirement.
- Idle CPU: kernel idles in `hlt` after boot (near-zero, not independently metered on VM 103).

## I. Known bugs and limitations

Confirmed open issues (from BUGFIXES.md and source audit):
- Exception handlers with CPU-pushed error codes: only slot 13 registered; slots 8, 10–14, 16 need dedicated ISRs.
- PS/2 handling is a minimal enable stub: no command-write timeout handling, no ACK byte checking.
- SpinMutex is not interrupt-safe (no reentrancy guard); safe only because ISRs avoid mutex-backed writers — must be hardened before general use.
- `~9 unsafe blocks` across modules; acceptable for a kernel but each needs review as subsystems grow.
- QEMU "PASS" means markers captured before harness timeout (kernel never exits cleanly from `hlt` idle).
- `dealloc` resets the bump allocator when no live allocations remain — no fragmentation handling, no real page management.

Missing OS subsystems (not implemented, do not claim otherwise): filesystem, persistent disk storage, physical memory manager/paging, virtual memory, scheduler/multitasking, user-mode processes, syscall interface, ELF executable loader, networking, package management, USB stack, security isolation for user programs.

## J. Development priorities (proposed, not completed)

Dependency-aware roadmap:
1. **Phase 4 — Physical memory management and paging**: audit multiboot mmap boundaries, reserve kernel/bootloader/MMIO regions, physical frame allocator, identity-mapped paging for boot-critical regions, host tests for allocation bounds.
2. Phase 5 — RAM filesystem + basic VFS (depends on Phase 4).
3. Phase 6 — Persistent block storage (ATA/IDE driver).
4. Phase 7 — Task scheduling and context switching (depends on paging).
5. Phase 8 — User-mode execution (ring 3) + syscall interface.
6. Phase 9 — ELF executable loading.
7. Phase 10 — Networking and expanded device support.

## K. Safe operating boundaries

- Preserve VM 103; never create duplicate VMs; never modify unrelated VMs.
- Preserve rollback ISOs; never overwrite the deployed verified release without a checksum record.
- Never expose credentials; scripts read them from environment variables only; never commit `.pve_auth`, `$AUTH`, `.env`, keys, or tickets.
- Never alter unrelated services on n100 or pve.
- Preserve test evidence; keep development reproducible (deterministic harnesses, pinned toolchain).

## L. Git checkpoint

Branch `main`, commit `1f560d904dd785350f7712097dc1bf51119be1c0` — `feat(rosti): establish v0.1.0 interactive kernel baseline`. Annotated local tag: `v0.1.0`.
