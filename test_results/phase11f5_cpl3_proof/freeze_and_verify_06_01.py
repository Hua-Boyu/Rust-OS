"""One parent-owned, source-frozen F5 component verification stream.

No F5 canonical runner is launched here. Candidate review must follow GREEN.
"""
import argparse
import datetime
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


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def collect():
    from phase6_verify import source_snapshot
    pins = source_snapshot()
    extras = list(BASE.glob('*.py')) + list(BASE.glob('*.s')) + list(BASE.glob('*.elf'))
    extras += [BASE/name for name in ('design.md','design_inputs_03.json','entry_design_amendment_01.md','harness_contract_01.json',
        'entry_design_amendment_inputs_01.json','failure_policy_conformance_inputs_01.json','authorization_01.md',
        'design_proposal_01.md','design_proposal_02.md')]
    extras += [BASE/'reviews'/name for name in ('design_review_01.json','design_review_02.json','design_review_03.json',
        'entry_design_amendment_review_01.json','failure_policy_conformance_01.json','prerequisite_review_01.json')]
    predecessor = ROOT/'test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p/acceptance.json'
    need(sha(predecessor.read_bytes()) == '3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4', 'wrong F4 predecessor identity')
    extras.append(predecessor)
    timing = ROOT/'test_results/f5p01/timing08'
    extras += [timing/name for name in ('measure.py','R2_RATIONALE.md','recovery.json','scope_proof.json',
        'measurement.json','measurement.log','qualification.json','qualification.log',
        'qualification09.json','qualification09.log','R2_RATIONALE09.md','scope_proof09.json',
        'f4_snapshot_diagnosis.json','adapter_green09.log','measure_freeze08.py.txt')]
    previous = json.loads(predecessor.read_bytes())
    extras += [ROOT/r['log'] for r in previous['gates'] if r['gate'] in ('host tests','Phase 9.6 B26 host safety regressions')]
    for path in extras:
        need(path.is_file() and not path.is_symlink(), 'missing/symlink frozen dependency: '+str(path))
        pins[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return dict(sorted(pins.items()))


def save(path, data):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def parent_readback(output, frozen, elf):
    """Invoke unchanged real validators, never infer validity from child exits."""
    from phase6_verify import source_snapshot
    import f1_composition_10
    import f2_evidence
    import f3_full_evidence
    import f4_evidence
    import f5_cpl3_evidence
    snapshot = source_snapshot()
    need(snapshot.items() <= frozen.items(), 'parent snapshot not bound to full freeze')
    def unique(folder):
        paths = list(folder.glob('*/report.json'))
        need(len(paths) == 1, 'missing/ambiguous aggregate: '+str(folder))
        return paths[0]
    paths = {'F1':unique(output/'f1/producer'), 'F2':unique(output/'f2'),
             'F3':unique(output/'f3'), 'F4':output/'f4/report.json', 'F5':output/'f5/report.json'}
    results = {}
    results['F1'] = f1_composition_10.readback(paths['F1'],snapshot,elf)
    results['F2'] = f2_evidence.validate(paths['F2'],snapshot)
    results['F3'] = f3_full_evidence.validate(paths['F3'],snapshot)
    results['F4'] = f4_evidence.validate_aggregate(paths['F4'],snapshot)
    results['F5'] = f5_cpl3_evidence.validate_aggregate(paths['F5'],snapshot)
    need(results['F1'].get('scenarios') == 10 and results['F2'].get('scenario_count') == 8
         and results['F3'].get('scenario_count') == 18 and results['F3'].get('full_f3_acceptance') is True
         and all(results[name].get('overall') == 'PASS' and results[name].get('scenario_count') == 12 for name in ('F4','F5')),
         'parent hardware readback incomplete')
    f5_cpl3_evidence.validate_audit(output/'audit',elf,BASE/'f2_before_macro_01.elf')
    need(sha((output/'f5/production/kernel.elf').read_bytes()) == sha(elf.read_bytes()),
         'parent production/audited ELF mismatch')
    # Re-read every returned pin and all retained component bytes. Do not exempt
    # entire evidence subtrees merely because a specialized report passed.
    for result in results.values():
        need(result.get('pins'), 'empty real validator pin set')
        for name, digest in result['pins'].items():
            need(sha(Path(name).read_bytes()) == digest, 'validated artifact drift: '+str(name))
        result['pins'] = {str(path):digest for path,digest in result['pins'].items()}
    artifacts = {}
    for path in output.rglob('*'):
        info = path.lstat()
        need(not path.is_symlink() and not getattr(info,'st_file_attributes',0) & 0x400,
             'reparse/symlink component artifact')
        if path.is_file():
            artifacts[str(path)] = sha(path.read_bytes())
    need(source_snapshot() == snapshot, 'source drift during parent readback')
    return {'overall':'PASS','source_sha256':snapshot,
            'paths':{key:str(path) for key,path in paths.items()},
            'components':results,'artifact_sha256':artifacts,'artifact_count':len(artifacts)}


def run(output):
    import psutil
    from f3_full_guest import run_owned
    need(not sys.flags.optimize, 'optimized verification refused')
    output = Path(output)
    need(output.is_absolute() and output.is_relative_to(ROOT/'test_results') and not output.exists(), 'new task-owned absolute output required')
    busy = [{'pid':p.pid,'name':p.info['name']} for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower() in
            ('cargo.exe','rustc.exe','link.exe','qemu-system-i386.exe','qemu-system-x86_64.exe')]
    need(not busy, 'foreign/unknown build or QEMU; do not kill it')
    output.mkdir(parents=True)
    regression_number = 3
    while (ROOT/f'test_results/f5r/r{regression_number:02d}').exists():
        regression_number += 1
    regression_output = ROOT/f'test_results/f5r/r{regression_number:02d}'
    pins = collect()
    number = 8
    freeze_root = ROOT/'test_results/f5p01'
    freeze_root.mkdir(parents=True, exist_ok=True)
    while (freeze_root/f'full_source_freeze_{number:02d}.json').exists():
        number += 1
    manifest = freeze_root/f'full_source_freeze_{number:02d}.json'
    freeze = {'schema':'rosti.f5-source-freeze.v1', 'status':'CANDIDATE_INPUTS_NOT_ACCEPTED',
              'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
              'pins':pins,'source_count':len(pins),
              'output_configuration':{'component_root':str(output),'f4_regression_root':str(regression_output),
                                      'canonical_planned_root':str(ROOT/'test_results/f5acc/r01'),
                                      'short_output_remedy':True,'CARGO_TARGET_DIR':None,'repository':str(ROOT)}}
    save(manifest,freeze)
    report = {'schema':'rosti.f5-full-component-verification.v1','overall':'FAIL',
              'canonical_acceptance':False,'source_freeze':str(manifest),'source_freeze_sha256':sha(manifest.read_bytes()),
              'steps':[], 'prelaunch_busy_processes':busy}
    py = sys.executable
    def task(script,*args):
        return [py,'-B',str(ROOT/script),*map(str,args)]
    def step(name,command,timeout=300,cwd=ROOT):
        need(collect() == pins, 'source membership/hash drift before '+name)
        logpath = output/(name+'.log')
        row = {'name':name,'command':command,'cwd':str(cwd),'timeout_seconds':timeout,'exit_code':None,'log':str(logpath)}
        report['steps'].append(row)
        started = time.monotonic()
        with logpath.open('xb') as log:
            # run_owned fixes CWD to ROOT; host Cargo itself is launched by the
            # explicit outside-CWD host_matrix helper, never through repo config.
            need(cwd == ROOT, 'unexpected stream child CWD')
            row['exit_code'] = run_owned(command,log,timeout,row)
        row.update(wall_seconds=time.monotonic()-started,log_sha256=sha(logpath.read_bytes()))
        need(row['exit_code'] == 0, 'component nonzero exit: '+name)
        need(collect() == pins, 'source membership/hash drift after '+name)
        print('PASS '+name,flush=True)
        return logpath.read_text(errors='replace')
    try:
        need(freeze['branch'] == 'maintenance/phase10','unexpected branch')
        step('kernel_format',['cargo','+nightly','fmt','--check'])
        step('host_format',['cargo','+nightly','fmt','--manifest-path',str(ROOT/'tests_kernel/Cargo.toml'),'--check'])
        step('production_build',['cargo','+nightly','build'])
        elf = ROOT/'target/target/debug/kernel'
        report['production_elf'] = {'path':str(elf),'sha256':sha(elf.read_bytes())}
        step('elf_contract',task('scripts/validate_elf.py',elf))
        step('entry_negative_controls',task('scripts/test_f5_entry_derivation.py'))
        step('entry_derivation',task('scripts/f5_entry_derivation.py','--root',ROOT,'--manifest',manifest,'--output',output/'entry_derivation.json'))
        step('terminal_negative_controls',task('scripts/test_f5_terminal_audit.py'))
        step('terminal_audit',task('scripts/f5_terminal_audit.py','--elf',elf,'--before',BASE/'f2_before_macro_01.elf','--output-dir',output/'audit'),900)
        step('harness_controls',task('scripts/test_f5_cpl3_harness.py'),900)
        step('predecessor_adapter_controls',task('test_results/phase11f5_cpl3_proof/test_f4_regression_adapter_09.py'))
        step('f1_cleanup_controls',task('test_results/phase11f5_cpl3_proof/test_f1_cleanup_10.py'))
        step('parent_readback_controls',task('test_results/phase11f5_cpl3_proof/test_parent_readback_10.py'))
        step('host_b26',task('test_results/phase11f5_cpl3_proof/host_matrix_06_01.py','--output-dir',output/'host'),900)
        step('f1_preservation',task('test_results/phase11f5_cpl3_proof/f1_composition_10.py','--output-dir',output/'f1'),900)
        step('f2_preservation',task('scripts/f2_exception_guest.py','--output-dir',output/'f2'),900)
        step('f3_preservation_isolated_short_path',task('scripts/f3_full_guest.py','--output-dir',output/'f3'),2100)
        step('f4_preservation',task('scripts/f4_arena_guest.py','--output-dir',output/'f4'),2100)
        step('f5_matrix',task('scripts/f5_cpl3_guest.py','--output-dir',output/'f5'),900)
        # User-authorized R2: exact unchanged95 identities, measured25% margin.
        text = step('mock_timing',task('scripts/test_acceptance_harness.py','-v'),1049)
        totals = re.findall(r'Ran ([1-9][0-9]*) tests? in ([0-9.]+)s',text)
        need(len(totals) == 1 and int(totals[0][0]) == 95 and re.search(r'^OK\s*$',text,re.M), 'mock verification lacks exact95 successful suite summary')
        import ast
        from collections import Counter
        tree = ast.parse((ROOT/'scripts/test_acceptance_harness.py').read_bytes())
        expected = [f'{c.name}.{n.name}' for c in tree.body if isinstance(c,ast.ClassDef)
                    for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
        observed = re.findall(r'^test_\w+ \(__main__\.([^)]+)\) \.\.\. ok$',text,re.M)
        need(Counter(observed) == Counter(expected) and len(expected) == 95, 'mock exact identity mismatch')
        need(not re.search(r'skipped=|expected failures=|unexpected successes=',text), 'mock skips or nonordinary successes')
        report['mock_timing'] = {'test_count':int(totals[0][0]),'suite_seconds':float(totals[0][1]),
                                'wall_seconds':report['steps'][-1]['wall_seconds'],'limit_seconds':1049}
        step('full_f4_regression',task('test_results/phase11f5_cpl3_proof/run_f4_regression_06_01.py','--output-dir',regression_output),14400)
        report['predecessor_regression_root'] = str(regression_output)
        need(sha(elf.read_bytes()) == report['production_elf']['sha256'], 'production ELF drift after regression')
        need(collect() == pins, 'source drift before parent readback')
        readback = parent_readback(output,pins,elf)
        save(output/'parent_readback.json',readback)
        report['parent_readback'] = {'path':str(output/'parent_readback.json'),
                                     'sha256':sha((output/'parent_readback.json').read_bytes()),
                                     'components':['F1','F2','F3','F4','F5'],
                                     'artifact_count':readback['artifact_count']}
        need(collect() == pins, 'source drift after parent readback')
        report['overall'] = 'PASS'
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        after = collect()
        save(output/'source_after.json',after)
        report['source_before_equals_after'] = after == pins
        report['source_after_sha256'] = sha((output/'source_after.json').read_bytes())
        if after != pins:
            report['overall'] = 'FAIL'
        remaining = [{'pid':p.pid,'name':p.info['name']} for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower().startswith('qemu-system')]
        report['remaining_qemu_observed'] = remaining
        if remaining:
            report['overall'] = 'FAIL'
        save(output/'report.json',report)
    print(json.dumps({'overall':report['overall'],'error':report.get('error'),'source_freeze':str(manifest),
                      'source_count':len(pins),'steps':len(report['steps']),'report':str(output/'report.json')},indent=2),flush=True)
    return 0 if report['overall'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.output_dir.resolve()))
