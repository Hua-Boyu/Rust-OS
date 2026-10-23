"""Reviewer-authored MOCK ONLY launcher lifecycle controls; no child spawned."""
import sys,pathlib,json,contextlib,hashlib,ast,re,subprocess
from unittest.mock import patch,Mock
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS');B=R/'test_results/phase11f4_user_arena';W=pathlib.Path(__file__).parent
sys.path.insert(0,str(B));sys.path.insert(0,str(R/'scripts'))
import test_canonical_03 as t
import canonical_provenance_03 as p
import run_canonical_03 as l
import phase6_verify as runner
import psutil
out=[]
for mode in ('success','nonzero','ambiguous','source_drift','reuse','late_artifact_drift'):
 c=t.ProvenanceTests();c.setUp()
 try:
  output=c.root/'MOCK_LAUNCHER_ONLY';argv=[str(c.rp),p.sha(c.rp),str(c.mp),p.sha(c.mp)]
  if mode=='reuse':output.mkdir()
  calls=[];waited=[]
  def admit(*args):
   calls.append('admission')
   if mode=='late_artifact_drift' and len(calls)==2:c.tool.write_text('# MOCK late changed artifact')
   return p.validate_admission(*args,root=c.root,required_tools=(c.tool,))
  def fake_spawn(command,**kw):
   assert kw['cwd']==c.root
   a=output/'acceptance_MOCK_ONLY'/'acceptance.json';a.parent.mkdir();c.save(a,c.a)
   if mode=='ambiguous':
    other=output/'acceptance_MOCK_other'/'acceptance.json';other.parent.mkdir();c.save(other,c.a)
   proc=Mock(pid=31415)
   def wait():waited.append(True);return 1 if mode=='nonzero' else 0
   proc.wait.side_effect=wait
   return proc
  snapshot_calls=[]
  def snapshot():
   snapshot_calls.append(1)
   return {} if mode=='source_drift' and len(snapshot_calls)>2 else c.source_map
  with contextlib.ExitStack() as stack:
   for obj,key,val in [(l,'ROOT',c.root),(l,'OUT',output),(l,'validate_admission',admit),(runner,'source_snapshot',snapshot),(runner,'predecessor_contract',lambda:None),(runner,'F3_PREDECESSOR_GATES',c.gates[:-2]),(runner,'F4_GATES',c.gates[-2:]),(psutil,'process_iter',lambda *args:[])]:stack.enter_context(patch.object(obj,key,val))
   spawn=stack.enter_context(patch.object(l.subprocess,'Popen',side_effect=fake_spawn))
   error=None
   try:l.main(argv)
   except RuntimeError as e:error=str(e)
   assert (error is None)==(mode=='success'),(mode,error)
   record=p.load(output/'driver_result.json') if (output/'driver_result.json').exists() else None
   if mode in ('reuse','late_artifact_drift'):assert spawn.call_count==0 and not waited
   else:
    assert spawn.call_count==1 and len(waited)==1 and record['exit_observed_by']=='Popen.wait'
    assert record['candidate_manifest_path']==str(c.mp) and record['candidate_manifest_sha256']==p.sha(c.mp) and record['review_path']==str(c.rp) and record['review_sha256']==p.sha(c.rp)
    assert record['status']==('COMPLETED' if mode=='success' else 'FAILED')
   out.append({'case':mode,'PASS':True,'spawn_mock_calls':spawn.call_count,'real_spawn_calls':0,'wait_observed':len(waited),'error':error,'admission_calls':len(calls),'scope':'MOCK ONLY not acceptance evidence'})
 finally:c.doCleanups()
# Independently compare actual retained controls verbose membership with AST.
text=(W/'canonical_controls.log').read_text();tree=ast.parse((B/'test_canonical_03.py').read_text())
names=[f.name for cls in tree.body if isinstance(cls,ast.ClassDef) for f in cls.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_')]
actual=re.findall(r'^(test_\w+) \(__main__\.ProvenanceTests\.\1\) \.\.\. ok$',text,re.M)
from collections import Counter
assert Counter(names)==Counter(actual) and len(names)==27
# New short output path and old path have equal prefix length, no limit inflation.
assert len(str(p.OUT))==len(str(R/'test_results/f4acc/c02'))
assert not p.OUT.exists()
# Record exact publication emitted region independently from new disassembly.
dis=(W/'disassembly.txt').read_text();region=[]
for line in dis.splitlines():
 match=re.match(r'^\s*([0-9a-f]+):',line)
 if match and 0x256940<=int(match[1],16)<=0x256ab0:region.append(line)
assert any('256a6a:' in x for x in region) and any('256a37:' in x for x in region)
(W/'publication_disassembly.txt').write_text('\n'.join(region))
record={'qualification':'Reviewer-authored Python-only mock controls; never real runner execution','launcher_cases':out,'canonical_controls_exact_identities':actual,'canonical_controls_count':len(actual),'short_output_parent':str(p.OUT),'production_output_absent':not p.OUT.exists()}
with (W/'extra_controls.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
print('reviewer extra controls PASS: six mock launcher lifecycles, exact27 controls, fresh publication region')
