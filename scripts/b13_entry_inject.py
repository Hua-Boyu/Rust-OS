"""B13-owned reusable i386 pre-entry GDB mutation helper (local QEMU only).

No disks, ISO writes, production builds, or remote hosts. The callback runs while
stopped at the ELF symbol, before its first instruction, with paging disabled.
Callbacks can read/write Multiboot physical memory and alter EAX/EBX/ESP/EFLAGS.
"""
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import time

QEMU = Path(r"C:\Program Files\qemu\qemu-system-i386.exe")
REGISTERS = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi", "eip", "eflags")


def elf_symbols(path):
    data = Path(path).read_bytes()
    if data[:6] != b"\x7fELF\x01\x01":
        raise ValueError("Expected little-endian ELF32")
    shoff = struct.unpack_from("<I", data, 32)[0]
    entsize, count = struct.unpack_from("<HH", data, 46)
    sections = [struct.unpack_from("<10I", data, shoff + i * entsize) for i in range(count)]
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], section[9]):
            name, value, size, info, other, index = struct.unpack_from("<IIIBBH", data, offset)
            text = names[name:names.find(b"\0", name)].decode("ascii")
            if text:
                symbols[text] = {"address": value, "size": size}
    return symbols


def patch_registers(packet, updates):
    data = bytearray.fromhex(packet)
    if len(data) < 40:
        raise ValueError("Short i386 GDB register packet")
    for name, value in updates.items():
        if name not in REGISTERS:
            raise ValueError(f"Unsupported register: {name}")
        struct.pack_into("<I", data, 4 * REGISTERS.index(name), value)
    return data.hex()


class Gdb:
    def __init__(self, sock):
        self.sock = sock
        self.mutations = []

    def send(self, text):
        payload = text.encode("ascii")
        self.sock.sendall(b"$" + payload + b"#" + f"{sum(payload) & 255:02x}".encode())

    def receive(self):
        while True:
            byte = self.sock.recv(1)
            if not byte:
                raise EOFError("GDB peer closed")
            if byte == b"$":
                break
        payload = bytearray()
        while True:
            byte = self.sock.recv(1)
            if not byte:
                raise EOFError("GDB packet truncated")
            if byte == b"#":
                break
            payload.extend(byte)
        checksum = b""
        while len(checksum) < 2:
            byte = self.sock.recv(2 - len(checksum))
            if not byte:
                raise EOFError("GDB checksum truncated")
            checksum += byte
        if int(checksum, 16) != sum(payload) & 255:
            raise ValueError("GDB checksum mismatch")
        self.sock.sendall(b"+")
        return payload.decode("ascii")

    def command(self, text):
        self.send(text)
        return self.receive()

    def registers(self):
        raw = self.command("g")
        return {name: struct.unpack_from("<I", bytes.fromhex(raw), i * 4)[0]
                for i, name in enumerate(REGISTERS)}

    def set_registers(self, **updates):
        packet = patch_registers(self.command("g"), updates)
        if self.command("G" + packet) != "OK":
            raise RuntimeError("GDB rejected register write")
        actual = self.registers()
        if any(actual[name] != value for name, value in updates.items()):
            raise RuntimeError("Register write readback mismatch")
        self.mutations.append({"registers": updates})

    def read(self, address, length):
        result = self.command(f"m{address:x},{length:x}")
        if result.startswith("E"):
            raise RuntimeError(f"GDB memory read failed: {result}")
        data = bytes.fromhex(result)
        if len(data) != length:
            raise RuntimeError("Short memory read")
        return data

    def write(self, address, data):
        data = bytes(data)
        # QEMU's gdbstub buffers cap M packets (~16 KiB) and m replies (~1 KiB
        # of data), so write and read back in bounded chunks; every chunk keeps
        # the strict readback verification.
        for offset in range(0, len(data), 0x400):
            chunk = data[offset:offset + 0x400]
            if self.command(
                    f"M{address + offset:x},{len(chunk):x}:" + chunk.hex()) != "OK":
                raise RuntimeError("GDB rejected memory write")
            if self.read(address + offset, len(chunk)) != chunk:
                raise RuntimeError("Memory write readback mismatch")
        self.mutations.append({"address": address, "bytes": data.hex()})


def run_injected(kernel, output, mutate, *, entry="_start", memory=128,
                 timeout=20, serial_markers=(), debug_bytes=None, expected_exit=None,
                 boot_iso=None):
    """Run one owned guest. Preserve evidence; raise on any incomplete contract.

    mutate(gdb, before_regs) can inspect EBX, copy/patch metadata, and redirect
    registers. Only m/M GDB memory accesses with CR0.PG off should be treated as
    physical. The bootstrap target guarantees that condition at this breakpoint.
    """
    kernel, output = Path(kernel).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "FAIL", "kernel": str(kernel), "entry": entry,
              "memory_mib": memory, "cleanup": False}
    proc = None
    connection = None
    start = time.monotonic()
    serial_path, debug_path = output / "serial.txt", output / "debugcon.txt"
    try:
        symbols = elf_symbols(kernel)
        address = symbols[entry]["address"]
        report["kernel_sha256"] = hashlib.sha256(kernel.read_bytes()).hexdigest()
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        boot = ["-cdrom", str(Path(boot_iso).resolve()), "-boot", "d"] if boot_iso else ["-kernel", str(kernel)]
        cmd = [str(QEMU), *boot, "-m", str(memory), "-display", "none",
               "-no-reboot", "-monitor", "none", "-nic", "none",
               "-serial", f"file:{serial_path}", "-debugcon", f"file:{debug_path}",
               "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
               "-d", "int,guest_errors", "-D", str(output / "qemu.log"),
               "-S", "-gdb", f"tcp:127.0.0.1:{port}"]
        report["command"] = cmd
        with (output / "qemu_stderr.txt").open("wb") as stderr:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=stderr)
            deadline = start + timeout
            while connection is None and time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError("QEMU exited before GDB connection")
                try:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                except OSError:
                    time.sleep(0.02)
            if connection is None:
                raise TimeoutError("No GDB connection")
            connection.settimeout(max(0.1, deadline - time.monotonic()))
            gdb = Gdb(connection)
            gdb.command("?")
            if gdb.command(f"Z0,{address:x},1") != "OK":
                raise RuntimeError("Entry breakpoint rejected")
            stopped = gdb.command("c")
            if not stopped.startswith(("T05", "S05")):
                raise RuntimeError(f"Unexpected GDB stop: {stopped}")
            before = gdb.registers()
            if before["eip"] != address:
                raise RuntimeError("Did not stop at entry")
            report["before"] = before
            if gdb.command(f"z0,{address:x},1") != "OK":
                raise RuntimeError("Entry breakpoint removal rejected")
            mutate(gdb, before)
            report["after"] = gdb.registers()
            report["mutations"] = gdb.mutations
            # Detach resumes QEMU and avoids an unread GDB Wxx exit packet
            # blocking isa-debug-exit while the harness waits on the process.
            if gdb.command("D") != "OK":
                raise RuntimeError("GDB detach rejected")
            connection.close()
            connection = None
            complete = False
            while time.monotonic() < deadline:
                serial = serial_path.read_text(errors="replace") if serial_path.exists() else ""
                cursor = 0
                ordered = True
                for marker in serial_markers:
                    index = serial.find(marker, cursor)
                    if index < 0:
                        ordered = False
                        break
                    cursor = index + len(marker)
                debug = debug_path.read_bytes() if debug_path.exists() else b""
                serial_ok = bool(serial_markers) and ordered
                debug_ok = debug_bytes is not None and debug == debug_bytes
                if serial_ok or debug_ok:
                    if expected_exit is None or proc.poll() == expected_exit:
                        complete = True
                        break
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
            report["serial"] = serial_path.read_text(errors="replace") if serial_path.exists() else ""
            report["debugcon"] = debug_path.read_text(errors="replace") if debug_path.exists() else ""
            report["observed_exit"] = proc.poll()
            if not complete:
                raise AssertionError("Missing ordered markers/debug bytes or expected exit")
            report["status"] = "PASS"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception as error:
                report["connection_cleanup_error"] = str(error)
                report["status"] = "FAIL"
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                report["cleanup"] = proc.poll() is not None
                report["final_exit"] = proc.returncode
            except Exception as error:
                report["process_cleanup_error"] = str(error)
                report["status"] = "FAIL"
        report["elapsed_s"] = time.monotonic() - start
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "PASS" or not report["cleanup"]:
        raise RuntimeError(f"Entry fixture failed: {output / 'report.json'}: {report.get('error')}")
    return report
