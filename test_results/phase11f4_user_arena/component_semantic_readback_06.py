"""Fresh offline semantic readback only; no builds or tests are executed."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot, predecessor_contract, F3_PREDECESSOR_GATES, F4_GATES
from f2_evidence import validate as f2_validate
from f3_full_evidence import validate as f3_validate
from f4_evidence import validate_aggregate as f4_validate

def need(ok, message):
    if not ok: raise RuntimeError(message)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
start=time.monotonic()
row={'scope':'Fresh parent offline semantic readback, NOT fresh test execution, independent approval, or canonical acceptance','overall':'FAIL'}
try:
    source=source_snapshot()
    manifest=json.loads((BASE/'candidate_manifest_04.json').read_bytes())
    need(source==manifest['source_sha256'],'source membership/hash drift')
    tree=ROOT/'test_results/f4p05'
    component=json.loads((tree/'report.json').read_bytes())
    parent=json.loads((BASE/'parent_components_readback_05.json').read_bytes())
    need(component['overall']==parent['overall']=='PASS','component status')
    need(component['source_before']==component['source_after']==parent['source_sha256']==source,'component freeze')
    scenario_counts={}
    validated_artifact_counts={}
    for family,validator in [('f2',f2_validate),('f3',f3_validate),('f4',f4_validate)]:
        reports=list((tree/family).glob('*/report.json')) if family!='f4' else [tree/'f4/report.json']
        need(len(reports)==1,'ambiguous aggregate '+family)
        actual=validator(reports[0],source)
        need(actual['pins']==component['evidence'][family]['pins'],'exact validated artifact membership '+family)
        scenario_counts[family]=actual['scenario_count']
        validated_artifact_counts[family]=len(actual['pins'])
    need(scenario_counts=={'f2':8,'f3':18,'f4':12},'hardware scenario identities/counts')
    host=json.loads((tree/'host_b26/report.json').read_bytes())
    need(host['overall']=='PASS' and host['source_before']==host['source_after']==source and not host['source_drift'],'host freeze')
    tests={}
    for family,count,ignored_count in [('host',380,2),('b26',149,0)]:
        records=[r for r in host['records'] if r['family']==family]
        need(Counter(r['mode'] for r in records)==Counter(['list','serial','parallel']),'mode identities')
        listed=next(r['listed'] for r in records if r['mode']=='list')
        need(len(listed)==len(set(listed))==count,'list membership')
        for r in records:
            need(r['exit_code']==0 and r['cwd']=='C:\\Users\\iamsv','child cwd/exit')
            need(sha(r['log'])==r['log_sha256'],'raw log digest')
            text=Path(r['log']).read_text(errors='replace')
            observed_list=re.findall(r'^([^\r\n]+): test$',text,re.M)
            passed=re.findall(r'^test (\S+) \.\.\. ok$',text,re.M)
            ignored=re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',text,re.M)
            need(observed_list==r['listed'] and passed==r['passed'] and ignored==r['ignored'],'raw identities')
            if r['mode']!='list':
                need(Counter(passed+ignored)==Counter(listed),'complete exact executed membership')
                need(len(passed)==count-ignored_count and len(ignored)==ignored_count,'executed counts')
                summaries=re.findall(r'test result: ok\. ([1-9][0-9]*) passed; 0 failed; (\d+) ignored',text)
                need(summaries==[(str(len(passed)),str(len(ignored)))],'nonzero execution summary')
        tests[family]={'listed':count,'passed':count-ignored_count,'ignored':ignored_count,'serial_parallel_membership_exact':True}
    ready=[]
    for path in (tree/'f4').rglob('report.json'):
        child=json.loads(path.read_bytes())
        if child.get('scenario')=='ready' and (path.parent/'serial.txt').is_file():
            serial=path.parent/'serial.txt'; data=serial.read_bytes()
            need(data.count(b'F4 USER arena PASS Ring0 terminal\n')==1 and b'F4 USER arena FAIL' not in data,'ready serial bytes')
            ready.append({'path':str(serial),'sha256':sha(serial)})
    need(len(ready)==2,'ready RAM evidence')
    pred=predecessor_contract()
    gates=list(F3_PREDECESSOR_GATES)+list(F4_GATES)
    need(len(gates)==72 and Counter(gates)==Counter(manifest['gate_identities']),'exact72 gate multiset')
    need(source_snapshot()==source,'late source drift')
    row.update(overall='PASS',source_count=len(source),manifest_sha256=sha(BASE/'candidate_manifest_04.json'),scenario_counts=scenario_counts,validated_artifact_counts=validated_artifact_counts,tests=tests,ready_serial=ready,F3_predecessor_sha256=sha(pred),gate_count=len(gates),gate_multiset_exact=True,component_report_sha256=sha(tree/'report.json'),reader_sha256=sha(__file__))
except Exception as exc:
    row['error']=repr(exc)
row['elapsed_seconds']=time.monotonic()-start
with (BASE/'component_semantic_readback_06.json').open('x',encoding='utf8',newline='\n') as f:
    json.dump(row,f,indent=2); f.write('\n')
print(json.dumps(row,indent=2))
raise SystemExit(0 if row['overall']=='PASS' else 1)
