# Rosti OS — Next Session Prompt (Phase 4: Physical Memory Management and Paging)

You are continuing development of Rosti OS. This prompt is standalone — no prior chat history is assumed.

## 1. Project identity

- Repo: `C:\Users\iamsv\Documents\rosti` (Windows 11 host, git-bash shell).
- Rosti is a bare-metal i686 Rust kernel (nightly, custom JSON target, `no_std`, only core/alloc), booted via GRUB Multiboot v1 under SeaBIOS, with VGA + COM1 serial consoles, PS/2 keyboard, PIT timer, and a minimal shell.
- Read `HANDOVER.md` first — it is the authoritative handover (architecture, boot sequence, test commands, Proxmox state, limitations, safety boundaries).

## 2. Last committed checkpoint

- Branch: `main`
- Commit: `1f560d904dd785350f7712097dc1bf51119be1c0` — `feat(rosti): establish v0.1.0 interactive kernel baseline`
- Tag: `v0.1.0` (annotated, local)

## 3. Verified functionality (do not re-litigate; re-run tests to confirm regressions)

- Build + `cargo fmt --check`: PASS.
- Host tests: 27/27 PASS (`bash scripts/run_tests.sh` — MUST run from outside the project dir, e.g. `$HOME`).
- QEMU boot harness: 10/10 PASS (`python scripts/boot_test.py --runs 10`); PASS = markers `ROSTI: entered kernel_main` then `ROSTI: boot complete`.
- Keyboard integration: PASS (`python scripts/keyboard_test.py`); live scancode 97 received via IDT.
- ELF/multiboot validation: 8/8 PASS (`python scripts/validate_elf.py target/target/debug/kernel`).
- GRUB ISO boot: PASS (`python scripts/build-proxmox-iso.py`; current `dist/rosti.iso` SHA256 `bbfa45f92211cef0a8aa587cc69adf3ba35342b05582db46e35e62d0d0afa8d5` matches the deployed release — do NOT rebuild unless a code change requires it, and then distinguish the new artifact from the deployed one).
- Proxmox: VM 103 booted the deployed ISO; shell commands `help`, `version`, `echo` (incl. Backspace), `uptime` verified over the serial socket.

## 4. Exact test commands

```bash
cargo fmt --check
cargo build
bash scripts/run_tests.sh            # from $HOME, not the project dir
python scripts/validate_elf.py target/target/debug/kernel
python scripts/boot_test.py --runs 10 --timeout 15
python scripts/keyboard_test.py
python scripts/build-proxmox-iso.py  # only when ISO-affecting changes are made
```

## 5. Proxmox VM 103 (preserve it)

- Node `pve`, VM 103 `rosti-dev`: i440fx, SeaBIOS, 1 core, 512 MiB, `serial0: socket`, boot IDE CD-ROM.
- Deployed ISO: `rosti_20261010T154256Z.iso` (SHA256 above); rollback ISO `dist/rosti_rollback.iso` retained.
- Serial console: `/var/run/qemu-server/103.serial0`; input via `qm sendkey 103 <key>`.
- Credentials come ONLY from environment variables (`PVE_TOKEN_ID`, `PVE_TOKEN_SECRET`, `PVE_ROOT_PASSWORD`). Never commit `.pve_auth`, `$AUTH`, `.env`, or any ticket/token.
- Deploy only to VM 103 via `scripts/deploy-proxmox.py` (11 gates) AFTER all tests pass.

## 6. Immediate objective — Phase 4: Physical memory management and paging

Scope, in order:
1. Audit the existing Multiboot memory-map handling (`src/multiboot.rs`) and bump-allocator boundaries (`src/allocator.rs`).
2. Design and implement a physical frame allocator (bitmap or free-list over usable mmap regions).
3. Reserve correctly: kernel image region, bootloader-held regions, ACPI/Reserved (mmap type 2/3) regions, MMIO gaps; do not allocate from non-usable entries.
4. Implement paging (i686 4 KiB pages): identity-map kernel and boot-critical regions; enable via CR0.PG + CR4.PSE or map page tables; keep the boot path safe.
5. Add host-side tests: frame allocation/release, bounds rejection, reserved-region protection, double-allocate, exhaustion.
6. Preserve serial/VGA behavior; keep the ISR rule (ISRs use only the lockfree serial writer — never a mutex-backed writer).
7. Regression-test with the QEMU boot harness (both markers) before any Proxmox deployment.
8. Deploy to VM 103 only after all gates pass; record the new ISO's SHA256 separately from the deployed release.

Do NOT implement multitasking, filesystem, or networking in this phase. Avoid architecture rewrites; extend the existing modules.

## 7. Known limitations to respect

- No filesystem, no scheduler, no user mode, no syscall interface, no ELF loader, no networking, no USB.
- Exception ISRs with error codes (8, 10–14, 16) are not yet registered — paging faults will need a real handler before paging is safe.
- SpinMutex is not interrupt-safe; harden or avoid it in new interrupt-adjacent code.
- PS/2 enable is a stub (no ACK/timeout handling).

## 8. Safety boundaries

- Preserve VM 103; never create duplicate VMs; never touch unrelated VMs or services.
- Preserve rollback ISOs and test evidence; keep everything reproducible.
- Never expose or commit credentials.
- Do not commit large ISO binaries; keep checksums + reproduction steps in docs.

## 9. Required deliverables for the Phase 4 session

- Frame allocator + paging implemented with host tests passing.
- Full regression suite green (fmt, build, host tests, QEMU boot, keyboard, ELF validation).
- Sanitized evidence under `test_results/`.
- A commit with a clear message; update `HANDOVER.md` with Phase 4 status.
- Only deploy to VM 103 if every gate passes.
