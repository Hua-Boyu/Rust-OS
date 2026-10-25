"""Authenticate continuation inputs and restore only the accepted F2 Git bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
F2 = 'a43dd7a8bb0db3bce288237d89705b2be4ef95723fa28de78fb1e87708423c60'
PINS = {
    'design.md': '6b0b3a9324576b0fa148fa415fcaea23fe33a8e5f655da608e8ea56794a1791c',
    'design_inputs_03.json': 'adea88bcf78b78ebe182c79c82563d88707de3075435c24a675e1ab22f69d42f',
    'entry_design_amendment_01.md': '9071c193419cd08f225f663bfeadebf10cefcd5b344ce2f2fae1b30a563c69c2',
    'harness_contract_01.json': '91984e72662a74558e34e7a158a045984762ed7534fd68ad8be3f3fa005d3df7',
    'reviews/design_review_03.json': '3c73bf80b6c504e6f6c982a90d928f3e66ba8fac18f1174ce000c528289cfd83',
    'reviews/failure_policy_conformance_01.json': 'efc9c0c77c344bb50c8abc2fcda7826833808692178c2af179ef765a7e14bf97',
    'reviews/entry_design_amendment_review_01.json': '4ceb888d1bdbaa72c84b11fec654f9bce2aea0c6883ff9b32f371487941a3ec7',
}


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True)
    return {'argv': list(args), 'exit': p.returncode,
            'stdout': p.stdout.decode('utf-8', errors='replace'),
            'stderr': p.stderr.decode('utf-8', errors='replace')}


def main():
    need(not sys.flags.optimize, 'optimized execution refused')
    output = BASE / 'continuation06_recovery_01.json'
    need(not output.exists(), 'immutable recovery output already exists')
    record = {'schema': 'rosti.f5-continuation06-recovery.v1', 'overall': 'FAIL',
              'authority': 'User continuation06 authorizes exact F2 restoration and approved implementation; not acceptance approval.'}
    try:
        record['git'] = [git(*a) for a in [('status', '--porcelain=v1', '-uall'),
            ('branch', '--show-current'), ('rev-parse', 'HEAD'),
            ('merge-base', '--is-ancestor', 'c1b28b2', 'HEAD'), ('diff', '--check')]]
        need(record['git'][1]['stdout'].strip() == 'maintenance/phase10', 'unexpected branch')
        need(record['git'][3]['exit'] == 0, 'F4 ancestor missing')
        record['authority_pins'] = {n: {'expected': h, 'actual': sha((BASE/n).read_bytes())} for n, h in PINS.items()}
        need(all(v['expected'] == v['actual'] for v in record['authority_pins'].values()), 'authority hash mismatch')
        record['reviews'] = {}
        for name in ('design_review_03', 'failure_policy_conformance_01', 'entry_design_amendment_review_01'):
            review = json.loads((BASE/'reviews'/(name+'.json')).read_bytes())
            need(review['verdict'] == 'APPROVE' and review['blockers'] == [] and review['complete_scope'] is True, 'review not approved')
            record['reviews'][name] = {'verdict': review['verdict'], 'blockers': review['blockers'], 'complete_scope': review['complete_scope']}
        recovery = json.loads((BASE/'continuation04_source_before_01.json').read_bytes())['pins']
        drift = {n: {'expected': h, 'actual': sha((ROOT/n).read_bytes())} for n, h in recovery.items() if sha((ROOT/n).read_bytes()) != h}
        record['recovery_count'] = len(recovery)
        record['recovery_drift'] = drift
        need(not drift, 'unexpected recovery source drift; no restoration performed')
        status = record['git'][0]['stdout'].splitlines()
        protected = {'.gitignore', 'README.md', 'test_results/phase11f4_user_arena/FINAL_REPORT.md',
                     'd1/f', 'docs/ROSTI_INIT_ARCHITECTURE.md', 'reviews/candidate_review_02.json', 'scripts/b13_boot_fixture.py.backup'}
        record['classification'] = {line[3:]: ('PROTECTED_UNRELATED' if line[3:] in protected else 'F5_OWNED' if line[3:] in recovery else 'UNKNOWN') for line in status}
        record['protected_pins'] = {n: sha((ROOT/n).read_bytes()) for n in protected}
        target = ROOT/'src/exception_entry.s'
        need(not target.is_symlink() and target.resolve().parent == ROOT/'src', 'target ownership/path')
        before = target.read_bytes()
        record['f2_before'] = {'sha256': sha(before), 'size': len(before), 'crlf': before.count(b'\r\n'), 'lf': before.count(b'\n')}
        blob = subprocess.run(['git', 'cat-file', 'blob', 'HEAD:src/exception_entry.s'], cwd=ROOT, check=True, capture_output=True).stdout
        need(sha(blob) == F2, 'HEAD blob is not accepted F2')
        need(before.replace(b'\r\n', b'\n') == blob, 'F2 substantive drift requires investigation')
        need(target.read_bytes() == before, 'sibling write detected')
        backup = BASE/'continuation06_f2_before_01.s'
        with backup.open('xb') as stream:
            stream.write(before)
        target.write_bytes(blob)
        need(sha(target.read_bytes()) == F2, 'restoration readback failed')
        record['f2_after'] = {'sha256': sha(target.read_bytes()), 'authenticated_blob': 'HEAD:src/exception_entry.s', 'backup': backup.relative_to(ROOT).as_posix()}
        record['restoration_git'] = [git('status', '--short', '--', 'src/exception_entry.s'),
            git('diff', '--ignore-cr-at-eol', '--', 'src/exception_entry.s'), git('ls-files', '--eol', '--', 'src/exception_entry.s')]
        need(record['restoration_git'][1]['stdout'] == '', 'substantive diff after restore')
        record['overall'] = 'PASS'
    except Exception as exc:
        record['error'] = repr(exc)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps(record, indent=2))
    return 0 if record['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
