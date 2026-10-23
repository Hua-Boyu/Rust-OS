"""One canonical F4-corrected invocation; run only after parent validates candidate_review_02 APPROVE."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil
if sys.flags.optimize or os.environ.get('PYTHONOPTIMIZE'):
    raise RuntimeError('optimized execution refused')
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot, predecessor_contract, F3_PREDECESSOR_GATES, F4_GATES
from collections import Counter

def need(ok,msg):
    if not ok: raise RuntimeError(msg)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
need(len(sys.argv)==3,'usage: run_canonical_02.py complete-review-path expected-raw-review-sha256')
review=Path(sys.argv[1]).resolve()
need(sha(review)==sys.argv[2],'review identity mismatch')
r=json.loads(review.read_bytes())
# Parent independently validates complete verdict/schema before executing this driver.
need(r.get('verdict')=='APPROVE' and r.get('blockers')==[],'independent approval missing')
expected=json.loads((ROOT/'test_results/f4p05/source_before.json').read_bytes())
need(len(expected)>=150 and source_snapshot()==expected,'source freeze mismatch')
predecessor_contract()
need(len(F3_PREDECESSOR_GATES)+len(F4_GATES)==72,'contract count')
for p in psutil.process_iter(['pid','name','cmdline']):
    try:
        args=p.info.get('cmdline') or []
        busy=any(str(a).endswith(('phase6_verify.py','test_acceptance_harness.py','mock_isolated_03.py','mock_isolated_04.py')) for a in args)
        busy=busy or any(x in (p.info.get('name') or '').lower() for x in ('cargo','rustc','qemu'))
        need(not busy,'competing build/test process '+str(p.info['pid']))
    except (psutil.NoSuchProcess,psutil.AccessDenied): pass
out=ROOT/'test_results/f4acc/c02'
need(not out.exists(),'refuse reuse canonical root')
out.mkdir(parents=True,exist_ok=False)
log=out/'driver.log'; record=out/'driver_result.json'
row={'schema':'rosti.f4-canonical-driver.v2','status':'RUNNING','command':[sys.executable,'-B',str(ROOT/'scripts/phase6_verify.py'),'--output-dir',str(out)],'cwd':str(ROOT),'interpreter':sys.executable,'review_path':str(review),'review_sha256':sha(review),'driver_sha256':sha(__file__),'source_before':expected,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
record.write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
start=time.monotonic()
with log.open('xb') as stream:
    proc=subprocess.Popen(row['command'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    row['runner_pid']=proc.pid
    record.write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
    row['exit_code']=proc.wait()
row.update(elapsed_seconds=time.monotonic()-start,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_after=source_snapshot(),log_sha256=sha(log),status='COMPLETED')
paths=list(out.glob('acceptance_*/acceptance.json'))
row['acceptance_paths']=[str(p) for p in paths]
if len(paths)==1:
    a=json.loads(paths[0].read_bytes())
    row.update(acceptance_sha256=sha(paths[0]),overall=a.get('overall'),gates_passed=a.get('gates_passed'),gates_total=a.get('gates_total'),gate_multiset_exact=Counter(g.get('gate') for g in a.get('gates',[]))==Counter(F3_PREDECESSOR_GATES)+Counter(F4_GATES))
row['source_stable']=row['source_after']==expected
record.write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:row.get(k) for k in ('status','exit_code','elapsed_seconds','overall','gates_passed','gates_total','gate_multiset_exact','source_stable','acceptance_paths')},indent=2),flush=True)
need(row['exit_code']==0,'canonical runner nonzero; preserve all evidence')
need(row.get('overall')=='PASS' and row.get('gates_passed')==row.get('gates_total')==72 and row.get('gate_multiset_exact') and row['source_stable'],'incomplete canonical acceptance')
