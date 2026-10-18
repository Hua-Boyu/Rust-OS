"""Task-local OFFLINE readback; not a runner or additional acceptance gate.

python -B verify_checkpoint.py EXACT_ACCEPTANCE NEW_OUTPUT
Only execute after the actual wrapper exits. RUNNING/incomplete inputs return 2
and NOT_READY (never FAIL). No builds, tests, QEMU launches or network activity.
The exact output-byte SHA256 is emitted on stdout (detached, not self-referential).
"""
import argparse
import collections
import csv
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

if sys.flags.optimize:
    raise RuntimeError('optimized Python disables legacy assertions; refused')
sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
HELPERS = {
    'test_results/phase11a2_structure_lifetime/verify_checkpoint.py': 'b64271b148a4c1b3ae660d6d12388db64ba1eabd71c0c6c900c1d27183c4dc5c',
    'test_results/phase11a2_continuation/evidence_validation.py': '50612066aae2001e9e883288df8f393239c39376cd5c25d9fc659ac5e375df36',
    'test_results/phase11a2_continuation/verify_closeout.py': 'db82bdc2928ffb46a6a6722cbf7dfc67d9df2a5e33f3d460607e9f942f4fa6be',
    'test_results/phase11a2_continuation/verify_table_access_checkpoint.py': 'b6034aacdc85ce3b24d6082f361e962ca0299a4c76fc4b06f6daff7639e6fcd5',
    'test_results/phase11/verify_checkpoint.py': '56b6921bd071baecd7b5963220561e2be30f631c81427bb6d0b2308356ab5324',
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

for relative, digest in HELPERS.items():
    require(sha(PROJECT / relative) == digest, 'historical helper drift: ' + relative)
sys.path.insert(0, str(PROJECT / 'test_results/phase11a2_continuation'))
legacy = load('generation_offline_legacy', PROJECT / next(iter(HELPERS)))

ACCEPTANCE = ROOT / 'acceptance/acceptance_20261018T103450Z_v2091tta/acceptance.json'
WRAPPER = PROJECT / 'test_results/phase11a2_continuation/generation_full_acceptance.json'
BASELINE = PROJECT / 'test_results/phase11a2_registry/run_20261018T054817_823884Z/acceptance/acceptance_20261018T054947Z_n_dqyuzm/acceptance.json'
BASELINE_SHA = '92397a24de25643054dc5d199dcafa3983494eb9e5b04f2dea0790ed91833109'
REVIEW_SHA = '18076b1a55df5db5877d90ffa103c900bb4868c1fb165de7befc9dd632dac02b'
PRE_SHA = 'e41160c3b973c5e78c270c204fdf6cd7659546fb51221b886728d31611e8aec1'
CANONICAL = ['python', '-B', 'scripts/phase6_verify.py', '--output-dir',
             'C:/Users/iamsv/Documents/Rust-OS/test_results/phase11a3_generation_ownership/acceptance']
FAMILIES = (
    ('phase11_generation_ownership', 'generation_ownership_tests', 'paging',
     'src/memory/generation_ownership_tests.rs', (
         'generation_safe_stale_lease_cannot_release_reused_frame',
         'generation_safe_double_release_of_lease_is_refused',
         'generation_safe_lease_transfer_then_release',
         'generation_safe_foreign_domain_lease_is_refused',
         'generation_safe_mapped_lease_release_is_refused_until_unmapped',
         'generation_safe_rejected_map_preserves_lease',
         'generation_safe_repeated_allocate_release_cycles_keep_state',
         'generation_safe_reset_with_live_lease_is_refused')),
    ('phase11_generation_ledger', 'generation_ledger_tests', 'frame', 'src/memory/frame.rs', (
         'generation_safe_stale_forged_lease_cannot_release_reused_frame',
         'generation_safe_double_release_by_forged_copy_is_refused',
         'generation_safe_ledger_identity_never_repeats_across_cycles',
         'generation_safe_identity_exhaustion_is_permanent_not_wrapping',
         'generation_safe_raw_free_path_clears_ledger_identity',
         'generation_safe_raw_allocated_frame_has_no_lease_release_path')),
    ('phase11_generation_boundaries', 'generation_boundary_tests', 'frame',
     'src/memory/generation_boundary_tests.rs', (
         'generation_boundary_structure_pin_refuses_matching_lease',
         'generation_boundary_reset_preserves_issuer_and_rejects_old_domain',
         'generation_boundary_exhaustion_survives_reset_without_capacity_loss',
         'generation_boundary_growth_claim_has_no_ordinary_identity',
         'generation_boundary_malformed_lease_preserves_current_owner',
         'generation_boundary_static_ledger_budget')),
)
MANDATORY = tuple('memory::' + area + '::' + module + '::' + name
                  for _, module, area, _, names in FAMILIES for name in names)

class NotReady(RuntimeError):
    pass

class Evidence:
    """Hash all bytes read and detect concurrent changes before publication."""
    def __init__(self):
        self.hashes = {}

    def raw(self, path):
        path = Path(path).resolve()
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(path not in self.hashes or self.hashes[path] == digest, 'evidence changed: ' + str(path))
        self.hashes[path] = digest
        return data

    def read(self, path):
        return json.loads(self.raw(path))

    def text(self, path):
        return self.raw(path).decode('utf-8', errors='replace')

    def stable(self):
        require(all(sha(p) == digest for p, digest in self.hashes.items()), 'readback inputs changed')


def completed(wrapper, data):
    if wrapper.get('status') == 'RUNNING' or data.get('overall') == 'RUNNING':
        raise NotReady('actual wrapper/acceptance still RUNNING; no acceptance verdict')
    if 'exit_code' not in wrapper or 'ended_utc' not in wrapper or 'gates_total' not in data:
        raise NotReady('wrapper/acceptance incomplete; no acceptance verdict')
    require(wrapper.get('status') == 'EXPECTED' and type(wrapper['exit_code']) is int and
            wrapper['exit_code'] == 0 and data.get('overall') == 'PASS', 'actual wrapper/acceptance not successful')
    start, end = (datetime.datetime.fromisoformat(wrapper[k]) for k in ('started_utc', 'ended_utc'))
    require(start.tzinfo is not None and end.tzinfo is not None and end >= start, 'completion timestamps')


def binding(wrapper, data, path, ev):
    completed(wrapper, data)
    require(path == ACCEPTANCE and wrapper.get('name') == 'generation_full_acceptance' and
            wrapper.get('command') == CANONICAL and Path(wrapper['cwd']).resolve() == PROJECT,
            'canonical argv/cwd/exact acceptance binding')
    log = WRAPPER.with_suffix('.log')
    require(Path(wrapper['log']).resolve() == log, 'actual wrapper log binding')
    require(ev.text(log).splitlines().count(f'PASS: 63/63 gates; {path}') == 1,
            'actual wrapper completion line does not bind acceptance')
    require(data.get('phase') == '11A-prerequisite' and data.get('phase11_release_ready') is False,
            'release boundary mismatch')


def test_log(text, count, ignored=0, exact=None, required=()):
    legacy.validate_test_log(text, [str(count), '0', str(ignored)], exact)
    names = re.findall(r'^test (\S+) \.\.\. ok\s*$', text, re.M)
    require(count > 0 and len(names) == len(set(names)) == count and set(required) <= set(names),
            'missing/duplicated successful test rows')
    require(len(re.findall(r'^test \S+ \.\.\. ignored(?:\b.*)?$', text, re.M)) == ignored,
            'ignored row cardinality')
    return names


def validate_gates(data, baseline, run, ev):
    require(baseline.get('overall') == 'PASS' and
            baseline['gates_total'] == baseline['gates_passed'] == len(baseline['gates']) == 60,
            'predecessor not complete 60-gate oracle')
    gates = data['gates']
    require(data.get('gates_total') == data.get('gates_passed') == len(gates) == 63, 'exact 63 gates')
    expected = collections.Counter(g['gate'] for g in baseline['gates'])
    expected.update('Phase 11A ' + key + ' prerequisite' for key, *_ in FAMILIES)
    require(collections.Counter(g['gate'] for g in gates) == expected, 'predecessor plus three gate multiset')
    fmt = {
        'kernel formatting': ['cargo', 'fmt', '--check'],
        'host formatting': ['cargo', '+nightly', 'fmt', '--manifest-path', str(PROJECT / 'tests_kernel/Cargo.toml'), '--check'],
        'RostiFS formatting': ['cargo', '+nightly', 'fmt', '--manifest-path', str(PROJECT / 'crates/rostifs/Cargo.toml'), '--check'],
    }
    logs = []
    for index, gate in enumerate(gates, 1):
        require(gate.get('status') == 'PASS' and type(gate.get('exit_code')) is int and gate['exit_code'] == 0,
                'incomplete/failed gate')
        path = legacy.confined(PROJECT / gate['log'], run)
        expected_name = f'{index:02d}_' + re.sub(r'[^a-z0-9]+', '_', gate['gate'].lower()) + '.log'
        require(path == run / expected_name, 'gate log identity/order')
        text = ev.text(path)
        if gate['gate'] in fmt:
            require(gate['command'] == fmt[gate['gate']], 'exact successful fmt command')
        else:
            require(bool(text), 'empty non-format log')
        logs.append(text)
    for key, module, area, source, names in FAMILIES:
        gate = next(g for g in gates if g['gate'] == 'Phase 11A ' + key + ' prerequisite')
        require(gate['command'] == ['cargo', '+nightly', 'test', '--manifest-path',
                str(PROJECT / 'tests_kernel/Cargo.toml'), '--lib', module + '::', '--', '--test-threads=1'],
                'generation gate argv')
        qualified = ['memory::' + area + '::' + module + '::' + name for name in names]
        declared = re.findall(r'#\[test\]\s*fn (\w+)\(', ev.text(PROJECT / source))
        if module == 'generation_ledger_tests':
            declared = [n for n in declared if n.startswith('generation_safe_')]
        require(collections.Counter(declared) == collections.Counter(names), 'actual exact source declarations')
        test_log(ev.text(PROJECT / gate['log']), len(names), exact=qualified)
        require(data['counts'].get(key) == {'pass': len(names), 'fail': 0}, 'generation count mismatch')
    require(data['counts'].get('host') == {'pass': 325, 'fail': 0}, 'canonical host total')
    host = next(g for g in gates if g['gate'] == 'host tests')
    require(host['command'] == ['cargo', '+nightly', 'test', '--manifest-path', str(PROJECT / 'tests_kernel/Cargo.toml')],
            'canonical host argv')
    test_log(ev.text(PROJECT / host['log']), 325, 2, required=MANDATORY)
    legacy.validate_lifetime_gate(data, run)
    legacy.validate_b26_gate(data, run)
    return logs


def reviews(current, ev):
    review_path, pre_path = ROOT / 'independent_source_review.json', ROOT / 'pre_acceptance.json'
    review, pre = ev.read(review_path), ev.read(pre_path)
    require(sha(review_path) == REVIEW_SHA and sha(pre_path) == PRE_SHA, 'frozen review/pre-acceptance identity')
    require(review.get('verdict') == 'BOUNDED_APPROVAL' and review.get('blockers') == [] and
            review.get('security_sensitive_blockers') == [], 'bounded source approval required')
    require(pre.get('review_sha256') == REVIEW_SHA and pre.get('review_hashes_match') is True and
            pre.get('source_snapshot') == current, 'pre-acceptance full membership/hash mismatch')
    hashes = review['reviewed_raw_sha256']
    require(len(hashes) == 11, 'reviewed file cardinality')
    all_hashes = {**hashes, **review['supplemental_context_raw_sha256']}
    for relative, digest in all_hashes.items():
        path = legacy.confined(PROJECT / relative, PROJECT)
        require(sha(path) == digest, 'independent raw reviewed byte drift: ' + relative)
        ev.raw(path)
        if relative.startswith(('src/', 'scripts/', 'tests_kernel/')):
            require(current.get(relative) == digest, 'review outside frozen source membership')
    return {'sha256': REVIEW_SHA, 'verdict': 'BOUNDED_APPROVAL', 'reviewed_raw_sha256': hashes,
            'supplemental_context_raw_sha256': review['supplemental_context_raw_sha256']}


def broad_candidate(ev):
    candidate = ev.read(ROOT / 'candidate_checks.json')
    require(candidate.get('status') == 'PASS', 'candidate checks incomplete')
    for crate, count, ignored in [('tests_kernel', 325, 2), ('tests_b26', 98, 0)]:
        for mode in ('parallel', 'serial'):
            name = 'generation_candidate_' + crate + '_' + mode
            row = ev.read(ROOT / (name + '.json'))
            require([r for r in candidate['steps'] if r.get('name') == name] == [row], 'candidate wrapper equality')
            completed(row, {'overall': 'PASS', 'gates_total': 0})
            expected = ['cargo', '+nightly', 'test', '--manifest-path', str(PROJECT / crate / 'Cargo.toml'), '--lib']
            if mode == 'serial':
                expected += ['--', '--test-threads=1']
            require(row['command'] == expected and Path(row['cwd']).resolve() == Path('C:/Users/iamsv'),
                    'candidate host argv/cwd')
            log = PROJECT / 'test_results/phase11a2_continuation' / (name + '.log')
            require(Path(row['log']).resolve() == log and ev.raw(log) == ev.raw(ROOT / log.name), 'candidate log identity')
            test_log(ev.text(log), count, ignored, required=MANDATORY)
            require(row['totals'] == [[str(count), '0', str(ignored)]], 'candidate declared totals')
    return candidate


def report_shape(path, run):
    parts = list(path.relative_to(run).parts)
    if parts[0] != 'b13_qemu':
        parts[1] = '<invocation>'
    return '/'.join(parts)


def nested(data, baseline, run, runner, ev):
    reports = sorted(run.rglob('report.json'))
    old_reports = sorted(BASELINE.parent.rglob('report.json'))
    require(len(reports) == len(old_reports) == 159 and
            collections.Counter(report_shape(p, run) for p in reports) ==
            collections.Counter(report_shape(p, BASELINE.parent) for p in old_reports), 'complete nested report membership')
    loaded = {p: ev.read(p) for p in reports}
    b13 = run / 'b13_qemu'
    names = ('fixture_128', 'fixture_512', 'production_128', 'production_512')
    special = {b13 / 'report.json'} | {b13 / n / 'report.json' for n in names}
    legacy.validate_b13(loaded[b13 / 'report.json'], {n: loaded[b13 / n / 'report.json'] for n in names})
    host = ev.read(run / 'b13_host.json')
    require(host.get('status') == 'PASS' and type(host.get('tests_run')) is int and
            host['tests_run'] >= 3 and host.get('failures') == [] and
            data['counts']['b13_host'] == {'pass': host['tests_run'], 'fail': 0}, 'B13 unusual host schema')
    cleanup = []
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('cleanup', 'owned_qemu_exited'):
                    require(child is True, 'false cleanup assertion')
                    cleanup.append(key)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for p, report in loaded.items():
        if p not in special:
            rows = runner.evidence_rows(report, p)
            key = str(p.relative_to(run))
            expected = {'pass': len(rows), 'fail': 0}
            if 'checks' in report:
                expected['commands'] = report.get('command_count')
            require(data['counts'].get(key) == expected, 'nested canonical counts mismatch: ' + key)
        visit(report)
    require(data['counts'].get('b13_qemu') == {'pass': 4, 'fail': 0}, 'B13 exact four configurations')
    require(len(cleanup) == 280, 'cleanup assertion cardinality (not distinct guests)')
    def one(area):
        paths = list((run / area).glob('*/report.json'))
        require(len(paths) == 1, 'missing/ambiguous mandatory aggregate: ' + area)
        return paths[0], loaded[paths[0]]
    for area, count in [('read_fault', 2), ('write_fault', 2), ('paging', 20), ('iso_paging', 2)] + [
            (f'{kind}_{boot}_{ram}', count) for boot in ('elf', 'iso') for ram in (128, 512)
            for kind, count in [('fs', 103), ('block', 98), ('rostifs', 168)]]:
        p, report = one(area)
        require(len(runner.evidence_rows(report, p)) == count, 'mandatory aggregate exact rows: ' + area)
        if area in ('read_fault', 'write_fault', 'paging', 'iso_paging'):
            expected = {(ram, i) for ram in (128, 512) for i in range(1, (10 if area == 'paging' else 1) + 1)}
            rows = report['results']
            require(collections.Counter((r['ram_mib'], r['iteration']) for r in rows) == collections.Counter(expected)
                    and report['fault_build'] is (area in ('read_fault', 'write_fault')) and
                    all(r.get('checks') and all(v is True for v in r['checks'].values()) for r in rows),
                    'complete paging/fault RAM/repeat matrix')
            for row in rows:
                serial = legacy.confined(PROJECT / row['serial'], p.parent)
                require(bool(ev.raw(serial)), 'empty paging serial evidence')
    p, matrix = one('phase10')
    runner.phase10_evidence(matrix, p)
    require(matrix['scenario_count'] == matrix['expected_scenarios'] == 56 and
            matrix['check_count'] == matrix['pass_count'] == 3379, 'Phase10 full matrix totals')
    p, metadata = one('boot_metadata')
    fixtures = ('nomodule', 'invalidmagic', 'null', 'headerbad', 'mmaptruncated', 'modulein-growth',
                'module-overlap', 'countedoverflow', 'validmodule', 'reservedgrowth', 'frameexhaustion')
    expected = {(boot, ram, fixture) for boot in ('elf', 'iso') for ram in (128, 512) for fixture in fixtures}
    scenarios = metadata['scenarios']
    require(metadata['scenario_count'] == metadata['expected_scenarios'] == len(scenarios) == 44 and
            collections.Counter((s['boot'], s['ram_mib'], s['name']) for s in scenarios) == collections.Counter(expected),
            'complete boot metadata matrix')
    for scenario in scenarios:
        child = p.parent / f"{scenario['boot']}_{scenario['ram_mib']}_{scenario['name']}" / 'report.json'
        require(scenario['overall'] == 'PASS' and Path(scenario['report']).resolve() == child and child in loaded,
                'metadata invocation-owned child')
    for ram in (128, 512):
        rows = list(csv.DictReader(ev.text(run / f'boot_{ram}/boot_results.csv').splitlines()))
        require(len(rows) == 10 and all(row.get('status') == 'PASS' for row in rows), 'ten-boot matrix')
    return {'nested_report_cardinality': len(reports), 'cleanup_true_assertions': len(cleanup),
            'phase10_scenarios': 56, 'phase10_checks': 3379, 'boot_metadata_scenarios': 44,
            'limitation': 'Nested reports and duplicated cleanup assertions are NOT distinct guests or complete process history.'}


def artifacts(data, baseline, candidate, ev):
    helper = load('generation_offline_iso', PROJECT / 'test_results/phase11/verify_checkpoint.py')
    # Record raw package implementation dependencies as well as pinned local helpers.
    import pycdlib
    package = Path(pycdlib.__file__).parent
    dependencies = {str(p): sha(p) for p in package.rglob('*') if p.is_file() and p.suffix in ('.py', '.pyd')}
    for p in dependencies:
        ev.raw(Path(p))
    for record in (data['iso'], baseline['iso'], data['rollback_iso']):
        path = legacy.confined(PROJECT / record['path'], PROJECT / 'dist')
        require(sha(path) == record['sha256'], 'ISO/rollback media hash')
        ev.raw(path)
        if 'bytes' in record:
            require(type(record['bytes']) is int and path.stat().st_size == record['bytes'], 'ISO size')
    iso, old, rollback = (PROJECT / record['path'] for record in (data['iso'], baseline['iso'], data['rollback_iso']))
    kernel = helper.extract(iso, '/boot/rosti.bin')
    digest = hashlib.sha256(kernel).hexdigest()
    require(digest == data['iso']['kernel_sha256'] == candidate['kernel_sha256'] == sha(PROJECT / 'target/target/debug/kernel'),
            'production ISO/kernel/candidate identity')
    ev.raw(PROJECT / 'target/target/debug/kernel')
    require(sha(PROJECT / 'dist/rosti.iso') == data['iso']['sha256'], 'production media/versioned ISO identity')
    ev.raw(PROJECT / 'dist/rosti.iso')
    fixture = data['phase10_fixture_kernel']
    fixture_path = legacy.confined(PROJECT / fixture['path'], PROJECT / 'dist')
    require(sha(fixture_path) == fixture['sha256'] and fixture['sha256'] != digest, 'feature-distinct fixture kernel hash')
    ev.raw(fixture_path)
    archive = helper.extract(iso, '/boot/system.cpio')
    require(archive == helper.extract(old, '/boot/system.cpio') == helper.extract(rollback, '/boot/system.cpio'),
            'predecessor/rollback archive identity')
    require(hashlib.sha256(helper.extract(old, '/boot/rosti.bin')).hexdigest() == baseline['iso']['kernel_sha256'],
            'predecessor extracted kernel hash')
    return {'iso': data['iso'], 'rollback_iso': data['rollback_iso'], 'kernel_sha256': digest,
            'archive_sha256': hashlib.sha256(archive).hexdigest(), 'pycdlib_raw_sha256': dependencies}


def write_report(output, result):
    raw = (json.dumps(result, indent=2) + '\n').encode('utf-8')
    with output.open('xb') as stream:
        stream.write(raw)
    digest = sha(output)
    require(digest == hashlib.sha256(raw).hexdigest(), 'output byte readback mismatch')
    print(json.dumps({'overall': result['overall'], 'output': str(output), 'output_raw_sha256': digest,
                      'error': result.get('error')}, indent=2))
    return digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acceptance', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    path, output = args.acceptance.resolve(), args.output.resolve()
    require(path == ACCEPTANCE, 'only the exact task acceptance path is supported')
    legacy.confined(output, ROOT)
    require(output.parent == ROOT and not output.exists(), 'new task-root output only; refuse overwrite')
    ev = Evidence()
    result = {'overall': 'FAIL', 'acceptance': str(path), 'offline': True, 'new_acceptance_gates': 0,
              'scope': 'Generation-safe ordinary frame release prerequisite; bounded source approval only.',
              'b19_complete': False, 'phase11_release_ready': False, 'tss_implemented': False, 'cpl3_executed': False,
              'output_hash_contract': 'Exact UTF-8 output-file SHA256 is detached on stdout; no self-referential digest.',
              'reader_raw_sha256': sha(Path(__file__)), 'helper_raw_sha256': HELPERS}
    exit_code = 1
    try:
        ev.raw(Path(__file__))
        for relative in HELPERS:
            ev.raw(PROJECT / relative)
        wrapper = ev.read(WRAPPER)
        if wrapper.get('status') == 'RUNNING' or 'exit_code' not in wrapper or 'ended_utc' not in wrapper:
            raise NotReady('actual wrapper still RUNNING/incomplete; no acceptance verdict')
        data = ev.read(path)
        binding(wrapper, data, path, ev)
        baseline = ev.read(BASELINE)
        require(sha(BASELINE) == BASELINE_SHA, 'historical predecessor oracle drift')
        current = legacy.independent_snapshot()
        require(current == data['source_sha256'], 'independently rediscovered source membership/hash drift')
        result['source_review'] = reviews(current, ev)
        runner = load('generation_offline_canonical_schema', PROJECT / 'scripts/phase6_verify.py')
        require(current == runner.source_snapshot(), 'independent discovery/runner disagreement')
        logs = validate_gates(data, baseline, path.parent, ev)
        candidate = broad_candidate(ev)
        result['nested_evidence'] = nested(data, baseline, path.parent, runner, ev)
        result['artifacts'] = artifacts(data, baseline, candidate, ev)
        crash = next(g for g in data['gates'] if g['gate'] == 'RostiFS host and crash recovery tests')
        for label, count in [('reordered pending crash cases', 2328), ('all root-sector byte-prefix tears', 4104),
                             ('rejected/torn/flush crash cases', 2639)]:
            require(re.findall(re.escape(label) + r'=(\d+)', ev.text(PROJECT / crash['log'])) == [str(count)], label)
        # Read-only local process query, never a QEMU launch; no remote actions.
        process = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
            "$ErrorActionPreference='Stop'; $p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^qemu-system' } | Select-Object ProcessId,ParentProcessId,Name); @{query_completed=$true; processes=$p} | ConvertTo-Json -Depth 3 -Compress"],
            capture_output=True, text=True, check=True, timeout=30)
        require(not process.stderr.strip(), 'QEMU process query emitted errors')
        result['local_qemu_remaining'] = legacy.decode_qemu_result(process.stdout)
        for relative, digest in HELPERS.items():
            require(sha(PROJECT / relative) == digest, 'helper changed during readback')
        require(legacy.independent_snapshot() == current == runner.source_snapshot(), 'source changed during readback')
        ev.stable()
        result.update(overall='PASS', gates_total=63, source_sha256=current, source_input_count=len(current),
                      counts=data['counts'], actual_wrapper_exit_code=wrapper['exit_code'],
                      predecessor_acceptance_sha256=BASELINE_SHA)
        exit_code = 0
    except NotReady as error:
        result.update(overall='NOT_READY', error=str(error))
        exit_code = 2
    except Exception as error:
        result['error'] = repr(error)
    result['evidence_raw_sha256'] = {str(p): digest for p, digest in sorted(ev.hashes.items())}
    write_report(output, result)
    return exit_code

if __name__ == '__main__':
    raise SystemExit(main())
