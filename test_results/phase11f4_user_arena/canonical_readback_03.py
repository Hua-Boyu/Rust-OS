"""Offline v3 reader. Usage: canonical_readback_03.py DRIVER_RESULT_JSON.
Preserves v2 deep validators; never launches acceptance.
"""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from canonical_provenance_03 import ROOT, BASE, OUT, sha, need, unoptimized, validate_driver

def one(pattern):
    items=list(pattern)
    need(len(items)==1,'missing/ambiguous canonical aggregate')
    return items[0]

def main(argv=None):
    unoptimized()
    args=list(sys.argv[1:] if argv is None else argv)
    need(len(args)==1,'usage: canonical_readback_03.py DRIVER_RESULT_JSON')
    import psutil
    import pycdlib
    sys.path.insert(0,str(ROOT/'scripts'))
    from phase6_verify import source_snapshot,predecessor_contract,F3_PREDECESSOR_GATES,F4_GATES,evidence_rows,phase10_evidence
    from f2_evidence import validate as validate_f2
    from f3_full_evidence import validate as validate_f3
    from f4_evidence import validate_aggregate as validate_f4
    report={'overall':'FAIL','scope':'Parent canonical artifact readback; NOT independent final review','reader_sha256':sha(__file__)}
    try:
        driver_path=Path(args[0]).resolve()
        current=source_snapshot()
        d,a,path,provenance=validate_driver(driver_path,current,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
        run=path.parent
        mpath=Path(provenance['candidate_manifest_path']); m=provenance['manifest']
        review=Path(provenance['review_path'])
        predecessor=predecessor_contract()
        need(sha(predecessor)=='2b74191d827fa477fa60433450b4618935fe1e89fab87cd49d039a1bcf9e431b','predecessor identity')
        rust_execution=[]
        for gate in a['gates']:
            need(gate['status']=='PASS' and gate['exit_code']==0,'gate status/exit')
            log=ROOT/gate['log']; need(log.is_file(),'missing gate log')
            if gate['command'][0]=='cargo' and 'test' in gate['command']:
                text=log.read_text(errors='replace')
                summaries=re.findall(r'test result: ok\. ([1-9][0-9]*) passed; 0 failed; (\d+) ignored',text)
                need(bool(summaries),'zero/missing actual Rust tests '+gate['gate'])
                rust_execution.append({'gate':gate['gate'],'summaries':summaries,'log':str(log),'sha256':sha(log)})
        specialized=set(); validators={}
        for family,folder,validator in [('f2','f2_exception',validate_f2),('f3','f3_gdt_tss',validate_f3),('f4','f4_user_arena',validate_f4)]:
            target=one((run/folder).glob('*/report.json'))
            v=validator(target,current); validators[family]=v
            need(v['pins']==a[family+'_evidence_sha256'],'canonical validator pin map '+family)
            specialized.update(Path(p) for p in v['pins'] if Path(p).name in ('report.json','guest_report.json'))
        b13dir=run/'b13_qemu'; b13path=b13dir/'report.json'; b13=json.loads(b13path.read_bytes())
        need(b13['status']==b13['qemu_status']==b13['inspection']['status']=='PASS','B13 aggregate')
        need(Counter((g['entry'],g['memory_mib']) for g in b13['guests'])==Counter((e,ram) for e in ('b13_handoff','_start') for ram in (128,512)),'B13 four identities')
        specialized.add(b13path)
        for g in b13['guests']:
            child=b13dir/f'{"fixture" if g["entry"]=="b13_handoff" else "production"}_{g["memory_mib"]}'/'report.json'
            need(g['status']=='PASS' and g['cleanup'] is True and json.loads(child.read_bytes())==g,'B13 child equality/cleanup')
            specialized.add(child)
        host=json.loads((run/'b13_host.json').read_bytes())
        need(host['status']=='PASS' and host['tests_run']==3 and host['failures']==[],'official B13 host artifact')
        for ram in (128,512):
            with (run/f'boot_{ram}'/'boot_results.csv').open(newline='') as f: rows=list(csv.DictReader(f))
            need(len(rows)==10 and all(x['status']=='PASS' for x in rows),'ten boot CSV')
        required={'read_fault':2,'write_fault':2,'paging':20,'iso_paging':2}
        for boot in ('elf','iso'):
            for ram in (128,512):
                for kind,count in [('fs',103),('block',98),('rostifs',168)]: required[f'{kind}_{boot}_{ram}']=count
        for directory,count in required.items():
            p=one((run/directory).glob('*/report.json'))
            need(len(evidence_rows(json.loads(p.read_bytes()),p))==count,'mandatory row count '+directory)
        p10=one((run/'phase10').glob('*/report.json'))
        need(len(phase10_evidence(json.loads(p10.read_bytes()),p10))==56,'Phase10 exact56')
        nested=0
        for p in run.rglob('report.json'):
            if p in specialized: continue
            evidence_rows(json.loads(p.read_bytes()),p); nested+=1
        iso_path=ROOT/a['iso']['path']
        need(sha(iso_path)==a['iso']['sha256'] and iso_path.stat().st_size==a['iso']['bytes'],'ISO identity')
        extract=BASE/'canonical_iso_kernel_03.bin'
        need(not extract.exists(),'refuse extracted kernel overwrite')
        iso=pycdlib.PyCdlib(); iso.open(str(iso_path))
        try: iso.get_file_from_iso(local_path=str(extract),iso_path='/BOOT/ROSTI.BIN;1')
        finally: iso.close()
        kernel=ROOT/'target/target/debug/kernel'
        need(sha(extract)==sha(kernel)==a['iso']['kernel_sha256']==a['f4_production_kernel_sha256']==m['terminal_elf_sha256'],'ISO exact GREEN kernel')
        graph=json.loads((BASE/'correction_green_02/closure.json').read_bytes())
        need(graph['result']=='GREEN' and graph['elf_sha256']==sha(kernel) and not graph['unresolved'] and not graph['forbidden'],'GREEN identity')
        active=[]
        for p in psutil.process_iter(['pid','name','cmdline']):
            name=(p.info.get('name') or '').lower(); args=p.info.get('cmdline') or []
            if any(x in name for x in ('qemu','cargo','rustc')) or any(str(x).endswith('phase6_verify.py') for x in args): active.append(p.info)
        need(not active,'active shared output work at final readback')
        pins={str(p):sha(p) for p in driver_path.parent.rglob('*') if p.is_file()}
        pins[str(extract)]=sha(extract); pins[str(iso_path)]=sha(iso_path); pins[str(kernel)]=sha(kernel)
        need(source_snapshot()==current,'source drift during readback')
        validate_driver(driver_path,current,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
        need(all(sha(p)==h for p,h in pins.items()),'artifact drift during readback')
        report.update(overall='PASS',acceptance_path=str(path),acceptance_sha256=sha(path),driver_path=str(driver_path),driver_sha256=sha(driver_path),source_sha256=current,source_pin_count=len(current),artifact_sha256=pins,artifact_pin_count=len(pins),candidate_review_sha256=sha(review),candidate_manifest_sha256=sha(mpath),F3_predecessor_sha256=sha(predecessor),gate_identities=[g['gate'] for g in a['gates']],rust_execution=rust_execution,scenario_counts={k:v['scenario_count'] for k,v in validators.items()},generic_nested_reports_checked=nested,iso=a['iso'],active_shared_work=active,process_qualification='Invocation-owned validators plus final global snapshot; snapshot is not a replacement for recorded exit codes.',limitations=m['limitations'])
    except Exception as exc: report['error']=repr(exc)
    with (BASE/'parent_canonical_readback_03.json').open('x',encoding='utf8',newline='\n') as f:
        json.dump(report,f,indent=2); f.write('\n')
    print(json.dumps({k:report.get(k) for k in ('overall','source_pin_count','artifact_pin_count','scenario_counts','acceptance_path','error')},indent=2))
    return 0 if report['overall']=='PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
