"""Verify local commit closure and unchanged accepted working bytes/artifacts."""
from pathlib import Path
import hashlib, importlib.util, json, subprocess, sys
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
scope=json.loads((OUT/'commit_scope.json').read_text())
head=git('rev-parse','HEAD').decode().strip()
assert git('branch','--show-current').decode().strip()=='maintenance/phase10'
assert git('rev-parse','HEAD^').decode().strip()=='dde07882be6e7a96f29b9839e0b11029f7c81e26'
committed=set(git('diff-tree','--no-commit-id','--name-only','-r','HEAD').decode().splitlines())
assert committed==set(scope['files']), {'extra':sorted(committed-set(scope['files'])),'missing':sorted(set(scope['files'])-committed)}
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
reader=load('postcommit_reader',OUT/'verify_checkpoint.py')
accepted=json.loads((OUT/'independent_final_readback.json').read_text())
execution=json.loads((OUT/'independent_final_execution.json').read_text())
assert accepted['overall']=='PASS' and execution['actual_exit_code']==0
assert sha(OUT/'independent_final_readback.json')==execution['output_raw_sha256']
current=reader.legacy.independent_snapshot()
assert current==accepted['source_sha256']
assert current==json.loads((OUT/'pre_acceptance.json').read_text())['source_snapshot']
for name,digest in accepted['source_review']['reviewed_raw_sha256'].items(): assert sha(ROOT/name)==digest
helper=load('postcommit_iso',ROOT/'test_results/phase11/verify_checkpoint.py')
iso=ROOT/accepted['artifacts']['iso']['path']
assert sha(iso)==accepted['artifacts']['iso']['sha256']
assert hashlib.sha256(helper.extract(iso,'/boot/rosti.bin')).hexdigest()==accepted['artifacts']['kernel_sha256']==sha(ROOT/'target/target/debug/kernel')
assert hashlib.sha256(helper.extract(iso,'/boot/system.cpio')).hexdigest()==accepted['artifacts']['archive_sha256']
blobs={}
for name in scope['source_files']:
    raw=(ROOT/name).read_bytes(); blob=git('show','HEAD:'+name)
    assert raw.replace(b'\r\n',b'\n')==blob.replace(b'\r\n',b'\n'), 'committed semantic byte drift: '+name
    blobs[name]={'working_sha256':hashlib.sha256(raw).hexdigest(),'commit_blob_sha256':hashlib.sha256(blob).hexdigest(),'raw_identical':raw==blob,'LF_normalized_identical':True}
assert git('show','HEAD:test_results/phase11a3_generation_ownership/review_original.txt')==(OUT/'review_original.txt').read_bytes()
status=git('status','--short').decode()
assert set(status.splitlines())=={'?? d1/','?? scripts/b13_boot_fixture.py.backup'}, status
import psutil
qemu=[{'pid':p.pid,'name':p.info['name']} for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower().startswith('qemu-system')]
assert not qemu,qemu
record={'overall':'PASS','head':head,'branch':'maintenance/phase10','initial_head':git('rev-parse','HEAD^').decode().strip(),'committed_file_count':len(committed),'source_inputs':len(current),'accepted_source_hashes_unchanged':True,'review_hashes_unchanged':True,'source_commit_blob_provenance':blobs,'review_original_commit_bytes_exact':True,'kernel_sha256':sha(ROOT/'target/target/debug/kernel'),'iso_sha256':sha(iso),'final_worktree':status,'qemu_remaining':qemu,'pushed':False,'note':'Raw working hashes are acceptance/review authority; source commit blobs may normalize CRLF only. Dynamic STATE/manifest/FINAL_REPORT stay task-local to avoid self-referential commit hashes.'}
p=OUT/'post_commit_verification.json'
if p.exists(): raise RuntimeError('refuse overwrite')
p.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
