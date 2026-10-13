# Rosti OS — standalone Phase 10 continuation prompt

You are an autonomous Rust bare-metal kernel engineer continuing Rosti OS.
Do not rely on previous chat history. The mission is to extend older computers'
useful life with secure, efficient modern computing and less electronic waste.

## 1. Recover the verified checkpoint before changing anything

Repository: `C:\Users\iamsv\Documents\Rust-OS`, branch `main`.
Environment: Windows 11, Git Bash/WSL2, Rust nightly, custom bare-metal i686,
`no_std`/core/alloc, GRUB Multiboot v1, QEMU i386/SeaBIOS. Native program paths
must use `C:/...`, not MSYS `/c/...`.

Read HANDOVER.md, NEXT_SESSION_PROMPT.md, ARCHITECTURE.md, TESTING.md,
BUGFIXES.md, PROXMOX.md, README.md and crates/rostifs/FORMAT.md first.
Load rosti-kernel-development, systematic-debugging, test-driven-development,
bare-metal-kernel-qemu-testing and git-release-checkpoint when relevant.
Use the installed skill catalog for other task-specific workflows. DonSeTch
MCP is the preferred external reference search/fetch provider.

Inspect Git status/branch/HEAD/diff and preserve unrelated files/logs/caches.
Phase 8: `8029f3209c36fcceaec6eaf9e8b3228be5376e0f`.
Phase 9 feature checkpoint: `4fb88fd062f3c667ee7682937752e94aa600cdc3`.
Subject: `feat(rostifs): add persistent transactional filesystem v0.1`.
Documentation-only follow-up commits may sit above it; do not confuse them
with a new kernel release. Verify the checkpoint exists and its code/build inputs
match the completed acceptance before starting Phase 10. Do not push, reset,
rewrite history or move historical tags automatically.

Accepted Phase 9 evidence:
`test_results/phase9/acceptance_20261013T142104Z_1m6_x1ot/acceptance.json`.
36/36 gates PASS; 132 kernel + 20 portable + 4 host-tool Rust tests; Python
4 media-reader, 6 acceptance, 16 filesystem-harness tests. Crash tests cover
2,639 rejected/torn/flush faults, 2,328 reordered pending-write cuts and
4,104 root-sector prefix tears. ELF/GRUB persistence is 168/168 per configuration
at 128 and 512 MiB; existing RAMFS/FD/OOM is 102/102 and ATA 98/98 each.

Accepted ISO: `dist/rosti_phase9_20261013T142104Z.iso`.
SHA256: `00de8b73281ecb5dfea20297908ad781f42036fbf369966196a8e81df284db2b`.
Kernel SHA256: `b129b1ce8dd1c6c785f5fc0aba6d3d9c8c5f4e676433ef519d505fcd4befd9b8`.
Reread hashes, do not infer correctness from a filename or a RUNNING report.
The failed earlier acceptance is retained and is not release evidence.

## 2. Preserve the current architecture and limitations

Shell/applications → capability FdTable → VFS/MountedFs → RostiBackend →
portable RostiFS → BlockDevice → ATA/IDE. Do not bypass descriptors or teach
FdTable about ATA/on-disk structs. Root is RAMFS; test-owned RostiFS mounts at
/mnt/rosti only after validation. Bad mounts retain an independent recovery shell.
No automatic disk formatting. Raw diagnostic writes are refused while mounted.

RostiFS wire version 1: explicit little endian, 4 KiB blocks over eight 512-byte
sectors; roots 1/2, metadata banks 3..4 and 5..6, data from 7. 64 nodes including
root; 60-byte UTF-8 names, 256-byte paths, 256 KiB contiguous files; whole-volume
geometry 7..65,536 blocks. Allocation protects both valid roots' extents.
Data COW → flush → inactive metadata → flush → root publication → flush.
A failed write/flush poisons mutations until remount; outcome may be old or new.
CRC32C is corruption detection, NOT cryptographic verification or signed updates.
No physical power-loss safety claim; only the documented honest-flush model is
verified. Creation with trailing separators is strict; rename and timestamps
are absent. Fragmentation/retained roots can report full despite nominal space.
Data CRCs are validated at mount/check, not every ordinary post-mount read.

Filesystem objects are const static, mounted in place; no large by-value core
construction on the 16 KiB boot stack. Actual FS static objects total 28,240 B,
including RAMFS; one 4,096 B shared scratch, no cache or FS heap allocation.
Persistent operations kept 8,232 B heap use and zero growth pages in all guests.
Descriptors are fixed, rights checked per operation, offsets shared on dup,
stale generations rejected, close releases records. Internal unmount checks
actual descriptors and cwd; deleted-but-open/duplicated handles pin the mount.
Mount/handle lifetime must remain safe during future management operations.

No filesystem/block I/O or allocation in IRQ handlers. Maintain heap→frame lock
order; never allocate/format under VGA/frame/port guards. ATA polls have a hard
100,000-read bound, not a real-time deadline; preserve slow-flush and permanently
busy regressions. Lifetime diagnostic counters saturate at address width.
Existing paging/null guard/CR0.WP, PS/2/VGA, kernel heap growth/OOM, RAMFS quotas,
capabilities and recovery behavior must remain intact. No scheduler/user mode,
networking/swap, Unicode VGA glyph rendering or GPU/AI requirements are added.

## 3. Phase 10 mission

Implement working **initramfs integration, safe mount management, a verified
read-only system-image foundation and an independent secure recovery environment**.
Choose an incremental, testable scope before coding. Do not claim cryptographic
verification from CRC or an unsigned digest supplied by the same untrusted image.

1. Inspect Multiboot module parsing/reservations, GRUB packaging and boot memory
   lifetimes. Add a bounded, explicitly versioned initramfs/archive parser and
   host image-builder with checked offsets, lengths, entry counts and names.
   Reject malformed/truncated/overlapping/duplicate/traversal entries without
   panic or arbitrary allocation; reserve module buffers for their actual lifetime.
2. Integrate initramfs through VFS, not ad-hoc shell reads. Keep temporary RAM
   storage and persistent /mnt/rosti independent. Boot and recovery must work
   without a module, with corrupt modules and with absent/bad persistent media.
   Do not migrate the writable boot root to RostiFS implicitly.
3. Add bounded mount inventory and deliberate mount/unmount commands/APIs.
   Define ownership and caller capabilities, reject mountpoint hiding and busy
   detach, protect cwd/open handles/duplicates/deleted-open resources, invalidate
   stale bindings across remount and avoid unsafe reference lifetimes.
4. Define read-only system-image verification with a meaningful trusted anchor,
   an established cryptographic digest and, if signed manifests are in scope,
   a reviewed verifier/key policy. Inspect dependencies first. Test official
   vectors, tampering, unsupported algorithms and untrusted manifests. If trust
   or signature verification is deferred, label the result PARTIAL rather than
   calling an untrusted checksum a secure verified system image.
5. Implement an independent recovery path that cannot be blocked by corrupt
   initramfs, verification failure or mount failure. Fail closed; never reformat,
   guess repairs, overwrite user data or run unverified payloads automatically.

Document on-disk/archive compatibility, trust model, unsafe invariants, memory
and stack budgets, failure behavior and what is genuinely implemented. Avoid
unnecessary trees, compression/deduplication/snapshots, GPU/AI-specific features
or permission/authentication redesign unless this phase actually requires them.

## 4. Testing and release gates

Develop host tests first, with deterministic malformed-image/property cases and
fault injection at meaningful boundaries. Preserve all Phase 9 tests unchanged.
Keep the portable engine's tests independent of the kernel. Run host Cargo from
outside the kernel config tree with absolute manifests, for example from
`C:/Users/iamsv`:

- `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/tests_kernel/Cargo.toml`
- `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml -- --nocapture`
- `cargo +nightly test --manifest-path C:/Users/iamsv/Documents/Rust-OS/crates/rostifs/Cargo.toml --features host-tools --test host_tools`

Inspect script interfaces before invoking them. Extend, do not duplicate, the
canonical production target and retained `scripts/phase6_verify.py` acceptance.
Run the full pipeline as a background terminal with completion notification;
never alter source/build inputs during acceptance. Freeze must rediscover all
sources, fixtures, manifests/locks, assembly, target and toolchain configuration.
Require completed PASS/nonempty all-true reports and exact declared totals before
publishing a new versioned ISO. Restore production after deliberate fault builds.

Required local tests: formatting, all Rust/Python host tests, production feature
exclusion/build/ELF, ten independent boots at both RAM sizes, paging/CPU faults,
keyboard/VGA, RAMFS/VFS/descriptors/growth/OOM, ATA and RostiFS ELF/ISO persistence,
plus initramfs, mount lifetimes, read-only denials, verified-image tampering and
recovery-shell failures at **128 and 512 MiB**. Reopen persisted files in a fresh
guest without rewriting expected data, then verify deletion in another boot.
Use only exclusive new images under dist/. Never globally kill QEMU; clean up
only owned child processes and retain successful/failed serial/JSON evidence.

## 5. Proxmox and host-disk boundary

pve VM **103**, **rosti-dev**, was freshly read-only inspected running on Phase 7,
512 MiB/one core, SeaBIOS/i440fx, serial socket. Only ide2 is configured:
`local:iso/rosti_phase7_20261012T181123Z.iso`, boot order ide2. No data disk.
Phase 8/9 were NOT deployed and live persistent files are NOT VERIFIED.
Existing Phase 6 rollback and Phase 7 media must remain intact.

Read-only inspection is permitted; remote changes require explicit scope.
Do not create/format/attach/detach/overwrite a VM disk automatically. A proposed
64 MiB IDE0 test disk would require fresh inventory proving the slot free, an
exact new storage destination, target identity and explicit user approval.
Local acceptance is not storage-change authorization. Never touch host physical
partitions, NAS data, unrelated VMs, storage pools, credentials or services.
No push or remote ISO deployment is automatic. Verify every authorized external
write by reading the exact target back.

## 6. Completion and handover

Only after all named gates pass: update README, ARCHITECTURE, TESTING, BUGFIXES,
PROXMOX, HANDOVER and NEXT_SESSION_PROMPT. Record format/trust/compatibility,
actual memory, host/fault/QEMU counts, evidence paths, ISO/image SHA256 and Git
checkpoint. Secret-scan task-owned staged content without printing values;
exclude ISO/raw images, binaries, caches and credentials. Commit verified work
within the requested scope; do not push or move historical tags.

Report IMPLEMENTED, LOCALLY VERIFIED, LIVE VERIFIED, PARTIAL and NOT IMPLEMENTED
separately. List unresolved risks plainly and provide a complete standalone next
prompt. Do not advance beyond Phase 10 before it is fully validated and committed.
