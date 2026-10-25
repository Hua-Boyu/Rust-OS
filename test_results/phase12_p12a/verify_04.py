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
    freeze = TASK / 'source_freeze_04.json'
    integrity.verify_freeze(freeze)
    # The real current-run mock already completed against byte-identical
    # canonical acceptance inputs. This closure-only repair does not rerun it.
    old = load(TASK / 'source_freeze_03.json')
    need(old['canonical_inputs'] == integrity.canonical_snapshot(), 'mock acceptance inputs changed')
    mock = load(OUT / 'mock_result.json')
    invocation = load(OUT / 'mock.json')
    need(mock['overall'] == 'PASS' and mock['actual_exit'] == invocation['exit_code'] == 0,
         'actual completed mock required')
    need(mock['enforced_timeout_seconds'] == 1049 and mock['elapsed_seconds'] < 1049,
         'actual bounded mock evidence required')
    need(invocation['sha256'] == hashlib.sha256((ROOT / invocation['log']).read_bytes()).hexdigest(),
         'mock log drift')
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
            text, row = step(name + '_04', cwd, timeout, args)
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
        report.update(overall='PASS', source_before_equals_after=True, mock_evidence='verification_03/mock_result.json', mock_canonical_inputs_unchanged=True, closure_disposition='freeze_extension_disposition_01.json')
    except Exception as e:
        report['error'] = repr(e)
        raise
    finally:
        (OUT / 'verification_report04.json').write_text(json.dumps(report, indent=2) + '\n')
    print('FROZEN VERIFICATION PASS')

if __name__ == '__main__':
    main()
