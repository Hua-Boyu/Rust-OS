# Phase 9.5B C03 — bounded occupancy diagnostics

## Disposition and scope

Starting HEAD: `55cda2f38603a9f4c9078f0328344d69d9e8db44`, maintenance/phase9-5b.
This is the second candidate in the bounded campaign (C01 had a rejected all-sector
prototype and accepted hybrid). No fourth implementation or Phase 10 is started.
C03 is VERIFIED and accepted for metadata-bounded work and host diagnostic
latency. Full acceptance and the bounded B/C/B/C replay completed successfully.
No whole-OS or guest speedup is claimed.
Previous C01 and earlier A/B reports/accepted binaries remain immutable.

## Hypothesis and smallest change

`mount_info` scanned every data block and tested membership in both 64-record
inventories, including on an empty maximum-sized volume. Host baseline latency
scaled with volume despite identical metadata. Sweep clipped extent endpoints
instead, counting the same union over `[7,total_blocks)`. Include previous-root
extents, duplicates and overlaps; do not assume disjoint inventories or a fully
mounted object. Each iteration advances strictly, with at most 257 passes over
128 records. No cache, sorted scratch, heap allocation, unsafe code, mutation,
I/O, allocation-helper, format, capability, COW, CRC, poisoning or flush change.
Widen start+blocks to u64 before clipping; emitted target remains baseline i686.

Affected source: crates/rostifs/src/engine.rs, new src/occupancy_tests.rs and the
host-tools integration fixture tests/read_performance.rs. The transfer-budget
regression was RED before implementation (15,488 versus 128 probes at 128 blocks).
Three default-core regressions now test empty-volume work at multiple capacities,
all 128 interleaved extents, and a BTreeSet oracle over 320 synthetic inventories.
NoIo panics on every transfer/flush. These are synthetic state models, not newly
simulated public failed-remount transitions. Existing failure/remount suites pass.

## Controlled host measurements — VERIFIED

B1/C1/B2/C2, same nightly host unoptimized/debuginfo profile and exact final
fixture, nine samples of three queries per batch:18 samples/state/size/checkpoint.
Same FS id 0xc03, inputs, geometry, warm query and assertions. Setup/format/mount/
mutations excluded. Empty states use 7 blocks; the deterministic fragmented case
creates 16 one-block files then deletes alternate files, retaining9 union blocks
plus7 metadata/reserved blocks. Fixed512 KiB backing covers every touched sector;
capacity-only modeling is expressly not a full-volume device test. Diagnostic
sector reads/writes/flushes are 0 on both sides. No concurrent benchmarks.

Clock overhead is included identically and not isolated. Three queries/sample
make submicrosecond absolute values sensitive to clock overhead: large ratios
are approximate host results, supported by deterministic work bounds, not guest
cycles. Min/max and all 216 raw timing samples are in c03_measurements.json.

| Blocks / state | Baseline median | Candidate median | Latency speedup | Samples each |
|---|---:|---:|---:|---:|
| 128 / empty | 27.250 us | 0.700 us | 38.929x | 18 |
| 128 / fragmented | 27.500 us | 13.000 us | 2.115x | 18 |
| 1024 / empty | 232.267 us | 0.700 us | 331.810x | 18 |
| 1024 / fragmented | 249.717 us | 12.833 us | 19.458x | 18 |
| 65536 / empty | 15468.767 us | 0.733 us | 21093.773x | 18 |
| 65536 / fragmented | 16660.033 us | 12.983 us | 1283.186x | 18 |

All six baseline/candidate ranges are disjoint. Do not combine these speedups
into an OS score, invent diagnostic frequency, or infer a weighted end-to-end gain.

## Space and assembly — VERIFIED bounds, not peak measurements

- Full ELF:5,157,868 ->5,153,472 bytes (-4,396, chiefly nonresident debug changes).
- Text:+496 B; rodata:-4 B; data:+16 B; BSS:0; allocated sections:+508 B.
- Page-rounded static address span:unchanged; no additional reserved frame.
- No persistent buffer/field/cache or heap allocation. Host core remains20,296 B.
- Target mount_info local prologue:92 ->204 B (+112). Register saves/callees,
  caller/IRQ frames and total stack high-water are not measured by this estimate.
- No compiler profile, LTO, CPU, linker, Multiboot or entry change. No SIMD added.

The extra loaded508 B is absorbed by existing page slack. Guest speed per extra
KiB is unavailable because isolated guest timing is unavailable; do not divide
host latency by guest section growth and present that as hardware efficiency.

## QEMU replay and failed harness attempt

Unchanged original small-file benchmark, same ISO inputs per checkpoint, default
QEMU CPU/pc/SeaBIOS/one vCPU,128/512 MiB and fresh canonical owned image geometry.
First pair has three runs/RAM/checkpoint. Its create median moved by about one
20 ms observation interval; a bounded second B/C round is retained, not used to
retune the workload or discard samples. Final ranges/disposition are below.
Startup includes firmware/GRUB/QMP/mount/observation. Command time includes 65 ms
key pacing and20 ms polling, not isolated guest execution or ATA latency.
Local ELF metadata in ISO-mode reports is not proof of the ISO payload; separate
extraction and SHA256 checks are required for each input and accepted output.

Final B/C/B/C has six samples/RAM/checkpoint. Create medians are 83.199 ->90.669 ms
at 128 MiB and83.051 ->94.345 ms at 512 MiB; baseline/candidate ranges overlap
(67.930..111.753 versus 79.232..111.989 ms;67.859..188.665 versus 68.621..110.103 ms).
The apparent first-pair shift does not establish a causal regression or improvement.
Boot/read/write/append ranges also overlap. All observations, including slower
candidate create medians and outliers, are retained in c03_validation.json and
the original per-round reports. There is no confirmed end-to-end speedup.
Every replay retains 9 reads/112 writes/61,952 transferred bytes,8,232 B retained
heap,1 MiB heap capacity,zero growth pages,three console descriptors and no
leaked file records. These are post-cleanup values, not transient peaks.

Initial candidate invocation was BLOCKED before guest launch by a missing ISO
path:build-proxmox-iso.py silently ignored unsupported --latest-name and wrote
its fixed dist/rosti.iso output. FAIL c03_qemu_candidate.json is preserved; copying
the newly built output to a unique benchmark ISO corrected the artifact path.
No test, polling budget or durability operation was changed. This is a known
packaging-path failure, unlike the unresolved earlier C01 append poll timeout.

## Full acceptance — VERIFIED

Canonical scripts/phase6_verify.py:PASS38/38, completed on frozen source inputs.
176 Rust tests (145 harness,23 core,4 tools,4 read regressions),47 Python tests.
All9071 modeled crash cases retained:2639 rejected/torn/flush,2328 reordered,
4104 root byte-prefix tears. Model success is not physical power-loss proof.
All84 source hashes and52 nested PASS reports independently rechecked. ELF/GRUB
128/512 MiB, faults, paging, keyboard/VGA, capability/FD, RAMFS/VFS growth/OOM,
ATA/RostiFS persistence, corruption and safe recovery-shell checks all pass.

Report:test_results/phase9_5/acceptance_20261014T123644Z_106sujbb/acceptance.json.
ISO:dist/rosti_phase9_5_20261014T123644Z.iso.
SHA256:c6c1f9381075320b864a4b4f9542c019879037da2d484764136db12a66e7267b.
Kernel SHA256:ba7b86f66c09e0dc7a7814df8ab82cdecfdba9314c0fc1cc19c34f6a1a5df0d0.

Independent read-only /boot/rosti.bin extraction matches the accepted ELF.
Earlier Phase9.5/C01 and both benchmark inputs were separately extracted and
hashed; their full ISO hashes are unchanged. Only engine.rs/read_performance.rs
changed among the prior83 source inputs, plus the new occupancy test module.

## Independent review and deferred work

Read-only specialist passed:no security concerns or logic errors. Code review
is not acceptance evidence. Optional widened-u32 oracle and public device-failure/
remount-stat transition cases are DEFERRED supplementary coverage; source was
not changed while acceptance ran. Absolute tiny host timings need clock caution.

C02 preservation reads, C04 frame scans, C05 allocator capacity reclamation and
isolated guest/IRQ/TLB/ATA/peak instrumentation remain DEFERRED. Existing
B11/B13/B18/B26 and wider module/safe-API prerequisites keep Phase10 BLOCKED.
Future scheduler/context switch/IPC/syscall/network/GPU/RDP tests are NOT APPLICABLE.
Proxmox was read only:VM103 running on Phase7 ISO,512 MiB,one vCPU,no data disk;
no deployment, restart or storage change. No push, tag or history rewrite.

Evidence:c03_measurements.json,c03_review.json,c03_validation.json and versioned
acceptance/c03_qemu_* reports under test_results/phase9_5. Prior optimization_*.json
remain the immutable C01 campaign reports. Assembly/binary payloads remain local
under dist/c03_payloads and are not committed.
