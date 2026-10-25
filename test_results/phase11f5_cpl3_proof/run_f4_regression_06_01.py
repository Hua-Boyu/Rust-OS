"""Run the authenticated accepted F4 runner against the live frozen candidate.

This is predecessor regression, NOT F5 canonical acceptance. All 72 gates run;
the historically failed first 48 are also reported as an exact prefix.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
ACCEPTED_RUNNER_SHA = '5f7a8800aa387ad2c4bb406ebd5051621923b1267f3827060a839daf36687f4d'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def prepare_runner(blob, out):
    """Adapt only current input inventory and the authorized specific mock bound.

    The original runner is preserved verbatim; every predecessor input must still
    occur byte-identically in the expanded live inventory. No validator changes.
    """
    import importlib.util
    original = b'gate("acceptance runner regressions", script("test_acceptance_harness.py"), timeout=900)'
    replacement = b'gate("acceptance runner regressions", script("test_acceptance_harness.py"), timeout=1049)'
    need(hashlib.sha256(blob).hexdigest() == ACCEPTED_RUNNER_SHA, 'accepted F4 runner blob mismatch')
    need(blob.count(original) == 1, 'specific predecessor mock timeout is not unique')
    derived = blob.replace(original, replacement)
    namespace = {'__file__':str(ROOT/'scripts/phase6_verify.py'), '__name__':'f4_predecessor_regression'}
    sys.path.insert(0, str(ROOT/'scripts'))
    exec(compile(derived, str(out/'derived_f4_runner.py'), 'exec'), namespace)
    spec = importlib.util.spec_from_file_location('f5_current_inventory', ROOT/'scripts/phase6_verify.py')
    current = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(current)
    predecessor = namespace['source_snapshot']()
    expanded = current.source_snapshot()
    need(predecessor and predecessor.items() <= expanded.items(), 'live inventory drops or changes predecessor pins')
    # The fixture drivers also extract this exact live function. The old runner
    # omitted task-local imported inputs; a subset cannot satisfy exact equality.
    namespace['source_snapshot'] = current.source_snapshot
    provenance = {'accepted_runner_sha256':ACCEPTED_RUNNER_SHA,
                  'derived_runner_sha256':hashlib.sha256(derived).hexdigest(),
                  'canonical_runner_sha256':hashlib.sha256((ROOT/'scripts/phase6_verify.py').read_bytes()).hexdigest(),
                  'predecessor_input_count':len(predecessor), 'expanded_input_count':len(expanded),
                  'added_input_paths':sorted(expanded.keys()-predecessor.keys()),
                  'predecessor_pins_preserved':True,
                  'only_gate_change':'acceptance runner regressions timeout900->1049 (user-authorized R2)',
                  'source_policy':'exact live expanded inventory, same as actual fixture drivers; no validator bypass'}
    return namespace, derived, provenance


def main():
    need(not sys.flags.optimize, 'optimized regression refused')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    need(args.output_dir.is_absolute() and out.is_relative_to(ROOT/'test_results') and not out.exists(), 'new absolute task output required')
    blob = subprocess.run(['git','cat-file','blob','c8b73654dd5f7f64c3c7872254b2b730ad2151f4:scripts/phase6_verify.py'], cwd=ROOT, capture_output=True, check=True).stdout
    need(hashlib.sha256(blob).hexdigest() == ACCEPTED_RUNNER_SHA, 'accepted F4 runner blob mismatch')
    out.mkdir(parents=True)
    (out/'accepted_f4_runner.py').write_bytes(blob)
    namespace, derived, provenance = prepare_runner(blob, out)
    (out/'derived_f4_runner.py').write_bytes(derived)
    (out/'runner_provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    sys.argv = [str(out/'accepted_f4_runner.py'),'--output-dir',str(out/'a')]
    code = namespace['main']()
    paths = list((out/'a').glob('*/acceptance.json'))
    need(len(paths) == 1, 'missing/ambiguous predecessor regression output')
    path = paths[0]
    result = json.loads(path.read_bytes())
    contract = json.loads((BASE/'harness_contract_01.json').read_bytes())
    expected = Counter(contract['predecessor_identities'])
    rows = result['gates']
    first48 = rows[:48]
    complete = (code == 0 and result['overall'] == 'PASS' and result['gates_passed'] == result['gates_total'] == 72
                and Counter(row['gate'] for row in rows) == expected
                and all(row['status'] == 'PASS' and row['exit_code'] == 0 for row in rows))
    record = {'schema':'rosti.f5-f4-regression.v1','overall':'PASS' if complete else 'FAIL',
              'runner_blob_sha256':ACCEPTED_RUNNER_SHA, 'runner_actual_exit':code,
              'runner_provenance':provenance,
              'acceptance_path':str(path), 'acceptance_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'first_48_attempted_prefix_passed':sum(row['status'] == 'PASS' and row['exit_code'] == 0 for row in first48),
              'first_48_attempted_prefix_total':len(first48),
              'full_predecessor_gates_passed':result['gates_passed'], 'full_predecessor_gates_total':result['gates_total'],
              'clarification':'Historical48 was an attempted prefix ending at F3, not the complete F4 contract; no gate was removed. Full72 required here; this is not canonical F5 acceptance.'}
    with (out/'regression.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps(record, indent=2))
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
