"""Tests of the REAL F1 resume guard, with no CPU/hardware attribution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from f1_capture import F1Capture, sha


class FakeGdb:
    def __init__(self):
        self.resumes = 0
    def registers(self):
        return {'eip': 0x10000}
    def command(self, command):
        return 'OK'
    def send(self, command):
        if command == 'c':
            self.resumes += 1


class RealGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.raw = bytes(range(256)) * 16
        for name in ('page.bin', 'repeat_page.bin'):
            (self.folder / name).write_bytes(self.raw)
        self.image = {'file': 'page.bin', 'length': 4096, 'sha256': sha(self.raw), 'physical': 0x1000, 'kind': 'PDE', 'role': 'active'}
        self.manifest = {'run': 'r1', 'case': 0, 'checkpoint': 'post_probes', 'ordinal': 0,
                         'capture_complete': True, 'images': [self.image]}
        self.path = self.folder / 'snapshot.json'
        self.write_manifest()
        self.guard = F1Capture('r1', 0, 128, {}, ['post_probes'], {'f1_post_probes': {'address': 0x10000}}, self.folder)
        self.guard.held = self.folder
        self.guard.captured_manifest_sha256 = sha(self.path.read_bytes())
        self.gdb = FakeGdb()

    def write_manifest(self):
        self.path.write_text(json.dumps(self.manifest))

    def ack(self):
        return {'run': 'r1', 'case': 0, 'checkpoint': 'post_probes', 'ordinal': 0,
                'capture_complete': True, 'manifest_sha256': sha(self.path.read_bytes())}

    def refuse(self, ack):
        with self.assertRaises((RuntimeError, OSError, ValueError)):
            self.guard.acknowledge(ack)
        self.assertEqual(self.gdb.resumes, 0)

    def test_missing_ack(self): self.refuse(None)
    def test_zero_ack(self): self.refuse({})
    def test_impostor_run(self): self.refuse(dict(self.ack(), run='impostor'))
    def test_substituted_case(self): self.refuse(dict(self.ack(), case=1))
    def test_substituted_checkpoint(self): self.refuse(dict(self.ack(), checkpoint='pre_seal'))
    def test_continue_without_ack(self):
        with self.assertRaises(RuntimeError): self.guard.continue_guest(self.gdb, final=True)
        self.assertEqual(self.gdb.resumes, 0)
    def test_zero_images(self):
        self.manifest['images'] = []
        self.write_manifest()
        self.refuse(self.ack())
    def test_missing_image(self):
        (self.folder / 'page.bin').unlink()
        self.refuse(self.ack())
    def test_substituted_bytes(self):
        (self.folder / 'page.bin').write_bytes(bytes(4096))
        self.refuse(self.ack())
    def test_repeat_substitution(self):
        (self.folder / 'repeat_page.bin').write_bytes(bytes(4096))
        self.refuse(self.ack())
    def test_duplicate_ack(self):
        self.guard.acknowledge(self.ack())
        self.refuse(self.ack())
    def test_positive_and_consumed_ack(self):
        ack = self.ack()
        self.guard.acknowledge(ack)
        self.guard.continue_guest(self.gdb, final=True)
        self.assertEqual(self.gdb.resumes, 1)
        with self.assertRaises(RuntimeError): self.guard.acknowledge(ack)
        with self.assertRaises(RuntimeError): self.guard.continue_guest(self.gdb, final=True)
        self.assertEqual(self.gdb.resumes, 1)
    def test_image_changed_after_ack_refuses_continue(self):
        self.guard.acknowledge(self.ack())
        (self.folder / 'page.bin').write_bytes(bytes(4096))
        with self.assertRaises(RuntimeError): self.guard.continue_guest(self.gdb, final=True)
        self.assertEqual(self.gdb.resumes, 0)
    def test_duplicate_image_inventory(self):
        self.manifest['images'] *= 2
        self.write_manifest()
        self.refuse(self.ack())


if __name__ == '__main__':
    if sys.flags.optimize: raise SystemExit('optimized verifier refused')
    unittest.main(verbosity=2)
