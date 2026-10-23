"""Fresh isolated 89-identity calibration under the unchanged 900-second bound."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import psutil
if sys.flags.optimize: raise RuntimeError('optimized execution refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
from f3_full_guest import run_owned
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
for p in psutil.process_iter(['pid','name','cmdline']):
    try:
        args=p.info.get('cmdline') or []
        busy=any(str(a).endswith(('phase6_verify.py','test_acceptance_harness.py','verify_components_03.py')) for a in args)
        busy=busy or any(x in (p.info.get('name') or '').lower() for x in ('cargo','rustc','qemu'))
        need(not busy,'competing work '+str(p.info['pid']))
    except (psutil.NoSuchProcess,psutil.AccessDenied): pass
OUT=BASE/'mock_isolated_04'
OUT.mkdir(exist_ok=False)
script=ROOT/'scripts/test_acceptance_harness.py'
tree=ast.parse(script.read_text())
expected=[c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_')]
need(len(expected)==89 and len(set(expected))==89,'mock identity count')
row={'overall':'FAIL','scope':'Fresh isolated mock calibration; NOT canonical acceptance','timeout_seconds':900,'source_before':source_snapshot(),'expected_identities':expected,'argv':[sys.executable,'-B',str(script),'-v'],'driver_sha256':sha(__file__),'interpreter':sys.executable}
(OUT/'driver.py').write_bytes(Path(__file__).read_bytes())
start=time.monotonic()
try:
    with (OUT/'mock.log').open('xb') as log: row['exit_code']=run_owned(row['argv'],log,900,row)
    text=(OUT/'mock.log').read_text(errors='replace')
    summaries=re.findall(r'^Ran (\d+) tests in ([\d.]+)s$',text,re.M)
    passed=re.findall(r'^test_\w+ \(__main__\.([\w.]+)\) \.\.\. ok$',text,re.M)
    need(row['exit_code']==0 and len(summaries)==1 and int(summaries[0][0])==89 and text.rstrip().endswith('OK'),'mock nonzero/fail/missing summary')
    need(Counter(passed)==Counter(expected),'exact 89 successful identities')
    row.update(overall='PASS',passed_identities=passed,test_count=len(passed),suite_seconds=float(summaries[0][1]))
except Exception as exc: row['error']=repr(exc)
finally:
    row.update(elapsed_seconds=time.monotonic()-start,source_after=source_snapshot(),log_sha256=sha(OUT/'mock.log'))
    row['source_stable']=row['source_before']==row['source_after']
    if not row['source_stable'] or row['elapsed_seconds']>=900: row.update(overall='FAIL',error='source drift or wall bound exceeded')
    with (OUT/'report.json').open('x',encoding='utf8',newline='\n') as f: json.dump(row,f,indent=2); f.write('\n')
    print(json.dumps({k:row.get(k) for k in ('overall','exit_code','test_count','suite_seconds','elapsed_seconds','error')}))
raise SystemExit(0 if row['overall']=='PASS' else 1)
