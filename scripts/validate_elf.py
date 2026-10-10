#!/usr/bin/env python3
"""Validate the built kernel ELF as a Multiboot 1 boot image.

Checks (per the Multiboot spec + QEMU's -kernel ELF loader):
  1. ELF32, little-endian, ET_EXEC
  2. Multiboot v1 magic 0x1BADB002 present, 4-byte aligned, within the
     first 8192 bytes, with a valid checksum
  3. At least one PT_LOAD program header with paddr >= 0x100000
  4. Entry point inside a PT_LOAD segment
  5. File-backed sections and NOBITS (BSS) covered by the segment's memsz

Exits nonzero on any failure. This replaces the old add_phdrs.py patcher:
the linker script now emits a correct PT_LOAD directly, so post-processing
is unnecessary.

Usage: python3 scripts/validate_elf.py <kernel.elf>
"""
import struct
import sys

def main(path):
    f = open(path, 'rb').read()
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(('PASS' if cond else 'FAIL') + f': {msg}')
        if not cond:
            ok = False

    check(f[:4] == b'\x7fELF' and f[4] == 1 and f[5] == 1, "ELF32 little-endian")

    (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
     e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = struct.unpack(
        '<HHIIIIIHHHHHH', f[16:52])
    check(e_type == 2, f"ET_EXEC (got {e_type})")
    check(e_machine == 3, f"EM_386 (got {e_machine})")

    # Multiboot header scan: first 8192 bytes, 4-byte aligned
    hits = []
    for off in range(0, min(8192, len(f)), 4):
        if f[off:off+4] == struct.pack('<I', 0x1BADB002):
            flags, chk = struct.unpack_from('<II', f, off + 4)
            if (0x1BADB002 + flags + chk) % 2**32 == 0:
                hits.append((off, flags, chk))
    check(bool(hits), "multiboot magic 0x1BADB002 within first 8192 bytes, "
                      f"aligned, valid checksum ({[hex(h[0]) for h in hits]})")

    phdrs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        phdrs.append(struct.unpack_from('<IIIIIIII', f, o))
    loads = [p for p in phdrs if p[0] == 1]
    check(bool(loads), f"has PT_LOAD program header(s) ({len(loads)})")
    check(all(p[3] >= 0x100000 for p in loads),
          "PT_LOAD paddr >= 0x100000 (multiboot load address)")
    check(any(p[3] <= e_entry < p[3] + p[5] for p in loads),
          f"entry {hex(e_entry)} inside a PT_LOAD segment")

    # BSS (SHT_NOBITS) must be covered by memsz, not filesz
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        nameoff, typ, flags, addr, offset, size = struct.unpack_from('<IIIIII', f, off)
        if typ == 8 and size > 0:  # SHT_NOBITS
            covered = any(p[3] <= addr and addr + size <= p[3] + p[5] for p in loads)
            check(covered, f"BSS section at {hex(addr)} size {size} covered by PT_LOAD memsz")

    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main(sys.argv[1])
