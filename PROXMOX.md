# PROXMOX DEPLOYMENT

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

### Current Phase 4 release (2026-10-12)

VM 103 runs `rosti_20261012T091633Z.iso`, SHA256
`6a679af55b5b76988b1b6a4f464517d6aba22a3f09d4633e802c7776f49adc94`.
All 25 deployment gates passed before/through upload, attachment, boot and
final readback. Local and remote checksums match. All 20 live checks passed:
CR0.PG set (`CR0=80000011`), CR3 loaded (`00001000`), null PTE absent,
`mem` reports paging enabled, and visual Backspace still works. VM is running
at a clean prompt; old versioned ISOs and local rollback remain available.

Evidence: `test_results/proxmox/deploy_report.json`,
`test_results/proxmox/phase4_live_report.json`, `test_results/phase4/acceptance.json`.
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
