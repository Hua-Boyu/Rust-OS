"""Disposable Ring-0 CPU-fault fixtures; never modify production build outputs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time

from b13_entry_inject import Gdb, QEMU, elf_symbols
from f1_capture import Qmp
from f1_retained_guest import port, connect

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('eax','ecx','edx','ebx','esp','ebp','esi','edi','eip','eflags','cs','ss','ds','es','fs','gs')
FIELDS = ('gs','fs','es','ds','edi','esi','ebp','pushad_esp','ebx','edx','ecx','eax','vector','error','eip','cs','eflags')
CASES = {'ud': (6,0), 'de': (0,0), 'gp': (13,0x58), 'pf': (14,2)}

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def source_snapshot():
    path = ROOT / 'scripts/phase6_verify.py'
    tree = ast.parse(path.read_text())
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('sha256','source_snapshot')]
    env = {'PROJECT': ROOT, 'hashlib': hashlib}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),env)
    return env['source_snapshot']()

def trigger_assembly():
    text = '\n// F2_FIXTURE_ASM_BEGIN\nglobal_asm!(r#"\n.section .text\n'
    for case in CASES:
        text += f'.global f2_trigger_{case}\nf2_trigger_{case}:\n cli\n'
        if case in ('ud','de'):
            text += ' xor %eax,%eax\n'
        else:
            text += ' mov $0x10,%eax\n'
        text += ' mov %ax,%ds\n mov %ax,%es\n mov %ax,%fs\n mov %ax,%gs\n'
        if case == 'de':
            text += ' push $0\n'
        text += ' mov $0x11112222,%eax\n mov $0x33334444,%ebx\n mov $0x55556666,%ecx\n mov $0x77778888,%edx\n mov $0x9999aaaa,%esi\n mov $0xbbbbcccc,%edi\n mov $0xddddeeee,%ebp\n'
        if case == 'gp':
            text += ' mov $0x58,%ax\n'
        text += f' std\n.global f2_fault_{case}\nf2_fault_{case}:\n'
        text += {'ud':' ud2\n','de':' divl (%esp)\n','gp':' mov %ax,%ds\n','pf':' mov %eax,0\n'}[case]
        text += ' cli\n1: hlt\n jmp 1b\n'
    text += '"#, options(att_syntax));\nunsafe extern "C" { fn f2_trigger_ud() -> !; }\n// F2_FIXTURE_ASM_END\n'
    return text.encode()

def registers(gdb, folder, label):
    raw = gdb.command('g')
    (folder/(label+'_register_packet.txt')).write_text(raw)
    return dict(zip(NAMES,struct.unpack_from('<16I',bytes.fromhex(raw))))

def scenario(kernel, symbols, output, case, ram):
    output.mkdir()
    vector,error = CASES[case]
    gp,qp = port(),port()
    argv = [str(QEMU),'-kernel',str(kernel),'-cpu','qemu32','-m',str(ram),'-smp','1','-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot','-serial','file:'+str(output/'serial.txt'),'-d','int,guest_errors','-D',str(output/'qemu.log'),'-S','-gdb',f'tcp:127.0.0.1:{gp}','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off']
    report = {'overall':'FAIL','case':case,'ram_mib':ram,'vector':vector,'expected_error':error,'command':argv,'kernel_sha256':sha(kernel.read_bytes()),'hardware_cpl3':False,'checks':[]}
    proc = None
    sockets = []
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)})
        require(value,name)
    try:
        with (output/'stderr.txt').open('wb') as stream:
            proc = subprocess.Popen(argv,stdout=subprocess.DEVNULL,stderr=stream)
        report['owned_pid'] = proc.pid
        deadline = time.monotonic()+25
        gs,qs = connect(gp,proc,deadline),connect(qp,proc,deadline)
        sockets = [gs,qs]
        gs.settimeout(25)
        qs.settimeout(10)
        gdb,qmp = Gdb(gs),Qmp(qs)
        gdb.command('?')
        def addr(name):
            return symbols[name]['address']
        def stop(name):
            address = addr(name)
            require(gdb.command(f'Z1,{address:x},1')=='OK','breakpoint install')
            reply = gdb.command('c')
            require(reply.startswith(('T05','S05')),'debug stop')
            regs = registers(gdb,output,name)
            require(regs['eip']==address,'wrong stopped EIP '+name)
            require(qmp.call('query-status')['running'] is False,'not paused')
            require(gdb.command(f'z1,{address:x},1')=='OK','breakpoint remove')
            return regs
        # Compiled fixture calls UD entry. Select another immutable trigger at
        # its first CLI, BEFORE any destructive setup; record mutation readback.
        entry = stop('f2_trigger_ud')
        if case != 'ud':
            gdb.set_registers(eip=addr('f2_trigger_'+case))
        report['fixture_selection_mutations'] = gdb.mutations
        before = stop('f2_fault_'+case)
        report['before'] = before
        hwfields,hw = qmp.hardware()
        (output/'before_hardware.txt').write_text(hw)
        check('observed_supported_profile',hwfields['CR0']&0x80010001==0x80010001 and hwfields['CR4']&((1<<5)|(1<<23))==0 and 'EFER=0000000000000000' in hw and before['cs']==8 and before['ss']==16)
        idt = re.search(r'IDT=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',hw)
        require(idt is not None,'missing actual IDTR')
        gates = gdb.read(int(idt.group(1),16),32*8)
        (output/'cpu_idt.bin').write_bytes(gates)
        decoded = []
        for v in range(32):
            low,selector,zero,attrs,high = struct.unpack_from('<HHBBH',gates,v*8)
            decoded.append({'vector':v,'offset':low|(high<<16),'selector':selector,'attrs':attrs,'zero':zero})
        report['actual_idt'] = decoded
        check('all32_actual_IDT_offsets_and_interrupt_gates',all(g['offset']==addr('f2_exc_'+str(g['vector'])) and g['selector']==8 and g['attrs']==0x8e and g['zero']==0 for g in decoded))
        check('trigger_IF0_DF1',before['eflags']&0x600==0x400)
        check('trigger_exact_sentinels',all(before[n]==v for n,v in {'eax':0x11110058 if case=='gp' else 0x11112222,'ebx':0x33334444,'ecx':0x55556666,'edx':0x77778888,'esi':0x9999aaaa,'edi':0xbbbbcccc,'ebp':0xddddeeee}.items()))
        normalized = stop('f2_normalized')
        report['normalized'] = normalized
        raw = gdb.read(normalized['esp'],68)
        (output/'mandatory_prefix.bin').write_bytes(raw)
        f = dict(zip(FIELDS,struct.unpack('<17I',raw)))
        report['frame'] = f
        check('live_kernel_selectors',all(normalized[n]==16 for n in ('ds','es','fs','gs')))
        check('live_IF0_DF0',normalized['eflags']&0x600==0)
        check('saved_original_selectors',all(f[n]==before[n] for n in ('ds','es','fs','gs')))
        check('saved_exact_GPRs',all(f[n]==before[n] for n in ('eax','ebx','ecx','edx','esi','edi','ebp')))
        check('saved_vector_and_error',f['vector']==vector and f['error']==error)
        # Intel SDM rev093 Vol3 PDF p680 / 20.3.1.1: fault-class exceptions
        # (except instruction-breakpoint #DB) push RF=1. All four are faults.
        check('saved_CPU_eip_cs_flags',f['eip']==before['eip'] and f['cs']&0xffff==before['cs'] and f['eflags']==(before['eflags'] | (1<<16)))
        check('same_ring_stack_geometry',normalized['esp']+68==before['esp'] and f['pushad_esp']==normalized['esp']+48)
        callee = stop('f2_fatal')
        report['callee'] = callee
        arg = struct.unpack('<I',gdb.read(callee['esp']+4,4))[0]
        check('raw_C_entry_alignment_and_argument',callee['esp']%16==12 and arg==normalized['esp'])
        check('raw_C_entry_kernel_state',callee['eflags']&0x600==0 and all(callee[n]==16 for n in ('ds','es','fs','gs')))
        fields,hw = qmp.hardware()
        (output/'callee_hardware.txt').write_text(hw)
        if case=='pf':
            match = re.search(r'CR2=([0-9a-fA-F]+)',hw)
            check('page_fault_CR2_zero',match is not None and int(match.group(1),16)==0)
        gdb.send('c')
        # Bounded observation of this owned guest; never acceptance-process polling.
        limit = time.monotonic()+5
        while time.monotonic()<limit:
            text = (output/'serial.txt').read_text(errors='replace')
            if 'F2 fatal terminal\n' in text:
                break
            require(proc.poll() is None,'guest exited before terminal')
            time.sleep(0.03)
        check('fatal_diagnostic_terminal','F2 fatal terminal\n' in text)
        time.sleep(0.15)
        qmp.call('stop')
        _,terminal_hw = qmp.hardware()
        (output/'terminal_hardware.txt').write_text(terminal_hw)
        check('terminal_halted_IF0','HLT=1' in terminal_hw)
        check('no_shell_return','rosti>' not in text and 'F2 FIXTURE TRIGGER' in text)
        # NMI can enter despite IF0. Reentry must hit the already-set latch and
        # halt silently without reusing formatting or returning to the first halt.
        qmp.call('inject-nmi')
        qmp.call('cont')
        time.sleep(0.15)
        qmp.call('stop')
        _,reentry_hw = qmp.hardware()
        (output/'reentry_hardware.txt').write_text(reentry_hw)
        reentry_serial = (output/'serial.txt').read_text(errors='replace')
        check('NMI_reentry_silent_halt',reentry_serial==text and 'HLT=1' in reentry_hw)
        trace = (output/'qemu.log').read_text(errors='replace')
        cpu_fault = re.search(rf'v={vector:02x} e=([0-9a-f]+) i=0 cpl=0 IP=0008:([0-9a-f]+)',trace)
        check('architectural_vector_trace',cpu_fault is not None and int(cpu_fault.group(1),16)==error and int(cpu_fault.group(2),16)==before['eip'] and 'v=08' not in trace)
        report['overall']='PASS'
    except Exception as exc:
        report['error']=repr(exc)
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            report.update(qemu_exit=proc.returncode,owned_qemu_exited=proc.poll() is not None)
        for sock in sockets:
            sock.close()
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    require(report['overall']=='PASS',f'{case}/{ram}: '+report.get('error','failed'))
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--case',choices=tuple(CASES))
    parser.add_argument('--ram',type=int,choices=(128,512))
    args=parser.parse_args()
    require(args.output_dir.is_absolute(),'absolute output required')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='f2_guest_',dir=args.output_dir))
    snapshot=source_snapshot()
    result={'overall':'FAIL','source_sha256':snapshot,'cases':[],'checks':[]}
    try:
        with tempfile.TemporaryDirectory(prefix='f2fixture_',dir=ROOT/'dist') as temp:
            stage=Path(temp)
            source=stage/'source'
            source.mkdir()
            for name,digest in snapshot.items():
                if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
                    raw=(ROOT/name).read_bytes()
                    require(sha(raw)==digest,'source drift '+name)
                    dest=source/name
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes(raw)
            mainpath=source/'src/main.rs'
            original=mainpath.read_bytes()
            anchor=b'    // stub: enable ps2 & interrupts'
            require(original.count(anchor)==1,'fixture anchor')
            call=b'    // F2_FIXTURE_CALL_BEGIN\n    io::serial::puts("F2 FIXTURE TRIGGER\\n");\n    unsafe { f2_trigger_ud(); }\n    // F2_FIXTURE_CALL_END\n'
            assembly=trigger_assembly()
            changed=original.replace(anchor,call+anchor)+assembly
            require(changed.replace(call,b'',1).replace(assembly,b'',1)==original,'stripping equality')
            mainpath.write_bytes(changed)
            result.update(owned_stage=str(stage),original_main_sha256=sha(original),injected_main_sha256=sha(changed),assembly_sha256=sha(assembly),stripping_equality=True)
            command=['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(stage/'build')]
            with (out/'build.log').open('wb') as log:
                build=subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=240)
            result.update(build_exit=build.returncode,build_command=command,build_cwd=str(source))
            require(build.returncode==0,'compile failure; not runtime RED')
            kernel=out/'kernel.elf'
            shutil.copyfile(stage/'build/target/debug/kernel',kernel)
            symbols=elf_symbols(kernel)
            result['kernel_sha256']=sha(kernel.read_bytes())
            for case in ([args.case] if args.case else CASES):
                for ram in ([args.ram] if args.ram else (128,512)):
                    row=scenario(kernel,symbols,out/f'{case}_{ram}',case,ram)
                    result['cases'].append({'case':case,'ram_mib':ram,'overall':row['overall'],'report':str(out/f'{case}_{ram}/report.json')})
        require(source_snapshot()==snapshot,'source freeze changed during guest run')
        result['checks']=[{'name':'all_requested_cpu_scenarios_PASS','pass':bool(result['cases']) and all(x['overall']=='PASS' for x in result['cases'])},{'name':'source_freeze_stable','pass':True}]
        result['overall']='PASS'
    finally:
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'overall':result['overall'],'output':str(out),'cases':result['cases']},indent=2))

if __name__=='__main__':
    main()
