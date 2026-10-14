# Rosti OS — Phase 9.5B performance maintenance handover

## Latest Phase 9.5B continuation — C03 VERIFIED

Continuation started from `55cda2f38603a9f4c9078f0328344d69d9e8db44`.
Verified source commit: `bea7e87e29b4c8b7fd0d6158ec1dd66d3ee11aca`.
Documentation/evidence commits may follow. Branch: maintenance/phase9-5b.
Occupancy diagnostics now count the clipped union of current/previous extents
with metadata-bounded endpoint work, not volume-wide scans. No cache/heap/I/O,
allocation helper, format, CRC, capability or durability change.

Final local acceptance: test_results/phase9_5/acceptance_20261014T123644Z_106sujbb/acceptance.json,
PASS 38/38, 176 Rust and 47 Python; all 84 source hashes and 52 nested reports
independently checked. All 9,071 modeled crash cases and ELF/ISO 128/512 MiB gates
remain passing. Accepted ISO: dist/rosti_phase9_5_20261014T123644Z.iso.
SHA256: c6c1f9381075320b864a4b4f9542c019879037da2d484764136db12a66e7267b.
Kernel SHA256: ba7b86f66c09e0dc7a7814df8ab82cdecfdba9314c0fc1cc19c34f6a1a5df0d0;
independently extracted /boot/rosti.bin matches. All earlier accepted ISOs survive.

B/C/B/C host diagnostic fixture, 18 samples/case: fragmented 512 KiB volume
27.500 -> 13.000 us (2.115x), maximum geometry 16.660 ms -> 12.983 us.
Capacity-only backing is disclosed; this is not guest/device/whole-OS speed.
QEMU B/C/B/C has six samples/RAM/checkpoint; observed timing ranges overlap,
including the retained first-pair create shift. No end-to-end gain is claimed.
Every replay preserves 9 reads/112 writes, retained heap 8,232 B, capacity 1 MiB,
zero growth pages and cleanup. Text +496 B, rodata -4 B, data +16 B, BSS 0;
loaded +508 B, page-rounded span unchanged; full ELF -4,396 B. Diagnostic local
prologue 92 -> 204 B is not peak/caller/IRQ stack usage.

Evidence: docs/PHASE9_5_C03_RESULTS.md and test_results/phase9_5/c03_measurements.json,
c03_review.json, c03_validation.json. Previous optimization_*.json remain immutable
C01 evidence. Optional widened-u32 oracle/public failed-remount stats transition
coverage is DEFERRED; independent review found no security concerns/logic errors.
The missing-ISO candidate FAIL was a resolved packaging-path error before guest
launch; no timeout or test was weakened. Earlier C01 append timeout remains open.

Proxmox read-only refresh: VM 103 running, Phase 7 ISO, 512 MiB, one vCPU, no data
disk; no upload, restart or storage change. No push/tag/history rewrite.
Stop this pass here: C02/C04/C05 and isolated guest/IRQ/TLB/ATA/peak metrics remain
DEFERRED. Phase 10 remains BLOCKED by B11/B13/B18/B26 and broader safety work.
The C01 checkpoint below is historical; current continuation is NEXT_SESSION_PROMPT.md.

## Historical C01 verified Phase 9.5B checkpoint

Canonical repository: C:\Users\iamsv\Documents\Rust-OS.
Branch: maintenance/phase9-5b. Clean campaign starting HEAD:
`9792bd4cc2dbb04e1b64b2f623fcb3d0325439e7`. Previous maintenance/documentation
commits were complete; no uncommitted work was discarded. Verified source commit:
`ab1e8033f3b766bcd41ed7b712ae12a1c0f2f871`
(`perf(rostifs): avoid unrequested sectors in partial reads`). Later documentation
commits do not change the accepted source/build inputs. No push, tag move/history rewrite,
Phase 10 implementation, physical disk or VM modification occurred.

Previous Phase 9.5 checkpoint was independently rechecked: 37/37 PASS, 82 source
hashes, 52 nested reports, historical ISO/kernel identities and paired benchmark
JSON. The older accepted Phase 9/9.5 binaries/reports remain unchanged. New evidence:
test_results/phase9_5/optimization_baseline.json, optimization_results.json and
optimization_review.json; docs/PHASE9_5_OPTIMIZATION_CANDIDATES.md and
docs/PHASE9_5_OPTIMIZATION_RESULTS.md.

**VERIFIED:** C01 hybrid partial-read optimization. Requested sectors only for
partial blocks, existing read_block for complete aligned blocks; same resident
scratch, no new heap/cache/static field/unsafe code. Full-block geometry, format 1,
mount/check whole-extent CRCs, writes/COW/delayed reuse/poison/flushes, capability
checks and shared offsets are unchanged. Read errors may leave a copied caller
prefix; unrequested sector errors are no longer probed. Four new portable read
regressions and a mandatory acceptance gate preserve boundary/error coverage.

Measurements: 64-byte reads use 8 -> 1 sectors. Original complete QEMU workload
uses 16 -> 9 reads, 112 writes unchanged, transfer bytes 65,536 -> 61,952.
Final counted RAM-fixture medians: 64 B 686.575 -> 182.325 ns, 128 B 697.825 ->
182.700 ns, 512 B 692.500 -> 180.450 ns (about 3.8x host-fixture latency ratios).
18 samples per read size, fixed 2,000 operations/sample, identical final fixture
and B/C/B/C order. QEMU also runs B/C/B/C, six samples per RAM size/checkpoint;
cat medians 68.831 -> 68.562 ms (128) and 68.769 -> 68.556 ms (512) overlap in
spread. **No confirmed QEMU cat/boot latency or whole-OS speedup.** Full-block
host differences overlap in noise. All observations/regressions are retained.

Space: ELF 5,148,792 -> 5,157,868 B; text +2,016 B, data +176 B, rodata/BSS
unchanged. Allocated sections +2,192 B, aligned static span +4,096 B (one more
reserved frame). FS static 28,240 B, descriptor table 2,328 B, scratch 4,096 B
included and heap 8,232 B/capacity 1 MiB unchanged; no persistent growth pages.
Allocated physical frames remain 33/129 at 128/512 MiB. Read prologue estimate
352 -> 500 B, not measured peak stack; boot stack remains 16 KiB. No compiler,
target, CPU tuning, SIMD, linker, Multiboot or diagnostic-profile change.

Final full acceptance:
`test_results/phase9_5/acceptance_20261013T233346Z_9aov10bm/acceptance.json`.
**PASS 38/38**, completed background exit 0. All 83 source/build inputs still
match after source commit; 52 nested reports validated. **173 Rust** (145 kernel,
20 portable, 4 tools, 4 reads), **47 Python** (4 media, 13 acceptance, 16 RostiFS,
14 benchmark). ELF validation 8/8, ten boots each RAM size, paging/faults,
keyboard/VGA, RAMFS/FD/growth/OOM, ATA/RostiFS persistence and corrupt-media recovery
pass on ELF/GRUB at 128/512 MiB. Mandatory matrix: 102 RAMFS + 98 ATA + 168 RostiFS
checks in each of four configurations (1,472 distinct checks). Crash model remains
2,639 rejected/torn/flush cases + 2,328 reordered cuts + 4,104 prefix tears (9,071).
Final owned-image hashes were reread; no owned QEMU remains. No physical power-loss proof.

Accepted ISO: `dist/rosti_phase9_5_20261013T233346Z.iso`, 10,280,960 B.
SHA256: `a3620655691625f36e760fae73b50878176dc940fd924686956053bd7eb91681`.
Kernel: `a01f5d2728187907312553bd2c2d76e58f6e6af028a0b1c2b7e81b5f00d7d330`;
independently extracted ISO payload matches. New ISO is local only.

**REJECTED:** all-sector C01 prototype increased full-block host CPU cost;
hybrid keeps the original block path. Five candidates audited, one experiment
with two implementations; no second/third unmeasured optimization was started.
First full acceptance failed 25/26 attempted gates on ELF128 append ATA poll
timeout. Failed logs/image/report remain. B/C/B/C exact ELF128 reproductions then
passed 168/168 in all four runs, followed by the complete 38/38 acceptance above.
The timeout cause remains unresolved; no poll budget/test was weakened and no ATA
fix is claimed. A reproduction harness read-only-copy interruption was separately
diagnosed/restored; its incomplete comparison is retained, not counted as PASS.

**DEFERRED:** C02 write preservation reads, C03 volume-wide occupancy diagnostics,
C04 frame scans and C05 allocator free-capacity loss. The performance suite is
explicitly partial: isolated guest/subphase/IRQ/TLB/ATA/open/dup/rights timings and
peak heap/stack remain unmeasured. Future process/scheduler/IPC/syscall/network/GPU/
RDP benchmarks are NOT APPLICABLE, not invented. No new IMPLEMENTED BUT UNVERIFIED
production change remains; prior audit findings are not silently resolved.

**BLOCKED:** safe Phase 10/module integration pending B11/B13/B18/B26, and broader
safe-API/exception/allocator/lock prerequisites before untrusted execution. Phase 10
was not begun. NEXT_SESSION_PROMPT.md is now a standalone maintenance continuation;
the previous Phase 10 prompt is retained in Git history, not current authority.

Fresh read-only Proxmox GETs: pve VM 103 rosti-dev still running, 512 MiB/one core,
SeaBIOS/i440fx, Phase 7 ide2 only, no data disk, unchanged digest
c0253f4f9bc55e6c3f222dcc893833cc46157a4b. No upload/reset/restart/storage change;
live RostiFS remains unverified. Temporary baseline worktree/build targets removed;
canonical dist/test_results retain payloads, measurements and failed evidence.

## Archived accepted Phase 9.5 maintenance checkpoint

Canonical repository `C:\Users\iamsv\Documents\Rust-OS`, branch
`maintenance/phase9-5`; `main` remains the original Phase 9 checkpoint.
Initial HEAD: `9da1d48e9c51207b51c31d8c296cf31fd080c49c`.
Verified maintenance source checkpoint:
`b647b7d336a77cb6c0a02678486f6dd2b3185e2a`.
Later documentation/evidence commits do not change its accepted source inputs.

Completed localized changes: correct single-bit clearing; descriptor generation
retirement, failed-open rollback and saturating cumulative counters; 128-byte
capability-checked cat batching; exclusive static-borrow SAFETY comments;
mandatory acceptance reports/exact boot totals; host monotonic benchmark with
failure evidence, owned cleanup and artifact freeze; untracked/ignored generated
Python caches, preserving local copies and the initial unrelated cache.

Audit: **26 distinct findings, 0 P0 / 21 P1 / 5 P2**, with source evidence,
risks and verification plans in docs/PHASE9_5_AUDIT.md. No P0 was identified by
the read-only reviewers; this is not a claim that all existing safe APIs are
sound for arbitrary concurrent/untrusted callers. B01/B02/B05/B07/B08/B24 have
implemented changes; B06 establishes honest partial measurement coverage.
Other findings are explicitly deferred or rejected, not silently fixed.

Initial Phase 9 was independently reverified: all 80 release-input hashes,
36 explicit successful gates, 52 valid nested reports and both ELF/ISO hashes.
`test_results/phase9_5/phase9_reverification.json` and
`phase9_report_reverification.json`. Original Phase 9/8/7 rollback artifacts
and all disposable-image evidence remain. No push, tag move, history rewrite,
physical-disk access, remote upload/attachment/reset/deployment or Phase 10 work.

Current full acceptance evidence:
`test_results/phase9_5/acceptance_20261013T221730Z_ibgi0pg6/acceptance.json`.
**PASS, 37/37 gates**, completed background exit 0. All **82** source/build
inputs were independently reread after acceptance and the final benchmark;
**52** nested reports have explicit PASS/nonempty all-true rows. Real totals:
**145 kernel + 20 portable + 4 host-tools = 169 distinct Rust tests**;
Python **4 media + 11 acceptance + 16 RostiFS + 14 benchmark = 45 tests**.
Inherited crash suites remain 2,639 rejected/torn/flush cases, 2,328 reordered
cuts and 4,104 root-prefix tears (9,071 modeled cases; not physical proof).
ELF validation 8/8, ten boots each at 128/512 MiB, paging 20/20, CPU read/write
faults 2/2 each, ISO paging 2/2, keyboard PASS, VGA 13/13 each ELF/ISO.
RAMFS/VFS/FD/growth/OOM **102/102 each configuration (408)**, ATA **98/98 (392)**,
RostiFS **168/168 (672)** across ELF/GRUB and both RAM sizes. These are **1,472**
distinct filesystem/block matrix checks; do not add nested aggregate reports
again. All owned QEMU processes exited; final task-list inspection found none.

Accepted ISO: **dist/rosti_phase9_5_20261013T221730Z.iso**, **10,272,768 B**.
SHA256: `26e0407ad977bcb573bac03682a95512562f67b9481b58d88c6cdfe3548e84eb`.
Kernel SHA256: `7c6a8097fafcea4fb95e3297d019e92363bb763790f1a54213c897abf083e5ea`.
The kernel extracted independently from the accepted ISO matches that hash;
the old Phase 9 ISO/hash remains unchanged. Sanitized aggregate verification:
test_results/phase9_5/verified_summary.json and suite_totals.json.

Measured filesystem memory remains 28,240 B static including one 4,096 B scratch;
descriptors 2,328 B separate, heap use 8,232 B, no persistent-workload growth.
The 64-byte benchmark workload drops ATA reads 520 -> 16, writes remain 112;
cat alone drops 512 -> 8 in the independently tested portable fixture. Target
cat local prologue estimate increases 316 -> 560 B, not hardware stack high-water.
The maintenance ELF grows 5,146,096 -> 5,148,792 B, text +1,520 B/data +64 B;
static address span and BSS unchanged. This is not a binary-size optimization.
Host timing samples vary substantially; no boot-speed improvement or physical
disk throughput is claimed. See docs/PHASE9_5_PERFORMANCE.md for final replay.
Final sequential same-host replay of old/new accepted ISOs passed six guests
each: boot medians **1046.675 -> 1033.911 ms (128 MiB)** and
**1154.715 -> 1240.394 ms (512 MiB; +7.420% host-observed regression)**.
Cat Enter-to-prompt **122.676 -> 67.968 / 116.855 -> 67.390 ms** at 128/512.
Key pacing/polling are included; no causal boot-speed attribution is established.
ATA/heap deltas remain exact in every replay; paired_comparison.json records all.

Final read-only VM 103 inventory: running, same configuration digest and Phase 7
CD-ROM, no data disk. No deployment; live RostiFS remains NOT VERIFIED.

Research deliverables: docs/MINIMAL_OS_COMPARISON.md,
docs/ROSTI_APPLICATION_ABI_DESIGN.md, docs/ROSTI_LIGHTWEIGHT_GUI_DESIGN.md.
Source-derived facts, vendor claims and hypotheses are separated. No foreign
code/assets imported; Menuet64 restrictions differ from Menuet32 GPL, bootOS is
BSD-2-Clause. Application ABI/ELF32 loading and optional GUI are **design only**.

Phase 10 recommendation remains initramfs, safe mount management, verified
read-only system images and independent recovery. Readiness is **conditional**:
first address B11 growth reservations/module mappings, B13 entry ABI, B18
fallible boot inventory and B26 error-path lock ordering with new tests. Before
untrusted callers, resolve B10/B14–B16/B19 and general error-code exceptions.
Allocator alignment leakage B09 and PS/2 hardware setup B17 remain limitations.
Do not run application bytes in ring0 or call CRC a cryptographic trust anchor.
The complete standalone continuation is NEXT_SESSION_PROMPT.md; no automatic
Phase 10 development or remote modification is authorized.

## Archived Phase 9 verified handover

The following sections record the original checkpoint. Their branch/count/ISO
statements are historical and do not override the maintenance section above.

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

Phase 9 feature checkpoint: `4fb88fd062f3c667ee7682937752e94aa600cdc3`.
Subject: `feat(rostifs): add persistent transactional filesystem v0.1`.
Documentation-only updates do not change that verified kernel. No push, tag move,
history rewrite, real-disk operation or remote deployment was performed.
An untracked Python cache is deliberately excluded from the deliverables.

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
