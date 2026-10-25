"""Sequential initial lists/runs and two production builds, before P12-A source."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT/'test_results/phase12_p12a'
OUT = ROOT/'test_results/p12a/b01'

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def need(v, msg):
    if not v:
        raise RuntimeError(msg)

def main():
    need(not sys.flags.optimize, 'optimized execution refused')
    import psutil
    OUT.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('f5host', ROOT/'test_results/phase11f5_cpl3_proof/host_matrix_06_01.py')
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    report = {'overall':'FAIL','steps':[], 'environment':{k:v for k,v in os.environ.items() if k.startswith(('CARGO','RUST'))}}
    before = subprocess.check_output(['git','status','--porcelain=v1','-uall'],cwd=ROOT)
    report['git_status_before'] = before.decode()
    def step(name, cmd, cwd, timeout=300):
        busy = [{'pid':p.pid,'name':p.info['name'],'command':p.info['cmdline']} for p in psutil.process_iter(['name','cmdline']) if (p.info['name'] or '').lower() in ('cargo.exe','rustc.exe','link.exe','qemu-system-i386.exe','qemu-system-x86_64.exe')]
        row = {'name':name,'command':cmd,'cwd':str(cwd),'available_bytes':psutil.virtual_memory().available,'busy':busy}
        report['steps'].append(row)
        need(not busy, 'foreign/unknown build/test process')
        need(row['available_bytes']>=1073741824, 'RAM below1GiB')
        start=time.monotonic()
        log=OUT/(name+'.log')
        with log.open('xb') as f:
            p=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        row.update(exit_code=p.returncode,elapsed_seconds=time.monotonic()-start,log=str(log.relative_to(ROOT)),sha256=sha(log))
        need(p.returncode==0,'nonzero '+name)
        print('PASS '+name,flush=True)
        return log.read_text(errors='replace'),row
    try:
        for key,manifest in [('host','tests_kernel'),('b26','tests_b26')]:
            cmd=['cargo','+nightly','test','--manifest-path',str(ROOT/manifest/'Cargo.toml'),'--lib']
            text,row=step(key+'_list',cmd+['--','--list'],Path.home())
            names=re.findall(r'^(\S+): test\s*$',text,re.M)
            need(names and len(names)==len(set(names)), 'empty/duplicate identities')
            report[key+'_identities']=names
            text,row=step(key+'_serial',cmd+['--','--test-threads=1'],Path.home())
            row['result']=host.verify_result(text,names,host.IGNORED if key=='host' else ())
        step('toolchain',['rustc','+nightly','-vV'],ROOT)
        elf=ROOT/'target/target/debug/kernel'
        for letter in ('A','B'):
            step('clean_kernel_'+letter,['cargo','+nightly','clean','-p','kernel'],ROOT)
            step('production_'+letter,['cargo','+nightly','build'],ROOT)
            dest=OUT/('production_'+letter+'.elf')
            shutil.copyfile(elf,dest)
            report['PRODUCTION_ELF_BASELINE_'+letter]={'path':str(dest.relative_to(ROOT)),'sha256':sha(dest),'command':['cargo','+nightly','build'],'cwd':str(ROOT)}
        report['reproducible']=report['PRODUCTION_ELF_BASELINE_A']['sha256']==report['PRODUCTION_ELF_BASELINE_B']['sha256']
        report['git_status_after']=subprocess.check_output(['git','status','--porcelain=v1','-uall'],cwd=ROOT).decode()
        need(before.decode()==report['git_status_after'], 'worktree changed during baseline')
        report['overall']='PASS'
    except Exception as e:
        report['error']=repr(e)
    finally:
        with (OUT/'report.json').open('x',encoding='utf-8',newline='\n') as f:
            json.dump(report,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('steps','host_identities','b26_identities')},indent=2))
    return 0 if report['overall']=='PASS' else 1

if __name__=='__main__':
    raise SystemExit(main())
