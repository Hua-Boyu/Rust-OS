# Rosti OS — standalone Phase 9.5B maintenance continuation

You are a senior Rust bare-metal kernel engineer. Continue evidence-driven
Phase 9.5 maintenance only. **Do not begin Phase 10.** The previous Phase 10
prompt is retained in Git history, not current execution authority.

## Current standalone instructions

Canonical repository: `C:\Users\iamsv\Documents\Rust-OS`.
Branch: `maintenance/phase9-5b`. Starting Phase 9.5B HEAD:
`9792bd4cc2dbb04e1b64b2f623fcb3d0325439e7`. Recover the actual latest HEAD/status,
not this historical start. Read HANDOVER.md for the latest verified source commit
and artifact identities, and c03_validation.json for final release status.
Latest continuation started at `55cda2f38603a9f4c9078f0328344d69d9e8db44`.
Verified source checkpoint: `bea7e87e29b4c8b7fd0d6158ec1dd66d3ee11aca`.
Final local acceptance: test_results/phase9_5/acceptance_20261014T123644Z_106sujbb/
acceptance.json, PASS 38/38, 176 Rust and 47 Python tests; 84 source hashes and
52 nested reports independently verified. Accepted ISO:
dist/rosti_phase9_5_20261014T123644Z.iso, SHA256
c6c1f9381075320b864a4b4f9542c019879037da2d484764136db12a66e7267b.
Kernel SHA256 ba7b86f66c09e0dc7a7814df8ab82cdecfdba9314c0fc1cc19c34f6a1a5df0d0
matches the independently extracted ISO payload. Documentation commits may follow.
Windows 11/Git Bash/WSL2, nightly Rust, i686 no_std/core/alloc, GRUB Multiboot v1,
SeaBIOS/QEMU i386. Native tools require C:/ paths, not /c/ paths.

First run git status --short, git branch --show-current, git rev-parse HEAD,
git log --oneline -12, git diff --stat and git diff --check. Preserve existing
changes and all old accepted ISOs/reports. Never push, reset history or move tags.
Read AGENTS.md if present, HANDOVER.md, ARCHITECTURE.md, TESTING.md, BUGFIXES.md,
PROXMOX.md, README.md, crates/rostifs/FORMAT.md, docs/PHASE9_5_AUDIT.md,
docs/PHASE9_5_PERFORMANCE.md, docs/PHASE9_5_OPTIMIZATION_CANDIDATES.md and
docs/PHASE9_5_OPTIMIZATION_RESULTS.md. Load rosti-kernel-development,
systematic-debugging, test-driven-development, bare-metal-kernel-qemu-testing,
requesting-code-review and git-release-checkpoint; use the local skills catalog.

Prior Phase 9.5 acceptance: PASS 37/37, 169 Rust/45 Python, 82 matching source
inputs, 52 nested reports; independently rechecked at campaign start. Preserved ISO:
dist/rosti_phase9_5_20261013T221730Z.iso, SHA256
26e0407ad977bcb573bac03682a95512562f67b9481b58d88c6cdfe3548e84eb.
Phase 9 feature checkpoint: 4fb88fd062f3c667ee7682937752e94aa600cdc3.
Historical A/B paired reports stay immutable; do not credit earlier cat batching
as a new optimization. Current B/C reports and all timing samples are indexed in
test_results/phase9_5/optimization_baseline.json, optimization_results.json and
optimization_review.json. Reread actual status/hashes before relying on them.

C01 hybrid partial-read optimization uses intersecting sectors with existing
scratch; complete aligned blocks keep read_block. Mount/check whole-extent CRC,
format version 1, COW/delayed reuse/poisoning, every flush and capability/shared
offset behavior are retained. Counted 64-byte reads fall 8 -> 1 sectors; original
QEMU workload falls 16 -> 9 reads with 112 writes unchanged. Host RAM fixture is
about 3.8x faster for small reads; QEMU cat timing overlaps, so no end-to-end or
whole-OS speed claim. Full-block-only observed difference is below variability.
Static aligned span costs an extra 4 KiB, one reserved frame; FS static 28,240 B,
descriptors 2,328 B and retained heap 8,232 B are unchanged. Read prologue estimate
352 -> 500 B is not peak stack. No profile/LTO/CPU/Multiboot/linker change.

The all-sector prototype was rejected for full-block CPU cost. First full candidate
acceptance failed on an actual ELF128 append poll timeout; preserve that evidence,
bounded B/C reproductions and the reproduction-harness interruption. Do not infer
the failure unrelated merely because the write-path diff is empty. No timeout
budget or durability check was weakened. The final completed acceptance, not a
subset/retry/RUNNING report, determines release status in the current handover.

C03 occupancy diagnostics are now VERIFIED: clipped current/previous extent union,
no heap/cache/I/O or allocation/durability change. Host B/C/B/C 18 samples/case:
fragmented 128 blocks 27.500 -> 13.000 us; maximum geometry 16.660 ms -> 12.983 us.
Capacity-only fixture is not disk or guest timing. QEMU ranges overlap; the observed
create shift and every sample were retained. +508 loaded bytes, no page-rounded
growth; local prologue 92 -> 204 B is not peak stack. See PHASE9_5_C03_RESULTS.md
and c03_measurements.json/c03_review.json/c03_validation.json for current evidence;
optimization_*.json remain immutable C01 reports, not the latest release index.

The continued bounded pass is complete: C01 prototype/hybrid plus C03 were evaluated.
Do not automatically start a fourth implementation to pursue a score.
Next authorized campaign may assess C02 preservation reads, C04 frame scans and
C05 allocator free-capacity loss, or supplementary u32-boundary/public-remount stats
tests. Recover actual state and scope before starting; do not duplicate C01/C03.
Prioritize correctness tests for allocator/growth reservations before changing
unsafe memory paths. Do not optimize source-derived hypotheses without actual
call/byte/transfer measurements. The suite is explicitly partial: isolated guest
boot/mount/IRQ/TLB/ATA timings, open/dup/rights distributions and stack/heap peaks
remain DEFERRED. No scheduler, process, IPC, syscall, network, GPU or RDP benchmarks
apply. Do not start features simply to manufacture a benchmark.

Use one experiment at a time, at most three in a pass, an independent read-only
reviewer and identical baseline/candidate configuration/data/profile/repetitions.
Keep all samples/rejected variants, median/spread/count, correct speedup formula,
memory and ELF section trade-offs. No concurrent QEMU benchmarks or acceptance.
Host Cargo runs from C:/Users/iamsv, outside kernel cargo configuration:

```bash
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml -- --nocapture
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test host_tools
cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test read_performance
```

For explicit host read measurement append -- --ignored --nocapture to the final
command. From the repository, inspect canonical interfaces then run the unchanged
phase9_5_bench.py with a fresh --output and exact --iso; full acceptance is
python -B scripts/phase6_verify.py as a notified background job. Freeze source first;
38 gates and all inherited ELF/GRUB 128/512 RAMFS/ATA/RostiFS/OOM/CPU-fault reports
must pass, plus four portable read regressions. Independently rediscover source
hashes, nested report totals, ISO/ELF identities and owned-process cleanup.
Preserve the 9,071 modeled crash cases; no physical power-loss proof is implied.

Proxmox pve VM 103 rosti-dev remains running on Phase 7, 512 MiB/one core,
SeaBIOS/i440fx, only ide2 CD-ROM, no data disk. Read-only inventory is permitted.
No upload, reset/restart, VM/disk attachment, existing storage or physical-drive
modification is authorized. Do not run historical live tests; they reset the VM.
Unresolved B11/B13/B18/B26 block safe Phase 10 module integration; the other
safe-API/exception/lock/allocator findings remain real prerequisites. Current
trusted ring-0 capabilities are not user-mode isolation.

Finish only with real focused/full acceptance evidence, exact reviewed diffs,
conventional local commits of task-owned source/sanitized reports and updated
handover/standalone prompt. Exclude ISO/raw disks/caches/credentials. Classify
VERIFIED, IMPLEMENTED BUT UNVERIFIED, REJECTED, BLOCKED and DEFERRED explicitly.
