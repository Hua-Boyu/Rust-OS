"""F4 v3 fail-closed provenance. Read-only validators; never spawn or write."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
OUT = ROOT / 'test_results/f4acc/c03'
REVIEW_SCHEMA = 'rosti.f4-independent-candidate-review.v5'
REQUIRED_AREAS = (
    'Review independence and scope',
    'Candidate source and discovered membership',
    'Candidate artifact freeze',
    'Full parent component artifact batch',
    'Atomic state publication: Rust aliasing, compiler and x86 ordering',
    'UART helper: literal bytes, provenance and compatibility',
    'Complete emitted F4 terminal call/control closure',
    'Preserved RED and failed first correction',
    'USER arena ownership, admission, alias and isolation semantics',
    'Publication, retention and resource policy',
    'Host, B26, focused identities and model qualification',
    'F1 fresh guest preservation',
    'F2 and F3 predecessor ABI/TSS preservation',
    'F4 complete physical/hardware matrix',
    'Fresh mock calibration and fail-closed acceptance integration',
    'Artifact-only supplement scope and review03 authenticity',
    'New artifact freeze and F4-C03-B1 identity resolution',
    'Complete launcher semantics and invocation ownership',
    'Windows F3 path and unchanged timeout qualification',
)
REQUIRED_TOOLS = tuple(BASE / n for n in (
    'run_canonical_03.py', 'canonical_readback_03.py',
    'canonical_identity_readback_03.py', 'canonical_provenance_03.py'))
INSUFFICIENT_REVIEW_SHA = 'a89bf90074bfec861a5d488a06ca4590674eb747c6f56e21a7ea2b800e99832f'

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

def unoptimized():
    need(not sys.flags.optimize and not os.environ.get('PYTHONOPTIMIZE'), 'optimized execution refused')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, 'duplicate JSON key ' + k)
            result[k] = v
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)

def digest(value):
    need(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None, 'invalid SHA256')
    return value

def resolve(root, value):
    need(isinstance(value, str) and bool(value), 'missing path')
    p = Path(value)
    return (p if p.is_absolute() else root / p).resolve()

def validate_admission(review_path, review_hash, manifest_path, manifest_hash,
                       current_source, root=ROOT, required_tools=REQUIRED_TOOLS):
    """Validate all admission bytes without side effects. MOCK fixtures are not approval."""
    unoptimized()
    root = Path(root).resolve()
    rp = resolve(root, str(review_path)); mp = resolve(root, str(manifest_path))
    need(sha(rp) == digest(review_hash), 'review raw hash mismatch')
    need(review_hash != INSUFFICIENT_REVIEW_SHA, 'insufficient historical review02 refused')
    r = load(rp)
    need(r.get('schema') == REVIEW_SCHEMA and r.get('review_complete') is True, 'complete review schema required')
    need(r.get('verdict') == 'APPROVE', 'review verdict not APPROVE')
    need(r.get('blockers') == [] and type(r.get('blocker_count')) is int and r['blocker_count'] == 0, 'review blockers/contradiction')
    need(r.get('authorizes_canonical_acceptance') is True, 'review authorization missing')
    binding = r.get('candidate_manifest')
    need(isinstance(binding, dict), 'manifest binding missing')
    need(resolve(root, binding.get('path')) == mp, 'review manifest path mismatch')
    need(binding.get('sha256') == r.get('candidate_manifest_sha256') == digest(manifest_hash) == sha(mp), 'manifest raw hash mismatch')
    checks = r.get('checks')
    need(isinstance(checks, list) and bool(checks), 'complete review checks list required')
    need(all(isinstance(c, dict) and c.get('status') == 'PASS' and isinstance(c.get('area'), str) for c in checks), 'review check not PASS')
    areas = [c['area'] for c in checks]
    need(len(areas) == len(set(areas)) and set(REQUIRED_AREAS).issubset(areas), 'review check areas incomplete/duplicate')
    m = load(mp)
    need(isinstance(current_source, dict) and bool(current_source) and m.get('source_sha256') == r.get('source_sha256') == current_source, 'exact discovered source mismatch')
    need(type(m.get('source_pin_count')) is int and m['source_pin_count'] == len(current_source), 'source count mismatch')
    for p, h in current_source.items():
        need(sha(resolve(root, p)) == digest(h), 'source bytes mismatch ' + p)
    artifacts = m.get('artifact_sha256')
    need(isinstance(artifacts, dict) and bool(artifacts), 'artifact map missing')
    need(type(m.get('artifact_pin_count')) is int and m['artifact_pin_count'] == len(artifacts), 'artifact count mismatch')
    resolved = {}
    for p, h in artifacts.items():
        target = resolve(root, p)
        need(target not in resolved, 'aliased artifact pin')
        need(sha(target) == digest(h), 'candidate artifact drift ' + p)
        resolved[target] = h
    for p in required_tools:
        need(Path(p).resolve() in resolved, 'new provenance tool not frozen ' + str(p))
    return {'review': r, 'manifest': m, 'review_path': str(rp), 'review_sha256': review_hash,
            'candidate_manifest_path': str(mp), 'candidate_manifest_sha256': manifest_hash}

def validate_acceptance(a, expected_gates, source):
    need(a.get('overall') == 'PASS' and type(a.get('gates_passed')) is int and type(a.get('gates_total')) is int and a['gates_passed'] == a['gates_total'] == 72, 'canonical PASS72 required')
    gates = a.get('gates')
    need(isinstance(gates, list) and len(gates) == 72 and Counter(g.get('gate') for g in gates) == Counter(expected_gates), 'exact72 gate multiset mismatch')
    need(all(g.get('status') == 'PASS' and type(g.get('exit_code')) is int and g['exit_code'] == 0 for g in gates), 'gate status/exit mismatch')
    need(a.get('source_sha256') == source, 'acceptance source mismatch')

def validate_driver(driver_path, current_source, expected_gates, root=ROOT,
                    expected_out=OUT, required_tools=REQUIRED_TOOLS):
    unoptimized()
    root = Path(root).resolve(); out = Path(expected_out).resolve(); dp = Path(driver_path).resolve()
    need(dp == out / 'driver_result.json', 'unexpected driver output path')
    d = load(dp)
    need(d.get('schema') == 'rosti.f4-canonical-driver.v3', 'stale driver schema')
    need(d.get('status') == 'COMPLETED' and type(d.get('exit_code')) is int and d['exit_code'] == 0 and d.get('overall') == 'PASS' and d.get('source_stable') is True, 'runner actual completion/exit')
    need(d.get('cwd') == str(root) and d.get('output_path') == str(out), 'invocation cwd/output mismatch')
    interpreter = d.get('interpreter')
    need(isinstance(interpreter, str) and Path(interpreter).is_absolute() and Path(interpreter).is_file(), 'absolute interpreter required')
    need(d.get('command') == [interpreter, '-B', str(root/'scripts/phase6_verify.py'), '--output-dir', str(out)], 'canonical command mismatch')
    need(type(d.get('runner_pid')) is int and d['runner_pid'] > 0 and d.get('exit_observed_by') == 'Popen.wait', 'owned actual exit missing')
    need(d.get('source_before') == d.get('source_after') == current_source, 'driver source mismatch')
    provenance = validate_admission(d['review_path'], d['review_sha256'], d['candidate_manifest_path'], d['candidate_manifest_sha256'], current_source, root, required_tools)
    need(d.get('driver_path') == str(root/'test_results/phase11f4_user_arena/run_canonical_03.py') and d.get('driver_sha256') == sha(d['driver_path']), 'launcher identity mismatch')
    need(sha(out/'driver.log') == d.get('log_sha256'), 'driver log drift')
    paths = list(out.glob('acceptance_*/acceptance.json'))
    need(len(paths) == 1 and d.get('acceptance_paths') == [str(paths[0])] and d.get('acceptance_path') == str(paths[0]), 'invocation acceptance ownership/ambiguity')
    ap = paths[0]
    need(ap.resolve().parent.parent == out and ap.parent.name.startswith('acceptance_'), 'acceptance path escape')
    need(sha(ap) == d.get('acceptance_sha256'), 'acceptance hash mismatch')
    a = load(ap)
    validate_acceptance(a, expected_gates, current_source)
    need(d.get('gates_passed') == d.get('gates_total') == 72 and d.get('gate_multiset_exact') is True, 'driver gate totals mismatch')
    need(Counter(provenance['manifest'].get('gate_identities', [])) == Counter(expected_gates), 'manifest gate identities mismatch')
    return d, a, ap, provenance
