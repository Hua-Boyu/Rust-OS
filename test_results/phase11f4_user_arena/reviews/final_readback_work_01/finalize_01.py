"""Finish separate independent final canonical readback; exclusive verdict only."""
import pathlib,json,hashlib,sys,datetime,subprocess,re
from collections import Counter
R=pathlib.Path('C:/Users/iamsv/Documents/Rust-OS');B=R/'test_results/phase11f4_user_arena';W=B/'reviews/final_readback_work_01';sys.path[:0]=[str(B),str(R/'scripts')]
def H(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_bytes())
def check(v,m):
 if not v:raise RuntimeError(m)
def save(n,v):
 with (W/n).open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,indent=2,default=str);f.write('\n')
from phase6_verify import source_snapshot,F3_PREDECESSOR_GATES,F4_GATES
from canonical_provenance_03 import REQUIRED_AREAS,validate_driver
S=source_snapshot();M=J(B/'candidate_manifest_04.json');Q=J(B/'reviews/candidate_review_05.json');C=J(B/'parent_canonical_readback_04.json');P=J(B/'parent_components_readback_05.json');X=J(W/'extra_validation_02.json');DEEP=J(W/'deep_summary_02.json');SUP=J(W/'supplement_resolution_01.json');EX=J(W/'provenance_and_rust_01.json')
findings=[
('Review independence and scope',[
 'Separate fresh delegated Hermes/gpt-6.1-sol final-review context, distinct from the parent and candidate_review_05 author. No participation in candidate construction or canonical execution. This is actual final artifact readback, not self-promotion of candidate approval.',
 'Inspected complete retained_owner.rs and user_arena.rs, all F4 tests/B26 controls, complete relevant PageMap/mod/linker diffs, shared serial source, full new reader/provenance/launcher and evidence validators. Read every candidate05 finding including unsafe, ordering, serial and full closure findings; independently reestablished the current byte/evidence boundary.',
 'Only unique review-work scripts/JSON/disassembly and this numbered verdict were written. No production/source/harness changes, builds, Cargo, tests, QEMU, acceptance reruns, commits or edits to pre-existing artifacts.'
]),
('Candidate source and discovered membership',[
 'Rediscovered exact source membership through inspected source_snapshot rules and rehashed all187 production/build/harness/system inputs. Maps equal manifest04, review05, driver before/after, canonical acceptance and supplement. Raw retained_owner.rs is53d5f46e9d977d86f3e180aefd6c3d4385bfa5875e77cf48f9fe508917cc9fe8.',
 'Source membership includes every trusted system byte, configuration/toolchain/target/manifests/locks, portable sources, boot assembly and harness. Offline supplemental artifacts are outside this frozen membership; adding them does not alter accepted sources. Working-tree raw acceptance is not a claim of equality to HEAD blobs.'
]),
('Candidate artifact freeze',[
 'Fresh independent complete rehash: all81 manifest04 artifact pins and all28 candidate05 reviewer-evidence pins match. Exact immutable manifest04 and candidate05 raw identities are explicitly bound below. Original03 reader remains authenticated by manifest04; new04 is separately pinned/reviewed, never substituted into original admission.',
 'Final stability pass rechecks source/candidate/reviewer and canonical/component maps. No source re-freeze, repinning, stale candidate substitution or newline normalization used.'
]),
('Full parent component artifact batch',[
 'Independently rehashed all61483 component artifacts, not a selected-report subset. Current production ELF equals corrected GREEN and canonical ISO payload. Full component source copies and logs are included in those authenticated pins.',
 'Fresh independently parsed component host serial/default-parallel/list records: host380 exact identities (378 passed,2 inherited ignored), B26149 all pass; all three modes have actual exit0 and exact raw log hash/membership. Canonical raw host and B26 memberships independently match these real list authorities.'
]),
('Atomic state publication: Rust aliasing, compiler and x86 ordering',[
 'STATE remains AtomicU8 interior storage; as_ptr does not manufacture a mutable/shared non-atomic Rust reference. Fresh ELF PIC destination resolves exactly to the one-byte STATE symbol. At0x26e9d6 MOVB immediate3 stores Terminal before serial selection/call.',
 'Default asm read/write memory effects prohibit compiler reordering across publication; x86 normal-memory byte-store atomicity/store ordering and the admitted one-vCPU CPL0/IF0/no owner reentry profile support the retained target-specific argument. preserves_flags/nostack are consistent with this MOV. Acquire observers unchanged.',
 'Not an SMP or portable Rust-memory-model proof, not permission for racing non-atomic/mixed-width observers or MMIO state storage.'
]),
('UART helper: literal bytes, provenance and compatibility',[
 'Compared entire private fixed-array asm helper with shared serial::putc/puts: byte COM1 THR0x3f8, LSR0x3fd, THRE0x20,100000 polls per byte, send only on readiness and drop-current-byte on timeout preserved. Shared serial source is byte-identical to F3 predecessor.',
 'Independent raw PT_LOAD reads at actual PIC-selected addresses establish both exact34-byte PASS/FAIL LF literals. Static typed [u8;34] provenance and loop progression permit indices0..33 only; one-past is never read. inout scratch registers cannot overlap early EAX/ECX/EDX outputs; emitted ESI/EDI distinct, callee-saved registers restored, flags declared clobbered.',
 'At most3400000 INs and34 OUTs. Finite iteration bound is not a wall-clock UART guarantee. Full ready logs may include preceding boot output; marker length is not log length.'
]),
('Complete emitted F4 terminal call/control closure',[
 'Fresh real LLVM objdump discovered through f3_full_guest.discover_objdump decoded210970 instructions from actual target ELF. Independently inspected all instructions in four reachable blocks and all11 edges, including both literal arms, calls, branches, symbol fallthrough and PIC call-next/pop.',
 'Fresh graph exact instruction equality with retained GREEN: f4_terminal, AtomicU8::as_ptr, f4_terminal_serial and f4_arena_terminal; zero forbidden/zero unresolved/zero indirect dispatch. No panic/unwind/format/VGA/mutex/allocation edge. Helper RETs are balanced; root never returns. Terminal bytes FA F4 EB FC are CLI/HLT/JMP.',
 'Source asm clobbers match actual code. Emitted terminal additional stack44 bytes excludes callers, IRQ/NMI and exception high-water. Strict closure approval is F4-terminal-scoped, not a global F1/F2/F3 fatal-path cleanup claim.'
]),
('Preserved RED and failed first correction',[
 'Original REJECT01, original emitted RED and failed first serial correction are retained by authenticated candidate/component/reviewer pins, not rewritten. Candidate05 complete analysis establishes why deleting atomic dispatch alone did not remove iterator/pointer panic paths.',
 'Current fresh complete terminal graph eliminates those dependencies only in exact corrected ELF db361522ac20f8d46bd033958aac5747b1fe0e61aaad13350247e50b3f3ba892. Static forbidden reachability in earlier ELFs is not fabricated evidence of an actual runtime panic.'
]),
('USER arena ownership, admission, alias and isolation semantics',[
 'Read complete admission and installation. Dedicated PDE256 spans0x40000000..0x40400000; PDE257 absent. Code/RO data first page P/U/RO, stack0x403ff000 P/U/RW, guard0x403fe000 and all1022 other leaves absent. Effective permissions intersect PDE/PTE, not leaf-only.',
 'Preflight validates live same-domain distinct leases, retained paging structures/role pins, raw/private inventory agreement, present writable supervisor identity accessibility, boot/kernel/privileged exclusion and absence of unexpected USER leaves. Existing map/unmap APIs reserve the entire arena and ordinary mapping never gains USER authority.',
 'Fresh F4 validator reconstructs complete repeated physical directories/tables, allocator ids/domain/role bitmaps, owner leases, payload pages and descriptor/TSS/IDT identities from raw evidence. No broad inherited supervisor promotion. Ring0 code-write PF/error3, stack positive read/write and guard/hole PF/error0 are real captured CPU controls, not CPL3 proof.',
 'Shared non-PAE CR3 has no NX; executable stack and supervisor writable aliases remain. No hardware W^X, user instruction-fetch proof, general isolation or F5 authorization.'
]),
('Publication, retention and resource policy',[
 'Complete scalar/range/accounting/accessibility preflight dominates initialization/pin writes. All leases enter permanent owner slots first; new stack/table expand inherited10 to12 retained frames. Owner->PAGE_MAP->FRAME_ALLOC order remains; guards end before GDT installation/terminal output.',
 'Code/stack initialization and table zeroing precede role/registry pins, both staged leaves, trusted inventory/accounting, Release compiler fence, volatile PDE-last store and INVLPGs. Raw pre/publish/ready captures independently establish owner authority with PDE absent before commit.',
 'Failure terminally retains bounded10/11/12 prefix, not rollback/restoration; postpublication refusal retains mapping and halts. Joint seal prevents mutation/release/retry/alternate CR3. Current profile remains one-shot, single-vCPU, CPL0/IF0; no unseal/reset/teardown added.',
 'Fresh target DWARF/symbols corroborate owner+latch+manifest485<=4096 and descriptor272<=4096. Twelve frames49152 bytes includes8192 USER payload and4096 table. No resource ceiling raised; cumulative heap/caller/IRQ/NMI high-water unknown.'
]),
('Host, B26, focused identities and model qualification',[
 'Canonical host378+2 ignored/list380 and B26149 exact membership freshly matched raw logs. Every tests_kernel filtered canonical Rust gate equals its exact selection from the independently captured host list, including F1 host9. Every Rust-test gate has actual exit0 and nonzero passed summaries reconciled to emitted names.',
 'Focused F4 exact12 names match real Rust #[test] declarations and F4_HOST_REQUIRED, B26 exact149 match B26_REQUIRED; portable test log names match real source functions. No zero-filter success accepted.',
 'Read complete focused/B26 bodies: isolated exact-one subprocess success required; refusal snapshots include ledgers/bitmaps/all mirror words/metadata/capacities. Foreign/stale/duplicate/reserved/role/accessibility/directory/range/accounting failures and effective permissions, bounded-prefix/seal/CR3 controls exercise real code.',
 'B26 preseed occurs outside guards, transfers into actual global owners, observes all layouts for zero allocations/deallocations and unchanged mirror backing on success/refusal. These are host-model controls, not physical CPU measurements.'
]),
('F1 fresh guest preservation',[
 'Corrected supplied expectation using actual source and aggregate: canonical boot_metadata has exactly44 standard metadata scenarios, NOT F1 retained-owner guests. The approved72 contract invokes no --f1 hardware path; it preserves exact F1 HOST9. No new canonical F1guest10 is claimed.',
 'Reusable current-source-bound component test_results/f4p05/f1/f1_retained_xj8h0cpm/report.json has exact cases0..4 x128/512=10 and142 stopped checkpoints, independently checked source/map, child paths, schedules, paused complete stable CPL0 captures, actual owned QEMU exit1 and cleanup. All artifacts freshly rehashed in full component map.',
 'Legacy full F1 validator was attempted read-only and correctly refused missing stage_removed: component deliberately records retained stage. Preserved the failed own reader attempt, then independently performed only the approved bounded-preservation checks. Historical F1 final-readback gap and retained-stage limitation remain; neither is waived or called closed.'
]),
('F2 and F3 predecessor ABI/TSS preservation',[
 'Fresh canonical specialized validators: F2 ud/de/gp/pf x128/512=8; full F3 exact18; source/fixture/ELF, actual command/RAM/mode/output ownership and cleanup checked. Returned pin maps exactly equal canonical acceptance maps (10 F2,1078 F3).',
 'Independently reconstructed all eight canonical68-byte17-u32 frames from raw binaries and register packets: vector/error, original GPR/selectors, EIP/CS, RF-adjusted EFLAGS, DF/IF normalization and same-CPL pushad/ESP geometry agree; terminal HLT evidence retained.',
 'Exception ABI/entry/fatal, GDT/TSS, F3 asm/privileged/shared serial source hashes equal authenticated F3 predecessor. F3 conditional one-nested-NMI stack bound remains conditional; general stack high-water/physical CPU/NMI task-switch proof not promoted.'
]),
('F4 complete physical/hardware matrix',[
 'Fresh canonical f4_evidence.validate_aggregate execution revalidated exact ready/code_write/lower_guard/unused_hole/occupied_refusal/capacity_refusal x128/512=12 and all12757 helper-returned pins; complete source transforms/stripping equality, actual DWARF layouts/symbols, variant ELF, frozen emulator/firmware and exact QEMU flags/operands/serial/output paths checked.',
 'Validated transport logs and ordered execute breakpoints, stopped register/hardware repeat captures, full physical page inventory and QMP origins, owner/allocator authority before PDE publication, staged leaves, unchanged supervisor state except CPU A/D, retained terminal leases and measured12-frame capacity delta.',
 'Code-write positive USER stack store/read0x5a17c0de then exact PF CR2=0x40000000/error3; guard/hole errors0 and exact instruction/frame evidence. Occupied refusal count0 and deterministic capacity refusal retained10 are distinguished from physical OOM. Only declared EIP fixture redirects permitted.',
 'All children have nonempty all-true checks, actual owned cleanup/exit records and HLT; no shell return, CPL3, double/triple fault promotion. This remains Ring0 bounded prerequisite evidence.'
]),
('Fresh mock calibration and fail-closed acceptance integration',[
 'Actual canonical PASS72/72 and exact multiset70 predecessor+2F4 verified independently against authenticated predecessor JSON. All72 gate statuses PASS and exact integer actual exit0; every log is invocation-owned/pinned and all Rust executions nonzero.',
 'Canonical acceptance-runner regression log derived from actual gate record (29_acceptance_runner_regressions.log):89 success dots, Ran89 in802.654s/OK, actual exit0 under unchanged900. Nonverbose canonical log does not enumerate names; frozen script AST has89 and source-identical isolated verbose calibration independently matches all89 names.',
 'Isolated604.056 suite/604.421 wall remains calibration, not canonical timing. Preserved own extra01 assertion failure caused by wrongly expecting verbose canonical names; no raw log rewritten, output synthesized, timeout increased or expensive tests rerun.',
 'Integration source/provenance preserve missing/failed/ambiguous/late-drift refusal and exact specialized pin maps. Mock89 is not72 real acceptance gates; no CPL3 inference.'
]),
('Artifact-only supplement scope and review03 authenticity',[
 'Original candidate/design historical verdicts retained by exact raw identities. Candidate02 narrow APPROVE never authorizes this run. Review03 REJECT on manifest02 drift and review04 REJECT remain truthful history; candidate05 genuine complete APPROVE binds manifest04 and current source.',
 'New ISO-reader supplement is postcanonical offline tooling only: exact original03 bytes/failure/empty output remain, new04 bytes/results independently reviewed and bound separately. No production/canonical source, runner, harness, design or gate contract changed; no rerun performed.'
]),
('New artifact freeze and F4-C03-B1 identity resolution',[
 'Fresh validate_driver/admission authenticates original manifest04 and genuine complete review05, all required unique PASS areas, raw path/hash bindings, source discovery, original frozen tools/artifacts, strict zero blockers and explicit canonical authorization. Historical insufficient review02 is excluded.',
 'No replacement review pin or self-authored candidate approval used. The new04 reader keeps the same validate_driver and original03 admission pins; independent supplement acceptance here covers only its exact additional bytes. F4-C03-B1 remains historical for manifest02, not repinned out of history.'
]),
('Complete launcher semantics and invocation ownership',[
 'Inspected complete exclusive-output launcher and shared validator. Driver_result schema v3 COMPLETED, actual captured PID32356/Popen.wait exit0, root CWD, absolute existing interpreter and exact -B scripts/phase6_verify.py --output-dir test_results/f4acc/c03 command verified. One unique acceptance path, no ambiguity/reuse; log/launcher/review/manifest/acceptance hashes and source before/after/current all match.',
 'Observed execution evidence is retained driver wait record; parent additionally reported managed launcher proc_a22e11d0780d exited0 notification/log. This reviewer did not poll, duplicate, kill or rerun the launcher. Outer managed-log report is supplied provenance, not a newly observed process handle.',
 'Deep independent readback includes official b13_host.json PASS3/no failures; B13 four exact children/aggregate equality/cleanup; ten successful CSV rows at each RAM; mandatory fault/paging and ELF/ISO FS103/block98/RostiFS168 rows at both RAMs; Phase10 exact56 invocation-owned children; metadata44 exact matrix;154 generic nested reports with explicit nonempty all-true checks.',
 'Generic154 is report cardinality, not154 distinct guests or complete historical process proof. Final empty shared-process snapshot is separate from recorded invocation-owned exits.'
]),
('Windows F3 path and unchanged timeout qualification',[
 'Actual completed canonical F3 full18 matrix proves short c03 output path worked without MAX_PATH workaround changes or timeout/resource relaxation. The prior path failure history and isolated timing evidence remain distinct.',
 'Independently rehashed protected README/.gitignore/init-architecture/backup and captured d1/f. No protected path, Git index/config or worktree source normalized/edited. HEAD/branch remain d81672c4b314f0388e10e4c8dc9466b35ea89ce7/maintenance/phase10.',
 'git_source_identity_01 remains untouched: inherited newline-only HEAD/raw differences are not a waiver for future staged mismatches. Prospective command-scoped core.autocrlf=false must be followed by actual all14 F4 raw staged-blob comparisons; this review does not assert unseen staging/commits/docs complete.'
]),
('Independent ISO namespace supplement resolution',[
 'Exact byte-delta validation permits only docstring/usage and exclusive04 output names plus iso_path=/BOOT/ROSTI.BIN;1 -> rr_path=/boot/rosti.bin. Every deep/provenance/source/stability check remains byte-identical. No check weakened; both readers main were NOT rerun.',
 'Independently exercised real pycdlib extraction entirely in memory on accepted ISO. Original uppercase ISO9660 selector reproduces Could not find path; actual lowercase ISO9660 /boot/rosti.bin;1 and Rock Ridge /boot/rosti.bin both extract byte-identical6575756-byte ELF matching target/correctedGREEN/manifest/canonical kernel hashes.',
 'Verified11700224-byte ISO raw2ceb19010a4cb52c224600db755e666de87d3c67aea7db41575a1d3c324f7c84, all13 supplement artifact pins, original03 failure/zero-length extraction, revised04 actual recorded PASS and all19149 parent canonical pins freshly rehashed. Original failure is a reader-namespace defect, not canonical/kernel failure.',
 'RESOLVED and independently ACCEPTED for this exact supplement b4d0579ca7841e3d1847d506b8beae4d1af51d69bceacd934c28f066aff18e3d. This file supplies requested independent resolution without editing its immutable AWAITING status or claiming retroactive original03 success.'
])]
check(set(REQUIRED_AREAS)<=set(a for a,b in findings),'all mandatory areas');check(len(findings)==len(set(a for a,b in findings)),'duplicate areas')
checks=[{'area':area,'status':'PASS','findings':text} for area,text in findings]
save('progress_04.json',{'verdict_pending_final_stability':'APPROVE','checks':checks,'blocker_count':0,'blockers':[]})
# Final complete stability pass, not just previously copied summary claims.
counts={}
for label,pins in [('source',S),('candidate_artifacts',M['artifact_sha256']),('candidate_reviewer_evidence',Q['evidence_sha256']),('canonical_artifacts',C['artifact_sha256']),('component_artifacts',P['artifact_sha256'])]:
 bad=[]
 for name,digest in pins.items():
  p=pathlib.Path(name);p=p if p.is_absolute() else R/p
  if H(p)!=digest:bad.append(str(p))
 check(not bad,'final '+label+' drift '+repr(bad));counts[label]={'count':len(pins),'mismatches':bad}
check(source_snapshot()==S==M['source_sha256'],'final discovered source')
D,A,AP,provenance=validate_driver(R/'test_results/f4acc/c03/driver_result.json',S,list(F3_PREDECESSOR_GATES)+list(F4_GATES))
head=subprocess.run(['git','rev-parse','HEAD'],cwd=R,capture_output=True,text=True,check=True).stdout.strip();branch=subprocess.run(['git','branch','--show-current'],cwd=R,capture_output=True,text=True,check=True).stdout.strip();check(head=='d81672c4b314f0388e10e4c8dc9466b35ea89ce7' and branch=='maintenance/phase10','HEAD/branch changed')
import psutil
active=[]
for p in psutil.process_iter(['pid','name','cmdline']):
 try:
  if any(x in (p.info.get('name') or '').lower() for x in ('qemu','cargo','rustc')) or any(str(x).endswith('phase6_verify.py') for x in p.info.get('cmdline') or []):active.append(p.info)
 except psutil.NoSuchProcess:pass
check(not active,'active shared work')
save('final_stability_01.json',{'overall':'PASS','counts':counts,'head':head,'branch':branch,'active_shared_processes':active,'qualification':'Final snapshot, not replacement for invocation exits'})
identity_paths=[B/'candidate_manifest_04.json',B/'reviews/candidate_review_05.json',B/'canonical_readback_supplement_01.json',B/'canonical_readback_03.py',B/'canonical_readback_04.py',B/'parent_canonical_readback_03.json',B/'parent_canonical_readback_04.json',B/'canonical_identity_readback_03.json',B/'git_source_identity_01.json',B/'run_canonical_03.py',B/'canonical_provenance_03.py',R/'test_results/f4acc/c03/driver_result.json',AP,R/A['iso']['path'],R/'target/target/debug/kernel']
report={'schema':'rosti.f4-independent-final-canonical-readback.v1','review_id':'final_canonical_readback_01','review_complete':True,'reviewed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verdict':'APPROVE','blocker_count':0,'blockers':[],'scope':'Exact Phase11 F4 Ring0 prerequisite canonical PASS72 plus source-identical reusable component preservation and explicit independent postcanonical ISO-reader resolution','independent_reviewer_provenance':{'agent':'Hermes Agent / gpt-6.1-sol / separate delegated final canonical reviewer','distinct_from_parent_and_candidate05':True,'candidate_implementation_participation':False,'candidate05_approval_is_not_this_verdict':True,'review_work_root':str(W.relative_to(R)),'forbidden_actions_performed':[],'algorithms_reused':'Inspected pure source_snapshot/provenance/evidence validators and audit() only; results freshly generated offline, no reader main/test/build/guest entrypoint'},'head':head,'branch':branch,'authorizes_CPL3':False,'authorizes_F5':False,'phase11_release_ready':False,'final_canonical_readback_approved':True,'supplement_resolution':{'status':'ACCEPTED_RESOLVED','supplement_sha256':H(B/'canonical_readback_supplement_01.json'),'finding_area':'Independent ISO namespace supplement resolution','production_or_harness_drift':False,'checks_weakened':False,'acceptance_rerun':False,'evidence':str((W/'supplement_resolution_01.json').relative_to(R))},'canonical':{'driver_path':str(R/'test_results/f4acc/c03/driver_result.json'),'driver_sha256':H(R/'test_results/f4acc/c03/driver_result.json'),'acceptance_path':str(AP),'acceptance_sha256':H(AP),'actual_runner_pid':D['runner_pid'],'actual_exit':D['exit_code'],'exit_observed_by':D['exit_observed_by'],'elapsed_seconds':D['elapsed_seconds'],'overall':A['overall'],'gates_passed':A['gates_passed'],'gates_total':A['gates_total'],'gate_identities':[g['gate'] for g in A['gates']],'iso':A['iso'],'canonical_mock_suite_seconds':802.654,'canonical_mock_count':89,'unchanged_mock_timeout_seconds':900,'canonical_F1_guest_count':0,'F1_preservation_scope':'Reusable current-source-bound component10/142 checkpoints; canonical exact F1 host9 only','metadata_scenario_count':44,'specialized_counts':{'F2':8,'F3':18,'F4':12},'generic_nested_report_count':154},'checks':checks,'mandatory_areas_required':list(REQUIRED_AREAS),'mandatory_areas_complete':True,'source_pin_count':len(S),'source_sha256':S,'candidate_artifact_pin_count':len(M['artifact_sha256']),'candidate_artifact_sha256':M['artifact_sha256'],'identity_sha256':{str(p.relative_to(R)):H(p) for p in identity_paths},'fresh_complete_rehash_counts':counts,'parent_map_binding':{'canonical_map_path':str((B/'parent_canonical_readback_04.json').relative_to(R)),'canonical_map_raw_sha256':H(B/'parent_canonical_readback_04.json'),'canonical_artifact_pins':19149,'component_map_path':str((B/'parent_components_readback_05.json').relative_to(R)),'component_map_raw_sha256':H(B/'parent_components_readback_05.json'),'component_artifact_pins':61483,'all_freshly_rehashed_not_inherited_only':True},'historical_reviews':X['historical_reviews'],'limitations':['No CPL3/F5 authorization or full user-mode release readiness.','Non-PAE/no NX, executable stack/supervisor RW aliases; no hardware W^X/general isolation proof.','Bounded permanent terminal retention, NOT rollback/restoration or general teardown.','Historical F1 full final-readback gap and retained-stage protocol remain; bounded component preservation is not legacy-validator approval.','F3 static emergency bound remains conditional on at most one nested NMI; cumulative runtime high-water unknown.','Strict emitted closure is only repaired F4 terminal; inherited F1/F2/F3/shared-driver edges are unchanged.','Target-specific single-vCPU/CPL0/IF0/no reentry asm ordering, not SMP/portable Rust proof.','Polling is iteration-bounded, not wall-clock UART delivery guarantee.','Final empty process snapshot is not complete historical process provenance; owned recorded exits are separately checked.','Future docs/staging/commit work is not preverified. No new newline waiver; compare every staged F4 raw blob under scoped autocrlf policy.'],'review_observation_corrections':[{'issue':'Supplied canonical F1 embedded expectation withdrawn','resolution':'Actual metadata44 and component F1guest10 kept distinct; approved72 unchanged.'},X['preserved_reviewer_tool_failure'],X['canonical_mock89_membership_qualification']],'evidence_sha256':{str(p.relative_to(R)):H(p) for p in W.rglob('*') if p.is_file()},'self_hash_scheme':'No embedded selfhash; parent may pin raw completed JSON externally.'}
idx=1
while (B/'reviews'/f'final_canonical_readback_{idx:02d}.json').exists():idx+=1
path=B/'reviews'/f'final_canonical_readback_{idx:02d}.json';report['review_id']=path.stem
with path.open('x',encoding='utf8',newline='\n') as f:json.dump(report,f,indent=2);f.write('\n')
# Read exact target to verify the delivered verdict, its mandatory areas and pins.
reread=J(path);check(reread['review_complete'] is True and reread['verdict']=='APPROVE' and reread['blocker_count']==0 and reread['blockers']==[],'final verdict readback');check(set(REQUIRED_AREAS)<=set(x['area'] for x in reread['checks']) and all(c['status']=='PASS' for c in reread['checks']),'final checklist readback')
print(json.dumps({'path':str(path.relative_to(R)),'sha256':H(path),'verdict':reread['verdict'],'blocker_count':reread['blocker_count'],'finding_count':len(checks),'fresh_rehash_counts':counts}))
