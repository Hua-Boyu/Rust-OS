# Phase 9.5B optimization candidates

Scope: maintenance only; no Phase 10, target/profile change, format migration,
flush deletion, VM deployment or physical media. Starting clean source:
`9792bd4cc2dbb04e1b64b2f623fcb3d0325439e7`. The existing cat batching and descriptor
fixes are retained, not credited again. Historical acceptance/artifacts are immutable.

Evidence labels distinguish actual instrumented transfers/timings from source-derived
complexity. A plausible complexity problem without representative measurements is
not approval to optimize. No new P0 was identified in the inspected paths; the prior
safe-API/boot-memory findings remain unresolved, not disproved by these tests.

## Five strongest remaining candidates

### C01 — partial-read sector amplification (P1, selected)

- Subsystem/source: `crates/rostifs/src/engine.rs`, Vfs::read; checked translation
  in `crates/rostifs/src/block.rs`; real-core shell fixture in `src/fs_commands.rs`.
- Measured evidence: previous accepted 64-byte cat transfers eight sectors. New
  RAM-device fixture measures 16,000 sector reads for 2,000 aligned reads of
  64/128/512 bytes. Its budget regression is RED: eight reads versus one.
- Root cause: each requested partial block reads all eight sectors, although
  ordinary post-mount reads have never recomputed the padded whole-file CRC.
- Proposed change: use the existing scratch for only intersecting sectors;
  preserve read_block for complete aligned blocks. No cache, allocation or new
  persistent field. Keep full-block geometry validation before any sector I/O.
- Benefit: reduce small-read device transfers without weakening mount/check CRCs;
  no prediction of disk throughput or whole-OS speed.
- Risk: EOF, offset arithmetic, sector/block boundaries, borrow release, read-error
  schedule and full-block CPU regressions. Partial caller buffers on I/O error
  are not transactional; an unrequested sector's I/O failure is no longer probed.
- Benchmark: unchanged phase9_5_bench.py accepted B/current C, sequential B/C/B/C,
  three fresh guests per RAM size in each round; counted portable reads at fixed
  sizes and nine fixed 2,000-operation samples. Preserve every prototype result.
- Tests: exact byte/tail sentinels, EOF/usize::MAX, empty buffers, first/second
  sector failure, cross-sector/cross-block reads, command-owned FD cleanup,
  unchanged rights/shared offsets, crash suites, full ELF/ISO 128/512 acceptance.
- Decision: see results report; all-sector prototype rejected for full-block CPU cost.

### C02 — old-data reads for fully replaced write regions (P1, DEFERRED)

- Subsystem/source: `engine.rs`, change; scratch read of preserved old blocks
  before supplied bytes overwrite the scratch range.
- Evidence: source call path only. Existing 64-byte workload includes eight
  preservation reads on append; exact per-range read savings beyond that are
  not measured in this pass. Writes remain whole-extent COW by format contract.
- Hypothesis/change: skip old block reads only when every required preserved byte
  is replaced, retaining zero padding, full data writes and all barriers.
- Expected benefit: fewer device reads on large overwrite-inside-file workloads;
  workload frequency and latency gain unknown.
- Risk: high relative to read-only C01: preserved prefixes/tails, holes, truncation,
  CRC and fault-schedule changes. Do not alter write acknowledgement boundaries.
- Benchmark/tests: fixed binary partial overwrite and append traces; sector/read/
  write/flush counts separately; exact remount bytes and all crash-fault suites.
- Priority: after C01, only with a measured representative overwrite workload.

### C03 — volume-wide mount_info occupancy scan (P1, VERIFIED)

- Subsystem/source: `engine.rs:82`, mount_info and occupied; adapter diagnostics
  in `src/fs/rosti.rs`, mounted persistent_info.
- Evidence: completed B/C/B/C host measurements, 18 samples/state/geometry.
  Fragmented 128-block diagnostics: 27.500 -> 13.000 us (2.115x); maximum
  geometry: 16.660 ms -> 12.983 us. Empty work regression was RED at 15,488
  probes/128-block volume; the adopted sweep is metadata-bounded. Frequency and
  isolated guest time remain unknown; no boot/whole-OS gain is claimed.
- Hypothesis/change: count union of bounded validated extent intervals instead of
  querying occupancy for each data block; include reserved blocks exactly once.
- Expected benefit: bounded diagnostic computation independent of volume capacity;
  prefer no new resident cache or disk-size bitmap.
- Risk: double-counting cross-root overlaps or freeing retained extents in reports.
- Benchmark/tests: 128/1,024/65,536-block diagnostic fixture, empty/full/fragmented/
  cross-root/degraded volumes; differential exact counts against current scan;
  separately time mount validation and mount_info, never conflate them.
- Decision: accepted after three portable regressions, independent read-only
  review and PASS 38/38. No heap/cache/I/O/allocator/format change; +508 loaded B,
  no page-rounded static growth. Evidence: PHASE9_5_C03_RESULTS.md and
  test_results/phase9_5/c03_measurements.json, c03_review.json, c03_validation.json.
  Synthetic inventory models include overlap/clipping; public failed-remount
  stats transitions and widened-u32 oracle remain supplementary DEFERRED coverage.

### C04 — frame allocation rescans bitmap prefix (P1, DEFERRED)

- Subsystem/source: `src/memory/frame.rs`, allocate; existing isolated frame/map/
  heap timing fixture `tests_kernel/src/lib.rs:1001`.
- Evidence: source starts allocation scan at zero each call. Existing host fixture
  exposes 1,000-operation timings; it excludes privileged TLB behavior. No measured
  guest allocation bottleneck or new scan-counter distribution in this pass.
- Hypothesis/change: bounded word scans preserving lowest-address first-fit,
  retaining reservation precedence,
  growth ownership, exhaustion, exact live counters and double-free checks.
- Expected benefit: lower worst-case scans after many frames are allocated.
- Risk: high: growth reservations/module mappings are unresolved prerequisite
  B11; allocation speed must not make unsafe reserved frames eligible.
- Benchmark/tests: sparse/dense/exhausted bitmap scan counts, allocate/free/chunk edges;
  real paging, OOM/growth and CPU fault acceptance at both RAM sizes.
- Priority: defer optimization until reservation safety and instrumentation are addressed.

### C05 — allocator free-capacity loss on aligned cycles (P1 correctness, DEFERRED)

- Subsystem/source: `src/allocator.rs:246–265,292–303`; prior audit B09.
- Evidence: removed aligned prefix/tiny suffix is not recorded in the allocation
  header returned by deallocation. Source-grounded correctness finding, not a newly
  measured byte total in the persistent workload (which does not allocate FS heap).
- Hypothesis/change: reclaim the whole allocation span with explicit ownership;
  first establish exact free-capacity restoration RED tests, not used-only tests.
- Expected benefit: avoid unnecessary growth/OOM under adversarial valid alignment;
  no claimed average latency gain.
- Risk: high unsafe-header/layout/coalescing changes; do not mix with storage work.
- Benchmark/tests: small/medium mixed alignment cycles, tiny tails, near-capacity
  failures, fragmentation, header accounting, real growth/OOM. Track free, capacity,
  peak, waste and used independently.
- Priority: correctness before a future allocator performance change; unresolved here.

## Excluded approaches

- REJECTED: delete per-sector or transaction flushes; changes durable-success contract.
- DEFERRED: compiler opt-level/LTO/inlining/CPU tuning. No measured compiler bottleneck,
  and i686/soft-float/no-SIMD/Multiboot/diagnostic configuration remains unchanged.
- NOT APPLICABLE: scheduling/context switching, IPC, userspace syscalls, networking,
  GPU and RDP; these components are not implemented. No synthetic numbers assigned.

Stopping rule: evaluate the C01 experiment and its rejected prototype; do not begin
unmeasured high-risk C02–C05 just to reach three changes or a 1.2x target. Review
reports, actual timings and final acceptance decide whether C01 is retained.
