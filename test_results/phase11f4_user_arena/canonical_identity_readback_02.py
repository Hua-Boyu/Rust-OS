"""Supplementary exact canonical Rust identity comparison against fresh libtest lists."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]; BASE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
parent=BASE/'parent_components_readback_05.json'; p=json.loads(parent.read_bytes())
need(p['overall']=='PASS','fresh list authority')
driver=ROOT/'test_results/f4acc/c02/driver_result.json'; d=json.loads(driver.read_bytes())
need(d['status']=='COMPLETED' and d['exit_code']==0,'actual canonical completion')
a_path=Path(d['acceptance_paths'][0]); a=json.loads(a_path.read_bytes())
need(a['overall']=='PASS' and sha(a_path)==d['acceptance_sha256'],'canonical identity')
rows=[]
for gate_name,expected in [('host tests',p['tests']['host']['identities']),('Phase 9.6 B26 host safety regressions',p['tests']['b26']['identities']),('Phase 11 F4 owned USER arena host contract',[n for n in p['tests']['host']['identities'] if 'f4_user_arena_tests::' in n])]:
    gates=[g for g in a['gates'] if g['gate']==gate_name]
    need(len(gates)==1,'gate multiplicity')
    g=gates[0]; need(g['exit_code']==0 and g['status']=='PASS','gate exit')
    log=ROOT/g['log']; text=log.read_text(errors='replace')
    passed=re.findall(r'^test (\S+) \.\.\. ok\s*$',text,re.M)
    ignored=re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',text,re.M)
    need(Counter(passed+ignored)==Counter(expected),'canonical identity mismatch '+gate_name)
    sums=re.findall(r'test result: ok\. ([1-9][0-9]*) passed; 0 failed; (\d+) ignored',text)
    need(len(sums)==1 and list(map(int,sums[0]))==[len(passed),len(ignored)],'canonical nonzero summary')
    rows.append({'gate':gate_name,'passed':passed,'ignored':ignored,'log':str(log),'log_sha256':sha(log)})
report={'overall':'PASS','acceptance_path':str(a_path),'acceptance_sha256':sha(a_path),'component_readback_sha256':sha(parent),'reader_sha256':sha(__file__),'identity_comparisons':rows}
with (BASE/'canonical_identity_readback_02.json').open('x',encoding='utf8',newline='\n') as f: json.dump(report,f,indent=2); f.write('\n')
print(json.dumps({'overall':'PASS','identities':[{k:(len(v) if k in ('passed','ignored') else v) for k,v in r.items() if k in ('gate','passed','ignored')} for r in rows]},indent=2))
