import sys,pathlib,json,hashlib,re,ast,struct
from collections import Counter
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS'); B=R/'test_results/phase11f4_user_arena'; W=B/'reviews/review05_work'; sys.path.insert(0,str(R/'scripts'))
J=lambda p:json.loads(pathlib.Path(p).read_bytes()); H=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
from phase6_verify import source_snapshot
from f2_evidence import validate as v2
from f3_full_evidence import validate as v3
from f4_evidence import validate_aggregate as v4
from f1_evidence import scenario_identities,schedule_for
S=source_snapshot(); C=J(R/'test_results/f4p05/report.json'); out={}
for fam,fun in [('f2',v2),('f3',v3),('f4',v4)]:
 p=R/'test_results/f4p05'/fam/'report.json' if fam=='f4' else next((R/'test_results/f4p05'/fam).glob('*/report.json'))
 fresh=fun(p,S); assert fresh['pins']==C['evidence'][fam]['pins']; out[fam]={'status':'PASS','report':str(p),'report_sha256':H(p),'validated_pins':len(fresh['pins']),'scenarios':fresh['scenario_count']}
 print(fam+' offline validation PASS',flush=True)
p=next((R/'test_results/f4p05/f1').glob('*/report.json')); f=J(p); scenario_identities(f['scenarios']); assert f['overall']=='PASS' and f['source_snapshot']==S and f['source_unchanged'] and f['default_elf_unchanged']; rows=[]
for row in f['scenarios']:
 child=pathlib.Path(row['report']); assert child.resolve()==(p.parent/f'{row["case"]}_{row["ram_mib"]}'/'report.json').resolve(); val=J(child); sched=schedule_for(row['case']); assert val['overall']=='PASS' and val['owned_qemu_exited'] and val['actual_qemu_exit']==1 and val['schedule']==sched and [c['checkpoint'] for c in val['checkpoints']]==sched
 for k,cp in enumerate(val['checkpoints']):
  q=child.parent/f'{k:02d}_{sched[k]}'/'snapshot.json'; assert pathlib.Path(cp['snapshot']).resolve()==q.resolve(); snap=J(q); assert snap['capture_complete'] and snap['failure_outcome'] is None and snap['query_status']['running'] is False and snap['hardware']==snap['hardware_after'] and 'CPL=0' in snap['registers'] and 'CPL=0' in snap['registers_after']
 rows.append({'case':row['case'],'ram_mib':row['ram_mib'],'checkpoints':len(sched),'exit':val['actual_qemu_exit']})
out['f1']={'status':'PASS_BOUNDED_PRESERVATION','rows':rows,'legacy_final_readback_gap_not_closed':True}
# Real libtest identities, not report counts.
h=J(R/'test_results/f4p05/host_b26/report.json'); assert h['overall']=='PASS' and h['source_before']==h['source_after']==S and not h['source_drift']; out['host']={}
def parsed(path):
 t=pathlib.Path(path).read_text(errors='replace'); return t,re.findall(r'^([^\r\n]+): test$',t,re.M),re.findall(r'^test (\S+) \.\.\. ok$',t,re.M),re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',t,re.M)
for fam,expected in [('host',(380,378,2)),('b26',(149,149,0))]:
 rows=[q for q in h['records'] if q['family']==fam]; assert Counter(q['mode'] for q in rows)==Counter(['serial','parallel','list']); listed=next(q['listed'] for q in rows if q['mode']=='list')
 for q in rows:
  t,l,p,i=parsed(q['log']); assert q['exit_code']==0 and H(q['log'])==q['log_sha256'] and (l,p,i)==(q['listed'],q['passed'],q['ignored'])
  if q['mode']!='list':
   assert Counter(p+i)==Counter(listed); assert re.findall(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored',t)==[(str(len(p)),str(len(i)))]; assert (len(listed),len(p),len(i))==expected
 baseline=J(B/('baseline_host_01/report.json' if fam=='host' else 'baseline_b26_01/report.json'))
 br=next(q for q in baseline['records'] if q['name']=='list'); _,bl,bp,bi=parsed(R/br['log']); assert Counter(bl)==Counter(br['listed']) and H(R/br['log'])==br.get('log_sha256',br.get('raw_sha256')) and br['exit_code']==0
 add=Counter(listed)-Counter(bl); removed=Counter(bl)-Counter(listed); assert not removed
 out['host'][fam]={'listed':len(listed),'serial_parallel_exact':True,'passed':expected[1],'ignored':expected[2],'baseline_listed':len(bl),'baseline_removed':dict(removed),'added':list(add.elements()),'identities':listed}
 # Ground exact new F4 family names in real declarations.
 for module in ['f4_user_arena_tests']+(['f4_b26_tests'] if fam=='b26' else []):
  names=re.findall(r'#\[test\]\s*fn (\w+)\(', (R/f'src/memory/{module}.rs').read_text()); actual=[x for x in listed if '::'+module+'::' in x]; assert Counter(x.rsplit('::',1)[1] for x in actual)==Counter(names)
# Focused exact twelve log, no zero filter.
fc=J(B/'commands/f4_focused_02.json'); out['focused_recorder_keys']=list(fc)
# Independently enumerate Python unittest AST and corroborate raw verbose successes.
m=J(B/'mock_isolated_04/report.json'); tree=ast.parse((R/'scripts/test_acceptance_harness.py').read_text()); declared=[c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef)) and f.name.startswith('test_')]
text=(B/'mock_isolated_04/mock.log').read_text(errors='replace'); successes=re.findall(r'^(test_\w+) \(__main__\.(\w+)\.\1\) \.\.\. ok$',text,re.M); got=[c+'.'+n for n,c in successes]
assert Counter(got)==Counter(declared)==Counter(m['passed_identities'])==Counter(m['expected_identities']); assert len(got)==89 and 'skipped' not in text.lower() and re.search(r'Ran 89 tests in 604\.056s\s+OK',text); assert m['source_before']==m['source_after']==S and m['exit_code']==0 and m['elapsed_seconds']<900 and m['timeout_seconds']==900
out['mock']={'status':'PASS','declared':len(declared),'actual_verbose_ok':len(got),'skips':0,'suite_seconds':m['suite_seconds'],'wall_seconds':m['elapsed_seconds'],'unchanged_timeout':900,'margin_seconds':900-m['elapsed_seconds'],'identities':got}
# Exact unchanged predecessor ABI/TSS and source delta.
pre=J(R/'test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json'); protected=['src/exception_abi.rs','src/exception_entry.s','src/exception_fatal.rs','src/gdt_tss.rs','src/f3_entry.s','src/memory/privileged.rs','src/io/serial.rs']; assert all(S[x]==pre['source_sha256'][x] for x in protected)
out['predecessor_preservation']={x:S[x] for x in protected}
(W/'evidence_checks.json').write_text(json.dumps(out,indent=2)); print(json.dumps({k:({x:v for x,v in val.items() if x not in ('identities','host')} if isinstance(val,dict) else val) for k,val in out.items() if k not in ('host','mock','predecessor_preservation')},indent=2)); print('host/B26/mocks and predecessor byte preservation PASS')
