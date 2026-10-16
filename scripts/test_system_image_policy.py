"""Trusted build-policy regressions; never boot or overwrite accepted media."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from build_initramfs import build

PROJECT = Path(__file__).resolve().parents[1]


class SystemImagePolicyTests(unittest.TestCase):
    def test_iso_configuration_loads_exact_system_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('iso_builder', PROJECT / 'scripts/build-proxmox-iso.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn('module /boot/system.cpio rosti.initramfs', module.GRUB_CFG)

    def test_policy_matches_independent_archive_digest(self):
        from system_image_policy import trusted_archive
        data = trusted_archive(PROJECT)
        self.assertEqual(data, build(PROJECT / 'system'))
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '8ff3bfdc925e1b0e60441b072f4c4c0c4f6b16f68dfce0c0ff50bb609d64a6a7')

    def test_changed_input_is_refused_instead_of_repinning(self):
        from system_image_policy import trusted_archive
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'system').mkdir()
            (root / 'src').mkdir()
            (root / 'system/README.txt').write_bytes(b'modified\n')
            (root / 'src/system_image.rs').write_bytes((PROJECT / 'src/system_image.rs').read_bytes())
            with self.assertRaisesRegex(ValueError, 'digest'):
                trusted_archive(root)

    def test_malformed_pin_is_refused(self):
        from system_image_policy import trusted_archive
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'system').mkdir()
            (root / 'src').mkdir()
            (root / 'src/system_image.rs').write_text('pub const EXPECTED_SHA256: [u8;32] = [0];')
            with self.assertRaisesRegex(ValueError, 'policy'):
                trusted_archive(root)


if __name__ == '__main__':
    unittest.main()
