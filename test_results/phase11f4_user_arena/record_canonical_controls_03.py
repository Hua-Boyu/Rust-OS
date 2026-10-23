"""Record final host-only v3 controls; never invoke acceptance/build/guest tools."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    sys.path.insert(0,str(BASE))
    from canonical_provenance_03 import OUT,unoptimized
    unoptimized()
    log=BASE/'canonical_controls_04.log'
    report=BASE/'canonical_controls_04.json'
    if log.exists() or report.exists():raise RuntimeError('exclusive numbered control outputs already exist')
    if OUT.exists():raise RuntimeError('production output already exists')
    started=time.monotonic()
    command=[sys.executable,'-B',str(BASE/'test_canonical_03.py')]
    with log.open('xb') as stream:
        result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    elapsed=time.monotonic()-started
    sys.path.insert(0,str(ROOT/'scripts'))
    from phase6_verify import source_snapshot
    snapshot=source_snapshot()
    manifest=json.loads((BASE/'candidate_manifest_03.json').read_bytes())
    historic_mismatches=[path for path,digest in manifest['artifact_sha256'].items() if sha(ROOT/path)!=digest]
    reviewed=BASE/'reviews/candidate_review_04.json'
    expected_review04='136183c5138ad366322692d3a9bf425b1ac05672cc62283d266f8e5ec8b83bc8'
    names=['canonical_provenance_03.py','run_canonical_03.py','canonical_readback_03.py',
           'canonical_identity_readback_03.py','test_canonical_03.py','canonical_usage_03.md',
           'record_canonical_controls_03.py','canonical_controls_03.log','canonical_controls_04.log']
    tree=ast.parse((BASE/'test_canonical_03.py').read_text())
    tests=[n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
    row={'scope':'HOST-ONLY MOCK provenance controls, NOT approval or acceptance evidence',
         'command':command,'cwd':str(ROOT),'actual_exit':result.returncode,'wall_seconds':elapsed,
         'test_count_source_ast':len(tests),'test_identities':tests,
         'production_output_created':OUT.exists(),'source_discovery_count':len(snapshot),
         'source_discovery_exact_manifest03':snapshot==manifest['source_sha256'],
         'historical_candidate03_artifact_count':len(manifest['artifact_sha256']),
         'historical_candidate03_artifact_mismatches':historic_mismatches,
         'review04_sha256':sha(reviewed),'review04_expected_sha256':expected_review04,
         'review04_preserved':sha(reviewed)==expected_review04,
         'artifact_sha256':{str(BASE/name):sha(BASE/name) for name in names},
         'not_executed':['acceptance','production builds','kernel tests','guest tests','QEMU','review approval','new freeze']}
    text=log.read_text()
    row['test_summary_ok']=f'Ran {len(tests)} tests in ' in text and '\nOK\n' in text and 'FAILED' not in text and 'skipped=' not in text
    row['overall']='PASS' if (result.returncode==0 and row['test_summary_ok'] and not row['production_output_created'] and row['source_discovery_exact_manifest03'] and not historic_mismatches and row['review04_preserved']) else 'FAIL'
    with report.open('x',encoding='utf8',newline='\n') as stream:json.dump(row,stream,indent=2);stream.write('\n')
    print(text)
    print(json.dumps({k:row[k] for k in ('overall','actual_exit','wall_seconds','test_count_source_ast','production_output_created','source_discovery_count','source_discovery_exact_manifest03','historical_candidate03_artifact_count','historical_candidate03_artifact_mismatches','review04_preserved')},indent=2))
    print('REPORT',str(report),'SHA256',sha(report))
    return 0 if row['overall']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
