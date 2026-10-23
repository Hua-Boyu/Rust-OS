"""Explicit scoped source staging; never commit, normalize, or touch unrelated paths."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
sha=lambda data:hashlib.sha256(data).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
need(git('branch','--show-current').decode().strip()=='maintenance/phase10','branch')
need(not git('diff','--cached','--name-only','-z'),'preexisting index changes')
m=json.loads((BASE/'candidate_manifest_04.json').read_bytes())
need(source_snapshot()==m['source_sha256'],'source drift')
final=BASE/'reviews/final_canonical_readback_01.json'
need(sha(final.read_bytes())=='c5a423c9ac83d3e753609822cbb84dbd51170abbe292e81ac4ae495083db47f0','final review drift')
r=json.loads(final.read_bytes())
need(r['verdict']=='APPROVE' and r['blocker_count']==0 and r['final_canonical_readback_approved'] is True,'final approval')
protected=json.loads((BASE/'continuation03_protected_inputs.json').read_bytes())
for p,h in protected['protected_sha256'].items(): need(sha((ROOT/p).read_bytes())==h,'protected drift '+p)
inv=json.loads((BASE/'git_source_identity_01.json').read_bytes())
paths=sorted(row['path'] for row in inv['changed_or_untracked'] if row['classification']!='NEWLINE_ONLY')
need(len(paths)==14,'source scope')
subprocess.run(['git','-c','core.autocrlf=false','add','--',*paths],cwd=ROOT,check=True)
staged=sorted(p for p in git('diff','--cached','--name-only','-z').decode().split('\0') if p)
need(staged==paths,'exact staged scope')
pins={}
for p in paths:
    blob=git('show',':'+p)
    need(sha(blob)==m['source_sha256'][p]==sha((ROOT/p).read_bytes()),'staged raw mismatch '+p)
    need(not re.search(rb'-----BEGIN [^-]*PRIVATE KEY-----|(?:api[_-]?key|password|secret)\s*[:=]\s*[\x22\x27][A-Za-z0-9_+/=-]{16,}',blob,re.I),'possible secret in '+p)
    pins[p]=sha(blob)
checks={}
for label,args in [
    ('default',['diff','--cached','--check']),
    ('normal_paths',['diff','--cached','--check','--',*[p for p in paths if p!='scripts/phase6_verify.py']]),
    ('immutable_crlf_runner',['-c','core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol','diff','--cached','--check','--','scripts/phase6_verify.py'])]:
    result=subprocess.run(['git',*args],cwd=ROOT,capture_output=True)
    log=BASE/f'staged_source_whitespace_{label}_01.log'
    with log.open('xb') as f:f.write(result.stdout+result.stderr)
    checks[label]={'actual_exit':result.returncode,'log':str(log),'sha256':sha(log.read_bytes())}
need(checks['normal_paths']['actual_exit']==checks['immutable_crlf_runner']['actual_exit']==0,'staged whitespace defect')
need(source_snapshot()==m['source_sha256'],'staging changed frozen inputs')
row={'overall':'PASS','head_before':git('rev-parse','HEAD').decode().strip(),'staged_paths':paths,'staged_raw_sha256':pins,'protected_bytes_match':True,'source_pin_count':len(m['source_sha256']),'source_stable':True,'whitespace':checks,'qualification':'Default CRLF diagnostics retained; ordinary paths default-checked and exact reviewed CRLF runner separately checked with scoped cr-at-eol, no persistent config or normalization. No commit yet.'}
with (BASE/'source_staging_readback_01.json').open('x',encoding='utf8',newline='\n') as f:json.dump(row,f,indent=2);f.write('\n')
print(json.dumps({'overall':'PASS','staged_count':len(paths),'staged_paths':paths,'whitespace_actual_exits':{k:v['actual_exit'] for k,v in checks.items()},'source_stable':True},indent=2))
