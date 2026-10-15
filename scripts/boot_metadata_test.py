#!/usr/bin/env python3
"""Disposable Multiboot metadata fixtures; no kernel builds or production writes.

Repackages exact kernel LOAD bytes with early ELF program headers. A stack-free trampoline
copies bounded metadata to conventional RAM and jumps to the original entry.
Only the fixture guest executes those writes. QMP is read-only except keyboard.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import shlex
import socket
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace

from block_test import BlockHarness
from fs_test import PROJECT

MAGIC = 0x2badb002
INFO = 0x70000
MMAP = INFO + 0x100
MODULE_TABLE = INFO + 0x400
TRAMPOLINE = 32 * 1024 * 1024
MODULE = 16 * 1024 * 1024
MODULE_SIZE = 65536
GROWTH = 8 * 1024 * 1024
FIXTURES = ('nomodule', 'invalidmagic', 'null', 'headerbad', 'mmaptruncated',
            'modulein-growth', 'module-overlap', 'countedoverflow', 'validmodule',
            'reservedgrowth', 'frameexhaustion')
REJECTED = frozenset(FIXTURES[1:8])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def align(value, boundary=4096):
    return (value + boundary - 1) // boundary * boundary


def parse_elf(data):
    if len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('expected ELF32 little-endian version 1')
    kind, machine, version, entry, phoff = struct.unpack_from('<HHIII', data, 16)
    ehsize, phsize, phnum = struct.unpack_from('<HHH', data, 40)
    if (kind, machine, version, ehsize, phsize) != (2, 3, 1, 52, 32) or not phnum:
        raise ValueError('unsupported ELF executable/program headers')
    if phoff < 52 or phoff + phnum * phsize > len(data):
        raise ValueError('truncated program-header table')
    segments = [struct.unpack_from('<8I', data, phoff + i * 32) for i in range(phnum)]
    for p in segments:
        if p[0] == 1 and (p[4] > p[5] or p[1] + p[4] > len(data) or
                         p[3] + p[5] > 2**32 or p[2] != p[3]):
            raise ValueError('invalid or nonidentity PT_LOAD')
    if not any(p[0] == 1 and p[2] <= entry < p[2] + p[5] for p in segments):
        raise ValueError('entry outside PT_LOAD')
    return {'entry': entry, 'segments': segments}


def build_fixture(original, name, ram):
    if name not in FIXTURES or ram not in (128, 512):
        raise ValueError('unsupported fixture')
    elf = parse_elf(original)
    loads = [p for p in elf['segments'] if p[0] == 1]
    kernel_start = min(p[3] for p in loads)
    kernel_end = max(p[3] + p[5] for p in loads)
    for low, high in ((INFO, INFO + 0x500), (GROWTH, GROWTH + 4096),
                      (MODULE, MODULE + MODULE_SIZE), (TRAMPOLINE, TRAMPOLINE + 4096)):
        if any(p[3] < high and low < p[3] + p[5] for p in loads):
            raise ValueError('production PT_LOAD overlaps fixture scratch region')
    blob = bytearray(0x500)
    flags = 1 << 6
    top = ram * 1024 * 1024 - 65536
    ranges = [(0, 0x9fc00, 1), (0x9fc00, 0x60400, 2),
              (0x100000, top - 0x100000, 1)]
    if name == 'reservedgrowth':
        ranges.append((GROWTH, 1, 2))
    if name == 'frameexhaustion':
        pool = 48 * 1024 * 1024
        if kernel_end >= pool:
            raise ValueError('kernel exceeds exhaustion fixture boundary')
        # Leave exactly two complete free frames. The full RAM window still
        # demands 33/129 page-table frames plus the directory, forcing rollback.
        ranges.extend([(0, kernel_start, 2), (kernel_end, pool - kernel_end, 2),
                       (pool + 8192, top - pool - 8192, 2)])
    mmap = b''.join(struct.pack('<IQQI', 20, base, length, kind)
                    for base, length, kind in ranges)
    blob[0x100:0x100 + len(mmap)] = mmap
    struct.pack_into('<II', blob, 44, len(mmap) - (name == 'mmaptruncated'), MMAP)
    module_payload = None
    if name in ('modulein-growth', 'module-overlap', 'validmodule', 'countedoverflow'):
        flags |= 1 << 3
        count = 0xffffffff if name == 'countedoverflow' else 2 if name == 'module-overlap' else 1
        struct.pack_into('<II', blob, 20, count, MODULE_TABLE)
        start = GROWTH if name == 'modulein-growth' else MODULE
        descriptor = struct.pack('<4I', start, start + MODULE_SIZE, 0, 0)
        blob[0x400:0x410] = descriptor
        if name == 'module-overlap':
            blob[0x410:0x420] = descriptor
        if name == 'validmodule':
            module_payload = bytes(i % 251 for i in range(MODULE_SIZE))
    struct.pack_into('<I', blob, 0, flags)
    info = 0 if name == 'null' else 0x9fff0 if name == 'headerbad' else INFO
    magic = 0xdeadbeef if name == 'invalidmagic' else MAGIC
    extra = 1 + (module_payload is not None)
    # GRUB's Multiboot loader only accepts program headers in its early search
    # buffer. Appending the table after a multi-megabyte debug ELF works with
    # QEMU's direct loader but GRUB rejects it before _start. Keep an early
    # table and copy each LOAD byte-for-byte at its unchanged physical address;
    # non-load debug/section headers are not needed by this disposable fixture.
    phoff = 52
    header_end = phoff + (len(loads) + extra) * 32
    if header_end > 8192:
        raise ValueError('fixture program headers exceed GRUB search window')
    result = bytearray(original[:52])
    # GRUB also requires a real section-table offset. A single null section
    # suffices; zero e_shnum/e_shoff triggers ELF extended-count validation.
    result.extend(bytes(header_end + 40 - len(result)))
    struct.pack_into('<I', result, 32, header_end)
    struct.pack_into('<HHH', result, 46, 40, 1, 0)
    segments = []
    for p in loads:
        alignment = max(4096, p[7])
        if alignment & (alignment - 1):
            raise ValueError('non-power-of-two LOAD alignment')
        offset = align(len(result), alignment) + p[2] % alignment
        result.extend(bytes(offset - len(result)))
        result.extend(original[p[1]:p[1] + p[4]])
        segments.append((p[0], offset, *p[2:]))
    code_offset = align(len(result))
    # Stack-free: preserve incoming EAX, except for the explicit invalid-magic
    # case. Clear DF for the copy; production entry is separately ABI-tested.
    code_size = 29 + (5 if name == 'invalidmagic' else 0)
    code = b'\xfa\xfc\xbe' + struct.pack('<I', TRAMPOLINE + code_size)
    code += b'\xbf' + struct.pack('<I', INFO) + b'\xb9' + struct.pack('<I', len(blob))
    code += b'\xf3\xa4'
    if name == 'invalidmagic':
        code += b'\xb8' + struct.pack('<I', magic)
    code += b'\xbb' + struct.pack('<I', info)
    code += b'\xe9' + struct.pack('<i', elf['entry'] - (TRAMPOLINE + code_size))
    assert len(code) == code_size
    payload = code + blob
    segments.append((1, code_offset, TRAMPOLINE, TRAMPOLINE,
                     len(payload), len(payload), 5, 4096))
    result.extend(bytes(code_offset - len(result)))
    result.extend(payload)
    if module_payload is not None:
        offset = align(len(result))
        result.extend(bytes(offset - len(result)))
        result.extend(module_payload)
        segments.append((1, offset, MODULE, MODULE, MODULE_SIZE, MODULE_SIZE, 4, 4096))
    for i, p in enumerate(segments):
        struct.pack_into('<8I', result, phoff + i * 32, *p)
    struct.pack_into('<II', result, 24, TRAMPOLINE, phoff)
    struct.pack_into('<H', result, 44, len(segments))
    manifest = {'name': name, 'ram_mib': ram, 'original_entry': elf['entry'],
                'code_size': code_size, 'info': info, 'magic': magic,
                'expected_rejection': name in REJECTED, 'metadata_hex': blob.hex(),
                'kernel_start': kernel_start, 'kernel_end': kernel_end,
                'mmap': [{'base': b, 'length': n, 'type': t} for b, n, t in ranges],
                'module_address': MODULE if module_payload else None,
                'module_size': len(module_payload) if module_payload else 0,
                'module_sha256': digest(module_payload) if module_payload else None}
    if name == 'frameexhaustion':
        manifest['free_pool_bytes'] = 8192
    return bytes(result), manifest


def write_json(path, report):
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def run_scenario(h, folder, exercise):
    """A workload PASS is provisional until independent process cleanup passes."""
    success = False
    try:
        image = getattr(h, 'image', None)
        if image is not None:
            h.report['recovery_image'] = str(image)
            h.report['recovery_image_before_sha256'] = digest(image.read_bytes())
        exercise(h)
        if not h.report['checks']:
            raise AssertionError('workload produced no verification checks')
        success = True
    except (Exception, KeyboardInterrupt) as error:
        h.report['error'] = f'{type(error).__name__}: {error}'
        h.report['checks'].append({'name': 'workload completed', 'pass': False})
        if getattr(h, 'sock', None) is not None and hasattr(h, 'screen'):
            try:
                h.report['failure_vga'] = h.screen('failure')
            except Exception as capture_error:
                h.report['failure_vga_error'] = str(capture_error)
    finally:
        try:
            h.close()
        except Exception as error:
            success = False
            h.report['cleanup_error'] = str(error)
            h.report['checks'].append({'name': 'harness cleanup completed', 'pass': False})
        # Do not trust close()'s status flag; reap precisely our captured Popen.
        try:
            if h.proc is not None:
                if h.proc.poll() is None:
                    h.proc.kill()
                h.proc.wait(timeout=5)
            exited = h.proc is None or h.proc.poll() is not None
        except Exception as error:
            exited = False
            h.report['fallback_cleanup_error'] = str(error)
        h.report['owned_qemu_exited'] = exited
        h.report['checks'].append({'name': 'owned QEMU process terminated', 'pass': exited})
        if getattr(h, 'image', None) is not None:
            try:
                if not exited:
                    raise RuntimeError('cannot hash recovery media before owned process exit')
                after = digest(h.image.read_bytes())
                h.report['recovery_image_after_sha256'] = after
                unchanged = after == h.report.get('recovery_image_before_sha256')
                h.report['checks'].append({'name': 'full recovery image unchanged after process exit',
                                           'pass': unchanged})
            except Exception as error:
                h.report['recovery_image_error'] = str(error)
                h.report['checks'].append({'name': 'full recovery image unchanged after process exit',
                                           'pass': False})
        success = success and exited and bool(h.report['checks']) and all(
            c['pass'] for c in h.report['checks'])
        h.report['overall'] = 'PASS' if success else 'FAIL'
        h.report['check_count'] = len(h.report['checks'])
        h.report['pass_count'] = sum(c['pass'] for c in h.report['checks'])
        write_json(folder / 'report.json', h.report)
    return success


def make_iso(elf, folder, log, timeout):
    """Only new files below invocation-owned dist/<unique> are ever written."""
    stage = folder / 'stage'
    grub = stage / 'boot/grub'
    grub.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(elf, stage / 'boot/rosti.bin')
    (grub / 'grub.cfg').write_text(
        'set timeout=0\nset default=0\nmenuentry "metadata fixture" {\n'
        ' multiboot /boot/rosti.bin\n boot\n}\n', encoding='ascii')
    iso = folder / 'fixture.iso'
    if shutil.which('grub-mkrescue'):
        command = ['grub-mkrescue', '-o', str(iso), str(stage)]
    elif shutil.which('wsl'):
        def wsl_path(path):
            path = path.resolve()
            if not path.drive:
                raise ValueError('WSL ISO build requires a drive-backed path')
            return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]
        command = ['wsl', 'bash', '-c', 'grub-mkrescue -o ' +
                   shlex.quote(wsl_path(iso)) + ' ' + shlex.quote(wsl_path(stage))]
    else:
        raise RuntimeError('HARNESS_FAIL: grub-mkrescue/WSL not found; no ISO substitution')
    with log.open('wb') as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)
    if not iso.is_file() or iso.stat().st_size == 0:
        raise RuntimeError('HARNESS_FAIL: empty/missing generated fixture ISO')
    return iso


class MetadataHarness(BlockHarness):
    def __init__(self, args, folder, deadline, manifest):
        super().__init__(args, folder, getattr(args, 'recovery_image', None), deadline)
        self.manifest = manifest
        self.report['fixture'] = manifest

    def start(self):
        from fs_test import QEMU, PROMPT
        executable = QEMU if Path(QEMU).is_file() else shutil.which('qemu-system-i386')
        if not executable:
            raise RuntimeError('HARNESS_FAIL: QEMU executable not found')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        boot = ['-cdrom', str(self.args.iso), '-boot', 'd'] if self.args.iso else [
            '-kernel', str(self.args.kernel)]
        command = [executable, *boot, '-machine', 'pc', '-m', str(self.args.ram),
                   '-display', 'none', '-nic', 'none', '-no-reboot', '-monitor', 'none',
                   '-serial', f'file:{self.serial}', '-qmp',
                   f'tcp:127.0.0.1:{port},server=on,wait=off', '-d', 'guest_errors',
                   '-D', str(self.run / 'qemu_log.txt')]
        if self.image is not None:
            command += ['-drive', f'file={self.image.as_posix()},format=raw,if=ide,index=0,cache=writeback']
        self.report['argv'] = command
        with (self.run / 'qemu_stderr.txt').open('wb') as error:
            self.proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error)
        self.report['qemu_pid'] = self.proc.pid
        while self.sock is None:
            self.remaining()
            try:
                self.sock = socket.create_connection(('127.0.0.1', port),
                                                     timeout=min(1, self.remaining()))
            except OSError:
                time.sleep(0.05)
        self.sock.settimeout(min(5, self.remaining()))
        self.stream = self.sock.makefile('rwb')
        self.check('QMP' in json.loads(self.stream.readline()), 'QMP greeting')
        self.qmp('qmp_capabilities')
        self.wait_boot(0)
        if self.args.iso or self.image is not None:
            blocks = self.qmp('query-block')
            self.report['query_block'] = blocks
        if self.image is not None:
            self.check(any(Path(b.get('inserted', {}).get('file', '')).resolve() ==
                           self.image.resolve() for b in blocks), 'exact disposable recovery image attached')
        if self.args.iso:
            self.check(any(Path(b.get('inserted', {}).get('file', '')).resolve() ==
                           self.args.iso.resolve() for b in blocks), 'exact disposable ISO attached')
        self.check(self.text().endswith(PROMPT), 'complete initial prompt')

    def physical(self, address, length, label):
        path = self.run / (label + '.bin')
        self.qmp('pmemsave', val=address, size=length, filename=path.as_posix())
        data = path.read_bytes()
        self.check(len(data) == length, label + ': exact physical capture length')
        return data

    def pte(self, directory, address, label):
        pde = struct.unpack('<I', self.physical(directory + (address >> 22) * 4,
                                                4, label + '_pde'))[0]
        if not pde & 1:
            return 0
        self.check(not pde & 0x80, label + ': 4 KiB page table')
        return struct.unpack('<I', self.physical((pde & ~4095) + ((address >> 12) & 1023) * 4,
                                                4, label + '_pte'))[0]

    def exercise_metadata(self):
        self.start()
        injected = bytes.fromhex(self.manifest['metadata_hex'])
        actual = self.physical(INFO, len(injected), 'injected_metadata')
        self.report['metadata_sha256'] = digest(actual)
        self.check(actual == injected, 'guest physical metadata exactly matches bounded fixture')
        name = self.manifest['name']
        rejected = name in REJECTED
        text = self.text()
        self.check(('ROSTI: boot metadata rejected:' in text) == rejected,
                   'metadata rejection matches fixture contract')
        if rejected:
            expected = {'invalidmagic': 'Magic', 'null': 'Address', 'headerbad': 'Address',
                        'mmaptruncated': 'Map', 'modulein-growth': 'Address',
                        'module-overlap': 'Module', 'countedoverflow': 'Limit'}[name]
            self.check(f'boot metadata rejected: {expected}; bootstrap-heap recovery' in text,
                       'precise bounded-parser rejection reason')
            self.check('DBG: frame init start' not in text and 'DBG: frame lock acquired' not in text,
                       'rejected inventory never initializes frame allocator')
            self.check('ROSTI: storage gate closed (boot metadata rejected)' in text,
                       'rejected inventory closes storage gate')
            self.check('ROSTI: block device present' not in text and
                       'ROSTI: RostiFS mounted at /mnt/rosti' not in text,
                       'rejected inventory never discovers device or mounts RostiFS')
            self.exact('disk', 'block: no device (IDENTIFY failed or 28-bit addressing unsupported)')
            self.exact('rostifs', 'RostiFS: not mounted (RAMFS recovery shell available)')
            self.exact('diskwrite 1', 'block: raw writes refused (boot metadata rejected)')
            stress = self.command('fsstress')
            self.check(stress.splitlines().count('fsstress: FAIL (out of memory)') == 1,
                       'rejected boot reaches bounded bootstrap-only OOM without growth')
            self.success('write /metadata-recovery.txt metadata-ramfs-recovery')
            self.exact('cat /metadata-recovery.txt', 'metadata-ramfs-recovery')
            self.success('rm /metadata-recovery.txt')
            self.exact('cat /metadata-recovery.txt', 'fs: not found')
        exhausted = name == 'frameexhaustion'
        paging = not rejected and not exhausted
        if exhausted:
            self.check('frame exhaustion during page table build' in text,
                       'B26 forced page-table exhaustion returns to shell')
        registers = self.qmp('human-monitor-command', **{'command-line': 'info registers'})
        self.report['registers'] = registers
        cr0 = re.search(r'\bCR0=([0-9a-fA-F]+)', registers)
        self.check(cr0 is not None and bool(int(cr0.group(1), 16) & 0x80000000) == paging,
                   'CPU CR0.PG agrees with expected paging state')
        out = self.command('mem')
        self.check(f"Paging: {'enabled' if paging else 'disabled'}" in out,
                   'shell reports expected paging state')
        self.check('Page faults: 0' in out and 'Invalid deallocs: 0' in out,
                   'no boot page faults or allocator corruption')
        if rejected:
            self.check('frame allocator: not initialized' in out,
                       'recovery shell has no initialized frame allocator')
            self.check('Growth pages: 0' in out,
                       'rejected recovery never claims a growth frame')
        if exhausted:
            self.check('Allocated frames: 0' in out and 'Free frames: 2' in out,
                       'B26 page-table failure returns every acquired frame')
        for label in ('Total frames', 'Free frames', 'Reserved frames', 'Allocated frames'):
            match = re.search(re.escape(label) + r':\s*(\d+)', out)
            if match:
                self.report.setdefault('frames', {})[label] = int(match.group(1))
        self.exact('echo metadata-alive', 'metadata-alive')
        before = None
        directory = None
        if paging:
            before = self.memory('before')
            match = re.search(r'Page directory:\s*(0x[0-9a-fA-F]+)', out)
            self.check(match is not None, 'page directory diagnostic parsed')
            directory = int(match.group(1), 16)
            self.check(not self.pte(directory, 0, 'null') & 1, 'null page remains absent')
        if name == 'validmodule':
            first = self.physical(MODULE, MODULE_SIZE, 'module_before')
            self.report['module_before_sha256'] = digest(first)
            self.check(digest(first) == self.manifest['module_sha256'],
                       'module payload matches deterministic source after paging')
            for offset in range(0, MODULE_SIZE, 4096):
                pte = self.pte(directory, MODULE + offset, f'module_{offset:x}')
                self.check((pte & ~4095) == MODULE + offset and pte & 1 and not pte & 4,
                           f'module page {offset:#x} pinned supervisor identity mapping')
        if name in ('nomodule', 'validmodule', 'reservedgrowth'):
            stress = self.command('fsstress')
            after = self.memory('after_stress')
            if name == 'reservedgrowth':
                self.check(stress.splitlines().count('fsstress: FAIL (out of memory)') == 1,
                           'one-byte competing reservation safely refuses stress allocation')
                self.check(after['growth_pages'] == before['growth_pages'] == 0 and
                           after['capacity'] == before['capacity'] and
                           after['failed_allocations'] > before['failed_allocations'],
                           'B11 blocked first growth slot cannot be claimed or skipped')
                self.check(not self.pte(directory, GROWTH, 'blocked_growth') & 1,
                           'reserved first growth page remains unmapped')
                self.check(after.get('fs_storage') == before.get('fs_storage') and
                           after.get('fs_entries') == before.get('fs_entries'),
                           'refused-growth stress cleans filesystem fixtures')
            else:
                self.check(stress.splitlines().count('fsstress: PASS') == 1,
                           'full fsstress succeeds with paging')
                self.check(after['growth_pages'] > before['growth_pages'],
                           'stress exercises actual heap growth')
            if name == 'validmodule':
                final = self.physical(MODULE, MODULE_SIZE, 'module_after')
                self.report['module_after_sha256'] = digest(final)
                self.check(digest(final) == self.report['module_before_sha256'] ==
                           self.manifest['module_sha256'], 'module bytes unchanged after fsstress/growth')
        self.exact('echo metadata-done', 'metadata-done')
        self.check(not re.search(r'PANIC:|page fault:|CPU exception', self.text()),
                   'no kernel fault through completed workflow')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path,
                        help='absolute evidence parent; unique child created per invocation')
    parser.add_argument('--kernel', type=Path, default=PROJECT / 'target/target/debug/kernel')
    parser.add_argument('--boot', choices=('elf', 'iso', 'both'), default='both')
    parser.add_argument('--ram', nargs='+', type=int, choices=(128, 512), default=[128, 512])
    parser.add_argument('--fixture', action='append', choices=FIXTURES,
                        help='focused diagnostics only; default is the complete fixture matrix')
    parser.add_argument('--timeout', type=float, default=1800, help='whole invocation deadline')
    parser.add_argument('--guest-timeout', type=float, default=90)
    args = parser.parse_args(argv)
    if not args.output_dir.is_absolute():
        parser.error('--output-dir must be absolute')
    if args.timeout <= 0 or args.guest_timeout <= 0:
        parser.error('timeouts must be positive')
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='boot_metadata_', dir=root))
    report = {'overall': 'FAIL', 'checks': [], 'scenarios': [], 'evidence': str(run)}
    write_json(run / 'report.json', report)
    started = time.monotonic()
    deadline = started + args.timeout
    owned = None
    original = None
    def check(value, name, **details):
        report['checks'].append({'name': name, 'pass': bool(value), **details})
        if not value:
            raise AssertionError(name)
    try:
        original = args.kernel.read_bytes()
        report['kernel'] = str(args.kernel.resolve())
        report['kernel_sha256'] = digest(original)
        parse_elf(original)
        check(True, 'source kernel ELF validated; no production build performed')
        dist = PROJECT / 'dist'
        dist.mkdir(exist_ok=True)
        owned = Path(tempfile.mkdtemp(prefix='boot_metadata_', dir=dist)).resolve()
        report['owned_stage'] = str(owned)
        modes = ('elf', 'iso') if args.boot == 'both' else (args.boot,)
        rams = list(dict.fromkeys(args.ram))
        fixtures = list(dict.fromkeys(args.fixture or FIXTURES))
        report['expected_scenarios'] = len(modes) * len(rams) * len(fixtures)
        for ram in rams:
            for name in fixtures:
                if time.monotonic() >= deadline:
                    raise TimeoutError('whole invocation deadline exceeded')
                artifact = owned / f'{ram}_{name}'
                artifact.mkdir()
                data, manifest = build_fixture(original, name, ram)
                elf = artifact / 'fixture.elf'
                with elf.open('xb') as stream:
                    stream.write(data)
                recovery_image = None
                if name in REJECTED:
                    recovery_image = artifact / 'owned.raw'
                    with recovery_image.open('xb') as stream:
                        stream.truncate(1024 * 1024)
                        stream.write(b'ROSTI-TESTDISK')
                manifest['fixture_sha256'] = digest(data)
                manifest['source_sha256'] = report['kernel_sha256']
                write_json(run / f'{ram}_{name}_manifest.json', manifest)
                iso = None
                if 'iso' in modes:
                    iso = make_iso(elf, artifact, run / f'{ram}_{name}_iso_build.log',
                                   max(0.01, deadline - time.monotonic()))
                    manifest['iso_sha256'] = digest(iso.read_bytes())
                    write_json(run / f'{ram}_{name}_manifest.json', manifest)
                for mode in modes:
                    folder = run / f'{mode}_{ram}_{name}'
                    folder.mkdir()
                    case_args = SimpleNamespace(ram=ram, iso=iso if mode == 'iso' else None,
                                                kernel=elf, timeout=args.guest_timeout,
                                                live=None, stress=False, recovery_image=recovery_image)
                    h = MetadataHarness(case_args, folder,
                                        min(deadline, time.monotonic() + args.guest_timeout), manifest)
                    passed = run_scenario(h, folder, lambda guest: guest.exercise_metadata())
                    report['scenarios'].append({'name': name, 'boot': mode, 'ram_mib': ram,
                                                'overall': 'PASS' if passed else 'FAIL',
                                                'report': str(folder / 'report.json')})
                    report['checks'].append({'name': f'{mode}/{ram}/{name}', 'pass': passed})
                    write_json(run / 'report.json', report)
                    if not h.report.get('owned_qemu_exited'):
                        raise RuntimeError('owned guest could not be reaped; refusing another launch')
        check(len(report['scenarios']) == report['expected_scenarios'], 'complete requested matrix')
        # Compare exact same synthetic maps/metadata pages, with only module pins added.
        for mode in modes:
            for ram in rams:
                if 'nomodule' in fixtures and 'validmodule' in fixtures:
                    base = json.loads((run / f'{mode}_{ram}_nomodule/report.json').read_text())
                    mod = json.loads((run / f'{mode}_{ram}_validmodule/report.json').read_text())
                    check(base.get('frames', {}).get('Reserved frames') is not None and
                          mod.get('frames', {}).get('Reserved frames', 0) >=
                          base['frames']['Reserved frames'] + MODULE_SIZE // 4096,
                          f'{mode}/{ram}: live module frames reserved beyond no-module baseline')
        check(all(c['pass'] for c in report['checks']), 'all guest checks pass')
        report['overall'] = 'PASS'
    except (Exception, KeyboardInterrupt) as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['checks'].append({'name': 'invocation completed without setup/workload failure', 'pass': False})
    finally:
        if original is not None:
            try:
                unchanged = digest(args.kernel.read_bytes()) == digest(original)
                check(unchanged, 'production ELF unchanged', sha256=digest(original))
            except Exception as error:
                report['overall'] = 'FAIL'
                report['preservation_error'] = str(error)
        if owned is not None:
            try:
                shutil.rmtree(owned)
                check(not owned.exists(), 'owned dist staging removed')
            except Exception as error:
                report['overall'] = 'FAIL'
                report['cleanup_error'] = str(error)
                report['checks'].append({'name': 'owned dist staging removed', 'pass': False})
        report['elapsed_s'] = round(time.monotonic() - started, 3)
        report['scenario_count'] = len(report['scenarios'])
        report['check_count'] = len(report['checks'])
        report['pass_count'] = sum(c['pass'] for c in report['checks'])
        if not report['checks'] or not all(c['pass'] for c in report['checks']):
            report['overall'] = 'FAIL'
        write_json(run / 'report.json', report)
    print(f"{report['overall']}: boot metadata {report['pass_count']}/{report['check_count']}; {run}")
    return 0 if report['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
