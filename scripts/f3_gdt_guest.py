"""Disposable F3 CPU oracle; --baseline preserves the historical RED path.

Normal mode builds copied canonical source, invokes production divergent F3,
then measures the exact minimal Ring-0 matrix at both RAM sizes. Only explicit,
logged/readback-verified fixture-selection EIP redirects are admitted. No disks,
production/acceptance-runner writes, fake fault words, or full acceptance claim.
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

from b13_entry_inject import Gdb, QEMU, elf_symbols
from f1_capture import Qmp
from f1_retained_guest import port, connect
from f2_exception_guest import source_snapshot, sha, require, NAMES

ROOT = Path(__file__).resolve().parents[1]
CALL = b'''    // F3_FIXTURE_CALL_BEGIN
    unsafe { f3_probe(); }
    // F3_FIXTURE_CALL_END
'''
ASM = b'''
// F3_FIXTURE_ASM_BEGIN
global_asm!(r#"
.section .bss
.balign 8
.global f3_observation
f3_observation:
 .zero 24
.section .text
.global f3_probe
f3_probe:
 cli
 sgdt f3_observation
 str f3_observation+6
 mov %cs,f3_observation+8
 mov %ss,f3_observation+10
 mov %ds,f3_observation+12
 mov %es,f3_observation+14
 mov %fs,f3_observation+16
 mov %gs,f3_observation+18
.global f3_ready
f3_ready:
 hlt
 jmp f3_ready
"#, options(att_syntax));
unsafe extern "C" { fn f3_probe() -> !; }
// F3_FIXTURE_ASM_END
'''


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


class LoggedGdb(Gdb):
    def __init__(self, sock, log):
        super().__init__(sock)
        self.log = log

    def command(self, text):
        if getattr(self, 'deadline', None) is not None:
            remaining = self.deadline-time.monotonic()
            require(remaining > 0, 'guest end-to-end deadline')
            self.sock.settimeout(min(25,remaining))
        reply = super().command(text)
        self.log.write(json.dumps({'command': text, 'reply': reply}) + '\n')
        self.log.flush()
        return reply


class LoggedQmp(Qmp):
    def __init__(self, sock, log):
        self.log = log
        super().__init__(sock)

    def call(self, command, **arguments):
        if getattr(self, 'deadline', None) is not None:
            remaining = self.deadline-time.monotonic()
            require(remaining > 0, 'guest end-to-end deadline')
            self.deadline_socket.settimeout(min(10,remaining))
        reply = super().call(command, **arguments)
        self.log.write(json.dumps({'command': command, 'arguments': arguments, 'reply': reply}) + '\n')
        self.log.flush()
        return reply


def guest(kernel, out, ram):
    symbols = elf_symbols(kernel)
    gp, qp = port(), port()
    argv = [str(QEMU), '-kernel', str(kernel), '-cpu', 'qemu32', '-m', str(ram),
            '-smp', '1', '-machine', 'pc', '-display', 'none', '-nic', 'none',
            '-monitor', 'none', '-no-reboot', '-serial', 'file:' + str(out/'serial.txt'),
            '-d', 'int,guest_errors', '-D', str(out/'qemu.log'), '-S',
            '-gdb', f'tcp:127.0.0.1:{gp}', '-qmp', f'tcp:127.0.0.1:{qp},server=on,wait=off']
    report = {'command': argv, 'ram_mib': ram, 'capture_complete': False,
              'hardware_cpl3': False, 'debugger_mutations': [], 'checks': []}
    proc, sockets = None, []
    try:
        with (out/'qemu_stderr.txt').open('wb') as err, (out/'gdb.jsonl').open('w') as glog, (out/'qmp.jsonl').open('w') as qlog:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=err)
            report['owned_pid'] = proc.pid
            deadline = time.monotonic() + 25
            gs = connect(gp, proc, deadline)
            sockets.append(gs)
            qs = connect(qp, proc, deadline)
            sockets.append(qs)
            gs.settimeout(25)
            qs.settimeout(10)
            gdb, qmp = LoggedGdb(gs, glog), LoggedQmp(qs, qlog)
            gdb.command('?')

            def stop(name):
                address = symbols[name]['address']
                require(gdb.command(f'Z1,{address:x},1') == 'OK', 'breakpoint install')
                reply = gdb.command('c')
                require(reply.startswith(('T05', 'S05')), 'actual debug stop')
                raw = gdb.command('g')
                (out/(name+'_register_packet.txt')).write_text(raw)
                regs = dict(zip(NAMES, struct.unpack_from('<16I', bytes.fromhex(raw))))
                require(regs['eip'] == address, 'checkpoint EIP mismatch')
                require(qmp.call('query-status')['running'] is False, 'vCPU not paused')
                require(gdb.command(f'z1,{address:x},1') == 'OK', 'breakpoint removal')
                return regs

            report['raw_probe_entry'] = stop('f3_probe')
            report['ready_registers'] = regs = stop('f3_ready')
            fields, hw = qmp.hardware()
            (out/'ready_hardware.txt').write_text(hw)
            report['hardware_fields'] = fields
            raw = gdb.read(symbols['f3_observation']['address'], 24)
            (out/'sgdt_str_selectors.bin').write_bytes(raw)
            limit, base, tr, cs, ss, ds, es, fs, gs_value = struct.unpack_from('<HI7H', raw)
            report.update(actual_gdtr={'base': base, 'limit': limit}, actual_tr=tr,
                          actual_selectors=dict(zip(('cs','ss','ds','es','fs','gs'), (cs,ss,ds,es,fs,gs_value))))
            gdtr = re.search(r'GDT=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)', hw)
            task = re.search(r'TR\s*=([0-9a-fA-F]+)', hw)
            require(gdtr and task, 'actual QMP GDTR/TR absent')
            require((base,limit) == tuple(int(v,16) for v in gdtr.groups()), 'SGDT/QMP disagreement')
            require(tr == int(task.group(1),16), 'STR/QMP disagreement')
            require(limit <= 4095 and (limit+1)%8 == 0, 'bounded wire GDT size')
            gdt = b''.join(gdb.read(base+i, min(512,limit+1-i)) for i in range(0,limit+1,512))
            (out/'cpu_gdt.bin').write_bytes(gdt)
            report['actual_gdt_hex'] = gdt.hex()
            report['actual_gdt_sha256'] = sha(gdt)
            require(all(regs[k] == v for k,v in report['actual_selectors'].items()), 'raw selector disagreement')
            require(cs == 8 and all(v == 16 for v in (ss,ds,es,fs,gs_value)), 'baseline kernel selectors')
            require(fields['CR4'] & (1<<23) == 0 and 'EFER=0000000000000000' in hw, 'unsupported CPU profile')
            require(gdb.command('g') == (out/'f3_ready_register_packet.txt').read_text(), 'capture advanced CPU')
            require(gdb.mutations == [], 'unauthorized debugger mutations')
            # Resume only into the already observed naked CLI/HLT terminal.
            gdb.send('c')
            glog.write(json.dumps({'command':'c', 'reply':'asynchronous; QMP stop follows'})+'\n')
            glog.flush()
            time.sleep(0.15)
            require(proc.poll() is None, 'guest exited before controlled halt')
            qmp.call('stop')
            _, terminal = qmp.hardware()
            (out/'terminal_hardware.txt').write_text(terminal)
            require('HLT=1' in terminal, 'not actually halted')
            require('Triple fault' not in (out/'qemu.log').read_text(errors='replace'), 'triple fault')
            report['capture_complete'] = True
            report['checks'] = [{'name':'actual_TR_equals_0x18', 'expected':24, 'actual':tr, 'pass':tr == 24}]
            if tr == 24:
                report['error'] = 'Baseline unexpectedly has TR18; full GREEN oracle not implemented'
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        if proc is not None:
            report['qemu_exit_before_cleanup'] = proc.poll()
            report['cleanup_action'] = 'kill_owned_Popen' if proc.poll() is None else 'already_exited'
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            report.update(qemu_exit=proc.returncode, owned_qemu_exited=proc.poll() is not None)
        for sock in sockets:
            sock.close()
        save(out/'guest_report.json', report)
    return report


def baseline_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--ram', type=int, choices=(128,512), default=128)
    args = parser.parse_args()
    require(args.output_dir.is_absolute(), 'absolute output required')
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema':'rosti.f3-runtime-baseline.v1', 'overall':'HARNESS_FAIL',
              'driver_exit':2, 'build_exit':None, 'baseline':True}
    snapshot = source_snapshot()
    save(out/'source_freeze_before.json', snapshot)
    try:
        review = ROOT/'test_results/phase11f3_gdt_tss/reviews/design_review_01.json'
        pins = json.loads(review.read_text())
        require(pins['verdict'] == 'APPROVE' and pins['blocker_count'] == 0, 'design not approved')
        require(sha((ROOT/pins['design_path']).read_bytes()) == pins['design_raw_sha256'], 'design drift')
        mismatches = [name for name,digest in pins['raw_sha256'].items() if sha((ROOT/name).read_bytes()) != digest]
        require(not mismatches, 'review pin drift: '+repr(mismatches))
        result['review_sha256'] = sha(review.read_bytes())
        result['design_sha256'] = pins['design_raw_sha256']
        stage = out/'fixture'
        source = stage/'source'
        source.mkdir(parents=True)
        for name,digest in snapshot.items():
            if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
                raw = (ROOT/name).read_bytes()
                require(sha(raw) == digest, 'source copy drift '+name)
                dest = source/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
        mainpath = source/'src/main.rs'
        original = mainpath.read_bytes()
        anchor = b'    // stub: enable ps2 & interrupts'
        require(original.count(anchor) == 1, 'unique postpaging anchor')
        changed = original.replace(anchor, CALL+anchor) + ASM
        require(changed.replace(CALL,b'',1).replace(ASM,b'',1) == original, 'stripping equality')
        mainpath.write_bytes(changed)
        (out/'fixture_assembly.rs').write_bytes(ASM)
        (out/'fixture_call.rs').write_bytes(CALL)
        result.update(original_main_sha256=sha(original), injected_main_sha256=sha(changed),
                      assembly_sha256=sha(ASM), call_sha256=sha(CALL), stripping_equality=True)
        command = ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(stage/'build')]
        result.update(build_command=command, build_cwd=str(source))
        with (out/'build.log').open('wb') as log:
            build = subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        result['build_exit'] = build.returncode
        require(build.returncode == 0, 'compile failure is NOT runtime RED')
        kernel = out/'kernel.elf'
        shutil.copyfile(stage/'build/target/debug/kernel', kernel)
        result['kernel_sha256'] = sha(kernel.read_bytes())
        result['guest'] = row = guest(kernel,out,args.ram)
        require(row['capture_complete'] and row['owned_qemu_exited'], 'incomplete CPU evidence/cleanup')
        require(row['actual_tr'] != 24, 'baseline did not expose missing TR; no GREEN claim')
        result.update(overall='RUNTIME_RED', driver_exit=1,
                      assertion_failure={'name':'actual_TR_equals_0x18','expected':24,'observed':row['actual_tr']})
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        after = source_snapshot()
        save(out/'source_freeze_after.json',after)
        stable = snapshot == after
        result.update(source_freeze_stable=stable, source_input_count=len(snapshot),
                      source_freeze_before_sha256=sha((out/'source_freeze_before.json').read_bytes()),
                      source_freeze_after_sha256=sha((out/'source_freeze_after.json').read_bytes()),
                      driver_source_sha256=sha(Path(__file__).read_bytes()))
        if not stable:
            result.update(overall='HARNESS_FAIL', driver_exit=2, error='source freeze changed')
        save(out/'report.json',result)
        print(json.dumps(result,indent=2))
    return result['driver_exit']


# GREEN fixtures select immutable assembly only; never patch CPU tables/maps.
def green_assembly():
    from f3_evidence import SCENARIOS
    text = '\n// F3_GREEN_ASM_BEGIN\nglobal_asm!(r#"\n.section .bss\n.balign 8\n.global f3_wire_probe\nf3_wire_probe:\n .zero 14\n.section .text\n.code32\n'
    for case in SCENARIOS:
        text += f'.global f3_trigger_{case}\nf3_trigger_{case}:\n cli\n sgdt f3_wire_probe\n str f3_wire_probe+6\n sidt f3_wire_probe+8\n'
        if case.endswith('_df'):
            # First push lands on the lower absent transition guard. No old
            # task stack bytes are fabricated by the debugger.
            text += ' mov $0x07c01000,%esp\n'
        text += f'.global f3_fault_{case}\nf3_fault_{case}:\n'
        text += {'ready':'', 'transition_guard_pf':' movl $0x12345678,0x07c00000\n',
                 'emergency_guard_pf':' movl $0x12345678,0x07c05000\n',
                 'exhausted_esp_ud2_df':' ud2\n',
                 'exhausted_esp_pf_df':' movl $0x12345678,0x07c00000\n'}[case]
        text += ' cli\n1: hlt\n jmp 1b\n'
    text += '"#, options(att_syntax));\n// F3_GREEN_ASM_END\n'
    return text.encode()


def green_snapshot():
    snapshot = source_snapshot()
    for name in ('scripts/f3_gdt_guest.py','scripts/f3_evidence.py','scripts/test_f3_evidence.py'):
        snapshot[name] = sha((ROOT/name).read_bytes())
    return dict(sorted(snapshot.items()))


def file_pins(folder, exclude=(), exclude_prefixes=()):
    return {p.relative_to(folder).as_posix():sha(p.read_bytes())
            for p in sorted(folder.rglob('*')) if p.is_file()
            and p.relative_to(folder).as_posix() not in exclude
            and not p.relative_to(folder).as_posix().startswith(exclude_prefixes)}


def green_guest(kernel, out, case, ram):
    from f3_evidence import hardware, scenario_assertions
    out.mkdir()
    symbols = elf_symbols(kernel)
    gp, qp = port(), port()
    argv = [str(QEMU), '-kernel', str(kernel), '-cpu', 'qemu32', '-m', str(ram),
            '-smp', '1', '-machine', 'pc', '-display', 'none', '-nic', 'none',
            '-monitor', 'none', '-no-reboot', '-serial', 'file:'+str(out/'serial.txt'),
            '-d', 'int,guest_errors', '-D', str(out/'qemu.log'), '-S',
            '-gdb', f'tcp:127.0.0.1:{gp}', '-qmp', f'tcp:127.0.0.1:{qp},server=on,wait=off']
    report = {'name':f'{case}_{ram}', 'case':case, 'ram_mib':ram, 'overall':'FAIL',
              'capture_complete':False, 'kernel_sha256':sha(kernel.read_bytes()),
              'command':argv, 'checks':[], 'debugger_mutations':[], 'hardware_cpl3':False}
    proc, sockets = None, []
    try:
        with (out/'stderr.txt').open('wb') as err, (out/'gdb.jsonl').open('w') as glog, (out/'qmp.jsonl').open('w') as qlog:
            proc = subprocess.Popen(argv,stdout=subprocess.DEVNULL,stderr=err)
            report['owned_pid'] = proc.pid
            deadline = time.monotonic()+75
            report['timeout_seconds'] = 75
            gs, qs = connect(gp,proc,deadline), connect(qp,proc,deadline)
            sockets = [gs,qs]
            gs.settimeout(min(25,max(0.01,deadline-time.monotonic())))
            qs.settimeout(min(10,max(0.01,deadline-time.monotonic())))
            gdb,qmp = LoggedGdb(gs,glog),LoggedQmp(qs,qlog)
            gdb.deadline = qmp.deadline = deadline
            qmp.deadline_socket = qs
            gdb.command('?')
            def address(name):
                return symbols[name]['address']
            def memory(name, addr, length):
                raw = b''.join(gdb.read(addr+i,min(512,length-i)) for i in range(0,length,512))
                (out/name).write_bytes(raw)
                return raw
            def stop(symbol, label):
                addr = address(symbol)
                require(gdb.command(f'Z1,{addr:x},1') == 'OK','breakpoint install')
                reply = gdb.command('c')
                require(reply.startswith(('T05','S05')),'actual debug stop')
                raw = gdb.command('g')
                (out/(label+'_register_packet.txt')).write_text(raw)
                regs = dict(zip(NAMES,struct.unpack_from('<16I',bytes.fromhex(raw))))
                require(regs['eip'] == addr,'checkpoint EIP '+symbol)
                require(qmp.call('query-status')['running'] is False,'vCPU not paused')
                require(gdb.command(f'z1,{addr:x},1') == 'OK','breakpoint removal')
                return regs
            def hw(name):
                _,text = qmp.hardware()
                (out/(name+'_hardware.txt')).write_bytes(text.encode('ascii'))
                return hardware(text.encode('ascii'))
            ready = stop('f3_ready','f3_ready')
            initial = hw('ready')
            raw_registers = gdb.command('g')
            base,limit = initial['GDT']
            require(limit == 39 and base == address('f3_context'),'production GDTR')
            memory('cpu_gdt.bin',base,40)
            memory('normal_tss.bin',base+40,104)
            memory('emergency_tss.bin',base+144,104)
            memory('context_attempt.bin',base+264,4)
            memory('idt8.bin',initial['IDT'][0]+64,8)
            def physical(name, pa, length):
                require(pa >= 4096 and pa+length <= ram*1024*1024,'physical RAM bound')
                target = out/name
                qmp.call('pmemsave',val=pa,size=length,filename=target.as_posix())
                raw = target.read_bytes()
                require(len(raw) == length,'short physical capture')
                return raw
            directory = physical('directory.bin',initial['CR3'],4096)
            pde = struct.unpack_from('<I',directory,31*4)[0]
            require(pde & 0x87 == 3,'actual PDE31')
            table_pa = pde & 0xfffff000
            table = physical('stack_table.bin',table_pa,4096)
            save(out/'physical_capture.json',{'directory':initial['CR3'],'stack_table':table_pa})
            # Bind each identity alias to actual captured physical page tables.
            tables = {table_pa:table}
            aliases = []
            for i in (1,2,3,4,6,7,8,9):
                pte = struct.unpack_from('<I',table,i*4)[0]
                frame = pte & 0xfffff000
                apde = struct.unpack_from('<I',directory,(frame>>22)*4)[0]
                require(apde & 0x87 == 3,'alias PDE')
                apa = apde & 0xfffff000
                if apa not in tables:
                    tables[apa] = physical(f'alias_table_{apa:08x}.bin',apa,4096)
                apte = struct.unpack_from('<I',tables[apa],((frame>>12)&1023)*4)[0]
                aliases.append({'physical':frame,'pde':apde,'pte':apte})
            save(out/'stack_aliases.json',aliases)
            # Retain opaque owner bytes for independent layout-aware review;
            # no invented repr(Rust) offsets or lease-identity claims.
            owner_symbols = {n:s for n,s in symbols.items() if 'retained_owner' in n and ('OWNER' in n or 'STATE' in n)}
            require(owner_symbols,'retained owner symbols absent')
            owner_capture = []
            for ordinal,(name,sym) in enumerate(sorted(owner_symbols.items())):
                require(0 < sym['size'] <= 4096,'bounded owner symbol')
                filename = f'owner_{ordinal}.bin'
                memory(filename,sym['address'],sym['size'])
                owner_capture.append({'symbol':name,'address':sym['address'],'size':sym['size'],'file':filename})
            save(out/'owner_capture.json',owner_capture)
            require(gdb.command('g') == raw_registers,'CPU advanced while captured')
            # Explicit, readback-verified, sole debugger mutation per boot.
            # No writes to ESP, CR3, tables, descriptors, TSSes or error words.
            gdb.set_registers(eip=address('f3_trigger_'+case))
            report['debugger_mutations'] = list(gdb.mutations)
            before = stop('f3_fault_'+case,'fault')
            memory('sgdt_str_sidt.bin',address('f3_wire_probe'),14)
            if case.endswith('_df'):
                entry = stop('f3_emergency_entry','emergency_entry')
                hw('emergency_entry')
                memory('emergency_error.bin',entry['esp'],4)
                stop('f3_emergency_terminal','emergency_terminal')
                memory('emergency_observed.bin',base+248,16)
                memory('post_task_gdt.bin',base,40)
                memory('post_emergency_tss.bin',base+144,104)
            elif case != 'ready':
                normalized = stop('f2_normalized','normalized')
                hw('normalized')
                memory('mandatory_prefix.bin',normalized['esp'],68)
            gdb.send('c')
            glog.write(json.dumps({'command':'c','reply':'asynchronous; QMP stop follows'})+'\n')
            glog.flush()
            marker = b'F3_DF_FATAL\n' if case.endswith('_df') else b'F2 fatal terminal\n'
            until = time.monotonic()+(0.2 if case == 'ready' else 5)
            while time.monotonic() < until:
                require(proc.poll() is None,'guest exited/reset before controlled halt')
                if case != 'ready' and marker in (out/'serial.txt').read_bytes():
                    break
                time.sleep(0.03)
            time.sleep(0.15)
            require(proc.poll() is None,'guest exited before terminal capture')
            qmp.call('stop')
            hw('terminal')
            report['checks'] = scenario_assertions(lambda name:(out/name).read_bytes(),symbols,case)
            require(report['checks'] and all(c['pass'] is True for c in report['checks']),'actual CPU assertions')
            report.update(overall='PASS',capture_complete=True)
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        if proc is not None:
            report['qemu_exit_before_cleanup'] = proc.poll()
            report['cleanup_action'] = 'kill_owned_Popen' if proc.poll() is None else 'already_exited'
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            report.update(qemu_exit=proc.returncode,owned_qemu_exited=proc.poll() is not None)
        for sock in sockets:
            sock.close()
        report['frozen_bytes'] = file_pins(out,('guest_report.json',))
        save(out/'guest_report.json',report)
    return report


def green_main():
    import tempfile
    from f3_evidence import CALL as green_call, SCENARIOS, RAMS, PLANNED, validate_matrix
    parser = argparse.ArgumentParser(description='F3 minimal actual Ring-0 matrix; not full acceptance')
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    require(args.output_dir.is_absolute(),'absolute output required')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='f3_minimal_',dir=args.output_dir)).resolve()
    result = {'schema':'rosti.f3-minimal-ring0.v1','overall':'HARNESS_FAIL','driver_exit':2,
              'build_exit':None,'baseline':False,'scenarios':[], 'hardware_cpl3':False,
              'full_f3_acceptance':False,'planned_only':PLANNED, 'invocation_dir':str(out)}
    snapshot = green_snapshot()
    save(out/'source_freeze_before.json',snapshot)
    result['source_sha256'] = snapshot
    try:
        review = ROOT/'test_results/phase11f3_gdt_tss/reviews/design_review_01.json'
        pins = json.loads(review.read_text())
        require(pins['verdict'] == 'APPROVE' and pins['blocker_count'] == 0,'design approval')
        design = (ROOT/pins['design_path']).read_bytes()
        require(sha(design) == pins['design_raw_sha256'],'design drift')
        # Design-reviewed preimplementation production hashes are historical;
        # do not pretend GREEN source must equal the deliberately RED source.
        (out/'design_review.json').write_bytes(review.read_bytes())
        (out/'design.md').write_bytes(design)
        (out/'driver.py').write_bytes(Path(__file__).read_bytes())
        (out/'validator.py').write_bytes((ROOT/'scripts/f3_evidence.py').read_bytes())
        stage,source = out/'fixture',out/'fixture/source'
        source.mkdir(parents=True)
        for name,digest in snapshot.items():
            frozen = (ROOT/name).read_bytes()
            require(sha(frozen) == digest,'source retention drift '+name)
            retained = out/'frozen_inputs'/name
            retained.parent.mkdir(parents=True,exist_ok=True)
            retained.write_bytes(frozen)
            if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
                raw = frozen
                require(sha(raw) == digest,'source copy drift '+name)
                dest = source/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(raw)
        mainpath = source/'src/main.rs'
        original = mainpath.read_bytes()
        anchor = b'    // stub: enable ps2 & interrupts'
        require(original.count(anchor) == 1,'unique postpaging anchor')
        assembly = green_assembly()
        changed = original.replace(anchor,green_call+anchor)+assembly
        require(changed.replace(green_call,b'',1).replace(assembly,b'',1) == original,'stripping equality')
        require(b'f3_probe' not in assembly and b'f3_ready:' not in assembly,'GREEN production-symbol collision')
        mainpath.write_bytes(changed)
        (out/'fixture_call.rs').write_bytes(green_call)
        (out/'fixture_assembly.rs').write_bytes(assembly)
        result.update(original_main_sha256=sha(original),injected_main_sha256=sha(changed),
                      assembly_sha256=sha(assembly),call_sha256=sha(green_call),stripping_equality=True)
        require(green_snapshot() == snapshot,'source changed before build')
        command = ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(stage/'build')]
        result.update(build_command=command,build_cwd=str(source))
        with (out/'build.log').open('wb') as log:
            build = subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        result['build_exit'] = build.returncode
        require(build.returncode == 0,'compile failure is not runtime RED/GREEN')
        kernel = out/'kernel.elf'
        shutil.copyfile(stage/'build/target/debug/kernel',kernel)
        result['kernel_sha256'] = sha(kernel.read_bytes())
        for ram in RAMS:
            for case in SCENARIOS:
                require(green_snapshot() == snapshot,'source drift before guest')
                row = green_guest(kernel,out/f'{case}_{ram}',case,ram)
                result['scenarios'].append(row)
                # Keep failures, but finish the exact bounded matrix. Never use
                # missing scenarios or a smaller RAM subset as a PASS.
                save(out/'running.json',result)
        require(len(result['scenarios']) == len(RAMS)*len(SCENARIOS) and all(r['overall'] == 'PASS' for r in result['scenarios']),'incomplete/failing actual matrix')
        result.update(overall='MINIMAL_RING0_GREEN',driver_exit=0)
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        after = green_snapshot()
        save(out/'source_freeze_after.json',after)
        result.update(source_freeze_stable=snapshot == after,source_input_count=len(snapshot))
        if snapshot != after:
            result.update(overall='HARNESS_FAIL',driver_exit=2,error='source freeze changed')
        # Pin source and evidence, not voluminous disposable cargo intermediates.
        result['frozen_bytes'] = file_pins(out,('report.json','running.json','validation.json'),('fixture/build/',))
        save(out/'report.json',result)
        if result['driver_exit'] == 0:
            try:
                validation = validate_matrix(result,out)
                save(out/'validation.json',validation)
            except Exception as exc:
                result.update(overall='HARNESS_FAIL',driver_exit=2,error='independent evidence validation: '+repr(exc))
                save(out/'report.json',result)
        print(json.dumps(result,indent=2))
    return result['driver_exit']


def main():
    return baseline_main() if '--baseline' in sys.argv[1:] else green_main()


if __name__ == '__main__':
    sys.exit(main())
