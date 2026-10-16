#!/usr/bin/env python3
"""Phase10 trusted-initramfs guest matrix; the parent executes this harness.

Enumerates 14 cases x (elf|iso) x (128|512) MiB = 56 scenarios. Module
metadata is injected with the B13 pre-entry GDB helper (exact bytes, read back
by Gdb.write) at the ELF's _start, which for ISO boot happens after the real
GRUB handoff, so the same validated GRUB fields are retained for both boot
modes. The header copy keeps loader-owned optional fields byte-for-byte and
only sets/clears the module flag (bit 3) and module count/table fields.

Layout constants are deliberately bounded for both RAM sizes:
  header 0x70000, module table 16 MiB, label 16 MiB + 0x100,
  payload 17 MiB (second duplicate copy 18 MiB), descriptor reserved word
  0xfffffffc for loader compatibility.

Fixture mode symbols INITRAMFS_TEST_MODE 1/2/3 are promised by the parent's
dist/phase10b_fixture_kernel; mount-collision (1), mount-failure (2),
reboot-after-failure (2) and resource-exhaustion (3) use that binary.
Mode 3 exhausts the real privileged
allocator through fallible pressure buffers and requires recovered archive-build
OOM with all pressure released and used/live accounting restored. Its exact
recovery marker is mandatory; a fixture-failure marker fails the scenario.
Missing-storage and corrupt-rostifs both inject the trusted module and exercise
the trusted /system shell independently of unavailable persistent storage.
reboot-after-failure injects the unchanged trusted archive and fixture mode 2:
the first boot must release the unpublished snapshot and reject publication
with OutOfMemory, then prove the recovery namespace before the guest's own
'reboot' command (same process, no -no-reboot, no QMP system_reset).
The second boot reloads the fixture kernel's unmodified mode data (0xff) and
loader-native absent-module metadata, with no reinjection; it must show the
absent marker and pass the full recovery-shell workload.

Every scenario owns its cleanup and full-image hash; the aggregate report is
always written, even on exception. Production inputs (kernel, fixture kernel,
system/ assets, ISOs) are read only and never modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time

from b13_entry_inject import Gdb, elf_symbols
from block_test import BlockHarness, MAGIC
from boot_metadata_test import make_iso, run_scenario as run_boot_scenario
from build_initramfs import build, MAX_ARCHIVE_BYTES
from fs_test import PROJECT, PROMPT, QEMU, counters
from rostifs_test import console_only, missing

CASES = ('absent', 'trusted', 'bad-digest', 'truncated', 'malformed', 'oversize',
         'duplicate', 'invalid-descriptor', 'missing-storage', 'corrupt-rostifs',
         'mount-collision', 'mount-failure', 'resource-exhaustion',
         'reboot-after-failure')
INFO = 0x70000
TABLE = 16 * 1024 * 1024
LABEL = TABLE + 0x100
PAYLOAD = 17 * 1024 * 1024
SECOND = 18 * 1024 * 1024
HEADER_BYTES = 116
LABEL_BYTES = b'rosti.initramfs\0'
RESERVED_WORD = 0xfffffffc
MODES = {'mount-collision': 1, 'mount-failure': 2, 'resource-exhaustion': 3,
         'reboot-after-failure': 2}
SUCCESS_CASES = frozenset(('trusted', 'missing-storage', 'corrupt-rostifs'))
NO_MODULE_CASES = frozenset(('absent',))
TRUSTED_MARKER = 'ROSTI: initramfs trusted; mounted at /system'
OOM_MARKER = 'ROSTI: initramfs real allocator OOM recovered'
BOOT_MARKERS = ('ROSTI: entered kernel_main', 'ROSTI: boot complete')
ABSENT_MARKER = 'ROSTI: initramfs absent; RAMFS recovery'
DIGEST_MARKER = 'ROSTI: initramfs archive rejected: DigestMismatch; RAMFS recovery'
STORAGE_GATE_MARKER = 'ROSTI: storage gate closed (boot metadata rejected)'
CASE_OUTCOMES = {
    'absent': (ABSENT_MARKER,),
    'duplicate': ('ROSTI: initramfs ambiguous; RAMFS recovery',),
    'invalid-descriptor': ('ROSTI: boot metadata rejected: Module; bootstrap-heap recovery',
                           STORAGE_GATE_MARKER, ABSENT_MARKER),
    'oversize': ('ROSTI: initramfs copy rejected: Span; RAMFS recovery',),
    'mount-collision': ('ROSTI: unpublished initramfs snapshot released',
                        'ROSTI: initramfs publication rejected: not a directory; RAMFS recovery'),
    'mount-failure': ('ROSTI: unpublished initramfs snapshot released',
                      'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'),
    'reboot-after-failure': ('ROSTI: unpublished initramfs snapshot released',
                             'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'),
    'resource-exhaustion': (OOM_MARKER,
                            'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'),
    **{case: (DIGEST_MARKER,) for case in
       ('bad-digest', 'truncated', 'malformed')},
    **{case: (TRUSTED_MARKER,) for case in SUCCESS_CASES},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def matrix():
    return [dict(case=case, boot=boot, ram=ram) for case in CASES
            for boot in ('elf', 'iso') for ram in (128, 512)]


def marker_groups(case):
    """Exact, ordered outcomes; no cross-class rejection alternatives."""
    entered, complete = (BOOT_MARKERS[0],), (BOOT_MARKERS[1],)
    first = [entered, *((marker,) for marker in CASE_OUTCOMES[case]), complete]
    if case == 'reboot-after-failure':
        return first + [entered, (ABSENT_MARKER,), complete]
    return first


def injection_plan(case, original_header, archive):
    """Preserve loader-owned optional fields; replace only module fields.

    The descriptor's compatibility word is deliberately nonzero. Duplicate
    candidates occupy separate nonoverlapping buffers so ambiguity, not overlap,
    is what the kernel must reject. No out-of-RAM writes implement invalid input.
    """
    if case not in CASES or len(original_header) != HEADER_BYTES:
        raise ValueError('unknown case or incomplete Multiboot header')
    if not 0 < len(archive) <= MAX_ARCHIVE_BYTES:
        raise ValueError('trusted archive must be nonempty and bounded')
    header = bytearray(original_header)
    flags = struct.unpack_from('<I', header)[0] & ~8
    payload = bytes(archive)
    if case == 'bad-digest':
        payload = payload[:-1] + bytes([payload[-1] ^ 1])
    elif case == 'truncated':
        payload = payload[:max(1, len(payload) // 2)]
    elif case == 'malformed':
        payload = b'XXXXXX' + payload[6:]
    elif case == 'oversize':
        payload = payload + bytes(MAX_ARCHIVE_BYTES + 1 - len(payload))
    writes = []
    count = 0
    if case not in NO_MODULE_CASES:
        flags |= 8
        count = 2 if case == 'duplicate' else 1
        end = PAYLOAD if case == 'invalid-descriptor' else PAYLOAD + len(payload)
        table = struct.pack('<4I', PAYLOAD, end, LABEL, RESERVED_WORD)
        writes.extend([(LABEL, LABEL_BYTES), (PAYLOAD, payload)])
        if count == 2:
            table += struct.pack('<4I', SECOND, SECOND + len(payload), LABEL, RESERVED_WORD)
            writes.append((SECOND, payload))
        writes.append((TABLE, table))
    struct.pack_into('<I', header, 0, flags)
    struct.pack_into('<II', header, 20, count, TABLE if count else 0)
    writes.append((INFO, bytes(header)))
    return {'writes': writes, 'module_count': count, 'mode': MODES.get(case, 0),
            'payload_sha256': digest(payload) if count else None,
            'payload_bytes': len(payload) if count else 0,
            'archive_sha256': digest(archive)}


def system_assets():
    """Parent-owned production inputs; read only, never written by this harness."""
    root = PROJECT / 'system'
    expected = {
        'README.txt': b'Rosti trusted system image\n',
        'docs/recovery.txt': b'Recovery shell is kernel-owned.\n',
    }
    for name, content in expected.items():
        path = root / name
        if not path.is_file() or path.read_bytes() != content:
            raise FileNotFoundError(f'trusted system asset missing or altered: {path}')
    return build(root)


def owned_media(run):
    """Fresh owned corrupt marker image: MAGIC + zeros, 64 KiB exact geometry.

    No formatting needed: full geometry is invalid, so the RostiFS gate must
    reject it; the exact full hash must be unchanged after cleanup.
    """
    dist = PROJECT / 'dist'
    dist.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='phase10_media_', dir=dist)).resolve()
    image = directory / 'corrupt-rostifs.img'
    with image.open('xb') as stream:
        stream.write(MAGIC + bytes(64 * 1024 - len(MAGIC)))
    return directory, image


class PhaseHarness(BlockHarness):
    """One owned guest: RSP inject at _start, detach, then QMP shell.

    BlockHarness supplies the paced QMP keyboard, serial boundaries, VGA
    capture and scoped cleanup; this adds the pre-entry injection phase,
    marker-group checks, media attachment and latency samples.
    """

    def __init__(self, args, run, image, deadline, case, archive, mode_symbol):
        super().__init__(args, run, image, deadline)
        self.case = case
        self.archive = archive
        self.mode_symbol = mode_symbol
        self.groups = marker_groups(case)
        self.report['case'] = case
        self.report['latency'] = {'boot_s': None, 'shell_command_s': []}

    def command(self, typed, edit=False):
        started = time.monotonic()
        out = super().command(typed, edit)
        self.report['latency']['shell_command_s'].append(
            {'command': typed, 'seconds': round(time.monotonic() - started, 4)})
        return out

    def start(self):
        executable = QEMU if Path(QEMU).is_file() else shutil.which('qemu-system-i386')
        if not executable:
            raise RuntimeError('HARNESS_FAIL: QEMU executable not found')
        kernel = Path(self.args.kernel.resolve())
        boot = ['-cdrom', str(self.args.iso.resolve()), '-boot', 'd'] \
            if self.args.iso else ['-kernel', str(kernel)]
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            qmp_port = listener.getsockname()[1]
        with socket.socket() as rsp:
            rsp.bind(('127.0.0.1', 0))
            gdb_port = rsp.getsockname()[1]
        argv = [executable, *boot, '-machine', 'pc', '-m', str(self.args.ram),
                '-display', 'none', '-serial', f'file:{self.serial}', '-monitor', 'none',
                '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                '-d', 'guest_errors', '-D', str(self.run / 'qemu_log.txt')]
        if self.case != 'reboot-after-failure':
            argv += ['-no-reboot']
        if self.image is not None:
            argv += ['-drive', f'file={self.image.as_posix()},format=raw,if=ide,index=0,cache=writeback']
        argv += ['-S', '-gdb', f'tcp:127.0.0.1:{gdb_port}']
        self.report['argv'] = argv
        self.report['qmp_port'] = qmp_port
        self.report['gdb_port'] = gdb_port
        self.inject_at_entry(argv, gdb_port)
        # QMP attach after the RSP client detached; same owned process.
        deadline_qmp = self.deadline
        while self.sock is None:
            self.remaining()
            try:
                self.sock = socket.create_connection(('127.0.0.1', qmp_port), timeout=min(1, self.remaining()))
            except OSError:
                if time.monotonic() >= deadline_qmp:
                    raise
                time.sleep(0.05)
        self.sock.settimeout(min(5, self.remaining()))
        self.stream = self.sock.makefile('rwb')
        self.check('QMP' in json.loads(self.stream.readline()), 'QMP greeting')
        self.qmp('qmp_capabilities')
        self.wait_boot(0)
        if self.args.iso is not None:
            blocks = self.qmp('query-block')
            self.report['query_block'] = blocks
            self.check(any(Path(b.get('inserted', {}).get('file', '')).resolve()
                           == self.args.iso.resolve() for b in blocks),
                       'live runtime media is exactly the built ISO')
        if self.image is not None:
            blocks = self.report.get('query_block') or self.qmp('query-block')
            self.check(any(Path(b.get('inserted', {}).get('file', '')).resolve()
                           == self.image for b in blocks), 'QMP exact owned image attached')

    def inject_at_entry(self, argv, gdb_port):
        """Stop at _start (after GRUB handoff for ISO), inject exact bytes."""
        with (self.run / 'qemu_stderr.txt').open('wb') as stderr:
            self.proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=stderr)
        self.report['qemu_pid'] = self.proc.pid
        connection = None
        start = time.monotonic()
        deadline = self.deadline
        while connection is None:
            self.remaining()
            try:
                connection = socket.create_connection(('127.0.0.1', gdb_port), timeout=min(1, self.remaining()))
            except OSError:
                time.sleep(0.05)
        try:
            connection.settimeout(max(0.1, deadline - time.monotonic()))
            gdb = Gdb(connection)
            gdb.command('?')
            symbols = elf_symbols(self.args.kernel.resolve())
            address = symbols['_start']['address']
            if gdb.command(f'Z0,{address:x},1') != 'OK':
                raise RuntimeError('Entry breakpoint rejected')
            stopped = gdb.command('c')
            if not stopped.startswith(('T05', 'S05')):
                raise RuntimeError(f'Unexpected GDB stop: {stopped}')
            before = gdb.registers()
            if before['eip'] != address:
                raise RuntimeError('Did not stop at entry')
            self.report['entry'] = {'eip': address, 'eax': hex(before['eax']),
                                    'ebx': hex(before['ebx'])}
            if gdb.command(f'z0,{address:x},1') != 'OK':
                raise RuntimeError('Entry breakpoint removal rejected')
            header = gdb.read(before['ebx'], HEADER_BYTES)
            plan = injection_plan(self.case, header, self.archive)
            self.plan = plan
            self.report['fixture'] = {
                'case': self.case, 'mode': plan['mode'], 'module_count': plan['module_count'],
                'payload_sha256': plan['payload_sha256'], 'payload_bytes': plan['payload_bytes'],
                'archive_sha256': plan['archive_sha256'],
                'injection': [{'address': hex(a), 'bytes_sha256': digest(d), 'length': len(d)}
                              for a, d in plan['writes']],
            }
            for address, data in plan['writes']:
                gdb.write(address, data)
            if plan['mode']:
                if (not isinstance(self.mode_symbol, dict)
                        or type(self.mode_symbol.get('address')) is not int
                        or self.mode_symbol.get('size') != 1):
                    raise KeyError('fixture mode symbol INITRAMFS_TEST_MODE required')
                mode_address = self.mode_symbol['address']
                gdb.write(mode_address, bytes([plan['mode']]))
                if gdb.read(mode_address, 1) != bytes([plan['mode']]):
                    raise RuntimeError('Fixture mode byte readback mismatch')
            # Gdb.set_registers patches and reads back the full i386 packet.
            gdb.set_registers(ebx=INFO)
            after = gdb.registers()
            if after['eax'] != before['eax'] or after['ebx'] != INFO:
                raise RuntimeError('Loader EAX or injected header EBX mismatch')
            self.report['entry_eax_preserved'] = True
            self.report['entry_ebx_redirected'] = True
            self.report['entry_after'] = {'eax': hex(after['eax']), 'ebx': hex(after['ebx'])}
            if gdb.command('D') != 'OK':
                raise RuntimeError('GDB detach rejected')
        finally:
            try:
                connection.close()
            except Exception as error:
                self.report['rsp_cleanup_error'] = str(error)
        boot_started = time.monotonic()
        self.wait(lambda: BOOT_MARKERS[1] in self.text(), 'boot complete marker', seconds=60)
        self.report['latency']['boot_s'] = round(time.monotonic() - boot_started, 3)

    def wait_boot(self, start):
        self.wait(lambda: self.text()[start:].endswith(PROMPT), 'boot shell prompt', seconds=60)
        text = self.text()[start:]
        self.check(0 <= text.find(BOOT_MARKERS[0]) < text.find(BOOT_MARKERS[1]), 'ordered boot markers')
        self.check('PANIC:' not in text and 'PAGE FAULT' not in text, 'no boot panic/fault')

    def markers(self, start=0, rebooted=True):
        text = self.text()[start:]
        self.check('OOM fixture FAILED' not in text, 'no initramfs OOM fixture failure')
        self.check('initramfs rollback accounting FAILED' not in text, 'no rollback accounting failure')
        lines = text.splitlines()
        self.check((STORAGE_GATE_MARKER in lines) == (self.case == 'invalid-descriptor'),
                   'storage gate closes only for invalid boot inventory')
        if self.case == 'invalid-descriptor':
            self.check('ROSTI: block device present' not in text and
                       'ROSTI: RostiFS mounted at /mnt/rosti' not in text,
                       'invalid inventory never discovers or mounts persistent storage')
        if self.case not in SUCCESS_CASES:
            self.check(TRUSTED_MARKER not in text, 'no trusted publication anywhere in refusal transcript')
        cursor = 0
        groups = self.groups if rebooted else self.groups[:len(CASE_OUTCOMES[self.case]) + 2]
        for group in groups:
            found = next((i for i in range(cursor, len(lines)) if lines[i] in group), -1)
            self.check(found >= 0, f'ordered exact marker group {group!r}')
            cursor = found + 1
        # Reject conflicting or extra outcomes, not merely a matching subsequence.
        relevant = [line for line in lines if line.startswith((
            'ROSTI: initramfs ', 'ROSTI: unpublished initramfs ',
            'ROSTI: boot metadata rejected', 'ROSTI: storage gate closed'))]
        expected = list(CASE_OUTCOMES[self.case])
        if self.case == 'reboot-after-failure' and rebooted:
            expected.append(ABSENT_MARKER)
        self.check(relevant == expected, 'exact outcome/error and storage policy sequence')

    def guest_reboot(self):
        start = len(self.text())
        self.type_text('reboot')
        self.key('ret')
        self.wait(lambda: BOOT_MARKERS[0] in self.text()[start:], 'guest reboot enters kernel', seconds=40)
        self.wait_boot(start)
        self.report['guest_reboot'] = True

    def refused_namespace(self):
        self.check(TRUSTED_MARKER not in self.text(), 'refused image never published')
        if self.case == 'mount-collision':
            # Exact bytes also prove this is still the original RAM file, not a directory.
            self.exact('cat /system', 'collision sentinel')
        else:
            missing(self, '/system')

    def recovery_shell(self):
        self.refused_namespace()
        self.exact('pwd', '/')
        self.success('mkdir recovery')
        self.success('write /recovery.txt Recovery RAMFS')
        self.exact('cat /recovery.txt', 'Recovery RAMFS')
        self.success('rm /recovery.txt')
        missing(self, '/recovery.txt')
        console_only(self)
        self.refused_namespace()
        self.check(not re.search(r'PANIC:|page fault:|CPU exception', self.text()),
                   'recovery shell remains fault-free')

    def trusted_shell(self):
        self.exact('pwd', '/')
        self.exact('ls /system', 'README.txt\ndocs/')
        self.exact('cat /system/README.txt', 'Rosti trusted system image')
        self.exact('ls /system/docs', 'recovery.txt')
        self.exact('cat /system/docs/recovery.txt', 'Recovery shell is kernel-owned.')
        for command in (
                'write /system/README.txt x', 'append /system/README.txt x',
                'touch /system/guard.txt', 'mkdir /system/guard',
                'rm /system/README.txt', 'rmdir /system/docs'):
            out = self.command(command)
            self.check(bool(re.search(r'read.?only', out, re.IGNORECASE)),
                       f'{command.split()[0]} on trusted mount rejected')
        self.exact('ls /system', 'README.txt\ndocs/')
        self.success('mkdir media')
        self.success('write /media.txt local RAMFS')
        self.exact('cat /media.txt', 'local RAMFS')
        self.success('rm /media.txt')
        missing(self, '/media.txt')
        console_only(self)

    def memory_diagnostics(self, label):
        if self.case != 'invalid-descriptor':
            # Inherited diagnostics retain heap/growth/allocation counters and
            # assert paging, zero faults and zero invalid deallocations.
            values = self.memory(label)
            self.system_diagnostics(label, self.command('mem'))
            return values
        # Invalid inventory intentionally never enables paging. Do not claim
        # an enabled-paging pass or discard the bootstrap heap counters.
        out = self.command('mem')
        self.check('Paging: disabled' in out, f'mem {label}: rejected inventory leaves paging off')
        self.check('Page faults: 0' in out and 'Invalid deallocs: 0' in out,
                   f'mem {label}: no faults or invalid deallocations')
        values = counters(out)
        self.check(all(k in values for k in ('used', 'capacity', 'growth_pages', 'failed_allocations')),
                   f'mem {label}: bootstrap heap counters parsed')
        self.check(values['growth_pages'] == 0, f'mem {label}: rejected inventory cannot grow heap')
        self.report['memory'][label] = values
        self.system_diagnostics(label, out)
        return values

    def system_diagnostics(self, label, out):
        values = {}
        if self.case in SUCCESS_CASES:
            self.check('System mount: absent' not in out, 'trusted system is accounted as mounted')
            for name in ('System nodes', 'System logical bytes', 'System payload capacity', 'System metadata'):
                match = re.search(r'^' + re.escape(name) + r':\s*(\d+)\b', out, re.MULTILINE)
                self.check(match is not None, f'{name}: parsed')
                values[name] = int(match[1])
                self.check(values[name] > 0, f'{name}: nonempty trusted image accounting')
        else:
            self.check('System mount: absent' in out.splitlines() and 'System nodes:' not in out,
                       'diagnostics prove no system publication')
            values['mounted'] = False
        self.report.setdefault('system_memory', {})[label] = values


def exercise_for(case):
    """Shell workload per expected outcome (fixture modes are recovery)."""
    if case in SUCCESS_CASES:
        return 'trusted'
    return 'recovery'


def run_scenario(harness, folder, exercise):
    """Adapt shared scoped cleanup evidence to the strict Phase10 contract."""
    success = run_boot_scenario(harness, folder, exercise)
    report = harness.report
    report['cleanup'] = report.get('owned_qemu_exited') is True and not any(
        name in report for name in ('cleanup_error', 'fallback_cleanup_error', 'rsp_cleanup_error'))
    report['checks'].append({'name': 'Phase10 scoped cleanup verified',
                             'pass': report['cleanup']})
    success = success and report['cleanup']
    report['overall'] = 'PASS' if success else 'FAIL'
    report['check_count'] = len(report['checks'])
    report['pass_count'] = sum(c['pass'] for c in report['checks'])
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return success


def scenario_folder(run, row):
    return run / f"{row['boot']}_{row['ram']}_{row['case']}"


def run_one(args, run, row, archive, image, deadline):
    case, boot, ram = row['case'], row['boot'], row['ram']
    folder = scenario_folder(run, row)
    folder.mkdir()
    args = argparse.Namespace(**vars(args))
    args.ram = ram
    fixture = case in MODES
    kernel = args.fixture_kernel.resolve() if fixture else args.kernel.resolve()
    args.kernel = kernel
    args.iso = None
    if boot == 'iso':
        args.iso = make_iso(kernel, folder, folder / 'grub_build.log',
                            max(10, min(180, deadline - time.monotonic())))
    mode_symbol = None
    if fixture:
        mode_symbol = elf_symbols(kernel)['INITRAMFS_TEST_MODE']
    # Never reuse media across scenarios, including successive refusal classes.
    image = None if case == 'missing-storage' else owned_media(folder)[1]
    h = PhaseHarness(args, folder, image, deadline, case, archive, mode_symbol)

    def exercise(harness):
        harness.start()
        if case == 'reboot-after-failure':
            harness.markers(0, rebooted=False)
            harness.refused_namespace()
            harness.guest_reboot()
        harness.markers(0)
        workload = exercise_for(case)
        if workload == 'trusted':
            harness.trusted_shell()
        else:
            harness.recovery_shell()
        missing(harness, '/mnt/rosti')
        harness.memory_diagnostics('final')
        harness.markers(0)

    return run_scenario(h, folder, exercise)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--kernel', type=Path, default=PROJECT / 'target/target/debug/kernel')
    parser.add_argument('--fixture-kernel', type=Path,
                        default=PROJECT / 'dist/phase10b_fixture_kernel')
    parser.add_argument('--timeout', type=float, default=3600)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('timeout must be positive')
    args.live = None
    args.stress = False
    args.iso = None
    root = (args.output_dir or PROJECT / 'test_results/phase10').resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d_%H%M%S_') + 'phase10_', dir=root))
    started = time.monotonic()
    deadline = started + args.timeout
    report = {'overall': 'FAIL', 'scenarios': [], 'checks': [], 'inputs': {},
              'expected_scenarios': len(matrix()), 'scenario_count': 0}
    try:
        kernel, fixture_kernel = args.kernel.resolve(), args.fixture_kernel.resolve()
        archive = system_assets()

        report['inputs'] = {
            'kernel': str(kernel), 'kernel_sha256': digest(kernel.read_bytes()),
            'fixture_kernel': str(fixture_kernel),
            'fixture_kernel_sha256': digest(fixture_kernel.read_bytes()),
            'system_archive_sha256': digest(archive),
            'system_archive_bytes': len(archive),

        }
        rows = matrix()
        for row in rows:
            success = run_one(args, run, row, archive, None, deadline)
            folder = scenario_folder(run, row)
            with (folder / 'report.json').open('r', encoding='utf-8') as stream:
                scenario_report = json.load(stream)
            report['scenarios'].append({'case': row['case'], 'boot': row['boot'],
                                        'ram_mib': row['ram'], 'overall': scenario_report['overall'],
                                        'cleanup': scenario_report.get('cleanup') is True,
                                        'report': str(folder / 'report.json')})
            report['checks'].extend({'name': f"{row['case']}_{row['boot']}_ram{row['ram']}: "
                                            f"{c['name']}", 'pass': c['pass']}
                                    for c in scenario_report['checks'])
            report['checks'].append({'name': f"{row['case']}_{row['boot']}_ram{row['ram']}: scenario completed",
                                     'pass': bool(success)})

        report['checks'].append({'name': 'all 56 scenarios enumerated',
                                 'pass': len(report['scenarios']) == 56})
        report['checks'].append({'name': 'every scenario report present and nonempty checks',
                                 'pass': all(s['overall'] in ('PASS', 'FAIL') for s in report['scenarios'])})
        report['checks'].append({'name': 'all scenarios passed',
                                 'pass': all(s['overall'] == 'PASS' for s in report['scenarios'])})
        report['overall'] = 'PASS' if all(c['pass'] for c in report['checks']) else 'FAIL'
    except (Exception, KeyboardInterrupt) as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        report['elapsed_s'] = round(time.monotonic() - started, 3)
        report['scenario_count'] = len(report['scenarios'])
        report['check_count'] = len(report['checks'])
        report['pass_count'] = sum(c['pass'] for c in report['checks'])
        (run / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['overall']}: phase10 initramfs matrix {report['pass_count']}/"
          f"{report['check_count']} checks; evidence: {run}")
    if 'error' in report:
        print(report['error'])
    return 0 if report['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
