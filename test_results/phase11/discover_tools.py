"""Read-only tool and baseline discovery for the Phase 11 prerequisite slice."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def run(name, command, mandatory, purpose):
    try:
        p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
        return dict(name=name, command=command, mandatory=mandatory, purpose=purpose,
                    path=shutil.which(command[0]), exit_status=p.returncode,
                    output=(p.stdout + p.stderr).strip())
    except (OSError, subprocess.TimeoutExpired) as e:
        return dict(name=name, command=command, mandatory=mandatory, purpose=purpose,
                    path=shutil.which(command[0]), exit_status=None, output=str(e))

commands = [
    ('Rust nightly', ['rustc', '+nightly', '-vV'], True, 'Production custom i686 compilation'),
    ('Cargo', ['cargo', '+nightly', '-V'], True, 'Host tests and production build'),
    ('rustfmt', ['rustfmt', '+nightly', '-V'], True, 'Rust formatting'),
    ('rustup', ['rustup', 'show', 'active-toolchain'], True, 'Resolve actual toolchain'),
    ('GNU assembler', ['wsl', 'bash', '-lc', 'command -v as; as --version'], True, 'Inspect available assembler; production uses Rust global_asm'),
    ('GNU linker', ['wsl', 'bash', '-lc', 'command -v ld; ld --version'], True, 'Inspect available linker; production uses rust-lld'),
    ('GNU GRUB', ['wsl', 'bash', '-lc', 'command -v grub-mkrescue; grub-mkrescue --version'], True, 'BIOS ISO packaging'),
    ('QEMU i386', ['C:/Program Files/qemu/qemu-system-i386.exe', '--version'], True, 'Privileged guest execution'),
    ('Python', [sys.executable, '--version'], True, 'Acceptance orchestration'),
    ('Git', ['git', '--version'], True, 'Checkpoint and diff verification'),
    ('SHA-256', ['sha256sum', '--version'], True, 'Artifact hashing; hashlib also used'),
    ('objdump', ['wsl', 'bash', '-lc', 'command -v objdump; objdump --version'], False, 'Emitted i686 instruction inspection'),
    ('readelf', ['wsl', 'bash', '-lc', 'command -v readelf; readelf --version'], False, 'ELF section and segment inspection'),
    ('GDB', ['wsl', 'bash', '-lc', 'command -v gdb; gdb --version'], False, 'Optional QEMU remote debugging'),
    ('llvm-objdump', ['llvm-objdump', '--version'], False, 'Optional alternate disassembler'),
    ('Clippy', ['cargo', '+nightly', 'clippy', '-V'], False, 'Optional Rust linting'),
    ('Miri', ['cargo', '+nightly', 'miri', '--version'], False, 'Optional host pure-code checking, not kernel execution'),
    ('Kani', ['cargo', 'kani', '--version'], False, 'Optional bounded pure-code proof, not custom target support'),
    ('cargo-fuzz', ['cargo', 'fuzz', '--version'], False, 'Optional host parser fuzzing'),
    ('process inventory', ['powershell.exe', '-NoProfile', '-Command', "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'qemu|cargo|rustc|python|codex|claude' } | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"], True, 'Read-only active worker names/PIDs; omit command lines'),
    ('local protection metadata', ['git', 'config', '--get-regexp', r'branch\..*|receive\.deny.*'], False, 'Local branch/upstream policy; remote protection not queried'),
]
rows = [run(*c) for c in commands]
report = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'tools': rows}
(OUT / 'tools.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
a = ROOT / 'test_results/phase10b/acceptance_20261016T120546Z_psboeekn/acceptance.json'
r = json.loads(a.read_text())
print('BASELINE_KEYS', list(r))
print('BASELINE_SUMMARY', json.dumps({k:v for k,v in r.items() if k not in ('gates', 'source_before', 'source_after', 'source_hashes', 'nested_reports')}, indent=2)[:12000])
print('ACCEPTANCE_SHA256', hashlib.sha256(a.read_bytes()).hexdigest())
