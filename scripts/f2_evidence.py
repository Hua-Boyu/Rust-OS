"""Fail-closed validation of the invocation-owned F2 hardware matrix."""
import hashlib
import json
from pathlib import Path

CASES = frozenset((case, ram) for case in ('ud','de','gp','pf') for ram in (128,512))
COMMON_CHECKS = frozenset(('observed_supported_profile','all32_actual_IDT_offsets_and_interrupt_gates','trigger_IF0_DF1','trigger_exact_sentinels','live_kernel_selectors','live_IF0_DF0','saved_original_selectors','saved_exact_GPRs','saved_vector_and_error','saved_CPU_eip_cs_flags','same_ring_stack_geometry','raw_C_entry_alignment_and_argument','raw_C_entry_kernel_state','fatal_diagnostic_terminal','terminal_halted_IF0','no_shell_return','NMI_reentry_silent_halt','architectural_vector_trace'))

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate(path, source):
    path=Path(path).resolve()
    report=json.loads(path.read_text())
    require(report.get('overall')=='PASS' and report.get('build_exit')==0,'F2 build/matrix failed')
    require(report.get('source_sha256')==source,'F2 source freeze mismatch')
    require(report.get('stripping_equality') is True,'F2 production-body equality missing')
    require(report.get('original_main_sha256')==source.get('src/main.rs'),'F2 canonical main mismatch')
    kernel=path.parent/'kernel.elf'
    require(report.get('kernel_sha256')==digest(kernel),'F2 fixture ELF identity mismatch')
    rows=report.get('cases')
    require(isinstance(rows,list) and len(rows)==len(CASES),'F2 missing/zero/extra cases')
    seen=set()
    pins={str(path):digest(path),str(kernel):digest(kernel)}
    for row in rows:
        identity=(row.get('case'),row.get('ram_mib'))
        require(identity in CASES and identity not in seen and type(identity[1]) is int,'F2 duplicate/substituted/impostor case')
        seen.add(identity)
        case,ram=identity
        child=path.parent/f'{case}_{ram}'/'report.json'
        require(row.get('overall')=='PASS' and Path(row.get('report','')).resolve()==child.resolve(),'F2 non-owned or failed child')
        guest=json.loads(child.read_text())
        require(guest.get('overall')=='PASS' and (guest.get('case'),guest.get('ram_mib'))==identity,'F2 child identity/status')
        require(guest.get('owned_qemu_exited') is True and type(guest.get('qemu_exit')) is int,'F2 process cleanup missing')
        require(guest.get('hardware_cpl3') is False,'F2 scope mismatch')
        require(guest.get('kernel_sha256')==report['kernel_sha256'],'F2 child ELF mismatch')
        checks=guest.get('checks')
        require(isinstance(checks,list) and checks and all(c.get('pass') is True for c in checks),'F2 missing/false hardware checks')
        names=[c.get('name') for c in checks]
        expected=COMMON_CHECKS | ({'page_fault_CR2_zero'} if case=='pf' else set())
        require(len(names)==len(set(names)) and set(names)==expected,'F2 hardware check identities')
        command=guest.get('command')
        require(isinstance(command,list),'F2 command missing')
        def operand(flag):
            require(command.count(flag)==1 and command.index(flag)+1<len(command),'F2 command operand '+flag)
            return command[command.index(flag)+1]
        require(Path(operand('-kernel')).resolve()==kernel.resolve(),'F2 wrong kernel operand')
        require(operand('-m')==str(ram) and operand('-smp')=='1' and operand('-cpu')=='qemu32','F2 actual guest mode/RAM')
        require(operand('-serial')=='file:'+str(child.parent/'serial.txt'),'F2 serial identity')
        require('F2 fatal terminal\n' in (child.parent/'serial.txt').read_text(),'F2 terminal marker missing')
        require((child.parent/'mandatory_prefix.bin').stat().st_size==68,'F2 saved frame length')
        pins[str(child)]=digest(child)
    require(seen==CASES,'F2 incomplete identity matrix')
    return {'scenario_count':len(seen),'pins':pins}
