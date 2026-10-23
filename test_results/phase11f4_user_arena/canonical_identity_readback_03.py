"""Supplementary v3 identities. Usage: canonical_identity_readback_03.py DRIVER_RESULT_JSON."""
from collections import Counter
import json
from pathlib import Path
import re
import sys
from canonical_provenance_03 import ROOT, BASE, sha, need, unoptimized, validate_driver

def main(argv=None):
    unoptimized()
    args=list(sys.argv[1:] if argv is None else argv)
    need(len(args)==1,'usage: canonical_identity_readback_03.py DRIVER_RESULT_JSON')
    sys.path.insert(0,str(ROOT/'scripts'))
    from phase6_verify import source_snapshot,F3_PREDECESSOR_GATES,F4_GATES
    parent=BASE/'parent_components_readback_05.json'; p=json.loads(parent.read_bytes())
    need(p['overall']=='PASS','fresh list authority')
    driver=Path(args[0]).resolve()
    current=source_snapshot()
    d,a,a_path,provenance=validate_driver(driver,current,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
    rows=[]
    for gate_name,expected in [('host tests',p['tests']['host']['identities']),('Phase 9.6 B26 host safety regressions',p['tests']['b26']['identities']),('Phase 11 F4 owned USER arena host contract',[n for n in p['tests']['host']['identities'] if 'f4_user_arena_tests::' in n])]:
        gates=[g for g in a['gates'] if g['gate']==gate_name]
        need(len(gates)==1,'gate multiplicity')
        g=gates[0]; need(g['exit_code']==0 and g['status']=='PASS','gate exit')
        log=ROOT/g['log']; text=log.read_text(errors='replace')
        passed=re.findall(r'^test (\S+) \.\.\. ok\s*$',text,re.M)
        ignored=re.findall(r'^test (\S+) \.\.\. ignored(?:,.*)?$',text,re.M)
        need(Counter(passed+ignored)==Counter(expected),'canonical identity mismatch '+gate_name)
        sums=re.findall(r'test result: ok\. ([1-9][0-9]*) passed; 0 failed; (\d+) ignored',text)
        need(len(sums)==1 and list(map(int,sums[0]))==[len(passed),len(ignored)],'canonical nonzero summary')
        rows.append({'gate':gate_name,'passed':passed,'ignored':ignored,'log':str(log),'log_sha256':sha(log)})
    validate_driver(driver,current,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
    report={'overall':'PASS','acceptance_path':str(a_path),'acceptance_sha256':sha(a_path),'component_readback_sha256':sha(parent),'reader_sha256':sha(__file__),'identity_comparisons':rows}
    with (BASE/'canonical_identity_readback_03.json').open('x',encoding='utf8',newline='\n') as f: json.dump(report,f,indent=2); f.write('\n')
    print(json.dumps({'overall':'PASS','identities':[{k:(len(v) if k in ('passed','ignored') else v) for k,v in r.items() if k in ('gate','passed','ignored')} for r in rows]},indent=2))
    
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
