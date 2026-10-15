"""Host-only tests: never build a kernel, start QEMU, or alter accepted media."""
import importlib.util
import hashlib
from pathlib import Path
import struct
from unittest import mock
import json
import types
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def tiny_elf():
    data = bytearray(4096)
    data[:16] = b'\x7fELF\x01\x01\x01' + bytes(9)
    struct.pack_into('<HHIIIIIHHHHHH', data, 16, 2, 3, 1, 0x100080, 52, 0, 0,
                     52, 32, 1, 40, 0, 0)
    struct.pack_into('<8I', data, 52, 1, 0, 0x100000, 0x100000, 4096, 8192, 5, 4096)
    struct.pack_into('<3I', data, 128, 0x1badb002, 3, (-0x1badb002 - 3) & 0xffffffff)
    return bytes(data)


class FixtureTests(unittest.TestCase):
    def test_large_elf_keeps_program_header_table_in_grub_search_window(self):
        m = self.module()
        original = tiny_elf() + bytes(65536)
        fixture, _ = m.build_fixture(original, 'nomodule', 128)
        offset = struct.unpack_from('<I', fixture, 28)[0]
        stride, count = struct.unpack_from('<HH', fixture, 42)
        self.assertLessEqual(offset + stride * count, 8192,
                             'GRUB rejects program headers at high file offsets')
        section_offset = struct.unpack_from('<I', fixture, 32)[0]
        section_stride, section_count = struct.unpack_from('<HH', fixture, 46)
        self.assertGreaterEqual(section_offset, 52)
        self.assertEqual((section_stride, section_count), (40, 1))
        self.assertEqual(fixture[section_offset:section_offset + 40], bytes(40))

    def module(self):
        spec = importlib.util.find_spec('boot_metadata_test')
        self.assertIsNotNone(spec, 'fixture generator must exist')
        import boot_metadata_test
        return boot_metadata_test

    def test_append_only_loads_preserve_original_and_entry(self):
        m = self.module()
        original = tiny_elf()
        fixture, manifest = m.build_fixture(original, 'nomodule', 128)
        old = m.parse_elf(original)
        new = m.parse_elf(fixture)
        for before, after in zip(old['segments'], new['segments']):
            self.assertEqual((after[0], *after[2:]), (before[0], *before[2:]))
            self.assertEqual(fixture[after[1]:after[1] + after[4]],
                             original[before[1]:before[1] + before[4]])
        self.assertEqual(new['entry'], 32 * 1024 * 1024)
        tramp = new['segments'][-1]
        self.assertEqual(tramp[3], new['entry'])
        self.assertEqual(manifest['original_entry'], old['entry'])
        code = fixture[tramp[1]:tramp[1] + manifest['code_size']]
        self.assertTrue(code.startswith(b'\xfa\xfc\xbe'))
        self.assertIn(b'\xf3\xa4\xbb\x00\x00\x07\x00\xe9', code)
        displacement = struct.unpack_from('<i', code, len(code)-4)[0]
        self.assertEqual(new['entry'] + len(code) + displacement, old['entry'])
        self.assertEqual(fixture[new['segments'][0][1] + 128:
                                 new['segments'][0][1] + 140], original[128:140])

    def test_metadata_matrix_and_module_segment(self):
        m = self.module()
        for ram in (128, 512):
            for name in m.FIXTURES:
                with self.subTest(ram=ram, name=name):
                    data, manifest = m.build_fixture(tiny_elf(), name, ram)
                    header = bytes.fromhex(manifest['metadata_hex'])
                    segments = m.parse_elf(data)['segments']
                    self.assertEqual(manifest['expected_rejection'], name in m.REJECTED)
                    self.assertEqual(manifest['info'], 0 if name == 'null' else
                                     0x9fff0 if name == 'headerbad' else m.INFO)
                    self.assertEqual(manifest['magic'], 0xdeadbeef if name == 'invalidmagic' else m.MAGIC)
                    count, table = struct.unpack_from('<II', header, 20)
                    if name == 'countedoverflow':
                        self.assertEqual(count, 0xffffffff)
                    if name == 'mmaptruncated':
                        self.assertEqual(struct.unpack_from('<I', header, 44)[0] % 24, 23)
                    if name == 'modulein-growth':
                        self.assertEqual(struct.unpack_from('<I', header, 0x400)[0], m.GROWTH)
                    if name == 'module-overlap':
                        self.assertEqual(count, 2)
                        self.assertEqual(header[0x400:0x410], header[0x410:0x420])
                    if name == 'reservedgrowth':
                        self.assertIn(struct.pack('<IQQI', 20, m.GROWTH, 1, 2), header)
                    if name == 'frameexhaustion':
                        self.assertEqual(manifest['free_pool_bytes'], 8192)
                    if name == 'validmodule':
                        segment = next(p for p in segments if p[3] == m.MODULE)
                        payload = data[segment[1]:segment[1] + segment[4]]
                        self.assertEqual(len(payload), 65536)
                        self.assertEqual(payload, bytes(i % 251 for i in range(65536)))
                        self.assertEqual(manifest['module_sha256'], m.digest(payload))
                    mmap_len = struct.unpack_from('<I', header, 44)[0]
                    if name != 'mmaptruncated':
                        high = struct.unpack_from('<IQQI', header, 0x100 + 48)
                        self.assertEqual(high[1] + high[2], ram * 1024 * 1024 - 65536)

    def test_invalid_elf_and_occupied_fixture_addresses_refused(self):
        m = self.module()
        for bad in (b'', tiny_elf()[:60]):
            with self.assertRaises(ValueError):
                m.build_fixture(bad, 'nomodule', 128)
        for address in (m.MODULE, m.TRAMPOLINE, m.GROWTH):
            bad = bytearray(tiny_elf())
            struct.pack_into('<I', bad, 52 + 20, address + 8192 - 0x100000)
            with self.subTest(address=address), self.assertRaises(ValueError):
                m.build_fixture(bytes(bad), 'validmodule', 128)

    def test_failed_probe_writes_nonempty_fail_report_without_launch(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(m, 'MetadataHarness', create=True) as harness, mock.patch('builtins.print'):
                status = m.main(['--output-dir', str(root), '--boot', 'elf',
                                 '--kernel', str(root / 'missing.elf')])
            self.assertEqual(status, 1)
            harness.assert_not_called()
            reports = list(root.glob('*/report.json'))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertEqual(report['overall'], 'FAIL')
            self.assertTrue(report['checks'])
            self.assertTrue(any(not row['pass'] for row in report['checks']))

    def test_cleanup_failure_cannot_publish_pass_and_fallback_reaps(self):
        m = self.module()
        proc = mock.Mock()
        proc.poll.side_effect = [None, 0]
        h = types.SimpleNamespace(report={'overall': 'FAIL', 'checks': []}, proc=proc,
                                  close=mock.Mock(side_effect=OSError('close failed')))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result = m.run_scenario(h, folder, lambda harness: None)
            report = json.loads((folder / 'report.json').read_text())
            self.assertFalse(result)
            self.assertEqual(report['overall'], 'FAIL')
            self.assertIn('close failed', report['cleanup_error'])
            self.assertTrue(report['owned_qemu_exited'])
            proc.kill.assert_called_once()
            proc.wait.assert_called_once()

    def test_scenario_exception_is_preserved_with_cleanup_evidence(self):
        m = self.module()
        h = types.SimpleNamespace(report={'overall': 'FAIL', 'checks': []}, proc=None,
                                  close=mock.Mock())
        def fail(harness):
            raise ValueError('workload failure')
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(m.run_scenario(h, Path(directory), fail))
            report = json.loads((Path(directory) / 'report.json').read_text())
            self.assertIn('workload failure', report['error'])
            self.assertTrue(report['checks'])
            self.assertTrue(report['owned_qemu_exited'])

    def test_empty_workload_checks_cannot_publish_pass(self):
        m = self.module()
        h = types.SimpleNamespace(report={'overall': 'FAIL', 'checks': []}, proc=None,
                                  close=mock.Mock())
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(m.run_scenario(h, Path(directory), lambda harness: None))

    def test_full_matrix_report_and_stage_cleanup_without_qemu(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / 'kernel.elf'
            kernel.write_bytes(tiny_elf())
            def fake_iso(elf, folder, log, timeout):
                path = folder / 'fixture.iso'
                path.write_bytes(b'owned fake ISO for host control-flow test only')
                return path
            class FakeHarness:
                def __init__(self, args, folder, deadline, manifest):
                    self.proc = None
                    self.report = {'overall': 'FAIL', 'checks': [], 'frames':
                                   {'Reserved frames': 100 + (16 if manifest['name'] == 'validmodule' else 0)}}
                def exercise_metadata(self):
                    self.report['checks'].append({'name': 'mocked guest, not live acceptance', 'pass': True})
                def close(self):
                    pass
            with mock.patch.object(m, 'PROJECT', root), mock.patch.object(m, 'make_iso', side_effect=fake_iso), \
                 mock.patch.object(m, 'MetadataHarness', FakeHarness), mock.patch('builtins.print'):
                status = m.main(['--output-dir', str(root / 'evidence'), '--kernel', str(kernel)])
            self.assertEqual(status, 0)
            report = json.loads(next((root / 'evidence').glob('*/report.json')).read_text())
            self.assertEqual(report['overall'], 'PASS')
            self.assertEqual(report['expected_scenarios'], 44)
            self.assertEqual(report['scenario_count'], 44)
            self.assertEqual(report['check_count'], len(report['checks']))
            self.assertTrue(all(c['pass'] for c in report['checks']))
            self.assertEqual(kernel.read_bytes(), tiny_elf())
            self.assertFalse(Path(report['owned_stage']).exists())

    def test_full_image_hash_is_checked_after_cleanup_and_process_wait(self):
        m = self.module()
        for change in ('none', 'workload_tail', 'close_tail', 'wait_tail', 'unreaped', 'missing'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                image = folder / 'owned.raw'
                original = b'ROSTI-TESTDISK' + bytes(8192)
                image.write_bytes(original)
                before = hashlib.sha256(original).hexdigest()
                proc = mock.Mock()
                proc.poll.return_value = None
                def mutate():
                    with image.open('r+b') as stream:
                        stream.seek(-1, 2)
                        stream.write(b'X')
                def wait(**kwargs):
                    if change == 'unreaped':
                        raise RuntimeError('mock process still running')
                    if change == 'wait_tail':
                        mutate()
                    proc.poll.return_value = 0
                # No real process is launched, including the failure-to-reap branch.
                proc.wait.side_effect = wait
                def close():
                    if change == 'close_tail':
                        mutate()
                    if change == 'missing':
                        image.unlink()
                h = types.SimpleNamespace(report={'checks': []}, image=image, proc=proc, close=close)
                def exercise(guest):
                    self.assertEqual(guest.report['recovery_image_before_sha256'], before)
                    guest.report['checks'].append({'name': 'mocked workload', 'pass': True})
                    if change == 'workload_tail':
                        mutate()
                result = m.run_scenario(h, folder, exercise)
                report = json.loads((folder / 'report.json').read_text())
                self.assertEqual(result, change == 'none')
                self.assertEqual(report['overall'], 'PASS' if change == 'none' else 'FAIL')
                self.assertEqual(report['recovery_image_before_sha256'], before)
                proc.wait.assert_called_once_with(timeout=5)
                if change in ('unreaped', 'missing'):
                    self.assertNotIn('recovery_image_after_sha256', report)
                    self.assertIn('recovery_image_error', report)
                else:
                    self.assertEqual(report['recovery_image_after_sha256'],
                                     hashlib.sha256(image.read_bytes()).hexdigest())
                    self.assertEqual(report['recovery_image_after_sha256'] == before,
                                     change == 'none')
                if change == 'unreaped':
                    self.assertFalse(report['owned_qemu_exited'])

    def test_rejected_workflow_checks_storage_gate_and_ramfs_lifecycle(self):
        m = self.module()
        reasons = {'invalidmagic': 'Magic', 'null': 'Address', 'headerbad': 'Address',
                   'mmaptruncated': 'Map', 'modulein-growth': 'Address',
                   'module-overlap': 'Module', 'countedoverflow': 'Limit'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in sorted(m.REJECTED):
                with self.subTest(name=name):
                    _, manifest = m.build_fixture(tiny_elf(), name, 128)
                    args = types.SimpleNamespace(ram=128, stress=False, timeout=90)
                    h = m.MetadataHarness(args, root, m.time.monotonic() + 90, manifest)
                    text = (f'ROSTI: boot metadata rejected: {reasons[name]}; bootstrap-heap recovery\n'
                            'ROSTI: storage gate closed (boot metadata rejected)\n')
                    files = {}
                    commands = []
                    def command(cmd):
                        commands.append(cmd)
                        if cmd == 'mem':
                            return ('Paging: disabled\nPage faults: 0\nInvalid deallocs: 0\n'
                                    'Growth pages: 0\nframe allocator: not initialized\n')
                        if cmd == 'fsstress':
                            return 'fsstress: FAIL (out of memory)\n'
                        if cmd == 'disk':
                            return 'block: no device (IDENTIFY failed or 28-bit addressing unsupported)\n'
                        if cmd == 'rostifs':
                            return 'RostiFS: not mounted (RAMFS recovery shell available)\n'
                        if cmd == 'diskwrite 1':
                            return 'block: raw writes refused (boot metadata rejected)\n'
                        if cmd.startswith('write '):
                            _, path, value = cmd.split(' ', 2)
                            files[path] = value
                            return ''
                        if cmd.startswith('cat '):
                            return files.get(cmd[4:], 'fs: not found') + '\n'
                        if cmd.startswith('rm '):
                            del files[cmd[3:]]
                            return ''
                        if cmd.startswith('echo '):
                            return cmd[5:] + '\n'
                        self.fail(f'unexpected mocked guest command: {cmd}')
                    with mock.patch.object(h, 'start'), \
                         mock.patch.object(h, 'physical', return_value=bytes.fromhex(manifest['metadata_hex'])), \
                         mock.patch.object(h, 'qmp', return_value='CR0=00000011'), \
                         mock.patch.object(h, 'text', return_value=text), \
                         mock.patch.object(h, 'command', side_effect=command):
                        h.exercise_metadata()
                        self.assertTrue(all(row['pass'] for row in h.report['checks']))
                        bad_serial = (
                            text.replace('ROSTI: storage gate closed (boot metadata rejected)\n', ''),
                            text + 'ROSTI: block device present\n',
                            text + 'ROSTI: RostiFS mounted at /mnt/rosti\n',
                        )
                        for bad in bad_serial:
                            with mock.patch.object(h, 'text', return_value=bad), self.assertRaises(AssertionError):
                                h.exercise_metadata()
                    for cmd in ('disk', 'rostifs', 'diskwrite 1', 'fsstress',
                                'write /metadata-recovery.txt metadata-ramfs-recovery',
                                'cat /metadata-recovery.txt', 'rm /metadata-recovery.txt'):
                        self.assertIn(cmd, commands)
                    self.assertEqual(commands.count('cat /metadata-recovery.txt'), 2)
                    self.assertEqual(files, {})

    def test_metadata_start_attaches_exact_recovery_image_as_primary_ide(self):
        m = self.module()
        from fs_test import PROMPT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'owned.raw'
            image.write_bytes(b'host-only attachment test')
            for attached in (image, None):
                with self.subTest(attached=attached):
                    args = types.SimpleNamespace(ram=128, stress=False, timeout=90,
                                                 iso=None, kernel=root / 'fixture.elf',
                                                 recovery_image=attached)
                    h = m.MetadataHarness(args, root, m.time.monotonic() + 90, {'name': 'invalidmagic'})
                    sock = mock.Mock()
                    sock.makefile.return_value.readline.return_value = b'{"QMP": {}}\n'
                    blocks = [{'inserted': {'file': str(image)}}] if attached else []
                    with mock.patch.object(m.shutil, 'which', return_value='mock-qemu'), \
                         mock.patch.object(m.subprocess, 'Popen') as launch, \
                         mock.patch.object(m.socket, 'create_connection', return_value=sock), \
                         mock.patch.object(h, 'remaining', return_value=90), \
                         mock.patch.object(h, 'wait_boot'), mock.patch.object(h, 'text', return_value=PROMPT), \
                         mock.patch.object(h, 'qmp', return_value=blocks) as qmp:
                        h.start()
                    argv = launch.call_args.args[0]
                    if attached:
                        self.assertEqual(h.image, image)
                        self.assertEqual(argv[argv.index('-drive') + 1],
                                         f'file={image.as_posix()},format=raw,if=ide,index=0,cache=writeback')
                        qmp.assert_any_call('query-block')
                        self.assertEqual(h.report['query_block'], blocks)
                    else:
                        self.assertIsNone(h.image)
                        self.assertNotIn('-drive', argv)

    def test_rejected_main_supplies_exclusive_owned_media_only(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / 'kernel.elf'
            kernel.write_bytes(tiny_elf())
            seen = []
            class FakeHarness:
                def __init__(self, args, folder, deadline, manifest):
                    self.proc = None
                    self.image = args.recovery_image
                    self.report = {'checks': []}
                    seen.append((manifest['name'], self.image))
                    if self.image is not None:
                        self_test.assertEqual(self.image.name, 'owned.raw')
                        self_test.assertTrue(self.image.is_relative_to(root / 'dist'))
                        data = self.image.read_bytes()
                        self_test.assertGreaterEqual(len(data), 1024)
                        self_test.assertEqual(data[:512], b'ROSTI-TESTDISK' + bytes(512 - len(b'ROSTI-TESTDISK')))
                        with self_test.assertRaises(FileExistsError):
                            self.image.open('xb')
                def exercise_metadata(self):
                    self.report['checks'].append({'name': 'mocked workload', 'pass': True})
                def close(self):
                    pass
            self_test = self
            with mock.patch.object(m, 'PROJECT', root), \
                 mock.patch.object(m, 'MetadataHarness', FakeHarness), mock.patch('builtins.print'):
                status = m.main(['--output-dir', str(root / 'evidence'), '--kernel', str(kernel),
                                 '--boot', 'elf', '--ram', '128', '--fixture', 'invalidmagic',
                                 '--fixture', 'frameexhaustion'])
            self.assertEqual(status, 0)
            self.assertEqual([name for name, image in seen], ['invalidmagic', 'frameexhaustion'])
            self.assertIsNotNone(seen[0][1])
            self.assertIsNone(seen[1][1])
            report = json.loads(next((root / 'evidence').glob('*/elf_128_invalidmagic/report.json')).read_text())
            self.assertEqual(report['recovery_image_before_sha256'],
                             report['recovery_image_after_sha256'])
            self.assertTrue(report['owned_qemu_exited'])
            self.assertFalse(seen[0][1].exists())

    def test_iso_stage_never_reuses_accepted_iso(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accepted = root / 'rosti.iso'
            accepted.write_bytes(b'accepted immutable')
            folder = root / 'owned'
            folder.mkdir()
            elf = folder / 'fixture.elf'
            elf.write_bytes(tiny_elf())
            def rescue(argv, **kwargs):
                self.assertEqual(argv[0], 'grub-mkrescue')
                Path(argv[2]).write_bytes(b'generated ISO mock')
            with mock.patch.object(m.shutil, 'which', side_effect=lambda command: '/tools/grub-mkrescue'), \
                 mock.patch.object(m.subprocess, 'run', side_effect=rescue):
                iso = m.make_iso(elf, folder, root / 'build.log', 10)
            self.assertEqual(iso, folder / 'fixture.iso')
            self.assertEqual((folder / 'stage/boot/rosti.bin').read_bytes(), tiny_elf())
            self.assertIn('multiboot /boot/rosti.bin', (folder / 'stage/boot/grub/grub.cfg').read_text())
            self.assertEqual(accepted.read_bytes(), b'accepted immutable')


if __name__ == '__main__':
    unittest.main()
