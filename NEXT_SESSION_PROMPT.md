# Rosti OS — standalone Phase 8 continuation prompt

You are an autonomous Rust bare-metal kernel engineer continuing Rosti OS.
Canonical repo: `C:\Users\iamsv\Documents\Rust-OS`, branch main, Windows 11
Git Bash, Rust nightly, i686 no_std/core+alloc, QEMU and WSL GRUB/SeaBIOS.

## 1. Recover the verified checkpoint

Read HANDOVER.md, NEXT_SESSION_PROMPT.md, ARCHITECTURE.md, TESTING.md, BUGFIXES.md,
PROXMOX.md and MIGRATION_REPORT.md if present. Verify git status, branch, log -5
and fsck --full. Locate Phase 7 by commit subject `feat(vfs): add capability-aware file descriptors and generational handles` and Phase 6 by `feat(fs): implement Phase 6 RAM filesystem and VFS`; verify current HEAD rather than assuming a hash. Phase 5 was 4ed27fb. Do not reset the historical v0.1.0 tag. Preserve unrelated changes, including external .gitignore edits, deleted archives and generated evidence. Do not automatically push.

Verify installed skills and load rosti-kernel-development, systematic-debugging,
test-driven-development, bare-metal-kernel-qemu-testing, proxmox-ve-mcp and
remote-linux-administration. Discover them through the local skills catalog
or installed registry, not an assumed tool list.

## 2. Current system: do not reimplement Phases 4–7

Multiboot i686 kernel, VGA/COM1, GDT/IDT/PIC, PS/2 ring, PIT/uptime, CPUID,
hlt idle and kernel shell. Paging/null guard/CR0.WP, runtime mappings, physical
frames below 256 MiB and reclaiming KernelHeap are implemented. Initial heap
1 MiB; growth window [0x800000,0xE00000), maximum capacity 7 MiB.

Phase 6: src/fs/mod.rs RamFs implements src/fs/vfs.rs Vfs. Hierarchical files/
directories, scoped generation-safe IDs, bounded paths/names, offset read/write,
atomic replace, truncate, listing, metadata and deletion. 64 nodes including
root, names 63 UTF-8 bytes, paths 256 bytes, files 512 KiB, retained payload
4 MiB. Metadata 5,888 i686 bytes; staged growth can add 512 KiB.

Phase 7: src/fd.rs FdTable — static, allocation-free descriptor subsystem owned
by kernel_main and passed to shell::poll. Numeric descriptors 0/1/2 reserved
for console (rights 0, default-deny until wired). Generational handles (slot +
generation, retired on exhaustion, never wrapped). Open-file descriptions hold
the shared offset and refcount; duplication attenuates rights only. 8-bit
capability mask (READ/WRITE/SEEK/STAT/DIRECTORY_READ/CREATE/DELETE/MAP-reserved),
validated on every operation. ResourceKind File/Directory/ConsoleInput/
ConsoleOutput; Pipe/Socket/Device reserved. 64 slots + 64 records, asserted
≤2,560 bytes overhead, TableFull on exhaustion, no allocation on any fd path,
lock order descriptor table → VFS. Generation-checked node binding: deleting an
open file fails cleanly. `fdlist` diagnostics; `mem` prints FdStats counters as
dispatch proof. Shell file commands go Shell → Descriptor API → VFS → RAMFS.
Denied writes do not advance the shared offset. Rights are capabilities, not
isolation (single privileged address space).

Shell: help clear version mem cpu uptime echo reboot plus pwd ls cd mkdir touch
cat write append rm rmdir stat fdlist and explicit fresh-boot fsstress. No persistence,
user programs, POSIX permissions, links, rename or mounted disk backend.
Overlong lines and kernel-ring loss reject partial input; upstream controller
loss remains a limitation. VGA has no Unicode glyph support; UTF-8 bytes/serial
are preserved. Shell input remains 128 bytes with unquoted path tokens.

## 3. Last verified release

ISO `rosti_phase7_20261012T181123Z.iso`
SHA256 `4c1e337d1362d827248ad0e3ee13f8c67bb29cdff3a1a460d1cd1d5e97b62bb4`

Local pipeline 21/21; Rust host 93/93; Python media-reader regressions 4/4; ELF
8/8; boot 10/10 each at 128/512 MiB; paging 20/20; CPU fault fixtures 4/4;
keyboard PASS; VGA editing 13/13 on ELF and ISO; filesystem + descriptor
integration 102/102 on each ELF/ISO and RAM-size combination (38 commands).
GRUB boot and ISO paging 2/2 PASS. VM 103 live 104/104 across 38 commands,
including descriptor dispatch proof (opens 12, closes 12, denials 0, stale 0,
records 0, open slots 3 reserved console) and fdlist. Live stress re-verified:
4 MiB data, 1,536 growth PTEs, capacity 1 -> 7 MiB, used 8,232 bytes after
cleanup. Expanded pages remain mapped. Evidence:
`test_results/phase7/acceptance_20261012T181123Z_ovwvkk1g/acceptance.json` and
`test_results/phase7/live_vm103/`. Rollback ISO remains
`rosti_phase6_20261012T152259Z.iso` SHA256
`8b3a4d4dbb0f245a2b969e3aed7d973cdf46a2b6e5da07f0a189da23c44472cb`.
Revalidate relevant baselines first.

## 4. Phase 8 objective and implementation boundaries

Implement the smallest testable persistent block-storage foundation, initially
ATA/IDE PIO for the SeaBIOS/i440fx platform. Inspect actual PCI/IDE topology and
port ownership; do not invent devices, symbols, imports or target disks. Scope
boot port-manager guards so new allocation cannot relock an existing guard.

Build a small block-device abstraction with sector size/capacity, bounded
sector read/write, checked LBA/count arithmetic and explicit errors. Use a
host-memory/test backend to drive RED/GREEN tests before privileged code.
ATA IDENTIFY and PIO polling must have finite timeouts and distinguish missing
devices, busy/error/DRQ states and unsupported addressing. Start with a stated
LBA/sector limit; do not claim LBA48, DMA or interrupt-driven I/O unless built
and tested. Never allocate or use FS/VGA locks from an ISR. Preserve heap ->
frame lock order and avoid filesystem activity under allocator guards. The
Phase 7 descriptor layer must stay filesystem-independent: any disk backend
plugs in behind the existing Vfs trait without fd-layer changes.

Use only newly created, explicitly test-owned virtual disk images under the
canonical repo dist/ tree for writes. NEVER target Windows/WSL host disks, the
Proxmox host root disk, existing guest data disks or unrelated VMs. No partition
or storage-layout changes. Add a data disk to VM 103 only after inventory and
explicit disk-creation/attachment authorization; current authorization does not
permit guessing its disk destination or overwriting existing data.

Do not build a complete Linux VFS/filesystem. Extend the existing Vfs with a
minimal disk-backed format/backend only if the persistence scope is clearly
chosen and its bounded allocation/format/recovery rules are documented. Never
call RAM files persistent because an ATA sector test passes. Keep swap, page
reclamation and filesystem persistence as separate responsibilities; design for
the future RostiFS (bounded memory, extents, transactional metadata, checksums)
without implementing it now.

## 5. Verification and deployment gates

Run formatting, build, all host tests, ELF, ten boots at both RAM sizes, paging
and CPU faults, keyboard/VGA, all Phase 6/7 filesystem/descriptor/growth/OOM tests and GRUB
ISO boot. Add isolated disk tests for identify/capacity, bounds, failed polling,
sector read/write integrity and data readback after guest reset/reboot. Prove
any claimed file persistence across reboot on the test disk. Keep fault/crash
fixtures out of production ISOs. Existing runner: python -B scripts/phase6_verify.py
(retained filename; reports phase 7). Host cargo tests run outside the kernel
.cargo config tree. Keep evidence under test_results/ and avoid concurrent QEMU
beside the global orphan checker.

Only deploy after local gates pass. Proxmox: node pve, 192.168.50.205, VM 103
rosti-dev, 1 vCPU/512 MiB, SeaBIOS/i440fx, serial socket. Verify passwordless
proxmox SSH alias and authenticated root/pve identity; never read/copy keys or
print credentials. Prefer structured MCP for supported operations. Key-auth
scp/SSH is available; deploy-proxmox.py's password path remains unchanged.
QMP may wrap media paths in JSON throttle/raw/file descriptors: check the exact
ide2 file leaf, not a substring, and pass the full runtime path as
--expected-iso. Capture serial before reset. Preserve rollback ISOs
(rosti_phase6_20261012T152259Z.iso and earlier). Verify full remote/local SHA256,
config, running media, live commands and final status. Never reboot/reconfigure
pve or touch unrelated guests/services.

## 6. Finish and hand over

Update README, ARCHITECTURE, TESTING, BUGFIXES, PROXMOX, HANDOVER and this prompt.
Report exact PASS/FAIL counts, ISO name/full SHA256, VM 103 results, persistence
proof and remaining bounds/risks. Review staged task-owned changes and scan for
secrets. Commit only after stated gates pass; do not push or rewrite tags.
Print a complete standalone Phase 9 continuation prompt. If blocked, report the
failed gate and verified subset honestly instead of inventing results.
