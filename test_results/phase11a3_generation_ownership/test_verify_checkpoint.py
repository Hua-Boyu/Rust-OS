"""Development tests only: synthetic transient evidence, no Cargo/build/guest.
Run: python -B test_results/phase11a3_generation_ownership/test_verify_checkpoint.py
Does not invoke main against actual acceptance or inspect/poll its progress.
"""
import collections
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('offline_reader_under_test', HERE / 'verify_checkpoint.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def rust_log(names, ignored=0):
    return ('\n'.join('test ' + name + ' ... ok' for name in names) + '\n' +
            '\n'.join('test ignored_' + str(i) + ' ... ignored' for i in range(ignored)) +
            f'\ntest result: ok. {len(names)} passed; 0 failed; {ignored} ignored; 0 measured\n')


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='offline_reader_synthetic_')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def record(self, wrapper=None, data=None):
        row = dict(status='EXPECTED', exit_code=0, started_utc='2026-10-18T10:00:00+00:00',
                   ended_utc='2026-10-18T10:01:00+00:00')
        row.update(wrapper or {})
        report = dict(overall='PASS', gates_total=63)
        report.update(data or {})
        return row, report

    def test_completion_positive(self):
        v.completed(*self.record())

    def test_running_and_incomplete_not_failure_verdict(self):
        for change in ({'status': 'RUNNING'}, {'ended_utc': None}):
            row, data = self.record(change)
            if row.get('ended_utc') is None:
                del row['ended_utc']
            with self.assertRaises(v.NotReady):
                v.completed(row, data)
        with self.assertRaises(v.NotReady):
            v.completed(*self.record(data={'overall': 'RUNNING'}))

    def test_nonzero_bool_unexpected_and_bad_time_refused(self):
        for change in ({'exit_code': 1}, {'exit_code': False}, {'status': 'UNEXPECTED'},
                       {'ended_utc': '2026-10-18T09:00:00+00:00'},
                       {'ended_utc': '2026-10-18T10:01:00'}):
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                v.completed(*self.record(change))

    def test_test_rows_exact_and_ignored(self):
        v.test_log(rust_log(['one', 'two']), 2, exact=['one', 'two'])
        v.test_log(rust_log(['one'], 2), 1, 2)
        for text in ('', rust_log([]), rust_log(['one', 'one']), rust_log(['one', 'other']),
                     rust_log(['one', 'two'], 1), rust_log(['one', 'two']) * 2,
                     rust_log(['one', 'two']).replace('0 failed', '1 failed'),
                     rust_log(['one', 'two']).replace('2 passed', '3 passed')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                v.test_log(text, 2, exact=['one', 'two'])

    def test_evidence_changed_after_read(self):
        p = self.root / 'evidence.json'
        p.write_text('{}')
        ev = v.Evidence()
        self.assertEqual(ev.read(p), {})
        p.write_text('{"changed":true}')
        with self.assertRaises(ValueError):
            ev.stable()
        with self.assertRaises(ValueError):
            ev.read(p)

    def test_output_exclusive_and_exact_detached_hash(self):
        out = self.root / 'out.json'
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            digest = v.write_report(out, {'overall': 'NOT_READY'})
        self.assertEqual(digest, hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertEqual(json.loads(stdout.getvalue())['output_raw_sha256'], digest)
        before = out.read_bytes()
        with self.assertRaises(FileExistsError):
            v.write_report(out, {'overall': 'FAIL'})
        self.assertEqual(out.read_bytes(), before)

    def test_binding_exact_command_cwd_log_and_path(self):
        acceptance = self.root / 'acceptance.json'
        wrapper_path = self.root / 'wrapper.json'
        log = wrapper_path.with_suffix('.log')
        row, data = self.record()
        row.update(name='generation_full_acceptance', command=v.CANONICAL[:], cwd=str(v.PROJECT), log=str(log))
        data.update(phase='11A-prerequisite', phase11_release_ready=False)
        log.write_text(f'PASS: 63/63 gates; {acceptance}\n')
        with patch.object(v, 'ACCEPTANCE', acceptance), patch.object(v, 'WRAPPER', wrapper_path):
            v.binding(row, data, acceptance, v.Evidence())
            for field, value in [('command', row['command'] + ['extra']), ('cwd', str(self.root)),
                                 ('log', str(self.root / 'other.log')), ('name', 'another')]:
                bad = {**row, field: value}
                with self.subTest(field=field), self.assertRaises(ValueError):
                    v.binding(bad, data, acceptance, v.Evidence())
            log.write_text(f'PASS: 63/63 gates; {self.root / "different.json"}\n')
            with self.assertRaises(ValueError):
                v.binding(row, data, acceptance, v.Evidence())

    def gate_fixture(self):
        run = self.root / 'acceptance'
        run.mkdir()
        names = ['kernel formatting', 'host formatting', 'RostiFS formatting', 'host tests']
        names += ['inherited synthetic gate ' + str(i) for i in range(56)]
        baseline = dict(overall='PASS', gates_total=60, gates_passed=60, gates=[{'gate': n} for n in names])
        names += ['Phase 11A ' + f[0] + ' prerequisite' for f in v.FAMILIES]
        gates = []
        sources = {}
        for index, name in enumerate(names, 1):
            p = run / (f'{index:02d}_' + v.re.sub(r'[^a-z0-9]+', '_', name.lower()) + '.log')
            command, text = ['synthetic'], 'synthetic successful nonempty log\n'
            manifests = {'host formatting': 'tests_kernel/Cargo.toml', 'RostiFS formatting': 'crates/rostifs/Cargo.toml'}
            if name == 'kernel formatting':
                command, text = ['cargo', 'fmt', '--check'], ''
            elif name in manifests:
                command, text = ['cargo', '+nightly', 'fmt', '--manifest-path', str(v.PROJECT / manifests[name]), '--check'], ''
            elif name == 'host tests':
                command = ['cargo', '+nightly', 'test', '--manifest-path', str(v.PROJECT / 'tests_kernel/Cargo.toml')]
                text = rust_log(list(v.MANDATORY) + ['other_' + str(i) for i in range(305)], 2)
            for key, module, area, source, tests in v.FAMILIES:
                sources[v.PROJECT / source] = '\n'.join('#[test]\nfn ' + n + '() {}' for n in tests)
                if name == 'Phase 11A ' + key + ' prerequisite':
                    command = ['cargo', '+nightly', 'test', '--manifest-path', str(v.PROJECT / 'tests_kernel/Cargo.toml'),
                               '--lib', module + '::', '--', '--test-threads=1']
                    text = rust_log(['memory::' + area + '::' + module + '::' + n for n in tests])
            p.write_text(text)
            gates.append(dict(gate=name, command=command, exit_code=0, status='PASS', log=str(p)))
        data = dict(gates=gates, gates_total=63, gates_passed=63,
                    counts={'host': {'pass': 325, 'fail': 0}, **{f[0]: {'pass': len(f[4]), 'fail': 0} for f in v.FAMILIES}})
        class SyntheticEvidence(v.Evidence):
            def text(self, path):
                return sources[path] if path in sources else super().text(path)
        return data, baseline, run, SyntheticEvidence

    def test_gate_multiset_positive_empty_fmt_and_mutations(self):
        data, baseline, run, evidence = self.gate_fixture()
        # Legacy gate validators are separately reused, not reimplemented in this fixture.
        with patch.object(v.legacy, 'validate_lifetime_gate'), patch.object(v.legacy, 'validate_b26_gate'):
            v.validate_gates(data, baseline, run, evidence())
            for mutate in ('duplicate', 'exit', 'bool_exit', 'zero_family', 'fmt_command', 'source_substitute'):
                bad = copy.deepcopy(data)
                if mutate == 'duplicate':
                    bad['gates'][-1]['gate'] = bad['gates'][-2]['gate']
                elif mutate == 'exit':
                    bad['gates'][4]['exit_code'] = 1
                elif mutate == 'bool_exit':
                    bad['gates'][4]['exit_code'] = False
                elif mutate == 'zero_family':
                    bad['counts'][v.FAMILIES[0][0]]['pass'] = 0
                elif mutate == 'fmt_command':
                    bad['gates'][0]['command'] = ['cargo', 'fmt']
                else:
                    p = Path(bad['gates'][-1]['log'])
                    p.write_text(rust_log(['substitute'] * 6))
                with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                    v.validate_gates(bad, baseline, run, evidence())

    def test_review_raw_hashes_and_freeze_are_not_repinned(self):
        raw = self.root / 'src'
        raw.mkdir()
        paths = ['src/f' + str(i) + '.rs' for i in range(11)]
        for relative in paths:
            (self.root / relative).write_text(relative)
        hashes = {p: v.sha(self.root / p) for p in paths}
        report = dict(verdict='BOUNDED_APPROVAL', blockers=[], security_sensitive_blockers=[],
                      reviewed_raw_sha256=hashes, supplemental_context_raw_sha256={})
        rp, pp = self.root / 'independent_source_review.json', self.root / 'pre_acceptance.json'
        rp.write_text(json.dumps(report))
        pre = dict(review_sha256=v.sha(rp), review_hashes_match=True, source_snapshot=hashes)
        pp.write_text(json.dumps(pre))
        with patch.object(v, 'ROOT', self.root), patch.object(v, 'PROJECT', self.root), \
                patch.object(v, 'REVIEW_SHA', v.sha(rp)), patch.object(v, 'PRE_SHA', v.sha(pp)):
            v.reviews(hashes, v.Evidence())
            with self.assertRaises(ValueError):
                v.reviews({**hashes, 'extra': 'a' * 64}, v.Evidence())
            (self.root / paths[0]).write_text('drift')
            with self.assertRaises(ValueError):
                v.reviews(hashes, v.Evidence())

    def test_legacy_b13_unusual_schema_exact_children(self):
        children = {f'{kind}_{ram}': dict(entry=entry, memory_mib=ram, status='PASS', cleanup=True)
                    for kind, entry in [('fixture', 'b13_handoff'), ('production', '_start')] for ram in (128, 512)}
        aggregate = dict(status='PASS', qemu_status='PASS', inspection={'status': 'PASS'}, guests=list(children.values()))
        v.legacy.validate_b13(aggregate, children)
        for bad in ({k: val for k, val in children.items() if k != 'fixture_128'},
                    {**children, 'unexpected': {}}):
            with self.assertRaises(ValueError):
                v.legacy.validate_b13(aggregate, bad)
        bad = copy.deepcopy(aggregate)
        bad['guests'][0]['cleanup'] = False
        with self.assertRaises(ValueError):
            v.legacy.validate_b13(bad, children)

    def test_complete_nested_synthetic_matrices_and_fail_closed_mutations(self):
        import shutil
        runner = v.load('synthetic_schema_only', v.PROJECT / 'scripts/phase6_verify.py')
        run = self.root / 'run'
        old = self.root / 'old'
        reports = {}
        def rows(count):
            return dict(overall='PASS', checks=[{'pass': True} for _ in range(count)],
                        check_count=count, pass_count=count)
        def put(relative, data):
            p = run / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data))
            reports[p] = data
            return p
        children = {f'{kind}_{ram}': dict(entry=entry, memory_mib=ram, status='PASS', cleanup=True)
                    for kind, entry in [('fixture', 'b13_handoff'), ('production', '_start')] for ram in (128, 512)}
        put('b13_qemu/report.json', dict(status='PASS', qemu_status='PASS', inspection={'status': 'PASS'},
                                      guests=list(children.values())))
        for name, data in children.items():
            put('b13_qemu/' + name + '/report.json', data)
        for area in ('read_fault', 'write_fault', 'paging', 'iso_paging'):
            results = []
            for ram in (128, 512):
                for i in range(1, (10 if area == 'paging' else 1) + 1):
                    serial = run / area / 'invocation' / f'ram_{ram}_run_{i}' / 'serial.txt'
                    serial.parent.mkdir(parents=True, exist_ok=True)
                    serial.write_text('SYNTHETIC ONLY')
                    results.append(dict(pass_=True, ram_mib=ram, iteration=i,
                                        checks={'synthetic_check': True}, serial=str(serial)))
                    results[-1]['pass'] = results[-1].pop('pass_')
            put(area + '/invocation/report.json', dict(overall='PASS', results=results,
                                                     fault_build=area in ('read_fault', 'write_fault')))
        for boot in ('elf', 'iso'):
            for ram in (128, 512):
                for kind, count in [('fs', 103), ('block', 98), ('rostifs', 168)]:
                    put(f'{kind}_{boot}_{ram}/invocation/report.json', rows(count))
        scenarios = []
        for boot in ('elf', 'iso'):
            for ram in (128, 512):
                for case in runner.PHASE10_CASES:
                    child = rows(1)
                    child['cleanup'] = True
                    p = put(f'phase10/invocation/{boot}_{ram}_{case}/report.json', child)
                    scenarios.append(dict(boot=boot, ram_mib=ram, case=case, overall='PASS', cleanup=True, report=str(p)))
        matrix = rows(3379)
        matrix.update(scenarios=scenarios, expected_scenarios=56, scenario_count=56)
        put('phase10/invocation/report.json', matrix)
        scenarios = []
        for boot in ('elf', 'iso'):
            for ram in (128, 512):
                for name in ('nomodule', 'invalidmagic', 'null', 'headerbad', 'mmaptruncated', 'modulein-growth',
                             'module-overlap', 'countedoverflow', 'validmodule', 'reservedgrowth', 'frameexhaustion'):
                    p = put(f'boot_metadata/invocation/{boot}_{ram}_{name}/report.json', rows(1))
                    scenarios.append(dict(boot=boot, ram_mib=ram, name=name, overall='PASS', report=str(p)))
        metadata = rows(1)
        metadata.update(scenarios=scenarios, expected_scenarios=44, scenario_count=44)
        metadata_path = put('boot_metadata/invocation/report.json', metadata)
        for i in range(36):
            data = rows(1)
            if i == 0:
                # 8 B13 + 112 Phase10 + 160 duplicate synthetic assertions = 280;
                # these are deliberately not a count of distinct guest processes.
                data['synthetic_duplicate_cleanup_rows'] = [{'cleanup': True} for _ in range(160)]
            put(f'synthetic_extra/invocation/stage_{i}/report.json', data)
        self.assertEqual(len(reports), 159)
        host = run / 'b13_host.json'
        host.write_text(json.dumps(dict(status='PASS', tests_run=3, failures=[])))
        for ram in (128, 512):
            p = run / f'boot_{ram}/boot_results.csv'
            p.parent.mkdir()
            p.write_text('status\n' + 'PASS\n' * 10)
        counts = {'b13_host': {'pass': 3, 'fail': 0}, 'b13_qemu': {'pass': 4, 'fail': 0}}
        for p, report in reports.items():
            if p.parts[len(run.parts)] == 'b13_qemu':
                continue
            fields = {'pass': len(report.get('checks', report.get('results'))), 'fail': 0}
            if 'checks' in report:
                fields['commands'] = None
            counts[str(p.relative_to(run))] = fields
        data = {'counts': counts}
        shutil.copytree(run, old)
        with patch.object(v, 'BASELINE', old / 'acceptance.json'):
            result = v.nested(data, {}, run, runner, v.Evidence())
            self.assertEqual(result['nested_report_cardinality'], 159)
            self.assertEqual(result['cleanup_true_assertions'], 280)
            original = metadata_path.read_bytes()
            bad = copy.deepcopy(metadata)
            bad['scenarios'][0] = bad['scenarios'][1]
            metadata_path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                v.nested(data, {}, run, runner, v.Evidence())
            metadata_path.write_bytes(original)
            bad_data = copy.deepcopy(data)
            bad_data['counts']['b13_qemu']['pass'] = 3
            with self.assertRaises(ValueError):
                v.nested(bad_data, {}, run, runner, v.Evidence())
            host.write_text('{"status":"PASS","tests_run":3,"failures":["synthetic"]}')
            with self.assertRaises(ValueError):
                v.nested(data, {}, run, runner, v.Evidence())
            host.write_text(json.dumps(dict(status='PASS', tests_run=3, failures=[])))
            phase10 = run / 'phase10/invocation/report.json'
            bad = copy.deepcopy(matrix)
            bad['scenarios'][0] = bad['scenarios'][1]
            phase10.write_text(json.dumps(bad))
            with self.assertRaises(RuntimeError):
                v.nested(data, {}, run, runner, v.Evidence())
            phase10.write_text(json.dumps(matrix))
            p = run / 'synthetic_extra/invocation/stage_0/report.json'
            bad = copy.deepcopy(reports[p])
            bad['synthetic_duplicate_cleanup_rows'][0]['cleanup'] = False
            p.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                v.nested(data, {}, run, runner, v.Evidence())
            p.unlink()
            with self.assertRaises(ValueError):
                v.nested(data, {}, run, runner, v.Evidence())

    def test_real_iso_extractor_with_temporary_synthetic_media(self):
        import pycdlib
        helper = v.load('synthetic_iso_helper_only', v.PROJECT / 'test_results/phase11/verify_checkpoint.py')
        dist = self.root / 'dist'
        dist.mkdir()
        kernel, archive = b'SYNTHETIC NOT AN EXECUTABLE', b'SYNTHETIC ARCHIVE'
        def image(name, payload, contents=archive):
            p = dist / name
            iso = pycdlib.PyCdlib()
            iso.new(rock_ridge='1.09')
            iso.add_directory(iso_path='/BOOT', rr_name='boot')
            for leaf, rr, raw in [('ROSTI.BIN', 'rosti.bin', payload), ('SYSTEM.CPI', 'system.cpio', contents)]:
                iso.add_fp(io.BytesIO(raw), len(raw), iso_path='/BOOT/' + leaf + ';1', rr_name=rr)
            iso.write(str(p))
            iso.close()
            return dict(path='dist/' + name, sha256=v.sha(p), bytes=p.stat().st_size,
                        kernel_sha256=hashlib.sha256(payload).hexdigest())
        production = image('candidate.iso', kernel)
        old = image('old.iso', b'SYNTHETIC PREDECESSOR')
        rollback = image('rollback.iso', b'SYNTHETIC ROLLBACK')
        (dist / 'rosti.iso').write_bytes((dist / 'candidate.iso').read_bytes())
        fixture = dist / 'fixture_kernel'
        fixture.write_bytes(b'SYNTHETIC FEATURE FIXTURE')
        target = self.root / 'target/target/debug/kernel'
        target.parent.mkdir(parents=True)
        target.write_bytes(kernel)
        data = dict(iso=production, rollback_iso=rollback,
                    phase10_fixture_kernel=dict(path='dist/fixture_kernel', sha256=v.sha(fixture)))
        candidate = dict(kernel_sha256=production['kernel_sha256'])
        with patch.object(v, 'PROJECT', self.root), patch.object(v, 'load', return_value=helper):
            result = v.artifacts(data, {'iso': old}, candidate, v.Evidence())
            self.assertEqual(result['archive_sha256'], hashlib.sha256(archive).hexdigest())
            self.assertEqual(result['kernel_sha256'], production['kernel_sha256'])
            self.assertTrue(result['pycdlib_raw_sha256'])
            data['rollback_iso'] = image('rollback_other.iso', b'SYNTHETIC ROLLBACK', b'CHANGED ARCHIVE')
            with self.assertRaises(ValueError):
                v.artifacts(data, {'iso': old}, candidate, v.Evidence())
            data['rollback_iso'] = rollback
            target.write_bytes(b'CHANGED PRODUCTION')
            with self.assertRaises(ValueError):
                v.artifacts(data, {'iso': old}, candidate, v.Evidence())

    def test_cleanup_process_query_requires_completion(self):
        self.assertEqual(v.legacy.decode_qemu_result('{"query_completed":true,"processes":[]}'), [])
        for text in ('', '{}', '{"processes":[]}', '{"query_completed":true,"processes":[{"ProcessId":1}]}'):
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                v.legacy.decode_qemu_result(text)

    def test_optimized_execution_refused_before_import_or_write(self):
        proc = subprocess.run([sys.executable, '-B', '-O', str(HERE / 'verify_checkpoint.py')],
                              capture_output=True, text=True, timeout=20)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('optimized Python', proc.stderr)

    def test_main_running_wrapper_synthetic_not_ready_and_output_hash(self):
        wrapper = self.root / 'wrapper.json'
        wrapper.write_text('{"status":"RUNNING"}')
        out = self.root / 'readback.json'
        acceptance = self.root / 'not_read_acceptance.json'
        with patch.object(v, 'ROOT', self.root), patch.object(v, 'WRAPPER', wrapper), \
                patch.object(v, 'ACCEPTANCE', acceptance), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(v.main([str(acceptance), str(out)]), 2)
        report = json.loads(out.read_text())
        self.assertEqual(report['overall'], 'NOT_READY')
        self.assertFalse(report['b19_complete'])
        self.assertFalse(acceptance.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
