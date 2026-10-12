#!/usr/bin/env python3
"""End-to-end keyboard integration test.

Pipeline stages verified (failure reported per stage):
  1. boot markers (entered kernel_main, boot complete)
  2. monitor accepts every sendkey (no 'invalid parameter' responses)
  3. decode stage: echoed characters appear on the serial mirror
  4. dispatch stage: commands execute EXACTLY ONCE each

Commands tested: help, version, echo, uptime, backspace edit, shift.
Unique temp files per run, dynamically allocated monitor port, bounded
timeout, terminates only the QEMU process it started.
"""
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"
KERNEL = str(PROJECT / "target" / "target" / "debug" / "kernel")
RUN = PROJECT / "test_results" / "keyboard"
RUN.mkdir(parents=True, exist_ok=True)
STAMP = time.strftime("%Y%m%d_%H%M%S")
OUT = RUN / f"serial_{STAMP}.txt"
DEADLINE = time.time() + 90

# Monitor key names this QEMU build accepts (probe-verified via
# scripts/sendkey_probe.py): 'space'/'hyphen'/'H' are rejected; 'spc',
# 'minus' and 'shift-<key>' are the valid names.
KEYNAME = {" ": "spc", "-": "minus", "H": "shift-h", "a": "a"}

# Dynamically allocated monitor port (no hardcoded conflicts).
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
PORT = srv.getsockname()[1]
srv.close()

q = subprocess.Popen([
    QEMU, "-kernel", KERNEL, "-display", "none", "-no-reboot", "-m", "128",
    "-serial", f"file:{OUT}", "-monitor", f"telnet:127.0.0.1:{PORT},server,nowait",
])

def connect():
    for _ in range(50):
        try:
            return socket.create_connection(("127.0.0.1", PORT), timeout=2)
        except OSError:
            time.sleep(0.2)
    return None

s = connect()
if s is None:
    print("STAGE 1 FAIL: monitor connection failed")
    q.kill()
    sys.exit(1)

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
rejected = []

def read_resp():
    time.sleep(0.25)
    s.setblocking(False)
    try:
        raw = ANSI.sub("", s.recv(4096).decode(errors="replace"))
        return raw
    except (BlockingIOError, OSError):
        return ""

def sendkey(k):
    s.sendall(f"sendkey {k}\n".encode())
    resp = read_resp()
    if "invalid" in resp.lower() or "error" in resp.lower():
        rejected.append(k)
    time.sleep(0.08)

def wait_for(marker, timeout=15):
    end = min(time.time() + timeout, DEADLINE)
    while time.time() < end:
        if OUT.exists() and marker in OUT.read_text(errors="replace"):
            return True
        time.sleep(0.2)
    return False

# Stage 1: boot markers
if not wait_for("entered kernel_main"):
    print("STAGE 1 FAIL: no 'entered kernel_main' marker")
    q.kill(); sys.exit(1)
if not wait_for("boot complete"):
    print("STAGE 1 FAIL: no 'boot complete' marker")
    q.kill(); sys.exit(1)

def type_line(line, enter=True):
    for ch in line:
        sendkey(KEYNAME.get(ch, ch))
    if enter:
        sendkey("ret")
    time.sleep(0.5)

# Stage 3/4: commands
type_line("help")
type_line("version")
type_line("echo rosti-test")
type_line("uptime")
# Backspace: 'echo okx' then backspace, THEN Enter -> dispatches 'echo ok'
# exactly once. (Enter must come after the backspace, otherwise the unedited
# line dispatches first.)
type_line("echo okx", enter=False)
sendkey("backspace")
sendkey("ret")
time.sleep(0.5)
# Shift: monitor sends shift+key for capital letters
type_line("echo H")
# Empty command: Enter on an empty line -> newline + prompt, no output
sendkey("ret")
time.sleep(0.5)

time.sleep(1)
q.kill()
q.wait()
text = OUT.read_text(errors="replace")
print(text)
print("--- stage report ---")

ok = True
def expect(stage, cond, label):
    global ok
    if not cond:
        print(f"STAGE {stage} FAIL: {label}")
        ok = False

# Stage 2: monitor accepted all keys
expect(2, not rejected, f"monitor rejected keys: {rejected}")

# Stage 3: decode/echo visible on serial mirror
expect(3, "echo rosti-test" in text, "echo line not echoed (decode stage)")
expect(3, "echo H" in text, "shift echo missing")

# Stage 4: dispatch, exactly once each. Serial writes bare LF (verified:
# zero CR bytes in the captured file), so line boundaries are "\n".
counts = {
    "commands: help": 1,
    "Rosti kernel v0.1.0": 1,
    "echo rosti-test": 1,     # typed line echoed once
    "echo okx\x08 \x08": 1,  # typed line plus terminal erase sequence
    "echo H": 1,              # typed line echoed once
    "\nH\n": 1,               # shift echo dispatch output
    "\nok\n": 1,              # backspace-corrected dispatch output
    "\nrosti-test\n": 1,      # echo dispatch output
}
for needle, n in counts.items():
    c = text.count(needle)
    expect(4, c == n, f"'{needle!r}' appeared {c} times (expected {n})")

m = re.search(r"ticks: (\d+)", text)
expect(4, m and int(m.group(1)) > 0, "uptime produced no positive tick count")
expect(4, "unknown command" not in text, "unexpected unknown-command dispatch")

print("PASS: keyboard integration (all stages)" if ok else "FAILED")
sys.exit(0 if ok else 1)
