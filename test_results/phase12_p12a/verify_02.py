"""Frozen P12-A verification, sequential jobs and exact real memberships."""
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / 'test_results/phase12_p12a'
OUT = TASK / 'verification_03'
sys.path.insert(0, str(TASK))
sys.path.insert(0, str(ROOT / 'scripts'))

def need(value, message):
    if not value:
        raise RuntimeError(message)

def load(path):
    return json.loads(Path(path).read_bytes())

def step(name, cwd, timeout, args):
    code = subprocess.call([sys.executable, '-B', str(TASK / 'run_step_01.py'), name, str(cwd), str(timeout), *map(str, args)], cwd=ROOT)
    row = load(OUT / (name + '.json'))
    need(code == 0 and row['exit_code'] == 0, 'failed actual command: ' + name)
    need(row['sha256'] == hashlib.sha256((ROOT / row['log']).read_bytes()).hexdigest(), 'log drift')
    return (ROOT / row['log']).read_text(errors='replace'), row

def main():
    need(not sys.flags.optimize, 'optimized verification refused')
    import integrity_02 as integrity
    freeze = TASK / 'source_freeze_03.json'
    integrity.verify_freeze(freeze)
    if sys.argv[1:] == ['mock']:
        decision = load(TASK / 'mock_gate_decision_01.json')
        need(decision['MOCK_GATE_DECISION'] == 'REQUIRED', 'mock trigger not established')
        tree = ast.parse((ROOT / 'scripts/test_acceptance_harness.py').read_text())
        expected = [f'{c.name}.{f.name}' for c in tree.body if isinstance(c, ast.ClassDef)
                    for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_')]
        need(len(expected) == len(set(expected)) == 95, 'reviewed mock membership changed')
        text, row = step('mock', ROOT, 1049, [sys.executable, '-B', 'scripts/test_acceptance_harness.py', '-v'])
        observed = re.findall(r'^(test_\S+) \(__main__\.(\w+)\.\1\) \.\.\. ok\s*$', text, re.M)
        names = [cls + '.' + method for method, cls in observed]
        need(Counter(names) == Counter(expected), 'mock exact membership mismatch')
        need(re.search(r'Ran 95 tests in [0-9.]+s\s+OK\s*$', text), 'mock summary/skips/failure')
        integrity.verify_freeze(freeze)
        result = {'overall': 'PASS', 'expected': expected, 'executed': names, 'failures': 0, 'skips': 0, 'actual_exit': row['exit_code'], 'elapsed_seconds': row['elapsed_seconds'], 'enforced_timeout_seconds': row['timeout_seconds'], 'source_before_equals_after': True}
        (OUT / 'mock_result.json').write_text(json.dumps(result, indent=2) + '\n')
        print('MOCK PASS exact', len(names))
        return
    report = {'overall': 'FAIL', 'source_freeze': freeze.relative_to(ROOT).as_posix(), 'steps': [], 'results': {}}
    try:
        spec = importlib.util.spec_from_file_location('host_oracle', ROOT / 'test_results/phase11f5_cpl3_proof/host_matrix_06_01.py')
        host = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(host)
        baseline = load(ROOT / 'test_results/p12a/b01/report.json')
        contract = (TASK / 'p12a_contract.md').read_text()
        policy_names = re.findall(r'^\d+\. (p12a_policy_tests::\w+)$', contract, re.M)
        need(len(policy_names) == len(set(policy_names)) and policy_names, 'contract identities missing')
        def run(name, args, cwd=Path('C:/Users/iamsv'), timeout=300):
            text, row = step(name, cwd, timeout, args)
            report['steps'].append(row)
            return text
        for key, manifest, names, ignored in [
            ('focused', 'tests_kernel', policy_names, ()),
            ('host', 'tests_kernel', baseline['host_identities'] + policy_names, host.IGNORED),
            ('b26', 'tests_b26', baseline['b26_identities'], ())]:
            cmd = ['cargo', '+nightly', 'test', '--manifest-path', str(ROOT / manifest / 'Cargo.toml'), '--lib']
            if key == 'focused':
                cmd.append('p12a_policy_tests::')
            for mode, tail in [('list', ['--', '--list']), ('serial', ['--', '--test-threads=1']), ('parallel', [])]:
                text = run(key + '_' + mode, cmd + tail)
                if mode == 'list':
                    listed = re.findall(r'^(\S+): test\s*$', text, re.M)
                    need(Counter(listed) == Counter(names), key + ' list membership')
                    result = {'listed': len(listed), 'identities': listed}
                else:
                    result = host.verify_result(text, names, ignored)
                report['results'][key + '_' + mode] = result
        run('fmt_kernel', ['cargo', '+nightly', 'fmt', '--check'], ROOT)
        run('fmt_host', ['cargo', '+nightly', 'fmt', '--manifest-path', str(ROOT / 'tests_kernel/Cargo.toml'), '--check'])
        run('fmt_policy', ['rustfmt', '+nightly', '--edition', '2021', '--check', str(ROOT / 'src/p12a_policy.rs')])
        run('api_no_std', ['rustc', '+nightly', '--edition=2021', '--crate-type', 'lib', str(TASK / 'api_probe_01.rs'), '-o', str(OUT / 'api_no_std.rlib')])
        run('toolchain', ['rustc', '+nightly', '-vV'], ROOT)
        run('clean_kernel', ['cargo', '+nightly', 'clean', '-p', 'kernel'], ROOT)
        run('production', ['cargo', '+nightly', 'build'], ROOT)
        elf = ROOT / 'target/target/debug/kernel'
        shutil.copyfile(elf, OUT / 'production.elf')
        digest = hashlib.sha256(elf.read_bytes()).hexdigest()
        for letter in ('A', 'B'):
            pin = baseline['PRODUCTION_ELF_BASELINE_' + letter]
            need(hashlib.sha256((ROOT / pin['path']).read_bytes()).hexdigest() == digest == pin['sha256'], 'production ELF differs')
        from f3_full_guest import discover_objdump
        tool = discover_objdump()
        symbols = run('production_symbols', [tool, '--syms', str(elf)], ROOT)
        need('p12a' not in symbols.lower(), 'runtime policy symbols')
        refs = []
        for directory in ['src', 'tests_kernel/src', 'scripts']:
            for path in sorted((ROOT / directory).rglob('*')):
                if path.is_file() and path.suffix in ('.rs', '.s', '.py', '.toml'):
                    for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
                        if 'p12a' in line.lower():
                            refs.append({'path': path.relative_to(ROOT).as_posix(), 'line': number, 'text': line})
        for path in ROOT.rglob('Cargo.toml'):
            if 'target' not in path.parts:
                need('p12a' not in path.read_text().lower(), 'manifest integration')
        need(refs and all(r['path'] in ('src/p12a_policy.rs', 'tests_kernel/src/lib.rs', 'tests_kernel/src/p12a_policy_tests.rs') for r in refs), 'unexpected runtime coupling')
        report.update(classification='Class T', production_elf_sha256=digest, production_references=refs, objdump=str(tool), preservation='SKIPPED fresh F1-F5 matrices10/8/18/12/12 at128/512MiB and emitted-closure rerun under approved identical-ELF Class T rule; not fresh hardware PASS', canonical_acceptance='NOT_APPLICABLE_NO_NEW_GATES')
        integrity.verify_freeze(freeze)
        report.update(overall='PASS', source_before_equals_after=True)
    except Exception as e:
        report['error'] = repr(e)
        raise
    finally:
        (OUT / 'verification_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('FROZEN VERIFICATION PASS')

if __name__ == '__main__':
    main()
