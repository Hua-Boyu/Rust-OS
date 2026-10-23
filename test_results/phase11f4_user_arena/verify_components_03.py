"""Frozen F4 component verification; never canonical acceptance or review approval."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
from f3_full_guest import run_owned
from f3_full_evidence import validate as validate_f3
from f2_evidence import validate as validate_f2
from f4_evidence import validate_aggregate
from f1_evidence import scenario_identities, schedule_for

OUT = Path(sys.argv[1]).resolve()
if OUT.parent != ROOT/'test_results':
    raise RuntimeError('short invocation-owned test_results child required')
OUT.mkdir(exist_ok=False)
shutil.copyfile(__file__,OUT/'driver.py')
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open('w',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,indent=2)
        f.write('\n')
def need(test,message):
    if not test:
        raise RuntimeError(message)
def single(parent):
    paths=list(parent.glob('*/report.json'))
    need(len(paths)==1,'missing/ambiguous invocation '+str(parent))
    return paths[0]

before = source_snapshot()
report = {'scope':'F4 frozen components, NOT canonical acceptance','overall':'RUNNING',
          'source_before':before,'recorder_sha256':sha(__file__),'steps':[],'evidence':{}}
save(OUT/'source_before.json',before)
for name,digest in before.items():
    path=OUT/'source'/name
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(ROOT/name).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==digest,'source copy drift '+name)
    path.write_bytes(raw)
save(OUT/'report.json',report)
def run(name,argv,timeout):
    need(source_snapshot()==before,'source drift before '+name)
    row={'name':name,'command':list(map(str,argv)),'exit_code':None,'log':name+'.log'}
    report['steps'].append(row)
    save(OUT/'report.json',report)
    try:
        with (OUT/row['log']).open('xb') as log:
            row['exit_code']=run_owned(row['command'],log,timeout,row)
    finally:
        row['log_sha256']=sha(OUT/row['log'])
        save(OUT/'report.json',report)
    need(row['exit_code']==0,'failed component '+name)
    need(source_snapshot()==before,'source drift after '+name)
    print(name+' exit0',flush=True)
py=sys.executable
try:
    run('production_format',['cargo','+nightly','fmt','--check'],180)
    run('production_build',['cargo','+nightly','build','--locked'],240)
    run('production_elf',[py,'-B','scripts/validate_elf.py','target/target/debug/kernel'],120)
    kernel_sha=sha(ROOT/'target/target/debug/kernel')
    report['production_kernel_sha256']=kernel_sha
    run('host_b26',[py,'-B',ROOT/'test_results/phase11f4_user_arena/host_matrix_01.py',OUT/'host_b26'],600)
    hosts=json.loads((OUT/'host_b26/report.json').read_bytes())
    need(hosts['overall']=='PASS' and hosts['source_before']==before and not hosts['source_drift'],'host/B26 binding')
    run('f1',[py,'-B','scripts/boot_metadata_test.py','--f1','--boot','elf','--output-dir',OUT/'f1'],2100)
    f1path=single(OUT/'f1')
    f1=json.loads(f1path.read_bytes())
    need(f1['overall']=='PASS' and f1['source_snapshot']==before and f1['source_unchanged'] is True and f1['default_elf_unchanged'] is True,'F1 aggregate/source')
    scenario_identities(f1['scenarios'])
    child_pins={str(f1path):sha(f1path)}
    checkpoint_count=0
    for row in f1['scenarios']:
        child=f1path.parent/f'{row["case"]}_{row["ram_mib"]}'/'report.json'
        need(Path(row['report']).resolve()==child.resolve(),'F1 child identity')
        value=json.loads(child.read_bytes())
        need(value['overall']=='PASS' and value['owned_qemu_exited'] is True and value['actual_qemu_exit']==1,'F1 guest/owned cleanup')
        schedule=schedule_for(row['case'])
        need(value['schedule']==schedule and [c['checkpoint'] for c in value['checkpoints']]==schedule,'F1 exact stopped checkpoints')
        for ordinal,checkpoint in enumerate(value['checkpoints']):
            path=child.parent/f'{ordinal:02d}_{schedule[ordinal]}'/'snapshot.json'
            need(Path(checkpoint['snapshot']).resolve()==path.resolve(),'F1 snapshot origin')
            snap=json.loads(path.read_bytes())
            need(snap['capture_complete'] is True and snap['failure_outcome'] is None and snap['query_status']['running'] is False,'F1 complete stopped capture')
            need(snap['hardware']==snap['hardware_after'] and 'CPL=0' in snap['registers'] and 'CPL=0' in snap['registers_after'],'F1 stable CPL0')
            checkpoint_count+=1
    for path in f1path.parent.rglob('*'):
        if path.is_file(): child_pins[str(path)]=sha(path)
    report['evidence']['f1']={'report':str(f1path),'scenario_count':len(f1['scenarios']),'checkpoint_count':checkpoint_count,'pins':child_pins,
        'limitation':'Historical full f1_evidence final-readback gap NOT closed. This is fresh unchanged F1 driver preservation plus bounded parent capture checks, not that legacy validator approval.',
        'stage_retained':f1.get('stage_retained')}
    save(OUT/'report.json',report)
    run('f2',[py,'-B','scripts/f2_exception_guest.py','--output-dir',OUT/'f2'],600)
    f2path=single(OUT/'f2')
    report['evidence']['f2']=validate_f2(f2path,before)
    save(OUT/'report.json',report)
    run('f3',[py,'-B','scripts/f3_full_guest.py','--output-dir',OUT/'f3'],2100)
    f3path=single(OUT/'f3')
    report['evidence']['f3']=validate_f3(f3path,before)
    save(OUT/'report.json',report)
    run('f4',[py,'-B','scripts/f4_arena_guest.py','--output-dir',OUT/'f4'],2100)
    report['evidence']['f4']=validate_aggregate(OUT/'f4/report.json',before)
    need(sha(ROOT/'target/target/debug/kernel')==kernel_sha,'production ELF drift')
    report['overall']='PASS'
except Exception as exc:
    report.update(overall='FAIL',error=repr(exc))
finally:
    after=source_snapshot()
    report['source_after']=after
    report['source_drift']={n:[before.get(n),after.get(n)] for n in before.keys()|after.keys() if before.get(n)!=after.get(n)}
    if report['source_drift']: report['overall']='FAIL'
    save(OUT/'report.json',report)
    print(json.dumps({'overall':report['overall'],'output':str(OUT),'error':report.get('error')}),flush=True)
sys.exit(0 if report['overall']=='PASS' else 1)
