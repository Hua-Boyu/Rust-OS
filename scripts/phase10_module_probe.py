"""Local pre-entry Multiboot-module probe, no disks or remote operations.
This proves copy/parser diagnostics only, never trust or namespace publication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from b13_entry_inject import run_injected


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--kernel', required=True, type=Path)
    p.add_argument('--archive', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--ram', type=int, choices=(128, 512), required=True)
    p.add_argument('--case', choices=('valid', 'corrupt', 'absent', 'ambiguous', 'oversize'), required=True)
    a = p.parse_args()
    payload = a.archive.read_bytes()
    if not 0 < len(payload) <= 256 * 1024:
        raise ValueError('fixture size')
    marker = {
        'valid': 'ROSTI: initramfs parsed; UNVERIFIED, not published',
        'corrupt': 'ROSTI: initramfs archive rejected:',
        'absent': 'ROSTI: initramfs absent; RAMFS recovery',
        'ambiguous': 'ROSTI: initramfs ambiguous; RAMFS recovery',
        'oversize': 'ROSTI: initramfs copy rejected: Span',
    }[a.case]

    def mutate(gdb, regs):
        header = bytearray(gdb.read(regs['ebx'], 88))
        flags = struct.unpack_from('<I', header)[0] | (1 << 3)
        count = 0 if a.case == 'absent' else 2 if a.case == 'ambiguous' else 1
        table, label, target = 0x1000000, 0x1000100, 0x1100000
        struct.pack_into('<I', header, 0, flags)
        struct.pack_into('<II', header, 20, count, table)
        gdb.write(label, b'rosti.initramfs\0')
        body = b'corrupt archive' if a.case == 'corrupt' else payload
        for i in range(count):
            start = target + i * 0x100000
            length = 256 * 1024 + 1 if a.case == 'oversize' else len(body)
            gdb.write(table + i * 16, struct.pack('<4I', start, start + length, label, 0))
            for off in range(0, len(body), 512):
                gdb.write(start + off, body[off:off + 512])
        gdb.write(0x70000, header)
        gdb.set_registers(ebx=0x70000)

    run_injected(a.kernel, a.output_dir, mutate, memory=a.ram,
                 serial_markers=('ROSTI: entered kernel_main', 'ROSTI: paging enabled', marker, 'ROSTI: boot complete'))
    report = json.loads((a.output_dir / 'report.json').read_text())
    report.update(scope='injected ELF module copy/parser probe; no trust/mount acceptance', case=a.case,
                  archive_sha256=hashlib.sha256(payload).hexdigest())
    (a.output_dir / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'case': a.case, 'ram': a.ram, 'status': report['status']}))


if __name__ == '__main__':
    main()
