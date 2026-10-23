"""Preserve manifest03 and freeze NEW provenance tools after actual negative controls."""
import hashlib
import json
import os
from pathlib import Path
import sys
if sys.flags.optimize or os.environ.get('PYTHONOPTIMIZE'): raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
old_path=BASE/'candidate_manifest_03.json'
need(sha(old_path)=='f50d86f092b90efd99307a46dfd2dbd7fc4dd9a91a98a418e440e5b5de29867f','manifest03 drift')
old=json.loads(old_path.read_bytes())
need(source_snapshot()==old['source_sha256'],'source membership or hash drift')
pins=dict(old['artifact_sha256'])
for p,d in pins.items(): need(sha(ROOT/p)==d,'historical candidate drift '+p)
review=BASE/'reviews/candidate_review_04.json'
need(sha(review)=='136183c5138ad366322692d3a9bf425b1ac05672cc62283d266f8e5ec8b83bc8','review04 drift')
controls_path=BASE/'canonical_controls_04.json'
controls=json.loads(controls_path.read_bytes())
need(controls['overall']=='PASS' and controls['actual_exit']==0 and controls['test_count_source_ast']==27 and controls['test_summary_ok'] and controls['production_output_created'] is False,'controls not passed')
for p,d in controls['artifact_sha256'].items(): need(sha(p)==d,'control artifact drift '+p)
parent=json.loads((BASE/'parent_components_readback_05.json').read_bytes())
for p,d in parent['artifact_sha256'].items(): need(sha(p)==d,'component drift '+p)
new_paths=[old_path,review,controls_path,BASE/'canonical_identity_readback_02.py',Path(__file__)]+[Path(p) for p in controls['artifact_sha256']]
for p in new_paths: pins[p.relative_to(ROOT).as_posix()]=sha(p)
new=dict(old)
new.update(schema='rosti.f4-candidate-manifest.v4',status='AWAITING_INDEPENDENT_REVIEW',artifact_sha256=pins,artifact_pin_count=len(pins),supersedes_manifest={'path':old_path.relative_to(ROOT).as_posix(),'sha256':sha(old_path)},artifact_delta=[],added_artifact_paths=sorted(set(pins)-set(old['artifact_sha256'])),canonical_tooling={'launcher':'test_results/phase11f4_user_arena/run_canonical_03.py','readback':'test_results/phase11f4_user_arena/canonical_readback_03.py','identity_readback':'test_results/phase11f4_user_arena/canonical_identity_readback_03.py','provenance':'test_results/phase11f4_user_arena/canonical_provenance_03.py','required_review_schema':'rosti.f4-independent-candidate-review.v5','output_parent':'test_results/f4acc/c03'},resolution_request={'blockers':['F4-C04-B1','F4-C04-B2'],'decision':'Preserve every prior artifact; add complete-review admission and mutually consistent dynamic launcher/readback revisions. Independent review of actual new bytes is mandatory.','controls_path':controls_path.relative_to(ROOT).as_posix(),'actual_control_tests':27,'source_or_component_change':False,'canonical_not_started':True})
need(source_snapshot()==old['source_sha256'],'source drift at completion')
with (BASE/'candidate_manifest_04.json').open('x',encoding='utf8',newline='\n') as f: json.dump(new,f,indent=2);f.write('\n')
print(json.dumps({'manifest_sha256':sha(BASE/'candidate_manifest_04.json'),'source_pin_count':len(new['source_sha256']),'artifact_pin_count':len(pins),'parent_artifact_count':len(parent['artifact_sha256']),'added_artifact_paths':new['added_artifact_paths']},indent=2))
