"""Finish existing text staging without altering immutable reviewed whitespace."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
if sys.flags.optimize:raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def need(ok,msg):
    if not ok:raise RuntimeError(msg)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
m=json.loads((BASE/'candidate_manifest_04.json').read_bytes())
need(source_snapshot()==m['source_sha256'],'source drift')
paths=sorted(p for p in git('diff','--cached','--name-only','-z').decode().split('\0') if p)
need(len(paths)==131,'unexpected inherited doc staging scope')
allowed=('test_results/phase11f4_user_arena/','test_results/f4p05/','test_results/f4acc/c03/')
docs={'HANDOVER.md','NEXT_SESSION_PROMPT.md','docs/PHASE11_HANDOVER.md','docs/PHASE11_MEMORY_AUTHORITY.md'}
need(all(p in docs or p.startswith(allowed) for p in paths),'out-of-scope staged path')
need(all(Path(p).suffix in ('.json','.md','.py') for p in paths),'binary stage')
immutable={
 'test_results/phase11f4_user_arena/canonical_identity_readback_03.py':'08f1885f324025d9a9ae403cf68de63a800c8deac0d07f2ce1bc5aa27ed553b5',
 'test_results/phase11f4_user_arena/decisions.md':'a7b82c73a09ee56ea06f0ccf036e008349b49c7608e8ea3b53cf56589e4c8382'}
expected='test_results/phase11f4_user_arena/canonical_identity_readback_03.py:36: trailing whitespace.\n+    \ntest_results/phase11f4_user_arena/decisions.md:66: new blank line at EOF.\n'
need((BASE/'documentation_whitespace_ordinary_01.log').read_text()==expected,'unclassified original whitespace diagnostic')
pins={};crlf=[]
for p in paths:
    raw=(ROOT/p).read_bytes();blob=git('show',':'+p)
    need(raw==blob,'raw staged drift '+p)
    pins[p]=sha(raw)
    need(not re.search(rb'-----BEGIN [^-]*PRIVATE KEY-----|(?:api[_-]?key|password|secret)\s*[:=]\s*[\x22\x27][A-Za-z0-9_+/=-]{16,}',blob,re.I),'possible secret in '+p)
    if b'\r\n' in raw:crlf.append(p)
for p,h in immutable.items():need(pins[p]==m['artifact_sha256'][p]==h,'immutable evidence changed '+p)
checks={}
for name,args in [('ordinary_excluding_two_authenticated_evidence_files',['diff','--cached','--check','--',*[p for p in paths if p not in crlf and p not in immutable]]),('preserved_crlf',['-c','core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol','diff','--cached','--check','--',*crlf])]:
    r=subprocess.run(['git',*args],cwd=ROOT,capture_output=True);need(r.returncode==0,'unclassified whitespace '+name)
    checks[name]={'actual_exit':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')}
need(source_snapshot()==m['source_sha256'],'late source drift')
protected=json.loads((BASE/'continuation03_protected_inputs.json').read_bytes())
for p,h in protected['protected_sha256'].items():need(sha((ROOT/p).read_bytes())==h and p not in paths,'protected altered/staged '+p)
row={'overall':'PASS','head_before':git('rev-parse','HEAD').decode().strip(),'staged_paths':paths,'staged_raw_sha256':pins,'preserved_crlf_paths':crlf,'whitespace':checks,'preserved_immutable_format_diagnostics':{'actual_default_exit':2,'exact_original_ordinary_diagnostics':expected,'authenticated_raw_sha256':immutable,'disposition':'Preserve reviewed bytes; these two historical evidence formatting findings are not new production changes and are not canonical gate waivers. No cleanup/normalization performed.'},'source_inputs_unchanged':True,'protected_bytes_match':True,'secret_scan_pass':True,'prior_attempt':{'path':'stage_documentation_closeout_01.py','actual_exit':1,'cause':'Overstrong demand that immutable pre-existing evidence have no whitespace diagnostics; all other strict checks passed.'}}
with (BASE/'documentation_staging_readback_02.json').open('x',encoding='utf8',newline='\n') as f:json.dump(row,f,indent=2);f.write('\n')
print(json.dumps({'overall':'PASS','staged_count':len(paths),'staged_total_bytes':sum((ROOT/p).stat().st_size for p in paths),'staged_paths':paths,'crlf_paths':crlf,'preserved_immutable_whitespace_files':list(immutable),'strict_other_whitespace_checks':checks},indent=2))
