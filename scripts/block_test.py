#!/usr/bin/env python3
"""Bounded Phase 8 ATA tests on NEW dist/ images only; no build or live VM access.

Uses the filesystem harness's paced QMP keyboard, serial dispatch boundaries,
VGA capture and scoped cleanup. No external image argument is accepted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

from fs_test import Harness, PROJECT, PROMPT, QEMU

SECTORS = 65552  # Exercises both IDENTIFY capacity words, not just word 60.
MAGIC = b"ROSTI-TESTDISK"
PATTERN = bytes(0xA5 ^ (i & 255) for i in range(512))


class BlockHarness(Harness):
    def __init__(self, args, run, image, deadline):
        super().__init__(args, run)
        self.image = image
        self.deadline = deadline

    def check(self, condition, label):
        self.report["checks"].append({"name": label, "pass": bool(condition)})
        if not condition:
            raise AssertionError(label)

    def start(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        executable = QEMU if Path(QEMU).is_file() else shutil.which("qemu-system-i386")
        if not executable:
            raise RuntimeError("HARNESS_FAIL: QEMU executable not found")
        boot = ["-cdrom", str(self.args.iso.resolve()), "-boot", "d"] if self.args.iso else [
            "-kernel", str(PROJECT / "target/target/debug/kernel")]
        argv = [executable, *boot, "-machine", "pc", "-m", str(self.args.ram),
                "-display", "none", "-serial", f"file:{self.serial}", "-monitor", "none",
                "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off",
                "-d", "guest_errors", "-D", str(self.run / "qemu_log.txt")]
        if self.image is not None:
            # Primary master, plain raw file, deliberately writeback-cached.
            argv += ["-drive", f"file={self.image.as_posix()},format=raw,if=ide,index=0,cache=writeback"]
        self.report["argv"] = argv
        with (self.run / "qemu_stderr.txt").open("wb") as stderr:
            self.proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=stderr)
        self.report["qemu_pid"] = self.proc.pid
        while self.sock is None:
            self.remaining()
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=min(1, self.remaining()))
            except OSError:
                time.sleep(0.05)
        self.sock.settimeout(min(5, self.remaining()))
        self.stream = self.sock.makefile("rwb")
        self.check("QMP" in json.loads(self.stream.readline()), "QMP greeting")
        self.qmp("qmp_capabilities")
        self.wait_boot(0)
        self.report["query_block"] = self.qmp("query-block")
        if self.image is not None:
            self.check(any(Path(b.get("inserted", {}).get("file", "")).resolve() == self.image
                           for b in self.report["query_block"]), "QMP exact owned image attached")

    def wait_boot(self, start):
        self.wait(lambda: self.text()[start:].endswith(PROMPT), "boot shell prompt", seconds=30)
        text = self.text()[start:]
        self.check(0 <= text.find("ROSTI: entered kernel_main") < text.find("ROSTI: boot complete"),
                   "ordered boot markers")
        self.check("PANIC:" not in text and "PAGE FAULT" not in text, "no boot panic/fault")

    def reboot(self):
        start = len(self.text())
        self.type_text("reboot")
        # Do not use command(): reboot deliberately cannot finish at the old prompt.
        self.key("ret")
        self.wait(lambda: "ROSTI: entered kernel_main" in self.text()[start:],
                  "guest-requested reboot enters kernel", seconds=30)
        self.wait_boot(start)
        self.report["guest_reboot"] = True

    def disk_info(self, owned):
        out = self.command("disk")
        self.check("block device: QEMU HARDDISK" in out, "ATA model identified")
        self.check(f"capacity: {SECTORS} sectors x 512 bytes" in out, "32-bit IDENTIFY capacity")
        self.check(f"test-owned media: {'yes' if owned else 'no'}" in out, "ownership is explicit")


def digest(image):
    return hashlib.sha256(image.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ram", type=int, choices=(128, 512), default=128)
    parser.add_argument("--iso", type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    # Fields needed by reused harness, never permitting its live mode.
    args.live = None
    args.stress = False
    root = (args.output_dir or PROJECT / "test_results/phase8").resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f"block_ram{args.ram}_", dir=root))
    disks = PROJECT / "dist"
    disks.mkdir(exist_ok=True)
    disk_dir = Path(tempfile.mkdtemp(prefix="phase8_block_", dir=disks)).resolve()
    owned, unowned = disk_dir / "owned.raw", disk_dir / "unowned.raw"
    for image, magic in [(owned, MAGIC), (unowned, b"")]:
        # Exclusive creation: cannot overwrite existing media.
        with image.open("xb") as stream:
            stream.truncate(SECTORS * 512)
            stream.seek(0)
            stream.write(magic)
    baseline = digest(unowned)
    report = {"overall": "FAIL", "ram_mib": args.ram, "iso": str(args.iso) if args.iso else None,
              "disk_dir": str(disk_dir), "checks": [], "scenarios": []}
    started = time.monotonic()
    deadline = started + args.timeout

    def check(value, name, **details):
        report["checks"].append({"name": name, "pass": bool(value), **details})
        if not value:
            raise AssertionError(name)

    def scenario(name, image, exercise):
        folder = run / name
        folder.mkdir()
        h = BlockHarness(args, folder, image, deadline)
        try:
            h.start()
            exercise(h)
            h.report["overall"] = "PASS"
        except (Exception, KeyboardInterrupt) as error:
            h.report["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            try:
                h.close()
            except Exception as error:
                h.report["overall"] = "FAIL"
                h.report["cleanup_error"] = str(error)
            h.report["checks"].append({"name": "owned QEMU process terminated", "pass": h.report.get("owned_qemu_exited", False)})
            (folder / "report.json").write_text(json.dumps(h.report, indent=2) + "\n")
            report["scenarios"].append({"name": name, "report": str(folder / "report.json"),
                                        "overall": h.report["overall"]})
            report["checks"].extend({**c, "name": name + ": " + c["name"]} for c in h.report["checks"])
            if h.report["overall"] != "PASS":
                check(False, name + ": scenario completed", error=h.report.get("error", h.report.get("cleanup_error")))

    def owned_first(h):
        h.disk_info(True)
        h.exact("diskread 1", "block: sector 1 mismatch 510 bytes")
        h.exact("diskwrite 0", "block: write refused: media not test-owned")
        h.exact(f"diskread {SECTORS}", "block: LBA out of range")
        h.exact(f"diskwrite {SECTORS}", "block: LBA out of range")
        h.exact("diskread 268435456", "block: LBA out of range")
        h.exact("diskwrite 4294967295", "block: LBA out of range")
        h.exact("diskwrite -1", "block: usage: diskwrite <sector>")
        h.exact("diskwrite 1", "block: wrote sector 1")
        h.exact(f"diskwrite {SECTORS - 1}", f"block: wrote sector {SECTORS - 1}")
        h.exact("diskread 1", "block: sector 1 pattern match (512 bytes)")
        h.reboot()
        h.disk_info(True)
        h.exact("diskread 1", "block: sector 1 pattern match (512 bytes)")
        h.exact(f"diskread {SECTORS - 1}", f"block: sector {SECTORS - 1} pattern match (512 bytes)")
        check(True, "full 512-byte markers persist after guest reboot")

    def owned_restart(h):
        h.disk_info(True)
        h.exact("diskread 1", "block: sector 1 pattern match (512 bytes)")
        h.exact(f"diskread {SECTORS - 1}", f"block: sector {SECTORS - 1} pattern match (512 bytes)")
        check(True, "full 512-byte markers persist after QEMU process restart")

    def absent(h):
        h.exact("disk", "block: no device (IDENTIFY failed or 28-bit addressing unsupported)")
        h.exact("diskread 1", "block: no device")
        h.exact("diskwrite 1", "block: no device")
        before = h.memory("absent before")
        h.exact("disk", "block: no device (IDENTIFY failed or 28-bit addressing unsupported)")
        after = h.memory("absent after")
        h.check(before["used"] == after["used"], "absent disk diagnostics allocate no retained heap")

    def protected(h):
        h.disk_info(False)
        h.exact("diskwrite 1", "block: write refused: media not test-owned")
        h.exact("diskwrite 0", "block: write refused: media not test-owned")
        h.exact(f"diskwrite {SECTORS}", "block: LBA out of range")
        h.exact("diskread 1", "block: sector 1 mismatch 510 bytes")
        h.check("writes 0" in h.command("disk"), "no successful writes to unowned image")

    try:
        scenario("owned_reboot", owned, owned_first)
        with owned.open("rb") as stream:
            sector0 = stream.read(512)
            sector1 = stream.read(512)
            stream.seek((SECTORS - 1) * 512)
            last = stream.read(512)
        check(sector0 == MAGIC + bytes(512 - len(MAGIC)), "ownership sector 0 preserved byte-for-byte")
        check(sector1 == PATTERN and last == PATTERN, "host readback verifies both complete sectors",
              marker_sha256=hashlib.sha256(PATTERN).hexdigest())
        scenario("owned_restart", owned, owned_restart)
        scenario("absent", None, absent)
        scenario("unowned", unowned, protected)
        check(digest(unowned) == baseline, "entire unowned image unchanged", sha256=baseline)
        check(all(c["pass"] for c in report["checks"]), "all checks pass")
        report["overall"] = "PASS"
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["elapsed_s"] = round(time.monotonic() - started, 3)
        report["check_count"] = len(report["checks"])
        report["pass_count"] = sum(c["pass"] for c in report["checks"])
        (run / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['overall']}: block integration {report['pass_count']}/{report['check_count']} checks; evidence: {run}")
    if "error" in report:
        print(report["error"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
