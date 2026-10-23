"""Parent exact final-review readback; does not replace independent approval."""
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from canonical_provenance_03 import load, sha, need, REQUIRED_AREAS, validate_driver
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot,F3_PREDECESSOR_GATES,F4_GATES,predecessor_contract
rp=BASE/'reviews/final_canonical_readback_01.json'
need(sha(rp)=='c5a423c9ac83d3e753609822cbb84dbd51170abbe292e81ac4ae495083db47f0','review raw drift')
r=load(rp)
need(r['schema']=='rosti.f4-independent-final-canonical-readback.v1','schema')
need(r['review_complete'] is True and r['mandatory_areas_complete'] is True and r['final_canonical_readback_approved'] is True,'incomplete')
need(r['verdict']=='APPROVE' and r['blockers']==[] and type(r['blocker_count']) is int and r['blocker_count']==0,'verdict/blockers')
need(r['independent_reviewer_provenance']['distinct_from_parent_and_candidate05'] is True,'independent provenance')
areas=[c['area'] for c in r['checks']]
need(len(areas)==len(set(areas))==20 and set(REQUIRED_AREAS).issubset(areas),'complete scope')
need(all(c['status']=='PASS' and bool(c['findings']) for c in r['checks']),'ungrounded/nonPASS check')
need(r['supplement_resolution']['status']=='ACCEPTED_RESOLVED' and r['supplement_resolution']['checks_weakened'] is False and r['supplement_resolution']['production_or_harness_drift'] is False,'reader resolution')
need(r['supplement_resolution']['supplement_sha256']==sha(BASE/'canonical_readback_supplement_01.json'),'supplement identity')
source=source_snapshot()
need(source==r['source_sha256'] and len(source)==187,'source')
counts={}
for field in ('candidate_artifact_sha256','identity_sha256','evidence_sha256'):
    pins=r[field]
    for name,h in pins.items():
        path=Path(name)
        if not path.is_absolute(): path=ROOT/path
        need(path.is_file() and sha(path)==h,'final reviewer referenced artifact drift '+name)
    counts[field]=len(pins)
d,a,ap,provenance=validate_driver(ROOT/'test_results/f4acc/c03/driver_result.json',source,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
need(str(ap)==r['canonical']['acceptance_path'] and sha(ap)==r['canonical']['acceptance_sha256'],'canonical binding')
need(sha(predecessor_contract())=='2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b','predecessor')
need(source_snapshot()==source,'late source drift')
row={'overall':'PASS','scope':'Parent complete final-review schema/provenance/scope/reference-pin validation; independent verdict is separately authored','review_path':str(rp),'review_sha256':sha(rp),'verdict':r['verdict'],'blocker_count':r['blocker_count'],'checks':[{k:c[k] for k in ('area','status')} for c in r['checks']],'source_pin_count':len(source),'source_sha256':source,'reference_maps_rehashed':counts,'canonical_acceptance_sha256':sha(ap),'supplement_resolution':r['supplement_resolution'],'independent_dispatch':{'delegation_id':'deleg_4a042c28','subagent_id':'sa-0-15d97b6d'},'reader_sha256':sha(__file__)}
with (BASE/'parent_final_readback_01.json').open('x',encoding='utf8',newline='\n') as f:
    json.dump(row,f,indent=2);f.write('\n')
print(json.dumps({k:row[k] for k in ('overall','review_sha256','verdict','blocker_count','source_pin_count','reference_maps_rehashed','canonical_acceptance_sha256')},indent=2))
