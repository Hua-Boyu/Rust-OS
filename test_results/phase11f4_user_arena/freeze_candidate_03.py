"""New artifact-only freeze after review03; never modifies prior manifests/reviews."""
import hashlib
import json
import os
from pathlib import Path
import sys
if sys.flags.optimize or os.environ.get('PYTHONOPTIMIZE'):
    raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
old_path=BASE/'candidate_manifest_02.json'
need(sha(old_path)=='070bb40f9f55e7868e378909ed794445638c3a7887f4e689dd6f67c9ec63fd78','prior manifest drift')
old=json.loads(old_path.read_bytes())
review_path=BASE/'reviews/candidate_review_03.json'
need(sha(review_path)=='6aa94d5d4c4bd0792ac21ddc6122849da585bf62d3fbc7b7b4ef322971d2216c','review03 drift')
review=json.loads(review_path.read_bytes())
need(review['verdict']=='REJECT' and review['blocker_count']==1 and review['blockers'][0]['id']=='F4-C03-B1','unexpected rejection')
need(source_snapshot()==old['source_sha256'],'source membership/bytes drift')
changed=[]
pins=dict(old['artifact_sha256'])
for path,expected in pins.items():
    actual=sha(ROOT/path)
    if actual!=expected:
        changed.append({'path':path,'before_sha256':expected,'after_sha256':actual})
need(changed==[{'path':'test_results/phase11f4_user_arena/run_canonical_02.py','before_sha256':'809fa5c453be32e0f67de73cb4710f042840664ae29f5e2dc3ce4e0f22c72a74','after_sha256':'671fefdfb49c477b45e04fd4276c46289bde88622159eed42113cec562921e88'}],'unexpected artifact drift')
parent=json.loads((BASE/'parent_components_readback_05.json').read_bytes())
for p,d in parent['artifact_sha256'].items(): need(sha(p)==d,'component artifact drift '+p)
pins[changed[0]['path']]=changed[0]['after_sha256']
for path in (old_path,review_path,Path(__file__)):
    pins[path.relative_to(ROOT).as_posix()]=sha(path)
new=dict(old)
new.update(schema='rosti.f4-candidate-manifest.v3',status='AWAITING_INDEPENDENT_REVIEW',artifact_sha256=pins,artifact_pin_count=len(pins),supersedes_manifest={'path':old_path.relative_to(ROOT).as_posix(),'sha256':sha(old_path)},artifact_delta=changed,added_artifact_paths=sorted(set(pins)-set(old['artifact_sha256'])),resolution_request={'blocker':'F4-C03-B1','decision':'Preserve original launcher pin and rejection; explicitly review current launcher in a new artifact freeze. No restoration without authenticated original bytes.','cause':'Parent overwrote existing run_canonical_02.py during interrupted continuation. This was task-local artifact drift, not production source drift.','required_review':'Inspect entire current launcher and verify all manifest pins; independently approve this exact new freeze before launch.','source_or_component_change':False,'regression_evidence':'Unchanged187 source pins and61483 component artifact pins freshly rehashed; no production revalidation is relabeled or replaced.'})
need(source_snapshot()==old['source_sha256'],'source drift at freeze completion')
with (BASE/'candidate_manifest_03.json').open('x',encoding='utf8',newline='\n') as f:
    json.dump(new,f,indent=2);f.write('\n')
print(json.dumps({'manifest_sha256':sha(BASE/'candidate_manifest_03.json'),'source_pin_count':len(new['source_sha256']),'artifact_pin_count':len(pins),'changed':changed,'parent_artifact_count':len(parent['artifact_sha256'])},indent=2))
