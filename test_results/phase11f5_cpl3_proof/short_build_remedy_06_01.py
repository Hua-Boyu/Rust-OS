"""Bounded short Cargo output remedy for reproduced F3 LNK1104; no guests."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    original = json.loads((BASE/'continuation06_lnk1104_reproduction_01.json').read_bytes())
    need(original['overall'] == 'LNK1104_REPRODUCED', 'must reproduce first')
    source = Path(original['cwd'])
    output = ROOT/'test_results/f5r/short_build_01'
    need(not output.exists(), 'refuse output reuse')
    output.mkdir(parents=True)
    # Same copied source/build policy as the failing invocation, only output path differs.
    command = original['command'][:-1] + [str(output/'target')]
    before = {p.relative_to(source).as_posix(): sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
    record = {'schema':'rosti.f5-short-build-remedy.v1', 'scope':'ENVIRONMENT_ONLY_NOT_FINAL_GUEST_VERIFICATION',
              'overall':'FAIL', 'source_tree':str(source), 'command':command,
              'cwd':str(source), 'source_before':before, 'repository_not_relocated':str(ROOT)}
    try:
        probe = output/'permission_probe'
        with probe.open('xb') as stream:
            stream.write(b'F5 task-owned generated output permission check\n')
        record['permission_probe_sha256'] = sha(probe.read_bytes())
        started = time.monotonic()
        with (output/'build.log').open('xb') as log:
            process = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        record.update(exit_code=process.returncode, wall_seconds=time.monotonic()-started)
        after = {p.relative_to(source).as_posix(): sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
        record['source_after'] = after
        need(before == after, 'copied source input drift')
        need(process.returncode == 0, 'short output did not repair build')
        elf = output/'target/target/debug/kernel'
        record['fixture_elf'] = {'path':str(elf), 'sha256':sha(elf.read_bytes()), 'bytes':elf.stat().st_size}
        libs = list((output/'target/debug/build/version_check').glob('*/out/libversion_check-*.rlib'))
        need(len(libs) == 1, 'missing/ambiguous corresponding rlib')
        record['rlib'] = {'path':str(libs[0]),'path_length':len(str(libs[0])),'sha256':sha(libs[0].read_bytes())}
        record['failing_rlib'] = original['failed_operands'][0]
        record['failed_build_had_no_reviewed_elf_identity'] = True
        record['artifact_provenance'] = 'New fixture ELF requires fresh audit/hardware/review. No path-related hash exemption. Source tree unchanged; generated target/output path changed, possible debug metadata differences not treated as equality.'
        record['overall'] = 'BUILD_PASS_SHORT_OUTPUT'
    except Exception as exc:
        record['error'] = repr(exc)
    record['log_sha256'] = sha((output/'build.log').read_bytes()) if (output/'build.log').is_file() else None
    with (BASE/'continuation06_short_build_remedy_01.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ('source_before','source_after')}, indent=2))
    return 0 if record['overall'] == 'BUILD_PASS_SHORT_OUTPUT' else 1


if __name__ == '__main__':
    raise SystemExit(main())
