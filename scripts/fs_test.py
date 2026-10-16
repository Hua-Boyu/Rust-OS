#!/usr/bin/env python3
"""Bounded filesystem/keyboard QEMU integration, with serial and VGA evidence.

No build is performed. Default boot target: target/target/debug/kernel.
--output-dir selects an evidence parent; every invocation creates a unique child.
Command results exclude the echoed input and are read only after the next prompt.
The VGA fallback supports legacy VGA-only commands; filesystem and mem mirror serial.
Stress contract: fsstress: PASS; mem exposes FS storage/entries as numeric counters.
"""
import argparse
import json
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"
PROMPT = "rosti>"
KEYS = {" ": "spc", ".": "dot", "!": "shift-1", "-": "minus", "/": "slash"}


def key_name(char):
    if char in KEYS:
        return KEYS[char]
    if char.isascii() and char.isupper():
        return "shift-" + char.lower()
    if char.isascii() and char.isalnum():
        return char
    raise ValueError(f"unsupported keyboard character: {char!r}")


def command_output(fragment, typed):
    """Reject echo-only/partial evidence; return only completed dispatch output."""
    fragment = fragment.replace("\r\n", "\n")
    prefix = typed + "\n"
    if not fragment.startswith(prefix) or not fragment.endswith(PROMPT):
        raise AssertionError(f"invalid command boundary for {typed!r}: {fragment!r}")
    return fragment[len(prefix):-len(PROMPT)]


def counters(text):
    patterns = {
        "used": r"Used(?: bytes)?:\s*(\d+)(?:\s+bytes)?",
        "capacity": r"Current capacity:\s*(\d+)",
        "growth_pages": r"Growth pages:\s*(\d+)",
        "failed_allocations": r"Failed allocations:\s*(\d+)",
        "live_allocations": r"Live allocations:\s*(\d+)",
        "fs_storage": r"(?:FS|Filesystem|File system) (?:storage|storage used|storage bytes|data bytes|used):\s*(\d+)",
        "fs_entries": r"(?:FS|Filesystem|File system) (?:entries|nodes):\s*(\d+)",
    }
    result = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result[name] = int(match.group(1))
    match = re.search(
        r"Descriptors: open (\d+) records (\d+) opens (\d+) closes (\d+) denials (\d+) stale (\d+)",
        text, re.IGNORECASE)
    if match:
        result["fd_open_slots"], result["fd_open_records"], result["fd_opens"], \
            result["fd_closes"], result["fd_denials"], result["fd_stale"] = map(int, match.groups())
    return result


class Harness:
    def __init__(self, args, run):
        self.args, self.run = args, run
        self.serial = run / "serial.txt"
        self.deadline = time.monotonic() + args.timeout
        self.proc = self.sock = self.stream = self.live_serial = None
        self.serial_bytes = bytearray()
        self.report = {"ram_mib": args.ram, "stress": args.stress, "checks": [],
                       "commands": [], "memory": {}, "overall": "FAIL"}
        self.sequence = 0

    def check(self, condition, label):
        self.report["checks"].append({"check": label, "pass": bool(condition)})
        if not condition:
            raise AssertionError(label)

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HARNESS_FAIL: end-to-end deadline exceeded")
        if self.proc is not None and self.proc.poll() is not None:
            raise RuntimeError(f"KERNEL_FAULT: QEMU exited ({self.proc.returncode})")
        return remaining

    def text(self):
        if self.live_serial is not None:
            while True:
                try:
                    data = self.live_serial.recv(65536)
                except BlockingIOError:
                    break
                if not data:
                    raise RuntimeError("HARNESS_FAIL: live serial socket closed")
                self.serial_bytes.extend(data)
                with self.serial.open("ab") as capture:
                    capture.write(data)
            return self.serial_bytes.decode("ascii", errors="replace")
        return self.serial.read_bytes().decode("ascii", errors="replace") if self.serial.exists() else ""

    def wait(self, predicate, label, seconds=12):
        end = min(self.deadline, time.monotonic() + seconds)
        while time.monotonic() < end:
            self.remaining()
            if predicate():
                return
            time.sleep(0.02)
        raise TimeoutError(f"HARNESS_FAIL: timed out waiting for {label}")

    def qmp(self, name, **arguments):
        self.sequence += 1
        ident = self.sequence
        self.sock.settimeout(min(5, self.remaining()))
        self.stream.write(json.dumps({"execute": name, "arguments": arguments, "id": ident}).encode() + b"\n")
        self.stream.flush()
        while True:
            self.sock.settimeout(min(5, self.remaining()))
            line = self.stream.readline()
            if not line:
                raise RuntimeError("HARNESS_FAIL: QMP closed connection")
            reply = json.loads(line)
            if reply.get("id") != ident:
                continue
            if "error" in reply:
                raise RuntimeError(f"HARNESS_FAIL: QMP {reply['error']}")
            return reply["return"]

    def key(self, name):
        reply = self.qmp("human-monitor-command", **{"command-line": f"sendkey {name} 20"})
        if reply.strip():
            raise RuntimeError(f"HARNESS_FAIL: sendkey {name}: {reply!r}")
        time.sleep(min(0.065, self.remaining()))

    def type_text(self, text):
        for char in text:
            before = len(self.text())
            self.key(key_name(char))
            self.wait(lambda: self.text()[before:] == char, f"decoded key {char!r}", seconds=3)

    def screen(self, label):
        path = self.run / f"{self.sequence:04d}_{label}.bin"
        self.qmp("pmemsave", val=0xB8000, size=4000, filename=path.as_posix())
        data = path.read_bytes()
        if len(data) != 4000:
            raise RuntimeError("HARNESS_FAIL: invalid VGA memory capture")
        rows = [data[i:i + 160:2].decode("ascii", errors="replace").rstrip()
                for i in range(0, 4000, 160)]
        path.with_suffix(".txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        return rows

    def command(self, typed, edit=False):
        start = len(self.text())
        self.type_text(typed)
        raw_echo = typed
        effective = typed
        if edit:
            self.key("backspace")
            raw_echo += "\x08 \x08"
            effective = typed[:-1]
            self.wait(lambda: self.text()[start:] == raw_echo, "backspace serial erase", seconds=3)
            rows = self.screen("backspace")
            self.check(rows[-1] == PROMPT + effective, "backspace erases VGA cell")
        self.key("ret")
        self.wait(lambda: self.text()[start:].endswith(PROMPT), f"next prompt after {effective!r}")
        fragment = self.text()[start:]
        serial_output = command_output(fragment, raw_echo)
        rows = self.screen("command")
        self.check(rows[-1] == PROMPT, f"VGA prompt after {effective}")
        # Find the most recent exact echoed command, never treat it as output.
        echoes = [i for i, row in enumerate(rows[:-1]) if row == PROMPT + effective]
        vga_output = "\n".join(rows[echoes[-1] + 1:-1]) + "\n" if echoes else ""
        output = serial_output if serial_output.strip() else vga_output
        # Long mem output can scroll the echoed command away. Its current VGA
        # snapshot is diagnostic-only, never used for other command assertions.
        if effective == "mem" and not output.strip():
            output = "\n".join(rows[:-1]) + "\n"
        self.report["commands"].append({"command": effective, "serial_fragment": fragment,
                                        "output": output, "vga": rows})
        return output

    def exact(self, cmd, value):
        out = self.command(cmd)
        self.check(out.rstrip("\n") == value, f"{cmd}: exact output {value!r}")

    def overlong_write(self):
        self.success("write guard safe")
        typed = "write guard " + "x" * 128
        start = len(self.text())
        self.type_text(typed[:128])
        for char in typed[128:]:
            self.key(key_name(char))
        self.key("ret")
        self.wait(lambda: self.text()[start:].endswith(PROMPT), "overlong input rejection")
        fragment = self.text()[start:]
        output = command_output(fragment, typed[:128])
        rows = self.screen("overlong")
        self.report["commands"].append({"command": typed, "serial_fragment": fragment,
                                       "output": output, "vga": rows})
        self.check(output == "shell: line too long; command not executed\n", "overlong input rejected rather than partially executed")
        self.exact("cat guard", "safe")
        self.success("rm guard")

    def success(self, cmd):
        out = self.command(cmd)
        self.check(out.strip() in ("", "ok"), f"{cmd}: successful dispatch")

    def memory(self, label):
        out = self.command("mem")
        self.check("Paging: enabled" in out and "Page directory:" in out and
                   "Total frames:" in out and "Free frames:" in out,
                   f"mem {label}: paging and physical frame diagnostics")
        self.check("Page faults: 0" in out and "Invalid deallocs: 0" in out,
                   f"mem {label}: no faults or invalid deallocations")
        values = counters(out)
        self.report["memory"][label] = values
        self.check(all(k in values for k in ("used", "capacity", "growth_pages", "failed_allocations")),
                   f"mem {label}: heap counters parsed")
        return values

    def verify_live_iso(self):
        blocks = self.qmp("query-block")
        self.report.setdefault("live_block_checks", []).append(blocks)
        paths = []
        for block in blocks:
            if block.get("qdev") != "ide2":
                continue
            path = block.get("inserted", {}).get("file")
            if isinstance(path, str) and path.startswith("json:"):
                descriptor = json.loads(path[5:])
                path = None
                # Proxmox may wrap raw/file with a throttle block driver.
                # Match the exact file leaf, never a substring in arbitrary JSON.
                for _ in range(8):
                    if not isinstance(descriptor, dict):
                        break
                    if descriptor.get("driver") == "file":
                        path = descriptor.get("filename")
                        break
                    descriptor = descriptor.get("file")
            paths.append(path)
        self.check(str(self.args.expected_iso) in paths, "live runtime media matches expected ISO")

    def start_live(self):
        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError("HARNESS_FAIL: --live must run on the Proxmox host")
        self.report["live_vmid"] = self.args.live
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(min(5, self.remaining()))
        self.sock.connect(f"/var/run/qemu-server/{self.args.live}.qmp")
        self.stream = self.sock.makefile("rwb")
        self.check("QMP" in json.loads(self.stream.readline()), "QMP greeting")
        self.qmp("qmp_capabilities")
        self.verify_live_iso()
        self.live_serial = socket.socket(socket.AF_UNIX)
        self.live_serial.settimeout(min(5, self.remaining()))
        self.live_serial.connect(f"/var/run/qemu-server/{self.args.live}.serial0")
        self.live_serial.setblocking(False)
        self.text()  # Preserve pre-reset bytes separately from boot evidence.
        start = len(self.serial_bytes)
        self.qmp("system_reset")
        self.wait(lambda: self.text()[start:].endswith(PROMPT) and
                  "ROSTI: boot complete" in self.text()[start:], "live fresh boot", seconds=40)
        text = self.text()[start:]
        self.check(0 <= text.find("ROSTI: entered kernel_main") < text.find("ROSTI: boot complete"),
                   "ordered boot markers")
        status = self.qmp("query-status")
        self.check(status.get("running") is True, "live VM running after reset")

    def start(self):
        if self.args.live is not None:
            self.start_live()
            return
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        boot = ["-cdrom", str(self.args.iso.resolve()), "-boot", "d"] if self.args.iso else [
            "-kernel", str(PROJECT / "target" / "target" / "debug" / "kernel")]
        executable = QEMU if Path(QEMU).is_file() else shutil.which("qemu-system-i386")
        if not executable:
            raise RuntimeError("HARNESS_FAIL: QEMU executable not found")
        argv = [executable, *boot, "-display", "none", "-no-reboot", "-m", str(self.args.ram),
                "-serial", f"file:{self.serial}", "-monitor", "none",
                "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off",
                "-d", "int,guest_errors", "-D", str(self.run / "qemu_log.txt")]
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
        greeting = json.loads(self.stream.readline())
        self.check("QMP" in greeting, "QMP greeting")
        self.qmp("qmp_capabilities")
        self.wait(lambda: self.text().endswith(PROMPT), "initial shell prompt", seconds=30)
        text = self.text()
        self.check(0 <= text.find("ROSTI: entered kernel_main") < text.find("ROSTI: boot complete"),
                   "ordered boot markers")

    def exercise(self):
        self.exact("pwd", "/")
        # A trusted initramfs may publish a read-only /system at root, so cleanup
        # must restore the pre-existing listing rather than assume an empty root.
        baseline_root = self.command("ls").rstrip("\n")
        before = self.memory("before")
        self.success("mkdir docs")
        self.success("cd docs")
        self.exact("pwd", "/docs")
        self.success("touch hello.txt")
        self.success("write hello.txt Hello from Rosti OS")
        self.exact("cat hello.txt", "Hello from Rosti OS")
        self.success("append hello.txt !")
        self.exact("cat hello.txt", "Hello from Rosti OS!")
        self.exact("ls", "hello.txt")
        stat = self.command("stat hello.txt")
        self.check(bool(re.search(r"(?m)^type: file$", stat)) and
                   bool(re.search(r"(?m)^size: 20 bytes$", stat)), "stat file type and exact 20-byte size")
        live = self.memory("live_file")
        self.check(live["used"] > before["used"], "filesystem uses real heap storage")
        self.check(all(k in live for k in ("fd_open_slots", "fd_opens", "fd_closes")),
                   "mem exposes descriptor counters")
        self.check(live["fd_opens"] >= 1 and live["fd_closes"] == live["fd_opens"] and
                   live["fd_open_records"] == 0 and live["fd_open_slots"] == 3,
                   "file commands dispatch through the descriptor layer, close cleanly, "
                   "and leave only the reserved console descriptors open")
        out = self.command("fdlist")
        self.check("fd 0 console-in" in out and "fd 1 console-out" in out and
                   "fd 2 console-out" in out, "fdlist shows reserved console descriptors")
        out = self.command("rmdir /docs")
        self.check(bool(re.search(r"(?im)^fs:.*(?:not empty|non.?empty)", out)), "rmdir refuses nonempty directory")
        self.exact("cat hello.txt", "Hello from Rosti OS!")
        self.success("rm hello.txt")
        out = self.command("stat hello.txt")
        self.check(bool(re.search(r"(?im)^fs:.*(?:not found|no such|does not exist|missing)", out)), "stat removed file is missing")
        self.success("cd ..")
        self.success("rmdir docs")
        self.exact("pwd", "/")
        self.exact("ls", baseline_root)
        self.overlong_write()
        after = self.memory("after_cleanup")
        self.check(after["used"] < live["used"], "filesystem cleanup releases heap storage")
        self.check(after["used"] <= before["used"] + self.args.max_retained_bytes, "bounded retained heap bytes")
        self.check(after["failed_allocations"] == before["failed_allocations"], "normal workflow has no allocation failures")
        self.check(after["growth_pages"] >= before["growth_pages"], "heap growth counter monotonic")
        if self.args.stress:
            self.check(all(k in after for k in ("fs_storage", "fs_entries")), "stress baseline FS accounting available")
            out = self.command("fsstress")
            self.check(out.splitlines().count("fsstress: PASS") == 1, "fsstress exact PASS output once")
            post = self.memory("after_stress")
            self.check(post["growth_pages"] > after["growth_pages"], "stress exercises runtime heap growth")
            self.check(post["failed_allocations"] > after["failed_allocations"], "stress exercises safe OOM")
            self.check(post["used"] <= after["used"] + self.args.max_retained_bytes, "stress releases bounded heap storage")
            self.check(all(post.get(k) == after[k] for k in ("fs_storage", "fs_entries")), "stress FS accounting restored")
            self.exact("ls", baseline_root)
        out = self.command("help")
        match = re.search(r"(?m)^commands:\s*(.*)$", out)
        self.check(match is not None and all(c in match.group(1).split() for c in
                   ("help", "version", "uptime", "echo", "clear", "pwd", "mkdir", "cat", "stat")), "help regression includes shell and filesystem commands")
        out = self.command("version")
        self.check(len(out.splitlines()) == 1 and out.startswith("Rosti kernel v"), "version regression")
        out = self.command("cpu")
        self.check(out.strip().startswith("cpu:") and "not available" not in out,
                   "CPU identification survives filesystem and OOM operations")
        out = self.command("uptime")
        match = re.search(r"^ticks: (\d+), uptime: \d+ s", out)
        self.check(match is not None and int(match.group(1)) > 0, "uptime positive ticks")
        self.exact("echo fs-regression", "fs-regression")
        out = self.command("echo editedx", edit=True)
        self.check(out.rstrip("\n") == "edited", "backspace dispatch exactly once")
        out = self.command("clear")
        self.check(not out.strip(), "clear emits no command output")
        self.check(self.report["commands"][-1]["vga"] == [""] * 24 + [PROMPT], "clear blanks VGA and retains prompt")
        self.exact("pwd", "/")
        if self.args.live is not None:
            self.check(self.qmp("query-status").get("running") is True, "live VM alive after workflow")
            self.verify_live_iso()
        else:
            self.check(self.proc.poll() is None, "owned guest alive after workflow")
        self.check(not re.search(r"PANIC:|page fault:|CPU exception", self.text()), "no serial kernel fault")
        if self.args.live is None:
            trace = (self.run / "qemu_log.txt").read_text(errors="replace")
            self.check("triple fault" not in trace.lower(), "no QEMU triple fault")

    def close(self):
        if self.live_serial:
            self.text()
            self.live_serial.close()
        if self.stream:
            self.stream.close()
        if self.sock:
            self.sock.close()
        if self.proc:
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait(timeout=5)
        self.report["owned_qemu_exited"] = self.proc is None or self.proc.poll() is not None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path)
    parser.add_argument("--ram", type=int, choices=(128, 512), default=128)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stress", action="store_true")
    parser.add_argument("--live", type=int, nargs="?", const=103,
                        help="Run ON pve against VMID (default 103); resets this VM, never terminates it")
    parser.add_argument("--expected-iso", help="Required exact runtime ISO path for --live")
    parser.add_argument("--timeout", type=float, default=180, help="End-to-end deadline in seconds")
    parser.add_argument("--max-retained-bytes", type=int, default=0,
                        help="Allowed retained vector/allocator capacity after cleanup")
    args = parser.parse_args(argv)
    if args.live is not None and (args.expected_iso is None or args.iso is not None or args.live != 103):
        parser.error("--live is restricted to VM 103 and requires --expected-iso; --iso cannot be combined")
    if args.expected_iso is not None and args.live is None:
        parser.error("--expected-iso requires --live")
    if args.timeout <= 0 or args.max_retained_bytes < 0:
        parser.error("timeout must be positive and retained bytes nonnegative")
    root = (args.output_dir or PROJECT / "test_results" / "filesystem").resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=time.strftime("%Y%m%d_%H%M%S_") + f"ram{args.ram}_", dir=root))
    harness = Harness(args, run)
    started = time.monotonic()
    try:
        harness.start()
        harness.exercise()
        harness.report["overall"] = "PASS"
    except (Exception, KeyboardInterrupt) as error:
        harness.report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            harness.close()
        except Exception as error:
            harness.report["overall"] = "FAIL"
            harness.report["cleanup_error"] = str(error)
        harness.report["elapsed_s"] = round(time.monotonic() - started, 3)
        harness.report["command_count"] = len(harness.report["commands"])
        harness.report["check_count"] = len(harness.report["checks"])
        (run / "report.json").write_text(json.dumps(harness.report, indent=2) + "\n", encoding="utf-8")
    print(f"{harness.report['overall']}: filesystem integration; "
          f"{harness.report['command_count']} commands, {harness.report['check_count']} checks; evidence: {run}")
    if "error" in harness.report:
        print(harness.report["error"])
    return 0 if harness.report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
