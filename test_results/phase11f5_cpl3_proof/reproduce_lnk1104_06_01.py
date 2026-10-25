"""One isolated F3 fixture BUILD-ONLY Windows path diagnostic; no guest claim."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'scripts'))
from f3_gdt_guest import green_assembly
from f3_evidence import CALL


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    need(not sys.flags.optimize, 'optimized diagnostic refused')
    out = ROOT/'test_results/f5reg/f4_regression_06/acceptance_20261024T000000Z_abcdefgh/f3_gdt_tss/f3_full_abcdefgh/minimal/f3_minimal_abcdefgh'
    need(not out.exists(), 'refuse old evidence')
    out.mkdir(parents=True)
    stage, source = out/'fixture', out/'fixture/source'
    source.mkdir(parents=True)
    record = {'scope': 'BUILD_ONLY_ENVIRONMENT_DIAGNOSIS_NOT_HARDWARE_RED_OR_FINAL_VERIFICATION',
              'overall': 'INCOMPLETE', 'competing_builds_observed': False,
              'process_scope': 'Parent-owned sole Cargo stream; scoped children prohibited builds/Cargo/QEMU.'}
    try:
        paths = set()
        for folder in ('src', 'system'):
            paths.update(p for p in (ROOT/folder).rglob('*') if p.is_file())
        for crate in (ROOT/'crates').iterdir():
            if crate.is_dir():
                paths.update(p for p in (crate/'src').rglob('*') if p.is_file())
                paths.update(p for p in (crate/'tests').rglob('*') if p.is_file())
                paths.update(p for p in (crate/'Cargo.toml', crate/'Cargo.lock', crate/'.cargo/config.toml') if p.is_file())
        paths.update(ROOT/n for n in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'))
        record['source_inputs'] = {}
        for path in sorted(paths):
            name, raw = path.relative_to(ROOT), path.read_bytes()
            record['source_inputs'][name.as_posix()] = sha(raw)
            dest = source/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        mainpath = source/'src/main.rs'
        original = mainpath.read_bytes()
        anchor = b'    // stub: enable ps2 & interrupts'
        need(original.count(anchor) == 1, 'postpaging anchor')
        assembly = green_assembly()
        changed = original.replace(anchor, CALL+anchor)+assembly
        need(changed.replace(CALL,b'',1).replace(assembly,b'',1) == original, 'stripping equality')
        mainpath.write_bytes(changed)
        record['fixture_transform'] = {'original_main_sha256':sha(original), 'injected_main_sha256':sha(changed),
            'call_sha256':sha(CALL), 'assembly_sha256':sha(assembly), 'stripping_equality':True}
        command = ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(stage/'build')]
        record.update(command=command, cwd=str(source))
        started = time.monotonic()
        with (out/'build.log').open('xb') as log:
            process = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        record.update(exit_code=process.returncode, wall_seconds=time.monotonic()-started)
        text = (out/'build.log').read_text(errors='replace')
        record['build_log_sha256'] = sha((out/'build.log').read_bytes())
        record['lnk1104_lines'] = [line for line in text.splitlines() if 'LNK1104' in line]
        operands = []
        for line in record['lnk1104_lines']:
            for value in re.findall(r"'([^']+)'", line):
                operand = Path(value)
                operands.append({'path':value,'length':len(value),'exists':operand.exists(),
                                 'bytes':operand.stat().st_size if operand.is_file() else None})
        record['failed_operands'] = operands
        record['overall'] = 'LNK1104_REPRODUCED' if record['lnk1104_lines'] else 'BUILD_PASS_NO_REPRODUCTION' if process.returncode == 0 else 'OTHER_BUILD_FAILURE'
        record['source_after_stable'] = all(sha((ROOT/n).read_bytes()) == h for n,h in record['source_inputs'].items())
    except Exception as exc:
        record['error'] = repr(exc)
    with (BASE/'continuation06_lnk1104_reproduction_01.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in record.items() if k != 'source_inputs'}, indent=2))
    return 0 if record['overall'] in ('LNK1104_REPRODUCED', 'BUILD_PASS_NO_REPRODUCTION') else 1


if __name__ == '__main__':
    raise SystemExit(main())
