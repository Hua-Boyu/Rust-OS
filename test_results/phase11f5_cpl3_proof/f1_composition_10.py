"""Real F1 producer-to-unchanged-reader composition and refusal controls."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import f1_evidence
from phase6_verify import source_snapshot


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def readback(path, snapshot, default_elf):
    report = json.loads(Path(path).read_bytes())
    need(report.get('stage_removed') is True and not os.path.lexists(report['owned_stage']),
         'F1 actual staging cleanup not established')
    need(report['default_elf_sha256'] == sha(default_elf), 'F1 default ELF identity')
    return f1_evidence.f1_evidence(path, snapshot)


def controls(path, snapshot, default_elf):
    original = json.loads(path.read_bytes())
    raw_read = Path.read_bytes
    rows = []
    def reject(name, transform, missing=None):
        changed = copy.deepcopy(original)
        transform(changed)
        def read(item):
            if item == path:
                return json.dumps(changed).encode()
            if missing is not None and item == missing:
                raise FileNotFoundError('injected missing child report')
            return raw_read(item)
        with patch.object(Path, 'read_bytes', read):
            try:
                readback(path, snapshot, default_elf)
            except Exception as error:
                rows.append({'name':name, 'rejected':True, 'error':repr(error)})
            else:
                raise RuntimeError('negative control accepted: '+name)
    reject('missing stage_removed', lambda r:r.pop('stage_removed'))
    reject('matrix FAIL falsely labeled passing cleanup', lambda r:r.update(overall='FAIL'))
    reject('cleanup claim while stage exists', lambda r:r.update(owned_stage=str(path.parent)))
    reject('missing required F1 identity', lambda r:r['scenarios'].pop())
    reject('incorrect source identity', lambda r:r.update(source_snapshot={}))
    reject('incorrect default ELF identity', lambda r:r.update(default_elf_sha256='0'*64))
    reject('missing child report', lambda r:None, path.parent/'0_128/report.json')
    return rows


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'overall':'FAIL','canonical_acceptance':False,'producer_exit':None}
    started = time.monotonic()
    before = source_snapshot()
    elf = ROOT/'target/target/debug/kernel'
    command = [sys.executable,'-B',str(ROOT/'scripts/boot_metadata_test.py'),
               '--f1','--boot','elf','--ram','128','512','--output-dir',str(output/'producer')]
    report.update(command=command,cwd=str(ROOT),source_snapshot=before,reader_sha256=sha(ROOT/'scripts/f1_evidence.py'))
    try:
        from f3_full_guest import run_owned
        with (output/'producer.log').open('xb') as log:
            report['producer_exit'] = run_owned(command,log,900,report)
        need(report['producer_exit'] == 0, 'real producer failed')
        path, = (output/'producer').glob('*/report.json')
        result = readback(path, before, elf)
        need(result['scenarios'] == 10, 'not ten F1 cases')
        report.update(aggregate=str(path),aggregate_sha256=sha(path),
                      real_reader={'scenarios':result['scenarios'],'snapshots':result['snapshots'],
                                   'pins':{str(p):d for p,d in result['pins'].items()}},
                      negative_controls=controls(path,before,elf))
        need(source_snapshot() == before, 'composition source drift')
        report['overall'] = 'PASS'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['elapsed_seconds'] = time.monotonic()-started
        with (output/'report.json').open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2)
    print(json.dumps({'overall':report['overall'],'error':report.get('error'),'output':str(output)},indent=2))
    return 0 if report['overall'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    raise SystemExit(run(parser.parse_args().output_dir))
