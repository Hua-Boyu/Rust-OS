# Phase 9.5C — final bounded maintenance

## Scope and starting checkpoint

Started clean on `maintenance/phase9-5b` at
`2903eb00f74f05c5c174f7fcb6f661bdcdd896d9`, not at the older source commit
`bea7e87e29b4c8b7fd0d6158ec1dd66d3ee11aca`. The difference was documentation.
Historical acceptance was independently reread: PASS 38/38, 84 frozen inputs,
52 nested reports, and the supplied ISO SHA256 matches its actual bytes.
`PHASE9_5_C03_RESULTS.md` is located under `docs/`, not the root.
Git fsck returned zero with dangling objects; none were pruned.

Only C02 received a production optimization. C04/C05 received explicit host
investigation fixtures, not speculative allocator changes. C01/C03 were not
reimplemented. No Phase 10 feature, compiler/profile/CPU tuning, physical disk,
existing VM storage, Proxmox operation, push, tag or history rewrite occurred.
All old accepted artifacts and measurements remain historical evidence.

## C02: avoid reads whose complete live old contents are supplied

For each COW output block, bound the live old prefix by old length, new length
and block size. Skip its old-block read only if no old byte survives or the
supplied write covers that entire prefix. Preserve whole-block reads whenever
any old byte survives. This deliberately does not add a sector-wise preservation
algorithm, cache, buffer or unsafe operation. The existing zero scratch fill,
final padding, complete new extent CRC, metadata COW, retained-root allocation,
poisoning and data/metadata/root flush barriers remain intact. Mount/check still
validate complete extents for both roots. Write is not now a source-data integrity
scan: post-mount preservation reads never recomputed the old extent CRC.
An error on a fully replaced old block is intentionally no longer probed.

RED: the new full 8,193-byte overwrite budget observed 24 sector reads versus 0.
GREEN: three focused tests cover eight exact overwrite/append/hole cases, remount
CRC validation and data bytes; all 16 surviving read-failure positions, old RAM
and remounted content plus mutation poisoning; and truncate/reextension zeros.
The acceptance runner now requires all three tests. Two additional mocked runner
tests were RED before the new mandatory gate and GREEN afterward. No existing
test, crash model, timeout or expected guest check count was weakened.

Independent final read-only review passed with no security concerns or logic
errors; verified JSON is `test_results/phase9_5/c02_review.json`. Its optional
suggestion to assert transfer counts inside the ignored timing loop is deferred:
ordinary regressions enforce the budgets and every raw measurement records the
actual counters. No source was changed during acceptance to add supplementary
coverage. Static approval is not a substitute for the full release pipeline.

### Repeated unchanged host workload

Counted volatile RAM, Rust nightly host debug profile, 128 blocks, 8,193-byte
binary file, ten warm-up transactions, nine samples of 100 transactions per
batch. B1/C1/B2/C2 yields 18 samples per side per workload. Setup excluded;
CRC, allocation scans, metadata commit and fixture counters included. No physical
ATA/guest throughput or weighted OS score follows. All samples and spreads:
`test_results/phase9_5/c02_measurements.json`.

| Overwrite | Reads before -> after | Median before -> after (ms/op) | B/C ratio |
|---|---:|---:|---:|
| Full 8,193 bytes | 24 -> 0 | 1.444695 -> 1.469776 | 0.983 |
| First 4,096 bytes | 24 -> 16 | 1.714591 -> 1.542253 | 1.112 |
| Offset 1, 8,192 bytes | 24 -> 8 | 2.001742 -> 1.467205 | 1.364 |
| Offset 4,095, 2 bytes | 24 -> 24 | 2.294066 -> 1.470824 | 1.560 |

Every transaction retains 48 sector writes and three flushes. Timings are noisy:
the unchanged-transfer control also improves, while full overwrite has a slightly
slower median. Do not causally attribute these timing differences or claim a 1.2x
latency gain. The deterministic benefit is avoiding 8/16/24 reads (and their
old-data transfers) on covered ranges, with a small, readable condition.
No extra caller copy is introduced; saved read blocks are 4,096 bytes each.
Copy/zero CPU instructions and transient peak memory were not separately profiled.
Reciprocal median host transaction rates (not ATA bandwidth) are: full overwrite
692.19 -> 680.38/s, first block 583.23 -> 648.40/s, unaligned 499.57 -> 681.57/s,
and unchanged-transfer partial control 435.91 -> 679.89/s. These are derived from
the same noisy latency samples, not an independent throughput experiment.

### Guest regression replay and space

Sequential original benchmark B then C: three fresh GRUB guests per RAM size per
checkpoint, twelve guests total. Both reports PASS. Every replay retains nine
sector reads, 112 writes, 61,952 transferred bytes; this original replace/append
workload does not exercise C02's full old-block coverage savings. Retained heap is
8,232 bytes, capacity 1 MiB, zero growth pages, three console slots and no file
records after cleanup. These are retained values, not runtime peaks.

| Host-observed median | B 128 | C 128 | B 512 | C 512 |
|---|---:|---:|---:|---:|
| Start to prompt (ms) | 1188.199 | 1215.836 | 1780.238 | 1338.618 |
| Read Enter-to-prompt (ms) | 68.995 | 69.257 | 68.592 | 67.523 |
| Write Enter-to-prompt (ms) | 134.032 | 91.551 | 124.152 | 89.308 |

All operation observations, including regressions, are retained in
`c02_qemu_B.json` and `c02_qemu_C.json`. Input pacing, polling, firmware/QMP and
host scheduling are included. This is a regression replay, not a causal guest
speed claim; no second guest round was used to chase favorable latency.

Both ISO payloads were independently extracted read-only. ELF bytes
5,153,472 -> 5,153,592 (+120 nonresident-inclusive bytes); text +16, data -16,
rodata/BSS unchanged. Allocated sections remain 1,880,767 bytes; initialized
allocated bytes 742,659; static address span 1,891,772. No added reserved frame,
resident buffer or filesystem/descriptor storage. `c02_space.json` retains exact
section/symbol identities. Peak heap/stack, IRQ/caller stack and isolated guest
CPU, ATA latency and throughput remain unmeasured.

## C04 / C05: measured, production changes DEFERRED

`tests_kernel/src/maintenance_measurements.rs` has two explicit ignored probes;
invoke each exact fully qualified name separately, never all ignored timings in
parallel. `c04_c05_investigation.json` retains samples and observations.

C04: nine samples of 100 allocate/free pairs for sparse versus 1,000 held frames,
and 100 failed allocations after exhaustion. Host medians: 114 ns sparse,
5,170 ns dense, 321,786 ns exhausted. Includes host assertions/free and does not
execute paging/TLB hardware. Source still scans 65,536 frame bits on exhaustion.
A word traversal or correctly reset lowest-free hint could help; defer production
optimization until B11 reservation precedence and mixed allocate/free/chunk-edge
oracle tests are established. No candidate speedup is claimed.

C05: one exact 4 KiB isolated heap cycle per case. Eight-byte payload aligned to
16 leaves free capacity 4,096 -> 4,088; 4,081-byte payload leaves 4,096 -> 4,089.
Both return used/live allocations to zero. The second loss is not in the waste
counter. This confirms B09, not a successful reclamation fix. Probes deliberately
do not require known loss as a permanent contract. A later change needs RED exact
restoration tests for prefixes/tiny tails, whole-span ownership, mixed alignments,
coalescing, failed allocations, growth reservations and real guest OOM rollback.
No unsafe header or reclamation redesign was attempted in this bounded pass.

## Phase 10 readiness: BLOCKED

- **B11:** growth claims still use usable coverage/prior claim state, not a separate
  competing-reservation eligibility map. Any overlapping boot/module/nonusable
  byte must deny the whole frame. Live modules in the growth window also lack
  boot identity mapping; eligibility alone cannot close B11.
- **B13:** boot entry still lacks explicit CLD/IRQ-state and 16-byte pre-call stack
  alignment setup. Add incoming ESP/DF and DF-set handoff fixtures for ELF/GRUB,
  verify generated call ABI and argument order before changing startup.
- **B18:** boot metadata still crosses assert/raw-span boundaries without a bounded
  fallible inventory. Design checked module/mmap counts/ranges and pinned mappings;
  test malformed/truncated inventories and recovery without executing module bytes.
- **B26:** error Vec allocation in `memory::prepare` still occurs under frame guard.
  Moving just that Vec is incomplete: `build_identity_map` consumes its tables Vec
  and drops it on failure under the same guard, acquiring the global heap lock.
  Return/reuse caller-owned backing across failure, release the frame guard before
  heap destruction/error construction, then instrument forced table exhaustion
  with a guard-held heap-operation detector and guest low-memory recovery tests.

These are prerequisites, not permission to begin Phase 10. Address them in a
separate bounded boot-memory correctness campaign, independently review, then
rerun official acceptance plus new module/fault/recovery fixtures. Broader B10,
B12, B14-B16, B19-B20 and allocator B09 remain before untrusted execution. The
previous intermittent ATA append poll timeout remains unresolved; no ATA fix or
physical power-loss proof is claimed.

## Final acceptance and local checkpoint

Official notified background acceptance completed with exit 0, **PASS 39/39**:
`test_results/phase9_5/acceptance_20261014T142055Z_qg7d7qid/acceptance.json`.
Independent readback validates all 86 frozen inputs after both source commits,
52 nested PASS reports, exact mandatory matrix totals and ten successful boots
at each RAM size. Rust: 145 kernel + 23 core + 4 tools + 4 reads + 3 writes =
179. Python: 4 media + 15 runner + 16 RostiFS + 14 benchmark = 49. Crash logs
retain 2,639 rejected/torn/flush + 2,328 reordered + 4,104 root-prefix cases =
9,071, not physical power-loss proof.

ELF/GRUB at 128/512 MiB passed paging/faults, RAMFS/VFS/capability descriptors,
growth/OOM, ATA/RostiFS persistence, corruption and independent recovery shell.
Mandatory matrix remains 102 RAMFS, 98 ATA and 168 RostiFS checks in each of four
configurations (1,472 distinct checks). All four final owned-image hashes were
independently reread. Final task-list inspection found no QEMU i386 process.

Accepted ISO: `dist/rosti_phase9_5_20261014T142055Z.iso`, 10,276,864 bytes
(same size as the starting accepted ISO).
SHA256: `5294625001799bfb5bdac7d6c01d95f7332b1e0255dc65927a1aff2c900e3331`.
Kernel SHA256: `0a5046e9d05d3642cc5876335372d298ba1bc703064774d8f0e3e972072c3248`.
Read-only independent extraction of `/boot/rosti.bin` matches the production ELF.
Four historical C03-indexed ISO identities were reread and remain unchanged.

Local verified commits:
- `825cb89c16272720615116f54ede05783b322fad`: C02 plus regressions/mandatory gate.
- `8f9082382cbdf442096e91a06c9903397b04d2e2`: ignored C04/C05 host probes;
  this is the complete accepted source checkpoint. Documentation/evidence follows.

Task diff/security scan and staged whitespace checks passed. No rejected production
prototype was left behind; sector-wise C02 preservation and unsafe allocator
changes were not attempted. C02 is accepted for deterministic transfer savings,
not an asserted latency speedup. Temporary detached baseline worktree and its
build outputs were removed; all measurements, failures and accepted media remain
under canonical test_results/dist. No push/tag/deployment or Phase 10 work.
Final independent release index: `test_results/phase9_5/c02_validation.json`.
