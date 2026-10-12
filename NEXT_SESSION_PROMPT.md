# Rosti OS — Next Session Prompt (Phase 5 verified; Phase 6 not started)

You are continuing development of Rosti OS. This prompt is standalone — no prior chat history is assumed.

## 1. Project identity

- Repo: `C:\Users\iamsv\Documents\Rust-OS` (canonical project root; Windows 11 host, git-bash shell).
- Phase 5 is implemented and verified: runtime page mapping (map/unmap/translate/permissions, conflict and alignment rejection, per-page TLB invalidation), the virtual growth window [0x800000, 0xE00000) mapped on demand, the dynamic reclaiming `KernelHeap` global allocator (coalescing free list, alignment-waste tracking, OOM-safe), extended page-fault diagnostics including the instruction-fetch bit, and shell `mem` diagnostics. Do not re-litigate the Phase 4/5 investigations; re-run tests to confirm regressions. Inspect `git status` before editing; preserve unrelated logs.
- Rosti is a bare-metal i686 Rust kernel (nightly, custom JSON target, `no_std`, only core/alloc), booted via GRUB Multiboot v1 under SeaBIOS, with VGA + COM1 serial consoles, PS/2 keyboard, PIT timer, and a minimal shell.
- Read `HANDOVER.md` first — it is the authoritative handover (architecture, boot sequence, test commands, Proxmox state, limitations, safety boundaries).

## 2. Checkpoint lookup

- Branch: `main`
- Phase 5 commit message: `feat(memory): implement Phase 5 virtual memory and dynamic kernel heap`. Resolve the actual hash with `git log -1 --oneline`; this document does not embed its own commit hash. Phase 4 baseline: `46af27e`.
- Tag: `v0.1.0` remains the historical annotated local baseline, not the current release.

## 3. Verified functionality (do not re-litigate; re-run tests to confirm regressions)

- Build + `cargo fmt --check`: PASS (warnings only).
- Host tests: 59/59 PASS (`bash scripts/run_tests.sh`; run from `$HOME`, not the project dir).
- QEMU boot harness: 10/10 PASS (`python scripts/boot_test.py --runs 10`); PASS = markers `ROSTI: entered kernel_main` then `ROSTI: boot complete`.
- Paging stability: 10 runs each at 128 and 512 MiB; CPU unmapped-read/null-write fault fixtures pass at both sizes with the extended `fetch=` diagnostics. Production builds contain no deliberate fault trigger.
- Keyboard integration PASS; VGA editing 13 checks on ELF and 13 on ISO.
- ELF/multiboot validation: 8/8 PASS (`python scripts/validate_elf.py target/target/debug/kernel`).
- Proxmox: 25/25 deployment gates; 20/20 pipeline live checks; Phase 5 shell verification 13/13 (`scripts/live_phase5_check.py`): `help`, `version`, `uptime`, `mem` (frames, paging, page directory, heap stats, failed allocations, page-fault count) and keyboard editing. Live registers: CR0 = `80010011` (PG + WP), CR3 = `00001000`, null PTE absent. VM 103 running at a clean prompt.
- Performance baseline recorded in `test_results/phase5/perf_baseline.json` (frame alloc ~2.4–2.6 µs, map ~275–300 ns, unmap ~260–290 ns, heap alloc ~1.9–2.0 µs, heap free ~1.5–1.7 µs, checkerboard fragmentation 251 blocks). No optimization applied yet.

## 4. Exact test commands

```bash
cargo fmt --check
cargo +nightly fmt --manifest-path tests_kernel/Cargo.toml --check
bash scripts/run_tests.sh            # from $HOME, not the project dir
cargo build --target target.json
python scripts/validate_elf.py target/target/debug/kernel
python scripts/boot_test.py --runs 10 --timeout 3
python scripts/paging_test.py --runs 10
python scripts/paging_test.py --fault          # with --features paging-fault-test build
python scripts/paging_test.py --write-fault    # with --features paging-write-fault-test build
python scripts/keyboard_test.py
python scripts/backspace_test.py
python scripts/build-proxmox-iso.py
python scripts/paging_test.py --iso dist/rosti.iso
python scripts/backspace_test.py --iso dist/rosti.iso
python scripts/live_phase5_check.py   # run on the Proxmox host via SSH
```

## 5. Proxmox VM 103 (preserve it)

- Node `pve`, VM 103 `rosti-dev`: i440fx, SeaBIOS, 1 core, 512 MiB, `serial0: socket`, boot IDE CD-ROM.
- Deployed ISO: `rosti_20261012T125244Z.iso` (SHA256 `5b8875f9e8b848a346ef22a93eec689688a5cf55ec0c4e765209a8f83ec9015f`); rollback ISO and earlier remote versions retained.
- Serial console: `/var/run/qemu-server/103.serial0`; input via `qm sendkey 103 <key>` (space is `spc` on this monitor build).
- Passwordless root SSH key auth is installed on `pve` from both native Windows (`~/.ssh/asus_client`) and WSL (`~/.ssh/id_ed25519`); `proxmox <cmd>` runs as root on pve (see the remote-linux-administration skill). `deploy-proxmox.py` still reads `PVE_ROOT_PASSWORD` from the environment for its gates; never commit credentials.
- Deploy only to VM 103 via `scripts/deploy-proxmox.py` (25 gates).

## 6. Phase 5 completion and next objective

Completed and verified in Phase 5:
1. Runtime `PageMap` operations: map, unmap, translate, permissions, conflict/alignment/range rejection, TLB invalidation counters.
2. Growth-window on-demand mapping with growth-frame claims; page tables can never live in the growth window.
3. `KernelHeap` dynamic global allocator: alloc/free, reuse, alignment, growth, OOM-safe stats; `BumpAlloc` retained for early boot.
4. Extended page-fault diagnostics (error-code bits including fetch, CR2, RIP) and shell `mem` reporting.
5. Full regression suite green, performance baseline recorded, gated VM 103 deployment, live shell verification.

Next proposed milestone is Phase 6 (RAM filesystem + basic VFS), but it has NOT been implemented. Confirm the next task with the user; do not implement filesystem, scheduling or networking merely because this handover mentions them. If the user instead requests the deferred optimization pass, use `test_results/phase5/perf_baseline.json` as the before-measurement and keep correctness tests green as the acceptance gate.

Do NOT implement multitasking, user mode, or networking in this phase. Avoid architecture rewrites; extend the existing modules.

## 7. Known limitations to respect

- No filesystem, no scheduler, no user mode, no syscall interface, no ELF loader, no networking, no USB.
- Vector 14 fatal diagnostics are CPU-tested; other error-code exception handlers still need hardening. Faults halt, not recover.
- Physical frame allocation below 256 MiB; identity paging covers the VM's full RAM. Heap growth verified in host tests only (live VM workload stayed under 1 MiB). NX is not supported in 32-bit single-directory paging and must not be claimed.
- SpinMutex is not interrupt-safe; harden or avoid it in new interrupt-adjacent code. Lock order: heap → frame allocator; never allocate while holding the frame lock.
- PS/2 enable is a stub (no ACK/timeout handling).
- Heap unsafe code invariants (header layout, block ownership, coalescing bounds) are documented in `src/allocator.rs` and regression-tested; keep them tested when extending.

## 8. Safety boundaries

- Preserve VM 103; never create duplicate VMs; never touch unrelated VMs or services.
- Preserve rollback ISOs and test evidence; keep everything reproducible.
- Never expose or commit credentials.
- Do not commit large ISO binaries; keep checksums + reproduction steps in docs.

## 9. Phase 5 deliverables — completed within the limits above

- Runtime virtual-memory subsystem + dynamic reclaiming heap, 59 passing host tests including fault-diagnostic and fragmentation regressions.
- Full regression suite green (fmt, build, host tests, QEMU boot, keyboard, ELF, paging, ISO/VGA checks).
- Sanitized acceptance and live evidence under `test_results/phase5/` and `test_results/proxmox/`.
- Phase 5 completion commit and updated `HANDOVER.md`.
- VM 103 deployment completed after all local gates passed; final checksum/config/status read back; live shell checks 13/13.
