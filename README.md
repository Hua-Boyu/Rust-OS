# Rust operating system on i686

## todo:  
- [x] gdt loading  
- [x] interrupts  
- [x] keyboard input (verified live: scancode received via IDT from ISO boot path)  
- [x] deterministic QEMU boot test (scripts/boot_test.py, 10/10 verified)  
- [x] Proxmox-ready ISO (dist/rosti.iso, GRUB multiboot, boot-verified in QEMU) — see PROXMOX.md  
- [ ] USE TYPES PROPERLY AND MAKE THINGS ACTUALLY WORK!!! <<<<  
- [x] regression/deployment harness (93 host tests; 21 acceptance gates)
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
