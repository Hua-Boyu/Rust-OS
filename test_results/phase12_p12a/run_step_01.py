"""Invocation-owned sequential subprocess recorder; no synthetic success."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / 'test_results/phase12_p12a'

def main():
    if sys.flags.optimize:
        raise RuntimeError('optimized execution refused')
    name, cwd, seconds, *cmd = sys.argv[1:]
    out = TASK / 'verification_03'
    out.mkdir(exist_ok=True)
    log = out / (name + '.log')
    record = out / (name + '.json')
    if record.exists() or log.exists():
        raise RuntimeError('existing invocation evidence refused')
    import psutil
    busy = [{'pid': p.pid, 'name': p.info['name'], 'command': p.info['cmdline']}
            for p in psutil.process_iter(['name', 'cmdline'])
            if (p.info['name'] or '').lower() in ('cargo.exe', 'rustc.exe', 'link.exe', 'qemu-system-i386.exe', 'qemu-system-x86_64.exe')]
    if busy:
        raise RuntimeError('foreign/unknown heavy process: ' + repr(busy))
    report = {'command': cmd, 'cwd': cwd, 'timeout_seconds': int(seconds),
              'environment': {k: v for k, v in os.environ.items() if k.startswith(('CARGO', 'RUST', 'PYTHONOPTIMIZE'))},
              'busy_before': busy, 'available_bytes': psutil.virtual_memory().available,
              'log': log.relative_to(ROOT).as_posix(), 'exit_code': None}
    start = time.monotonic()
    try:
        with log.open('xb') as f:
            result = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=int(seconds))
        report['exit_code'] = result.returncode
    except Exception as e:
        report['error'] = repr(e)
    finally:
        report['elapsed_seconds'] = time.monotonic() - start
        report['sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        record.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report['exit_code'] if report['exit_code'] is not None else 1

if __name__ == '__main__':
    raise SystemExit(main())
