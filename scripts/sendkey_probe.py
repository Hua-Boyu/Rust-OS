#!/usr/bin/env python3
"""Probe QEMU monitor sendkey syntax: which names are accepted, which rejected.
Boots the kernel headless, sends candidate keys, prints raw monitor responses."""
import re, socket, subprocess, sys, time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"
KERNEL = str(PROJECT / "target" / "target" / "debug" / "kernel")
OUT = PROJECT / "test_results" / "keyboard" / "probe_serial.txt"
OUT.parent.mkdir(parents=True, exist_ok=True)

srv = socket.socket(); srv.bind(("127.0.0.1", 0)); PORT = srv.getsockname()[1]; srv.close()
q = subprocess.Popen([QEMU, "-kernel", KERNEL, "-display", "none", "-no-reboot", "-m", "128",
                      "-serial", f"file:{OUT}", "-monitor", f"telnet:127.0.0.1:{PORT},server,nowait"])

s = None
for _ in range(50):
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=2); break
    except OSError:
        time.sleep(0.2)
if s is None:
    print("probe: monitor connect failed"); q.kill(); sys.exit(1)

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
def read_resp():
    time.sleep(0.3)
    s.setblocking(False)
    try:
        return ANSI.sub("", s.recv(4096).decode(errors="replace"))
    except (BlockingIOError, OSError):
        return ""

# drain banner
read_resp()

CANDIDATES = ["shift-a", "shift-h", "H", "a", "minus", "spc", "backspace", "ret",
              "caps_lock", "shift", "hyphen", "space"]
for k in CANDIDATES:
    s.sendall(f"sendkey {k}\n".encode())
    resp = read_resp()
    print(f"sendkey {k!r} -> {resp.strip()!r}")

time.sleep(1.5)
q.kill(); q.wait()
print("--- serial after probe ---")
print(OUT.read_text(errors="replace"))
