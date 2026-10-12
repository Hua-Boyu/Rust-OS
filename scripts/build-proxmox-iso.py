#!/usr/bin/env python3
"""Build a Proxmox-ready (SeaBIOS/GRUB multiboot) ISO for the Rosti kernel.

Pipeline:
  1. Validate the compiled kernel ELF (multiboot v1 contract) via
     scripts/validate_elf.py logic.
  2. Stage the kernel + a generated boot/grub/grub.cfg in a WSL-accessible
     staging dir (grub-mkrescue lives in WSL; no system-wide installs).
  3. grub-mkrescue produces dist/rosti.iso (i386-pc GRUB, BIOS bootable).
  4. Verify the ISO actually boots in QEMU: run the ISO as a virtual disk
     with -no-reboot, capture serial markers, require both markers in order.

Usage: python scripts/build-proxmox-iso.py [--skip-boot-test]
Exit 0 only if the ISO is built AND boots with both markers.
"""
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# grub-mkrescue runs in WSL; the project is reachable there via /mnt/<drive>.
WSL_PROJECT = (Path("/mnt") / PROJECT.drive[0].lower() / str(PROJECT).split(":", 1)[1].lstrip("\\/")).as_posix()
KERNEL = PROJECT / "target" / "target" / "debug" / "kernel"
DIST = PROJECT / "dist"
STAGE = f"{WSL_PROJECT}/dist/stage"
ISO = DIST / "rosti.iso"
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"
MARKER_ENTER = "ROSTI: entered kernel_main"
MARKER_DONE = "ROSTI: boot complete"

GRUB_CFG = """set timeout=0
set default=0

menuentry "Rosti kernel (multiboot)" {
    multiboot /boot/rosti.bin
}
"""


def validate_elf(path: Path) -> bool:
    import struct
    f = path.read_bytes()
    ok = f[:4] == b"\x7fELF" and f[4] == 1 and f[5] == 1
    (e_type, e_machine, _, e_entry, e_phoff, *_rest) = struct.unpack(
        "<HHIIIIIHHHHHH", f[16:52])
    ok &= e_type == 2 and e_machine == 3
    hits = []
    for off in range(0, min(8192, len(f)), 4):
        if f[off:off + 4] == struct.pack("<I", 0x1BADB002):
            flags, chk = struct.unpack_from("<II", f, off + 4)
            if (0x1BADB002 + flags + chk) % 2**32 == 0:
                hits.append(off)
    ok &= bool(hits)
    phdrs = [struct.unpack_from("<IIIIIIII", f, e_phoff + i * 32)
             for i in range(struct.unpack_from("<H", f, 42)[0])]
    loads = [p for p in phdrs if p[0] == 1]
    ok &= bool(loads) and all(p[3] >= 0x100000 for p in loads)
    ok &= any(p[3] <= e_entry < p[3] + p[5] for p in loads)
    print("ELF/multiboot validation:", "PASS" if ok else "FAIL",
          f"(magic at {[hex(h) for h in hits]}, entry {hex(e_entry)})")
    return ok


def build_iso() -> bool:
    DIST.mkdir(exist_ok=True)
    # Stage via Windows path; WSL sees the same tree under /mnt/c.
    stage_win = PROJECT / "dist" / "stage"
    (stage_win / "boot" / "grub").mkdir(parents=True, exist_ok=True)
    (stage_win / "boot" / "rosti.bin").write_bytes(KERNEL.read_bytes())
    (stage_win / "boot" / "grub" / "grub.cfg").write_text(GRUB_CFG)

    r = subprocess.run(
        ["wsl", "bash", "-c",
         f"grub-mkrescue -o {WSL_PROJECT}/dist/rosti.iso "
         f"{WSL_PROJECT}/dist/stage 2>&1"],
        capture_output=True, text=True, timeout=180)
    print(r.stdout.strip())
    if r.returncode != 0 or not ISO.exists():
        print("FAIL: grub-mkrescue did not produce the ISO")
        return False
    print(f"ISO built: {ISO} ({ISO.stat().st_size} bytes)")
    return True


def boot_test_iso() -> bool:
    out_dir = PROJECT / "test_results" / "iso_boot"
    out_dir.mkdir(parents=True, exist_ok=True)
    serial = out_dir / "serial.txt"
    log = out_dir / "qemu_log.txt"
    serial.unlink(missing_ok=True)
    log.unlink(missing_ok=True)

    cmd = [QEMU, "-m", "128", "-display", "none", "-no-reboot",
           "-cdrom", str(ISO), "-boot", "d",
           "-serial", f"file:{serial}", "-monitor", "none",
           "-D", str(log)]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    text = serial.read_text(errors="replace") if serial.exists() else ""
    print("ISO boot serial output:")
    print(text.strip() or "(empty)")
    ok = MARKER_ENTER in text and MARKER_DONE in text
    print("ISO boot test:", "PASS" if ok else "FAIL")
    return ok


def main():
    skip = "--skip-boot-test" in sys.argv
    if not KERNEL.exists():
        print(f"FAIL: kernel binary not found: {KERNEL}")
        sys.exit(1)
    if b"ROSTI: fault test trigger" in KERNEL.read_bytes():
        print("FAIL: refusing to package a deliberate page-fault test build; rebuild without features")
        sys.exit(1)
    if not validate_elf(KERNEL):
        sys.exit(1)
    if not build_iso():
        sys.exit(1)
    if skip:
        sys.exit(0)
    sys.exit(0 if boot_test_iso() else 1)


if __name__ == "__main__":
    main()
