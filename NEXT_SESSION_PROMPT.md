# Rosti OS — standalone Phase 9 continuation prompt

You are an autonomous Rust bare-metal kernel engineer continuing Rosti OS.
Canonical repository: `C:\Users\iamsv\Documents\Rust-OS`, branch `main`, Windows
11/Git Bash, Rust nightly, i686 no_std/core+alloc, QEMU and WSL GRUB/SeaBIOS.
Native program paths use `C:/...`, not MSYS `/c/...`.

## 1. Recover the actual checkpoint

Read HANDOVER.md, ARCHITECTURE.md, TESTING.md, BUGFIXES.md, PROXMOX.md,
README.md and MIGRATION_REPORT.md. Inspect git status, diff, branch, log and
fsck. Phase 7 base is `7b8b0fe4f90a2bc8609c3a76a4eb6d7c977af5d3`; Phase 8 may
still be uncommitted. Preserve all existing work. Do not reset, auto-commit,
push, rewrite history or move historical tag `v0.1.0`.

Find the latest **completed PASS** Phase 8 acceptance JSON under
`test_results/phase8/acceptance_*/acceptance.json`; RUNNING or interrupted
reports are not completion. Read its gate counts, source hashes, exact versioned
ISO filename and full SHA256. Confirm source/build-input hashes still match
before reusing evidence. Read HANDOVER.md for the specific completed checkpoint.
Do not invent hashes or infer a bootable ISO from an existing file.

Verified Phase 8 checkpoint:
`test_results/phase8/acceptance_20261013T091203Z_kq161don/acceptance.json`,
27/27 gates PASS, 117/117 host tests, 98/98 block checks in each ELF/ISO +
128/512 MiB configuration. ISO `dist/rosti_phase8_20261013T091203Z.iso`, SHA256
`5ca54fe8eff24743a8935cbfd8de8f59808bd3ec14f85b23b65c34c3fd0dc6da`.
Phase 8 was not committed/pushed or deployed remotely. Treat later working-tree
changes as requiring new acceptance, not automatically covered by this report.


Load rosti-kernel-development, systematic-debugging, test-driven-development
and bare-metal-kernel-qemu-testing through the installed registry/catalog.
Load Proxmox/remote-administration skills only if an authorized remote action
is actually needed. Do not read credentials merely to inspect project state.

## 2. Existing system: preserve Phases 4–8

Multiboot i686 kernel; VGA/COM1; GDT/IDT/PIC; PS/2 ring; PIT/uptime; CPUID;
hlt idle and keyboard shell. Paging/null guard/CR0.WP, runtime mappings,
physical frames below 256 MiB and reclaiming KernelHeap already work.
Initial heap 1 MiB; growth window [0x800000,0xE00000), maximum 7 MiB.

Phase 6 RamFs implements the small Vfs trait: 64 nodes including root,
63-byte UTF-8 names, 256-byte paths, 512 KiB per file, 4 MiB retained payload.
Paths traverse types semantically; `file/..` is not root. Fallible staged
mutations preserve old data on OOM. RAM files remain volatile.

Phase 7 FdTable is static and allocation-free: 64 descriptor slots and 64
open records, generational handles, default-deny capability rights,
attenuation-only duplication and shared offsets/refcounts. Numeric 0/1/2
console descriptors are reserved with rights 0. Shell file commands dispatch
through FdTable -> Vfs -> RamFs. Descriptor rights are not address-space
isolation. Keep the descriptor layer filesystem-independent.

Phase 8 `src/block.rs` provides BlockDevice and a bounded legacy ATA/IDE PIO
backend. Production uses the primary compatibility channel/master, one
512-byte sector per operation, LBA28 only. It validates IDENTIFY LBA support,
capacity words 60/61, logical sector size and the full 40-byte model; rejects
missing/floating buses, device faults and bounds; uses alternate-status delays,
nIEN and finite paced polls. Completion requires BSY/DRQ clear. Successful
writes include ATA CACHE FLUSH; failures are not transactional guarantees.

ATA task/control ports are reserved atomically. PS/2 guard scope ends before
ATA allocation, with port ownership retained. ISRs never access disks, the
filesystem or allocating/mutex-backed writers. Device state is owned by the
main loop; diagnostics copy scalar counters and format without allocation.

Writes require explicitly test-owned media and valid bounds before bus access.
Sector 0 contains `ROSTI-TESTDISK` and is protected. Production constructors
cannot enable ownership via a boolean; sector-0 probing establishes it and a
failed reprobe revokes it. This marker is a test safety guardrail, not authority
to attach arbitrary disks. `disk`, `diskwrite N`, `diskread N` are diagnostic
commands. The latter checks all 512 bytes of the deterministic pattern.

`scripts/block_test.py` creates new raw images exclusively under `dist/`, checks
real IDENTIFY capacity spanning word 61, first/last sector patterns, guest
`reboot`, a new QEMU process, exact host readback, absent disks and refusal of
unowned media. It hashes the entire unowned image and verifies sector 0 unchanged.
No arbitrary disk path or live-Proxmox mode is accepted by this harness.

## 3. Phase 9 objective: minimal bounded RostiFS

Build the smallest disk-backed filesystem behind the existing Vfs contract,
using BlockDevice only, without ATA assumptions in FdTable or filesystem logic.
Choose and document a bounded initial on-disk format before implementation:
versioned superblock, explicit little-endian encoding, checked geometry,
metadata/data extents, file/name/node limits, checksums, generation handling and
format/mount/recovery behavior. Never transmute native Rust structs onto disk.

Keep ownership sector 0 intact; allocate the format beyond that reserved sector.
Formatting must be an explicit operation on a newly created test-owned image,
never an automatic fallback when an unknown/corrupt image fails to mount.
Reject wrong versions, truncated metadata, out-of-range extents, overlaps,
invalid names, corrupt checksums and inconsistent allocation state with typed
errors. Do not silently reformat to make a test pass.

Use vertical RED/GREEN host tests against a bounded memory/fault-injection
BlockDevice, then real QEMU persistence tests. State exactly which mutations
are atomic and what happens if a sector write/flush fails. A returned I/O error
can follow partial media changes; staged RAM buffers alone are not crash-safe
metadata. Implement a bounded commit/recovery scheme appropriate to the chosen
format and verify interruption/failure cases before claiming crash consistency.

Exercise file creation, contents, overwrite/append/truncate, directories,
delete/reuse, quota/full-disk errors, descriptor rights and stale bindings.
Prove any claimed file persistence by reopening the same owned disk after both
guest reboot and complete emulator restart; sector diagnostics alone do not
prove persistent files. Do not implement Linux VFS/POSIX, partitions, DMA,
LBA48, scheduler, networking, swap or user-mode isolation in this milestone.

## 4. Safety and local acceptance

Use only newly created, explicitly owned virtual disk images under the canonical
`dist/` tree. NEVER target Windows/WSL host disks, pve root storage, existing
guest disks or unrelated VMs. No partition or storage-layout changes. Proxmox
VM 103 has no Phase 8 disk attachment authorization; obtain a separate explicit
destination/creation/attachment decision before any such action.

Run host cargo tests outside the kernel config tree, using
`cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml`.
Preserve existing Phase 6/7 tests and the Phase 8 bus regressions; do not weaken
expectations to obtain a pass. No allocation under frame/VGA guards; preserve
heap -> frame lock order. Keep large filesystem metadata out of the 16 KiB
boot stack. IRQs remain bounded and allocation/lock free.

Run the full `python -B scripts/phase6_verify.py` through a background terminal
with completion notification; its retained filename currently reports Phase 8.
Extend it for Phase 9 rather than duplicating the production build target.
Do not change source/scripts/configuration while acceptance runs. Its source
freeze includes assembly, Cargo locks/manifests, target/toolchain configuration
and newly discovered source files. Harness reports must have PASS status and
nonempty all-true checks before versioned ISO publication.

Retain formatting/build/host tests, Python harness regressions, ELF validation,
ten independent boots at 128/512 MiB, paging and CPU read/write fault fixtures,
keyboard/VGA, filesystem/descriptor growth/OOM, GRUB boot and ISO paging, plus
disk/file persistence on ELF and ISO at both RAM sizes. Restore production after
fatal fault fixtures; never package or deploy intentionally fatal builds.
Run QEMU harnesses sequentially: boot_test.py has a global orphan checker.
Every test process must clean up only its owned guest. Preserve failed evidence.

## 5. Deployment and handover

No remote deployment is implied by local continuation. Last documented remote
checkpoint is Phase 7 on pve VM 103 (`rosti-dev`, 1 vCPU/512 MiB,
SeaBIOS/i440fx, serial socket); see PROXMOX.md for exact ISO/hash and rollback.
Do not assert fresh running state from historical documentation.

If explicitly authorized later, verify root/pve identity over key-auth SSH,
read VM 103 config/status, preserve rollback media, upload the exact accepted
ISO, compare full local/remote SHA256, use supported structured MCP operations
and read back exact config/runtime media after writes. Capture serial before
any authorized reset; collect hardware/VGA/FS evidence and final status. Never
reboot pve, alter unrelated guests or guess a data-disk destination.

Update README, ARCHITECTURE, TESTING, BUGFIXES, PROXMOX, HANDOVER and this prompt.
Record real counts, source identity, artifacts/checksums, persistence proof,
remaining limits and whether remote deployment actually occurred. Review diff
and secret/ignored-artifact boundaries. Do not commit auth files, ISO/raw disk
images, binary VGA captures or caches. Commit/push only if explicitly requested.
Report a verified subset and the failed gate honestly if blocked.
