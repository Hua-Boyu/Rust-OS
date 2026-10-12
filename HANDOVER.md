# Rosti OS — Phase 6 verified handover

## Checkpoint

Canonical repository: `C:\Users\iamsv\Documents\Rust-OS`, branch `main`.
Phase 6 completion commit subject: `feat(fs): implement Phase 6 RAM filesystem and VFS`. Resolve the actual
hash with `git log -1 --format='%h %s' --grep='feat(fs): implement Phase 6'`;
the document cannot embed its own containing commit hash. Starting HEAD was
`f93d7e4`; Phase 5 is `4ed27fb`. Historic tag `v0.1.0` was not moved.
No automatic push is authorized or performed for this milestone.

Windows 11/Git Bash, Rust nightly, bare-metal i686 no_std/core+alloc, QEMU,
WSL GRUB/SeaBIOS. Native program paths use `C:/...`, not MSYS `/c/...`.
Host cargo tests run outside the kernel cargo-config tree (`scripts/run_tests.sh`).

## Verified capabilities

Existing Multiboot boot, VGA/COM1, GDT/IDT/PIC, PS/2 queue, PIT/uptime, CPUID,
idle hlt and hardware shell are preserved. Phase 4/5 paging, null guard,
runtime mappings, CR0.WP, reclaiming/coalescing KernelHeap and diagnostic mem
remain active. Physical frame tracking is still capped below 256 MiB.

Phase 6 adds a per-instance `RamFs` implementing `Vfs`, directory hierarchy,
generation-safe IDs, semantic path traversal, offset reads/writes, atomic
replacement, zero-filling truncate, callback listing, metadata, deletion and
empty-directory removal. No filesystem work or allocation occurs in an ISR.
One static (.data) instance is exclusively owned by kernel_main, with cwd
passed to the shell. No global FS lock or heap/frame lock inversion.

New commands: `pwd ls cd mkdir touch cat write append rm rmdir stat`, plus
explicit `fsstress`. All existing commands remain. Errors distinguish missing
files, duplicates, types, invalid paths, nonempty directories, quota and OOM.
Shell first-write failures roll back new files; failed replacement retains old
data. Overlong lines and kernel-ring input loss cannot execute partial commands.

## Storage and path rules

- 64 nodes including root; 63 UTF-8 bytes per name; 256 bytes for raw/canonical
  paths; absolute/relative paths, repeated separators, dot and root-clamped
  parent traversal. `file/..` and trailing separators on files fail.
- Files: max 512 KiB logical length. Retained buffers: max 4 MiB total Vec
  capacity. Fixed i686 metadata: 5,888 bytes, separate from heap file storage.
  Staged growth may temporarily add 512 KiB, plus allocator overhead.
- Shrinking nonzero files retains capacity for reuse; zero truncation and
  deletion free it. Offset writes/extension zero-fill gaps.
- Shell paths are single tokens without quotes/spaces. Input is at most 128
  bytes. Write/append strip separator whitespace, preserve trailing data, and
  do not append a newline; cat adds a display newline and escapes unsafe bytes.
- All files disappear on reboot. No timestamps, permissions, links, rename,
  mounted disk filesystem, user processes, syscalls or Linux/POSIX support.

## Acceptance

Kernel/host fmt and production build PASS; 78/78 Rust host tests; 4/4 Python
reader tests; ELF 8/8; boot 10/10 each at 128/512 MiB; paging 20/20; CPU-fault
fixtures 4/4; keyboard all stages; VGA editing 13/13 ELF and 13/13 ISO.
Filesystem integration 98/98 each on ELF and ISO at both RAM configurations.
GRUB boot and ISO paging 2/2 PASS. Local pipeline 21/21. Live hardware/VGA
20/20, live filesystem/shell/stress 100/100 across 37 commands.

Acceptance: `test_results/phase6/acceptance_20261012T152259Z_onc_58z8/acceptance.json`. Deployment/live readbacks:
`test_results/phase6/deployment.json`, `test_results/phase6/live_vm103/`.
A Proxmox QMP JSON-wrapper reader mismatch was fixed after kernel acceptance;
only the Python transport reader changed. Four reader tests, another 98-check
ISO/512 workflow and the full live suite passed afterward.

## Heap growth: now live-verified

Under QEMU and VM 103, fsstress verified 4,194,304 file bytes, quota rejection,
and real KernelHeap failure with old bytes/metadata preserved on replace,
write and extending truncate. It inspected all 1,536 new growth-window PTEs
for present/writable/supervisor/identity mapping. Capacity grew from 1 MiB to
7 MiB; four intentional allocation failures; used returned to 8,232 bytes,
payload 0 and root-only state. Pages remain mapped for reuse, not returned to
physical allocation. Use fsstress from a fresh boot; it asserts new growth.

## VM 103 and rollback

Node pve, 192.168.50.205, rosti-dev, 1 vCPU/512 MiB, SeaBIOS/i440fx, serial
socket. Running ISO `rosti_phase6_20261012T152259Z.iso`. SHA256:
`8b3a4d4dbb0f245a2b969e3aed7d973cdf46a2b6e5da07f0a189da23c44472cb`

Remote and local hashes matched before attachment and after verification.
CR0=80010011 (PG/WP), CR3=00001000; null PTE absent. VM left at a clean prompt.
Passwordless SSH proxmox alias verified root/pve; no keys or passwords copied.
MCP power operations and readbacks used; only ide2 was changed through SSH.

Rollback: `local:iso/rosti_20261012T125244Z.iso`, SHA256
`5b8875f9e8b848a346ef22a93eec689688a5cf55ec0c4e765209a8f83ec9015f`.
Local original preserved at `dist/rosti_preserved_5b8875f9e8b848a3.iso`; the older
`dist/rosti_rollback.iso` and prior versions are untouched.

## Reproduction and safe boundaries

```bash
cargo fmt --check
cargo +nightly fmt --manifest-path tests_kernel/Cargo.toml --check
bash scripts/run_tests.sh
python -B scripts/phase6_verify.py
python -B scripts/test_fs_harness.py
```
Read the acceptance runner before deployment. Do not change source while it
is running or run another QEMU beside boot_test.py's orphan check. Always
rebuild production after deliberate fault features; never deploy those builds.
For live tests, copy scripts to a unique pve temporary directory, check exact
QMP media, capture serial before reset, verify metadata/data and paging, then
retrieve evidence and reread checksum/config/status. Only VM 103 is authorized.
No host reboot, packages, networking/storage changes or unrelated VMs.

Historical Phase 4/5 evidence was removed by the sync commit f93d7e4; inspect
with `git show 4ed27fb:<path>` rather than restoring it without permission.
The existing external `.gitignore` change is preserved and not part of Phase 6.
Task evidence was staged explicitly despite the test_results ignore rule.

## Remaining limits and next milestone

RAM-only files; single main-loop execution; no scheduler/user mode/networking.
Long output/stress can delay shell processing. Kernel-ring loss is detected,
but upstream PS/2 controller loss and command ACK/timeouts remain limitations.
VGA is byte-oriented, not Unicode glyph rendering; UTF-8 serial/data is preserved.
General exception recovery is absent; NX unsupported in current 32-bit paging.
SpinMutex is not interrupt-safe; ISRs must stay allocation/lock free.

Next: Phase 7 persistent block storage, initially a bounded ATA/IDE PIO driver
and test-owned virtual disk. Do not silently claim a persistent filesystem
until a format/backend survives verified reboot. Inspect boot port-manager
guard lifetimes before adding ATA port allocation. See NEXT_SESSION_PROMPT.md.
