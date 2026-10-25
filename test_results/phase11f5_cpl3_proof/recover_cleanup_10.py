"""Read-only recovery snapshot for authorized F1 evidence correction."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from phase6_verify import source_snapshot

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def command(argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    return {'command': argv, 'cwd': str(ROOT), 'exit': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}

commands = [command(['git', *args]) for args in (
    ['status', '--porcelain=v1', '-uall'], ['branch', '--show-current'],
    ['rev-parse', 'HEAD'], ['log', '-6', '--oneline', '--decorate'],
    ['diff', '--check'], ['merge-base', '--is-ancestor', 'c1b28b2', 'HEAD'])]
protected = {'.gitignore', 'README.md', 'test_results/phase11f4_user_arena/FINAL_REPORT.md',
             'docs/ROSTI_INIT_ARCHITECTURE.md', 'scripts/b13_boot_fixture.py.backup'}
classification = {}
for line in commands[0]['stdout'].splitlines():
    name = line[3:]
    kind = 'PROTECTED_UNRELATED' if name in protected or name.startswith(('d1/', 'reviews/')) else 'F5_OWNED'
    classification[name] = {'class': kind, 'sha256': digest(ROOT / name) if (ROOT / name).is_file() else None}
historical = []
for path in (ROOT / 'dist').glob('phase11f1_guest_*'):
    info = path.lstat()
    historical.append({'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
                       'reparse': bool(getattr(info, 'st_file_attributes', 0) & 0x400),
                       'symlink': stat.S_ISLNK(info.st_mode), 'size': 'NOT_MEASURED'})
freeze = json.loads((ROOT / 'test_results/f5p01/full_source_freeze_09.json').read_bytes())
prior_pins = freeze['pins']
report = {'commands': commands, 'worktree': classification,
          'historical_stages': historical, 'historical_stage_count': len(historical),
          'historical_stage_logical_size': 'NOT_MEASURED (bounded directory-only inventory)',
          'initial_source': source_snapshot(),
          'previous_freeze_drift': [name for name, value in prior_pins.items() if digest(ROOT/name) != value],
          'reader_sha256': digest(ROOT/'scripts/f1_evidence.py'),
          'producer_before_sha256': digest(ROOT/'scripts/f1_retained_guest.py'),
          'logical_red': {'command': [sys.executable, '-B', 'test_results/phase11f5_cpl3_proof/test_f1_cleanup_10.py'],
                          'exit': 1, 'log': 'test_results/phase11f5_cpl3_proof/f1_cleanup_red_10.log',
                          'sha256': digest(ROOT/'test_results/phase11f5_cpl3_proof/f1_cleanup_red_10.log')},
          'process_inspection': command(['powershell.exe', '-NoProfile', '-Command',
              '$os=Get-CimInstance Win32_OperatingSystem; $os | Select-Object FreePhysicalMemory,TotalVisibleMemorySize | ConvertTo-Json; Get-CimInstance Win32_Process | Where-Object { $_.Name -match "cargo|rustc|link|qemu|python" } | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Depth 3']),
          'process_classification': 'No Cargo/rustc/link/QEMU observed at initial inspection; Hermes gateway/dashboard/serve/kernel are infrastructure; Strata inference is infrastructure; hub.py UNKNOWN, no overlapping writer established. No process killed.',
          'correction_cycle': 1, 'scope': 'F1 evidence producer and F5 task-local orchestration only; production validators read-only'}
with (Path(__file__).parent/'cleanup_recovery_10.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
print(json.dumps({'historical_stage_count':len(historical),'prior_pin_drift':report['previous_freeze_drift']}))
