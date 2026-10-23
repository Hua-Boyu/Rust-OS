"""Read-only recovery and all shortest RED problem chains; no acceptance."""
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import subprocess
import sys
if sys.flags.optimize:
    raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
old=json.loads((BASE/'correction_checkpoint_01.json').read_bytes())
need(source_snapshot()==old['source_after'],'checkpoint source mismatch')
for p,d in old['artifact_sha256'].items(): need(sha(ROOT/p)==d,'historical drift '+p)
reports={}
for folder,expected in [('correction_red_01','241ecb209f9a2687daa430d5ff0f0e2596937eb829f7d080fb868122cd0bb516'),('correction_green_01','a21454d323c908aa1bdeb2dc8ee72c13a0dd0f8ca0c0ec5ac9384ce90e5df3eb')]:
    directory=BASE/folder
    g=json.loads((directory/'closure.json').read_bytes())
    r=json.loads((directory/'report.json').read_bytes())
    need(sha(directory/'kernel.elf')==g['elf_sha256']==expected,'ELF mismatch')
    need(g['result']=='RED' and len(g['unresolved'])==7 and len(g['forbidden'])==30,'RED counts')
    need(all(x['exit_code']==0 for x in r['commands']),'historical build/compiler')
    need(r['overall']==('PASS' if folder=='correction_red_01' else 'FAIL'),'historical result')
    blocks={int(k):v for k,v in g['closure'].items()}
    adjacency=defaultdict(list)
    for e in g['edges']:
        if e['kind']!='pic_call_next': adjacency[e['from']].append(e['to'])
    paths={g['root']:[g['root']]}; q=deque([g['root']])
    while q:
        a=q.popleft()
        for b in adjacency[a]:
            if b not in paths: paths[b]=paths[a]+[b]; q.append(b)
    byname={b['name']:a for a,b in blocks.items()}
    issues=[]
    for kind,items in [('forbidden',g['forbidden']),('unresolved',g['unresolved'])]:
        for item in items:
            a=item.get('address') if kind=='forbidden' else byname.get(item.get('block'))
            if a not in paths:
                a=next((a for a,b in blocks.items() if any(i['address']==item['address'] for i in b['instructions'])),None)
            need(a in paths,'unreachable issue')
            names=[blocks[x]['name'] for x in paths[a]]
            issues.append({'kind':kind,'item':item,'shortest_path':names,'through_shared_serial':any('6serial4puts' in n for n in names)})
    reports[folder]={'report_sha256':sha(directory/'report.json'),'elf_sha256':expected,'blocks':len(blocks),'edges':len(g['edges']),'issues':issues}
need(sha(ROOT/'target/target/debug/kernel')==reports['correction_green_01']['elf_sha256'],'current exact ELF')
protected={p:sha(ROOT/p) for p in old['protected_raw_sha256']}
need(protected==old['protected_raw_sha256'],'protected drift')
value={'STATUS':'PARTIAL','checkpoint_readback_exit':0,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'status':subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),'source_sha256':source_snapshot(),'protected_raw_sha256':protected,'red_analysis':reports,'two_snapshots':{'first':'b22a98164fd2a0c7af7f0ae70fcb34f750515d20e7cb40814ad8eefa8dac8309','second':sha(ROOT/'src/memory/retained_owner.rs'),'intervening_read':'serial driver, f4_terminal, approved design, checkpoint verifier'},'process_classification':{'managed':[],'foreign_build_test':[],'foreign_writer':'not observed; matching hashes do not prove exclusive ownership','infrastructure':'Hermes gateway/dashboard/serve/desktop/MCP, Strata, Docker/WSL; no interference','unknown':'persistent Hermes kernel contexts; no build/QEMU descendants observed','owned':'this recovery and later explicitly recorded drivers','foreign_killed':False},'terminal_bytes':{k:{'hex':v.hex(),'length':len(v)} for k,v in [('success',b'F4 USER arena PASS Ring0 terminal\n'),('failure',b'F4 USER arena FAIL Ring0 terminal\n')]}}
with (BASE/'correction_recovery_02.json').open('x',encoding='utf8',newline='\n') as f: json.dump(value,f,indent=2); f.write('\n')
print(json.dumps({'STATUS':'PARTIAL','source_count':len(value['source_sha256']),'issues':{k:{'total':len(v['issues']),'through_serial':sum(x['through_shared_serial'] for x in v['issues'])} for k,v in reports.items()},'terminal_bytes':value['terminal_bytes']},indent=2))
