"""Read-only recovery and raw source/protected-byte inventory; unique output."""
from pathlib import Path
import hashlib
import json
import subprocess
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'recovery_01.json'
if OUT.exists():
    raise SystemExit('refuse overwrite')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
paths = ['src/interrupt.rs', 'src/gdt.rs', 'src/boot.s', 'src/main.rs', 'src/memory/paging.rs', 'tests_kernel/src/lib.rs', 'Cargo.toml', 'scripts/phase6_verify.py', 'scripts/test_acceptance_harness.py', 'HANDOVER.md', 'NEXT_SESSION_PROMPT.md', 'docs/PHASE11_HANDOVER.md', 'docs/PHASE11_MEMORY_AUTHORITY.md']
protected = [ROOT / 'README.md', ROOT / 'docs/ROSTI_INIT_ARCHITECTURE.md', ROOT / 'scripts/b13_boot_fixture.py.backup', *sorted((ROOT / 'd1').rglob('*'))]
p = next((ROOT / 'test_results/phase11f1_retained_owner/f1_acceptance_01').glob('acceptance_*/acceptance.json'))
a = json.loads(p.read_text())
record = {'head': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'), 'status': git('status', '--short'), 'raw_sha256': {s: sha(ROOT / s) for s in paths}, 'protected_sha256': {str(p.relative_to(ROOT)): sha(p) for p in protected if p.is_file()}, 'acceptance_path': str(p), 'acceptance_sha256': sha(p), 'acceptance_overall': a['overall'], 'acceptance_gates_total': a['gates_total'], 'acceptance_gates': a['gates'], 'accepted_source_sha256': a['source_sha256'], 'note': 'No competing Cargo/rustc/QEMU/source-editing process identified in native process inventory. Multiple Hermes infrastructure runners exist; stable hashes do not establish exclusive ownership. Initial six-file hashes unchanged immediately after targeted source recovery.'}
OUT.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('acceptance_gates', 'accepted_source_sha256', 'protected_sha256')},indent=2))
