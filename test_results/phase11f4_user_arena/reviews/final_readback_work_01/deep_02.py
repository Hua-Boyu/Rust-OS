"""Continuation retaining failed overstrong legacy-F1-reader attempt unchanged."""
from pathlib import Path
p=Path(__file__).with_name('deep_01.py')
code=p.read_text()
code=code.replace("(W/n).open('x'","(W/n.replace('_01','_02')).open('x'")
old="f1path=one(f1paths);v=f1_evidence(f1path,S);check(v['scenarios']==10,'component F1 scenarios');"
new="""f1path=one(f1paths)
from f1_evidence import scenario_identities,schedule_for
f=J(f1path);scenario_identities(f['scenarios']);check(f['overall']=='PASS' and f['source_snapshot']==S and f['source_unchanged'] is True and f['default_elf_unchanged'] is True,'F1 bounded aggregate/source')
frows=[];snapshots=0
for row in f['scenarios']:
 child=pathlib.Path(row['report']);check(child.resolve()==(f1path.parent/f'{row["case"]}_{row["ram_mib"]}'/'report.json').resolve(),'F1 owned child');val=J(child);sched=schedule_for(row['case']);check(val['overall']=='PASS' and val['owned_qemu_exited'] is True and val['actual_qemu_exit']==1 and val['schedule']==sched and [c['checkpoint'] for c in val['checkpoints']]==sched,'F1 checkpoints and actual exit')
 for k,cp in enumerate(val['checkpoints']):
  q=child.parent/f'{k:02d}_{sched[k]}'/'snapshot.json';check(pathlib.Path(cp['snapshot']).resolve()==q.resolve(),'F1 snapshot path');snap=J(q);check(snap['capture_complete'] is True and snap['failure_outcome'] is None and snap['query_status']['running'] is False and snap['hardware']==snap['hardware_after'] and 'CPL=0' in snap['registers'] and 'CPL=0' in snap['registers_after'],'F1 stopped complete capture');snapshots+=1
 frows.append({'case':row['case'],'ram_mib':row['ram_mib'],'checkpoints':len(sched),'actual_qemu_exit':val['actual_qemu_exit']})
check(snapshots==142,'F1 exact142 checkpoints')
v={'scenarios':10,'snapshots':snapshots,'pins':component['evidence']['f1']['pins'],'rows':frows,'legacy_full_validator_approved':False,'legacy_gap_preserved':True,'retained_stage':f.get('stage_retained'),'qualification':'Bounded current-source component preservation only. Legacy validator correctly refuses stage_removed absent; retained-stage protocol is not being waived/promoted to full legacy readback.'}
"""
if code.count(old)!=1:raise RuntimeError('continuation anchor')
code=code.replace(old,new)
exec(compile(code,str(p.with_name('deep_02_virtual.py')),'exec'),{'__file__':str(p.with_name('deep_02_virtual.py')),'__name__':'__main__'})
