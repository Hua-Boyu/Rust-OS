"""Canonical four-case Ring-0 supplement. Import/prepare never builds or boots.
Run requires explicit authorization. Alone this is not complete F3 acceptance.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
from f3_gdt_guest import LoggedGdb, LoggedQmp, green_snapshot, file_pins, save
from f3_evidence import CALL, require, sha, hardware, registers, descriptor, tss
from b13_entry_inject import QEMU, elf_symbols
from f1_retained_guest import port, connect

CASES = ('ss_nonpresent', 'nmi_ready', 'nmi_entry', 'nmi_output')
RAMS = (128, 512)
ASM = b'''
// F3_SUPPLEMENT_ASM_BEGIN
global_asm!(r#"
.section .bss
.balign 8
.global f3s_gdt
f3s_gdt: .zero 48
.global f3s_wire
f3s_wire: .zero 14
.section .rodata
f3s_gdtr: .word 47
 .long f3s_gdt
.section .text
.code32
.global f3s_ss
f3s_ss:
 cli
 cld
 mov $f3_context,%esi
 mov $f3s_gdt,%edi
 mov $10,%ecx
 rep movsl
 movl $0x0000ffff,f3s_gdt+40
 movl $0x00cf1300,f3s_gdt+44
 lgdt f3s_gdtr
 sgdt f3s_wire
 str f3s_wire+6
 sidt f3s_wire+8
 mov $0x28,%ax
.global f3s_ss_fault
f3s_ss_fault:
 mov %ax,%ss
 cli
1: hlt
 jmp 1b
.global f3s_df
f3s_df:
 cli
 mov $0x07c01000,%esp
.global f3s_df_fault
f3s_df_fault:
 movl $0x12345678,0x07c00000
 cli
2: hlt
 jmp 2b
"#, options(att_syntax));
// F3_SUPPLEMENT_ASM_END
'''


def bounded_output(path):
    path = Path(path)
    require(path.is_absolute(), 'absolute output required')
    path = path.resolve()
    require(path.is_relative_to((ROOT/'test_results').resolve()) and path != (ROOT/'test_results').resolve(), 'output must be owned within test_results/')
    return path


def prepare(out):
    out = bounded_output(out)
    out.mkdir(parents=True, exist_ok=False)
    before = green_snapshot()
    # The approved F5 entry amendment deliberately extends source_snapshot with
    # named authority inputs under test_results/phase11f5_cpl3_proof (design,
    # reviews, contract, pinned baseline ELF, and direct .py modules). Mirror
    # that exact enumeration; any other tasklocal file still fails closed.
    authority = 'test_results/phase11f5_cpl3_proof/'
    allowed = {authority + name for name in (
        'design.md', 'harness_contract_01.json', 'entry_design_amendment_01.md',
        'design_inputs_03.json', 'entry_design_amendment_inputs_01.json',
        'reviews/design_review_03.json', 'reviews/entry_design_amendment_01.json',
        'f2_before_macro_01.elf')}
    for name in before:
        if name.startswith('test_results/'):
            require(name in allowed or (name.startswith(authority) and name.endswith('.py')),
                    'unapproved tasklocal file entered source_snapshot: ' + name)
    review = ROOT/'test_results/phase11f3_gdt_tss/reviews/design_review_01.json'
    approval = json.loads(review.read_text())
    require(approval['verdict'] == 'APPROVE' and approval['blocker_count'] == 0, 'design approval')
    require(sha((ROOT/approval['design_path']).read_bytes()) == approval['design_raw_sha256'], 'design pin')
    source = out/'fixture/source'
    for name, digest in before.items():
        raw = (ROOT/name).read_bytes()
        require(sha(raw) == digest, 'source drift '+name)
        p = out/'frozen_inputs'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
            p = source/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
    main = source/'src/main.rs'
    original = main.read_bytes()
    anchor = b'    // stub: enable ps2 & interrupts'
    require(original.count(anchor) == 1, 'postpaging anchor')
    changed = original.replace(anchor, CALL+anchor)+ASM
    require(changed.replace(CALL,b'',1).replace(ASM,b'',1) == original, 'stripping equality')
    main.write_bytes(changed)
    (out/'fixture_assembly.rs').write_bytes(ASM)
    (out/'fixture_call.rs').write_bytes(CALL)
    (out/'design.md').write_bytes((ROOT/approval['design_path']).read_bytes())
    (out/'design_review.json').write_bytes(review.read_bytes())
    for filename in ('f3_supplemental.py','f3_supplemental_evidence.py'):
        (out/filename).write_bytes((HERE/filename).read_bytes())
    save(out/'source_freeze_before.json',before)
    require(green_snapshot() == before, 'source changed during prepare')
    plan = {'schema':'rosti.f3-supplement-prepared.v1', 'builds_or_qemu_executed':False,
            'source_snapshot_excludes_tasklocal':True, 'source_sha256':before,
            'prepared_dir':str(out), 'cases':list(CASES), 'rams':list(RAMS),
            'fixture_stripping_equality':True, 'prepared_pins':file_pins(out,('prepared.json',))}
    save(out/'prepared.json',plan)
    return plan


def emitted_output(kernel, tool, out):
    text = subprocess.check_output([str(tool),'-d',str(kernel)], text=True, timeout=60)
    (out/'disassembly.txt').write_text(text,encoding='utf-8')
    symbols = elf_symbols(kernel)
    start = symbols['f3_emergency_entry']['address']
    end = symbols['f3_emergency_terminal']['address']
    found = []
    for line in text.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)$',line)
        if m and start <= int(m[1],16) < end and re.search(r'\bout[bwl]?\b',m[3]):
            require(bytes.fromhex(m[2]) == b'\xee', 'UART OUT must be emitted OUT AL,DX')
            found.append(int(m[1],16))
    require(len(found) == 1, 'unique emitted emergency UART OUT')
    return found[0]


def finish_terminal(qmp, proc, out, state):
    # f2_fatal -> ! never returns to exception_entry.s:f2_terminal.
    # Resume without an outstanding GDB continue and observe the real halt.
    qmp.call('cont')
    deadline = time.monotonic()+5
    while True:
        require(proc.poll() is None, 'QEMU exited/reset before terminal')
        if b'F2 fatal terminal\n' in (out/'serial.txt').read_bytes():
            break
        require(time.monotonic() < deadline, 'fatal diagnostic timeout')
        time.sleep(0.03)
    time.sleep(0.15)
    qmp.call('stop')
    state('terminal')


def guest(kernel, out, case, ram, output_ip):
    out.mkdir()
    symbols = elf_symbols(kernel)
    gp, qp = port(), port()
    argv = [str(QEMU),'-kernel',str(kernel),'-cpu','qemu32','-m',str(ram),'-smp','1',
            '-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot',
            '-serial','file:'+str(out/'serial.txt'),'-d','int,guest_errors','-D',str(out/'qemu.log'),
            '-S','-gdb',f'tcp:127.0.0.1:{gp}','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off']
    row = {'name':f'{case}_{ram}','case':case,'ram_mib':ram,'command':argv,
           'overall':'FAIL','capture_complete':False,'debugger_mutations':[],
           'checkpoints':{},'memory_origins':{},'output_ip':output_ip,'checks':[]}
    proc, sockets = None, []
    try:
        with (out/'stderr.txt').open('wb') as err, (out/'gdb.jsonl').open('w') as glog, (out/'qmp.jsonl').open('w') as qlog:
            proc = subprocess.Popen(argv,stdout=subprocess.DEVNULL,stderr=err)
            row['owned_pid'] = proc.pid
            deadline = time.monotonic()+240
            gs, qs = connect(gp,proc,deadline),connect(qp,proc,deadline)
            sockets = [gs,qs]
            gs.settimeout(60)
            qs.settimeout(10)
            gdb,qmp = LoggedGdb(gs,glog),LoggedQmp(qs,qlog)
            gdb.deadline = qmp.deadline = deadline
            qmp.deadline_socket = qs
            gdb.command('?')
            def addr(name):
                return symbols[name]['address']
            def mem(name, address, size):
                raw = b''.join(gdb.read(address+i,min(512,size-i)) for i in range(0,size,512))
                (out/name).write_bytes(raw)
                row['memory_origins'][name] = {'address':address,'size':size}
                return raw
            def state(label):
                packet = gdb.command('g')
                (out/(label+'_register_packet.txt')).write_text(packet)
                _, text = qmp.hardware()
                (out/(label+'_hardware.txt')).write_bytes(text.encode('ascii'))
                require(qmp.call('query-status')['running'] is False,'CPU must be paused')
                require(gdb.command('g') == packet, 'CPU advanced during capture')
                regs = registers(packet.encode())
                row['checkpoints'][label] = regs['eip']
                return regs,hardware(text.encode())
            def stop(address, label):
                require(gdb.command(f'Z1,{address:x},1') == 'OK','breakpoint install')
                reply = gdb.command('c')
                require(reply.startswith(('T05','S05')),'actual breakpoint stop')
                regs, hw = state(label)
                require(regs['eip'] == address, 'checkpoint EIP')
                require(gdb.command(f'z1,{address:x},1') == 'OK','breakpoint removal')
                return regs,hw
            ready, initial = stop(addr('f3_ready'),'ready')
            base = addr('f3_context')
            mem('ready_gdt.bin',base,40)
            mem('normal_tss.bin',base+40,104)
            mem('emergency_tss.bin',base+144,104)
            mem('idt8.bin',initial['IDT'][0]+64,8)
            mem('idt2.bin',initial['IDT'][0]+16,8)
            mem('idt12.bin',initial['IDT'][0]+96,8)
            # No debugger writes other than the explicit fixture EIP redirect.
            if case != 'nmi_ready':
                target = addr('f3s_ss' if case == 'ss_nonpresent' else 'f3s_df')
                gdb.set_registers(eip=target)
                row['debugger_mutations'] = list(gdb.mutations)
                if case == 'ss_nonpresent':
                    before,_ = stop(addr('f3s_ss_fault'),'before')
                    mem('fixture_gdt.bin',addr('f3s_gdt'),48)
                    mem('production_gdt_after.bin',base,40)
                    mem('fixture_wire.bin',addr('f3s_wire'),14)
                    mem('fault_instruction.bin',before['eip'],2)
                else:
                    stop(addr('f3s_df_fault'),'fault')
                    entry,_ = stop(addr('f3_emergency_entry'),'entry')
                    mem('df_error.bin',entry['esp'],4)
                    mem('post_task_gdt.bin',base,40)
                    mem('post_emergency_tss.bin',base+144,104)
                    if case == 'nmi_output':
                        before,_ = stop(output_ip,'before')
                        mem('output_instruction.bin',before['eip'],1)
                        mem('emergency_observed.bin',base+248,16)
                    else:
                        before,_ = state('before')
            else:
                before,_ = state('before')
            if case != 'ss_nonpresent':
                require(qmp.call('query-status')['running'] is False,'NMI checkpoint paused')
                qmp.call('inject-nmi')
                # QMP queues NMI, it must not manufacture an F2 frame or advance EIP.
                require(gdb.command('g') == (out/'before_register_packet.txt').read_text(),'NMI advanced paused CPU')
            normalized,_ = stop(addr('f2_normalized'),'normalized')
            mem('mandatory_prefix.bin',normalized['esp'],68)
            finish_terminal(qmp, proc, out, state)
            from f3_supplemental_evidence import validate_case
            row['checks'] = validate_case(out,symbols,case,ram,output_ip,row)
            row.update(overall='PASS',capture_complete=True)
    except Exception as exc:
        row['error'] = repr(exc)
    finally:
        if proc is not None:
            row['qemu_exit_before_cleanup'] = proc.poll()
            row['cleanup_action'] = 'kill_owned_Popen' if proc.poll() is None else 'already_exited'
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            row.update(qemu_exit=proc.returncode,owned_qemu_exited=proc.poll() is not None)
        for sock in sockets:
            sock.close()
        row['frozen_bytes'] = file_pins(out,('guest_report.json',))
        save(out/'guest_report.json',row)
    return row


def run(out, parent_ready, objdump):
    require(parent_ready, 'parent authorization required BEFORE build/QEMU')
    out = bounded_output(out)
    from f3_supplemental_evidence import validate_prepared, validate_matrix
    plan = validate_prepared(out)
    require(not (out/'report.json').exists() and not (out/'build.log').exists(),'refuse rerun/overwrite')
    before = plan['source_sha256']
    result = {'schema':'rosti.f3-supplement.v1','overall':'HARNESS_FAIL','driver_exit':2,
              'parent_authorized':True,'full_f3_acceptance':False,'hardware_cpl3':False,
              'source_sha256':before,'scenarios':[],'prepared_dir':str(out)}
    try:
        require(green_snapshot() == before,'canonical source drift since prepare; prepare afresh')
        source = out/'fixture/source'
        argv = ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(out/'fixture/build')]
        result['build_command'] = argv
        result['build_cwd'] = str(source)
        with (out/'build.log').open('wb') as log:
            proc = subprocess.run(argv,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        result['build_exit'] = proc.returncode
        require(proc.returncode == 0,'fixture compilation failed; not runtime evidence')
        kernel = out/'kernel.elf'
        shutil.copyfile(out/'fixture/build/target/debug/kernel',kernel)
        result['kernel_sha256'] = sha(kernel.read_bytes())
        result['objdump'] = str(objdump.resolve())
        output_ip = emitted_output(kernel,objdump,out)
        result['output_ip'] = output_ip
        for ram in RAMS:
            for case in CASES:
                require(green_snapshot() == before,'source drift before guest')
                result['scenarios'].append(guest(kernel,out/f'{case}_{ram}',case,ram,output_ip))
                save(out/'running.json',result)
        require(len(result['scenarios']) == 8 and all(r['overall'] == 'PASS' for r in result['scenarios']),'incomplete/failing supplemental matrix')
        result.update(overall='SUPPLEMENTAL_RING0_GREEN',driver_exit=0)
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        after = green_snapshot()
        save(out/'source_freeze_after.json',after)
        result['source_freeze_stable'] = before == after
        if before != after:
            result.update(overall='HARNESS_FAIL',driver_exit=2,error='source freeze changed')
        result['frozen_bytes'] = file_pins(out,('report.json','running.json','validation.json'),('fixture/build/',))
        save(out/'report.json',result)
        if result['driver_exit'] == 0:
            try:
                validation = validate_matrix(out)
                save(out/'validation.json',validation)
            except Exception as exc:
                result.update(overall='HARNESS_FAIL',driver_exit=2,error='independent validator: '+repr(exc))
                save(out/'report.json',result)
        print(json.dumps(result,indent=2))
    return result['driver_exit']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action',required=True)
    a = sub.add_parser('prepare',help='copy and inject fixture only; NO build/QEMU')
    a.add_argument('--output-dir',type=Path,required=True)
    a = sub.add_parser('run',help='requires parent readiness; builds then boots eight guests')
    a.add_argument('--prepared-dir',type=Path,required=True)
    a.add_argument('--parent-ready',action='store_true',required=True)
    a.add_argument('--objdump',type=Path,required=True)
    args = p.parse_args()
    if args.action == 'prepare':
        print(json.dumps(prepare(args.output_dir),indent=2))
        return 0
    return run(args.prepared_dir,args.parent_ready,args.objdump)


if __name__ == '__main__':
    sys.exit(main())
