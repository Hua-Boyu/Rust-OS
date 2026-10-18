"""Run corrected oracle against isolated predecessor without touching live source."""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
TREE=OUT/'red_v4_predecessor'
if TREE.exists(): raise SystemExit('refuse overwrite')
for name in ('src','tests_kernel','crates','system'):
    shutil.copytree(ROOT/name,TREE/name,ignore=shutil.ignore_patterns('target','.git','__pycache__'))
old=subprocess.check_output(['git','show','dde0788:src/memory/frame.rs'],cwd=ROOT)
(TREE/'src/memory/frame.rs').write_bytes(old)
record={'scope':'Corrected oracle + unchanged predecessor frame.rs; isolated snapshot, no live source rollback',
 'frame_sha256':hashlib.sha256(old).hexdigest(),
 'oracle_sha256':hashlib.sha256((TREE/'src/memory/generation_ownership_tests.rs').read_bytes()).hexdigest()}
(OUT/'red_v4_snapshot.json').write_text(json.dumps(record,indent=2)+'\n')
wrapper=ROOT/'test_results/phase11a2_continuation/run_step.py'
argv=[sys.executable,'-B',str(wrapper),'generation_red_v4','C:/Users/iamsv','101','cargo','+nightly','test','--manifest-path',str(TREE/'tests_kernel/Cargo.toml'),'--lib','generation_ownership_tests::','--','--test-threads=1']
r=subprocess.run(argv,cwd=Path('C:/Users/iamsv'))
for suffix in ('.log','.json'):
    shutil.copyfile(wrapper.parent/('generation_red_v4'+suffix),OUT/('generation_red_v4'+suffix))
text=(OUT/'generation_red_v4.log').read_text(errors='replace')
if 'FrameLease' not in text or 'allocate_owned' not in text or 'release_frame' not in text:
    raise SystemExit('RED is not the expected missing ownership API failure')
raise SystemExit(r.returncode)
