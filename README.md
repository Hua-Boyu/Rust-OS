# Rust operating system on i686

## Latest continuation: allocator-domain runtime payload pins — PARTIAL

Mapped runtime payloads now refuse free and a second runtime PageMap reference;
unmap requires the matching allocator. Stale numeric release and structure/CPU
lifetime remain blockers. Current verification and superseding status:
`docs/PHASE11A2_MAPPING_PINS_HANDOVER.md`. No TSS/CPL3 or Phase 12.

## Latest continuation: runtime table-access guard, still PARTIAL

A new-table candidate must retain writable supervisor identity access before
physical-pointer writes; refusal rolls back the candidate. Full B19 and CPL3
remain blocked. Current patch, review, tests and exact acceptance status:
`docs/PHASE11A2_TABLE_ACCESS_HANDOVER.md` (supersedes current-status text below).

## Latest: Phase 11A.2 PARTIAL — registry/reservation checkpoints and tested exception-entry conventions

Registry/boot-alias repairs are locally checkpointed as `4bfbe60`; reserved-frame
admission + mandatory identity gate as `8f02162`; exception-entry conventions as
`b82e9b1`. Raw runtime mapping refuses
reserved/uncovered backing unless the allocator records a current allocation or
exact growth claim. Exception-entry conventions are corrected and host-tested
(#AC(17) error-code frame routing, corrected vector oracle, four green ABI tests,
mandatory acceptance gate family; 58/58 acceptance PASS). No USER permission is
enabled. Free-while-mapped, cross-map authority and stale numeric release
remain demonstrated blockers; recoverable #GP/user-fault continuation, TSS and
CPL3 are not approved or complete. Current tests, source-frozen acceptance,
artifact identity, review limits and next task: `docs/PHASE11_HANDOVER.md`;
standalone resume: `NEXT_SESSION_PROMPT.md`. No Phase12, Proxmox deployment or
remote Git write was performed.

## Historical predecessor: Phase 11A PARTIAL — no user execution

Continuation repairs retained PageMap aliases with private ownership/copied
snapshots and fixes nonzero-base GDT descriptor encoding. Host273 pass
(2 ignored), harness39 pass; focused paging and1536-page heap growth pass
sequentially at128/512MiB. Full B19 frame/mapping lifetime, exception ABI,
TSS/stacks and CPL3 continuation are still blockers. Current evidence/review/
acceptance and the exact next task: `docs/PHASE11_HANDOVER.md` (A–K).
No ELF/syscall/scheduler/Phase12, push or Proxmox deployment was introduced.

### Historical permission-only checkpoint

First 11A prerequisite repairs effective PDE/PTE permissions and refuses
unowned user/nonpresent map requests. Host270 pass (2 ignored), harness37 pass;
full inherited prerequisite acceptance **PASS54/54**, actual exit0, not full
Phase11 acceptance. Exact evidence:
`test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json`.
All135 frozen inputs, ISO-extracted kernel/archive and local cleanup verified.
No Ring3 launch, TSS, syscalls, ELF loader or process lifecycle is implemented.
Design/dependency diagram: `docs/PHASE11_DESIGN.md`; tool manifest:
`docs/PHASE11_TOOLS.md`; status and exact next task:
`docs/PHASE11_HANDOVER.md` and `NEXT_SESSION_PROMPT.md`.
Existing branch retained; no push, Proxmox deployment or Phase12. All accepted
Phase10B media/evidence below remain historical rollback checkpoints.

## Phase 10B COMPLETE — local acceptance verified

Source checkpoint: `449ed434ed5dbf1518b99821178a5fcd1d343b75` on `maintenance/phase10`.
Full acceptance: **PASS 53/53 gates**, invocation-owned
**56/56 initramfs scenarios, 3379/3379 matrix checks**.
Evidence: `test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json`;
independent closeout: `test_results/phase10b/final_verification.json`.
All 134 source/build inputs were independently rediscovered and hash-matched.
Scoped independent review: no blocking findings (`test_results/phase10b/independent_scoped_review_20261016T111204Z_f632dad1df.json`).

Trusted complete-byte SHA-256 verification precedes parse/publication at read-only
`/system`. The kernel is the trust anchor, not the module. Real GRUB and injected
ELF recovery, allocator exhaustion, mount failure and reboot are covered at
128/512 MiB. No archive code is executed; RAMFS recovery is independently owned.
Host serial/parallel: **265 passed, zero failed, two ignored** each. Inherited
B11/B13/B18/B26, CPU faults/paging, keyboard/VGA, growth/OOM, ATA/RostiFS and all
9,071 modeled crash cases remain covered. Old failures below are historical.

Accepted ISO: `dist\rosti_phase10b_20261016T120546Z.iso` (11096064 bytes), SHA256
`117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8`. Independently extracted production kernel SHA256:
`f292cd2e406487ead05a2b9008e0cf6bf39d145b122f7ebac160ba4d1c53386f`. Fixture features are excluded.
No local QEMU remains. Historical Phase 9.6 ISO is unchanged.

No Phase 10 deployment, VM/storage mutation, Phase 11, tag or history rewrite.
Fresh read-only inspection shows VM 103 running Phase 9.6 ISO, 512 MiB/one vCPU,
SeaBIOS/pc, no data disk; stale Phase 7 references below are historical.
Commit/push of completed Phase 10B is explicitly authorized. Unrelated `d1/`
and `scripts/b13_boot_fixture.py.backup` stay excluded and preserved.

Limits: trusted-loader/single-owner ring-0 assumptions; no hardware secure boot
or hostile-userspace isolation. Runtime heap/stack high-water is **unknown**.
The 546,228-byte import capacity bound excludes allocator overhead/fragmentation
and is not a measured peak. Guest malformed/truncated images prove digest
rejection; authenticated structural-parser rejection is covered on the host.
See `docs/PHASE10_INITRAMFS.md` for exact contracts and retained failures.

## Phase 9.6 — safety before new features

Boot-memory hardening adds bounded fallible Multiboot inventory, reservation-
aware contiguous growth, explicit aligned/DF-clear Rust entry, permanent boot
mapping pins, allocation-free paging diagnostics and unlocked backing cleanup.
Rejected boot metadata retains an independent RAMFS recovery environment while
persistent storage remains disabled. No initramfs or Phase 10 feature is added.
RostiFS format v1, 4 KiB blocks, COW/CRC/capabilities and flush ordering remain.

Current release status, exact verification evidence, footprint and limitations:
`docs/PHASE9_6_SAFETY_HARDENING.md` and `HANDOVER.md`. Full local acceptance is
`python -B scripts/phase6_verify.py`. Proxmox VM 103 remains on Phase 7; no
deployment is authorized. This remains a trusted ring-0 kernel, not verified
untrusted-userspace isolation. Earlier milestone sections below are historical.

## Phase 9.5C final bounded maintenance

COW offset writes avoid old-block reads only when every live old byte is replaced.
This reduces measured covered-overwrite transfers without a cache or durability,
CRC, wire-format or capability change. Host timings are mixed; no whole-OS speedup
is claimed. Resident section total and static span are unchanged. Frame/heap
investigations confirm costs and stranded capacity but leave unsafe allocator
changes deferred. Read docs/PHASE9_5C_RESULTS.md and current HANDOVER.md for the
final verified checkpoint. Phase 10 is blocked, not started; no VM was deployed.

## Phase 9.5B evidence-driven performance maintenance

Ordinary partial RostiFS reads avoid unrequested sectors, retaining the existing
full-block path, resident scratch, capability checks, mount CRCs and every durable
commit barrier. Five candidates were audited; the all-sector prototype was rejected,
and four unmeasured/higher-risk candidates remain deferred. The counted small-read
host fixture improves about 3.8x; paced QEMU cat latency is not distinguishable from
noise. No whole-OS speedup or physical disk throughput is claimed. Static aligned
kernel span costs an additional 4 KiB; filesystem and retained heap storage do not grow.

Read docs/PHASE9_5_OPTIMIZATION_CANDIDATES.md and
docs/PHASE9_5_OPTIMIZATION_RESULTS.md plus the current HANDOVER.md for final release
acceptance, rejected/failing probes, space costs and explicit partial-suite coverage.
NEXT_SESSION_PROMPT.md now continues maintenance, not Phase 10. Proxmox is unchanged.

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
