# PROXMOX DEPLOYMENT

## Phase 9.5: read-only boundary, no deployment

Structured GET inventory during maintenance confirmed VM 103 `rosti-dev`
running with 512 MiB, one CPU, SeaBIOS, pc/i440fx, serial socket and only
ide2 `local:iso/rosti_phase7_20261012T181123Z.iso`; no data disk entry.
Recorded digest `c0253f4f9bc55e6c3f222dcc893833cc46157a4b` in
`test_results/phase9_5/proxmox_readonly.json`. Phase 8/9/9.5 have not been
uploaded/deployed or live persistent-file tested. No attach/detach, disk creation,
formatting, reset/start/stop, upload or other remote write was performed.

The current Phase 9.5 acceptance and benchmarks use disposable local QEMU media
only. Future deployment/storage changes need explicit user approval and fresh
exact target inventory/readback. Do not invoke historical live tests below
under read-only authorization: they reset the VM and destroy volatile state.

## Phase 9 safety boundary and fresh read-only inventory

Read-only `pve_get_qemu_config` and `pve_get_qemu_status` confirmed node `pve`,
VM **103**, name **rosti-dev**, running, **512 MiB**, one core, SeaBIOS,
runtime i440fx, `serial0: socket`. Its only disk entry is the CD-ROM:
`ide2: local:iso/rosti_phase7_20261012T181123Z.iso,media=cdrom,size=9204K`;
boot order `ide2`. **No data disk is configured.** Evidence:
`test_results/phase9/proxmox_readonly.json`.

No create/format/attach/detach/upload/reset/start/stop operation was performed.
Phase 8 and Phase 9 are local-only releases; **live RostiFS persistence is NOT
VERIFIED**. Existing deployed Phase 7 media and Phase 6 rollback remain intact.

A possible future VM test would require a **64 MiB raw virtual data disk on
IDE0** of VM 103, after re-inventory proving IDE0 free and selecting an exact
new storage allocation distinct from all existing disks. This is a proposal,
not permission or a completed allocation: the storage pool/destination and disk
identity must be presented for explicit approval before any change. No raw host
disk, NAS volume or other guest disk is a formatting target. The host formatter
currently creates only exclusive images under this repository's `dist/`.

All current filesystem tests use newly created local QEMU images. Do not claim
live file persistence from local evidence or the remote VM's running status.
The prior deployment workflow and rollback identities below remain historical
reference, not authorization for new storage changes.

Phase 8 is fully verified locally and has not been deployed. No guest data
disk was created or attached during this continuation. The
Phase 7 deployment below is the last recorded remote checkpoint, not a fresh
live-state query. Phase 8 disk tests use new `dist/` images in local QEMU.
A VM 103 disk requires separate explicit creation/attachment authorization,
a read-only inventory, an exact owned destination and verified readback.

## Current Phase 7 deployment

VM 103 (`rosti-dev`) on pve is running the Phase 7 build. Only its CD-ROM and
power state were changed; 1 vCPU, 512 MiB, SeaBIOS and serial socket are
unchanged. No host reboot, other guest, storage layout or authentication
implementation was changed. Deployment used the existing key-auth SSH alias
(`ssh proxmox` / `proxmox` wrapper), verified before use.

- ISO: `rosti_phase7_20261012T181123Z.iso`
- SHA256: `4c1e337d1362d827248ad0e3ee13f8c67bb29cdff3a1a460d1cd1d5e97b62bb4`
  (local == remote, verified with `sha256sum` on pve)
- Attached to VM 103 ide2 only; runtime QMP media, final config and status
  read back and verified.
- Live integration: 38 commands, 104/104 checks, including descriptor-layer
  dispatch proof (`mem` counters, `fdlist` reserved console descriptors) and
  full stress (4 MiB integrity, heap growth 1,048,576 -> 7,340,032 bytes,
  1,536 growth pages, four intentional OOMs, cleanup to 8,232-byte baseline).
- Descriptor counters live: opens 12, closes 12, denials 0, stale 0, open
  records 0, open slots 3 (reserved console descriptors only).
- VM left running at a clean prompt; remote evidence preserved under
  `/root/live_evidence_phase7/` and copied to `test_results/phase7/live_vm103/`.
- Rollback media remains the verified Phase 6 ISO
  `local:iso/rosti_phase6_20261012T152259Z.iso`, SHA256
  `8b3a4d4dbb0f245a2b969e3aed7d973cdf46a2b6e5da07f0a189da23c44472cb`;
  local copy `dist/rosti_preserved_8b3a4d4dbb0f245a.iso`. Earlier rollback ISOs
  are kept; nothing was deleted.

Evidence: `test_results/phase7/live_vm103/report.json` and `serial.txt`.
The live media check compares the exact QMP file leaf; pass the full runtime
path as `--expected-iso` (the bare-filename form fails by design — that failure
is retained as a regression fixture, not weakened).

Repeat live checks ON pve using copied scripts and a unique temporary directory:
```bash
python3 verify_proxmox_backspace.py --require-paging --expected-iso rosti_phase7_20261012T181123Z.iso
python3 fs_test.py --live 103 --ram 512 --stress --expected-iso /var/lib/vz/template/iso/rosti_phase7_20261012T181123Z.iso --output-dir <owned-temporary-directory>
```
These reset VM 103 and erase its volatile files; run only with deployment/test
authorization. Preserve the previous ISO and collect reports before cleanup.
The older deploy-proxmox.py password workflow remains unchanged.


## VM configuration (minimal, current kernel)

| Setting | Value |
|---|---|
| Machine | i440fx |
| BIOS | SeaBIOS |
| Guest OS type | Other |
| CPU | 1 core |
| Memory | 512 MiB |
| Boot disk | `rosti.iso` (from `dist/rosti.iso`) |
| Display | Standard VGA |
| Disk | not required |
| Network | not required initially |

SeaBIOS is required: the kernel is a Multiboot v1 ELF and the ISO uses GRUB's
i386-pc (BIOS) image. OVMF/UEFI is not supported by this kernel.

## GUI steps

1. Build the ISO on the dev machine: `python scripts/build-proxmox-iso.py`
   (requires the kernel built + WSL grub-mkrescue; output `dist/rosti.iso`).
2. In Proxmox, select the node → ISO Images → Upload `rosti.iso`.
3. Create VM: General → name `rosti`, Other OS.
4. System: Machine `i440fx`, BIOS `SeaBIOS`.
5. CPU: 1 core. Memory: 512 MiB.
6. Hardware: add the uploaded `rosti.iso` as a CD/DVD drive.
7. Options: boot order = CD/DVD drive first.
8. Start the VM; console shows the kernel output (VGA text at bottom row),
   serial markers observable via the test harness on the dev machine.

## Optional `qm` CLI

```bash
qm create 900 --name rosti --ostype other --machine i440fx --bios seabios \
  --cores 1 --memory 512 --vga std
qm set 900 --ide2 /path/to/rosti.iso --boot order=ide2
qm start 900
```

## Verified status

### Historical Phase 5 release (2026-10-12)

VM 103 runs `rosti_20261012T125244Z.iso`, SHA256
`5b8875f9e8b848a346ef22a93eec689688a5cf55ec0c4e765209a8f83ec9015f`
(local == remote, verified before attachment and again after live checks).
All 25 deployment gates passed. Live checks: 20/20 pipeline checks plus the
Phase 5 shell verification (`scripts/live_phase5_check.py`, 13/13): `help`,
`version`, `uptime`, `mem` (frame stats, paging, page directory, heap stats,
failed allocations, page-fault count) and a keyboard-edit round trip. Hardware
registers read back live via QMP: CR0 = `80010011` (PG + WP), CR3 =
`00001000`, null PTE absent. VM left running at a clean prompt. Rollback ISO
and prior versioned ISOs remain available.

Evidence: `test_results/proxmox/deploy_report.json`,
`test_results/proxmox/phase4_live_report.json`,
`test_results/phase5/live_vm103_report.json`.
The pipeline supports SSH/scp/pvesh with `PVE_ROOT_PASSWORD` from environment;
no API token is required on that path. Password uses binary stdin, not argv.
The live verifier adds hardware paging assertions with `--require-paging`.

### Earlier Backspace release (2026-10-12)

That earlier ISO contained the visual Backspace fix, the pending frame/paging
work, and the memory-statistics boot-deadlock fix. The ISO boots and passes
13 actual VGA/serial editing checks in QEMU at the VM's 512 MiB setting.
Authenticated SSH uploaded `rosti_20261012T081528Z.iso` and attached it to
VM 103 (`rosti-dev`) only. Remote SHA256 matched local before attachment and
again after verification. The running QEMU CD-ROM was checked before reset.
Live verification passed all 16 checks: ordered boot markers, actual VGA
deletion/replacement, wrapped editing, prompt protection, whitespace-only
dispatch, and serial erase sequences. VM 103 is running at a clean `rosti>`
prompt with `backspace-ok` displayed. The previous ISO remains available.

Evidence: `test_results/proxmox/backspace_verified.json` (source `ff48a62`).
Repeatable live verifier: `scripts/verify_proxmox_backspace.py`; run it on the
Proxmox host through authenticated SSH with `--expected-iso <ISO filename>`.
It resets only VM 103 and never accepts or stores credentials.

Local ISO SHA256:
`7ce870322780fa639319b8734582310566553c1faeafc91388e3ae6e685589d8`.

At that earlier checkpoint, paging fell back to disabled at 512 MiB. The
current Phase 4 release fixes mapping coverage independently of the physical
frame cap. Physical allocation remains below 256 MiB; paging is now active.

- ISO is bootable under QEMU SeaBIOS+GRUB (verified 2026-10-09 via
  `scripts/build-proxmox-iso.py` boot test: both markers captured from the ISO
  path, plus a live interrupt reaching the IDT).
- Proxmox MCP connectivity verified read-only (2026-10-09): node `pve` online
  (8 cores, ~33 GiB). No VM was created or modified — deployment requires
  explicit authorization.
- Full deployment verified 2026-10-10 on VM 103 (`rosti-dev`, i440fx, SeaBIOS,
  `serial0: socket`): versioned ISO `rosti_20261010T154256Z.iso` uploaded,
  remote SHA256 matched local (`bbfa45f92211cef0a8aa587cc69adf3ba35342b05582db46e35e62d0d0afa8d5`), attached to ide2, booted, and both markers plus shell interaction (`help`, `version`, `echo abc`→`abc`, Backspace `echo abc`→`ab`, `uptime` timer progression) captured over the serial socket `/var/run/qemu-server/103.serial0` with input via `qm sendkey`. Machine-readable report: `test_results/proxmox/deploy_report.json`.
- Repeatable gated pipeline: `scripts/deploy-proxmox.py` (25 gates, stops on
  any failure, only touches VM 103, preserves `dist/rosti_rollback.iso`).
  Credentials come from environment variables only.
- Historical size mismatch explained: the earlier remote listing (8,622,187 B)
  was a staging artifact from the 501-failing upload endpoint, not the final
  file; the actual destination file is byte-identical to the local ISO.
