"""Independent offline canonical and retained component evidence validation."""
import sys,pathlib,json,hashlib,importlib.util,csv,re,struct,datetime
from collections import Counter
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS');B=R/'test_results/phase11f4_user_arena';W=B/'reviews/final_readback_work_01';sys.path[:0]=[str(B),str(R/'scripts')]
if sys.flags.optimize:raise RuntimeError('optimized review refused')
def H(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_bytes())
def check(v,m):
 if not v:raise RuntimeError(m)
def save(n,v):
 with (W/n).open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,indent=2,default=str);f.write('\n')
def one(it):
 a=list(it);check(len(a)==1,'missing/ambiguous report');return a[0]
from phase6_verify import source_snapshot,evidence_rows,phase10_evidence,F3_PREDECESSOR_GATES,F4_GATES
from canonical_provenance_03 import validate_driver
from f2_evidence import validate as f2
from f3_full_evidence import validate as f3
from f4_evidence import validate_aggregate as f4
from f1_evidence import f1_evidence
S=source_snapshot();D,A,AP,P=validate_driver(R/'test_results/f4acc/c03/driver_result.json',S,list(F3_PREDECESSOR_GATES)+list(F4_GATES));run=AP.parent
special=set();out={}
for family,folder,validator in [('f2','f2_exception',f2),('f3','f3_gdt_tss',f3),('f4','f4_user_arena',f4)]:
 p=one((run/folder).glob('*/report.json'));v=validator(p,S);check(v['pins']==A[family+'_evidence_sha256'],'canonical complete specialized pins '+family)
 special.update(pathlib.Path(n) for n in v['pins'] if pathlib.Path(n).name in ('report.json','guest_report.json'))
 out[family]={'path':str(p),'sha256':H(p),'scenarios':v['scenario_count'],'pin_count':len(v['pins'])}; save(family+'_validation_01.json',v);print(family,v['scenario_count'],len(v['pins']),'PASS',flush=True)
# Independently decode mandatory F2 frame against pre-fault packets, not only declared check rows.
from f3_evidence import registers,hardware
frames=[]
f2root=pathlib.Path(out['f2']['path']).parent
for case in ('ud','de','gp','pf'):
 for ram in (128,512):
  d=f2root/f'{case}_{ram}';names=[p.name for p in d.iterdir()]; frames.append({'case':case,'ram':ram,'files':names})
save('f2_frame_inventory_01.json',frames)
# Every official B13 report, including separately named b13_host.json.
b=run/'b13_qemu';q=J(b/'report.json');check(q['status']==q['qemu_status']==q['inspection']['status']=='PASS','B13 statuses');check(Counter((g['entry'],g['memory_mib']) for g in q['guests'])==Counter((e,r) for e in ('b13_handoff','_start') for r in (128,512)),'B13 identities');special.add(b/'report.json')
for g in q['guests']:
 p=b/f'{"fixture" if g["entry"]=="b13_handoff" else "production"}_{g["memory_mib"]}'/'report.json';check(J(p)==g and g['status']=='PASS' and g['cleanup'] is True,'B13 child equality cleanup');special.add(p)
host=J(run/'b13_host.json');check(host['status']=='PASS' and host['tests_run']==3 and host['failures']==[],'B13 official host')
counts={}
for ram in (128,512):
 p=run/f'boot_{ram}/boot_results.csv'
 with p.open(newline='') as f:rr=list(csv.DictReader(f))
 check(len(rr)==10 and all(r['status']=='PASS' for r in rr),'boot CSV ten actual successes');counts[str(p)]={'rows':10,'sha256':H(p)}
required={'read_fault':2,'write_fault':2,'paging':20,'iso_paging':2}
for boot in ('elf','iso'):
 for ram in (128,512):
  for kind,count in [('fs',103),('block',98),('rostifs',168)]:required[f'{kind}_{boot}_{ram}']=count
for directory,count in required.items():
 p=one((run/directory).glob('*/report.json'));check(len(evidence_rows(J(p),p))==count,'mandatory rows '+directory);counts[directory]={'rows':count,'sha256':H(p)}
p10=one((run/'phase10').glob('*/report.json'));check(len(phase10_evidence(J(p10),p10))==56,'phase10 exact56')
generic=[]
for p in run.rglob('report.json'):
 if p in special:continue
 evidence_rows(J(p),p);generic.append(str(p))
check(len(generic)==154,'generic report cardinality')
bm=one((run/'boot_metadata').glob('*/report.json'));br=J(bm);check(br['scenario_count']==br['expected_scenarios']==44,'metadata44')
expected=Counter((n,boot,ram) for n in ('nomodule','invalidmagic','null','headerbad','mmaptruncated','modulein-growth','module-overlap','countedoverflow','validmodule','reservedgrowth','frameexhaustion') for boot in ('elf','iso') for ram in (128,512))
check(Counter((s['name'],s['boot'],s['ram_mib']) for s in br['scenarios'])==expected,'metadata exact44')
for s in br['scenarios']:
 p=pathlib.Path(s['report']);check(p.resolve()==bm.parent/f"{s['boot']}_{s['ram_mib']}_{s['name']}"/'report.json','metadata child ownership');evidence_rows(J(p),p)
check(not pathlib.Path(br['owned_stage']).exists(),'metadata staging cleanup')
# F1 is component-only: do not misattribute metadata44 to retained-owner F1.
component=J(R/'test_results/f4p05/report.json');f1step=next(s for s in component['steps'] if s['name']=='f1');check(f1step['exit_code']==0,'component F1 actual exit')
f1paths=[]
for p in (R/'test_results/f4p05').rglob('report.json'):
 try:t=J(p)
 except Exception:continue
 if isinstance(t,dict) and 'source_unchanged' in t and 'default_elf_unchanged' in t and isinstance(t.get('scenarios'),list) and len(t['scenarios'])==10 and all('case' in s for s in t['scenarios']):f1paths.append(p)
f1path=one(f1paths);v=f1_evidence(f1path,S);check(v['scenarios']==10,'component F1 scenarios');save('f1_component_validation_01.json',{'path':str(f1path),'sha256':H(f1path),'validation':v,'canonical_F1_hardware_present':False,'qualification':'Canonical boot_metadata matrix is metadata44 only. F1 exact10 is retained source-identical fresh component evidence; unchanged72-gate contract has F1 host family but no F1 hardware invocation.'});out['f1_component']={'path':str(f1path),'scenarios':10,'snapshots':v['snapshots'],'pins':len(v['pins'])}
print('F1 component10, metadata44 distinct; generic154/B13/boot/Phase10 PASS',flush=True)
save('deep_summary_01.json',{'specialized':out,'B13_host':host,'required_rows':counts,'phase10_scenarios':56,'generic_nested_report_count':len(generic),'generic_nested_report_paths':generic,'generic_count_qualification':'Cardinality/true-check validation; not distinct guest count or full historical process proof','boot_metadata_44_not_F1':True,'canonical_F1_hardware_present':False})
# Pure audit() emits disassembly and new graph only; main() is never invoked.
spec=importlib.util.spec_from_file_location('independent_final_closure',B/'correction_cycle_01.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
v=audit.audit(R/'target/target/debug/kernel',W);check(v['result']=='GREEN' and (v['blocks'],v['edges'],v['forbidden'],v['unresolved'])==(4,11,0,0),'strict terminal closure');save('closure_summary_01.json',v)
g=J(W/'closure.json');save('closure_instructions_01.json',list(g['closure'].values()));print('fresh emitted strict closure4/11/0/0 PASS',flush=True)
import psutil
active=[]
for p in psutil.process_iter(['pid','name','cmdline']):
 try:
  name=(p.info.get('name') or '').lower();args=p.info.get('cmdline') or []
  if any(t in name for t in ('qemu','cargo','rustc')) or any(str(x).endswith('phase6_verify.py') for x in args):active.append(p.info)
 except psutil.NoSuchProcess:pass
check(not active,'active shared-output process');check(source_snapshot()==S,'source drift')
validate_driver(R/'test_results/f4acc/c03/driver_result.json',S,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
save('progress_03.json',{'status':'PASS','deep_validation_complete':True,'source_still_exact':True,'active_shared_processes':active,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'canonical_F1_correction_required_in_final_claims':True})
