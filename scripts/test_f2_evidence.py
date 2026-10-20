"""Host-only malformed evidence controls, NOT CPU execution proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from f2_evidence import CASES, COMMON_CHECKS, digest, validate

class F2EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/'report.json'
        self.kernel=self.root/'kernel.elf'
        self.kernel.write_bytes(b'UNIT TEST MOCK ELF - NEVER EXECUTED')
        self.source={'src/main.rs':'unit-mock-main'}
        self.report={'overall':'PASS','build_exit':0,'source_sha256':self.source,
                     'stripping_equality':True,'original_main_sha256':'unit-mock-main',
                     'kernel_sha256':digest(self.kernel),'cases':[]}
        for case,ram in sorted(CASES):
            folder=self.root/f'{case}_{ram}'
            folder.mkdir()
            (folder/'serial.txt').write_text('F2 fatal terminal\n')
            (folder/'mandatory_prefix.bin').write_bytes(bytes(68))
            names=COMMON_CHECKS | ({'page_fault_CR2_zero'} if case=='pf' else set())
            guest={'overall':'PASS','case':case,'ram_mib':ram,'owned_qemu_exited':True,
                   'qemu_exit':1,'hardware_cpl3':False,'kernel_sha256':digest(self.kernel),
                   'checks':[{'name':n,'pass':True} for n in sorted(names)],
                   'command':['unit-mock-qemu','-kernel',str(self.kernel),'-m',str(ram),'-cpu','qemu32','-smp','1','-serial','file:'+str(folder/'serial.txt')]}
            (folder/'report.json').write_text(json.dumps(guest))
            self.report['cases'].append({'case':case,'ram_mib':ram,'overall':'PASS','report':str(folder/'report.json')})
        self.save()
    def save(self):
        self.path.write_text(json.dumps(self.report))
    def reject(self):
        self.save()
        with self.assertRaises((RuntimeError,OSError,ValueError)):
            validate(self.path,self.source)
    def change_child(self, mutate):
        path=Path(self.report['cases'][0]['report'])
        row=json.loads(path.read_text())
        mutate(row)
        path.write_text(json.dumps(row))
    def test_complete_mock_control(self):
        self.assertEqual(validate(self.path,self.source)['scenario_count'],8)
    def test_missing_zero_duplicate_extra_substituted_impostor(self):
        original=copy.deepcopy(self.report['cases'])
        invalid=[[],original[:-1],original[:-1]+[original[0]],original+[original[0]],
                 [dict(x,case='impostor') for x in original],
                 [dict(x,ram_mib=256) for x in original]]
        for rows in invalid:
            with self.subTest(rows=len(rows)):
                self.report['cases']=rows
                self.reject()
    def test_wrong_source(self):
        self.report['source_sha256']={}
        self.reject()
    def test_wrong_kernel(self):
        self.kernel.write_bytes(b'substitution')
        self.reject()
    def test_wrong_child_ownership(self):
        self.report['cases'][0]['report']=str(self.root/'other.json')
        self.reject()
    def test_wrong_command_ram_or_elf(self):
        self.change_child(lambda row: row['command'].__setitem__(4,'512'))
        # First sorted identity is de128: operand index4 is RAM.
        self.reject()
    def test_cleanup_missing(self):
        self.change_child(lambda row: row.pop('owned_qemu_exited'))
        self.reject()
    def test_hardware_check_removed(self):
        self.change_child(lambda row: row['checks'].pop())
        self.reject()
    def test_hardware_check_duplicate(self):
        self.change_child(lambda row: row['checks'].append(row['checks'][0]))
        self.reject()
    def test_hardware_check_false(self):
        self.change_child(lambda row: row['checks'][0].update({'pass':False}))
        self.reject()
    def test_no_positive_matrix_status(self):
        self.report['overall']='RUNNING'
        self.reject()

if __name__=='__main__':
    unittest.main(verbosity=2)
