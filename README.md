# Rust operating system on i686

## Phase 9.5: measured maintenance, not Phase 10

The minimalist audit uses MenuetOS and nanochess/bootOS as references, not code
to copy. Rosti retains Rust, capability-aware descriptors, GRUB/i686, RAMFS and
transactional RostiFS format 1. Bounded cat batching reduces repeated persistent
reads; descriptor exhaustion/retirement and bit clearing are corrected, and
acceptance now requires complete evidence. No scheduler, syscall, application
loader, graphical desktop or initramfs feature was added.

Read [comparison](docs/MINIMAL_OS_COMPARISON.md),
[audit](docs/PHASE9_5_AUDIT.md), [measurements](docs/PHASE9_5_PERFORMANCE.md),
[ABI proposal](docs/ROSTI_APPLICATION_ABI_DESIGN.md) and
[GUI proposal](docs/ROSTI_LIGHTWEIGHT_GUI_DESIGN.md). Designs remain unimplemented.
HANDOVER.md records actual release status/artifact identities and unresolved
pre-existing safety prerequisites; passing current QEMU tests is not proof of
user isolation, physical durability or safe module integration. The canonical
acceptance entry point remains `python -B scripts/phase6_verify.py`, now Phase 9.5.
Proxmox remains Phase 7; local maintenance does not authorize deployment.

## Phase 9: RostiFS v0.1

Rosti OS aims to extend the useful life of older computers through secure,
efficient computing and reduced electronic waste. RostiFS is a portable,
dependency-free `no_std` Rust storage engine, not a Linux filesystem port.

The existing capability descriptors and VFS now route files under `/mnt/rosti`
to an explicitly test-owned ATA image. `/` remains RAMFS; no boot-root migration
or automatic formatting occurs. Invalid volumes leave the RAMFS recovery shell
available. Existing commands (`ls`, `cd`, `pwd`, `mkdir`, `touch`, `cat`, `write`,
`append`, `rm`, `rmdir`, `stat`) work through the existing descriptor/VFS stack.
`rostifs` reports mount, capacity and bounded metadata memory. Raw `diskwrite`
is refused while a filesystem is mounted.

Format version **1** uses 4 KiB blocks, explicit little-endian encoding, two
checksummed root slots, two complete metadata banks and copy-on-write file data.
Each mutation orders **data → flush → metadata → flush → root → flush**.
Recovery validates snapshots rather than guessing repairs. CRC32C detects
accidental corruption; it is not cryptographic integrity. **Physical power-loss
safety has not been established.**

Initial limits: 64 nodes including root, 60-byte UTF-8 names, 256-byte paths,
256 KiB files in contiguous extents, volumes up to 256 MiB. Metadata and scratch
are fixed; mount/traversal/write operations allocate no heap memory. Old snapshot
retention and fragmentation can produce a full-volume error despite nominal
free capacity. Rename, timestamps, symlinks, compression and user snapshots are
not implemented.

Host tools: `mkrostifs`, `rostifsck`, `rostifs-inspect`; build the portable crate
with `--features host-tools` from outside the kernel Cargo configuration. They
accept only explicit absolute test-owned `.img` paths under this repository's
`dist/`, reject raw devices, and never overwrite an existing image on format.
See [the format and tool contract](crates/rostifs/FORMAT.md).

Local verification and exact release artifacts are recorded in `HANDOVER.md`
and `test_results/phase9/`; `scripts/phase6_verify.py` now runs Phase 9 acceptance.
Proxmox VM 103 remains on Phase 7 with no data disk attached; Phase 9 is not
live-verified or deployed. The older milestone descriptions below are archived
context and do not override this section.

## todo:  
- [x] gdt loading  
- [x] interrupts  
- [x] keyboard input (verified live: scancode received via IDT from ISO boot path)  
- [x] deterministic QEMU boot test (scripts/boot_test.py, 10/10 verified)  
- [x] Proxmox-ready ISO (dist/rosti.iso, GRUB multiboot, boot-verified in QEMU) — see PROXMOX.md  
- [ ] USE TYPES PROPERLY AND MAKE THINGS ACTUALLY WORK!!! <<<<  
- [x] regression/deployment harness (117 host tests; 27 local acceptance gates)
- [x] physical frames and identity paging (active on 512 MiB VM 103; null guard and CPU faults verified)
- [x] shell Backspace visually erases characters, including wrapped input
  (QEMU ELF/ISO and live Proxmox VM 103 display regression verified)
- [ ] rtc?  

## Project goals  
Learn more about operating systems and attempt to reimplement (nearly) 
everything without working with external libraries, minus the Rust core and 
alloc libraries.

## Phase 6: RAM filesystem and VFS

Rosti now has a heap-backed, hierarchical RAM filesystem behind a small `Vfs`
trait. **Files are volatile and disappear on reboot.** This is kernel-shell
functionality, not user-space execution or a persistent disk filesystem.

| Command | Behavior |
|---|---|
| `pwd`, `cd PATH` | Inspect/change the current directory |
| `ls [PATH]` | List a directory; directory names end in `/` |
| `mkdir PATH`, `rmdir PATH` | Create/remove an empty directory |
| `touch PATH` | Create an empty file; existing files are unchanged |
| `write PATH [TEXT]` | Create/atomically overwrite a file; omitted text empties it |
| `append PATH [TEXT]` | Append to an existing file |
| `cat PATH` | Display UTF-8/text; unsafe control and invalid bytes are escaped |
| `rm PATH`, `stat PATH` | Delete a file / show type and byte size |
| `fsstress` | Explicit fresh-boot growth/OOM diagnostic; never runs automatically |

Existing hardware/shell commands are preserved. Absolute and relative paths,
repeated `/`, `.` and root-clamped `..` work. Paths are limited to 256 UTF-8
bytes, names to 63 bytes, file contents to 512 KiB, and retained file buffers to
4 MiB across 64 nodes (including root). Shell paths are single tokens, without
quoting or spaces; the PS/2 input line limit remains 128 bytes. Overlong input
is rejected entirely. File text keeps trailing spaces, with no automatic newline
added by `write` or `append`. `cat` adds a display newline.

Local acceptance: `python -B scripts/phase6_verify.py`. See `TESTING.md`,
`PROXMOX.md` and `HANDOVER.md` for measured results, ISO identity and limitations.

## Phase 7: file descriptors and capability handles

Phase 7 adds `src/fd.rs`: a static, allocation-free descriptor subsystem that
all shell file commands now dispatch through (`Shell → Descriptor API → VFS →
RAMFS`). It provides Unix-style numeric descriptors (0/1/2 reserved for
console), generation-checked internal handles, explicit capability rights
(default-deny, attenuation-only duplication), separate open-file descriptions
with shared offsets, and reference-counted open resources. `fdlist` shows open
descriptors with type, rights, offset and refcount; `mem` reports descriptor
counters. Tables are fixed at 64 slots + 64 records (≤2,560 bytes asserted
overhead, no heap allocation on any fd path). Stale handles, double closes,
escalation, type mismatches and exhaustion are rejected with typed errors.
Rights are capabilities, not isolation: the kernel still shares one privileged
address space.

## Phase 8: bounded persistent block-storage foundation

Phase 8 adds ATA/IDE PIO behind the filesystem-independent
`BlockDevice` trait. `disk` reports the device and I/O counters; `diskwrite N`
writes a deterministic 512-byte diagnostic pattern to a test-owned sector;
`diskread N` checks every byte against that pattern. Sector 0 is reserved for
the test-media ownership marker. Only newly created virtual disks under
`dist/` are test targets; no host disks or existing VM disks are authorized.

**Sector persistence is not file persistence.** Shell files still use RamFs
through the descriptor/VFS stack and disappear on reboot. RostiFS, mounting,
partitioning, DMA, LBA48, swap and user-mode isolation remain future work.

Phase 8 acceptance is recorded separately under `test_results/phase8/`.
The retained `scripts/phase6_verify.py` filename runs the current acceptance
pipeline, including block readback across guest reboot and QEMU process restart
on ELF/GRUB boot paths at 128/512 MiB. Consult HANDOVER.md for the latest actual
results; the presence of a disk image or ISO alone does not establish a pass.
