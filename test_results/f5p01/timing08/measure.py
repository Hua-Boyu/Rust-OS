"""Bounded R2 measurement only; does not change or accept the 900s contract."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from f3_full_guest import run_owned
import psutil

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualification', action='store_true')
    parser.add_argument('--qualification09', action='store_true')
    args = parser.parse_args()
    limit = 1049 if args.qualification09 else (1009 if args.qualification else 1500)
    label = 'qualification09' if args.qualification09 else ('qualification' if args.qualification else 'measurement')
    source = ROOT / 'scripts/test_acceptance_harness.py'
    expected_pin = 'f6274eac8eb8ef3075597ed3d946df5a41f19fed14b0e616efe6038404288d2f'
    if sys.flags.optimize or digest(source) != expected_pin:
        raise RuntimeError('measurement requires exact run07 mock bytes and asserts')
    tree = ast.parse(source.read_bytes())
    identities = [f'{c.name}.{n.name}' for c in tree.body if isinstance(c, ast.ClassDef)
                  for n in c.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
    if len(identities) != 95 or len(set(identities)) != 95:
        raise RuntimeError('baseline identity set differs')
    busy = [{'pid': p.pid, 'name': p.info['name']} for p in psutil.process_iter(['name'])
            if (p.info['name'] or '').lower() in ('cargo.exe','rustc.exe','link.exe','qemu-system-i386.exe','qemu-system-x86_64.exe')]
    if busy:
        raise RuntimeError(f'competing build/test process: {busy}')
    pins = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / 'scripts').glob('*.py')}
    record = {'kind': ('R2_QUALIFICATION_NOT_CANONICAL' if args.qualification or args.qualification09 else 'R2_PROVISIONAL_MEASUREMENT_NOT_CANONICAL'), 'ceiling_seconds': limit,
              'identities': identities, 'source_sha256': pins, 'actual_exit': None,
              'command': [sys.executable, '-B', str(source), '-v'], 'cwd': str(ROOT),
              'parent_pid': __import__('os').getpid(), 'overall': 'FAIL'}
    started = time.monotonic()
    try:
        with (OUT / (label + '.log')).open('xb') as log:
            record['actual_exit'] = run_owned(record['command'], log, limit, record)
        record['wall_seconds'] = time.monotonic() - started
        text = (OUT / (label + '.log')).read_text(errors='replace')
        rows = re.findall(r'^test_(\w+) \(([^\n]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$', text, re.M)
        actual = []
        for method, location, status in rows:
            # Python 3.11: __main__.Class.test_name; 3.12: __main__.Class.test_name
            location = location.removeprefix('__main__.')
            actual.append(location if location.endswith('.test_' + method) else location + '.test_' + method)
        summary = re.findall(r'Ran (\d+) tests? in ([0-9.]+)s', text)
        record.update(actual_identities=actual, summaries=summary,
                      identity_union_exact=Counter(actual) == Counter(identities),
                      all_rows_ok=all(r[2] == 'ok' for r in rows),
                      complete_ok=bool(re.search(r'^OK\s*$', text, re.M)),
                      log_sha256=digest(OUT / (label + '.log')))
        record['inputs_unchanged'] = all(digest(ROOT / p) == h for p, h in pins.items())
        record['remaining_owned_script_processes'] = [p.pid for p in psutil.process_iter(['cmdline'])
            if p.pid != __import__('os').getpid() and any(str(source).lower() in a.lower() for a in (p.info['cmdline'] or []))]
        if (record['actual_exit'] == 0 and record['identity_union_exact'] and record['all_rows_ok']
                and record['complete_ok'] and len(summary) == 1 and int(summary[0][0]) == 95
                and record['inputs_unchanged'] and not record['remaining_owned_script_processes']):
            record['overall'] = 'PASS'
    except Exception as exc:
        record['error'] = repr(exc)
        record['wall_seconds'] = time.monotonic() - started
    finally:
        with (OUT / (label + '.json')).open('x') as f:
            json.dump(record, f, indent=2)
    print(json.dumps({k: record.get(k) for k in ('overall','actual_exit','wall_seconds','identity_union_exact','error')}), flush=True)
    return 0 if record['overall'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
