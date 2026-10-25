"""Real mutation controls for approved F5 entry derivation. No guest/build."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import f5_entry_derivation as derivation

ROOT = Path(__file__).resolve().parents[1]


class DerivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f2 = (ROOT/'src/exception_entry.s').read_bytes()
        cls.f5 = (ROOT/'src/f5_exception_entry.s').read_bytes()
        if derivation.sha(cls.f2) != derivation.F2_SHA256:
            raise RuntimeError('test fixture F2 raw pin is wrong')

    def test_complete_approved_expansion(self):
        result = derivation.compare_bytes(self.f2, self.f5)
        self.assertEqual(result['overall'], 'PASS')
        self.assertFalse(result['literal_source_shared'])
        self.assertEqual(result['f2_sequence_sha256'], result['mapped_f5_sequence_sha256'])
        self.assertEqual(len(result['ordered_vector_definitions']), 32)

    def test_comments_only_allowed(self):
        self.assertEqual(derivation.compare_bytes(self.f2, b'# diagnostic comment\r\n'+self.f5)['overall'], 'PASS')

    def test_required_mutations_rejected(self):
        mutations = {
            'opcode': (b'    pushal', b'    popal'),
            'immediate': (b'    sub $12,%esp', b'    sub $16,%esp'),
            'error_class': (b'F5_STUB 14,1', b'F5_STUB 14'),
            'tail_offset_assertion': (b'{vector_offset} != 48', b'{vector_offset} != 52'),
            'abi': (b'{frame_size} != 68', b'{frame_size} != 76'),
            'bridge': (b'call f5_bridge', b'call f5_fatal'),
            'unknown_alias': (b'f5_entry_terminal', b'f5_surprise_terminal'),
            'table_member': (b'.long f5_exc_0,', b'.long f5_exc_1,'),
            'table_order': (b'f5_exc_0,f5_exc_1,', b'f5_exc_1,f5_exc_0,'),
            'deleted_instruction': (b'    pushal\n', b''),
            'inserted_instruction': (b'    pushal', b'    nop\n    pushal'),
            'dropped_vector': (b'F5_STUB 31\n', b''),
            'duplicate_vector': (b'F5_STUB 31\n', b'F5_STUB 31\nF5_STUB 31\n'),
            'reordered_vectors': (b'F5_STUB 0\nF5_STUB 1', b'F5_STUB 1\nF5_STUB 0'),
            'unexpected_string': (b'F5 frame size mismatch', b'F5 wrong frame size'),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(mutation=name):
                self.assertIn(old, self.f5)
                with self.assertRaises(RuntimeError):
                    derivation.compare_bytes(self.f2, self.f5.replace(old, new, 1))
        with self.assertRaises(RuntimeError):
            derivation.compare_bytes(self.f2, self.f5[:len(self.f5)//2])

    def test_wrong_raw_f2_before_parsing(self):
        for raw in (self.f2.replace(b'\n', b'\r\n'), b'\xff', self.f2+b'\n'):
            with self.subTest(raw_hash=derivation.sha(raw)):
                with patch.object(derivation, 'lexical', side_effect=RuntimeError('PARSER MUST NOT RUN')) as parser:
                    with self.assertRaisesRegex(RuntimeError, 'wrong accepted F2 raw'):
                        derivation.compare_bytes(raw, self.f5)
                    parser.assert_not_called()

    def test_dictionary_closed(self):
        self.assertEqual(derivation.map_identifier('f5_bridge'), 'f2_fatal')
        for name in ('f5_fatal', 'f5_unknown', 'f5_exc_32', 'F5_OTHER'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'unknown F5 identifier'):
                derivation.map_identifier(name)

    def test_source_path_and_hash_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sources = {'src/exception_entry.s': self.f2, 'src/f5_exception_entry.s': self.f5,
                       'scripts/f5_entry_derivation.py': (ROOT/'scripts/f5_entry_derivation.py').read_bytes()}
            pins = {n: derivation.sha(raw) for n, raw in sources.items()}
            for name, raw in sources.items():
                (root/name).parent.mkdir(parents=True, exist_ok=True)
                (root/name).write_bytes(raw)
            self.assertEqual(derivation.validate(root, pins)['overall'], 'PASS')
            for name in sources:
                with self.subTest(stale=name), self.assertRaisesRegex(RuntimeError, 'stale source/validator pin'):
                    derivation.validate(root, {**pins, name: '0'*64})
                with self.subTest(missing_pin=name), self.assertRaises(RuntimeError):
                    derivation.validate(root, {n: h for n, h in pins.items() if n != name})
            (root/'src/f5_exception_entry.s').unlink()
            with self.assertRaises(FileNotFoundError):
                derivation.validate(root, pins)

    def test_invalid_dictionary_and_duplicate_input_paths(self):
        with patch.dict(derivation.IDENTIFIERS, {'f5_bridge': 'f2_unsupported'}):
            with self.assertRaisesRegex(RuntimeError, 'derivation mismatch'):
                derivation.compare_bytes(self.f2, self.f5)
        with self.assertRaisesRegex(RuntimeError, 'duplicate input path/key'):
            json.loads('{"src/exception_entry.s":"a","src/exception_entry.s":"b"}',
                       object_pairs_hook=derivation.unique_object)

    def test_actual_optimized_subprocess_refuses(self):
        child = subprocess.run([sys.executable, '-O', '-B', str(ROOT/'scripts/f5_entry_derivation.py'), '--help'], capture_output=True, text=True)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn('optimized evidence execution refused', child.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
