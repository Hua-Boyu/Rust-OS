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

- ISO is bootable under QEMU SeaBIOS+GRUB (verified 2026-10-09 via
  `scripts/build-proxmox-iso.py` boot test: both markers captured from the ISO
  path, plus a live interrupt reaching the IDT).
- Proxmox MCP connectivity verified read-only (2026-10-09): node `pve` online
  (8 cores, ~33 GiB). No VM was created or modified — deployment requires
  explicit authorization.
- Full deployment verified 2026-10-10 on VM 103 (`rosti-dev`, i440fx, SeaBIOS,
  `serial0: socket`): versioned ISO `rosti_20261010T154256Z.iso` uploaded,
  remote SHA256 matched local (`bbfa45f92211cef0a8aa587cc69adf3ba35342b05582db46e35e62d0d0afa8d5`), attached to ide2, booted, and both markers plus shell interaction (`help`, `version`, `echo abc`→`abc`, Backspace `echo abc`→`ab`, `uptime` timer progression) captured over the serial socket `/var/run/qemu-server/103.serial0` with input via `qm sendkey`. Machine-readable report: `test_results/proxmox/deploy_report.json`.
- Repeatable gated pipeline: `scripts/deploy-proxmox.py` (11 gates, stops on
  any failure, only touches VM 103, preserves `dist/rosti_rollback.iso`).
  Credentials come from environment variables only.
- Historical size mismatch explained: the earlier remote listing (8,622,187 B)
  was a staging artifact from the 501-failing upload endpoint, not the final
  file; the actual destination file is byte-identical to the local ISO.
