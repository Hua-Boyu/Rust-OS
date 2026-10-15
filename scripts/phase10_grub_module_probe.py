"""Build/boot one new local GRUB module probe ISO; never deploy or replace media."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
from b13_entry_inject import run_injected


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--iso', type=Path, required=True)
    p.add_argument('--expect-reserved-rejection', action='store_true')
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        execute(a)
    except Exception as error:
        report = dict(status='FAIL', scope='real GRUB module copy/parser probe only',
                      error=f'{type(error).__name__}: {error}', iso=str(a.iso.resolve()))
        (a.output_dir / 'report.json').write_text(json.dumps(report, indent=2))
        raise


def execute(a):
    project = Path(__file__).resolve().parent.parent
    iso = a.iso.resolve()
    if iso.parent != project / 'dist' or iso.exists() or iso.suffix != '.iso':
        raise ValueError('new dist ISO required')
    stage = a.output_dir / 'stage'
    (stage / 'boot/grub').mkdir(parents=True)
    shutil.copyfile(a.kernel, stage / 'boot/rosti.bin')
    shutil.copyfile(a.archive, stage / 'boot/system.cpio')
    (stage / 'boot/grub/grub.cfg').write_text('set timeout=0\nset default=0\nmenuentry "Phase10 module probe" {\n multiboot /boot/rosti.bin\n module /boot/system.cpio rosti.initramfs\n boot\n}\n')
    def wsl(path):
        path = path.resolve()
        return '/mnt/' + path.drive[0].lower() + str(path)[2:].replace('\\', '/')
    command = ['wsl', 'bash', '-c', f'grub-mkrescue -o {shlex.quote(wsl(iso))} {shlex.quote(wsl(stage))}']
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    (a.output_dir / 'build.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    # Independently extract the ISO's ELF rather than trusting staging alone.
    extracted = a.output_dir / 'extracted_kernel'
    command = ['wsl', 'bash', '-c', f'xorriso -osirrox on -indev {shlex.quote(wsl(iso))} -extract /boot/rosti.bin {shlex.quote(wsl(extracted))}']
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (a.output_dir / 'extract.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    if extracted.read_bytes() != a.kernel.read_bytes():
        raise AssertionError('ISO kernel mismatch')
    expected = a.archive.read_bytes()
    def inspect(gdb, regs):
        header = gdb.read(regs['ebx'], 88)
        flags = struct.unpack_from('<I', header)[0]
        count, table = struct.unpack_from('<II', header, 20)
        assert flags & 8 and count == 1
        start, end, name, reserved = struct.unpack('<4I', gdb.read(table, 16))
        observed = dict(start=start, end=end, name_address=name, reserved=reserved, count=count, flags=flags)
        (a.output_dir / 'observed_descriptor.json').write_text(json.dumps(observed, indent=2))
        if a.expect_reserved_rejection:
            assert reserved != 0, 'negative fixture requires nonzero loader reserved field'
        else:
            assert not reserved, f'loader reserved field is {reserved:#x}; validator requires zero'
        assert end - start == len(expected)
        assert gdb.read(name, len(b'rosti.initramfs\0')) == b'rosti.initramfs\0'
        for off in range(0, len(expected), 512):
            assert gdb.read(start + off, len(expected[off:off + 512])) == expected[off:off + 512]
    markers = (('ROSTI: entered kernel_main', 'ROSTI: boot metadata rejected: Module',
                'ROSTI: storage gate closed', 'ROSTI: boot complete') if a.expect_reserved_rejection else
               ('ROSTI: entered kernel_main', 'ROSTI: paging enabled',
                'ROSTI: initramfs parsed; UNVERIFIED, not published', 'ROSTI: boot complete'))
    for ram in (128, 512):
        run_injected(a.kernel, a.output_dir / f'boot_{ram}', inspect, memory=ram, boot_iso=iso,
                     serial_markers=markers)
    report = dict(scope='real GRUB module copy/parser probe only; no trust/mount/recovery acceptance',
                  status='PASS', expected_reserved_rejection=a.expect_reserved_rejection, iso=str(iso), iso_sha256=hashlib.sha256(iso.read_bytes()).hexdigest(),
                  kernel_sha256=hashlib.sha256(extracted.read_bytes()).hexdigest(),
                  archive_sha256=hashlib.sha256(expected).hexdigest(), ram_mib=[128, 512])
    (a.output_dir / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
