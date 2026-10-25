"""Read accepted baseline and record initial protected bytes; no source changes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'test_results/phase12_p12a'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def save(name, data):
    with (OUT / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')

def run(command):
    start = time.monotonic()
    p = subprocess.run(command, cwd=ROOT, capture_output=True)
    return {'command':command, 'cwd':str(ROOT), 'exit_code':p.returncode,
            'elapsed_seconds':time.monotonic()-start,
            'stdout':p.stdout.decode(errors='replace'), 'stderr':p.stderr.decode(errors='replace')}

if __name__ == '__main__':
    if sys.flags.optimize:
        raise RuntimeError('optimized verification refused')
    commands = [['git','status','--porcelain=v1','-uall'], ['git','branch','--show-current'],
                ['git','rev-parse','HEAD'], ['git','log','-8','--oneline','--decorate'],
                ['git','diff','--check'], ['git','merge-base','--is-ancestor',
                'd9cebe28eb5139b6b614b7000688857361e2afc4','HEAD']]
    rows = [run(c) for c in commands]
    protected = []
    for line in rows[0]['stdout'].splitlines():
        path = line[3:]
        if path.startswith('test_results/phase12_p12a/'):
            continue
        category = 'ACCEPTED_HISTORICAL' if path in ('src/exception_entry.s','test_results/phase11f4_user_arena/FINAL_REPORT.md') else 'PREEXISTING_USER_WORK'
        protected.append({'path':path,'git_status':line[:2], 'classification':category,'sha256':sha(ROOT/path)})
    review_path = ROOT/'test_results/phase12_design/review_inputs_01.json'
    review = json.loads(review_path.read_bytes())
    verified = {k:sha(ROOT/k) for k in review['pins']}
    inventory = json.loads((ROOT/'test_results/phase12_design/source_inventory.json').read_bytes())
    inv_verified = {k:sha(ROOT/v['path']) for k,v in inventory['source_files'].items()}
    need = lambda value, message: None if value else (_ for _ in ()).throw(RuntimeError(message))
    need(verified == review['pins'], 'approved review pin drift')
    need(all(inv_verified[k] == v['sha256'] for k,v in inventory['source_files'].items()), 'inventory drift')
    f5 = ROOT/'test_results/phase11f5_cpl3_proof'
    evidence = json.loads((f5/'evidence_manifest.json').read_bytes())
    acceptance = ROOT/evidence['canonical']['path']
    need(sha(acceptance) == evidence['canonical']['sha256'], 'F5 canonical hash mismatch')
    a = json.loads(acceptance.read_bytes())
    need(a['overall']=='PASS' and len(a['gates'])==76 and a['gates_passed']==76, 'F5 predecessor not PASS76')
    sys.path.insert(0,str(ROOT/'scripts'))
    from phase6_verify import source_snapshot
    snapshot = source_snapshot()
    ps = run(['powershell.exe','-NoProfile','-Command',
        '$os=Get-CimInstance Win32_OperatingSystem; [pscustomobject]@{FreePhysicalMemoryBytes=([long]$os.FreePhysicalMemory*1024);Processes=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match "cargo|rustc|link|qemu|python" } | Select-Object ProcessId,ParentProcessId,Name,CommandLine)} | ConvertTo-Json -Depth 5'])
    resources = json.loads(ps['stdout'])
    for p in resources['Processes']:
        cmd = p['CommandLine'] or ''
        p['classification'] = 'INFRASTRUCTURE' if any(s in cmd for s in ('hermes_cli','hermes_kernel','Strata')) else 'UNKNOWN'
    data = {'schema':'rosti.p12a-preflight.v1', 'git':rows,'protected':protected,
            'review_manifest_sha256':sha(review_path),'review_pins':verified,
            'inventory_pins':inv_verified,'canonical_source_before':snapshot,
            'f5_predecessor':{'path':evidence['canonical']['path'],'sha256':sha(acceptance),
                             'gates':[g['gate'] for g in a['gates']], 'actual_exit':evidence['canonical']['actual_exit'],
                             'files':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in (f5/'FINAL_REPORT.md', f5/'evidence_manifest.json',acceptance)}},
            'resources':resources, 'resource_command':ps, 'owned_processes':[]}
    save('preflight_01.json',data)
    print(json.dumps({'review_pins':len(verified),'inventory_inputs':len(inv_verified),'protected':len(protected),'canonical_inputs':len(snapshot),'available_bytes':resources['FreePhysicalMemoryBytes'],'git_exits':[r['exit_code'] for r in rows]},indent=2))
