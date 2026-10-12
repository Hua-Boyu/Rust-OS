# Rosti OS — Next Session Prompt (Phase 4 verified; Phase 5 not started)

You are continuing development of Rosti OS. This prompt is standalone — no prior chat history is assumed.

## 1. Project identity

- Repo: `C:\Users\iamsv\Documents\Rust-OS` (canonical project root; Windows 11 host, git-bash shell).
- Phase 4 is implemented and verified within its documented limits: protected physical frames, bounded bootstrap heap, identity paging, null-page guard, real CPU-fault tests, and active paging on VM 103. Do not repeat the old host-compilation or boot-deadlock investigation. Inspect `git status` before editing; preserve unrelated logs and the user's archive deletion.
- Rosti is a bare-metal i686 Rust kernel (nightly, custom JSON target, `no_std`, only core/alloc), booted via GRUB Multiboot v1 under SeaBIOS, with VGA + COM1 serial consoles, PS/2 keyboard, PIT timer, and a minimal shell.
- Read `HANDOVER.md` first — it is the authoritative handover (architecture, boot sequence, test commands, Proxmox state, limitations, safety boundaries).

## 2. Checkpoint lookup

- Branch: `main`
- Phase 4 commit message: `feat(memory): complete Phase 4 paging and gated VM verification`. Resolve the actual hash with `git log -1 --oneline`; this document does not embed its own commit hash.
- Tag: `v0.1.0` remains the historical annotated local baseline, not the current release.

## 3. Verified functionality (do not re-litigate; re-run tests to confirm regressions)

- Build + `cargo fmt --check`: PASS.
- Host tests: 49/49 PASS (`bash scripts/run_tests.sh`; the wrapper runs cargo outside the project dir). Pipeline uses the equivalent native cargo invocation from the user home to avoid Windows resolving `bash` to WSL.
- QEMU boot harness: 10/10 PASS (`python scripts/boot_test.py --runs 10`); PASS = markers `ROSTI: entered kernel_main` then `ROSTI: boot complete`.
- Keyboard integration: PASS (`python scripts/keyboard_test.py`); live scancode 97 received via IDT.
- ELF/multiboot validation: 8/8 PASS (`python scripts/validate_elf.py target/target/debug/kernel`).
- GRUB ISO boot and paging: PASS; current `dist/rosti.iso` SHA256 `6a679af55b5b76988b1b6a4f464517d6aba22a3f09d4633e802c7776f49adc94` matches the deployed release. Rebuild only for code changes and distinguish artifacts by checksum.
- Paging boot stability: 10/10 each at 128 and 512 MiB; CPU unmapped-read/null-write fault tests pass at both RAM sizes. Production builds contain no deliberate fault trigger.
- Proxmox: 25/25 deployment gates; 20/20 live VGA/serial/paging checks. CR0.PG set, CR3 loaded, null PTE absent, `mem` reports paging enabled. VM is running at a clean prompt.
- Acceptance summary: `test_results/phase4/acceptance.json`; live details: `test_results/proxmox/phase4_live_report.json`.

## 4. Exact test commands

```bash
cargo fmt --check
cargo build
bash scripts/run_tests.sh            # from $HOME, not the project dir
python scripts/validate_elf.py target/target/debug/kernel
python scripts/boot_test.py --runs 10 --timeout 15
python scripts/keyboard_test.py
python scripts/build-proxmox-iso.py  # only when ISO-affecting changes are made
python scripts/paging_test.py --runs 10
python scripts/backspace_test.py --iso dist/rosti.iso
```

## 5. Proxmox VM 103 (preserve it)

- Node `pve`, VM 103 `rosti-dev`: i440fx, SeaBIOS, 1 core, 512 MiB, `serial0: socket`, boot IDE CD-ROM.
- Deployed ISO: `rosti_20261012T091633Z.iso` (SHA256 above); rollback ISO and earlier remote versions retained.
- Serial console: `/var/run/qemu-server/103.serial0`; input via `qm sendkey 103 <key>`.
- Credentials come ONLY from environment variables (`PVE_TOKEN_ID`, `PVE_TOKEN_SECRET`, `PVE_ROOT_PASSWORD`). Never commit `.pve_auth`, `$AUTH`, `.env`, or any ticket/token.
- Deploy only to VM 103 via `scripts/deploy-proxmox.py` (25 gates). SSH deployment needs `PVE_ROOT_PASSWORD` privately supplied to the process environment, not an API token. Password uses binary stdin; no secrets in argv or files.

## 6. Phase 4 completion and next objective

Completed and verified:
1. Multiboot layout/parser and allocator arithmetic audited; bootstrap heap bounded to 1 MiB in kernel BSS.
2. Bitmap physical-frame allocator; complete usable pages, reserved/ACPI overlap precedence and boot metadata/module reservations.
3. Release/bounds/reservation/double-free/exhaustion tests; failed page-table allocation returns its frames.
4. Zeroed i686 4 KiB identity tables, full RAM mapping independent of the physical allocation cap, null page absent, CR3/CR0.PG enable after IDT and mapping validation.
5. CPU-delivered fatal read and write page faults verified; serial diagnostics only, no ISR locks or allocation.
6. Full regression, sanitized evidence, gated VM 103 deployment and live paging/Backspace checks.

Next proposed milestone is Phase 5 (RAM filesystem/basic VFS), but it has NOT been implemented. Confirm the next task with the user; do not implement filesystem, scheduling or networking merely because this handover mentions them.

Local fatal-fault fixtures: build with `--features paging-fault-test`, run `python scripts/paging_test.py --fault`; build with `--features paging-write-fault-test`, run `--write-fault`. Always rebuild without features afterward. The ISO builder rejects these test binaries.

Do NOT implement multitasking, filesystem, or networking in this phase. Avoid architecture rewrites; extend the existing modules.

## 7. Known limitations to respect

- No filesystem, no scheduler, no user mode, no syscall interface, no ELF loader, no networking, no USB.
- Vector 14 fatal diagnostics are CPU-tested; other error-code exception handlers still need hardening. Faults halt, not recover.
- Physical frame allocation below 256 MiB; identity paging covers the VM's full RAM. Bootstrap heap is 1 MiB; no demand paging, user address spaces, swapping or reclaiming general-purpose heap. Boot string/config buffers conservatively reserve 4 KiB.
- SpinMutex is not interrupt-safe; harden or avoid it in new interrupt-adjacent code.
- PS/2 enable is a stub (no ACK/timeout handling).

## 8. Safety boundaries

- Preserve VM 103; never create duplicate VMs; never touch unrelated VMs or services.
- Preserve rollback ISOs and test evidence; keep everything reproducible.
- Never expose or commit credentials.
- Do not commit large ISO binaries; keep checksums + reproduction steps in docs.

## 9. Phase 4 deliverables — completed within the limits above

- Frame allocator + active paging, 49 passing host tests and real CPU-fault tests.
- Full regression suite green (fmt, build, host tests, QEMU boot, keyboard, ELF, paging and ISO/VGA checks).
- Sanitized acceptance and live evidence under `test_results/`.
- Phase 4 completion commit and updated `HANDOVER.md`.
- VM 103 deployment completed after all local gates passed; final checksum/config/status read back.
