"""Aggregate provenance only; canonical acceptance and independent readback remain authority."""
from pathlib import Path
import datetime, hashlib, json, shutil, subprocess
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
CONT=ROOT/'test_results/phase11a2_continuation'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
p=OUT/'evidence_manifest.json'; data=json.loads(p.read_text())
data['recorded_final_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
data['current_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
data['current_branch']=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
data['historical_partial_capture']={'snapshot':'partial_snapshot/','status':'superseded interrupted pause; preserved unchanged','clarification':'User explicitly authorized resume. Recovery and snapshot frame hashes identical; apparent view length difference does not authenticate concurrent mutation.'}
data['blocker']='No current source-review blocker; see actual acceptance and final readback status.'
data['historical_red']={}
for name,validity in [('red_generation_ownership','INVALID ownership RED: wrong repository CWD/std/test failures'),('red_generation_ownership_v2','INVALID ownership RED: wrong repository CWD/std/test failures'),('red_generation_ownership_v3','VALID historical compile RED29 missing API errors; old oracle superseded by corrected v4')]:
    jp=CONT/(name+'.json'); lp=CONT/(name+'.log')
    data['historical_red'][name]={'record':json.loads(jp.read_text()),'json_sha256':digest(jp),'log_sha256':digest(lp),'validity':validity}
data['candidate']=json.loads((OUT/'candidate_checks.json').read_text())
data['independent_review']={'path':'independent_source_review.json','sha256':digest(OUT/'independent_source_review.json'),'verdict':json.loads((OUT/'independent_source_review.json').read_text())['verdict'],'all_reviewed_hashes_match':all(digest(ROOT/name)==h for name,h in json.loads((OUT/'independent_source_review.json').read_text())['reviewed_raw_sha256'].items())}
data['resource_evidence']={'path':'resource_readback.json','sha256':digest(OUT/'resource_readback.json')}
data['finished_command_records']={}
for jp in sorted(CONT.glob('generation_*.json')):
    row=json.loads(jp.read_text())
    if 'exit_code' not in row: continue
    lp=jp.with_suffix('.log')
    for src in [jp,lp]:
        dest=OUT/src.name
        if dest.exists():
            if src.read_bytes()!=dest.read_bytes(): raise RuntimeError('refuse changed evidence copy: '+src.name)
        else: shutil.copyfile(src,dest)
    data['finished_command_records'][jp.stem]={'report_sha256':digest(jp),'log_sha256':digest(lp),'actual_exit':row['exit_code'],'cwd':row['cwd'],'command':row['command']}
accept=list((OUT/'acceptance').glob('*/acceptance.json'))
if len(accept)==1:
    report=json.loads(accept[0].read_text())
    data['acceptance']={'path':str(accept[0]),'overall':report.get('overall'),'gates_total':report.get('gates_total'),'source_sha256':report.get('source_sha256')}
    if report.get('overall')!='RUNNING': data['acceptance']['sha256']=digest(accept[0])
final=OUT/'independent_final_readback.json'
if final.exists(): data['final_readback']={'path':str(final),'sha256':digest(final),'report':json.loads(final.read_text())}
if data.get('acceptance',{}).get('overall')=='RUNNING':
    data['status']='IN PROGRESS'
elif final.exists() and data['final_readback']['report'].get('overall')=='PASS' and data.get('acceptance',{}).get('overall')=='PASS' and data['independent_review']['all_reviewed_hashes_match']:
    data['status']='VERIFIED BOUNDED CHECKPOINT; NOT FULL PHASE11 RELEASE'
else:
    data['status']='PARTIAL: final closeout pending'
for name in ['independent_final_execution.json','target_layout.json','post_commit_verification.json']:
    path=OUT/name
    if path.exists():
        data[name]={'path':name,'sha256':digest(path),'record':json.loads(path.read_text())}
data['verification']={'candidate':data['candidate']['status'],'source_review':data['independent_review']['verdict'],'acceptance':data.get('acceptance',{}).get('overall','NOT RUN'),'final_readback':'recorded' if final.exists() else 'pending'}
p.write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({'head':data['current_head'],'candidate':data['candidate']['status'],'acceptance':data.get('acceptance'),'copied_records':len(data['finished_command_records']),'review_hashes_match':data['independent_review']['all_reviewed_hashes_match']},indent=2))
