"""Fresh exact-membership host/B26 verification; Cargo CWD stays outside repo."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
F4 = ROOT/'test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p/acceptance.json'
F4_SHA = '3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4'
IGNORED = ('maintenance_measurements::measured_frame_scan_states', 'maintenance_measurements::measured_heap_capacity_loss')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def observed(text):
    passed = re.findall(r'^test (\S+) \.\.\. ok\s*$', text, re.M)
    ignored = re.findall(r'^test (\S+) \.\.\. ignored[^\r\n]*$', text, re.M)
    return passed, ignored


def verify_result(text, expected, ignored_expected):
    summaries = re.findall(r'test result:\s+ok\.\s+([1-9][0-9]*) passed;\s+0 failed;\s+(\d+) ignored', text)
    passed, ignored = observed(text)
    need(len(summaries) == 1 and tuple(map(int,summaries[0])) == (len(passed),len(ignored)), 'nonzero unique successful summary required')
    need(Counter(passed+ignored) == Counter(expected), 'exact executed/list identity membership mismatch')
    need(Counter(ignored) == Counter(ignored_expected), 'wrong ignored identities')
    return {'passed':len(passed), 'failed':0, 'ignored':len(ignored), 'passed_names':passed, 'ignored_names':ignored}


def run(output):
    need(not sys.flags.optimize, 'optimized verification refused')
    output = Path(output)
    need(output.is_absolute() and not output.exists(), 'unique absolute output required')
    output.mkdir(parents=True)
    record = {'schema':'rosti.f5-host-matrix.v1', 'overall':'FAIL', 'steps':[], 'cargo_child_cwd':str(Path.home())}
    try:
        need(sha(F4.read_bytes()) == F4_SHA, 'wrong F4 predecessor identity')
        predecessor = json.loads(F4.read_bytes())
        contract = json.loads((BASE/'harness_contract_01.json').read_bytes())
        historical = {}
        for gate, key in (('host tests','host'),('Phase 9.6 B26 host safety regressions','b26')):
            rows = [r for r in predecessor['gates'] if r['gate'] == gate]
            need(len(rows) == 1 and rows[0]['status'] == 'PASS' and rows[0]['exit_code'] == 0, 'bad predecessor host gate')
            path = ROOT/rows[0]['log']
            raw = path.read_bytes()
            passed, ignored = observed(raw.decode('utf-8',errors='replace'))
            need(passed and len(set(passed+ignored)) == len(passed+ignored), 'invalid predecessor host identities')
            historical[key] = passed+ignored
            record[key+'_predecessor'] = {'log':str(path), 'sha256':sha(raw), 'listed':len(passed+ignored)}
        f5 = contract['host_identities']
        expected = historical['host']+f5
        need(len(expected) == 394 and Counter(IGNORED) <= Counter(expected), 'unexpected full-host identity inventory')
        need(len(historical['b26']) == 149, 'unexpected inherited B26 membership')
        def command(name, args):
            row = {'name':name,'command':['cargo','+nightly','test','--manifest-path',str(ROOT/args[0]),'--lib',*args[1:]],
                   'cwd':str(Path.home()),'exit_code':None,'log':name+'.log'}
            record['steps'].append(row)
            start = time.monotonic()
            with (output/row['log']).open('xb') as log:
                proc = subprocess.run(row['command'], cwd=Path.home(), stdout=log, stderr=subprocess.STDOUT, timeout=180)
            row.update(exit_code=proc.returncode, wall_seconds=time.monotonic()-start,
                       log_sha256=sha((output/row['log']).read_bytes()))
            need(proc.returncode == 0, 'Cargo failed: '+name)
            return (output/row['log']).read_text(errors='replace'),row
        text,row = command('f5_focused', ['tests_kernel/Cargo.toml','f5_','--','--test-threads=1'])
        row['result'] = verify_result(text,f5,())
        for key,manifest,names,ignored in (('host','tests_kernel/Cargo.toml',expected,IGNORED),('b26','tests_b26/Cargo.toml',historical['b26'],())):
            for mode,tail in (('serial',['--','--test-threads=1']),('parallel',[]),('list',['--','--list'])):
                text,row = command(key+'_'+mode,[manifest,*tail])
                if mode == 'list':
                    listed = re.findall(r'^(\S+): test\s*$',text,re.M)
                    need(Counter(listed) == Counter(names), key+' exact --list membership mismatch')
                    row['result'] = {'listed':len(listed),'identities':listed}
                else:
                    row['result'] = verify_result(text,names,ignored)
        record['overall'] = 'PASS'
    except Exception as exc:
        record['error'] = repr(exc)
    with (output/'report.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(record,stream,indent=2)
        stream.write('\n')
    print(json.dumps({'overall':record['overall'],'steps':[{k:r.get(k) for k in ('name','exit_code','wall_seconds')} for r in record['steps']], 'error':record.get('error'),'report':str(output/'report.json')},indent=2))
    return 0 if record['overall'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output_dir))
