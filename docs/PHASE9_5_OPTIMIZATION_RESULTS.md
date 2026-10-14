# Phase 9.5B optimization results

## Latest final bounded pass: Phase 9.5C

See [PHASE9_5C_RESULTS.md](PHASE9_5C_RESULTS.md). C02 eliminates measured redundant
preservation transfers while retaining complete COW writes/CRCs/barriers; mixed
host timing does not establish general latency gain. C04/C05 are measured but
production changes deferred. No C01/C03 repeat or Phase 10 implementation.
Earlier acceptance and measurements below are preserved historical checkpoints.

## Latest continuation: C03 VERIFIED

Source checkpoint `bea7e87e29b4c8b7fd0d6158ec1dd66d3ee11aca` adds a bounded
current/previous extent-union diagnostic sweep. See [PHASE9_5_C03_RESULTS.md](PHASE9_5_C03_RESULTS.md)
for the second candidate's actual host measurements, all QEMU replay observations,
space/stack trade-offs and PASS 38/38 (176 Rust/47 Python, 84 source hashes).
No confirmed guest/end-to-end gain is claimed. C02/C04/C05 remain DEFERRED;
Phase 10 remains BLOCKED. This concludes the bounded continued pass.

The C01 narrative and optimization_*.json evidence below are historical and
preserved; use c03_measurements.json/c03_review.json/c03_validation.json for
the latest release identity and verification. No prior timing report is rewritten.

## Scope and decisions

Starting clean HEAD: `9792bd4cc2dbb04e1b64b2f623fcb3d0325439e7`.
Branch: `maintenance/phase9-5b`. Previous documentation/staging/maintenance commits
were complete; no uncommitted work needed checkpointing. Previous acceptance was
independently rechecked: PASS 37/37, 82 matching source hashes, 52 valid nested
reports, both historical ISO hashes and independently extracted kernel payloads.
Evidence: `test_results/phase9_5/phase9_5b_initial_verification.json`.

Five candidates were audited. One candidate (C01) was implemented as a bounded
experiment with an all-sector prototype and a revised hybrid. No second or third
candidate was started without representative measurements. This is not a whole-OS
speedup, a Phase 10 implementation or completion of every desired profiling metric.

- **VERIFIED measurement:** partial-read transfer amplification, unchanged bytes,
  counted RAM-fixture timing, QEMU transfers/memory, ELF payload/sections/assembly.
- **REJECTED:** the all-sector prototype; full-block CPU cost increased.
- **DEFERRED:** C02 write-preservation reads, C03 occupancy diagnostics, C04 frame
  scanning, C05 allocator reclamation, full guest/IRQ/peak instrumentation.
- **BLOCKED:** safe Phase 10/module integration claims by existing B11/B13/B18/B26
  prerequisites; arbitrary untrusted execution also needs the broader prior audit.
- **VERIFIED:** final candidate local release, complete PASS 38/38 and independent
  source/report/artifact readback indexed in optimization_results.json. No new
  IMPLEMENTED BUT UNVERIFIED production change remains. A RUNNING report or static
  reviewer verdict alone never substitutes for that gate.

## Methodology

Accepted A (Phase 9), accepted B (Phase 9.5), candidate C identities are retained.
A's paired report is historical context, not contemporary latency attribution.
B/C QEMU replay order is B/C/B/C, each round three independent fresh GRUB guests
at each of 128/512 MiB: six samples per RAM size per checkpoint. One runner only.
The canonical `phase9_5_bench.py` and its workload were not changed: traverse,
create, write 64 ASCII bytes, cat, append four bytes, list, delete. Same QEMU
10.2.0 default CPU, pc/SeaBIOS, one default vCPU, RAM, IDE writeback raw image
geometry, compiler/profile and input. Owned image creation/cleanup is checked.
Versioned old ISOs are untouched; ISO payloads are extracted to verify identity.

New portable read fixture: host Rust Instant, counted RAM BlockDevice, 128 blocks,
8,193-byte deterministic binary file, aligned offset-zero reads of 64/128/512/4096
bytes, 100 warm-up operations then nine fixed samples of 2,000 reads per size.
Final source-identical fixture is run in B/C/B/C order using an isolated detached
baseline worktree; 18 samples per size/checkpoint. Temporary baseline worktree and
its build targets were removed after measurements. Production configuration stays
unoptimized dev/debug, nightly 1.101.0, i686 soft-float, no SIMD/LTO/CPU tuning.

Timing includes host scheduling, counters, assertions and emulation as applicable.
QEMU Enter-to-prompt includes 65 ms key pacing and 20 ms serial polling. Startup
includes firmware/GRUB, kernel/mount, QMP and prompt observation. These are NOT
isolated guest execution, disk bandwidth, kernel initialization or IRQ timings.
Instrumentation overhead has not been isolated; identical fixture overhead is
included in both checkpoints. Report median, min/max and sample count, not a
single best run. Tiny overlapping changes are not confirmed speedups.

## C01 hypothesis, implementation and tests

`Vfs::read` loaded eight sectors for any partial 4 KiB block. Ordinary reads have
never recomputed whole-file CRCs, so this traffic did not add integrity checking.
Use only intersecting sectors with the existing resident scratch; keep complete
aligned blocks on read_block. All slices remain safe. Full-block geometry is
checked before each partial sector read. EOF clamping bounds offset arithmetic.
No new heap/cache/static field, unsafe code, capability bypass, ATA protocol,
write/commit/mount/CRC/poison/flush change. Format remains version 1.

The transfer-budget regression was RED (8 versus 1) before implementation.
Four portable regressions now check boundaries/EOF/tail sentinels, transfer budgets,
invalid post-mount geometry before I/O, and every one of 17 fault positions over
partial/full/partial reads, with subsequent exact recovery. Existing cat error
indices moved from 0/8 to 0/1 (first/second refill); the output/error/FD ownership/
shared-offset assertions are retained. A new mandatory acceptance gate requires
all four tests; mocked missing invocation and incomplete totals were RED/GREEN.

Read failures may leave an already copied prefix in caller buffers, as before;
copy granularity changes. An unrequested sector's error is no longer probed.
Mount/check still read and validate all padded extent bytes. Do not interpret
this intentional read schedule change as post-mount bit-rot protection.

## Before/after measurements

Final portable host ns/read, 18 samples each; units include fixture overhead:

| Component | Baseline | Optimized | Speedup | Memory Delta | Tests |
|---|---:|---:|---:|---|---|
| Aligned 64 B read | 686.575 ns | 182.325 ns | 3.766x host fixture | no heap/cache growth | bytes, EOF, failures, budget |
| Aligned 128 B read | 697.825 ns | 182.700 ns | 3.820x host fixture | same | same |
| Aligned 512 B read | 692.500 ns | 180.450 ns | 3.838x host fixture | same | same |
| Aligned 4096 B read | 700.525 ns | 668.725 ns | 1.048x observed only; noise | same | block-path/boundary coverage |
| 64/128/512 B sector transfers | 8/read | 1/read | N/A: seven fewer sectors/read | same scratch | exact counter assertions |
| Full 4096 B sector transfers | 8/read | 8/read | unchanged | same scratch | exact budget |
| QEMU complete workload | 16 reads, 112 writes | 9 reads, 112 writes | 7 reads saved, no OS score | retained heap unchanged | original exact workload |

Host min..max ns/read:
64 B 650.200..885.900 -> 162.800..194.300;
128 B 651.200..3204.050 -> 174.750..199.700;
512 B 618.550..1335.000 -> 172.200..197.450;
4096 B 642.300..1238.250 -> 637.950..962.250.
Small-read distributions are separated; full-block ranges overlap. Latency speedup
is baseline median / optimized median, not an average of unrelated operations.

QEMU medians (six samples per row), milliseconds:

| Observation | B 128 MiB | C 128 MiB | B 512 MiB | C 512 MiB |
|---|---:|---:|---:|---:|
| Start to mounted shell | 1890.580 | 1418.980 | 2028.250 | 2026.281 |
| Cat Enter-to-prompt | 68.831 | 68.562 | 68.769 | 68.556 |

Cat ranges: 68.626..79.776 -> 67.203..77.125 (128),
68.540..69.009 -> 68.259..77.769 (512). Boot ranges also overlap broadly:
1239.659..1999.870 -> 1156.034..1772.073 (128),
1923.733..2307.019 -> 1484.076..2295.602 (512).
**No confirmed QEMU cat or boot latency improvement** is claimed. All command
observations, including regressions, are retained in the JSON. ATA transfer bytes
fall 65,536 -> 61,952 (mount excluded); writes stay 112. No flush was deleted.
Historical A used 520 reads/112 writes; the earlier A->B reduction is not new credit.

## Rejected prototype

All-sector version retained eight transfers for a full block but repeated geometry/
borrow work. Unchanged initial fixture, nine samples per workload:
full-block median 1,373,600 -> 2,203,100 ns per 2,000 reads (slower).
Logs `phase9_5b_host_baseline1.log`, `phase9_5b_host_sector_probe.log`.
The full-block fast path corrected this regression. Initial exploratory logs are
not pooled with final measurements: review-added geometry fault controls alter
RAM-fixture overhead. Final B/C use the exact same updated fixture and workload;
production code only changes the read strategy. No benchmark sizes/repetitions
were changed to select a favorable result.

## Space and compatibility trade-off

| Metric | Accepted B | Candidate C | Delta |
|---|---:|---:|---:|
| Full ELF bytes (includes debug) | 5,148,792 | 5,157,868 | +9,076 |
| .text | 608,449 | 610,465 | +2,016 |
| .rodata | 39,126 | 39,126 | 0 |
| .data | 92,176 | 92,352 | +176 |
| .bss | 1,138,108 | 1,138,108 | 0 |
| Allocated sections | 1,878,067 | 1,880,259 | +2,192 |
| Static aligned address span | 1,887,676 | 1,891,772 | +4,096 |
| ISO packaging | 10,272,768 | 10,280,960 | +8,192 |
| FS static objects | 28,240 | 28,240 | 0 |
| Descriptor table | 2,328 | 2,328 | 0 |
| FRAME_ALLOC object | 32,804 | 32,804 | 0 |
| Retained heap / capacity | 8,232 / 1,048,576 | same | 0 |
| Growth pages / failed allocations | 0 / 0 | same | 0 |
| Allocated physical frames (128 / 512 MiB GRUB) | 33 / 129 | 33 / 129 | 0 |
| Reserved frames (128 / 512 MiB GRUB) | 2050 / 2018 | 2051 / 2019 | +1 each |
| Mapped pages (128 / 512 MiB GRUB) | 31199 / 129503 | same | 0 |
| Boot stack reservation | 16,384 | 16,384 | 0 |
| Read function prologue push+sub estimate | 352 | 500 | +148 |

The extra 4 KiB static span is a real low-RAM cost, not hidden as unchanged memory.
It buys seven fewer transfers per small read without a persistent cache. Actual
per-workload frequency is unknown: no weighted whole-OS impact or speed-per-KiB
claim is invented. Additional peak transient allocation/stack high-water is
unmeasured. Function prologue estimates exclude callees/interrupts and do not prove
maximum stack. Assembly is retained; Multiboot, linker, entry, target and diagnostic
symbols are preserved. Both 128/512 MiB must pass privileged acceptance.

## Rosti-specific performance-suite coverage

| Requested area | Actual coverage in this pass | Remaining status |
|---|---|---|
| Boot | original GRUB start-to-mounted-prompt distribution, full ELF/ISO boot acceptance | DEFERRED: isolated kernel/paging/heap/probe/mount and ELF-vs-ISO latency |
| Allocation | existing isolated 1,000 mixed-size alloc/free host fixture, checkerboard fragmentation; real growth/OOM acceptance; static/retained memory | DEFERRED: per-size distributions, failure/growth latency, peaks and exact lost-capacity workload |
| Paging | existing isolated frame allocate/free/map/unmap host fixture, nine samples each B/C; privileged paging/CPU faults | DEFERRED: guest cycles, hardware TLB cost, translation distribution |
| FD/VFS | original traversal and actual capability/dup/shared-offset regressions | DEFERRED: isolated open/close/dup/rights/handle/mount-dispatch timing/call counters |
| RostiFS | original create/read/write/append/list/delete timings; counted read microbench; complete crash/corrupt/recovery acceptance | DEFERRED: isolated mount/commit/recovery latency, per-operation write/flush counter suite |
| ATA/IDE | exact real guest sector transfer counters, read/write/poll/error/flush protocol regressions | DEFERRED: isolated single/sequential sector/flush/poll latency |
| IRQ/timer/keyboard | keyboard/VGA/PIT regressions, no profiling hooks | DEFERRED: reliable IRQ execution/latency/timer/event costs |
| Future features | no implemented scheduler/process/IPC/syscall/network/GPU/RDP | NOT APPLICABLE |

This is an expanded, reproducible **partial** suite, not fabricated complete guest
profiling. No profiler that cannot observe bare-metal execution is credited. Model
frame/heap timings are retained but unchanged source and wide variation prohibit
attributing their fluctuations to C01. Memory models do not execute hardware TLBs.

## Review, acceptance, release and handover

The first frozen full acceptance failed **25/26 attempted gates** on ELF128
RostiFS append: serial recorded `filesystem block I/O failed: poll timeout`,
one ATA timeout and `fs: device I/O error`. Evidence:
`acceptance_20261013T231811Z_w8uxdqs9` beneath test_results/phase9_5.
No versioned candidate ISO was published by that failed run. All prior passing
gates remain evidence, not a substitute for full acceptance. ATA, storage and
checked block-helper production diffs are empty. B/C/B/C exact ELF128 reproductions
use independently extracted accepted B and preserved candidate payloads, identical
harness/data/geometry and unchanged timeout bounds; their results are retained in
phase9_5b_poll_reproduction2/comparison.json. Do not infer the cause solely from
an empty write-path diff, hide the failure, lengthen polls or retry indefinitely.

The first reproduction runner completed accepted B at 168/168 but was interrupted
before C: copy2 propagated the extracted ELF's read-only mode to the generated
kernel target. Observed target mode 0444/READONLY and no live QEMU; only that
generated target was made writable, the candidate hash restored and a new directory
used with copyfile. The interrupted runner and its evidence are not discarded or
counted as a completed comparison. phase9_5b_poll_harness_interruption.json records it.

The corrected B/C/B/C comparison completed **168/168 PASS in all four runs**,
with exact payload hashes, owned process cleanup and candidate restoration checked.
The timeout was not reproduced; its cause remains unresolved and no ATA fix is
claimed. One fresh full frozen acceptance is required after these reproductions;
the campaign does not use an unbounded retry-until-pass loop.

Read-only storage and memory specialists identified source-grounded candidates.
Independent correctness reviewers inspected the final production/test/harness diff;
no security or logic error was reported. Earlier suggestions for geometry and
mixed-read fault coverage were implemented. Static review is not execution proof.
`optimization_review.json` records verdicts, provenance and remaining suggestions.

Final acceptance `acceptance_20261013T233346Z_9aov10bm/acceptance.json` is
**PASS 38/38**. All 83 source/build hashes still match after source commit
`ab1e8033f3b766bcd41ed7b712ae12a1c0f2f871`; 52 nested reports validate, and the
mandatory filesystem/block matrix has 1,472 distinct checks. Rust: 145 kernel +
20 portable + 4 tools + 4 reads = 173; Python: 4 media + 13 acceptance + 16
RostiFS + 14 benchmark = 47. Both ELF/GRUB and both RAM sizes passed persistence,
growth/OOM, paging/CPU faults, boot, keyboard/VGA and corrupt-media recovery.
The four final owned image hashes were independently reread, and no local QEMU
i386 remained. Full checks and artifact identities are in optimization_results.json.

Accepted ISO: `dist/rosti_phase9_5_20261013T233346Z.iso`, 10,280,960 bytes,
SHA256 `a3620655691625f36e760fae73b50878176dc940fd924686956053bd7eb91681`.
Independently extracted kernel matches SHA256
`a01f5d2728187907312553bd2c2d76e58f6e6af028a0b1c2b7e81b5f00d7d330`.
The older accepted Phase 9/9.5 ISO bytes remain unchanged. The timeout's underlying
cause remains unresolved despite the bounded reproductions and final PASS.
The original crash model covers 2,639 rejected/torn/flush failures, 2,328 reordered
cuts and 4,104 root-sector prefix tears (9,071 cases); no physical power-loss proof.
Raw failures/probes, sanitized measurements and old accepted binaries remain.

Proxmox VM 103 was only read: running, 512 MiB/one core, SeaBIOS/i440fx, same
Phase 7 ide2 and config digest, no data disk. No upload/restart/storage mutation,
push, tag move, history rewrite or Phase 10 development. Remaining candidates and
profiling gaps are intentionally DEFERRED. Continue with NEXT_SESSION_PROMPT.md,
not the archived Phase 10 mission.
