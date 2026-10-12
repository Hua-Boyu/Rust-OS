# Rosti OS — Phase 7 verified handover

## Checkpoint

Canonical repository: `C:\Users\iamsv\Documents\Rust-OS`, branch `main`.
Phase 7 completion commit subject: `feat(vfs): add capability-aware file descriptors and generational handles`. Resolve the actual hash with `git log -1 --format='%h %s' --grep='feat(vfs): add capability-aware'`; the document cannot embed its own containing commit hash.
Phase 6 is committed as `5495a3e feat(fs): implement Phase 6 RAM filesystem and VFS` (plus `124496b` sync); Phase 5 is `4ed27fb`. Historic tag `v0.1.0` was not moved. No automatic push is authorized or performed.

Windows 11/Git Bash, Rust nightly, bare-metal i686 no_std/core+alloc, QEMU,
WSL GRUB/SeaBIOS. Native program paths use `C:/...`, not MSYS `/c/...`.
Host cargo tests run outside the kernel cargo-config tree (`scripts/run_tests.sh`).

## Phase 6 checkpoint status

Phase 6 was recovered and confirmed committed before Phase 7 work began; its
source, docs and evidence (`test_results/phase6/`) were left intact and its
deployed ISO (`rosti_phase6_20261012T152259Z.iso`, SHA256
`8b3a4d4dbb0f245a2b969e3aed7d973cdf46a2b6e5da07f0a189da23c44472cb`) was not
redeployed — it remains the rollback media on VM 103 storage. All Phase 6
functionality (RamFs, VFS, path rules, quotas, stress, shell commands) was
preserved; Phase 7 only rerouted shell file commands through the descriptor
layer and added `fdlist` plus `mem` descriptor counters.

## Phase 7 implemented and tested

`src/fd.rs` — static, allocation-free kernel object subsystem:
- Unix-style numeric descriptors; 0/1/2 reserved for console input/output at
  boot with rights 0 (default-deny until wired to real console operations).
- Generational internal handles (slot + generation), never kernel pointers.
  Stale handles fail after slot reuse; exhausted generations retire, never
  wrap (no ABA aliasing). Double close rejected.
- Separate open-file descriptions: shared offset and refcount live there, so
  duplicated descriptors share the offset. A descriptor is not the node.
- 8-bit capability rights (READ, WRITE, SEEK, STAT, DIRECTORY_READ, CREATE,
  DELETE, MAP reserved). Default-deny; duplication attenuates only; escalation
  rejected; every operation validates rights at call time.
- Reference-counted open resources; last close releases the record and bumps
  its generation. Generation-checked node binding through the VFS: deleting an
  open file makes its descriptor fail cleanly, never dangle.
- ResourceKind: File, Directory, ConsoleInput, ConsoleOutput; Pipe/Socket/Device
  reserved. No dynamic dispatch, no allocation on any fd path.
- Fixed tables: 64 descriptor slots + 64 open records; asserted budget slot
  ≤16 B, record ≤24 B → ≤2,560 B fixed overhead plus counters (smaller on
  i686). Exhaustion returns `TableFull` without touching filesystem metadata.
- Lock order: descriptor table → VFS; no fd path allocates, so the heap →
  frame order is never crossed. ISRs must not touch this subsystem.
- `FdStats` counters printed by `mem`; `fdlist` lists fd, type, rights,
  offset, refs. Shell file commands dispatch Shell → Descriptor API → VFS →
  RAMFS; existing command semantics preserved.
- Denied writes do not advance the shared offset (defined semantics).
- Rights are capabilities, not isolation: the kernel still shares one
  privileged address space. No user mode, no scheduler, single main-loop
  execution.

## Acceptance

Kernel/host fmt and production build PASS; 93/93 Rust host tests (15 new
descriptor tests covering allocation, reuse, generation validation, stale
handles, invalid indexes, double close, exhaustion, open/close, read/write
offsets, seek boundaries, EOF, shared offsets, refcounts, read-only
restrictions, attenuation, escalation rejection, deletion while open,
directory type rules, offset overflow, OOM handling, leak-free cycles, static
budget); 4/4 Python reader tests; ELF 8/8; boot 10/10 each at 128/512 MiB;
paging 20/20; CPU-fault fixtures 4/4; keyboard all stages; VGA editing 13/13
ELF and 13/13 ISO. Filesystem + descriptor integration 102/102 each on ELF
and ISO at both RAM configurations (38 commands). GRUB boot and ISO paging
2/2. Local pipeline 21/21 gates.

Live VM 103: 38 commands, 104/104 checks, including descriptor dispatch proof
(`mem` counters: opens 12, closes 12, denials 0, stale 0, records 0, open
slots 3 = reserved console only) and `fdlist` showing fd 0 console-in,
fd 1/2 console-out. Full stress re-verified live: 4 MiB data integrity, heap
1,048,576 → 7,340,032 bytes, 1,536 growth pages, four intentional OOMs,
cleanup to 8,232-byte baseline.

Acceptance evidence: `test_results/phase7/acceptance_20261012T181123Z_ovwvkk1g/acceptance.json` (deployed ISO run) and `test_results/phase7/acceptance_20261012T231050Z_afsptz17/acceptance.json` (final re-run against the exact committed source; comment-only delta in src/fd.rs);
live evidence: `test_results/phase7/live_vm103/` (report.json, serial.txt).
Two test expectations were corrected to defined semantics before code changes
(denied-write offset; `touch` does not open a descriptor); no existing
assertion was weakened to obtain a pass.

## VM 103 and rollback

Node pve, 192.168.50.205, rosti-dev, 1 vCPU/512 MiB, SeaBIOS/i440fx, serial
socket. Running ISO `rosti_phase7_20261012T181123Z.iso`, SHA256
`4c1e337d1362d827248ad0e3ee13f8c67bb29cdff3a1a460d1cd1d5e97b62bb4`
(local == remote, verified on pve). Attached to ide2 only; QMP media, final
config and status read back; VM left running at a clean prompt. Key-auth SSH
alias `proxmox` verified before use; no credentials read or copied.

Rollback media remains the verified Phase 6 ISO
`local:iso/rosti_phase6_20261012T152259Z.iso` (SHA256 as above); local copy
`dist/rosti_preserved_8b3a4d4dbb0f245a.iso`. Earlier rollback ISOs untouched.

Live media check note: the harness compares the exact QMP file leaf; pass the
full runtime path as `--expected-iso` (bare filename fails by design; retained
as regression fixture).

## Reproduction and safe boundaries

```bash
cargo fmt --check
cargo +nightly fmt --manifest-path tests_kernel/Cargo.toml --check
bash scripts/run_tests.sh
python -B scripts/phase6_verify.py   # retained filename; reports phase 7
python -B scripts/test_fs_harness.py
```
Read the acceptance runner before deployment. Do not change source while it
is running or run another QEMU beside boot_test.py's orphan check. Always
rebuild production after deliberate fault features; never deploy those builds.
For live tests, copy scripts to a unique pve temporary directory, check exact
QMP media, capture serial before reset, verify metadata/data and paging, then
retrieve evidence and reread checksum/config/status. Only VM 103 is authorized.
No host reboot, packages, networking/storage changes or unrelated VMs.

Historical Phase 4/5 evidence was removed by sync commit f93d7e4; inspect with
`git show 4ed27fb:<path>`. The external `.gitignore` change is preserved. Task
evidence was staged explicitly despite the test_results ignore rule.

## Remaining limits and next milestone

RAM-only files; single main-loop execution; no scheduler/user mode/networking.
Descriptor rights are capabilities within one privileged address space, not
isolation. Long output/stress can delay shell processing. Kernel-ring loss is
detected, but upstream PS/2 controller loss and command ACK/timeouts remain
limitations. VGA is byte-oriented, not Unicode glyph rendering; UTF-8
serial/data is preserved. General exception recovery is absent; NX unsupported
in current 32-bit paging. SpinMutex is not interrupt-safe; ISRs must stay
allocation/lock free. The descriptor layer is filesystem-independent and ready
to back a future disk filesystem.

Next: Phase 8 persistent block storage — a bounded ATA/IDE PIO driver behind a
block-device abstraction, test-owned virtual disk images only, then the first
bounded RostiFS format surviving verified reboot. The descriptor layer must not
gain filesystem-specific assumptions; keep swap, page reclamation and
persistence as separate responsibilities. Inspect boot port-manager guard
lifetimes before adding ATA port allocation. See NEXT_SESSION_PROMPT.md.
