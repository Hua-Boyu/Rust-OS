# PROXMOX DEPLOYMENT

## Current Phase 6 deployment

VM 103 (`rosti-dev`) on pve is running the new SeaBIOS/i440fx build. Only its
CD-ROM and power state were changed; 1 vCPU, 512 MiB and serial socket are
unchanged. No host reboot, other guest, storage layout or authentication
implementation was changed. MCP stop/start tasks completed; SSH attached ide2
because the available MCP update schema does not expose that field.

- ISO: `rosti_phase6_20261012T152259Z.iso`
- SHA256: `8b3a4d4dbb0f245a2b969e3aed7d973cdf46a2b6e5da07f0a189da23c44472cb`
- Runtime QMP media, final config/status and remote/local checksums verified.
- Hardware/VGA checks 20/20; file/shell/stress checks 100/100, 37 commands.
- CR0 `80010011` (PG + WP), CR3 `00001000`; null PTE absent.
- Real live heap growth: 1,536 pages, 4 MiB file integrity, safe OOM and cleanup.
- VM left running at a clean prompt; owned remote test directory removed.
- Rollback media remains `local:iso/rosti_20261012T125244Z.iso`, SHA256
  `5b8875f9e8b848a346ef22a93eec689688a5cf55ec0c4e765209a8f83ec9015f`.
  Local copy: `dist/rosti_preserved_5b8875f9e8b848a3.iso`; older rollback ISO kept.

Evidence: `test_results/phase6/deployment.json`, `live_vm103/report.json`,
`live_vm103/hardware_vga.json`, serial and final config/status readbacks.
The initial exact-media reader failure is retained as a regression fixture;
the fixed reader handles Proxmox JSON block-driver wrappers without weakening
path identity. Passwordless key-auth SSH used the existing proxmox alias.

Repeat live checks ON pve using copied scripts and a unique temporary directory:
```bash
python3 verify_proxmox_backspace.py --require-paging --expected-iso rosti_phase6_20261012T152259Z.iso
python3 fs_test.py --live 103 --ram 512 --stress --expected-iso /var/lib/vz/template/iso/rosti_phase6_20261012T152259Z.iso --output-dir <owned-temporary-directory>
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
