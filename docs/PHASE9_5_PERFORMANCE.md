# Phase 9.5 performance evidence

## Baseline and measurement scope

Before production edits, all 80 Phase 9 inputs and accepted ELF/ISO hashes matched. `test_results/phase9_5/baseline.json` is PASS with three independent GRUB/QEMU executions per RAM size. Baseline uses the accepted Phase 9 ISO; one i440fx/pc virtual CPU, SeaBIOS, ATA raw test-owned images with writeback cache, no parallel QEMU. Formatter creates exclusive new images; timing begins after formatting. No physical disks. Rust nightly 1.101.0 (2026-10-07), QEMU 10.2.0.

Clock: host `time.perf_counter_ns`, not guest PIT/TSC cycles. Boot is host start-to-mounted-shell-prompt (includes firmware, emulation startup, QMP connection and serial polling); mount-only latency is unavailable. Command timings start before the Enter QMP request and stop at the next observed prompt, including 65 ms key pacing and 20 ms serial polling. Typed input is excluded from these dispatch observations, but full command observations also exist. No emulator timing is a physical hardware guarantee.

## Kernel payload versus packaging

| Metric | Phase 9 baseline | Final Phase 9.5 |
|---|---:|---:|
| Kernel ELF file bytes | 5,146,096 | 5,148,792 |
| .text | 606,929 | 608,449 |
| .rodata | 39,126 | 39,126 |
| .data | 92,112 | 92,176 |
| .bss | 1,138,108 | 1,138,108 |
| Allocated section bytes | 1,876,483 | 1,878,067 |
| Static address span (includes alignment) | 1,887,676 | 1,887,676 |
| Initialized allocated section bytes | 738,375 | 739,959 |
| GRUB ISO bytes | 10,268,672 | 10,272,768 |

Allocated sections exclude debug/symbol tables; static address span includes linker alignment. BSS includes the 1 MiB bootstrap heap and 16 KiB boot stack: do not add them twice. ELF file bytes include nonloaded DWARF/symbols, whereas ISO also contains GRUB and padding.

## Memory

Baseline actual i686 symbols: filesystem namespace 6,940 B + core/adapter 21,300 B = 28,240 B; scratch 4,096 B included, cache zero. Descriptor table 2,328 B separate. FRAME_ALLOC mutex/object is 32,804 B. Boot stack reservation 16,384 B, not measured high-water. Six mounted guest workloads each retain heap 8,232 B, capacity 1,048,576 B, growth pages zero, failed allocations zero, five opens/five closes and only three console slots afterward. No measured peak transient allocation counter exists. Fixed metadata resident footprint is not per-mount heap overhead. No mount/traversal/file-sized FS heap buffer is introduced.

## Baseline filesystem observations

Fixed workload: cd mount, create sample, replace with 64 ASCII bytes, cat exact data, append four bytes, list, delete. Entire workload ATA reads 520 / writes 112 / bytes 323,584 in every run. Mount traffic is excluded from this delta. Ordinary disk diagnostics do not read a sector. Flush command count is not exposed. Driver flushes each sector, core flushes data/metadata/root barriers; this ordering is unchanged.

| Host observation median (ms) | 128 MiB baseline | 512 MiB baseline |
|---|---:|---:|
| Start to mounted prompt | 1006.272 | 1105.275 |
| traverse Enter-to-prompt | 67.651 | 68.134 |
| create Enter-to-prompt | 112.035 | 111.498 |
| write Enter-to-prompt | 111.230 | 126.376 |
| read Enter-to-prompt | 191.935 | 193.446 |
| append Enter-to-prompt | 123.419 | 125.348 |
| list Enter-to-prompt | 68.537 | 68.603 |
| delete Enter-to-prompt | 91.017 | 109.008 |

These tiny-file end-to-end observations are NOT isolated filesystem throughput. Sustained read/write bandwidth, CPU-only parsing/dispatch/formatting time, per-operation guest cycles, mount-only latency, page-allocation peaks and stack high-water remain **unavailable**. It would be misleading to divide 64 bytes by paced command latency and call that disk bandwidth. IRQ instrumentation or an invasive profiling framework is not justified for this localized change.

## Build configuration study

Current target already uses panic=abort, no redzone, soft-float/no SIMD. Multiboot section is explicitly KEEP-ed in linker.ld; existing Cargo/rust-lld linker garbage collection retains the required header. Existing debug-friendly development profile remains canonical. No opt-level/LTO/stripping/inline/GRUB-loader change was adopted; therefore no compiler-option speedup is claimed. Removing symbols would shrink the file, not necessarily loadable payload or RAM. Optimized profiles require separate controlled comparisons, stack analysis and complete privileged acceptance; assembly is not presumed faster. Serial diagnostics/page-fault reporting are preserved.

## Reproduce

From canonical repository, sequentially (choose a new output filename; existing evidence is refused):

```bash
python -B scripts/test_phase9_5_bench.py
python -B scripts/phase9_5_bench.py --output test_results/phase9_5/new_baseline.json --iso dist/rosti_phase9_20261013T142104Z.iso
python -B scripts/phase6_verify.py
```

Never overlap the benchmark with acceptance or another QEMU harness. Do not change source/build inputs during acceptance. Initial probe used empty-output equality for commands that return `ok`; its honest failed report is retained as baseline_probe_failed.json and the corrected six-run baseline is the measurement evidence.

## Final comparison

The corrected `after_review.json` is PASS across six independent GRUB guests,
with cleanup and unchanged ELF/ISO hashes checked before aggregate PASS.
Workload is unchanged. Every run uses **16 reads / 112 writes / 65,536 transfer
bytes**, versus **520 / 112 / 323,584** before. ATA read reduction is **96.923%**
for this specific workload, not a general throughput percentage. The real
portable-core counting test separately measures cat alone at **512 -> 8**
sector reads for 64 ASCII bytes. No flush barrier was removed.

Heap/static filesystem/descriptor budgets remain unchanged. The local cat
buffer grows 4 -> 128 B; actual debug i686 prologue push/sub estimate grows
**316 -> 560 B (+244)**. Evidence: cat_stack_baseline.txt/cat_stack_after.txt.
This excludes callers, interrupts and dynamic paths: it is NOT peak stack.
The 16 KiB reservation is unchanged; privileged stack acceptance remains needed.

Binary cost is explicit: **ELF +2,696 B, text +1,520 B, data +64 B**, no rodata
or BSS increase. Named data-symbol sizes are unchanged (data_symbol_diff.json);
the data-section delta is compiler/linker-emitted non-owner storage, not new FS
or descriptor tables. Static address span is unchanged because alignment slack
absorbs the small section growth. ISO packaging increases one 4,096-byte unit.
These costs buy tested FD edge correctness and reduced block traffic; there is
no claimed code-size improvement.

Host timing variability must not be hidden. The first replay (`after.json`)
observed start-to-mounted-prompt medians 963.531 / 1170.303 ms at 128/512 MiB;
the corrected replay (`after_review.json`) observed 1788.326 / 1425.663 ms,
versus baseline 1006.272 / 1105.275 ms. The latter is a measured regression in
host elapsed observation, **not attributed** to kernel execution. Different
replay observations on identical kernel payload are not a boot-speed result.
No physical hardware claim and no statistical attribution from three samples.

The corrected replay's Enter-to-prompt cat medians are 68.986 / 68.401 ms,
versus 191.935 / 193.446 ms before. Input pacing/polling still dominate the new
observations; sector-transfer counts are the stronger causal evidence.

### Final sequential same-host replay

After acceptance completed, `paired_phase9.json` and `paired_phase9_5.json`
each passed six independent guests with the finalized harness, fresh images,
verified cleanup and artifact freeze. The old/new ISO payloads were independently
extracted and checked against their recorded kernel hashes; ISO-mode local ELF
metrics alone are not a payload-identity check. Summaries below are medians in
milliseconds, include host/QMP/pacing overhead and are not isolated guest timing.

| Observation | Old 128 | New 128 | Old 512 | New 512 |
|---|---:|---:|---:|---:|
| Start to mounted prompt | 1046.675 | 1033.911 | 1154.715 | 1240.394 |
| Traverse Enter-to-prompt | 67.369 | 67.339 | 68.267 | 67.432 |
| Create | 73.628 | 67.748 | 90.961 | 67.712 |
| Write | 90.425 | 89.608 | 90.475 | 89.737 |
| Read/cat | 122.676 | 67.968 | 116.855 | 67.390 |
| Append | 104.525 | 89.564 | 90.327 | 90.683 |
| List | 67.983 | 67.860 | 69.048 | 67.506 |
| Delete | 67.357 | 67.553 | 67.691 | 68.229 |

Every old run still uses 520 reads/112 writes and every new run 16/112; heap
8,232 B/capacity 1,048,576 B/growth zero in both. The 512 MiB boot observation
is **7.420% slower**, while 128 is 1.219% faster. Small append/delete/traversal
observation increases are disclosed in the table. Timing attribution remains
unestablished; no boot optimization was adopted and no overall speed claim is
made from these samples. I/O-count improvement remains deterministic.

Acceptance **37/37 PASS**, 82 source inputs unchanged, 52 nested reports valid;
no owned QEMU remains. Final ISO `rosti_phase9_5_20261013T221730Z.iso`, SHA256
`26e0407ad977bcb573bac03682a95512562f67b9481b58d88c6cdfe3548e84eb`;
kernel `7c6a8097fafcea4fb95e3297d019e92363bb763790f1a54213c897abf083e5ea`.
All machine-readable before/after distributions and limitations remain available;
isolated bandwidth/guest cycles/peak stack/peak transient allocations stay null.
