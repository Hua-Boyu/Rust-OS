"""MOCK-ONLY host provenance controls. Never run acceptance/build/guest commands."""
import ast
from collections import Counter
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import canonical_provenance_03 as p
import run_canonical_03 as launcher

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='MOCK_canonical03_', dir=p.BASE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root/'mock_source.txt'; self.source.write_text('MOCK ONLY, not production')
        self.tool = self.root/'test_results/phase11f4_user_arena/run_canonical_03.py'
        self.tool.parent.mkdir(parents=True); self.tool.write_text('# MOCK ONLY launcher identity')
        self.source_map = {'mock_source.txt':p.sha(self.source)}
        self.gates = ['MOCK gate '+str(i) for i in range(72)]
        self.mp = self.root/'MOCK_manifest_04.json'
        self.rp = self.root/'MOCK_complete_review_05.json'
        self.m = {'schema':'MOCK ONLY manifest', 'source_sha256':self.source_map,
                  'source_pin_count':1, 'artifact_sha256':{str(self.tool):p.sha(self.tool)},
                  'artifact_pin_count':1, 'gate_identities':self.gates}
        self.save(self.mp, self.m)
        self.r = {'schema':p.REVIEW_SCHEMA, 'scope':'MOCK ONLY, NOT independent approval or evidence',
                  'review_complete':True, 'verdict':'APPROVE', 'blockers':[], 'blocker_count':0,
                  'authorizes_canonical_acceptance':True,
                  'candidate_manifest':{'path':str(self.mp),'sha256':p.sha(self.mp)},
                  'candidate_manifest_sha256':p.sha(self.mp), 'source_sha256':self.source_map,
                  'checks':[{'area':x,'status':'PASS','basis':'MOCK ONLY'} for x in p.REQUIRED_AREAS]}
        self.save(self.rp,self.r)
        self.out=self.root/'MOCK_output'
        self.out.mkdir()
        self.ap=self.out/'acceptance_MOCK_ONLY'/'acceptance.json'
        self.ap.parent.mkdir()
        self.a={'scope':'MOCK ONLY, NOT acceptance evidence','overall':'PASS', 'gates_passed':72,
                'gates_total':72,'source_sha256':self.source_map,
                'gates':[{'gate':x,'status':'PASS','exit_code':0} for x in self.gates]}
        self.save(self.ap,self.a)
        (self.out/'driver.log').write_text('MOCK ONLY: no subprocess launched')
        self.dp=self.out/'driver_result.json'
        self.d={'scope':'MOCK ONLY, NOT a real process result','schema':'rosti.f4-canonical-driver.v3',
                'status':'COMPLETED','exit_code':0,'overall':'PASS','source_stable':True,
                'cwd':str(self.root),'output_path':str(self.out),'interpreter':sys.executable,
                'command':[sys.executable,'-B',str(self.root/'scripts/phase6_verify.py'),'--output-dir',str(self.out)],
                'runner_pid':123,'exit_observed_by':'Popen.wait',
                'source_before':self.source_map,'source_after':self.source_map,
                'review_path':str(self.rp),'review_sha256':p.sha(self.rp),
                'candidate_manifest_path':str(self.mp),'candidate_manifest_sha256':p.sha(self.mp),
                'driver_path':str(self.tool),'driver_sha256':p.sha(self.tool),
                'log_sha256':p.sha(self.out/'driver.log'), 'acceptance_paths':[str(self.ap)],
                'acceptance_path':str(self.ap),'acceptance_sha256':p.sha(self.ap),
                'gates_passed':72,'gates_total':72,'gate_multiset_exact':True}
        self.save(self.dp,self.d)

    @staticmethod
    def save(path,data):
        path.write_text(json.dumps(data),encoding='utf8')

    def admit(self):
        with patch('subprocess.Popen',side_effect=AssertionError('NO SUBPROCESS')) as spawn:
            try:
                return p.validate_admission(self.rp,p.sha(self.rp),self.mp,p.sha(self.mp),self.source_map,self.root,(self.tool,))
            finally:
                spawn.assert_not_called()
                self.assertFalse(p.OUT.exists())

    def driver(self):
        with patch('subprocess.Popen',side_effect=AssertionError('NO SUBPROCESS')) as spawn:
            try:
                return p.validate_driver(self.dp,self.source_map,self.gates,self.root,self.out,(self.tool,))
            finally:
                spawn.assert_not_called()
                self.assertFalse(p.OUT.exists())

    def test_complete_mock_review_admitted_pure_only(self):
        with patch('subprocess.Popen',side_effect=AssertionError('NO SUBPROCESS')) as spawn:
            self.assertEqual(self.admit()['manifest'],self.m)
            spawn.assert_not_called()

    def test_required_fields_each_missing(self):
        original=copy.deepcopy(self.r)
        for key in ('schema','review_complete','verdict','blockers','blocker_count','authorizes_canonical_acceptance','candidate_manifest','candidate_manifest_sha256','source_sha256','checks'):
            with self.subTest(key=key):
                self.r=copy.deepcopy(original);del self.r[key];self.save(self.rp,self.r)
                with self.assertRaises((RuntimeError,KeyError,TypeError)): self.admit()

    def test_contradictions_and_nonzero_blockers(self):
        original=copy.deepcopy(self.r)
        for key,value in [('review_complete',False),('verdict','REJECT'),('blockers',[{'id':'MOCK BLOCKER'}]),('blocker_count',1),('blocker_count',False),('authorizes_canonical_acceptance',False)]:
            with self.subTest(key=key,value=value):
                self.r=copy.deepcopy(original);self.r[key]=value;self.save(self.rp,self.r)
                with self.assertRaises(RuntimeError): self.admit()

    def test_check_area_missing_failed_duplicate_or_dict(self):
        for checks in [self.r['checks'][:-1],self.r['checks']+[self.r['checks'][0]],{'spot':'PASS'},[dict(c,status='FAIL') for c in self.r['checks']]]:
            with self.subTest(checks_type=type(checks).__name__):
                self.r['checks']=checks;self.save(self.rp,self.r)
                with self.assertRaises(RuntimeError):self.admit()

    def test_manifest_path_disagreement(self):
        self.r['candidate_manifest']['path']=str(self.root/'other_manifest.json');self.save(self.rp,self.r)
        with self.assertRaisesRegex(RuntimeError,'path mismatch'):self.admit()

    def test_manifest_hash_disagreement(self):
        self.r['candidate_manifest_sha256']='0'*64;self.save(self.rp,self.r)
        with self.assertRaisesRegex(RuntimeError,'hash mismatch'):self.admit()

    def test_stale_manifest_bytes(self):
        self.mp.write_text(self.mp.read_text()+' ')
        with self.assertRaisesRegex(RuntimeError,'hash mismatch'):self.admit()

    def test_stale_review_hash(self):
        with self.assertRaisesRegex(RuntimeError,'review raw hash'):
            p.validate_admission(self.rp,'0'*64,self.mp,p.sha(self.mp),self.source_map,self.root,(self.tool,))

    def test_stale_source_membership_and_hash(self):
        for source in [{},dict(self.source_map,extra='0'*64),{'mock_source.txt':'0'*64}]:
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError,'source mismatch'):
                    p.validate_admission(self.rp,p.sha(self.rp),self.mp,p.sha(self.mp),source,self.root,(self.tool,))

    def test_mutated_source_bytes(self):
        self.source.write_text('MOCK mutated')
        with self.assertRaisesRegex(RuntimeError,'source bytes mismatch'):self.admit()

    def test_mutated_artifact_refused(self):
        self.tool.write_text('# MOCK mutation')
        with self.assertRaisesRegex(RuntimeError,'candidate artifact drift'):self.admit()

    def test_tools_must_be_frozen(self):
        with self.assertRaisesRegex(RuntimeError,'tool not frozen'):
            p.validate_admission(self.rp,p.sha(self.rp),self.mp,p.sha(self.mp),self.source_map,self.root,(self.root/'missing_tool.py',))

    def test_actual_historical_reviews_rejected_before_spawn(self):
        sys.path.insert(0,str(p.ROOT/'scripts'))
        import phase6_verify
        for number in ('02','03','04'):
            review=p.BASE/'reviews'/('candidate_review_'+number+'.json')
            manifest=p.BASE/'candidate_manifest_03.json'
            with self.subTest(review=number), patch.object(phase6_verify,'source_snapshot',return_value=self.source_map), patch('subprocess.Popen',side_effect=AssertionError('NO ACCEPTANCE')) as spawn:
                with self.assertRaises(RuntimeError):launcher.main([str(review),p.sha(review),str(manifest),p.sha(manifest)])
                spawn.assert_not_called()
                self.assertFalse(p.OUT.exists(),'production output must not exist')

    def test_malformed_review_launcher_rejects_without_output_or_spawn(self):
        sys.path.insert(0,str(p.ROOT/'scripts'))
        import phase6_verify
        for key,value in [('review_complete',False),('blocker_count',3),('verdict','REJECT'),('authorizes_canonical_acceptance',False)]:
            self.r[key]=value;self.save(self.rp,self.r)
            with self.subTest(key=key),patch.object(phase6_verify,'source_snapshot',return_value=self.source_map),patch('subprocess.Popen',side_effect=AssertionError('NO ACCEPTANCE')) as spawn:
                with self.assertRaises(RuntimeError):launcher.main([str(self.rp),p.sha(self.rp),str(self.mp),p.sha(self.mp)])
                spawn.assert_not_called();self.assertFalse(p.OUT.exists())

    def test_dynamic_mock_driver_roundtrip_pure_only(self):
        with patch('subprocess.Popen',side_effect=AssertionError('NO SUBPROCESS')) as spawn:
            self.assertEqual(self.driver()[2],self.ap)
            spawn.assert_not_called()

    def test_driver_missing_manifest_metadata_or_stale_schema(self):
        original=copy.deepcopy(self.d)
        for key,value in [('candidate_manifest_path',None),('candidate_manifest_sha256',None),('schema','rosti.f4-canonical-driver.v2')]:
            with self.subTest(key=key):
                self.d=copy.deepcopy(original);self.d[key]=value;self.save(self.dp,self.d)
                with self.assertRaises((RuntimeError,TypeError)):self.driver()

    def test_driver_command_ownership_exit_and_source_contradictions(self):
        original=copy.deepcopy(self.d)
        for key,value in [('command',['MOCK wrong runner']),('cwd','wrong'),('output_path','wrong'),('exit_code',1),('exit_code',False),('runner_pid',None),('exit_observed_by','unobserved'),('source_after',{}),('acceptance_paths',['foreign']),('acceptance_path','foreign'),('driver_sha256','0'*64),('log_sha256','0'*64)]:
            with self.subTest(key=key):
                self.d=copy.deepcopy(original);self.d[key]=value;self.save(self.dp,self.d)
                with self.assertRaises(RuntimeError):self.driver()

    def test_ambiguous_invocation_acceptance(self):
        other=self.out/'acceptance_MOCK_other'/'acceptance.json';other.parent.mkdir();self.save(other,self.a)
        with self.assertRaisesRegex(RuntimeError,'ownership/ambiguity'):self.driver()

    def test_stale_acceptance_bytes(self):
        self.ap.write_text(self.ap.read_text()+' ')
        with self.assertRaisesRegex(RuntimeError,'acceptance hash mismatch'):self.driver()

    def test_exact72_gate_multiset_and_failed_gate_refusals(self):
        original=copy.deepcopy(self.a)
        variants=[original['gates'][:-1],original['gates']+[original['gates'][0]],original['gates'][:-1]+[original['gates'][0]], [dict(g,status='FAIL') for g in original['gates']]]
        for gates in variants:
            with self.subTest(length=len(gates)):
                a=copy.deepcopy(original);a['gates']=gates
                with self.assertRaises(RuntimeError):p.validate_acceptance(a,self.gates,self.source_map)

    def test_readers_import_without_side_effects(self):
        with patch('subprocess.Popen',side_effect=AssertionError('NO ACCEPTANCE')) as spawn:
            importlib.import_module('canonical_readback_03')
            importlib.import_module('canonical_identity_readback_03')
            spawn.assert_not_called()
        self.assertFalse(p.OUT.exists())
        for n in ('parent_canonical_readback_03.json','canonical_identity_readback_03.json','canonical_iso_kernel_03.bin'):
            self.assertFalse((p.BASE/n).exists())

    def test_inherited_deep_evidence_checks_preserved(self):
        old=(p.BASE/'canonical_readback_02.py').read_text()
        new=(p.BASE/'canonical_readback_03.py').read_text()
        inherited=old[old.index('    predecessor=predecessor_contract()'):old.index("    report.update(overall='PASS'")]
        for line in inherited.splitlines():
            line=line.strip().replace('canonical_iso_kernel_02.bin','canonical_iso_kernel_03.bin')
            if line:self.assertIn(line,new)
        old=(p.BASE/'canonical_identity_readback_02.py').read_text()
        new=(p.BASE/'canonical_identity_readback_03.py').read_text()
        for line in old[old.index('rows=[]'):old.index("report={'overall'")].splitlines():
            if line.strip():self.assertIn(line.strip(),new)

    def test_real_runner_cli_nesting_static_contract(self):
        source=(p.ROOT/'scripts/phase6_verify.py').read_text()
        self.assertIn('parent = (args.output_dir or PROJECT / "test_results" / "phase11").resolve()',source)
        self.assertIn('run = Path(tempfile.mkdtemp(prefix=f"acceptance_{stamp}_", dir=parent))',source)
        self.assertIn('(run / "acceptance.json").write_text',source)

    def test_duplicate_json_keys_refused(self):
        self.rp.write_text('{"verdict":"REJECT","verdict":"APPROVE"}')
        with self.assertRaisesRegex(RuntimeError,'duplicate JSON key'):self.admit()

    def test_actual_launcher_cli_rejects_review02_without_output(self):
        review=p.BASE/'reviews/candidate_review_02.json'
        manifest=p.BASE/'candidate_manifest_03.json'
        result=subprocess.run([sys.executable,'-B',str(p.BASE/'run_canonical_03.py'),str(review),p.sha(review),str(manifest),p.sha(manifest)],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        self.assertIn('insufficient historical review02 refused',result.stderr)
        self.assertFalse(p.OUT.exists())
        print('REAL_CLI_REVIEW02_REFUSAL exit='+str(result.returncode)+' output_created=False')

    def test_source_and_artifact_declared_count_refusals(self):
        original=copy.deepcopy(self.m)
        for key in ('source_pin_count','artifact_pin_count'):
            with self.subTest(key=key):
                self.m=copy.deepcopy(original);self.m[key]=2;self.save(self.mp,self.m)
                self.r['candidate_manifest']['sha256']=p.sha(self.mp)
                self.r['candidate_manifest_sha256']=p.sha(self.mp);self.save(self.rp,self.r)
                with self.assertRaisesRegex(RuntimeError,'count mismatch'):self.admit()

    def test_actual_optimized_python_refused_before_acceptance(self):
        for script in ('run_canonical_03.py','canonical_readback_03.py','canonical_identity_readback_03.py'):
            with self.subTest(script=script):
                result=subprocess.run([sys.executable,'-B','-O',str(p.BASE/script)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('optimized execution refused',result.stderr)
                print('OPTIMIZED_REFUSAL '+script+' exit='+str(result.returncode))
        result=subprocess.run([sys.executable,'-B',str(p.BASE/'run_canonical_03.py')],env={**os.environ,'PYTHONOPTIMIZE':'1'},capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('optimized execution refused',result.stderr)
        self.assertFalse(p.OUT.exists())

if __name__ == '__main__':
    p.unoptimized()
    unittest.main(verbosity=2)
