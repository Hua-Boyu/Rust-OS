# Rosti OS — standalone Phase 10 continuation prompt

## Readiness gate

**Phase 9.6 is COMPLETE / VERIFIED: PASS 47/47 source-frozen acceptance at
`test_results/phase9_6/acceptance_20261015T070148Z_tg2yx8i8/acceptance.json`,
final source checkpoint and evidence commits recorded in HANDOVER.md. This
Phase 10 prompt is authorized to execute.**

This file is prepared for a separately invoked continuation. Preparing it does
not implement or automatically start Phase 10.

## Mission

Implement bounded initramfs parsing, safe Multiboot module integration,
VFS-backed startup files, bounded mount management, read-only system-image
verification and an independent recovery environment. Prioritize safety,
correctness and explicit ownership over optimization. Do not introduce isolated
applications, user mode, syscalls, scheduling, networking or a GUI.

## Canonical repository and verified baseline

- Repository: `C:\Users\iamsv\Documents\Rust-OS`.
- Branch: `maintenance/phase9-5b`; verify actual branch, HEAD and status first.
- Phase 9.6 started at `17de9fd12d31e60f7f3dcaef726f4e579871d4dd`.
- B13 entry contract commit: `53e27fb5c71aff408ef13f4945ace1f4da64e69f`.
- B11 reservation policy commit: `f12d1ced9dd26e8ed60009e75c4814c3245f67f3`.
- Final Phase 9.6 source checkpoint, acceptance path, ISO and full hashes:
  **pending closeout; replace this line only from verified final evidence.**

Environment: Windows 11, native Git Bash, WSL2 GRUB tools, Rust nightly,
i686 bare-metal no_std/core+alloc, GRUB Multiboot v1, QEMU i386/SeaBIOS.
The previous campaign used Python 3.11.15 and rustc 1.101.0-nightly
(1d81eb4ad 2026-10-07); inspect actual tools rather than assuming versions.
Native programs need `C:/Users/iamsv/...` paths, not MSYS `/c/...` arguments.
Host Cargo must run outside the kernel tree to avoid custom-target build-std
configuration leaking into host tests.

Read AGENTS.md if present, HANDOVER.md, ARCHITECTURE.md, TESTING.md, BUGFIXES.md,
PROXMOX.md, README.md, crates/rostifs/FORMAT.md, docs/PHASE9_5_AUDIT.md,
docs/PHASE9_5C_RESULTS.md and docs/PHASE9_6_SAFETY_HARDENING.md. Load the Hermes
rosti-kernel-development, systematic-debugging, test-driven-development,
bare-metal-kernel-qemu-testing, requesting-code-review and git-release-checkpoint
skills. Inspect definitions/usages and actual manifests before changing APIs.

Preserve all historical accepted reports/ISOs. Do not reset a dirty tree,
remove existing tests or invent baseline results. Reverify any changed inputs
before treating the prior acceptance as evidence for a new candidate.

## Non-negotiable safety foundation

1. One competing-reservation denial policy applies to ordinary frames and growth.
   Partial-byte reservations win over usable coverage. Growth is exact-slot and
   contiguous; a blocked slot causes conservative failure, not address skipping.
2. Failed maps restore growth-only reservation/ownership and leave existing PTEs
   unchanged. Page tables never consume the growth-reserved pool.
3. `_start` clears DF, controls initial IF, installs the aligned 16 KiB stack and
   passes EAX/EBX through the documented C entry boundary. Preserve the Multiboot
   header and do not infer peak stack headroom from one function's prologue.
4. Use the checked bounded inventory; never restore raw BootInfo dereferences or
   assertions over bootloader pointers. Header/mmap conventional-RAM restrictions
   and trusted-loader backing assumptions remain explicit compatibility limits.
5. Accepted module/metadata spans and page-structure identity aliases remain
   pinned/mapped until reboot. Do not reclaim them as part of this phase. Module
   placements intersecting 8..14 MiB currently reject safely; do not weaken that
   policy merely to accept a larger image. Any relocation would require its own
   independently tested reservation/copy/rollback contract.
6. Preserve heap -> frame lock order. No allocation or backing destruction under
   FRAME_ALLOC; production paging preparation uses static errors and streaming
   validation. Keep borrowed-builder rollback slots cleared and reprepare denied.
7. Rejected boot metadata disables persistent storage probing/mount/raw writes.
   The bootstrap heap and RAMFS recovery shell remain independently available.
8. Do not retain static PageMap views across growth mutation. B19 and broader
   historical public-API/exception/stack findings are not blanket-resolved.
9. Preserve RostiFS wire format v1, 4 KiB blocks, metadata layout, COW, CRC32C,
   protected retained roots, transaction ordering, flush guarantees, capability
   access and existing shell interfaces. Keep all 9,071 modeled crash cases.
10. No claim of untrusted-userspace isolation, authenticated execution or physical
    power-loss proof follows from these boot and filesystem tests.

## Implementation requirements

### A. Retain sanitized modules and integrate lifetime safely

Trace `prepare_boot_memory`, inventory parsing, synthetic reservations and
PageMap pins first. Retain bounded owned sanitized module descriptors before
the local inventory Vec is dropped. Expose module bytes only through an
explicit bounded physical-span access contract after proving every page is
mapped and pinned. No unchecked public raw-pointer slice constructors.

A missing module must keep ordinary RAMFS boot usable. Define deterministic
module selection; reject ambiguity, duplicate names and malformed required
metadata. No archive/module content is executable. Accepted modules stay pinned
until reboot even after import or mount failure.

### B. Bounded archive parser

Use one documented uncompressed format (prefer cpio newc if no prior repository
format is specified). Freeze numeric limits before implementation: input bytes,
entries, name bytes, per-file bytes, total payload/metadata and nesting depth.
No decompression or recursive traversal is required in this milestone.

Validate header fields, ASCII-hex conversions, exact record boundaries,
alignment/padding, name terminators, checked arithmetic, trailer and complete
input consumption. Reject truncation, unsupported file kinds, duplicate paths,
absolute/escaping paths, dot/dotdot components, terminal controls, invalid names,
symlinks/hardlinks/devices and conflicting file/directory prefixes. Never allow
archive path traversal to alter an existing namespace. Keep parsing separate
from publication; fallible failure leaves RAMFS, mounts, descriptors and frame
ownership unchanged.

Build independent byte fixtures, not a parser encoder testing itself. Cover
zero/max/overflow endpoints, hostile records, collisions, padding/trailer,
allocation refusal and partial construction cleanup.

### C. Verified read-only system image

Create a deterministic host image builder under canonical project artifact
folders. Define exactly what a bounded manifest hashes and what the trusted
expected digest is. Pin the expected digest in a trusted build input or use a
separately justified signature/trust-root design; a digest supplied only by the
same untrusted image is not authentication. Do not call CRC32C cryptography.

Verify the complete selected image/manifest before exposing any system files.
Reject altered, missing, duplicate, oversized or unexpected entries. Keep all
system-image reads bounded and all writes denied at the backend as well as
through descriptors. No partially verified namespace may become visible.
Source-freeze discovery must include the image builder, manifest/trust inputs,
archive fixtures, feature/configuration inputs and any dependency locks.

### D. VFS-backed startup files and bounded mount management

Expose validated startup/configuration files through the VFS, not an ad hoc raw
module reader in shell commands. Use a bounded read-only `/system` mount and
ordinary writable RAMFS recovery/work areas unless repository conventions
require another layout. Do not automatically execute archive-supplied scripts
or arbitrary shell commands. Startup data must have bounded parsers/defaults.

Add only the mount-management API/diagnostics needed for this phase. Preserve
semantic path traversal, opaque generational identities, descriptor capability
attenuation, stale-handle rejection and existing `/mnt/rosti` behavior. Never
hide nonempty mountpoints or detach a filesystem referenced by cwd/open/duplicated
descriptors. Preserve conservative persistent-mount pinning unless a separately
tested lifetime design justifies changing it. Mount failure is transactional.

### E. Independent recovery

The kernel-owned RAMFS shell must boot when the module is absent, malformed,
corrupt, verification-rejected, too large or out of allocation capacity. Recovery
must not depend on files or code from the rejected system image. Keep boot
metadata rejection distinct from a safely rejected archive/system image after
valid metadata. Specify and test persistent-storage policy for each outcome;
never silently expose writes under rejected boot metadata.

Verify actual RAMFS create/read/delete, bounded OOM, keyboard/VGA, diagnostics
and continued prompt dispatch in each recovery class. Attach only newly-created
owned disposable local images; hash them before and after every refusal path
that promises no persistent mutation.

## Test-driven delivery and mandatory gates

For each vertical slice: deterministic RED, confirm the intended failure, minimal
GREEN, host regressions, sequential guest tests, unsafe/lock/Drop review and exact
resource-accounting checks. Do not remove inherited tests or replace privileged
mapping/CPU proof with host models. Commit focused verified changes conventionally.

Official acceptance remains `python -B scripts/phase6_verify.py` after inspecting
its current interface. Extend it fail-closed with invocation-owned complete
new host/guest evidence, not optional report discovery. Require ordinary ELF and
GRUB boots, 128/512 MiB, all inherited B11/B13/B18/B26 fixtures, page/fault/growth/
OOM tests, keyboard/VGA, RAMFS/VFS/capability descriptors, ATA and RostiFS
persistence, all crash models and corrupt-volume recovery. New initramfs/image/
mount/recovery fixtures must run through both boot paths at both RAM sizes.

Run long acceptance in a notified background terminal, freeze all source/build
inputs, and run no competing QEMU. Require final exit zero plus explicit full
PASS, nonempty all-true rows, exact required identities/counts, cleanup and final
rediscovered source hashes. Preserve failures and incomplete reports. Verify the
versioned ISO SHA256 and independently extracted `/boot/rosti.bin` against the
accepted production kernel. Never publish a fixture-feature kernel.

Measure static/loaded ELF sections, module pins, frame availability, heap retained
and transient budgets, real growth/OOM behavior and relevant stack estimates.
Record unknown high-water values honestly. Retain operation at both RAM sizes.

## Remote and repository safety

Proxmox node pve, VM 103 rosti-dev: 512 MiB, one vCPU, SeaBIOS/pc, Phase 7 ISO
on ide2 and no data disk. Read-only inspection is allowed, but no upload,
deployment, reset/restart/ISO change, disk attachment/format, storage-pool or host
partition change is authorized. Do not touch other VMs/services or physical disks.

No automatic push, tag, history rewrite, credentials, caches, raw disk images or
binary ISOs in commits. Preserve all accepted artifacts and rollback media.

## Required final deliverables

1. Starting/final HEAD, exact reviewed conventional commits and working-tree state.
2. Precise implementation/ownership/trust/limit contract, not just design proposals.
3. Independent RED/GREEN parser, lifetime, mount, verification and refusal tests.
4. Complete final acceptance counts, 128/512 MiB ELF/GRUB evidence and source freeze.
5. Versioned ISO SHA256 and independently extracted production-kernel SHA256.
6. Resource footprint/availability/growth/stack estimates and measured limitations.
7. Current read-only Proxmox inventory and explicit no-deployment statement.
8. Updated HANDOVER.md, NEXT_SESSION_PROMPT.md, ARCHITECTURE.md, TESTING.md,
   BUGFIXES.md, PROXMOX.md, README.md and a dedicated Phase 10 implementation report.
9. Remaining safety findings, independent review verdict and next continuation
   prompt. Do not start a later milestone automatically.
