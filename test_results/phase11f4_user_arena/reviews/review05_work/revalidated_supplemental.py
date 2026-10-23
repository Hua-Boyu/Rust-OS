import sys,pathlib,json,hashlib,re,ast,struct,importlib.util
from collections import Counter,deque
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS');B=R/'test_results/phase11f4_user_arena';W=B/'reviews/review05_work';sys.path.insert(0,str(R/'scripts'))
J=lambda p:json.loads(pathlib.Path(p).read_bytes()); H=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
from phase6_verify import source_snapshot
from f4_dwarf import extract
from b13_entry_inject import elf_symbols
from f3_evidence import registers
S=source_snapshot();out={}
# Existing reviewed raw-ELF literal checker, execute read-only prefix only.
p=B/'terminal_contract_02.py'; code=p.read_text().split("with (BASE/'terminal_contract_02.json')")[0]; ns={'__file__':str(p),'__name__':'review03_read_only'};exec(compile(code,str(p),'exec'),ns);v=ns['report'];assert v['overall']=='PASS';out['raw_elf_literals']={k:v[k] for k in ('elf_sha256','bytes','serial_protocol','closure')}
# Independently derive source STATE address from symbols and PIC destination.
elf=B/'correction_green_02/kernel.elf'; syms=elf_symbols(elf); lay=extract(elf);state=next(x for n,x in syms.items() if 'retained_owner5STATE' in n); owner=next(x for n,x in syms.items() if 'retained_owner5OWNER' in n);assert state['size']==1 and owner['size']==lay['OwnerMutex']['size'] and owner['size']+13<=4096 and syms['f3_context']['size']<=4096
G=J(W/'closure.json'); root=G['closure'][str(G['root'])];pic=next(x for x in G['edges'] if x['kind']=='pic_call_next');got=pic['target']+int(next(x for x in root['instructions'] if x['op']=='addl' and '%ebx' in x['args'])['args'].split(',')[0][1:],16);lea=next(x for x in root['instructions'] if x['op']=='leal' and '%ebx' in x['args']);off=int(lea['args'].split('(')[0],16);assert got+off==state['address']
out['target_resources']={'owner_mutex':owner,'state':state,'owner_plus_latch_manifest':owner['size']+13,'descriptors':syms['f3_context'],'atomic_pointer_matches_state':True,'layout_sha256':H(B/'production_audit_02/target_layout.json'),'fresh_green_layout':lay}
# Original RED and first failed correction remain real emitted REDs, not guest failures.
spec=importlib.util.spec_from_file_location('audit',B/'correction_cycle_01.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);out['historical_red']={}
for folder in ('correction_red_01','correction_green_01'):
 d=W/folder;d.mkdir(exist_ok=False);v=a.audit(B/folder/'kernel.elf',d);assert v['result']=='RED' and v['forbidden']==30 and v['unresolved']==7;out['historical_red'][folder]=v
 graph=J(d/'closure.json');adj={int(k):[] for k in graph['closure']}
 for edge in graph['edges']:adj[edge['from']].append(edge['to'])
 distance={graph['root']:0};todo=deque(distance)
 while todo:
  p=todo.popleft()
  for q in adj[p]:
   if q not in distance:distance[q]=distance[p]+1;todo.append(q)
 assert all(x['address'] in distance for x in graph['forbidden'])
 recovery=J(B/'correction_recovery_02.json')['red_analysis'][folder];assert len(recovery['issues'])==37
 for issue in recovery['issues']:
  path=issue['shortest_path'];assert path[0]==graph['closure'][str(graph['root'])]['name']
 out['historical_red'][folder]['recovery_issues']=len(recovery['issues'])
# Exact focused Rust identities and successful summary from real log.
f=J(B/'commands/f4_focused_02.json');text=pathlib.Path(f['log']).read_text();names=re.findall(r'#\[test\]\s*fn (\w+)\(', (R/'src/memory/f4_user_arena_tests.rs').read_text());passed=re.findall(r'^test (\S+) \.\.\. ok$',text,re.M);assert Counter(x.rsplit('::',1)[1] for x in passed)==Counter(names) and len(passed)==12 and f['exit_code']==0 and H(f['log'])==f['log_sha256'];out['focused']={'exact_passed':passed,'ignored':0,'exit':0}
# Preserve real historical test identities, not a self-generated baseline assertion.
E=J(W/'evidence_checks.json')
for family,hist in [('host',R/'test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/03_host_tests.log'),('b26',R/'test_results/phase11f3_gdt_tss/b26_full_list_05.log')]:
 txt=hist.read_text(errors='replace');old=re.findall(r'^test (\S+) \.\.\. (?:ok|ignored(?:,.*)?)$',txt,re.M) if family=='host' else re.findall(r'^([^\r\n]+): test$',txt,re.M);new=E['host'][family]['identities'];assert not(Counter(old)-Counter(new));assert len(new)-len(old)==(12 if family=='host' else 15);out['historical_'+family]={'raw_sha256':H(hist),'preserved':len(old),'added':len(new)-len(old),'removed':0}
# Reconstruct actual F2 frames and normalized state from binary and register packets.
fp=next((R/'test_results/f4p05/f2').glob('*/report.json'));f=J(fp);fields=('gs fs es ds edi esi ebp pushad_esp ebx edx ecx eax vector error eip cs eflags').split();verified=[]
for row in f['cases']:
 child=pathlib.Path(row['report']);v=J(child);d=child.parent;case=v['case'];before=registers((d/f'f2_fault_{case}_register_packet.txt').read_bytes());normal=registers((d/'f2_normalized_register_packet.txt').read_bytes());frame=dict(zip(fields,struct.unpack('<17I',(d/'mandatory_prefix.bin').read_bytes())));assert before==v['before'] and normal==v['normalized'] and frame==v['frame'];assert frame['vector']=={'ud':6,'de':0,'gp':13,'pf':14}[case] and frame['error']==v['expected_error'] and frame['eip']==before['eip'] and frame['cs']==8 and frame['eflags']==(before['eflags']|65536);assert all(frame[k]==before[k] for k in ('eax','ecx','edx','ebx','ebp','esi','edi','ds','es','fs','gs'));assert normal['esp']+68==before['esp'] and frame['pushad_esp']==normal['esp']+48 and not(normal['eflags']&0x600);assert 'HLT=1' in (d/'terminal_hardware.txt').read_text();verified.append([case,v['ram_mib']])
out['raw_f2_frames']={'identities':verified,'status':'PASS'}
# Audit every retained component log hash and exact step code.
C=J(R/'test_results/f4p05/report.json');assert all(q['exit_code']==0 and H(R/'test_results/f4p05'/q['log'])==q['log_sha256'] for q in C['steps']);assert H(R/'target/target/debug/kernel')==H(elf);out['component_log_and_production_binding']=True
# Record immutable predecessors (not adopting prior insufficient APPROVE).
out['authority']={str(p.relative_to(R)):H(p) for p in [B/'candidate_manifest_02.json',B/'reviews/design_review_02.json',B/'reviews/candidate_review_01.json',B/'reviews/candidate_review_02.json',R/'reviews/candidate_review_02.json',R/'test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json']}
out['remaining_artifact_mismatch']={'path':str(B/'run_canonical_02.py'),'expected':J(B/'candidate_manifest_02.json')['artifact_sha256']['test_results/phase11f4_user_arena/run_canonical_02.py'],'observed':H(B/'run_canonical_02.py')}
assert source_snapshot()==S
(W/'supplemental_checks.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ('target_resources','focused')},indent=2))
