"""Task-local producer cleanup controls; mocked CPU/build transport, real workflow."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import f1_retained_guest as producer
import boot_metadata_test
import phase6_verify


class WorkflowCleanup(unittest.TestCase):
    def exercise(self, mode=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'dist').mkdir()
            default = root / 'default.elf'
            default.write_bytes(b'default CPU transport fixture')
            args = SimpleNamespace(output_dir=root / 'evidence', kernel=default,
                                   timeout=60, guest_timeout=1, ram=[128, 512])
            def build(project, stage, snapshot, case, folder, deadline):
                kernel = stage / 'kernel.elf'
                kernel.write_bytes(b'emitted CPU transport fixture')
                producer.save(folder / 'build.json', {'case': case, 'exit': 0,
                                                     'kernel_sha256': producer.sha(kernel.read_bytes())})
                return kernel
            def guest(kernel, symbols, ram, case, folder, identities, timeout):
                folder.mkdir()
                row = {'overall': 'PASS', 'owned_qemu_exited': True,
                       'actual_qemu_exit': 1, 'case': case, 'ram_mib': ram,
                       'name': producer.CASES[case], 'identities': identities}
                if mode == 'matrix_fail':
                    row['overall'] = 'FAIL'
                if mode == 'source_identity':
                    row['identities']['source_snapshot_sha256'] = '0' * 64
                if mode == 'default_elf':
                    default.write_bytes(b'drift')
                if mode != 'missing_child':
                    producer.save(folder / 'report.json', row)
                return row
            if mode == 'missing_scenario':
                args.ram = [128]
            with patch.object(boot_metadata_test, 'PROJECT', root), \
                 patch.object(phase6_verify, 'source_snapshot', return_value={}), \
                 patch.object(producer, 'build_case', side_effect=build), \
                 patch.object(producer, 'run_guest', side_effect=guest), \
                 patch.object(boot_metadata_test, 'parse_elf'), \
                 patch.object(boot_metadata_test, 'build_fixture', return_value=(b'boot fixture', {})):
                status = producer.workflow(args)
            report_path, = args.output_dir.glob('*/report.json')
            report = json.loads(report_path.read_bytes())
            if mode:
                self.assertEqual(status, 1, report)
                self.assertEqual(report['overall'], 'FAIL')
                self.assertIs(report['stage_removed'], False)
                self.assertTrue(Path(report['owned_stage']).exists(), 'failed matrix must retain its stage')
                return
            self.assertEqual(status, 0, report)
            self.assertEqual(report['overall'], 'PASS')
            self.assertIs(report.get('stage_removed'), True,
                          'matrix PASS must establish completed staging cleanup')
            self.assertFalse(Path(report['owned_stage']).exists())
            self.assertNotIn('stage_retained', report)
            for case in range(5):
                build_root = report_path.parent / f'build_{case}'
                self.assertTrue((build_root / 'kernel.elf').is_file())
                build_report = json.loads((build_root / 'build.json').read_bytes())
                self.assertEqual(build_report['kernel_sha256'], producer.sha((build_root / 'kernel.elf').read_bytes()))
                for ram in (128, 512):
                    self.assertTrue((build_root / f'fixture_{ram}.elf').is_file())


    def test_successful_producer_actually_removes_owned_stage(self):
        self.exercise()

    def test_matrix_fail_falsely_labeled_pass_preserves_stage(self):
        self.exercise('matrix_fail')

    def test_missing_child_preserves_stage(self):
        self.exercise('missing_child')

    def test_missing_scenario_preserves_stage(self):
        self.exercise('missing_scenario')

    def test_incorrect_source_identity_preserves_stage(self):
        self.exercise('source_identity')

    def test_default_elf_drift_preserves_stage(self):
        self.exercise('default_elf')


class StageSafety(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dist = self.root / 'dist'
        self.dist.mkdir()

    def test_owned_stage_removed(self):
        owned = producer.OwnedStage(self.dist)
        stage = owned.path
        (stage / 'file').write_bytes(b'owned')
        owned.remove()
        self.assertFalse(stage.exists())

    def test_outside_root_refused(self):
        owned = producer.OwnedStage(self.dist)
        owned.path = self.root
        with self.assertRaises(Exception):
            owned.remove()
        self.assertTrue(self.root.exists())

    def test_invalid_prefix_refused(self):
        owned = producer.OwnedStage(self.dist)
        moved = self.dist / 'unrelated'
        owned.path.rename(moved)
        owned.path = moved
        with self.assertRaises(Exception):
            owned.remove()
        self.assertTrue(moved.exists())

    def test_not_owned_stage_refused(self):
        owned = producer.OwnedStage(self.dist)
        other = producer.OwnedStage(self.dist)
        owned.path = other.path
        with self.assertRaises(Exception):
            owned.remove()
        self.assertTrue(other.path.exists())

    def test_replaced_stage_identity_refused(self):
        owned = producer.OwnedStage(self.dist)
        moved = self.dist / 'original_preserved'
        owned.path.rename(moved)
        owned.path.mkdir()
        with self.assertRaisesRegex(RuntimeError, 'creation identity changed'):
            owned.remove()
        self.assertTrue(moved.exists())
        self.assertTrue(owned.path.exists())

    def test_removal_failure_refused(self):
        owned = producer.OwnedStage(self.dist)
        with patch.object(producer.shutil, 'rmtree', side_effect=PermissionError('injected')):
            with self.assertRaises(PermissionError):
                owned.remove()
        self.assertTrue(owned.path.exists())

    def test_still_present_after_claimed_removal_refused(self):
        owned = producer.OwnedStage(self.dist)
        with patch.object(producer.shutil, 'rmtree'):
            with self.assertRaises(Exception):
                owned.remove()
        self.assertTrue(owned.path.exists())

    def test_junction_escape_refused(self):
        import os
        import subprocess
        owned = producer.OwnedStage(self.dist)
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = outside / 'sentinel'
        sentinel.write_bytes(b'untouched')
        link = owned.path / 'escape'
        if os.name == 'nt':
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(Exception):
                owned.remove()
            self.assertEqual(sentinel.read_bytes(), b'untouched')
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_reparse_attribute_refused(self):
        owned = producer.OwnedStage(self.dist)
        original = Path.lstat
        def reparse(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == owned.path:
                return SimpleNamespace(st_file_attributes=0x400, st_mode=result.st_mode,
                                       st_dev=result.st_dev, st_ino=result.st_ino)
            return result
        with patch.object(Path, 'lstat', reparse):
            with self.assertRaises(Exception):
                owned.remove()
        self.assertTrue(owned.path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
