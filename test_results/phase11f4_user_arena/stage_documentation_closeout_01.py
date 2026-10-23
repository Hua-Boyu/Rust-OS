"""Stage only scoped text evidence/docs after final approval; no commits or source writes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
if sys.flags.optimize:raise RuntimeError('optimized execution refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
sha=lambda data:hashlib.sha256(data).hexdigest()
def need(ok,msg):
    if not ok:raise RuntimeError(msg)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
need(not git('diff','--cached','--name-only','-z'),'preexisting index dirt')
m=json.loads((BASE/'candidate_manifest_04.json').read_bytes())
need(source_snapshot()==m['source_sha256'],'source drift')
e=json.loads((BASE/'evidence_manifest.json').read_bytes())
need(e['status']=='ACCEPTED','acceptance outcome')
final=BASE/'reviews/final_canonical_readback_01.json'
need(sha(final.read_bytes())=='c5a423c9ac83d3e753609822cbb84dbd51170abbe292e81ac4ae495083db47f0','final pin')
paths=set()
allowed=('test_results/phase11f4_user_arena/','test_results/f4p05/','test_results/f4acc/c03/')
for p,h in e['final_closeout_artifact_sha256'].items():
    target=Path(p)
    if not target.is_absolute():target=ROOT/target
    target=target.resolve()
    need(sha(target.read_bytes())==h,'cited artifact drift '+p)
    relative=target.relative_to(ROOT).as_posix()
    if relative.startswith(allowed) and target.suffix.lower() in ('.json','.md','.py'):paths.add(relative)
for p in ['HANDOVER.md','NEXT_SESSION_PROMPT.md','docs/PHASE11_HANDOVER.md','docs/PHASE11_MEMORY_AUTHORITY.md']:
    paths.add(p)
for p in ['FINAL_REPORT.md','STATE.md','evidence_manifest.json','source_staging_readback_01.json','source_commit_readback_01.json','stage_source_closeout_01.py','stage_documentation_closeout_01.py']:
    paths.add((BASE/p).relative_to(ROOT).as_posix())
protected=json.loads((BASE/'continuation03_protected_inputs.json').read_bytes())
for p,h in protected['protected_sha256'].items():need(sha((ROOT/p).read_bytes())==h,'protected drift '+p)
need(not any(p in paths for p in protected['protected_sha256']),'protected stage scope')
need(not any(p.startswith(('d1/','reviews/')) for p in paths),'unrelated scope')
paths=sorted(paths)
subprocess.run(['git','-c','core.autocrlf=false','add','-f','--',*paths],cwd=ROOT,check=True)
staged=sorted(p for p in git('diff','--cached','--name-only','-z').decode().split('\0') if p)
need(staged==paths,'exact doc staging membership')
pins={};crlf=[]
for p in staged:
    raw=(ROOT/p).read_bytes();blob=git('show',':'+p)
    need(blob==raw,'staging changed raw bytes '+p)
    need(not re.search(rb'-----BEGIN [^-]*PRIVATE KEY-----|(?:api[_-]?key|password|secret)\s*[:=]\s*[\x22\x27][A-Za-z0-9_+/=-]{16,}',blob,re.I),'possible secret in '+p)
    pins[p]=sha(blob)
    if b'\r\n' in blob:crlf.append(p)
checks={}
for name,args in [('default',['diff','--cached','--check']),('ordinary',['diff','--cached','--check','--',*[p for p in staged if p not in crlf]]),('preserved_crlf',['-c','core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol','diff','--cached','--check','--',*crlf])]:
    result=subprocess.run(['git',*args],cwd=ROOT,capture_output=True)
    log=BASE/f'documentation_whitespace_{name}_01.log'
    with log.open('xb') as f:f.write(result.stdout+result.stderr)
    checks[name]={'actual_exit':result.returncode,'log':str(log),'sha256':sha(log.read_bytes())}
    if result.returncode:print(name+' diagnostics:\n'+result.stdout.decode(errors='replace')[:2500])
need(checks['ordinary']['actual_exit']==checks['preserved_crlf']['actual_exit']==0,'documentation whitespace defect; preserve evidence, do not normalize')
need(source_snapshot()==m['source_sha256'],'source drift during docs staging')
row={'overall':'PASS','head_before':git('rev-parse','HEAD').decode().strip(),'staged_paths':staged,'staged_raw_sha256':pins,'preserved_crlf_paths':crlf,'whitespace':checks,'source_inputs_unchanged':True,'protected_bytes_match':True,'secret_scan_pass':True,'qualification':'Selected text only; no binaries, protected work or source. Exact raw staged hashes verified; no normalization or persistent config. No commit yet.'}
with (BASE/'documentation_staging_readback_01.json').open('x',encoding='utf8',newline='\n') as f:json.dump(row,f,indent=2);f.write('\n')
print(json.dumps({'overall':'PASS','staged_count':len(staged),'staged_total_bytes':sum((ROOT/p).stat().st_size for p in staged),'staged_paths':staged,'crlf_paths':crlf,'whitespace_actual_exits':{k:v['actual_exit'] for k,v in checks.items()}},indent=2))
