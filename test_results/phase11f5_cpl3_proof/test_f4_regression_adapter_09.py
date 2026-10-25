"""Offline controls for the F5-owned predecessor regression adapter; no guests."""
import ast
from collections import Counter
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('adapter', Path(__file__).with_name('run_f4_regression_06_01.py'))
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = subprocess.check_output(['git','cat-file','blob',
            'c8b73654dd5f7f64c3c7872254b2b730ad2151f4:scripts/phase6_verify.py'], cwd=ROOT)

    def test_actual_derived_runner_preserves_all_gates_and_complete_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            namespace, derived, provenance = ADAPTER.prepare_runner(self.blob, Path(temp))
        old = b'gate("acceptance runner regressions", script("test_acceptance_harness.py"), timeout=900)'
        new = old.replace(b'900)', b'1049)')
        self.assertEqual(derived, self.blob.replace(old, new))
        self.assertEqual(provenance['only_gate_change'], 'acceptance runner regressions timeout900->1049 (user-authorized R2)')
        # The exact guest inventory is obtained from the real live implementation,
        # not a guessed count or a subset accepted by a weakened validator.
        sys.path.insert(0, str(ROOT/'scripts'))
        from f2_exception_guest import source_snapshot
        self.assertEqual(namespace['source_snapshot'](), source_snapshot())
        self.assertGreater(provenance['expanded_input_count'], provenance['predecessor_input_count'])
        self.assertTrue(provenance['predecessor_pins_preserved'])
        def gates(raw):
            return Counter(ast.dump(n.args[0]) for n in ast.walk(ast.parse(raw))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'gate')
        self.assertEqual(gates(derived), gates(self.blob))

    def test_corrupt_blob_and_dropped_or_changed_predecessor_pin_refuse(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'blob mismatch'):
                ADAPTER.prepare_runner(self.blob + b'\n', Path(temp))
            namespace, _, _ = ADAPTER.prepare_runner(self.blob, Path(temp))
            full = namespace['source_snapshot']()
            for bad in ({}, {**full, 'src/main.rs': '0'*64}):
                fake = SimpleNamespace(source_snapshot=lambda: bad)
                spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
                with patch('importlib.util.spec_from_file_location', return_value=spec), \
                     patch('importlib.util.module_from_spec', return_value=fake):
                    with self.assertRaisesRegex(RuntimeError, 'drops or changes'):
                        ADAPTER.prepare_runner(self.blob, Path(temp))


if __name__ == '__main__':
    unittest.main(verbosity=2)
