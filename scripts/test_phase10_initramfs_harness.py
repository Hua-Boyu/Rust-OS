"""Host-only contracts. Never launch QEMU or invoke Cargo."""
import importlib
import unittest
import argparse
import json
from pathlib import Path
import tempfile
import time
from unittest import mock

import phase10_initramfs_test as h
import phase6_verify


class ReportContract(unittest.TestCase):
    def test_cleanup_failure_is_explicit_and_fallback_reaps_owned_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guest = host_harness(root)
            proc = mock.Mock()
            proc.poll.side_effect = [None, 0]
            guest.proc = proc
            with mock.patch.object(guest, 'close', side_effect=OSError('close failed')):
                result = h.run_scenario(guest, root, lambda g: g.check(True, 'workload'))
            report = json.loads((root / 'report.json').read_text())
            self.assertFalse(result)
            self.assertEqual(report['overall'], 'FAIL')
            self.assertIs(report['cleanup'], False)
            self.assertIs(report['owned_qemu_exited'], True)
            self.assertIn('close failed', report['cleanup_error'])
            proc.kill.assert_called_once()
            proc.wait.assert_called_once_with(timeout=5)

    def test_rsp_cleanup_failure_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guest = host_harness(root)
            guest.report['rsp_cleanup_error'] = 'socket close failed'
            with mock.patch.object(guest, 'close'):
                result = h.run_scenario(guest, root, lambda g: g.check(True, 'workload'))
            self.assertFalse(result)
            report = json.loads((root / 'report.json').read_text())
            self.assertIs(report['cleanup'], False)
            self.assertEqual(report['overall'], 'FAIL')
            self.assertEqual(report['check_count'], len(report['checks']))
            self.assertLess(report['pass_count'], report['check_count'])

    def test_input_failure_retains_fail_report_and_actual_completed_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(h, 'system_assets', side_effect=ValueError('bad assets')), \
                    mock.patch.object(h.subprocess, 'Popen') as launch, mock.patch('builtins.print'):
                self.assertEqual(h.main(['--output-dir', str(root)]), 1)
            launch.assert_not_called()
            paths = list(root.glob('*/report.json'))
            self.assertEqual(len(paths), 1)
            report = json.loads(paths[0].read_text())
            self.assertEqual(report['overall'], 'FAIL')
            self.assertEqual(report['expected_scenarios'], 56)
            self.assertEqual(report['scenario_count'], 0)
            self.assertIn('bad assets', report['error'])
            with self.assertRaises(RuntimeError):
                phase6_verify.phase10_evidence(report, paths[0])

    def test_real_harness_matrix_satisfies_strict_acceptance_without_guests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / 'kernel'
            kernel.write_bytes(b'host-only kernel placeholder')

            def verified_start(guest):
                guest.check(True, 'host-only workload stand-in')
                guest._host_text = transcript(guest.case, reboot=False)

            def verified_reboot(guest):
                guest._host_text = transcript(guest.case)

            with mock.patch.object(h, 'system_assets', return_value=b'archive'), \
                    mock.patch.object(h, 'PROJECT', root), \
                    mock.patch.object(h, 'make_iso', return_value=root / 'test.iso'), \
                    mock.patch.object(h, 'elf_symbols', return_value={
                        'INITRAMFS_TEST_MODE': {'address': 0x1234, 'size': 1}}), \
                    mock.patch.object(h.PhaseHarness, 'start', verified_start), \
                    mock.patch.object(h.PhaseHarness, 'text', lambda guest: guest._host_text), \
                    mock.patch.object(h.PhaseHarness, 'guest_reboot', verified_reboot), \
                    mock.patch.object(h.PhaseHarness, 'trusted_shell'), \
                    mock.patch.object(h.PhaseHarness, 'recovery_shell'), \
                    mock.patch.object(h.PhaseHarness, 'refused_namespace'), \
                    mock.patch.object(h.PhaseHarness, 'memory_diagnostics'), \
                    mock.patch.object(h.PhaseHarness, 'close'), \
                    mock.patch.object(h, 'missing'), \
                    mock.patch.object(h.subprocess, 'Popen') as launch, \
                    mock.patch('builtins.print'):
                code = h.main(['--output-dir', str(root / 'reports'),
                               '--kernel', str(kernel), '--fixture-kernel', str(kernel)])
            launch.assert_not_called()
            self.assertEqual(code, 0)
            reports = list((root / 'reports').glob('*/report.json'))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertEqual(len(phase6_verify.phase10_evidence(report, reports[0])), 56)
            images = []
            for row in report['scenarios']:
                nested = json.loads(Path(row['report']).read_text())
                if row['case'] == 'missing-storage':
                    self.assertNotIn('recovery_image', nested)
                else:
                    images.append(nested['recovery_image'])
                    self.assertEqual(nested['recovery_image_before_sha256'],
                                     nested['recovery_image_after_sha256'])
            self.assertEqual(len(images), 52)
            self.assertEqual(len(set(images)), len(images))


class MatrixContract(unittest.TestCase):
    def test_trusted_system_is_independent_of_missing_or_corrupt_storage(self):
        for case in ('missing-storage', 'corrupt-rostifs'):
            with self.subTest(case=case):
                plan = h.injection_plan(case, bytes(h.HEADER_BYTES), b'archive')
                self.assertEqual(plan['module_count'], 1)
                self.assertEqual(dict(plan['writes'])[h.PAYLOAD], b'archive')
                self.assertEqual(h.exercise_for(case), 'trusted')
                self.assertEqual(h.marker_groups(case), [
                    (h.BOOT_MARKERS[0],), (h.TRUSTED_MARKER,), (h.BOOT_MARKERS[1],)])

    def test_storage_independence_workloads_verify_no_persistent_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'corrupt.img'
            image.write_bytes(bytes(65536))
            for case in ('missing-storage', 'corrupt-rostifs'):
                with self.subTest(case=case):
                    guest = host_harness(root, case)
                    text = '\n'.join((h.BOOT_MARKERS[0], h.TRUSTED_MARKER, h.BOOT_MARKERS[1]))
                    with mock.patch.object(h, 'PhaseHarness', return_value=guest) as factory, \
                            mock.patch.object(h, 'owned_media', return_value=(root, image)), \
                            mock.patch.object(guest, 'start'), \
                            mock.patch.object(guest, 'text', return_value=text), \
                            mock.patch.object(guest, 'trusted_shell') as trusted, \
                            mock.patch.object(guest, 'recovery_shell') as recovery, \
                            mock.patch.object(guest, 'memory_diagnostics'), \
                            mock.patch.object(guest, 'close'), \
                            mock.patch.object(h, 'missing') as missing:
                        self.assertTrue(h.run_one(guest.args, root,
                            {'case': case, 'boot': 'elf', 'ram': 128},
                            b'archive', image, guest.deadline))
                    trusted.assert_called_once()
                    recovery.assert_not_called()
                    missing.assert_called_once_with(guest, '/mnt/rosti')
                    self.assertEqual(factory.call_args.args[2],
                                     image if case == 'corrupt-rostifs' else None)

    def test_complete_unique_matrix(self):
        spec = importlib.util.find_spec('phase10_initramfs_test')
        self.assertIsNotNone(spec, 'Phase10 matrix harness must exist')
        h = importlib.import_module('phase10_initramfs_test')
        rows = h.matrix()
        self.assertEqual(len(rows), 56)
        self.assertEqual(len({(r['case'], r['boot'], r['ram']) for r in rows}), 56)
        self.assertEqual({r['ram'] for r in rows}, {128, 512})
        self.assertEqual({r['boot'] for r in rows}, {'elf', 'iso'})
        self.assertEqual(len({r['case'] for r in rows}), 14)


def host_harness(folder, case='trusted', mode_symbol=None):
    args = argparse.Namespace(kernel=folder / 'kernel', fixture_kernel=folder / 'fixture-kernel',
                              ram=128, stress=False, timeout=10, iso=None, live=None)
    return h.PhaseHarness(args, folder, None, time.monotonic() + 10,
                          case, b'archive', mode_symbol)


class EntryContract(unittest.TestCase):
    def test_real_gdb_register_api_redirects_only_ebx_with_readback(self):
        import struct
        from b13_entry_inject import REGISTERS
        raw = bytearray(range(128))
        struct.pack_into('<I', raw, REGISTERS.index('eax') * 4, 0x2badb002)
        struct.pack_into('<I', raw, REGISTERS.index('ebx') * 4, 0x90000)
        expected = bytearray(raw)
        struct.pack_into('<I', expected, REGISTERS.index('ebx') * 4, h.INFO)
        gdb = h.Gdb(None)
        gdb.command = mock.Mock(side_effect=[raw.hex(), 'OK', expected.hex()])
        gdb.set_registers(ebx=h.INFO)
        self.assertEqual(gdb.command.call_args_list,
                         [mock.call('g'), mock.call('G' + expected.hex()), mock.call('g')])
        self.assertEqual(gdb.mutations, [{'registers': {'ebx': h.INFO}}])

    def inject(self, case='trusted', symbol=None):
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory), case, symbol)
            connection = mock.Mock()
            gdb = mock.create_autospec(h.Gdb, instance=True)
            registers = {'eax': 0x2badb002, 'ebx': 0x90000, 'eip': 0x100000}
            gdb.registers.side_effect = lambda: dict(registers)
            gdb.set_registers.side_effect = lambda **updates: registers.update(updates)
            gdb.command.side_effect = lambda command: 'T05' if command == 'c' else 'OK'
            writes = {}
            gdb.write.side_effect = lambda address, data: writes.update({address: data})
            gdb.read.side_effect = lambda address, count: (
                bytes(h.HEADER_BYTES) if address == 0x90000 else writes[address][:count])
            proc = mock.Mock(pid=123)
            proc.poll.return_value = None
            with mock.patch.object(h.socket, 'create_connection', return_value=connection), \
                    mock.patch.object(h, 'Gdb', return_value=gdb), \
                    mock.patch.object(h, 'elf_symbols', return_value={
                        '_start': {'address': 0x100000, 'size': 10}}), \
                    mock.patch.object(h.subprocess, 'Popen', return_value=proc) as launch, \
                    mock.patch.object(guest, 'wait'):
                guest.inject_at_entry(['owned-qemu', '-S'], 12345)
            self.assertEqual(registers['eax'], 0x2badb002)
            self.assertEqual(registers['ebx'], h.INFO,
                             'the kernel must consume the injected header, not the original')
            gdb.set_registers.assert_called_once_with(ebx=h.INFO)
            connection.close.assert_called_once()
            return guest, writes, launch, proc

    def test_kernel_consumes_injected_header_with_loader_magic_preserved(self):
        self.inject()

    def test_entry_injection_launches_and_retains_exact_owned_process(self):
        guest, _, launch, proc = self.inject()
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0], ['owned-qemu', '-S'])
        self.assertIs(guest.proc, proc)
        self.assertEqual(guest.report['qemu_pid'], proc.pid)

    def test_fixture_symbol_dictionary_selects_each_mode_byte(self):
        for case, mode in h.MODES.items():
            with self.subTest(case=case):
                guest, writes, _, _ = self.inject(case, {'address': 0x1234, 'size': 1})
                self.assertEqual(writes[0x1234], bytes([mode]))
                self.assertEqual(guest.report['fixture']['mode'], mode)


# Independent expected wire transcripts: do not derive the oracle from marker_groups.
ABSENT = 'ROSTI: initramfs absent; RAMFS recovery'
DIGEST = 'ROSTI: initramfs archive rejected: DigestMismatch; RAMFS recovery'
GATE = 'ROSTI: storage gate closed (boot metadata rejected)'
OUTCOMES = {
    'absent': [ABSENT],
    'duplicate': ['ROSTI: initramfs ambiguous; RAMFS recovery'],
    'invalid-descriptor': ['ROSTI: boot metadata rejected: Module; bootstrap-heap recovery', GATE, ABSENT],
    'oversize': ['ROSTI: initramfs copy rejected: Span; RAMFS recovery'],
    'mount-collision': ['ROSTI: unpublished initramfs snapshot released',
                        'ROSTI: initramfs publication rejected: not a directory; RAMFS recovery'],
    'mount-failure': ['ROSTI: unpublished initramfs snapshot released',
                      'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'],
    'resource-exhaustion': ['ROSTI: initramfs real allocator OOM recovered',
                            'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'],
    'reboot-after-failure': ['ROSTI: unpublished initramfs snapshot released',
                             'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'],
    **{case: [DIGEST] for case in ('bad-digest', 'truncated', 'malformed')},
    **{case: [h.TRUSTED_MARKER] for case in h.SUCCESS_CASES},
}


def transcript(case, reboot=True):
    lines = [h.BOOT_MARKERS[0], *OUTCOMES[case], h.BOOT_MARKERS[1]]
    if case == 'reboot-after-failure' and reboot:
        lines += [h.BOOT_MARKERS[0], ABSENT, h.BOOT_MARKERS[1]]
    return '\n'.join(lines)


class StrictMarkerContract(unittest.TestCase):
    def test_reboot_initial_mount_failure_requires_complete_first_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory), 'reboot-after-failure')
            self.assertEqual(h.CASE_OUTCOMES[guest.case], tuple(OUTCOMES[guest.case]))
            self.assertEqual(h.marker_groups(guest.case), [
                (h.BOOT_MARKERS[0],), *((line,) for line in OUTCOMES[guest.case]),
                (h.BOOT_MARKERS[1],), (h.BOOT_MARKERS[0],), (ABSENT,),
                (h.BOOT_MARKERS[1],)])
            good = transcript(guest.case, reboot=False)
            with mock.patch.object(guest, 'text', return_value=good):
                guest.markers(rebooted=False)
            for bad in (good.replace(h.BOOT_MARKERS[1], ''),
                        good.replace(OUTCOMES[guest.case][0], ''),
                        good.replace(OUTCOMES[guest.case][1], DIGEST)):
                with self.subTest(text=bad), mock.patch.object(guest, 'text', return_value=bad):
                    with self.assertRaises(AssertionError):
                        guest.markers(rebooted=False)

    def test_mount_rollback_requires_release_and_forbids_failed_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in ('mount-collision', 'mount-failure'):
                good = transcript(case)
                for text in (good.replace(OUTCOMES[case][0], ''),
                             good + '\nROSTI: initramfs rollback accounting FAILED'):
                    with self.subTest(case=case, text=text):
                        guest = host_harness(Path(directory), case)
                        with mock.patch.object(guest, 'text', return_value=text):
                            with self.assertRaises(AssertionError):
                                guest.markers()

    def test_invalid_inventory_never_probes_or_mounts_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory), 'invalid-descriptor')
            for marker in ('ROSTI: block device present', 'ROSTI: RostiFS mounted at /mnt/rosti'):
                with mock.patch.object(guest, 'text', return_value=transcript(guest.case) + '\n' + marker):
                    with self.assertRaises(AssertionError):
                        guest.markers()

    def test_exact_outcomes_and_wrong_absent_class_for_each_target(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in h.CASES:
                with self.subTest(case=case):
                    guest = host_harness(Path(directory), case)
                    with mock.patch.object(guest, 'text', return_value=transcript(case)):
                        guest.markers()
                    if case != 'absent':
                        wrong = '\n'.join((h.BOOT_MARKERS[0], ABSENT, h.BOOT_MARKERS[1]))
                        if case == 'reboot-after-failure':
                            wrong += '\n' + wrong
                        with mock.patch.object(guest, 'text', return_value=wrong):
                            with self.assertRaises(AssertionError):
                                guest.markers()

    def test_wrong_error_wrong_order_gate_and_late_publication_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in h.CASES:
                text = transcript(case)
                mutations = [text.replace(OUTCOMES[case][0], OUTCOMES[case][0] + ' WRONG'),
                             text.replace(h.BOOT_MARKERS[0], '', 1) + '\n' + h.BOOT_MARKERS[0]]
                if case not in h.SUCCESS_CASES:
                    mutations.append(text + '\n' + h.TRUSTED_MARKER)
                if case != 'invalid-descriptor':
                    mutations.append(text + '\n' + GATE)
                else:
                    mutations.append(text.replace(GATE, ''))
                for bad in mutations:
                    with self.subTest(case=case, text=bad):
                        guest = host_harness(Path(directory), case)
                        with mock.patch.object(guest, 'text', return_value=bad):
                            with self.assertRaises(AssertionError):
                                guest.markers()


class MarkerContract(unittest.TestCase):
    def test_wrong_initial_reboot_class_never_reboots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guest = host_harness(root, 'reboot-after-failure')
            wrong = '\n'.join((h.BOOT_MARKERS[0], ABSENT, h.BOOT_MARKERS[1]))
            with mock.patch.object(h, 'PROJECT', root), \
                    mock.patch.object(h, 'elf_symbols', return_value={
                        'INITRAMFS_TEST_MODE': {'address': 0x1234, 'size': 1}}), \
                    mock.patch.object(h, 'PhaseHarness', return_value=guest), \
                    mock.patch.object(guest, 'start'), \
                    mock.patch.object(guest, 'guest_reboot') as reboot, \
                    mock.patch.object(guest, 'text', return_value=wrong), \
                    mock.patch.object(guest, 'close'):
                result = h.run_one(guest.args, root,
                    {'case': guest.case, 'boot': 'elf', 'ram': 128}, b'archive', None, guest.deadline)
            self.assertFalse(result)
            reboot.assert_not_called()

    def test_resource_exhaustion_requires_real_recovered_oom_without_fixture_failure(self):
        recovered = 'ROSTI: initramfs real allocator OOM recovered'
        refused = 'ROSTI: initramfs publication rejected: out of memory; RAMFS recovery'
        with tempfile.TemporaryDirectory() as directory:
            for middle, passed in (([refused], False),
                                   ([recovered, 'ROSTI: initramfs OOM fixture FAILED', refused], False),
                                   ([recovered, refused], True)):
                with self.subTest(middle=middle):
                    guest = host_harness(Path(directory), 'resource-exhaustion')
                    text = '\n'.join([h.BOOT_MARKERS[0], *middle, h.BOOT_MARKERS[1]])
                    with mock.patch.object(guest, 'text', return_value=text):
                        if passed:
                            guest.markers()
                        else:
                            with self.assertRaises(AssertionError):
                                guest.markers()

    def test_publication_refusal_is_recognized_before_boot_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in h.MODES:
                with self.subTest(case=case):
                    guest = host_harness(Path(directory), case)
                    text = '\n'.join((h.BOOT_MARKERS[0],
                                     *OUTCOMES[case],
                                     h.BOOT_MARKERS[1]))
                    with mock.patch.object(guest, 'text', return_value=text):
                        guest.markers(rebooted=case != 'reboot-after-failure')

    def test_reboot_scenario_checks_both_boots_only_after_guest_reboot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guest = host_harness(root, 'reboot-after-failure')
            text = []

            def boot():
                text.extend((h.BOOT_MARKERS[0], *OUTCOMES[guest.case], h.BOOT_MARKERS[1]))
                guest.check(True, 'mock first boot')

            def reboot():
                text.extend((h.BOOT_MARKERS[0], ABSENT, h.BOOT_MARKERS[1]))

            symbol = {'address': 0x1234, 'size': 1}
            events = mock.Mock()
            with mock.patch.object(h, 'elf_symbols', return_value={
                        'INITRAMFS_TEST_MODE': symbol}), \
                    mock.patch.object(h, 'PhaseHarness', return_value=guest) as factory, \
                    mock.patch.object(guest, 'start', side_effect=boot), \
                    mock.patch.object(guest, 'guest_reboot', side_effect=reboot) as reset, \
                    mock.patch.object(guest, 'text', side_effect=lambda: '\n'.join(text)), \
                    mock.patch.object(guest, 'recovery_shell') as recovery, \
                    mock.patch.object(guest, 'refused_namespace') as namespace, \
                    mock.patch.object(guest, 'memory_diagnostics'), \
                    mock.patch.object(guest, 'close'), \
                    mock.patch.object(h, 'missing'):
                events.attach_mock(namespace, 'initial_namespace')
                events.attach_mock(reset, 'guest_reboot')
                events.attach_mock(recovery, 'full_recovery')
                result = h.run_one(guest.args, root,
                                   {'case': guest.case, 'boot': 'elf', 'ram': 128},
                                   b'archive', None, guest.deadline)
            self.assertTrue(result)
            reset.assert_called_once()
            self.assertEqual(events.mock_calls, [mock.call.initial_namespace(),
                mock.call.guest_reboot(), mock.call.full_recovery()])
            self.assertEqual(factory.call_args.args[0].kernel, guest.args.fixture_kernel.resolve())
            self.assertEqual(factory.call_args.args[-1], symbol)

    def test_real_guest_reboot_uses_shell_without_relaunch_or_reinjection(self):
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory), 'reboot-after-failure')
            proc = mock.Mock(pid=123)
            guest.proc = proc
            before = transcript(guest.case, reboot=False)
            with mock.patch.object(guest, 'text', side_effect=[before, transcript(guest.case)]), \
                    mock.patch.object(guest, 'type_text') as typed, \
                    mock.patch.object(guest, 'key') as key, \
                    mock.patch.object(guest, 'wait', side_effect=lambda predicate, *a, **k:
                        self.assertTrue(predicate())), \
                    mock.patch.object(guest, 'wait_boot') as wait_boot, \
                    mock.patch.object(guest, 'qmp') as qmp, \
                    mock.patch.object(guest, 'inject_at_entry') as inject, \
                    mock.patch.object(h.subprocess, 'Popen') as launch:
                guest.guest_reboot()
            typed.assert_called_once_with('reboot')
            key.assert_called_once_with('ret')
            wait_boot.assert_called_once_with(len(before))
            qmp.assert_not_called()
            inject.assert_not_called()
            launch.assert_not_called()
            self.assertIs(guest.proc, proc)
            self.assertIs(guest.report['guest_reboot'], True)

    def test_markers_follow_kernel_emission_before_boot_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in h.CASES:
                if case == 'reboot-after-failure':
                    continue
                with self.subTest(case=case):
                    guest = host_harness(Path(directory), case)
                    text = transcript(case)
                    with mock.patch.object(guest, 'text', return_value=text):
                        guest.markers()


class MediaAndDiagnosticsContract(unittest.TestCase):
    def test_each_refusal_owns_fresh_hashed_media_and_detects_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = []
            for case in set(h.CASES) - {'missing-storage'}:
                row = {'case': case, 'boot': 'elf', 'ram': 128}
                def start(guest):
                    self.assertIsNotNone(guest.image)
                    images.append(guest.image)
                    self.assertTrue(guest.image.read_bytes().startswith(h.MAGIC))
                    if case == 'invalid-descriptor':
                        guest.image.write_bytes(b'mutated')
                    guest.check(True, 'host stand-in')
                with mock.patch.object(h, 'PROJECT', root), \
                        mock.patch.object(h.PhaseHarness, 'start', start), \
                        mock.patch.object(h.PhaseHarness, 'markers'), \
                        mock.patch.object(h.PhaseHarness, 'guest_reboot'), \
                        mock.patch.object(h.PhaseHarness, 'recovery_shell'), \
                        mock.patch.object(h.PhaseHarness, 'refused_namespace'), \
                        mock.patch.object(h.PhaseHarness, 'trusted_shell'), \
                        mock.patch.object(h.PhaseHarness, 'memory_diagnostics'), \
                        mock.patch.object(h.PhaseHarness, 'close'), \
                        mock.patch.object(h, 'missing'), \
                        mock.patch.object(h, 'elf_symbols', return_value={
                            'INITRAMFS_TEST_MODE': {'address': 1234, 'size': 1}}):
                    result = h.run_one(host_harness(root).args, root, row, b'archive', None,
                                       time.monotonic() + 10)
                self.assertEqual(result, case != 'invalid-descriptor')
                report = json.loads((h.scenario_folder(root, row) / 'report.json').read_text())
                self.assertIn('recovery_image_before_sha256', report)
                self.assertIn('recovery_image_after_sha256', report)
            self.assertEqual(len(images), len(set(images)))

    def test_accepted_inventory_uses_inherited_memory_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory))
            with mock.patch.object(h.BlockHarness, 'memory', return_value={'used': 12}) as memory, \
                    mock.patch.object(guest, 'command', return_value=(
                        'System nodes: 4\nSystem logical bytes: 58\n'
                        'System payload capacity: 58 bytes\nSystem metadata: 4096 bytes')):
                guest.memory_diagnostics('final')
            memory.assert_called_once_with('final')

    def test_real_memory_parser_retains_heap_and_rejects_faults_or_deallocations(self):
        base = ('Paging: enabled\nPage directory: 0x1000\nTotal frames: 100\nFree frames: 90\n'
                'Page faults: 0\nInvalid deallocs: 0\nUsed: 10 bytes\nCurrent capacity: 1000\n'
                'Growth pages: 2\nFailed allocations: 3\nLive allocations: 4\nSystem mount: absent\n')
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory), 'mount-failure')
            with mock.patch.object(guest, 'command', return_value=base):
                guest.memory_diagnostics('final')
            self.assertEqual(guest.report['memory']['final']['live_allocations'], 4)
            self.assertEqual(guest.report['memory']['final']['failed_allocations'], 3)
            for bad in (base.replace('Page faults: 0', 'Page faults: 1'),
                        base.replace('Invalid deallocs: 0', 'Invalid deallocs: 1')):
                with mock.patch.object(guest, 'command', return_value=bad):
                    with self.assertRaises(AssertionError):
                        guest.memory_diagnostics('bad')
            guest = host_harness(Path(directory), 'invalid-descriptor')
            rejected = base.replace('Paging: enabled', 'Paging: disabled').replace('Growth pages: 2', 'Growth pages: 0')
            with mock.patch.object(guest, 'command', return_value=rejected):
                guest.memory_diagnostics('bootstrap')
            self.assertEqual(guest.report['memory']['bootstrap']['growth_pages'], 0)
            self.assertIs(guest.report['system_memory']['bootstrap']['mounted'], False)

    def test_diagnostics_refuse_system_publication_in_negative_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in ('mount-collision', 'mount-failure', 'resource-exhaustion', 'bad-digest'):
                guest = host_harness(Path(directory), case)
                with mock.patch.object(guest, 'memory', return_value={'used': 12}), \
                        mock.patch.object(guest, 'command', return_value='System nodes: 4'):
                    with self.assertRaises(AssertionError):
                        guest.memory_diagnostics('final')
                with mock.patch.object(guest, 'memory', return_value={'used': 12}), \
                        mock.patch.object(guest, 'command', return_value='System mount: absent'):
                    guest.memory_diagnostics('final')


class RefusalNamespaceContract(unittest.TestCase):
    def test_refusal_namespace_checked_before_and_after_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in set(h.CASES) - h.SUCCESS_CASES:
                with self.subTest(case=case):
                    guest = host_harness(Path(directory), case)
                    with mock.patch.object(guest, 'exact') as exact, \
                            mock.patch.object(guest, 'success'), \
                            mock.patch.object(h, 'missing') as missing, \
                            mock.patch.object(h, 'console_only'), \
                            mock.patch.object(guest, 'text', return_value=transcript(case)):
                        guest.recovery_shell()
                    paths = [call.args[1] for call in missing.call_args_list]
                    if case == 'mount-collision':
                        self.assertEqual(exact.call_args_list.count(
                            mock.call('cat /system', 'collision sentinel')), 2)
                        self.assertNotIn('/system', paths)
                    else:
                        self.assertEqual(paths.count('/system'), 2)


class ShellContract(unittest.TestCase):
    def test_directory_listing_matches_shell_trailing_slash_format(self):
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory))
            with mock.patch.object(guest, 'exact') as exact, \
                    mock.patch.object(guest, 'success'), \
                    mock.patch.object(h, 'missing'), \
                    mock.patch.object(h, 'console_only'), \
                    mock.patch.object(guest, 'command', return_value='error: read-only filesystem'):
                guest.trusted_shell()
            listings = [call.args[1] for call in exact.call_args_list
                        if call.args[0] == 'ls /system']
            self.assertEqual(listings, ['README.txt\ndocs/', 'README.txt\ndocs/'])

    def test_mutations_use_existing_targets_or_valid_creation_syntax(self):
        expected = [
            'write /system/README.txt x', 'append /system/README.txt x',
            'touch /system/guard.txt', 'mkdir /system/guard',
            'rm /system/README.txt', 'rmdir /system/docs',
        ]
        with tempfile.TemporaryDirectory() as directory:
            guest = host_harness(Path(directory))
            with mock.patch.object(guest, 'exact'), \
                    mock.patch.object(guest, 'success'), \
                    mock.patch.object(h, 'missing'), \
                    mock.patch.object(h, 'console_only'), \
                    mock.patch.object(guest, 'command', return_value='error: read-only filesystem') as command:
                guest.trusted_shell()
            self.assertEqual([call.args[0] for call in command.call_args_list], expected)


class InjectionContract(unittest.TestCase):
    def setUp(self):
        import phase10_initramfs_test as h
        self.h = h

    def test_exact_payload_and_preserved_loader_fields(self):
        self.assertTrue(hasattr(self.h, 'injection_plan'), 'bounded injection planner required')
        import struct
        original = bytearray(range(116))
        struct.pack_into('<I', original, 0, 0x24f)
        archive = b'070701\x00\xff\x80archive\n'
        plan = self.h.injection_plan('trusted', bytes(original), archive)
        writes = dict(plan['writes'])
        self.assertEqual(writes[self.h.PAYLOAD], archive)
        self.assertEqual(writes[self.h.LABEL], b'rosti.initramfs\0')
        header = writes[self.h.INFO]
        self.assertEqual(header[4:20], original[4:20])
        self.assertEqual(header[28:], original[28:])
        self.assertEqual(struct.unpack_from('<I', header)[0], 0x24f | 8)
        self.assertEqual(struct.unpack('<4I', writes[self.h.TABLE]),
                         (self.h.PAYLOAD, self.h.PAYLOAD + len(archive), self.h.LABEL, 0xfffffffc))

    def test_reboot_injects_trusted_archive_into_mount_failure_fixture(self):
        archive = b'070701\x00\xffarchive'
        plan = h.injection_plan('reboot-after-failure', bytes(h.HEADER_BYTES), archive)
        self.assertEqual(dict(plan['writes'])[h.PAYLOAD], archive)
        self.assertEqual(plan['mode'], 2)
        self.assertEqual(plan['module_count'], 1)
        self.assertEqual(plan['payload_sha256'], h.digest(archive))
        self.assertEqual(plan['archive_sha256'], h.digest(archive))
        self.assertEqual(h.MODES['reboot-after-failure'], 2)

    def test_every_case_bounded_and_distinct(self):
        self.assertTrue(hasattr(self.h, 'injection_plan'), 'bounded injection planner required')
        import struct
        header = bytes(116)
        archive = b'070701' + bytes(1018)
        for case in self.h.CASES:
            with self.subTest(case=case):
                plan = self.h.injection_plan(case, header, archive)
                for address, data in plan['writes']:
                    self.assertGreaterEqual(address, self.h.INFO)
                    self.assertLessEqual(address + len(data), 19 * 1024 * 1024)
                if case == 'absent':
                    self.assertEqual(struct.unpack_from('<I', dict(plan['writes'])[self.h.INFO])[0] & 8, 0)
                if case in ('bad-digest', 'truncated', 'malformed', 'oversize'):
                    self.assertNotEqual(dict(plan['writes'])[self.h.PAYLOAD], archive)
                if case == 'duplicate':
                    self.assertEqual(len(dict(plan['writes'])[self.h.TABLE]), 32)

    def test_invalid_inputs_rejected(self):
        self.assertTrue(hasattr(self.h, 'injection_plan'), 'bounded injection planner required')
        for case, header, payload in [('invented', bytes(116), b'a'), ('trusted', b'', b'a'),
                                      ('trusted', bytes(116), b''),
                                      ('trusted', bytes(116), bytes(262145))]:
            with self.assertRaises(ValueError):
                self.h.injection_plan(case, header, payload)


if __name__ == '__main__':
    unittest.main()
