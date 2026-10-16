"""Independent read-only closeout for the bounded Phase11 permission slice.

Run only after the canonical acceptance process exits. Never builds or starts
QEMU. Extracts artifacts in memory and writes task-owned JSON evidence only.
"""
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import pycdlib

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def digest(data):
    return hashlib.sha256(data).hexdigest()

def extract(iso_path, rr_path):
    iso = pycdlib.PyCdlib()
    iso.open(str(iso_path))
    try:
        output = io.BytesIO()
        iso.get_file_from_iso_fp(output, rr_path=rr_path)
        return output.getvalue()
    finally:
        iso.close()

def sections(data):
    assert data[:6] == b'\x7fELF\x01\x01'
    shoff = struct.unpack_from('<I', data, 32)[0]
    entsize, count, names_index = struct.unpack_from('<HHH', data, 46)
    assert entsize == 40
    rows = [struct.unpack_from('<IIIIIIIIII', data, shoff + i * entsize) for i in range(count)]
    strings = rows[names_index]
    names = data[strings[4]:strings[4]+strings[5]]
    allocated = {}
    for row in rows:
        if row[2] & 2 and row[5]:
            name = names[row[0]:].split(b'\0', 1)[0].decode('ascii')
            allocated[name] = dict(address=row[3], bytes=row[5], initialized=row[1] != 8)
    return dict(sha256=digest(data), file_bytes=len(data), allocated_sections=allocated,
                allocated_bytes=sum(r['bytes'] for r in allocated.values()),
                initialized_bytes=sum(r['bytes'] for r in allocated.values() if r['initialized']),
                static_span_bytes=max(r['address']+r['bytes'] for r in allocated.values())
                                  - min(r['address'] for r in allocated.values()))

def main():
    acceptance = Path(sys.argv[1]).resolve()
    report = dict(overall='FAIL', acceptance=str(acceptance.relative_to(ROOT)),
                  scope='11A permission prerequisite and inherited regression only; not CPL3 proof',
                  phase11_release_ready=False, pycdlib_version=importlib.metadata.version('pycdlib'))
    try:
        evidence = json.loads(acceptance.read_text())
        assert evidence['overall'] == 'PASS'
        assert evidence['phase'] == '11A-prerequisite'
        assert evidence['phase11_release_ready'] is False
        assert evidence['gates_total'] == evidence['gates_passed'] == len(evidence['gates']) == 54
        assert all(g['status'] == 'PASS' and g['exit_code'] == 0 for g in evidence['gates'])
        spec = importlib.util.spec_from_file_location('acceptance', ROOT / 'scripts/phase6_verify.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        live = module.source_snapshot()
        assert live == evidence['source_sha256']
        report.update(gates_total=54, gates_passed=54, source_inputs_rediscovered=len(live),
                      source_freeze_verified=True, source_sha256=live, counts=evidence['counts'])
        counts = {}
        for memory in (128, 512):
            with (acceptance.parent / f'boot_{memory}/boot_results.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == 10 and all(r['status'] == 'PASS' for r in rows)
            counts[str(memory)] = len(rows)
        report['boot_counts'] = counts
        phase10_paths = list((acceptance.parent / 'phase10').glob('*/report.json'))
        assert len(phase10_paths) == 1
        phase10 = json.loads(phase10_paths[0].read_text())
        module.phase10_evidence(phase10, phase10_paths[0])
        report.update(phase10_scenarios=phase10['scenario_count'],
                      phase10_check_count=phase10['check_count'])
        nested = list(acceptance.parent.rglob('report.json'))
        cleanup = 0
        for p in nested:
            r = json.loads(p.read_text())
            if 'guests' in r and r.get('qemu_status') == 'PASS':
                assert len(r['guests']) == 4
            elif r.get('status') == 'PASS' and r.get('entry') in ('_start', 'b13_handoff'):
                assert r['cleanup'] is True
            else:
                module.evidence_rows(r, p)
            def visit(value):
                nonlocal cleanup
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key in ('cleanup', 'owned_qemu_exited'):
                            assert item is True, (str(p), key, item)
                            cleanup += 1
                        visit(item)
                elif isinstance(value, list):
                    for item in value:
                        visit(item)
            visit(r)
        report.update(nested_reports=len(nested), cleanup_assertions=cleanup)
        iso_path = ROOT / evidence['iso']['path']
        assert digest(iso_path.read_bytes()) == evidence['iso']['sha256']
        kernel = extract(iso_path, '/boot/rosti.bin')
        assert digest(kernel) == evidence['iso']['kernel_sha256']
        assert digest(kernel) == digest((ROOT / 'target/target/debug/kernel').read_bytes())
        system = extract(iso_path, '/boot/system.cpio')
        baseline_iso = ROOT / 'dist/rosti_phase10b_20261016T120546Z.iso'
        assert digest(baseline_iso.read_bytes()) == '117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8'
        baseline_kernel = extract(baseline_iso, '/boot/rosti.bin')
        assert digest(baseline_kernel) == 'f292cd2e406487ead05a2b9008e0cf6bf39d145b122f7ebac160ba4d1c53386f'
        assert extract(baseline_iso, '/boot/system.cpio') == system
        old, new = sections(baseline_kernel), sections(kernel)
        delta = {k: new[k]-old[k] for k in ('file_bytes', 'allocated_bytes', 'initialized_bytes', 'static_span_bytes')}
        resources = dict(baseline=old, candidate=new, delta=delta, peak_heap_bytes=None,
                         peak_stack_bytes=None, syscall_latency=None, cpl3_entry_exit_latency=None,
                         process_creation_cleanup_time=None, boot_to_shell_delta=None,
                         scope='Independent ISO extraction and SHF_ALLOC accounting, not runtime peak or timing')
        (OUT / 'resource_sections.json').write_text(json.dumps(resources, indent=2)+'\n')
        report.update(iso=evidence['iso'], independent_extracted_kernel_sha256=digest(kernel),
                      independent_extracted_system_sha256=digest(system),
                      baseline_iso_unchanged=True, resources=resources)
        # Names/PIDs only: never collect other processes' credentials/arguments.
        proc = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
            "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^qemu-system' } | Select-Object ProcessId,ParentProcessId,Name) | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30, check=True)
        remaining = json.loads(proc.stdout) if proc.stdout.strip() else []
        report['qemu_remaining'] = remaining
        assert remaining == [], remaining
        report['overall'] = 'PASS'
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        (OUT / 'final_verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256', 'counts', 'resources')}, indent=2))

if __name__ == '__main__':
    main()
