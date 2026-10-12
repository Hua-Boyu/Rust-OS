#!/usr/bin/env python3
"""Verify shell editing against actual QEMU VGA memory, not serial echo alone."""
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, help="Boot this ISO instead of the kernel ELF")
    parser.add_argument("--memory", type=int, default=512, help="Guest RAM in MiB (VM 103: 512)")
    args = parser.parse_args()
    run = PROJECT / "test_results" / "backspace" / time.strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    serial = run / "serial.txt"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    boot = ["-cdrom", str(args.iso.resolve()), "-boot", "d"] if args.iso else [
        "-kernel", str(PROJECT / "target" / "target" / "debug" / "kernel")]
    q = subprocess.Popen([QEMU, *boot, "-display", "none", "-no-reboot", "-m", str(args.memory),
                          "-serial", f"file:{serial}",
                          "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off"])
    sock = None
    checks = []
    deadline = time.monotonic() + 120
    try:
        while sock is None:
            if time.monotonic() > deadline or q.poll() is not None:
                raise RuntimeError("HARNESS_FAIL: QMP connection unavailable")
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            except OSError:
                time.sleep(0.1)
        stream = sock.makefile("rwb")
        json.loads(stream.readline())

        def command(name, **arguments):
            stream.write(json.dumps({"execute": name, "arguments": arguments}).encode() + b"\n")
            stream.flush()
            while True:
                result = json.loads(stream.readline())
                if "error" in result:
                    raise RuntimeError(result["error"])
                if "return" in result:
                    return result["return"]

        command("qmp_capabilities")
        while not serial.exists() or "rosti>" not in serial.read_text(errors="replace"):
            if time.monotonic() > deadline or q.poll() is not None:
                raise RuntimeError("KERNEL_FAULT: shell did not boot")
            time.sleep(0.1)

        def key(name):
            if time.monotonic() > deadline:
                raise RuntimeError("HARNESS_FAIL: test deadline exceeded")
            command("human-monitor-command", **{"command-line": f"sendkey {name} 20"})
            time.sleep(0.06)

        def type_text(text):
            for ch in text:
                key("spc" if ch == " " else ch)

        def screen(label):
            path = run / f"{label}.bin"
            command("pmemsave", val=0xB8000, size=4000, filename=path.as_posix())
            data = path.read_bytes()[::2]
            return [data[i:i + 80].decode("ascii", errors="replace") for i in range(0, 2000, 80)]

        def expect(condition, label):
            checks.append({"check": label, "pass": bool(condition)})
            if not condition:
                raise AssertionError(label)

        expect(screen("boot")[-1].startswith("rosti>"), "VGA capture contains real shell prompt")
        type_text("echo okx")
        expect(screen("typed")[-1].startswith("rosti>echo okx"), "typed characters visible")
        key("backspace")
        expect(screen("deleted")[-1].startswith("rosti>echo ok "), "backspace blanks deleted VGA cell")
        key("z")
        expect(screen("replacement")[-1].startswith("rosti>echo okz "), "replacement uses erased cell")
        key("ret")
        expect(screen("dispatch")[-2].strip() == "okz", "edited command executes correctly")
        before = screen("empty_before")
        key("backspace")
        expect(screen("empty_after") == before, "empty backspace preserves prompt and output")
        type_text("   ")
        key("ret")
        before = screen("whitespace_before")
        key("backspace")
        expect(screen("whitespace_after") == before, "whitespace-only command resets input and protects new prompt")
        type_text("a" * 75)
        rows = screen("wrapped")
        expect(rows[-2] == "rosti>" + "a" * 74 and rows[-1].startswith("a "), "input wraps at VGA width")
        key("backspace")
        key("backspace")
        rows = screen("wrap_deleted")
        expect(rows[-2] == "rosti>" + "a" * 73 + " " and rows[-1].strip() == "", "backspace crosses wrap and blanks both cells")
        key("z")
        key("y")
        rows = screen("wrap_replaced")
        expect(rows[-2] == "rosti>" + "a" * 73 + "z" and rows[-1].startswith("y "), "replacement rewraps without scrolling away input")
        for _ in range(75):
            key("backspace")
        key("backspace")
        rows = screen("fully_erased")
        expect(rows[-2].strip() == "rosti>" and rows[-1].strip() == "", "erasing wrapped input stops at prompt")
        type_text("echo final")
        key("ret")
        expect(screen("final")[-2].strip() == "final", "new command after wrapped deletion executes")
        raw = serial.read_bytes()
        expect(b"echo okx\x08 \x08z\nokz\n" in raw, "serial mirror erases deleted character")
        print(f"PASS: VGA backspace regression ({len(checks)} checks); evidence: {run}")
    finally:
        if sock is not None:
            sock.close()
        if q.poll() is None:
            q.kill()
        q.wait(timeout=5)
        (run / "report.json").write_text(json.dumps({"checks": checks, "qemu_exited": q.poll() is not None}, indent=2))


if __name__ == "__main__":
    main()
