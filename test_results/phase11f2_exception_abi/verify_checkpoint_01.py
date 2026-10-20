"""Scoped newline preservation and checkpoint readback (no kernel writes)."""
from pathlib import Path
import hashlib
import json
import subprocess
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
recovery = json.loads((OUT / 'recovery_01.json').read_text())
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
row = {'status': 'RUNNING', 'source_implemented': False, 'f2_accepted': False, 'newline_preservation': []}
for name in ('HANDOVER.md', 'NEXT_SESSION_PROMPT.md', 'docs/PHASE11_HANDOVER.md', 'docs/PHASE11_MEMORY_AUTHORITY.md'):
    original = subprocess.check_output(['git', 'show', recovery['head'] + ':' + name], cwd=ROOT)
    # Git blobs may be LF even where the recovered working source was CRLF.
    path = ROOT / name
    current = path.read_bytes()
    old_heading = (b'## CURRENT F1 v2 checkpoint' if name == 'NEXT_SESSION_PROMPT.md' else b'## F1 v2 current checkpoint' if name.endswith('MEMORY_AUTHORITY.md') else b'## Current ' + '\u2014'.encode() + b' F1 v2 ACCEPTED')
    suffix = current[current.index(old_heading):]
    original_suffix = original[original.index(old_heading):]
    if suffix.replace(b'\r\n', b'\n') != original_suffix.replace(b'\r\n', b'\n'):
        raise RuntimeError('historical section drift: ' + name)
    # Recover the unchanged suffix's original working-tree convention. Prefix
    # insertion must not leave mixed line endings or bulk-normalize prior bytes.
    crlf = b'\r\n' in suffix
    normalized = current.replace(b'\r\n', b'\n')
    fixed = normalized.replace(b'\n', b'\r\n') if crlf else normalized
    path.write_bytes(fixed)
    row['newline_preservation'].append({'path': name, 'convention': 'CRLF' if crlf else 'LF', 'historical_suffix_text_unchanged': True, 'sha256': sha(fixed)})
row['production_drift'] = [p for p,h in recovery['raw_sha256'].items() if p not in {v['path'] for v in row['newline_preservation']} and sha((ROOT/p).read_bytes()) != h]
row['protected_drift'] = [p for p,h in recovery['protected_sha256'].items() if sha((ROOT/p).read_bytes()) != h]
for name in ('design_review_02.json',):
    review = json.loads((OUT/'reviews'/name).read_text())
    mismatches = [v['path'] for v in review['inputs'] if sha((ROOT/v['path']).read_bytes()) != v['sha256']]
    if mismatches:
        raise RuntimeError('reviewed input drift: '+str(mismatches))
    row['design_review'] = {'verdict': review['verdict'], 'blockers': review['blockers'], 'raw_sha256': sha((OUT/'reviews'/name).read_bytes()), 'all_input_pins_match': True}
red = json.loads((OUT/'runtime_red_02/report.json').read_text())
control = json.loads((OUT/'runtime_red_01/report.json').read_text())
row['runtime_red'] = {'status': red['status'], 'build_exit': red['build_exit'], 'qemu_exit': red['qemu_exit'], 'owned_qemu_exited': red['owned_qemu_exited'], 'failed_check': not red['checks']['kernel_data_selectors_before_call']}
row['control_pass'] = control['status'] == 'PASS' and all(control['checks'].values())
proc = subprocess.run(['powershell.exe', '-NoProfile', '-Command', 'Get-CimInstance Win32_Process | Where-Object { $_.Name -match "^qemu-system" } | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress'], capture_output=True, text=True)
row['qemu_process_readback'] = {'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
row['source_owner_limit'] = 'No observed competing writer; stable hashes and empty QEMU snapshot do not prove exclusive process ownership or historical exit status.'
row['status'] = 'PASS_PARTIAL_CHECKPOINT_NOT_F2_IMPLEMENTATION' if not row['production_drift'] and not row['protected_drift'] and row['control_pass'] and row['runtime_red']['failed_check'] and proc.returncode == 0 and not proc.stdout.strip() else 'FAIL'
path = OUT / 'checkpoint_verification_01.json'
if path.exists():
    raise SystemExit('refuse evidence overwrite')
path.write_text(json.dumps(row,indent=2)+'\n')
print(json.dumps(row,indent=2))
if row['status'] == 'FAIL':
    raise SystemExit(1)
