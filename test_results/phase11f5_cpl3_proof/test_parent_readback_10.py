"""F5 orchestration controls only, never substitute for actual reader runs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import freeze_and_verify_06_01 as driver


class ParentIntegration(unittest.TestCase):
    def setUp(self):
        from contextlib import ExitStack
        import hashlib
        import f1_composition_10
        import f2_evidence
        import f3_full_evidence
        import f4_evidence
        import f5_cpl3_evidence
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.snapshot = {'src/main.rs':'a'*64}
        self.elf = self.root/'production.elf'
        self.elf.write_bytes(b'production')
        self.paths = {}
        for name, child in (('F1','f1/producer/f1_retained_test'),('F2','f2/f2_guest_test'),
                            ('F3','f3/f3_full_test'),('F4','f4'),('F5','f5')):
            folder = self.root/child
            folder.mkdir(parents=True)
            path = folder/'report.json'
            path.write_bytes(b'{}')
            self.paths[name] = path
        (self.root/'f5/production').mkdir()
        (self.root/'f5/production/kernel.elf').write_bytes(self.elf.read_bytes())
        self.stack.enter_context(patch('phase6_verify.source_snapshot',return_value=self.snapshot))
        self.readers = {}
        specifications = [('F1',f1_composition_10,'readback',{'scenarios':10}),
                          ('F2',f2_evidence,'validate',{'scenario_count':8}),
                          ('F3',f3_full_evidence,'validate',{'scenario_count':18,'full_f3_acceptance':True}),
                          ('F4',f4_evidence,'validate_aggregate',{'scenario_count':12,'overall':'PASS'}),
                          ('F5',f5_cpl3_evidence,'validate_aggregate',{'scenario_count':12,'overall':'PASS'})]
        for name,module,attribute,result in specifications:
            result['pins'] = {str(self.paths[name]):hashlib.sha256(b'{}').hexdigest()}
            self.readers[name] = self.stack.enter_context(patch.object(module,attribute,autospec=True,return_value=result))
        self.audit = self.stack.enter_context(patch.object(f5_cpl3_evidence,'validate_audit',autospec=True))

    def test_all_actual_interfaces_receive_exact_paths_and_source(self):
        result = driver.parent_readback(self.root,self.snapshot,self.elf)
        self.assertEqual(result['overall'],'PASS')
        self.assertEqual(set(result['components']),set(self.paths))
        for name,reader in self.readers.items():
            expected = [self.paths[name],self.snapshot]
            if name == 'F1':
                expected.append(self.elf)
            reader.assert_called_once_with(*expected)
        self.audit.assert_called_once_with(self.root/'audit',self.elf,BASE/'f2_before_macro_01.elf')

    def test_each_reader_refusal_propagates(self):
        for name,reader in self.readers.items():
            with self.subTest(name=name):
                reader.side_effect = RuntimeError('injected strict reader refusal '+name)
                with self.assertRaisesRegex(RuntimeError,'strict reader refusal'):
                    driver.parent_readback(self.root,self.snapshot,self.elf)
                reader.side_effect = None

    def test_missing_and_ambiguous_f1_aggregate_refused(self):
        self.paths['F1'].unlink()
        with self.assertRaisesRegex(RuntimeError,'missing/ambiguous'):
            driver.parent_readback(self.root,self.snapshot,self.elf)
        self.paths['F1'].write_bytes(b'{}')
        extra = self.root/'f1/producer/f1_retained_other'
        extra.mkdir()
        (extra/'report.json').write_bytes(b'{}')
        with self.assertRaisesRegex(RuntimeError,'missing/ambiguous'):
            driver.parent_readback(self.root,self.snapshot,self.elf)

    def test_snapshot_not_bound_to_freeze_refused(self):
        with self.assertRaisesRegex(RuntimeError,'not bound'):
            driver.parent_readback(self.root,{},self.elf)

    def test_incomplete_matrix_refused(self):
        self.readers['F1'].return_value['scenarios'] = 9
        with self.assertRaisesRegex(RuntimeError,'incomplete'):
            driver.parent_readback(self.root,self.snapshot,self.elf)

    def test_validated_pin_drift_refused(self):
        self.readers['F2'].return_value['pins'][str(self.paths['F2'])] = '0'*64
        with self.assertRaisesRegex(RuntimeError,'artifact drift'):
            driver.parent_readback(self.root,self.snapshot,self.elf)

    def test_production_elf_substitution_refused(self):
        (self.root/'f5/production/kernel.elf').write_bytes(b'wrong')
        with self.assertRaisesRegex(RuntimeError,'ELF mismatch'):
            driver.parent_readback(self.root,self.snapshot,self.elf)


if __name__ == '__main__':
    unittest.main(verbosity=2)
