"""Independent host-only controls. Synthetic rows are not runtime evidence."""
import copy
import contextlib
import json
import tempfile
from unittest import mock
from pathlib import Path
import subprocess
import sys
import unittest

import f5_terminal_audit as audit


def row(pc, mnemonic, operand='', raw='90'):
    return {'pc': pc, 'mnemonic': mnemonic, 'operand': operand,
            'bytes': raw, 'size': len(bytes.fromhex(raw))}


class NormalizeControls(unittest.TestCase):
    def test_both_terminal_aliases(self):
        for alias in ('f5_entry_terminal', 'f5_terminal'):
            self.assertEqual(audit.normalize(('jmp', '0x123 <'+alias+'+0x1>'), True),
                             ('jmp', 'f2_terminal+0x1'))

    def test_all_exact_vector_aliases(self):
        for vector in range(32):
            self.assertEqual(audit.normalize(('jmp', f'0x123 <f5_exc_{vector}>'), True),
                             ('jmp', f'f2_exc_{vector}'))

    def test_unknown_aliases_never_disappear(self):
        for name in ('f5_fatal','f5_exc_32','f5_exc_01','f5_terminal_extra','f5_bridge_fake','F5_WRONG'):
            for mnemonic, operand in [('jmp',f'0x123 <{name}>'), ('mov',f'eax, [{name}]')]:
                with self.subTest(name=name, mnemonic=mnemonic), self.assertRaisesRegex(RuntimeError, 'unknown F5'):
                    audit.normalize((mnemonic,operand),True)

    def test_old_signature_and_offset_binding(self):
        self.assertEqual(audit.normalize(('mov','eax, esp')), ('mov','eax, esp'))
        self.assertEqual(audit.normalize(('jmp','0x100 <f2_terminal+0x2>')),
                         ('jmp','f2_terminal+0x2'))
        self.assertNotEqual(audit.normalize(('jmp','0x100 <f5_terminal+0x2>'), True),
                            ('jmp','f2_terminal+0x1'))

    def test_indirect_comparison_refused(self):
        for operand in ('eax','dword ptr [eax]','0x100'):
            with self.assertRaisesRegex(RuntimeError, 'comparison edge'):
                audit.normalize(('call',operand))


class ClosureControls(unittest.TestCase):
    def graph(self, rows, calls=(), iret=None):
        return audit.closure(rows,[0],set(rows),set(calls),iret)

    def test_exact_halt_cycle(self):
        rows={0:row(0,'cli',raw='fa'),1:row(1,'hlt',raw='f4'),2:row(2,'jmp','0x1 <halt>',raw='ebfd')}
        result=self.graph(rows)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['instructions']),3)
        self.assertIn({'from':1,'to':2,'kind':'halt_wakeup_fallthrough'},result['edges'])

    def test_conditional_forbidden_arm_not_pruned(self):
        rows={0:row(0,'je','0x3 <bad>'),1:row(1,'jmp','0x1 <loop>'),3:row(3,'ret')}
        result=self.graph(rows)
        self.assertFalse(result['complete'])
        self.assertTrue(any(v.get('mnemonic')=='ret' for v in result['violations']))

    def test_call_continuation_inspected_even_divergent_target(self):
        rows={0:row(0,'call','0x4 <terminal>'),1:row(1,'ret'),4:row(4,'jmp','0x4 <terminal>')}
        self.assertFalse(self.graph(rows,(4,))['complete'])

    def test_every_foreign_call_tail_indirect_and_trap_rejected(self):
        for mnemonic,operand in [('call','0x4 <panic>'),('jmp','eax'),('call','dword ptr [eax]'),
                                 ('ret',''),('int3',''),('ud2',''),('sysenter',''),('loop','0x0')]:
            rows={0:row(0,mnemonic,operand),1:row(1,'jmp','0x1 <loop>'),4:row(4,'jmp','0x4 <panic>')}
            with self.subTest(mnemonic=mnemonic,operand=operand):
                self.assertFalse(self.graph(rows)['complete'])

    def test_foreign_tail_and_noncontiguous_fallthrough_rejected(self):
        for rows in ({0:row(0,'jmp','0x99 <foreign>')},
                     {0:row(0,'mov','eax, ebx'),2:row(2,'jmp','0x2 <loop>')}):
            self.assertFalse(self.graph(rows)['complete'])

    def test_iret_only_at_exact_reviewed_pc(self):
        rows={0:row(0,'iretd',raw='cf')}
        self.assertFalse(self.graph(rows)['complete'])
        self.assertTrue(self.graph(rows,iret=0)['complete'])


class AliasByteControls(unittest.TestCase):
    class Image:
        symbols={'terminal':{'address':0,'size':0}}
        def __init__(self, raw):
            self.raw=raw
        def read(self, pc, size, executable=False):
            return self.raw[pc:pc+size]

    def test_raw_bytes_and_target_mandatory(self):
        rows={0:row(0,'cli',raw='fa'),1:row(1,'hlt',raw='f4'),2:row(2,'jmp','0x1 <terminal+0x1>',raw='ebfd')}
        result=audit.terminal_alias(self.Image(bytes.fromhex('faf4ebfd')),rows,'terminal')
        self.assertEqual(result['raw_hex'],'faf4ebfd')
        for raw in ('fbf4ebfd','faf4ebfc','faf49090'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                audit.terminal_alias(self.Image(bytes.fromhex(raw)),rows,'terminal')
        changed=copy.deepcopy(rows);changed[2]['operand']='0x0 <terminal>'
        with self.assertRaises(RuntimeError):
            audit.terminal_alias(self.Image(bytes.fromhex('faf4ebfd')),changed,'terminal')


class StackControls(unittest.TestCase):
    def fixture(self):
        rows = {
            0:row(0,'push','0x0'), 1:row(1,'push','0x6'), 2:row(2,'jmp','0x10 <common>'),
            3:row(3,'push','0xd'), 4:row(4,'jmp','0x10 <common>'),
            5:row(5,'push','0xe'), 6:row(6,'jmp','0x10 <common>'),
            7:row(7,'push','0x0'), 8:row(8,'push','0x2'), 9:row(9,'jmp','0x10 <common>'),
            16:row(16,'pushal'),17:row(17,'push','eax'),18:row(18,'push','eax'),
            19:row(19,'push','eax'),20:row(20,'push','eax'),
            21:row(21,'and','esp, -0x10'),22:row(22,'sub','esp, 0xc'),
            23:row(23,'push','eax'),24:row(24,'call','0x20 <bridge>'),
            25:row(25,'jmp','0x40 <terminal>'),
            32:row(32,'mov','edi, esp'),33:row(33,'pushfd'),34:row(34,'pop','ebx'),
            35:row(35,'jmp','0x40 <terminal>'),
            64:row(64,'cli'),65:row(65,'hlt'),66:row(66,'jmp','0x41 <halt>')}
        class Image:
            symbols={'f5_bridge':{'address':32,'size':4},
                     'f5_unsupported':{'address':64,'size':0},
                     'f5_terminal':{'address':64,'size':0},
                     'f5_entry_terminal':{'address':64,'size':0},
                     'f5_exc_6':{'address':0},'f5_exc_13':{'address':3},
                     'f5_exc_14':{'address':5},'f5_exc_2':{'address':7}}
        return rows, Image()

    def analyze(self, rows, image):
        graph=audit.closure(rows,[0,3,5,7],set(rows),{32})
        self.assertTrue(graph['complete'])
        return audit.stack_paths(rows,image,graph)

    def test_concrete_alignment_paths_not_sum_of_unrelated_maxima(self):
        rows,image=self.fixture()
        result=self.analyze(rows,image)
        self.assertEqual(result['max_first_entry_bytes'],104)
        self.assertEqual(result['conditional_stack_ceiling_bytes'],200)
        self.assertEqual(result['bridge_scratch_path']['max_bytes'],4)
        self.assertTrue(all(p['witness'] for p in result['one_nested_nmi_paths']))

    def test_unknown_esp_mutation_refused(self):
        rows,image=self.fixture()
        rows[35]=row(35,'xchg','eax, esp')
        rows[36]=row(36,'jmp','0x40 <terminal>')
        with self.assertRaisesRegex(RuntimeError,'XCHG ESP'):
            self.analyze(rows,image)

    def test_wrong_alignment_refused(self):
        rows,image=self.fixture();rows[21]['operand']='esp, -0x20'
        with self.assertRaisesRegex(RuntimeError,'alignment mask'):
            self.analyze(rows,image)

    def test_bridge_scratch_ceiling_refused(self):
        rows,image=self.fixture();rows[35]=row(35,'sub','esp, 0x50')
        rows[36]=row(36,'jmp','0x40 <terminal>')
        with self.assertRaisesRegex(RuntimeError,'64-byte ceiling'):
            self.analyze(rows,image)


class ArtifactAPIControls(unittest.TestCase):
    def test_read_only_validator_api_exists(self):
        self.assertTrue(callable(getattr(audit, 'validate_artifacts', None)))


class ArtifactReadbackControls(unittest.TestCase):
    """MOCK transport fixtures; real binary readback is a separate diagnostic."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root/'audit'
        self.directory.mkdir()
        self.elf, self.before, self.tool = [self.root/n for n in ('elf', 'before', 'objdump')]
        for p in (self.elf, self.before, self.tool):
            p.write_bytes(p.name.encode())
        self.baseline_sha = audit.sha(self.before.read_bytes())
        self.patch = contextlib.ExitStack()
        self.addCleanup(self.patch.close)
        self.patch.enter_context(mock.patch.object(audit, 'BEFORE_SHA256', self.baseline_sha))
        self.patch.enter_context(mock.patch.object(audit, 'discover_objdump', return_value=self.tool))
        pins = {}
        for name in audit.REQUIRED_ARTIFACTS:
            raw = name.encode()
            (self.directory/name).write_bytes(raw)
            pins[name] = audit.sha(raw)
        self.record = dict(overall='PASS', blockers=[], reader_sha256=audit.READER_SHA256,
            dependencies=audit.LOADED_PINS, checks=dict.fromkeys(audit.REQUIRED_CHECKS, True),
            elf=str(self.elf.resolve()), elf_sha256=audit.sha(self.elf.read_bytes()),
            before=str(self.before.resolve()), before_required_sha256=self.baseline_sha,
            before_elf_sha256=self.baseline_sha, objdump=str(self.tool),
            objdump_sha256=audit.sha(self.tool.read_bytes()), artifact_sha256=pins,
            terminal_closure={'complete': True, 'instructions': ['MOCK']})
        self.expected = copy.deepcopy(self.record)
        self.analyze = self.patch.enter_context(mock.patch.object(audit, 'analyze', return_value=self.expected))
        self.save()

    def save(self):
        (self.directory/'report.json').write_text(json.dumps(self.record))

    def validate(self):
        return audit.validate_artifacts(self.directory, self.elf)

    def test_read_only_success_recomputes_without_any_python_write(self):
        original = Path.open
        def readonly(path, mode='r', *args, **kwargs):
            if any(c in mode for c in 'wax+'):
                raise AssertionError('validator attempted write: '+str(path))
            return original(path, mode, *args, **kwargs)
        with mock.patch.object(Path, 'open', readonly), \
             mock.patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir')), \
             mock.patch.object(tempfile, 'TemporaryDirectory', side_effect=AssertionError('tempdir')):
            self.assertEqual(self.validate(), self.record)
        self.analyze.assert_called_once()
        self.assertIsInstance(self.analyze.call_args.args[3], audit.Artifacts)
        self.assertFalse(self.analyze.call_args.args[3].write)

    def test_exact_nonempty_check_sets_and_boolean_values(self):
        for checks in ({}, dict.fromkeys(audit.REQUIRED_CHECKS, 1),
                       {**self.record['checks'], 'invented': True},
                       {k: v for k, v in self.record['checks'].items() if k != 'stack_paths'},
                       {**self.record['checks'], 'stack_paths': False}):
            with self.subTest(checks=checks):
                self.record['checks'] = checks
                self.save()
                with self.assertRaisesRegex(RuntimeError, 'exact audit checks'):
                    self.validate()
        self.analyze.assert_not_called()

    def test_stale_reader_dependency_and_contract_pins(self):
        for key, value in [('reader_sha256', '0'*64), ('dependencies', {}),
                           ('dependencies', {**audit.LOADED_PINS, 'src/f5_contract.rs': '0'*64})]:
            with self.subTest(key=key):
                self.record = copy.deepcopy(self.expected)
                self.record[key] = value
                self.save()
                with self.assertRaisesRegex(RuntimeError, 'stale audit'):
                    self.validate()

    def test_live_dependencies_drift(self):
        with mock.patch.object(audit, 'current_pins', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'dependency'):
                self.validate()

    def test_exact_elf_path_and_bytes(self):
        other = self.root/'other'
        other.write_bytes(self.elf.read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'exact ELF'):
            audit.validate_artifacts(self.directory, other)
        self.elf.write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'exact ELF'):
            self.validate()

    def test_baseline_and_tool_bytes(self):
        for path, message in ((self.before, 'provenance'), (self.tool, 'objdump')):
            raw = path.read_bytes()
            path.write_bytes(b'tampered')
            with self.assertRaisesRegex(RuntimeError, message):
                self.validate()
            path.write_bytes(raw)

    def test_all_artifact_bytes_and_missing_files(self):
        for name in audit.REQUIRED_ARTIFACTS:
            path = self.directory/name
            raw = path.read_bytes()
            path.write_bytes(b'tampered')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'artifact pin'):
                self.validate()
            path.unlink()
            with self.assertRaisesRegex(RuntimeError, 'directory entries'):
                self.validate()
            path.write_bytes(raw)

    def test_exact_artifact_sets(self):
        self.record['artifact_sha256'] = {}
        self.save()
        with self.assertRaisesRegex(RuntimeError, 'exact artifact'):
            self.validate()
        self.record = copy.deepcopy(self.expected)
        self.save()
        (self.directory/'unlisted').write_bytes(b'extra')
        with self.assertRaisesRegex(RuntimeError, 'directory entries'):
            self.validate()

    def test_metadata_pass_cannot_override_recomputed_proof_failure(self):
        for name in audit.REQUIRED_CHECKS:
            failed = copy.deepcopy(self.expected)
            failed.update(overall='BLOCKED', blockers=[name+': rejected'])
            failed['checks'][name] = False
            self.analyze.return_value = failed
            with self.subTest(proof=name), self.assertRaisesRegex(RuntimeError, 'recomputed audit blocked'):
                self.validate()

    def test_tampered_report_proofs_and_unknown_fields(self):
        for key, value in [('terminal_closure', {'complete': True, 'instructions': []}),
                           ('terminal_closure', {'complete': 1, 'instructions': ['MOCK']}),
                           ('untrusted_extra', True), ('diagnostic_only', False)]:
            self.record = copy.deepcopy(self.expected)
            self.record[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'proof disagreement'):
                self.validate()

    def test_duplicate_json_keys_refused(self):
        (self.directory/'report.json').write_text('{"overall":"PASS","overall":"PASS"}')
        with self.assertRaisesRegex(RuntimeError, 'duplicate report key'):
            self.validate()

    def test_report_and_artifact_late_mutation(self):
        def mutate(*args):
            (self.directory/'report.json').write_bytes(b'{}')
            return self.expected
        self.analyze.side_effect = mutate
        with self.assertRaisesRegex(RuntimeError, 'report changed'):
            self.validate()
        self.save()
        def mutate_artifact(*args):
            (self.directory/'current_disassembly.txt').write_bytes(b'changed')
            return self.expected
        self.analyze.side_effect = mutate_artifact
        with self.assertRaisesRegex(RuntimeError, 'artifact changed'):
            self.validate()

    def test_artifact_sink_recomputes_bytes_even_if_pin_is_updated(self):
        path = self.directory/'f5_payload_entry_01.elf'
        path.write_bytes(b'forged')
        with self.assertRaisesRegex(RuntimeError, 'recomputed artifact mismatch'):
            audit.Artifacts(self.directory)(path.name, b'actual linked view')

    def test_run_refuses_existing_directory_without_analysis(self):
        with self.assertRaises(FileExistsError):
            audit.run(self.elf, self.before, self.directory)
        self.analyze.assert_not_called()


class SharedAnalysisControls(unittest.TestCase):
    def test_every_mandatory_binary_procedure_runs_and_refusal_blocks(self):
        # Keep the real shared analyzer; mock only binary inputs/procedures.
        procedures = ('terminal_alias', 'compare_entries', 'stack_paths',
                      'installer_inventory', 'compare_fatal_functions',
                      'installer_failure_proof', 'payload_obligation')
        with tempfile.TemporaryDirectory() as td, contextlib.ExitStack() as stack:
            root = Path(td)
            elf, before, tool = [root/n for n in ('elf', 'before', 'objdump')]
            for p in (elf, before, tool): p.write_bytes(p.name.encode())
            class Image:
                def __init__(self, path):
                    self.path = Path(path).resolve()
                    self.raw = self.path.read_bytes()
                    names = [f'f5_exc_{v}' for v in range(32)] + [
                        'f5_exception_common', 'f5_bridge', 'f5_unsupported', 'f5_iret',
                        'f5_terminal', 'f5_entry_terminal', 'f5_fail_report', 'f5_report', 'f5_before_iret']
                    self.symbols = {n: {'address': i, 'size': 1} for i, n in enumerate(names)}
            stack.enter_context(mock.patch.object(audit, 'BEFORE_SHA256', audit.sha(before.read_bytes())))
            stack.enter_context(mock.patch.object(audit, 'Image', Image))
            stack.enter_context(mock.patch.object(audit, 'discover_objdump', return_value=tool))
            stack.enter_context(mock.patch.object(audit, 'disassemble', return_value=(b'raw', {}, ['MOCK'])))
            stack.enter_context(mock.patch.object(audit, 'body', return_value=[{'pc': 0}]))
            graph = stack.enter_context(mock.patch.object(audit, 'closure', return_value={'complete': True, 'iret_exits': [0]}))
            mocks = {n: stack.enter_context(mock.patch.object(audit, n, return_value={'complete': True})) for n in procedures}
            artifacts = mock.Mock(hashes={})
            result = audit.analyze(elf, before, root, artifacts)
            self.assertEqual(result['overall'], 'PASS', result['blockers'])
            self.assertEqual(set(result['checks']), audit.REQUIRED_CHECKS)
            for m in mocks.values(): self.assertTrue(m.called)
            for name, m in mocks.items():
                m.side_effect = RuntimeError('NEGATIVE '+name)
                with self.subTest(procedure=name):
                    result = audit.analyze(elf, before, root, artifacts)
                    self.assertEqual(result['overall'], 'BLOCKED')
                    self.assertTrue(any('NEGATIVE '+name in b for b in result['blockers']))
                m.side_effect = None
            graph.return_value = {'complete': False, 'iret_exits': []}
            mocks['stack_paths'].reset_mock()
            result = audit.analyze(elf, before, root, artifacts)
            self.assertEqual(result['overall'], 'BLOCKED')
            mocks['stack_paths'].assert_not_called()


class ProcessControls(unittest.TestCase):
    def test_actual_optimized_execution_refused(self):
        script=Path(audit.__file__).resolve()
        result=subprocess.run([sys.executable,'-O','-B',str(script),'--help'],capture_output=True,text=True,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('optimized evidence execution refused',result.stderr)


if __name__=='__main__':
    unittest.main(verbosity=2)
