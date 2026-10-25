"""F5 pre-edit baseline inventory only; not test execution or acceptance."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from phase6_verify import source_snapshot


def main():
    out = ROOT / 'test_results/f5p01/baseline_02'
    out.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'pre-edit listing only; no passed tests claimed',
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_before': source_snapshot(), 'records': [], 'overall': 'FAIL'}
    try:
        for name, manifest in [('host', 'tests_kernel/Cargo.toml'),
                               ('b26', 'tests_b26/Cargo.toml')]:
            command = ['cargo', '+nightly', 'test', '--manifest-path', str(ROOT / manifest),
                       '--lib', '--', '--list']
            started = time.monotonic()
            result = subprocess.run(command, cwd=Path('C:/Users/iamsv'),
                                    capture_output=True, timeout=600)
            (out / (name + '.stdout.txt')).write_bytes(result.stdout)
            (out / (name + '.stderr.txt')).write_bytes(result.stderr)
            text = result.stdout.decode('utf-8', errors='strict')
            names = re.findall(r'^([^\s]+): test\s*$', text, re.M)
            row = {'family': name, 'command': command, 'child_cwd': 'C:/Users/iamsv',
                   'exit_code': result.returncode, 'elapsed_seconds': time.monotonic() - started,
                   'identities': names, 'identity_count': len(names), 'tests_executed': False}
            report['records'].append(row)
            if result.returncode or not names or len(names) != len(set(names)):
                raise RuntimeError('invalid nonempty exact list: ' + name)
        predecessor = ROOT / 'test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p/acceptance.json'
        raw = predecessor.read_bytes()
        expected = '3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4'
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError('F4 predecessor hash mismatch')
        old = json.loads(raw)
        gates = [row['gate'] for row in old['gates']]
        if old['overall'] != 'PASS' or len(gates) != 72 or len(set(gates)) != 72:
            raise RuntimeError('invalid F4 gate inventory')
        report['predecessor'] = {'path': str(predecessor), 'sha256': expected, 'gates': gates}
        report['source_after'] = source_snapshot()
        if report['source_before'] != report['source_after']:
            raise RuntimeError('source membership or raw bytes changed during listing')
        report['overall'] = 'PASS'
    except Exception as exc:
        report['error'] = repr(exc)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'overall': report['overall'], 'output': str(out),
                      'lists': {r['family']: r['identity_count'] for r in report['records']},
                      'tests_executed': False, 'error': report.get('error')}), flush=True)
    return 0 if report['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
