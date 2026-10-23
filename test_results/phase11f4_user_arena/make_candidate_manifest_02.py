"""Bind fresh corrected candidate only after all mandatory component evidence."""
import hashlib
import json
from pathlib import Path
import sys
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot,predecessor_contract,F3_PREDECESSOR_GATES,F4_GATES
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
current=source_snapshot()
parent=json.loads((BASE/'parent_components_readback_05.json').read_bytes())
need(parent['overall']=='PASS' and parent['source_sha256']==current,'parent readback')
for p,d in parent['artifact_sha256'].items(): need(sha(p)==d,'parent artifact drift '+p)
mock=json.loads((BASE/'mock_isolated_04/report.json').read_bytes())
need(mock['overall']=='PASS' and mock['exit_code']==0 and mock['test_count']==89 and mock['elapsed_seconds']<900 and mock['source_before']==mock['source_after']==current,'fresh timing calibration')
need(sha(BASE/'mock_isolated_04/mock.log')==mock['log_sha256'],'mock log')
focused=json.loads((BASE/'commands/f4_focused_02.json').read_bytes())
need(focused['status']=='EXPECTED' and focused['exit_code']==0 and focused['summaries']==[['12','0','0']] and len(focused['passed'])==12,'focused nonzero identities')
need(sha(focused['log'])==focused['log_sha256'],'focused log drift')
need(set(focused['passed'])=={x for x in parent['tests']['host']['identities'] if 'f4_user_arena_tests::' in x},'focused exact list membership')
contract=json.loads((BASE/'terminal_contract_02.json').read_bytes())
need(contract['overall']=='PASS' and contract['source_sha256']==current,'terminal contract')
files=[ROOT/'test_results/f4p05/source_before.json',ROOT/'test_results/f4p05/report.json',ROOT/'test_results/f4p05/host_b26/report.json']
for name in ('correction_checkpoint_01.json','correction_recovery_02.py','correction_recovery_02.json','terminal_contract_02.py','terminal_contract_02.json','decisions.md','parent_components_readback_05.py','parent_components_readback_05.json','verify_components_03.py','host_matrix_01.py','run_canonical_02.py','make_candidate_manifest_02.py','mock_isolated_04.py','mock_isolated_04/report.json','mock_isolated_04/mock.log','commands/f4_focused_02.json','commands/f4_focused_02.log','commands/f4_components_05.json','commands/f4_components_05.log','reviews/candidate_review_01.json','reviews/design_review_01.json','reviews/design_review_02.json','design.md','design_revision_01_reviewed.md','operator_disposition_01.json','parent_integration_02.json','production_audit_02/report.json'):
    files.append(BASE/name)
files.append(BASE/'canonical_readback_02.py')
for folder in ('correction_red_01','correction_green_01','correction_green_02'):
    files.extend(p for p in (BASE/folder).iterdir() if p.is_file())
pred=predecessor_contract(); files.append(pred)
pins={p.relative_to(ROOT).as_posix():sha(p) for p in files}
need(pins['test_results/phase11f4_user_arena/reviews/candidate_review_01.json']=='0181d8707e0fa5ab12f4d09a3e0500d497072c5af12277f84395d390468cd50e','historical REJECT')
value={'schema':'rosti.f4-candidate-manifest.v2','status':'AWAITING_INDEPENDENT_REVIEW','source_sha256':current,'source_pin_count':len(current),'artifact_sha256':pins,'artifact_pin_count':len(pins),'component_root':'test_results/f4p05','parent_artifact_pin_count':parent['artifact_pin_count'],'source_delta':parent['source_delta'],'gate_identities':list(F3_PREDECESSOR_GATES)+list(F4_GATES),'acceptance_contract':'72 = preserved F3 70 plus reviewed F4 2; unchanged 900-second mock bound','F3_predecessor_sha256':sha(pred),'state_decision':'KEEP existing x86 byte-store asm; detailed compiler/hardware/atomic argument in decisions.md D13; unchanged Acquire observers','terminal_closure':contract['closure'],'terminal_elf_sha256':contract['elf_sha256'],'serial_protocol':contract['serial_protocol'],'timing_disposition':'Fresh isolated calibration, no reuse of historical785.812s evidence','mock_elapsed_seconds':mock['elapsed_seconds'],'limitations':['No CPL3 or F5 isolation proof','Non-PAE paging without NX/hardware W^X','Bounded terminal retention, not rollback','Historical F1 final-readback gap remains','F3 emergency static stack bound conditional on one nested NMI','Inherited F1/F3/shared serial emitted edges unchanged; strict audit scoped to F4 terminal'],'not_run':['canonical acceptance','independent final canonical readback','closeout commits']}
need(source_snapshot()==current,'source drift during candidate construction')
with (BASE/'candidate_manifest_02.json').open('x',encoding='utf8',newline='\n') as f: json.dump(value,f,indent=2); f.write('\n')
print(json.dumps({'source_count':len(current),'artifact_count':len(pins),'manifest_sha256':sha(BASE/'candidate_manifest_02.json')},indent=2))
