"""Task-local provenance capture; never edits source or historical evidence."""
from pathlib import Path
import datetime, hashlib, json, shutil, subprocess
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
original = Path('C:/Users/iamsv/AppData/Local/hermes/cache/delegation/subagent-summary-0-20261018_175240_935522.txt')
copy = OUT / 'review_original.txt'
if copy.exists() and copy.read_bytes() != original.read_bytes():
    raise SystemExit('refusing review replacement')
shutil.copyfile(original, copy)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(original) == sha(copy)
manifest = {
    'status': 'PARTIAL', 'recorded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'initial_head': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
    'review': {'source': str(original), 'copy': str(copy), 'bytes': copy.stat().st_size, 'sha256': sha(copy),
               'verdict_literal': 'APPROVE-WITH-CHANGES', 'scope': 'Option A design only, not implementation approval'},
    'recovery': 'Inherited frame.rs already implements lease draft, including invalid true; tail. Eight generation tests, not seven. No AGENTS.md found.',
    'model': 'gpt-6.1-sol (exposed session metadata; not switched)',
    'context_limit': 'UNKNOWN', 'compaction_mode': 'UNKNOWN', 'clef_status': 'UNAVAILABLE',
    'sole_writer': 'User confirmed earlier session stopped after sibling-write warning; no live children in this session.',
    'wrapper': {'path': 'test_results/phase11a2_continuation/run_step.py', 'schema': 'name cwd expected_exit *argv',
                'outputs': 'wrapper parent, refuses overwrite; executes argv directly; actual subprocess exit in JSON'},
    'first_edit': 'Approximately 3 minutes after first timestamped discovery; exact initial turn timestamp unavailable. First successful edit was move-only oracle repair.',
    'inherited_frame_sha256_at_recovery': sha(ROOT/'src/memory/frame.rs')
}
(OUT/'evidence_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps(manifest, indent=2))
