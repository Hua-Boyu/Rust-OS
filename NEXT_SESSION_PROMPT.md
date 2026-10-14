# Rosti OS — next session after completed Phase 9.5C

The final bounded maintenance pass is complete. Recover its checkpoint; do not
start Phase 10 or another optimization campaign automatically. Ask for fresh
scope before implementing boot-memory prerequisites or further allocator work.

Repository: `C:\Users\iamsv\Documents\Rust-OS`.
Branch: `maintenance/phase9-5b`.
Campaign starting HEAD: `2903eb00f74f05c5c174f7fcb6f661bdcdd896d9`.
Accepted source checkpoint: `8f9082382cbdf442096e91a06c9903397b04d2e2`.
C02 source/gate commit: `825cb89c16272720615116f54ede05783b322fad`.
Later documentation/evidence commits may follow. Verify actual HEAD/status.

Read HANDOVER.md, docs/PHASE9_5C_RESULTS.md,
docs/PHASE9_5_AUDIT.md, TESTING.md and ARCHITECTURE.md. Load
rosti-kernel-development and git-release-checkpoint; use the local skills catalog
for debugging/testing/review skills when authorized work needs them.
Run git status --short, git branch --show-current, git rev-parse HEAD,
git log -5 --oneline and git diff --check. Preserve unrelated work and evidence.

Latest official local acceptance:
`test_results/phase9_5/acceptance_20261014T142055Z_qg7d7qid/acceptance.json`.
PASS 39/39, 179 Rust, 49 Python; all 9,071 modeled crash cases. All 86 source
inputs and 52 nested reports independently checked after source commits. The
128/512 MiB ELF/GRUB paging/fault/memory/OOM/capability/VFS/ATA/RostiFS and
corruption/recovery-shell gates passed. Release index:
`test_results/phase9_5/c02_validation.json`.
Accepted ISO: `dist/rosti_phase9_5_20261014T142055Z.iso`.
SHA256: `5294625001799bfb5bdac7d6c01d95f7332b1e0255dc65927a1aff2c900e3331`.
Kernel SHA256: `0a5046e9d05d3642cc5876335372d298ba1bc703064774d8f0e3e972072c3248`;
independent /boot/rosti.bin extraction matches. Historical media survive.

C02 skips old-block reads only when every live old byte is supplied by the write.
Host B/C/B/C: 18 samples per workload/side; full/first-block/unaligned reads
24 -> 0/16/8, writes 48 and flushes three unchanged. Host latency is mixed;
no overall speedup claim. Guest replay is three samples/RAM/checkpoint, original
small-file workload, transfers unchanged. ELF +120 B, resident total/static span
unchanged, retained heap 8,232 B/capacity 1 MiB/zero growth pages. Peak memory and
isolated guest/IRQ/ATA timing are unmeasured. C01/C03 were not repeated.
Independent read-only review passed. Exact samples and scope: c02_measurements.json,
c02_space.json, c02_review.json, c02_qemu_B.json and c02_qemu_C.json.

C04/C05: measured, production changes deferred. Explicit ignored host probes
reproduce sparse/dense/exhausted frame scan costs and 8-byte alignment-prefix /
7-byte tiny-tail capacity loss. No unsafe reclamation or frame hint was adopted.
Do not assert used returning to baseline proves capacity restoration. Add RED
exact restoration tests before any future ownership/header change.

Phase 10 is BLOCKED, not ready. A separately authorized correctness campaign must:
- B11: exclude every competing reservation/one-byte overlap from growth claims,
  and establish live module mappings/lifetimes inside/outside the growth window.
- B13: establish IRQ/DF/stack entry ABI with incoming ESP/DF-set handoff fixtures,
  argument-order/assembly checks and ELF/GRUB testing.
- B18: introduce a bounded fallible boot inventory, checked module/mmap spans and
  pinned mappings; require malformed/truncated metadata recovery fixtures.
- B26: eliminate ALL heap operations while frame guard lives. The consumed tables
  Vec also drops inside build_identity_map failure; moving prepare's error Vec
  alone is insufficient. Test forced table exhaustion with a guard-held heap
  detector and guest low-memory recovery.
Resolve broader safe-API/exception/allocator findings before untrusted execution.
The older intermittent ATA append poll timeout remains unresolved; do not weaken
poll bounds or infer it fixed from successful retries. CRC is not cryptography
and modeled crash success is not physical power-loss proof.

Host cargo runs from C:/Users/iamsv with absolute manifests, outside kernel config.
If fresh acceptance is needed, use `python -B scripts/phase6_verify.py` from the
repository as a notified background job. Freeze source; never run competing QEMU.
Require complete PASS and independently recheck source/report/artifact identities.

Preserve i686, 128/512 MiB, capabilities, wire format v1, all checksums/COW/flushes,
crash recovery and independent RAMFS shell. Only new test-owned dist images.
Never modify physical disks, existing VM storage or Proxmox VM 103; no deployment,
restart/reset, upload, push, tag or history rewrite is authorized. Do not implement
scheduler/userspace/network/GUI features or start Phase 10 without fresh scope.
Stop after checkpoint recovery unless the user explicitly authorizes more work.
