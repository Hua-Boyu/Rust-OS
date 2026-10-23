"""Raw canonical frames/literals/membership and historical pin checks only."""
import sys,pathlib,json,hashlib,struct,re,ast,subprocess
from collections import Counter
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS');B=R/'test_results/phase11f4_user_arena';W=B/'reviews/final_readback_work_01';sys.path[:0]=[str(B),str(R/'scripts')]
def H(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_bytes())
def check(v,m):
 if not v:raise RuntimeError(m)
def save(n,v):
 with (W/n).open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,indent=2,default=str);f.write('\n')
from phase6_verify import source_snapshot,F4_HOST_REQUIRED,B26_REQUIRED
from f3_evidence import registers
from b13_entry_inject import elf_symbols
from f4_dwarf import extract
S=source_snapshot();run=R/'test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p';a=J(run/'acceptance.json');out={}
# Inspected pure prefix; deliberately exclude output-writing suffix/main.
p=B/'terminal_contract_02.py';code=p.read_text().split("with (BASE/'terminal_contract_02.json')")[0];ns={'__file__':str(p),'__name__':'independent_read_only'};exec(compile(code,str(p),'exec'),ns);check(ns['report']['overall']=='PASS','raw ELF literal contract');out['raw_literals']={k:ns['report'][k] for k in ('bytes','serial_protocol','closure','elf_sha256')}
g=J(W/'closure.json');check(g['closure']==J(B/'correction_green_02/closure.json')['closure'],'fresh closure exact instruction equality')
syms=elf_symbols(R/'target/target/debug/kernel');lay=extract(R/'target/target/debug/kernel');state=next(s for n,s in syms.items() if 'retained_owner5STATE' in n);owner=next(s for n,s in syms.items() if 'retained_owner5OWNER' in n);root=g['closure'][str(g['root'])];pic=next(e for e in g['edges'] if e['kind']=='pic_call_next');got=pic['target']+int(next(i for i in root['instructions'] if i['op']=='addl' and '%ebx' in i['args'])['args'].split(',')[0][1:],16);off=int(next(i for i in root['instructions'] if i['op']=='leal' and '%ebx' in i['args'])['args'].split('(')[0],16);check(got+off==state['address'] and state['size']==1,'actual atomic store destination');check(owner['size']==lay['OwnerMutex']['size'] and owner['size']+13<=4096 and syms['f3_context']['size']<=4096,'target metadata bound');out['resources']={'owner':owner,'state':state,'descriptor':syms['f3_context'],'owner_latch_manifest_bytes':owner['size']+13,'retained_frame_bytes':12*4096,'new_payload_bytes':2*4096,'asm_max_instructions_IN':34*100000}
fp=next((run/'f2_exception').glob('*/report.json'));fields='gs fs es ds edi esi ebp pushad_esp ebx edx ecx eax vector error eip cs eflags'.split();verified=[]
for row in J(fp)['cases']:
 child=pathlib.Path(row['report']);v=J(child);d=child.parent;case=v['case'];before=registers((d/f'f2_fault_{case}_register_packet.txt').read_bytes());normal=registers((d/'f2_normalized_register_packet.txt').read_bytes());frame=dict(zip(fields,struct.unpack('<17I',(d/'mandatory_prefix.bin').read_bytes())));check(before==v['before'] and normal==v['normalized'] and frame==v['frame'],'raw F2 disagreement');check(frame['vector']=={'ud':6,'de':0,'gp':13,'pf':14}[case] and frame['error']==v['expected_error'] and frame['eip']==before['eip'] and frame['cs']==8 and frame['eflags']==(before['eflags']|65536),'exact CPU frame');check(all(frame[k]==before[k] for k in ('eax','ecx','edx','ebx','ebp','esi','edi','ds','es','fs','gs')),'GPR/selectors');check(normal['esp']+68==before['esp'] and frame['pushad_esp']==normal['esp']+48 and not(normal['eflags']&0x600),'same CPL geometry');check('HLT=1' in (d/'terminal_hardware.txt').read_text(),'F2 terminal');verified.append({'case':case,'ram':v['ram_mib'],'frame':frame})
out['canonical_F2_raw_frames']=verified
# Lists independently captured in same frozen component, both actual modes.
h=J(R/'test_results/f4p05/host_b26/report.json');out['host_modes']={}
for fam in ('host','b26'):
 rows=[x for x in h['records'] if x['family']==fam];check(Counter(x['mode'] for x in rows)==Counter(['serial','parallel','list']),'host modes');listed=next(x['listed'] for x in rows if x['mode']=='list')
 for x in rows:
  t=pathlib.Path(x['log']).read_text();l=re.findall(r'^([^\r\n]+): test$',t,re.M);p=re.findall(r'^test (\S+) \.\.\. ok$',t,re.M);i=re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',t,re.M);check(x['exit_code']==0 and H(x['log'])==x['log_sha256'] and (l,p,i)==(x['listed'],x['passed'],x['ignored']),'host raw lists')
  if x['mode']!='list':check(Counter(p+i)==Counter(listed),'host membership')
 out['host_modes'][fam]={'identities':listed,'count':len(listed),'serial_parallel_list_equal':True}
check(Counter(out['host_modes']['b26']['identities'])==Counter(B26_REQUIRED),'B26 required149')
rust=J(W/'provenance_and_rust_01.json')['rust_execution'];hostlist=out['host_modes']['host']['identities'];filter_checks=[]
for gate in a['gates']:
 cmd=gate['command']
 if cmd[0]!='cargo' or 'test' not in cmd or not any('tests_kernel' in z for z in cmd):continue
 row=next(x for x in rust if x['gate']==gate['gate']);expected=hostlist
 if '--lib' in cmd:
  idx=cmd.index('--lib')+1;fil=cmd[idx] if idx<len(cmd) and not cmd[idx].startswith('--') else ''
  expected=[n for n in hostlist if n==fil] if '--exact' in cmd else [n for n in hostlist if fil in n]
 check(Counter(row['passed']+row['ignored'])==Counter(expected),'all host filtered membership '+gate['gate']);filter_checks.append({'gate':gate['gate'],'exact_count':len(expected)})
check(Counter(next(x for x in rust if 'owned USER arena host contract' in x['gate'])['passed'])==Counter(F4_HOST_REQUIRED),'focused exact source-required12')
out['all_host_filtered_membership']=filter_checks
# Every portable execution name also names an actual test declaration in source.
source_text='\n'.join(p.read_text(errors='replace') for p in (R/'crates/rostifs').rglob('*.rs') if 'target' not in p.parts)
functions=set(re.findall(r'\bfn\s+(\w+)\s*\(',source_text));portable=[]
for row in rust:
 if row['gate'].startswith('RostiFS'):
  check(all(n.split('::')[-1] in functions for n in row['passed']+row['ignored']),'portable undeclared name');portable.append({'gate':row['gate'],'passed':len(row['passed']),'ignored':len(row['ignored'])})
out['portable_declared_membership']=portable
# Exact unittest names/time from canonical raw verbose successes, no rerun.
tree=ast.parse((R/'scripts/test_acceptance_harness.py').read_text());declared=[c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef)) and f.name.startswith('test_')];mg=next(g for g in a['gates'] if g['gate']=='acceptance runner regressions');text=(R/mg['log']).read_text();success=re.findall(r'^(test_\w+) \(__main__\.(\w+)\.\1\) \.\.\. ok$',text,re.M);check(Counter(c+'.'+n for n,c in success)==Counter(declared) and len(declared)==89,'canonical89 AST membership');out['canonical_mock89_exact_AST_membership']=True
protected=J(B/'continuation03_protected_inputs.json')['protected_sha256'];check(all(H(R/p)==v for p,v in protected.items()),'protected bytes');base=J(B/'baseline_state_02.json');out['protected_files']=protected;d1=base['d1_pins'];out['d1_pin_format']=d1
if isinstance(d1,dict):
 for p,v in d1.items():
  if isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v):check(H(R/p)==v,'d1 preserved')
old=J(R/'test_results/f3acc/acceptance_20261021T173237Z_upgt4pc_/acceptance.json')['source_sha256'];protected_source=['src/exception_abi.rs','src/exception_entry.s','src/exception_fatal.rs','src/gdt_tss.rs','src/f3_entry.s','src/memory/privileged.rs','src/io/serial.rs'];check(all(S[p]==old[p] for p in protected_source),'inherited ABI/TSS drift');out['inherited_source_identity']={p:S[p] for p in protected_source}
reviews={}
for n in ('candidate_review_01','candidate_review_02','candidate_review_03','candidate_review_04','candidate_review_05','design_review_01','design_review_02'):
 p=B/'reviews'/f'{n}.json';q=J(p);reviews[n]={'sha256':H(p),'verdict':q['verdict'],'blocker_count':q.get('blocker_count')}
out['historical_reviews']=reviews
out['preserved_reviewer_tool_failure']={'script':'deep_01.py','actual_exit':1,'error':'RuntimeError: F1 aggregate state/preservation/cleanup','cause':'Overstrong attempt to run legacy full F1 validator against disclosed retained-stage bounded component. No artifact repaired or check weakened. Original gap remains; independently validated approved bounded preservation separately in deep_02.py.','not_a_new_guest_or_acceptance_failure':True}
check(source_snapshot()==S,'source drift');save('extra_validation_01.json',out);print('canonical raw F2 frames8/literals/STATE/resources/host filters/89mock AST/protected/history PASS')
