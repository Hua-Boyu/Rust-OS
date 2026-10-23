"""Parent readback of new F4 component freeze, all nested artifacts and identities."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import psutil
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
from f2_evidence import validate as f2_validate
from f3_full_evidence import validate as f3_validate
from f4_evidence import validate_aggregate
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
root=ROOT/'test_results/f4p05'
report={'scope':'Parent exact source/artifact/test readback; NOT independent approval','overall':'FAIL','reader_sha256':sha(__file__)}
try:
    value=json.loads((root/'report.json').read_bytes())
    current=source_snapshot()
    need(value['overall']=='PASS' and not value['source_drift'],'component result')
    need(value['source_before']==value['source_after']==current,'source membership/hash drift')
    old=json.loads((ROOT/'test_results/f4p04/source_before.json').read_bytes())
    delta={p:[old.get(p),current.get(p)] for p in old.keys()|current.keys() if old.get(p)!=current.get(p)}
    need(set(delta)=={'src/memory/retained_owner.rs'},'unexpected rejected freeze delta')
    need([s['name'] for s in value['steps']]==['production_format','production_build','production_elf','host_b26','f1','f2','f3','f4'],'component step identities')
    need(all(s['exit_code']==0 for s in value['steps']),'component exit failure')
    for p,d in current.items(): need(sha(root/'source'/p)==d,'frozen copy drift '+p)
    pins={}
    for family,evidence in value['evidence'].items():
        need(bool(evidence['pins']),'empty '+family+' pins')
        for p,d in evidence['pins'].items():
            need(Path(p).is_absolute() and sha(p)==d,'artifact drift '+p)
            need(p not in pins or pins[p]==d,'contradictory pin')
            pins[p]=d
    for step in value['steps']: need(sha(root/step['log'])==step['log_sha256'],'component log drift')
    for family,validator in [('f2',f2_validate),('f3',f3_validate)]:
        paths=list((root/family).glob('*/report.json'))
        need(len(paths)==1,'ambiguous '+family+' aggregate')
        fresh=validator(paths[0],current)
        need(fresh['pins']==value['evidence'][family]['pins'],'revalidated '+family+' membership changed')
    f4=validate_aggregate(root/'f4/report.json',current)
    need(f4['pins']==value['evidence']['f4']['pins'],'F4 validated membership')
    hosts=json.loads((root/'host_b26/report.json').read_bytes())
    need(hosts['overall']=='PASS' and not hosts['source_drift'] and hosts['source_before']==hosts['source_after']==current,'host freeze')
    test_totals={}
    for family in ('host','b26'):
        rows=[r for r in hosts['records'] if r['family']==family]
        need(len(rows)==3,'host mode count')
        listed=next(r['listed'] for r in rows if r['mode']=='list')
        for row in rows:
            need(row['exit_code']==0 and row['cwd']=='C:\\Users\\iamsv','host child cwd/exit')
            need(sha(row['log'])==row['log_sha256'],'host raw log')
            text=Path(row['log']).read_text(errors='replace')
            actual_list=re.findall(r'^([^\r\n]+): test$',text,re.M)
            actual_pass=re.findall(r'^test (\S+) \.\.\. ok$',text,re.M)
            actual_ignore=re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',text,re.M)
            need(actual_list==row['listed'] and actual_pass==row['passed'] and actual_ignore==row['ignored'],'host parsed identities')
            if row['mode']!='list':
                need(Counter(actual_pass+actual_ignore)==Counter(listed),'host exact membership')
                summary=re.findall(r'test result: ok\. ([1-9][0-9]*) passed; 0 failed; (\d+) ignored',text)
                need(len(summary)==1 and list(map(int,summary[0]))==[len(actual_pass),len(actual_ignore)],'host nonzero summary')
        serial=next(r for r in rows if r['mode']=='serial')
        test_totals[family]={'listed':len(listed),'passed':len(serial['passed']),'ignored':len(serial['ignored']),'identities':listed}
    need(sha(ROOT/'target/target/debug/kernel')==value['production_kernel_sha256'],'production ELF drift')
    graph=json.loads((BASE/'correction_green_02/closure.json').read_bytes())
    need(value['production_kernel_sha256']==graph['elf_sha256'] and graph['result']=='GREEN' and not graph['forbidden'] and not graph['unresolved'],'exact GREEN ELF')
    # Explicitly corroborate the two invocation-owned ready guest outputs.
    serial_paths=[p for p in (root/'f4').rglob('serial.txt') if p.parent.name in ('ready_128','ready_512')]
    if not serial_paths:
        # Derive from recorded guest identities rather than inventing directories.
        serial_paths=[]
        for p in (root/'f4').rglob('report.json'):
            child=json.loads(p.read_bytes())
            if child.get('scenario')=='ready' and (p.parent/'serial.txt').exists(): serial_paths.append(p.parent/'serial.txt')
    need(len(serial_paths)==2,'ready serial evidence count')
    for p in serial_paths:
        data=p.read_bytes()
        need(data.count(b'F4 USER arena PASS Ring0 terminal\n')==1 and b'F4 USER arena FAIL' not in data,'terminal exact ready bytes')
    # Include every artifact under this uniquely owned component tree, not only report.json.
    for p in root.rglob('*'):
        if p.is_file(): pins[str(p)]=sha(p)
    pins[str(ROOT/'target/target/debug/kernel')]=sha(ROOT/'target/target/debug/kernel')
    active=[]
    for p in psutil.process_iter(['pid','name']):
        if 'qemu' in (p.info.get('name') or '').lower(): active.append(p.info)
    need(not active,'active QEMU at parent readback')
    need(source_snapshot()==current,'source changed during readback')
    counts={k:v['scenario_count'] for k,v in value['evidence'].items()}
    need(counts=={'f1':10,'f2':8,'f3':18,'f4':12},'hardware counts')
    report.update(overall='PASS',source_sha256=current,source_pin_count=len(current),source_delta=delta,
        artifact_sha256=pins,artifact_pin_count=len(pins),scenario_counts=counts,tests=test_totals,
        production_kernel_sha256=value['production_kernel_sha256'],active_qemu=active,
        process_qualification='Global snapshot is separate from invocation-owned exit/cleanup assertions; not complete historical process provenance.',
        f1_limitation=value['evidence']['f1']['limitation'],serial_paths=list(map(str,serial_paths)))
except Exception as exc: report['error']=repr(exc)
with (BASE/'parent_components_readback_05.json').open('x',encoding='utf8',newline='\n') as f: json.dump(report,f,indent=2); f.write('\n')
print(json.dumps({k:report.get(k) for k in ('overall','source_pin_count','artifact_pin_count','scenario_counts','error')},indent=2))
raise SystemExit(0 if report['overall']=='PASS' else 1)
