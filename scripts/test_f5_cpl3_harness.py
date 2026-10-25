"""F5 host-only refusal controls. Synthetic bytes below are NOT guest evidence."""
from collections import Counter
import argparse
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'test_results/phase11f5_cpl3_proof'
sys.path.insert(0, str(ROOT/'scripts'))
import phase6_verify as runner
import f5_cpl3_guest as guest
import f5_cpl3_evidence as evidence
import f5_entry_derivation as derivation
import f5_terminal_audit as audit


def clone(value):
    return copy.deepcopy(value)


class IntegrationTests(unittest.TestCase):
    def test_exact_76_gate_contract(self):
        contract = runner.f5_contract()
        expected = Counter(contract['predecessor_identities'] + contract['f5_gates'])
        actual = Counter(runner.F3_PREDECESSOR_GATES) + Counter(runner.F4_GATES) + Counter(runner.F5_GATES)
        self.assertEqual(actual, expected)
        self.assertEqual(sum(actual.values()), 76)
        self.assertEqual(set(actual.values()), {1})
        self.assertEqual(Counter(runner.F5_HOST_REQUIRED), Counter(contract['host_identities']))

    def test_missing_duplicate_extra_substituted_and_failed_gates_refuse(self):
        names = (*runner.F3_PREDECESSOR_GATES, *runner.F4_GATES, *runner.F5_GATES)
        rows = [{'gate': name, 'status': 'PASS', 'exit_code': 0} for name in names]
        runner.validate_f5_gates(rows)
        mutations = [lambda r: r.pop(), lambda r: r.append(clone(r[-1])),
                     lambda r: r[-1].update(gate=r[-2]['gate']),
                     lambda r: r[-1].update(gate='unapproved F5 substitute'),
                     lambda r: r[-1].update(status='FAIL'), lambda r: r[-1].update(exit_code=1),
                     lambda r: r[-1].update(exit_code=False)]
        for mutation in mutations:
            bad = clone(rows); mutation(bad)
            with self.subTest(rows=bad[-2:]), self.assertRaisesRegex(RuntimeError, 'gate identity'):
                runner.validate_f5_gates(bad)

    def test_predecessor_raw_hash_and_identities_refuse(self):
        self.assertEqual(hashlib.sha256((ROOT/runner.F4_PREDECESSOR_PATH).read_bytes()).hexdigest(),
                         '3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4')
        runner.f4_predecessor_contract()
        with patch.object(runner, 'F4_PREDECESSOR_SHA256', '0'*64):
            with self.assertRaisesRegex(RuntimeError, 'digest mismatch'):
                runner.f4_predecessor_contract()
        real = json.loads((ROOT/runner.F4_PREDECESSOR_PATH).read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root/runner.F4_PREDECESSOR_PATH
            path.parent.mkdir(parents=True)
            for mutate in (lambda r: r['gates'].pop(),
                           lambda r: r['gates'][-1].update(gate=r['gates'][-2]['gate']),
                           lambda r: r.update(gates_passed=71),
                           lambda r: r['gates'][-1].update(exit_code=1)):
                bad = clone(real); mutate(bad); path.write_text(json.dumps(bad))
                with patch.object(runner, 'PROJECT', root), patch.object(runner, 'F4_PREDECESSOR_SHA256', runner.sha256(path)):
                    with self.assertRaisesRegex(RuntimeError, 'identity multiset'):
                        runner.f4_predecessor_contract()

    def test_nonzero_exact_fourteen_and_no_ignored_membership(self):
        names = runner.F5_HOST_REQUIRED
        def output(rows, passed=None, ignored=0):
            return ''.join(f'test {n} ... ok\n' for n in rows) + f'test result: ok. {len(rows) if passed is None else passed} passed; 0 failed; {ignored} ignored\n'
        runner.validate_f5_host(output(names))
        for text in ('', output([]), output(names[:-1]), output(names+(names[0],)),
                     output(names[:-1]+(names[0],)), output(names[:-1]+('impostor',)),
                     output(names, 0), output(names, ignored=1), output(names)+output(names),
                     output(names)+'test unapproved::ignored ... ignored\n'):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, 'fourteen'):
                runner.validate_f5_host(text)
        listing = ''.join(f'{n}: test\n' for n in names)+'14 tests, 0 benchmarks\n'
        runner.validate_f5_host(listing, listing=True)
        with self.assertRaisesRegex(RuntimeError, 'fourteen'):
            runner.validate_f5_host(listing.replace(names[-1], 'renamed'), listing=True)

    def test_full_rust_ancestry_is_source_declared(self):
        files = [('tests_kernel/src/f5_cpl3_tests.rs', 'f5_cpl3_tests::'),
                 ('src/memory/f5_cpl3_owner_tests.rs', 'memory::paging::f5_cpl3_owner_tests::')]
        import re
        names = []
        for path, prefix in files:
            text = (ROOT/path).read_text()
            names += [prefix+n for n in re.findall(r'#\[test\]\s*fn (\w+)\(', text)]
        self.assertEqual(Counter(names), Counter(runner.F5_HOST_REQUIRED))

    def test_four_validator_suites_and_new_gate_timeouts_are_explicit(self):
        self.assertEqual(set(runner.F5_PYTHON_TESTS), {'test_f5_cpl3_harness', 'test_f5_entry_derivation',
                                                    'test_f5_terminal_audit', 'test_f5_cpl3_evidence'})
        tree = ast.parse(Path(runner.__file__).read_text())
        gates = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == 'gate' and n.args and isinstance(n.args[0], ast.Subscript)
                 and isinstance(n.args[0].value, ast.Name) and n.args[0].value.id == 'F5_GATES']
        self.assertEqual(sorted(ast.literal_eval(n.args[0].slice) for n in gates), [0,1,2,3])
        for gate in gates:
            self.assertEqual(next(ast.literal_eval(k.value) for k in gate.keywords if k.arg == 'timeout'), 900)
        inherited = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == 'gate' and n.args and isinstance(n.args[0], ast.Constant)
                     and n.args[0].value in ('acceptance runner regressions', 'Phase 11F3 minimal Ring0 hardware matrix')]
        self.assertEqual({n.args[0].value: next(ast.literal_eval(k.value) for k in n.keywords if k.arg == 'timeout')
                          for n in inherited}, {'acceptance runner regressions':1049,'Phase 11F3 minimal Ring0 hardware matrix':2100})

    def test_narrow_authority_and_imported_task_modules_are_frozen(self):
        snapshot = runner.source_snapshot()
        for name in ('design.md','harness_contract_01.json','entry_design_amendment_01.md',
                     'f2_before_macro_01.elf','run_cpl3_probe_01.py'):
            self.assertIn((BASE/name).relative_to(ROOT).as_posix(), snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); authority = root/runner.F5_ROOT; authority.mkdir(parents=True)
            (authority/'design.md').write_text('approved authority fixture only')
            (authority/'imported.py').write_text('mock helper')
            (authority/'unlisted-report.json').write_text('{}')
            with patch.object(runner,'PROJECT',root):
                first = runner.source_snapshot()
                self.assertIn(runner.F5_ROOT+'/imported.py',first)
                self.assertNotIn(runner.F5_ROOT+'/unlisted-report.json',first)
                (authority/'design.md').write_text('drift')
                self.assertNotEqual(first,runner.source_snapshot())

    def test_existing_emitted_mapper_rejects_unapproved_alias(self):
        with self.assertRaisesRegex(RuntimeError, 'unknown|unapproved|forbidden'):
            audit.normalize(('call', '0x1234 <f5_fatal>'), True)
        self.assertEqual(audit.normalize(('call','0x1234 <f5_bridge>'),True),('call','f2_fatal'))
        for target in ('eax','[eax]','0x1234','0x1234 <f5_unknown>'):
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                audit.normalize(('call',target),True)

    def test_raw_f2_hash_precedes_lexical_equivalence(self):
        f2=(ROOT/'src/exception_entry.s').read_bytes(); f5=(ROOT/'src/f5_exception_entry.s').read_bytes()
        self.assertEqual(derivation.compare_bytes(f2,f5)['overall'],'PASS')
        with self.assertRaisesRegex(RuntimeError,'raw SHA256'):
            derivation.compare_bytes(f2.replace(b'\n',b'\r\n'),f5)
        for raw in (f5+b'\nnop\n', f5.replace(b'push',b'pop',1), f5[:len(f5)//2],
                    f5.replace(b'f5_bridge',b'f5_fatal')):
            with self.subTest(raw_hash=hashlib.sha256(raw).hexdigest()), self.assertRaises(RuntimeError):
                derivation.compare_bytes(f2,raw)

    def test_pin_ownership_staleness_and_generic_schema_stay_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); path=root/'report.json'; path.write_text('MOCK NOT EVIDENCE')
            pins={str(path):runner.sha256(path)}
            self.assertEqual(runner.validate_owned_pins(pins,root,[path]),pins)
            for bad in ({}, {str(path):'0'*64}, {'report.json':runner.sha256(path)}):
                with self.subTest(pins=bad), self.assertRaises(RuntimeError):
                    runner.validate_owned_pins(bad,root,[path])
            with self.assertRaisesRegex(RuntimeError,'invocation-owned'):
                runner.validate_owned_pins(pins,root/'other',[])
            with self.assertRaisesRegex(RuntimeError,'empty harness rows'):
                runner.evidence_rows({'overall':'PASS','schema':'rosti.f5-cpl3-matrix.v1'},path)

    def test_review_requires_actual_scope_findings_not_metadata_only(self):
        # This temporary schema fixture is explicitly NOT independent approval.
        frozen={'UNIT_MODEL_ONLY':'0'*64}
        model={'schema':'rosti.f5-candidate-review.v1','verdict':'APPROVE','complete_scope':True,
               'reviewer':{'independent':True,'identity':'UNIT MODEL ONLY'},'blockers':[],
               'source_sha256':frozen,'findings':[{'area':area,'verdict':'APPROVE',
               'evidence':['UNIT MODEL ONLY scope-validation control']} for area in runner.F5_REVIEW_AREAS]}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'UNIT_MODEL_ONLY_REVIEW.json'
            path.write_text(json.dumps(model))
            runner.validate_f5_review(path,runner.sha256(path),frozen)
            for mutate in (lambda r:r.update(findings=[]), lambda r:r['findings'].pop(),
                           lambda r:r['findings'][-1].update(area=r['findings'][0]['area']),
                           lambda r:r['findings'][-1].update(evidence=[]),
                           lambda r:r.update(source_sha256={}),lambda r:r.update(complete_scope=False),
                           lambda r:r.update(blockers=['open']),lambda r:r['reviewer'].update(independent=False)):
                bad=clone(model);mutate(bad);path.write_text(json.dumps(bad))
                with self.assertRaisesRegex(RuntimeError,'stale/incomplete/narrow'):
                    runner.validate_f5_review(path,runner.sha256(path),frozen)
            path.write_text(json.dumps(model))
            with self.assertRaisesRegex(RuntimeError,'digest mismatch'):
                runner.validate_f5_review(path,'0'*64,frozen)
        with self.assertRaisesRegex(RuntimeError,'byte-pinned'):
            runner.validate_f5_review(None,None,frozen)


class AdmissionTests(unittest.TestCase):
    def test_exact_parser_grammar_and_types(self):
        for n in range(1,7): self.assertEqual(guest.parse_scenario(str(n)),n)
        invalid=['',' ',' 1','1 ','0','7','-1','+1','01','1.0','1e0','True','false','A','1x','\u0661','\uff11',
                 True,False,1,1.0,None,[],{},('1',)]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(argparse.ArgumentTypeError): guest.parse_scenario(value)

    def test_real_main_refuses_before_all_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'must_not_exist'
            bad=[['--scenario','01'],['--scenario','1','--scenario','2'],['--scenario=1','--scenario=2'],
                 ['--scenario','1','2'],['--ram','128'],['--unknown'],['--scen','1']]
            for tail in bad:
                with self.subTest(argv=tail),patch.object(guest,'RunnerLock') as lock,patch.object(guest,'run') as run, \
                     patch.object(guest,'build_fixture') as build,patch.object(guest,'capture') as capture, \
                     patch.object(guest.subprocess,'Popen') as spawn,contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error: guest.main(['--output-dir',str(output),*tail])
                    self.assertEqual(error.exception.code,2)
                    for operation in (lock,run,build,capture,spawn): operation.assert_not_called()
                    self.assertFalse(output.exists())

    def test_valid_raw_parser_dispatch_is_exact_integer(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'unused'
            for n in range(1,7):
                with patch.object(guest,'RunnerLock') as lock,patch.object(guest,'run',return_value=0) as run:
                    self.assertEqual(guest.main(['--output-dir',str(output),'--scenario',str(n)]),0)
                    self.assertEqual(type(run.call_args.args[0].scenario),int)
                    self.assertEqual(run.call_args.args[0].scenario,n)
                    self.assertEqual(guest.IDENTITIES[n-1],evidence.IDENTITIES[n-1])
                    lock.assert_called_once_with()
                self.assertFalse(output.exists())

    def test_actual_cli_malformed_and_duplicate_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'must_not_exist'
            for tokens in (['--scenario','01'],['--scenario','\u0661'],['--scenario','1','--scenario','2']):
                result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/f5_cpl3_guest.py'),
                    '--output-dir',str(output),*tokens],capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,2,result.stderr)
                self.assertIn('error:',result.stderr)
                self.assertFalse(output.exists())

    def test_actual_optimized_and_inherited_optimization_refusal(self):
        for name in ('phase6_verify.py','f5_cpl3_guest.py','f5_cpl3_evidence.py',
                     'f5_terminal_audit.py','f5_entry_derivation.py'):
            for flags,env in ((['-O'],dict(os.environ,PYTHONOPTIMIZE='')),([],dict(os.environ,PYTHONOPTIMIZE='1'))):
                with self.subTest(script=name,flags=flags):
                    result=subprocess.run([sys.executable,'-B',*flags,str(ROOT/'scripts'/name),'--help'],
                                          env=env,capture_output=True,text=True,timeout=20)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('optimized',result.stdout+result.stderr)


class RawEvidenceTests(unittest.TestCase):
    def matrix(self):
        return [{'scenario':name,'scenario_integer':n,'ram_mib':ram}
                for n,name in enumerate(evidence.IDENTITIES,1) for ram in (128,512)]

    def test_missing_scenario_ram_duplicate_and_model_report_refuse(self):
        rows=self.matrix();evidence.validate_matrix_rows(rows)
        for bad in (rows[:-1],rows+[rows[0]],rows[:-1]+[rows[0]],list(reversed(rows)),
                    [{**r,'ram_mib':str(r['ram_mib'])} for r in rows],
                    [{**r,'scenario':'model_only'} for r in rows]):
            with self.subTest(rows=bad),self.assertRaises(ValueError):evidence.validate_matrix_rows(bad)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'report.json').write_text(json.dumps({'schema':'MODEL_ONLY','overall':'PASS'}))
            with self.assertRaisesRegex(ValueError,'aggregate outcome'):evidence.validate(root)

    @staticmethod
    def record(scenario=1,af=0,padding=0):
        words=[0]*64;vector,error,cr2=evidence.FAULTS[scenario-1]
        words[:16]=[0x46354350,scenario,1,0x07c04fb4,0x07c04f9c,0x80010001,cr2 or 0,0x1000,0,0,8,16,16,16,16,16]
        frame=[0x33]*4+[0,0,0,0x07c04fe4,0x5a17c0de,0,0,0x2b,vector,error,
               0x4000010c+(scenario-1)*64,padding|0x2b,0x10446|af,0x40400000,padding|0x33]
        words[16:35]=frame;words[35]=55;words[37:41]=[24,0x07c05000,16,104]
        return bytearray(struct.pack('<64I',*words))

    def test_raw_record_all_six_faults_af_and_padded_cpu_selectors(self):
        for scenario in range(1,7):
            for af in (0,0x10):
                for padding in (0,0xabcd0000):
                    evidence.records(self.record(scenario,af,padding),scenario,0x1000,0x446|af)

    def test_wrong_cs_ss_pc_error_cr2_rf_tail_bounds_tss_marker_refuse(self):
        controls={0:0,2:0,3:0x07c04fb0,4:0x07c04f98,7:0x2000,16+7:0x07c04fe0,
                  16+8:0,16+13:0x80000007,16+14:0x40000100,16+15:8,16+16:0x446,
                  16+17:0x40400004,16+18:16,35:39,37:40,38:0x07c04000,39:0,40:0,41:1}
        for word,value in controls.items():
            raw=self.record(2);struct.pack_into('<I',raw,word*4,value)
            with self.subTest(word=word),self.assertRaises(ValueError):evidence.records(raw,2,0x1000,0x446)
        raw=self.record(2);struct.pack_into('<I',raw,6*4,0x40000804)
        with self.assertRaisesRegex(ValueError,'CR3/CR2'):evidence.records(raw,2,0x1000,0x446)
        with self.assertRaisesRegex(ValueError,'extent'):evidence.records(self.record()[:68],1,0x1000,0x446)

    def test_unlisted_stale_and_missing_artifact_bytes_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'raw.bin';path.write_bytes(b'raw observation fixture')
            pins=evidence.tree_pins(root);evidence.verify_pins(root,pins)
            path.write_bytes(b'stale')
            with self.assertRaises(ValueError):evidence.verify_pins(root,pins)
            path.write_bytes(b'raw observation fixture');(root/'unlisted.bin').write_bytes(b'unlisted')
            with self.assertRaisesRegex(ValueError,'unlisted'):evidence.verify_pins(root,pins)
            (root/'unlisted.bin').unlink();path.unlink()
            with self.assertRaises((ValueError,FileNotFoundError)):evidence.verify_pins(root,pins)

    def test_process_cleanup_marker_only_uart_failure_and_model_only_refuse_before_io(self):
        row={'overall':'PASS','capture_complete':True,'hardware_cpl3':True,'owned_qemu_exited':True,
             'owned_pid':123,'qemu_exit':0,'qemu_exit_before_cleanup':None,'cleanup_errors':[],
             'debugger_mutations':[],'checks':[{'pass':True}]}
        mutations=[lambda r:r.update(hardware_cpl3=False),lambda r:r.update(capture_complete=False),
                   lambda r:r.update(owned_qemu_exited=False),lambda r:r.update(qemu_exit=None),
                   lambda r:r.update(owned_pid=0),lambda r:r.update(qemu_exit_before_cleanup=0),
                   lambda r:r.update(cleanup_errors=['kill/wait missing']),lambda r:r.update(debugger_mutations=['M write']),
                   lambda r:r.update(overall='UART_TIMEOUT'),lambda r:r.update(checks=[])]
        for mutation in mutations:
            bad=clone(row);mutation(bad)
            with self.subTest(row=bad),self.assertRaisesRegex(ValueError,'cleanup|checks'):
                evidence.validate_guest(Path('DOES_NOT_EXIST'),bad,{}, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
