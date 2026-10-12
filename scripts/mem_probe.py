#!/usr/bin/env python3
"""Probe the shell `mem` command in QEMU: VGA dump + serial mirror."""
import os
import socket
import struct
import subprocess
import time

QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"
KERNEL = r"C:\Users\iamsv\Documents\Rust-OS\target\target\debug\kernel"
TMP = r"C:\Users\iamsv\Documents\Rust-OS\test_results\mem_probe"
os.makedirs(TMP, exist_ok=True)
OUT = os.path.join(TMP, "serial.txt")
DUMP = os.path.join(TMP, "vga.bin")
for f in (OUT, DUMP):
    if os.path.exists(f):
        os.remove(f)

srv = socket.socket()
srv.bind(("127.0.0.1", 0))
PORT = srv.getsockname()[1]
srv.close()
q = subprocess.Popen([QEMU, "-kernel", KERNEL, "-display", "none", "-no-reboot", "-m", "512",
                      "-serial", f"file:{OUT}", "-monitor", f"telnet:127.0.0.1:{PORT},server,nowait"])

def connect():
    for _ in range(50):
        try:
            return socket.create_connection(("127.0.0.1", PORT), timeout=2)
        except OSError:
            time.sleep(0.2)
    return None

s = connect()
assert s, "monitor connect failed"

def read():
    time.sleep(0.3)
    s.setblocking(False)
    try:
        return s.recv(8192).decode(errors="replace")
    except Exception:
        return ""

time.sleep(6)
read()
for ch in "mem":
    s.sendall(f"sendkey {ch}\n".encode())
    time.sleep(0.4)
s.sendall(b"sendkey ret\n")
time.sleep(2)
s.sendall(f"pmemsave 0xB8000 4000 {DUMP}\n".encode())
time.sleep(1)
cells = open(DUMP, "rb").read()
text = "".join(chr(struct.unpack("<H", cells[i:i + 2])[0] & 0xFF) for i in range(0, len(cells), 2))
print("=== VGA screen ===")
print(text)
print("=== serial ===")
print(open(OUT, errors="replace").read())
q.terminate()
