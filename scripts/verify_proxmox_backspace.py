#!/usr/bin/env python3
"""Run ON the Proxmox host: verify VM 103 Backspace against live VGA cells.

No credentials are accepted or stored. Invoke through an authenticated SSH
connection. Resets only VM 103, checks boot markers and actual VGA contents,
and emits a JSON evidence report. Leaves a clean shell prompt afterward.
"""
import argparse
import json
import re
import socket
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-iso", required=True)
    parser.add_argument("--require-paging", action="store_true")
    args = parser.parse_args()
    report = {"vmid": 103, "expected_iso": args.expected_iso, "checks": [], "screens": {}}
    serial_bytes = bytearray()
    deadline = time.monotonic() + 120
    with tempfile.TemporaryDirectory(prefix="rosti-vga-103-") as scratch:
        with socket.socket(socket.AF_UNIX) as qmp, socket.socket(socket.AF_UNIX) as serial:
            qmp.settimeout(5)
            qmp.connect("/var/run/qemu-server/103.qmp")
            serial.connect("/var/run/qemu-server/103.serial0")
            serial.setblocking(False)
            stream = qmp.makefile("rwb")
            json.loads(stream.readline())

            def command(name, **arguments):
                if time.monotonic() > deadline:
                    raise TimeoutError("live verification exceeded deadline")
                stream.write(json.dumps({"execute": name, "arguments": arguments}).encode() + b"\n")
                stream.flush()
                while True:
                    result = json.loads(stream.readline())
                    if "error" in result:
                        raise RuntimeError(result["error"])
                    if "return" in result:
                        return result["return"]

            def drain():
                while True:
                    try:
                        data = serial.recv(4096)
                    except BlockingIOError:
                        break
                    if not data:
                        break
                    serial_bytes.extend(data)

            def expect(condition, label):
                report["checks"].append({"check": label, "pass": bool(condition)})
                if not condition:
                    raise AssertionError(label)

            def key(name):
                command("human-monitor-command", **{"command-line": f"sendkey {name} 20"})
                time.sleep(0.08)
                drain()

            def type_text(text):
                for ch in text:
                    key("spc" if ch == " " else "minus" if ch == "-" else ch)

            def screen(label):
                path = Path(scratch) / (label + ".bin")
                command("pmemsave", val=0xB8000, size=4000, filename=str(path))
                data = path.read_bytes()[::2]
                rows = [data[i:i + 80].decode("ascii", errors="replace") for i in range(0, 2000, 80)]
                report["screens"][label] = rows
                return rows

            try:
                command("qmp_capabilities")
                blocks = command("query-block")
                expect(args.expected_iso in json.dumps(blocks), "running CD-ROM uses uploaded ISO")
                command("system_reset")
                while b"rosti>" not in serial_bytes:
                    if time.monotonic() > deadline:
                        raise TimeoutError("shell did not boot after reset")
                    time.sleep(0.1)
                    drain()
                expect(0 <= serial_bytes.find(b"ROSTI: entered kernel_main") < serial_bytes.find(b"ROSTI: boot complete"), "boot markers captured in order")
                expect(screen("boot")[-1].startswith("rosti>"), "VGA capture contains real shell prompt")
                if args.require_paging:
                    expect(b"ROSTI: paging enabled" in serial_bytes and b"paging validation FAILED" not in serial_bytes,
                           "paging enabled without validation failure")
                    registers = command("human-monitor-command", **{"command-line": "info registers"})
                    report["registers"] = registers
                    cr0 = re.search(r"CR0=([0-9a-fA-F]+)", registers)
                    cr3 = re.search(r"CR3=([0-9a-fA-F]+)", registers)
                    expect(cr0 and cr3 and int(cr0.group(1), 16) & (1 << 31) and int(cr3.group(1), 16) != 0,
                           "hardware CR0.PG set and CR3 loaded")
                    directory = int(cr3.group(1), 16) & ~0xFFF
                    path = Path(scratch) / "null_entry.bin"
                    command("pmemsave", val=directory, size=4, filename=str(path))
                    table = int.from_bytes(path.read_bytes(), "little") & ~0xFFF
                    command("pmemsave", val=table, size=4, filename=str(path))
                    expect(int.from_bytes(path.read_bytes(), "little") & 1 == 0, "hardware null-page PTE absent")
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
                expect(screen("whitespace_after") == before, "whitespace-only command protects new prompt")
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
                expect(rows[-2] == "rosti>" + "a" * 73 + "z" and rows[-1].startswith("y "), "replacement rewraps without losing input")
                for _ in range(75):
                    key("backspace")
                key("backspace")
                rows = screen("fully_erased")
                expect(rows[-2].strip() == "rosti>" and rows[-1].strip() == "", "erasing wrapped input stops at prompt")
                type_text("echo final")
                key("ret")
                expect(screen("final")[-2].strip() == "final", "new command after wrapped deletion executes")
                drain()
                expect(b"echo okx\x08 \x08z\nokz\n" in serial_bytes, "serial mirror erases deleted character")
                if args.require_paging:
                    type_text("mem")
                    key("ret")
                    # mem prints several VGA-only lines. Wait for dispatch
                    # completion, not an arbitrary key-delay screenshot.
                    end = min(deadline, time.monotonic() + 5)
                    while not serial_bytes.endswith(b"rosti>") and time.monotonic() < end:
                        time.sleep(0.1)
                        drain()
                    expect("paging: enabled" in "\n".join(screen("mem")), "shell mem reports paging enabled")
                type_text("clear")
                key("ret")
                type_text("echo backspace-okx")
                key("backspace")
                key("ret")
                expect(screen("finished")[-2].strip() == "backspace-ok" and screen("prompt")[-1].strip() == "rosti>", "VM left at clean prompt with successful edit output")
                report["overall"] = "PASS"
            except Exception as exc:
                report["overall"] = "FAIL"
                report["error"] = str(exc)
            finally:
                drain()
                report["serial"] = serial_bytes.decode(errors="replace")
                print(json.dumps(report, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
