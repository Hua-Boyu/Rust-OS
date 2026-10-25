"""Disposable host-only source mutation controls; never edits live kernel source."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'test_results/f5m/m01'
IDENTITY = 'memory::paging::f5_cpl3_owner_tests::before_publication_payload_copy_exact'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot():
    files = list((ROOT / 'src').rglob('*.rs')) + list((ROOT / 'tests_kernel/src').rglob('*.rs'))
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'disposable host-only mutation controls, no CPL3/QEMU',
              'source_before': snapshot(), 'rows': [], 'overall': 'FAIL'}
    try:
        for variant in ['baseline', 'omitted_copy', 'early_pde']:
            stage = OUT / variant
            stage.mkdir()
            for directory in ['src', 'tests_kernel', 'crates/rostifs']:
                shutil.copytree(ROOT / directory, stage / directory,
                                ignore=shutil.ignore_patterns('target', '__pycache__', '.git'))
            arena = stage / 'src/memory/user_arena.rs'
            raw = arena.read_bytes()
            if variant == 'omitted_copy':
                anchor = b'if image == Image::F5 {'
                if raw.count(anchor) != 1:
                    raise RuntimeError('omitted-copy mutation anchor')
                arena.write_bytes(raw.replace(anchor, b'if false {', 1))
            elif variant == 'early_pde':
                anchor = b'    if !initialize_owned_pages(code, stack, image) {'
                if raw.count(anchor) != 1:
                    raise RuntimeError('early-PDE mutation anchor')
                arena.write_bytes(raw.replace(anchor,
                    b'    store(pm.directory, 256, table as u32 | 7);\n' + anchor, 1))
            command = ['cargo', '+nightly', 'test', '--manifest-path',
                       str(stage / 'tests_kernel/Cargo.toml'), '--lib', IDENTITY,
                       '--', '--exact', '--test-threads=1', '--nocapture']
            start = time.monotonic()
            proc = subprocess.run(command, cwd='C:/Users/iamsv', capture_output=True, timeout=600)
            (stage / 'stdout.txt').write_bytes(proc.stdout)
            (stage / 'stderr.txt').write_bytes(proc.stderr)
            text = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
            built = 'Finished `test` profile' in text and 'could not compile' not in text
            ran = 'running 1 test' in text
            valid = built and ran and (
                (variant == 'baseline' and proc.returncode == 0
                 and 'test result: ok. 1 passed; 0 failed; 0 ignored;' in text)
                or (variant != 'baseline' and proc.returncode == 101
                    and 'assertion `left == right` failed' in text
                    and 'test result: FAILED. 0 passed; 1 failed; 0 ignored;' in text))
            row = {'variant': variant, 'stage': str(stage), 'command': command,
                   'child_cwd': 'C:/Users/iamsv', 'actual_exit': proc.returncode,
                   'elapsed_seconds': time.monotonic() - start,
                   'built': built, 'executed_exact_test': ran,
                   'expected_assertion_detected': valid and variant != 'baseline',
                   'arena_sha256': digest(arena), 'verified': valid}
            report['rows'].append(row)
            print(json.dumps(row), flush=True)
            if not valid:
                raise RuntimeError('mutation control did not produce its required result: ' + variant)
        report['source_after'] = snapshot()
        if report['source_before'] != report['source_after']:
            raise RuntimeError('live source drift during mutation controls')
        report['overall'] = 'PASS'
    except Exception as exc:
        report['error'] = repr(exc)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['overall'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
