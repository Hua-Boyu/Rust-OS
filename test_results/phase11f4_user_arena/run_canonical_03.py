"""Reviewed F4 launcher. Parent must launch background=True, notify=True; no polling.
Usage: run_canonical_03.py REVIEW REVIEW_SHA256 MANIFEST MANIFEST_SHA256
No acceptance may be launched before a new freeze and complete independent approval.
"""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter
from canonical_provenance_03 import (ROOT, OUT, need, sha, load, unoptimized,
                                     validate_admission, validate_acceptance)

def main(argv=None):
    unoptimized()
    args = list(sys.argv[1:] if argv is None else argv)
    need(len(args) == 4, 'usage: run_canonical_03.py REVIEW REVIEW_SHA256 MANIFEST MANIFEST_SHA256')
    sys.path.insert(0, str(ROOT/'scripts'))
    from phase6_verify import source_snapshot, predecessor_contract, F3_PREDECESSOR_GATES, F4_GATES
    import psutil
    expected = source_snapshot()
    provenance = validate_admission(*args, expected)
    predecessor_contract()
    gates = list(F3_PREDECESSOR_GATES) + list(F4_GATES)
    need(len(gates) == 72 and Counter(provenance['manifest'].get('gate_identities', [])) == Counter(gates), 'manifest exact72 gate contract')
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            args = p.info.get('cmdline') or []
            busy = any(str(a).endswith(('phase6_verify.py', 'test_acceptance_harness.py', 'mock_isolated_03.py', 'mock_isolated_04.py')) for a in args)
            busy = busy or any(x in (p.info.get('name') or '').lower() for x in ('cargo', 'rustc', 'qemu'))
            need(not busy, 'competing build/test process ' + str(p.info['pid']))
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied as exc:
            raise RuntimeError('cannot establish process quiescence') from exc
    # Rehash the complete admission set immediately before exclusive output creation/spawn.
    need(source_snapshot() == expected, 'prelaunch source drift')
    validate_admission(provenance['review_path'], provenance['review_sha256'], provenance['candidate_manifest_path'], provenance['candidate_manifest_sha256'], expected)
    need(not OUT.exists(), 'refuse canonical output reuse')
    OUT.mkdir(parents=True, exist_ok=False)
    log = OUT/'driver.log'; record = OUT/'driver_result.json'
    row = {k: provenance[k] for k in ('review_path', 'review_sha256', 'candidate_manifest_path', 'candidate_manifest_sha256')}
    row.update(schema='rosti.f4-canonical-driver.v3', status='RUNNING',
               command=[sys.executable, '-B', str(ROOT/'scripts/phase6_verify.py'), '--output-dir', str(OUT)],
               cwd=str(ROOT), output_path=str(OUT), interpreter=sys.executable,
               driver_path=str(Path(__file__).resolve()), driver_sha256=sha(__file__),
               source_before=expected, started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    def write_record(first=False):
        with record.open('x' if first else 'w', encoding='utf8', newline='\n') as stream:
            json.dump(row, stream, indent=2); stream.write('\n')
    write_record(True)
    started = time.monotonic()
    try:
        with log.open('xb') as stream:
            proc = subprocess.Popen(row['command'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            row['runner_pid'] = proc.pid
            try:
                write_record()
            finally:
                # Even a recorder write failure cannot abandon the owned child.
                row['exit_code'] = proc.wait()
                row['exit_observed_by'] = 'Popen.wait'
        row.update(status='COMPLETED', source_after=source_snapshot(), log_sha256=sha(log))
        paths = list(OUT.glob('acceptance_*/acceptance.json'))
        row['acceptance_paths'] = [str(p) for p in paths]
        row['source_stable'] = row['source_after'] == expected
        need(len(paths) == 1, 'missing/ambiguous invocation acceptance')
        a = load(paths[0])
        row.update(acceptance_path=str(paths[0]), acceptance_sha256=sha(paths[0]), overall=a.get('overall'),
                   gates_passed=a.get('gates_passed'), gates_total=a.get('gates_total'),
                   gate_multiset_exact=Counter(g.get('gate') for g in a.get('gates', [])) == Counter(gates))
        need(row['exit_code'] == 0 and row['source_stable'], 'runner nonzero/source drift')
        validate_acceptance(a, gates, expected)
    except Exception as exc:
        row.update(status='FAILED', error=repr(exc))
        raise
    finally:
        row.update(elapsed_seconds=time.monotonic()-started, ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        write_record()
        print(json.dumps({k: row.get(k) for k in ('status','exit_code','overall','gates_passed','gates_total','acceptance_path','error')}, indent=2), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
