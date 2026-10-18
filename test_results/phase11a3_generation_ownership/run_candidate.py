"""Sequential candidate checks through the existing command recorder (not acceptance)."""
from pathlib import Path
import datetime, hashlib, json, re, shutil, subprocess, sys
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
WRAPPER=ROOT/'test_results/phase11a2_continuation/run_step.py'
HOME=Path('C:/Users/iamsv')
report={'status':'RUNNING','steps':[],'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def save(): (OUT/'candidate_checks.json').write_text(json.dumps(report,indent=2)+'\n')
save()
kernel=ROOT/'target/target/debug/kernel'
baseline=OUT/'baseline_kernel.elf'
if baseline.exists(): raise SystemExit('refuse overwrite baseline')
shutil.copyfile(kernel,baseline)
report['baseline_kernel_sha256']=hashlib.sha256(baseline.read_bytes()).hexdigest()
assert report['baseline_kernel_sha256']=='8b43ae2ee1d20e40bd1754e031202a1d0085ae21de8bb6162edbea671c2ba9b9'
def run(name,cwd,argv,expected_count=None):
    full_name='generation_candidate_'+name
    r=subprocess.run([sys.executable,'-B',str(WRAPPER),full_name,str(cwd),'0',*map(str,argv)],cwd=HOME,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    for suffix in ['.json','.log']:
        src=WRAPPER.parent/(full_name+suffix)
        if src.exists(): shutil.copyfile(src,OUT/(full_name+suffix))
    row=json.loads((OUT/(full_name+'.json')).read_text())
    report['steps'].append(row)
    save()
    print(f"{name}: actual exit={row.get('exit_code')}",flush=True)
    if r.returncode or row.get('exit_code')!=0:
        print(r.stdout.decode(errors='replace'),flush=True)
        raise RuntimeError('step failed: '+name)
    if expected_count is not None:
        text=(OUT/(full_name+'.log')).read_text(errors='replace')
        observed=re.findall(r'^test (\S+) \.\.\. ok\s*$',text,re.M)
        totals=re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored',text)
        if totals!=[(str(expected_count),'0','0')] or len(set(observed))!=expected_count:
            raise RuntimeError('selected test count/identities invalid: '+name)
try:
    for name,count in [('generation_ownership_tests::',8),('generation_ledger_tests::',6),('generation_boundary_tests::',6)]:
        run(name[:-2],HOME,['cargo','+nightly','test','--manifest-path',ROOT/'tests_kernel/Cargo.toml','--lib',name,'--','--test-threads=1'],count)
    for crate in ['tests_kernel','tests_b26']:
        for mode,extra in [('serial',['--','--test-threads=1']),('parallel',[])]:
            run(crate+'_'+mode,HOME,['cargo','+nightly','test','--manifest-path',ROOT/crate/'Cargo.toml','--lib',*extra])
    run('contracts',ROOT,[sys.executable,'-B','scripts/test_acceptance_harness.py'])
    run('production_build',ROOT,['cargo','+nightly','build'])
    report['kernel_sha256']=hashlib.sha256(kernel.read_bytes()).hexdigest()
    run('paging_128_512',ROOT,[sys.executable,'-B','scripts/paging_test.py','--output-dir',OUT/'focused_paging'])
    reports=list((OUT/'focused_paging').glob('*/report.json'))
    if len(reports)!=1: raise RuntimeError('ambiguous focused guest report')
    guest=json.loads(reports[0].read_text())
    assert guest['overall']=='PASS' and sorted(row['ram_mib'] for row in guest['results'])==[128,512]
    assert all(row['pass'] and row['checks'] and all(v is True for v in row['checks'].values()) for row in guest['results'])
    report['focused_guest_report']=str(reports[0])
    report['status']='PASS'
except BaseException as error:
    report['status']='FAIL'; report['error']=str(error); raise
finally:
    report['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat(); save()
