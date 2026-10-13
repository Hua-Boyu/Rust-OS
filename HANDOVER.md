# Rosti OS — Phase 9 verified handover

## 1. Checkpoint and safety

Canonical repository: `C:\Users\iamsv\Documents\Rust-OS`, branch `main`.
Windows 11/Git Bash/WSL2; Rust nightly; bare-metal i686 `no_std` kernel;
GRUB Multiboot v1, SeaBIOS and QEMU i386. Native tool paths use `C:/...`.
The mission remains extending older computers' useful life through secure,
efficient computing and reduced electronic waste.

Phase 8 is secured as `8029f3209c36fcceaec6eaf9e8b3228be5376e0f`
(`feat(block): add ATA IDE persistent block storage`), distinct from Phase 7
`7b8b0fe4f90a2bc8609c3a76a4eb6d7c977af5d3` and the Phase 9 release.
Phase 8 acceptance inputs matched the recovered worktree; normalized Git blobs
matched that checkpoint (Git CRLF/LF storage differs). Its accepted ISO hash was
independently reread and matched. No redundant Phase 8 commit or deployment.

Phase 9 feature checkpoint: resolve with
`git log -1 --format='%H' --grep='^feat(rostifs): add persistent transactional filesystem v0.1$'`.
A documentation-only follow-up may record that exact hash. No push, tag move,
history rewrite, real-disk operation or remote deployment was performed.
The preexisting untracked Python cache is unrelated and deliberately excluded.

## 2. Implemented and locally verified

| Feature | Status |
|---|---|
| Portable dependency-free no_std Rust engine and host tools | IMPLEMENTED / LOCALLY VERIFIED |
| Format version 1, explicit LE, checked 4 KiB / 512-byte translation | IMPLEMENTED / LOCALLY VERIFIED |
| Root/nested directories; create/read/write/append/replace/truncate/stat/list/remove | IMPLEMENTED / LOCALLY VERIFIED |
| Contiguous allocation, exhaustion, fragmentation rejection, delayed reuse | IMPLEMENTED / LOCALLY VERIFIED |
| CRC32C roots, metadata banks and whole padded file extents | IMPLEMENTED / LOCALLY VERIFIED |
| COW metadata/data, flush-ordered commit, recovery and malformed-volume rejection | IMPLEMENTED / LOCALLY VERIFIED within documented model |
| VFS mount routing /mnt/rosti; descriptor rights, offsets, stale IDs, cleanup | IMPLEMENTED / LOCALLY VERIFIED |
| Guarded internal unmount and mount lifetime pins | IMPLEMENTED / HOST VERIFIED; no shell unmount command |
| ELF and GRUB cross-reboot/process persistence, deletion and recovery shell | LOCALLY VERIFIED at 128/512 MiB |
| Physical power-loss safety or cryptographic integrity | NOT VERIFIED / NOT CLAIMED |
| Proxmox persistent-file verification | NOT LIVE VERIFIED; no data disk configured |
| Initramfs, verified system images, signed updates and user snapshots | NOT IMPLEMENTED |

The kernel root stays RAMFS. Only validated test-owned media is exposed at
`/mnt/rosti`; boot never formats a disk. Bad volumes leave the recovery shell
available. Existing file commands retain the capability-descriptor/VFS path.
`rostifs` reports volume/memory; raw `diskwrite` is refused while mounted.

## 3. Source changes

- `crates/rostifs/Cargo.toml`, `Cargo.lock`, `FORMAT.md`.
- Portable modules: `src/{lib,block,checksum,format,engine,vfs,crash_tests,additional_tests}.rs`.
- Host tools: `src/bin/{mkrostifs,rostifsck,rostifs-inspect}.rs`, `src/bin/support/mod.rs`;
  real tool integration tests: `tests/host_tools.rs`.
- Kernel: `src/storage.rs`, `src/block.rs`, `src/main.rs`, `src/shell.rs`,
  `src/fs/{mod,vfs,mounted,rosti}.rs`, `src/fs_commands.rs`, root Cargo files.
- Host kernel harness: `tests_kernel/Cargo.toml`, `Cargo.lock`,
  `tests_kernel/src/{block_tests,mount_tests}.rs`.
- Scripts: `phase6_verify.py`, `test_acceptance_harness.py`, `rostifs_test.py`,
  `test_rostifs_harness.py`, `verify_production.py`.
- All seven required documentation files updated; sanitized evidence retained
  under `test_results/phase9/`. Generated ISO/images/binaries are not committed.

The existing descriptor implementation, RAMFS quotas, heap, paging, keyboard
and IRQ behavior were not replaced. NodeId's slot widened without changing its
8-byte footprint. ATA counters saturate instead of overflowing on long-lived
32-bit I/O. ATA polls have a finite 100,000-read bound, not a wall-clock deadline.

## 4. Format, allocation and recovery

Authoritative specification: `crates/rostifs/FORMAT.md`.
Wire version **1**, blocks **4,096 B**, sectors **512 B**, volume **7..65,536
blocks (28 KiB..256 MiB)**. 64 nodes including root, 60-byte UTF-8 names,
256-byte paths, 256 KiB files, one contiguous extent per file.

Block 0 is reserved for ownership; roots are blocks 1/2; two complete metadata
banks occupy 3..4 and 5..6; data begins at 7. Root headers explicitly encode
magic/version/block size/geometry/fs identifier/generation/bank/metadata CRCs/
root inode/data boundary, with a full padded-root checksum. Records are encoded
field-by-field, never transmuted. Future versions fail closed.

Allocation is the union of both validated snapshots' extents, not a disk-size
RAM bitmap. Duplicate allocation, metadata-as-data, overflow, invalid parents,
cycles, duplicate names, invalid UTF-8/control characters and inconsistent free
records are rejected. Deleted space becomes reusable after the retained older
snapshot releases it; fragmentation can refuse a multi-block extent.

Commit: stage → write fresh data → flush → write inactive metadata → flush →
write inactive CRC-protected root with next generation → flush → acknowledge.
Each storage mutation is one transaction; shell create-plus-write is two.
Any write/flush error leaves old RAM state visible and poisons writes until
remount: durable media may contain old or new committed state. Recovery validates
both complete candidates and file CRCs, selects the newer valid generation and
never guesses repairs. One valid root is degraded recovery; checker rejects
redundancy degradation without modifying media. Unreadable/future-version roots
fail closed because their allocation protection is unknown.

CRC32C is accidental-corruption detection, not cryptography. Tests assume an
honest successful flush durably orders all preceding writes. Rejected/torn
sectors and reordered/lost unflushed writes are modeled; dishonest firmware,
CRC collisions and arbitrary physical power interruption are not proved.

## 5. Completed acceptance

`test_results/phase9/acceptance_20261013T142104Z_1m6_x1ot/acceptance.json`
reports **PASS, 36/36 gates**. All **80** source/build-input hashes were
independently rediscovered and matched after completion. ISO, ELF and final
owned disk hashes were reread. Reports have complete nonempty all-true checks;
all owned guests exited. Final local task-list inspection found no QEMU i386.

| Gate | Actual result |
|---|---|
| Kernel host tests | 132 PASS / 0 FAIL |
| Portable-core tests | 20 PASS / 0 FAIL |
| Host-tool subprocess tests | 4 PASS / 0 FAIL |
| Total Rust host tests (distinct suites) | 156 PASS / 0 FAIL |
| Python media / acceptance / RostiFS harness tests | 4 / 6 / 16 PASS |
| Kernel/host/portable formatting, production build | PASS |
| Production resolved features / deliberate fault exclusion | PASS; default only |
| ELF validation | 8/8 |
| Independent ELF boots | 10/10 at each of 128/512 MiB |
| Paging stability; CPU read/write faults; ISO paging | 20/20; 2/2 each; 2/2 |
| Keyboard; VGA Backspace ELF/ISO | PASS; 13/13 each |
| Existing RAMFS/VFS/FD/growth/OOM matrix | 102/102, 38 commands per configuration |
| ATA block persistence matrix | 98/98 per configuration |
| RostiFS ELF 128 / ELF 512 / ISO 128 / ISO 512 | 168/168 each, 56 commands each |
| GRUB ISO build and boot | PASS |

Crash suites: **2,639** rejected/torn/flush-failure cases, **2,328** reordered
pending-subset crash cuts, **4,104** root-sector prefix tears (**9,071** modeled
cases total). Counts are trace-derived inside tests, not extra test binaries.
Includes exact old/new trees and bytes, repeated failed recovery/reuse, modeled
random sequences, bounds, full volumes/slots, fragmentation and forged metadata
with recomputed CRCs. Rename is not implemented, so rename crash tests do not apply.

Each QEMU filesystem run proves real guest reboot plus new emulator read/delete
and another independent read-only deletion check. The second boot never rewrites
expected content. Host checker/inspector validate guest-written media read-only.
Corrupt and unowned images remain unchanged while RAMFS recovery commands work.
Full details, hashes and per-stage serial reports: `test_results/phase9/verified_summary.json`.

## 6. Artifact identities

Phase 9 ISO: `dist/rosti_phase9_20261013T142104Z.iso`, **10,268,672 B**.
SHA256: `00de8b73281ecb5dfea20297908ad781f42036fbf369966196a8e81df284db2b`.
ELF SHA256: `b129b1ce8dd1c6c785f5fc0aba6d3d9c8c5f4e676433ef519d505fcd4befd9b8`.

Phase 8 ISO preserved: `dist/rosti_phase8_20261013T091203Z.iso`.
SHA256: `5ca54fe8eff24743a8935cbfd8de8f59808bd3ec14f85b23b65c34c3fd0dc6da`.
Its completed acceptance is `test_results/phase8/acceptance_20261013T091203Z_kq161don/acceptance.json`
(27/27 gates, 117 host tests). Earlier rollback and deployed media remain intact.

Final persistent test images (after deletion, verification-only boot unchanged):

| Configuration | Image | Final SHA256 |
|---|---|---|
| ELF 128 | dist/phase9_rostifs_470b26h7/owned.img | 9f87c48a6c7f6d2c6e00e47395b9ca9452109f9d2f4f5a8e7f942a738b67e001 |
| ELF 512 | dist/phase9_rostifs_ycvu0r34/owned.img | 29bbfa9ecf8065f0f5444e49b5b0600292b1a4be846f51a492f3e19afc505578 |
| ISO 128 | dist/phase9_rostifs_jf7s4x_k/owned.img | f7d5bf79d95322ab3ee7ac8fd4b2b6cadbb4e70943506bf759d1ccdffe479508 |
| ISO 512 | dist/phase9_rostifs_9hydcvtc/owned.img | fa0975d9c32f08fb3a64a41f510c49e3133e0b6a85aa6a69a95ac4070b6040e7 |

Pre-deletion hashes are recorded in the verified summary and each report; those
are earlier image states, not the final images' identities.

## 7. Measured memory

Actual i686 ELF symbols: namespace **6,940 B**, core/adapter **21,300 B**,
total FS static objects **28,240 B**, including RAMFS. The diagnostic metadata
and binding-table subtotal is **22,324 B**; it excludes RAMFS and 28 control
bytes. One shared **4,096 B** scratch is included; cache **0 B**. Descriptor
storage **2,328 B**, driver/mutex **104 B**, boot stack **16,384 B**, separate.

Mount/traversal/open/write do not allocate FS heap memory; open records use the
existing fixed descriptor table (no per-open heap allocation). All four real
QEMU configurations retained **8,232 B** heap use and **0** growth pages during
persistent operations, with opens/closes balanced and only console descriptors
remaining. FS static storage remains resident even without a mounted volume.
Peak write metadata/scratch residency is the same fixed budget, not file-sized
staging. Target assembly stack reservations are compiler estimates, not a
hardware stack high-water proof. `test_results/phase9/memory_measurements.json`.

## 8. Proxmox boundary

Fresh read-only config/status inspection at start and finish: pve VM 103,
`rosti-dev`, **running**, 512 MiB, one core, SeaBIOS/i440fx; serial socket;
only ide2 `local:iso/rosti_phase7_20261012T181123Z.iso`, boot order ide2.
No data disk configured. Configuration digest unchanged. No remote mutations,
reset, attachment, upload or deployment. **Live RostiFS is NOT VERIFIED**.
Phase 6 rollback ISO remains the previous verified artifact described in PROXMOX.md.
A possible 64 MiB IDE0 test disk requires fresh inventory, exact storage identity
and explicit user approval; this handover does not grant it.

## 9. Failures retained and limits

The initial draft failed 10/18 host tests. In-flight scratch conversion and
nested Cargo workspace errors were recorded. First full acceptance failed
32/33 attempted gates on an actual ISO ATA flush poll timeout; no versioned
release was published. The corrected bounded polling protocol passed three
168/168 ISO128 reproductions before the full 36/36 rerun. Counter overflow and
old-budget host regressions were RED then GREEN. Failed logs/images remain;
`test_results/phase9/development_checks.json` indexes them.

Limits: test-owned whole images only; no partitions/DMA/LBA48; 64 nodes and
contiguous 256 KiB files; retained roots delay reuse and require COW headroom;
no rename/timestamps/symlinks/user snapshots/compression. RostiFS creation leaves
are strict (trailing separators are not normalized on persistent creates).
Data CRCs are checked at mount/check, not every post-mount ordinary read;
post-mount bit rot can therefore escape a read until revalidation. Poll limits
are iteration bounds, not real-time deadlines. Host path guards assume no hostile
concurrent directory replacement; fs IDs are probabilistic u64, not cryptographic
UUIDs. Descriptor rights do not create user-mode/address-space isolation.
Existing VGA Unicode, PS/2 upstream-loss/ACK, general exception recovery,
256 MiB frame-tracking, no scheduler/networking/swap limitations remain.

## 10. Reproduction and continuation

From repository: `python -B scripts/phase6_verify.py` (background, notification).
Read TESTING.md before invoking individual harnesses. Host Cargo runs from
`C:/Users/iamsv` with absolute manifests. Never run another QEMU alongside the
boot runner; never change source/build inputs during acceptance; restore default
production after deliberate fault fixtures. Use only new dist/ test images.
Formatting is explicit host-only `mkrostifs --test-owned-image ABSOLUTE.img --blocks N`.

The complete standalone Phase 10 prompt is in NEXT_SESSION_PROMPT.md:
initramfs integration, mount management, verified read-only system images and a
secure recovery environment. Phase 10 implementation has not started. Preserve
this accepted filesystem and rollback artifacts; require new acceptance before
another release, and explicit scope before remote storage changes or push.
