#!/usr/bin/env python3
"""Run ON the Proxmox host: live shell command checks for VM 103 (Phase 5).

Exercises help, version, uptime, mem and a keyboard-edit round trip over the
live serial socket, plus heap/paging diagnostics from the `mem` screen via VGA
capture. Read-only except sendkey input; no credentials. Emits a JSON report
including screens captured at failure.
"""
import json
import socket
import tempfile
import time
from pathlib import Path

VMID = 103
DEADLINE = time.monotonic() + 120
report = {"vmid": VMID, "checks": [], "screens": {}}
serial_bytes = bytearray()


def main():
    with tempfile.TemporaryDirectory(prefix="rosti-live-103-") as scratch:
        with socket.socket(socket.AF_UNIX) as qmp, socket.socket(socket.AF_UNIX) as serial:
            qmp.settimeout(5)
            qmp.connect(f"/var/run/qemu-server/{VMID}.qmp")
            serial.connect(f"/var/run/qemu-server/{VMID}.serial0")
            serial.setblocking(False)
            stream = qmp.makefile("rwb")
            json.loads(stream.readline())

            def command(name, **arguments):
                if time.monotonic() > DEADLINE:
                    raise TimeoutError("live check exceeded deadline")
                stream.write(json.dumps({"execute": name, "arguments": arguments}).encode() + b"\n")
                stream.flush()
                while True:
                    result = json.loads(stream.readline())
                    if "error" in result:
                        raise RuntimeError(result["error"])
                    if "return" in result:
                        return result["return"]

            command("qmp_capabilities")

            def drain():
                while True:
                    try:
                        data = serial.recv(4096)
                    except BlockingIOError:
                        break
                    if not data:
                        break
                    serial_bytes.extend(data)

            def expect(cond, label):
                report["checks"].append({"check": label, "pass": bool(cond)})
                if not cond:
                    report["screens_at_failure"] = dict(report["screens"])
                    raise AssertionError(label)

            def screen(name):
                path = Path(scratch) / f"{name}.bin"
                command("pmemsave", val=0xB8000, size=4000, filename=str(path))
                cells = path.read_bytes()
                rows = ["".join(chr(int.from_bytes(cells[r * 160 + c:r * 160 + c + 2], "little") & 0xFF)
                                for c in range(0, 160, 2)).rstrip()
                        for r in range(25)]
                return [r for r in rows if r]

            def hmc(line):
                return command("human-monitor-command", **{"command-line": line})

            KEYNAME = {" ": "spc", "-": "minus"}

            def type_text(text):
                for ch in text:
                    hmc(f"sendkey {KEYNAME.get(ch, ch)} 20")
                    time.sleep(0.08)

            def key(k):
                hmc(f"sendkey {k} 20")
                time.sleep(0.08)

            # Fresh boot so serial captures all command output in order.
            command("system_reset")
            end = time.monotonic() + 40
            while time.monotonic() < end:
                drain()
                text = serial_bytes.decode(errors="replace")
                if text.endswith("rosti>"):
                    break
                time.sleep(0.2)
            text = serial_bytes.decode(errors="replace")
            expect("ROSTI: entered kernel_main" in text and "ROSTI: boot complete" in text,
                   "boot markers captured in order")
            expect("rosti>" in text, "shell prompt reached")

            def run(cmd):
                drain()
                before = len(serial_bytes)
                type_text(cmd)
                key("ret")
                end = time.monotonic() + 10
                while time.monotonic() < end:
                    drain()
                    time.sleep(0.1)
                return serial_bytes[before:].decode(errors="replace")

            out = run("help")
            expect("commands: help clear version mem cpu uptime echo reboot" in out,
                   "help lists commands")
            out = run("version")
            expect("Rosti kernel v0.1.0" in out, "version reports kernel version")
            out = run("uptime")
            expect("uptime: " in out, "uptime reports tick-based uptime")
            out = run("mem")
            expect("mem" in out, "mem command echoes on serial")
            mem_screen = screen("mem")
            report["screens"]["mem"] = mem_screen
            joined = "\n".join(mem_screen)
            expect("Paging: enabled" in joined, "mem reports paging enabled")
            expect("Total frames:" in joined and "Free frames:" in joined,
                   "mem reports frame statistics")
            expect("Kernel heap:" in joined and "Current capacity:" in joined,
                   "mem reports heap statistics")
            expect("Failed allocations:" in joined, "mem reports failed allocations")
            expect("Page faults:" in joined, "mem reports page fault count")
            expect("Page directory: 0x00001000" in joined, "mem reports page directory")

            # Keyboard editing round trip: two backspaces erase the last two
            # typed characters ("5x"), so the executed command is "echo phase".
            drain()
            type_text("echo phase5x")
            key("backspace")
            key("backspace")
            key("ret")
            time.sleep(1)
            edit_screen = screen("edit")
            report["screens"]["edit"] = edit_screen
            joined_edit = "\n".join(edit_screen)
            expect("echo phase" in joined_edit and "phase" in joined_edit,
                   "edited command executes correctly")

            report["overall"] = "PASS"
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(json.dumps({"overall": "FAIL", "error": str(e), **report}, indent=2))
        raise SystemExit(1)
