"""Independent final offline review. No build/test/guest entrypoints."""
import sys, pathlib, json, hashlib, datetime, difflib, io, re, importlib.util, csv
from collections import Counter
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS'); B=R/'test_results/phase11f4_user_arena'; W=B/'reviews/final_readback_work_01'
sys.path[:0]=[str(B),str(R/'scripts')]
if sys.flags.optimize: raise RuntimeError('optimized review refused')
def H(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def J(p): return json.loads(pathlib.Path(p).read_bytes())
def save(n,v):
 with (W/n).open('x',encoding='utf8',newline='\n') as f: json.dump(v,f,indent=2,default=str); f.write('\n')
def check(v,msg):
 if not v: raise RuntimeError(msg)
def pins(m):
 bad=[]
 for p,h in m.items():
  p=pathlib.Path(p); p=p if p.is_absolute() else R/p
  if not p.is_file() or H(p)!=h: bad.append(str(p))
 check(not bad,repr(bad)); return {'count':len(m),'mismatches':bad}
from phase6_verify import source_snapshot,F3_PREDECESSOR_GATES,F4_GATES,predecessor_contract,evidence_rows,phase10_evidence
from canonical_provenance_03 import validate_driver
M=J(B/'candidate_manifest_04.json'); Q=J(B/'reviews/candidate_review_05.json'); S=source_snapshot()
check(H(B/'candidate_manifest_04.json')=='0b56cff4baefb9763152e68332e2b7bdee8cb95a30fbc6bb17bffbc8cdc17765','manifest hash')
check(H(B/'reviews/candidate_review_05.json')=='fbcb7dad91b437393379fcbd9211cd4f9362be4445128848b0bd36e22a53d3d9','review hash')
check(S==M['source_sha256']==Q['source_sha256'] and len(S)==187,'discovered source')
f={'source':pins(S),'candidate_artifacts':pins(M['artifact_sha256']),'reviewer_evidence':pins(Q['evidence_sha256'])}
save('freeze_01.json',f); print('source187/candidate81/reviewer28 PASS',flush=True)
P=J(B/'parent_components_readback_05.json'); C=J(B/'parent_canonical_readback_04.json')
f['parent_canonical_artifacts']=pins(C['artifact_sha256']); save('canonical_pins_01.json',f['parent_canonical_artifacts']); print('canonical pins',f['parent_canonical_artifacts'],flush=True)
f['parent_component_artifacts']=pins(P['artifact_sha256']); save('component_pins_01.json',f['parent_component_artifacts']); print('component pins',f['parent_component_artifacts'],flush=True)
sup=J(B/'canonical_readback_supplement_01.json')
check(H(B/'canonical_readback_supplement_01.json')=='b4d0579ca7841e3d1847d506b8beae4d1af51d69bceacd934c28f066aff18e3d','supplement identity')
f['supplement_artifacts']=pins(sup['artifact_sha256']); check(sup['source_sha256']==S,'supplement source')
old=(B/'canonical_readback_03.py').read_bytes(); new=(B/'canonical_readback_04.py').read_bytes()
expected=old.replace(b'Offline v3 reader. Usage: canonical_readback_03.py DRIVER_RESULT_JSON.\nPreserves v2 deep validators; never launches acceptance.',b'Offline v4 reader. Usage: canonical_readback_04.py DRIVER_RESULT_JSON.\nPreserves v3 validators; only fixes ISO Rock Ridge lookup. Never launches acceptance.').replace(b'usage: canonical_readback_03.py DRIVER_RESULT_JSON',b'usage: canonical_readback_04.py DRIVER_RESULT_JSON').replace(b'canonical_iso_kernel_03.bin',b'canonical_iso_kernel_04.bin').replace(b"iso_path='/BOOT/ROSTI.BIN;1'",b"rr_path='/boot/rosti.bin'").replace(b'parent_canonical_readback_03.json',b'parent_canonical_readback_04.json')
check(expected==new,'reader byte delta beyond declared replacements')
check(J(B/'parent_canonical_readback_03.json')['overall']=='FAIL' and (B/'canonical_iso_kernel_03.bin').stat().st_size==0,'original failure preserved')
D,A,AP,provenance=validate_driver(R/'test_results/f4acc/c03/driver_result.json',S,list(F3_PREDECESSOR_GATES)+list(F4_GATES)); run=AP.parent
check(H(AP)=='3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4','acceptance identity')
check(H(predecessor_contract())=='2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b','predecessor')
check(Counter(g['gate'] for g in A['gates'])==Counter(g['gate'] for g in J(predecessor_contract())['gates'])+Counter(F4_GATES),'70+2 multiset')
check(A['phase11_release_ready'] is False,'release qualification')
import pycdlib
iso=pycdlib.PyCdlib(); ip=R/A['iso']['path']; iso.open(str(ip)); buf=io.BytesIO(); low=io.BytesIO(); err=None
try:
 try: iso.get_file_from_iso_fp(io.BytesIO(),iso_path='/BOOT/ROSTI.BIN;1')
 except Exception as e: err=repr(e)
 iso.get_file_from_iso_fp(buf,rr_path='/boot/rosti.bin'); iso.get_file_from_iso_fp(low,iso_path='/boot/rosti.bin;1')
 listing=list(iso.walk(iso_path='/'))
finally: iso.close()
raw=buf.getvalue(); kh=hashlib.sha256(raw).hexdigest(); check(raw==low.getvalue(),'RR/ISO9660 payload mismatch')
check(len(raw)==6575756 and kh==H(R/'target/target/debug/kernel')==M['terminal_elf_sha256']==A['iso']['kernel_sha256']==A['f4_production_kernel_sha256'],'kernel identities')
check(H(ip)==A['iso']['sha256'] and ip.stat().st_size==A['iso']['bytes']==11700224,'ISO identity')
check(err is not None and 'Could not find path' in err,'original namespace failure independently reproduced in memory')
save('supplement_resolution_01.json',{'status':'PASS','classification':'Postcanonical task-local offline namespace reader correction, not source/harness/candidate drift','exact_declared_byte_replacements_only':True,'all_original_provenance_and_deep_checks_unchanged':True,'reader03_failure_preserved':True,'original_selector_error_independent':err,'namespace_listing':listing,'RR_and_lowercase_ISO9660_payload_identical':True,'extracted_bytes':len(raw),'kernel_sha256':kh,'supplement_sha256':H(B/'canonical_readback_supplement_01.json'),'supplement_pins':f['supplement_artifacts'],'reader_diff':list(difflib.unified_diff(old.decode().splitlines(),new.decode().splitlines()))})
rows=[]
for g in A['gates']:
 log=R/g['log']; text=log.read_text(errors='replace'); check(log.is_file() and g['status']=='PASS' and type(g['exit_code']) is int and g['exit_code']==0,'actual gate status')
 if g['command'][0]=='cargo' and 'test' in g['command']:
  sums=re.findall(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored',text); passed=re.findall(r'^test (\S+) \.\.\. ok\s*$',text,re.M); ignored=re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',text,re.M)
  check(sums and sum(int(p) for p,i in sums)>0,'zero Rust suite')
  check(sum(int(p) for p,i in sums)==len(passed) and sum(int(i) for p,i in sums)==len(ignored),'summary/member mismatch '+g['gate'])
  rows.append({'gate':g['gate'],'passed':passed,'ignored':ignored,'summaries':sums,'log_sha256':H(log)})
for name,expected in [('host tests',P['tests']['host']['identities']),('Phase 9.6 B26 host safety regressions',P['tests']['b26']['identities']),('Phase 11 F4 owned USER arena host contract',[n for n in P['tests']['host']['identities'] if 'f4_user_arena_tests::' in n])]:
 row=next(r for r in rows if r['gate']==name); check(Counter(row['passed']+row['ignored'])==Counter(expected),'exact identities '+name)
focused=re.findall(r'#\[test\]\s*fn\s+(\w+)',(R/'src/memory/f4_user_arena_tests.rs').read_text()); check(len(focused)==12,'Rust focused declarations')
fr=next(r for r in rows if r['gate']=='Phase 11 F4 owned USER arena host contract'); check(Counter(n.split('::')[-1] for n in fr['passed'])==Counter(focused) and not fr['ignored'],'focused declaration membership')
mock=next(g for g in A['gates'] if g['gate']=='acceptance runner regressions'); text=(R/mock['log']).read_text(); timing=re.findall(r'Ran (\d+) tests in ([0-9.]+)s\s+OK',text); check(timing==[('89','802.654')],'canonical mock timing')
save('provenance_and_rust_01.json',{'driver':D,'acceptance_sha256':H(AP),'gate_multiset_exact_70_plus_2':True,'rust_execution':rows,'canonical_mock':{'tests':89,'suite_seconds':802.654,'bound_seconds':900,'log':mock['log'],'sha256':H(R/mock['log'])},'isolated_calibration_not_canonical':{'suite_seconds':604.056,'wall_seconds':604.420999999973}})
save('progress_02.json',{'status':'PASS','completed':['all source/candidate/reviewer/component/canonical pins','driver admission and exact gate multiset','ISO namespace independent extraction and exact delta','Rust actual nonzero identities'],'remaining':['deep canonical validators','emitted closure','final findings and stability']})
print('supplement/extraction/provenance/Rust PASS',flush=True)
