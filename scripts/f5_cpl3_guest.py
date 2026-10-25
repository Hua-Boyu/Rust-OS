"""Invocation-owned one-shot F5 CPL3 fixture matrix; never canonical acceptance.

Capture foundation: task-local run_cpl3_probe_01.py. No debugger writes.
CLI admission runs before output, locks, builds or guest entry.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')
sys.path.insert(0, str(ROOT / 'scripts'))
from b13_entry_inject import QEMU, elf_symbols
from f1_retained_guest import port, connect
from f2_exception_guest import source_snapshot as canonical_snapshot, NAMES
from b13_entry_inject import Gdb
from f1_capture import Qmp
from f4_user_guest import ASM as BASE_ASM
from f4_ready_guest import END
from f4_evidence import storage_symbols, decode_owner
from f4_dwarf import extract

IDENTITIES = ('f5_cpl3_A_entry', 'f5_cpl3_B_ro_write', 'f5_cpl3_C_supervisor_read',
              'f5_cpl3_D_hlt', 'f5_cpl3_E_io_denied', 'f5_cpl3_F_guard_read')
FAULTS = ((6,0,0,12),(14,7,0x40000800,12),(14,5,0x07c01000,12),
          (13,0,0,12),(13,0,0,12),(14,4,0x403fe000,12))
SNIPPETS = ('31c0668cc868dec0175a5bfd0f0b0f0b',
            '31c0668cc868dec0175a5bfdc605000800407e0f0b',
            '31c0668cc868dec0175a5bfd8b0d0010c0070f0b',
            '31c0668cc868dec0175a5bfdf40f0b',
            '31c0668cc868dec0175a5bfde6800f0b',
            '31c0668cc868dec0175a5bfd8b0d00e03f400f0b')


class HardwareAssertion(RuntimeError):
    pass


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def image():
    raw = bytearray(4096)
    raw[:4] = bytes.fromhex('0f0bebfc')
    raw[2048:2059] = b'F4-RO-DATA\0'
    for slot, text in enumerate(SNIPPETS):
        payload = bytes.fromhex(text)
        raw[256 + slot*64:256 + slot*64+len(payload)] = payload
    return bytes(raw)


def cpu(qmp, out, label):
    text = qmp.call('human-monitor-command', **{'command-line': 'info registers'})
    # Preserve QMP wire newlines exactly (Windows text mode doubles CRLF).
    (out / (label + '_hardware.txt')).write_bytes(text.encode('ascii'))
    result = {n:int(v,16) for n,v in re.findall(r'\b(CR0|CR2|CR3|CR4|EIP|EFL)=([0-9a-fA-F]+)',text)}
    need(set(result) == {'CR0','CR2','CR3','CR4','EIP','EFL'}, 'CPU control capture')
    for name in ('GDT','IDT'):
        match = re.search(name+r'=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
        need(match is not None, 'CPU '+name)
        result[name] = [int(v,16) for v in match.groups()]
    match = re.search(r'\bTR\s*=([0-9a-fA-F]+)',text)
    need(match is not None, 'CPU TR')
    result['TR'] = int(match[1],16)
    need(result['CR0'] & 0x80010001 == 0x80010001
         and result['CR4'] & 0x00a00030 == 0
         and 'EFER=0000000000000000' in text, 'non-PAE/non-NX supported CPU profile')
    need(result['CR3'] != 0 and result['CR3'] & 4095 == 0, 'aligned CR3')
    result['CPL'] = int(re.search(r'CPL=([0-3])', text)[1])
    result['HLT'] = int(re.search(r'HLT=([01])', text)[1])
    return result


class LoggedGdb(Gdb):
    def __init__(self,sock,log,sequence):
        super().__init__(sock)
        self.log,self.sequence=log,sequence

    def command(self,text):
        if getattr(self,'deadline',None) is not None:
            remaining=self.deadline-time.monotonic()
            need(remaining>0,'guest deadline')
            self.sock.settimeout(min(25,remaining))
        start=time.monotonic_ns()
        reply=super().command(text)
        self.sequence[0]+=1
        self.log.write(json.dumps({'seq':self.sequence[0],'started_ns':start,'ended_ns':time.monotonic_ns(),
                                   'command':text,'reply':reply})+'\n')
        self.log.flush()
        return reply


class LoggedQmp(Qmp):
    def __init__(self,sock,log,sequence):
        self.log,self.sequence=log,sequence
        super().__init__(sock)

    def call(self,command,**arguments):
        if getattr(self,'deadline',None) is not None:
            remaining=self.deadline-time.monotonic()
            need(remaining>0,'guest deadline')
            self.deadline_socket.settimeout(min(10,remaining))
        start=time.monotonic_ns()
        reply=super().call(command,**arguments)
        self.sequence[0]+=1
        self.log.write(json.dumps({'seq':self.sequence[0],'started_ns':start,'ended_ns':time.monotonic_ns(),
                                   'command':command,'arguments':arguments,'reply':reply})+'\n')
        self.log.flush()
        return reply


def wait_stable_interval(started_ns):
    """Require measured elapsed time even if the host sleep wakes early."""
    deadline = started_ns + 200000000
    while True:
        remaining = deadline - time.monotonic_ns()
        if remaining <= 0:
            return
        time.sleep(remaining / 1000000000)


def capture(kernel, out, ram, scenario, layout, bios):
    out.mkdir()
    symbols = elf_symbols(kernel)
    stores = storage_symbols(symbols)
    row = {'overall':'FAIL','scenario':IDENTITIES[scenario-1], 'scenario_integer':scenario,
           'ram_mib':ram, 'kernel_sha256':sha(kernel.read_bytes()), 'hardware_cpl3':False,
           'capture_complete':False, 'owned_qemu_exited':False,'checks':[],
           'failure_class':'INFRASTRUCTURE_INCOMPLETE',
           'debugger_mutations':[],'snapshots':{}}
    proc, sockets, streams = None, [], []
    def check(name, value):
        row['checks'].append({'name':name,'pass':bool(value)})
        if not value:
            raise HardwareAssertion(name)
    try:
        gp, qp = port(), port()
        while gp == qp:
            qp = port()
        command = [str(QEMU),'-bios',str(bios),'-kernel',str(kernel),'-cpu','qemu32','-m',str(ram),'-smp','1',
                   '-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot',
                   '-serial','file:'+str(out/'serial.txt'),'-d','int,guest_errors','-D',str(out/'qemu.log'),
                   '-S','-gdb',f'tcp:127.0.0.1:{gp}','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off']
        row['command'] = command
        err = (out/'stderr.txt').open('xb'); streams.append(err)
        glog = (out/'gdb.jsonl').open('x'); streams.append(glog)
        qlog = (out/'qmp.jsonl').open('x'); streams.append(qlog)
        proc = subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=err)
        row['owned_pid'] = proc.pid
        deadline = time.monotonic()+180
        gs = connect(gp,proc,deadline); sockets.append(gs)
        qs = connect(qp,proc,deadline); sockets.append(qs)
        gs.settimeout(25); qs.settimeout(10)
        sequence=[0]
        gdb, qmp = LoggedGdb(gs,glog,sequence), LoggedQmp(qs,qlog,sequence)
        gdb.deadline = qmp.deadline = deadline
        qmp.deadline_socket = qs
        gdb.command('?')
        row['qemu_version'] = qmp.call('query-version')

        def memory(name, address, size):
            raw = b''.join(gdb.read(address+i,min(512,size-i)) for i in range(0,size,512))
            (out/name).write_bytes(raw)
            return raw

        def physical(name, address, size):
            need(address >= 4096 and size > 0 and address+size <= ram*1024*1024,'physical RAM bound')
            target = out/name
            qmp.call('pmemsave',val=address,size=size,filename=target.as_posix())
            raw = target.read_bytes()
            need(len(raw)==size,'physical extent')
            return raw

        def stop(address, label, cpl):
            need(gdb.command(f'Z1,{address:x},1')=='OK','install '+label)
            reply = gdb.command('c')
            need(reply.startswith(('T05','S05')),'debug stop '+label)
            packet = gdb.command('g')
            (out/(label+'_register_packet.txt')).write_text(packet)
            regs = dict(zip(NAMES,struct.unpack_from('<16I',bytes.fromhex(packet))))
            need(regs['eip']==address and regs['cs'] & 3 == cpl,'exact EIP/CPL '+label)
            need(qmp.call('query-status')['running'] is False,'paused '+label)
            need(gdb.command(f'z1,{address:x},1')=='OK','remove '+label)
            return regs, cpu(qmp,out,label)

        def snapshot(label, controls):
            directory = physical(label+'_directory.bin',controls['CR3'],4096)
            need(directory == physical(label+'_directory_repeat.bin',controls['CR3'],4096),'stable directory')
            dp = struct.unpack('<1024I',directory)
            tables = {}
            for index, pde in enumerate(dp):
                if pde & 1:
                    need(pde & 0x80 == 0,'ordinary tables')
                    raw = physical(f'{label}_table_{index:03d}.bin',pde & 0xfffff000,4096)
                    need(raw == physical(f'{label}_table_{index:03d}_repeat.bin',pde & 0xfffff000,4096),'stable table')
                    tables[index] = raw
            def identity(address,size):
                for page in range(address & ~4095,(address+size+4095)&~4095,4096):
                    pde = dp[page >> 22]
                    need(pde & 0x87 == 3,'metadata supervisor PDE')
                    pte = struct.unpack_from('<I',tables[page >> 22],((page >> 12)&1023)*4)[0]
                    need(pte & 0xfffff007 == page | 3,'metadata supervisor identity')
            data = {'directory':directory,'tables':tables,'controls':controls}
            allstores = {**stores, **{name:symbols[name] for name in
                         ('f3_context','f5_gdt','f5_record','f5_expect','f5_latch')}}
            for name, sym in allstores.items():
                identity(sym['address'],sym['size'])
                raw = physical(label+'_'+name+'.bin',sym['address'],sym['size'])
                need(raw == physical(label+'_'+name+'_repeat.bin',sym['address'],sym['size']),'stable metadata '+name)
                data[name] = raw
            owner = decode_owner(data['owner'],layout)
            data['decoded_owner'] = owner
            for slot, labelname in [('payload','code'),('user_stack','stack')]:
                lease = owner['slots'][slot]
                if lease is None:
                    continue
                identity(lease['addr'],4096)
                data[labelname] = physical(label+'_'+labelname+'.bin',lease['addr'],4096)
                need(data[labelname] == physical(label+'_'+labelname+'_repeat.bin',lease['addr'],4096), 'stable payload/stack')
            gdtbase, limit = controls['GDT']
            identity(gdtbase,limit+1)
            data['gdt'] = physical(label+'_gdt.bin',gdtbase,limit+1)
            idtbase, idtlimit = controls['IDT']
            identity(idtbase,idtlimit+1)
            data['idt'] = physical(label+'_idt.bin',idtbase,idtlimit+1)
            if controls['TR'] == 0x18:
                for slot, role in [(3,'normal_tss'),(4,'emergency_tss')]:
                    descriptor = data['gdt'][slot*8:slot*8+8]
                    base = int.from_bytes(descriptor[2:4],'little') | descriptor[4]<<16 | descriptor[7]<<24
                    identity(base,104)
                    data[role] = physical(label+'_'+role+'.bin',base,104)
            meta = {'controls':controls,'decoded_owner':owner,'symbols':allstores,
                    'table_indices':list(tables),'capture_stable':True}
            save(out/(label+'_capture.json'),meta)
            row['snapshots'][label] = meta
            need(gdb.command('g') == (out/(label+'_register_packet.txt')).read_text(),'register stability')
            return data

        initial_regs, initial_cpu = stop(symbols['f5_fixture_initial']['address'],'initial',0)
        initial = snapshot('initial',initial_cpu)
        entry = 0x40000100+(scenario-1)*64
        before_regs, before_cpu = stop(symbols['f5_before_iret']['address'],'before_iret',0)
        before = snapshot('before_iret',before_cpu)
        check('installed_GDTR55_TR18',before_cpu['GDT']==[symbols['f5_gdt']['address'],55] and before_cpu['TR']==0x18)
        check('original_five_descriptors_preserved',before['gdt'][:40]==before['f3_context'][:40])
        check('exact_new_USER_descriptors',before['gdt'][40:56]==struct.pack('<QQ',0x00cffb000000ffff,0x00cff3000000ffff))
        # USER data has its accessed bit set by the already-executed segment loads.
        check('normal_ESP0_SS0_iomap',struct.unpack_from('<II',before['normal_tss'],4)==(0x07c05000,16) and struct.unpack_from('<H',before['normal_tss'],102)[0]==104)
        check('code_image_before_USER_exact',before['code']==image())
        check('stack_before_USER_zero',before['stack']==bytes(4096))
        check('sealed_before_USER',before['state'][0]==2)
        check('IRET_five_words',memory('iret_words.bin',before_regs['esp'],20)==struct.pack('<5I',entry,0x2b,2,0x40400000,0x33))
        user_regs,user_cpu = stop(entry,'user_entry',3)
        check('hardware_CPL3_entry',user_cpu['CPL']==3 and user_regs['cs']==0x2b and user_regs['ss']==0x33
              and user_regs['esp']==0x40400000 and user_regs['eflags']==2)
        check('USER_segments',all(user_regs[n]==0x33 for n in ('ds','es','fs','gs')))
        check('retained_CR3_USER',user_cpu['CR3']==before_cpu['CR3'])
        row['hardware_cpl3']=True
        faultpc = entry+FAULTS[scenario-1][3]
        fault_regs,fault_cpu = stop(faultpc,'before_fault',3)
        check('actual_prefault_sentinels',fault_regs['eax']==0x2b and fault_regs['ebx']==0x5a17c0de
              and fault_regs['esp']==0x40400000 and fault_regs['eflags'] in (0x446,0x456))
        memory('fault_instruction.bin',faultpc,len(bytes.fromhex(SNIPPETS[scenario-1]))-12)
        bridge_regs, bridge_cpu = stop(symbols['f5_bridge']['address'],'bridge',0)
        memory('mandatory_frame.bin',0x07c04fb4,76)
        memory('bridge_call.bin',bridge_regs['esp'],8)
        final_regs,final_cpu = stop(symbols['f5_terminal']['address'],'terminal',0)
        terminal = snapshot('terminal',final_cpu)
        record = struct.unpack('<64I',terminal['f5_record'])
        vector,error,cr2,_ = FAULTS[scenario-1]
        frame = record[16:35]
        check('one_matching_PASS_record',record[:3]==(0x46354350,scenario,1) and int.from_bytes(terminal['f5_latch'],'little')==1)
        check('exact_frame_geometry',record[3:5]==(0x07c04fb4,0x07c04f9c) and frame[7]==record[3]+48)
        check('exact_exception_oracle',frame[12:15]==(vector,error,faultpc) and (vector!=14 or record[6]==cr2))
        check('saved_origin_tail_flags',frame[0:4]==(0x33,)*4 and frame[8]==0x5a17c0de
              and frame[11]==0x2b and frame[15]&65535==0x2b and frame[16]&~0x10==0x10446
              and frame[17]==0x40400000 and frame[18]&65535==0x33)
        check('kernel_context_restored',record[10:16]==(8,16,16,16,16,16) and record[9]&0x600==0)
        check('same_CR3_every_checkpoint',before_cpu['CR3']==user_cpu['CR3']==fault_cpu['CR3']==final_cpu['CR3']==record[7])
        check('retained_owner_allocator_TSS',all(before[n]==terminal[n] for n in ('owner','allocator','normal_tss','emergency_tss')))
        check('code_RO_preserved',terminal['code']==before['code'])
        check('stack_cookie_only',terminal['stack']==bytes(4092)+struct.pack('<I',0x5a17c0de))
        check('terminal_owner_state',terminal['state'][0]==3)
        check('page_table_inventory_preserved',before['tables'].keys()==terminal['tables'].keys())
        for label, old, new, mask in [('directory',before['directory'],terminal['directory'],0x20),
                                      *[(f'table_{i}',before['tables'][i],terminal['tables'][i],0x60) for i in before['tables']]]:
            check('only_hardware_AD_'+label,all((a^b)&~mask==0 for a,b in zip(struct.unpack('<1024I',old),struct.unpack('<1024I',new))))
        marker = f'F5 {chr(64+scenario)} PASS CPL3 terminal\n'.encode()
        serial = (out/'serial.txt').read_bytes()
        check('unique_exact_terminal_marker',serial.count(marker)==1 and serial.endswith(marker) and b'F5 FAIL' not in serial)
        record_before = terminal['f5_record']
        trace_before = (out/'qemu.log').read_bytes()
        (out/'trace_before_stable.bin').write_bytes(trace_before)
        (out/'serial_before_stable.bin').write_bytes(serial)
        row['stable_interval_seconds'] = 0.2
        # All execute breakpoints are removed. Let the CPU enter its real HLT.
        qmp.call('cont')
        wait_stable_interval(time.monotonic_ns())
        qmp.call('stop')
        until = time.monotonic()+5
        while qmp.call('query-status')['running']:
            need(time.monotonic()<until,'stable-stop deadline')
        stable = cpu(qmp,out,'stable_terminal')
        check('stable_actual_HLT_IF0',stable['CPL']==0 and stable['HLT']==1 and stable['EFL']&0x200==0
              and gdb.read(stable['EIP']-1,1)==b'\xf4')
        memory('stable_record.bin',symbols['f5_record']['address'],256)
        memory('stable_halt.bin',stable['EIP']-1,3)
        check('no_resume_or_duplicate_output',(out/'stable_record.bin').read_bytes()==record_before
              and (out/'qemu.log').read_bytes()==trace_before
              and (out/'serial.txt').read_bytes()==serial)
        check('read_only_debugger',gdb.mutations==[])
        row.update(overall='PASS',capture_complete=True,debugger_mutations=gdb.mutations,failure_class=None)
    except Exception as exc:
        row['error']=repr(exc)
        row['failure_class']='HARDWARE_PROPERTY_ASSERTION' if isinstance(exc,HardwareAssertion) else 'INFRASTRUCTURE_INCOMPLETE'
    finally:
        errors=[]
        if proc is not None:
            row['qemu_exit_before_cleanup']=proc.poll()
            try:
                if proc.poll() is None: proc.kill()
                proc.wait(timeout=10)
            except Exception as exc:
                errors.append(repr(exc))
                try:
                    proc.kill();proc.wait(timeout=10)
                except Exception as retry: errors.append(repr(retry))
            row.update(qemu_exit=proc.poll(),owned_qemu_exited=proc.poll() is not None)
        if proc is None or proc.poll() is not None:
            for sock in sockets:
                try: sock.close()
                except Exception as exc: errors.append(repr(exc))
        for stream in streams:
            try: stream.close()
            except Exception as exc: errors.append(repr(exc))
        row['cleanup_errors']=errors
        if errors or not row['owned_qemu_exited']:
            row.update(overall='FAIL',failure_class='OWNED_PROCESS_CLEANUP')
        from f5_cpl3_evidence import tree_pins
        row['frozen_bytes'] = tree_pins(out, ('guest_report.json',))
        save(out/'guest_report.json',row)
    return row




# No alternate grammar: this exact function is passed directly to argparse.
def parse_scenario(value):
    if type(value) is not str or value not in ('1','2','3','4','5','6'):
        raise argparse.ArgumentTypeError('scenario must be exactly one ASCII digit 1..6')
    return ord(value)-ord('0')


scenario_type = parse_scenario
_parse_scenario = parse_scenario


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--scenario', type=parse_scenario)
    parser.add_argument('--output-dir', type=Path, required=True)
    tokens = list(sys.argv[1:] if argv is None else argv)
    seen = set()
    for token in tokens:
        if type(token) is not str:
            parser.error('CLI arguments must be strings')
        if token.startswith('--'):
            flag = token.split('=',1)[0]
            if flag in seen:
                parser.error('duplicate option '+flag)
            seen.add(flag)
    args = parser.parse_args(tokens)
    if not args.output_dir.is_absolute():
        parser.error('--output-dir must be absolute')
    return args


def source_snapshot():
    result = canonical_snapshot()
    # Include the complete Python import/build-policy surface, not just F5 names.
    for path in sorted((ROOT/'scripts').rglob('*.py')):
        result[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    for name in ('design.md','harness_contract_01.json','entry_design_amendment_01.md'):
        path = ROOT/'test_results/phase11f5_cpl3_proof'/name
        result[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return dict(sorted(result.items()))


def fixture_assembly(scenario):
    need(type(scenario) is int and 1 <= scenario <= 6,'typed scenario')
    need(BASE_ASM.count(END)==1,'fixture CPUID tail')
    tail = (f'4:\n.global f5_fixture_initial\nf5_fixture_initial:\n'
            f' and $-16,%esp\n sub $12,%esp\n push ${scenario}\n call f5_run_cpl3\n').encode()
    return BASE_ASM.replace(END,tail).replace(b'f4_',b'f5_fixture_')


CALL = b'    // F5_PROBE_CALL_BEGIN\n    unsafe { f5_fixture_baseline_probe(); }\n    // F5_PROBE_CALL_END\n'


def transformations(originals, scenario):
    result = dict(originals)
    original = originals['src/main.rs']
    anchor = b'    // stub: enable ps2 & interrupts'
    need(original.count(anchor)==1,'main fixture anchor')
    assembly = fixture_assembly(scenario)
    changed = original.replace(anchor,CALL+anchor)+assembly
    need(changed.replace(CALL,b'',1).replace(assembly,b'',1)==original,'fixture stripping equality')
    result['src/main.rs'] = changed
    return result


def run_audit(elf, output, before):
    # Shared audit CLI is owned by the terminal-audit integration, not this driver.
    command = [sys.executable,'-B',str(ROOT/'scripts/f5_terminal_audit.py'),
               '--elf',str(elf),'--before',str(before),'--output-dir',str(output)]
    with output.with_suffix('.log').open('xb') as stream:
        result = subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    need(result.returncode==0,'exact ELF terminal audit failed')
    from f5_cpl3_evidence import validate_audit
    validate_audit(output,elf,before)


def build_fixture(source, target, log):
    command = ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),
               '--target-dir',str(target)]
    with log.open('xb') as stream:
        result = subprocess.run(command,cwd=source,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
    need(result.returncode==0,'fixture build failed (infrastructure, not hardware RED)')
    return command, result.returncode


class RunnerLock:
    """OS-held nonblocking lock; retain pathname, never unlink or kill others."""
    def __enter__(self):
        self.stream = (ROOT/'dist/f5_cpl3_runner.lock').open('a+b')
        try:
            self.stream.seek(0)
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            self.stream.close()
            raise
        return self

    def __exit__(self,*unused):
        self.stream.close()


def run(args):
    from f5_cpl3_evidence import tree_pins, validate
    out = args.output_dir.resolve()
    # mkdir is exclusive: no old report/artifact is rewritten or cleaned up.
    out.mkdir(parents=True,exist_ok=False)
    before = source_snapshot()
    report = {'schema':'rosti.f5-cpl3-matrix.v1','overall':'FAIL','driver_exit':1,
              'not_canonical_acceptance':True,'full_f5_matrix':args.scenario is None,
              'selected_scenario':args.scenario,'builds':{},'guests':[], 'checks':[]}
    save(out/'source_before.json',before)
    try:
        from f5_cpl3_evidence import check_authority
        originals = {}
        for name,digest in before.items():
            raw = (ROOT/name).read_bytes()
            need(sha(raw)==digest,'source copy drift '+name)
            target = out/'source'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            originals[name] = raw
        check_authority(out/'source')
        baseline = ROOT/'test_results/phase11f5_cpl3_proof/f2_before_macro_01.elf'
        need(sha(baseline.read_bytes())=='770f18590e186465fcb301f8d09c044d1055707027f0fa9ba596d0e2a1f33fcc','historical baseline ELF pin')
        (out/'authority').mkdir()
        baseline_copy=out/'authority/f2_before_macro_01.elf'
        shutil.copyfile(baseline,baseline_copy)
        production = ROOT/'target/target/debug/kernel'
        (out/'production').mkdir()
        shutil.copyfile(production,out/'production/kernel.elf')
        run_audit(out/'production/kernel.elf',out/'production/emitted',baseline_copy)
        firmware = next((p for p in (Path(QEMU).parent/'share/bios-256k.bin',
                         Path(QEMU).parent/'share/qemu/bios-256k.bin') if p.is_file()),None)
        need(firmware is not None,'QEMU BIOS discovery failed')
        (out/'firmware').mkdir()
        shutil.copyfile(firmware,out/'firmware/bios-256k.bin')
        save(out/'toolchain.json',{'qemu_path':str(QEMU),'qemu_sha256':sha(Path(QEMU).read_bytes()),
                                  'bios_sha256':sha(firmware.read_bytes())})
        (out/'toolchain').mkdir()
        shutil.copyfile(QEMU,out/'toolchain/qemu-system-i386.exe')
        scenarios = range(1,7) if args.scenario is None else (args.scenario,)
        for scenario in scenarios:
            letter = chr(64+scenario)
            folder = out/'builds'/letter
            folder.mkdir(parents=True)
            transformed = transformations(originals,scenario)
            changes = {n:r for n,r in transformed.items() if r != originals[n]}
            manifest = {}
            for name,raw in changes.items():
                target = folder/'transformed'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(raw)
                manifest[name] = {'original_sha256':before[name],'transformed_sha256':sha(raw)}
            save(folder/'transforms.json',manifest)
            # Short disposable path avoids Windows linker MAX_PATH; never remove evidence.
            with tempfile.TemporaryDirectory(prefix='f5_',dir=ROOT/'dist') as temporary:
                stage = Path(temporary).resolve()
                source = stage/'s'
                source.mkdir()
                for name,raw in transformed.items():
                    if name.startswith(('src/','crates/','system/')) or name in (
                        'Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
                        target = source/name
                        target.parent.mkdir(parents=True,exist_ok=True)
                        target.write_bytes(raw)
                command,code = build_fixture(source,stage/'b',folder/'build.log')
                shutil.copyfile(stage/'b/target/debug/kernel',folder/'kernel.elf')
                kernel = folder/'kernel.elf'
                run_audit(kernel,folder/'emitted',baseline_copy)
                layout = extract(kernel)
                save(folder/'target_layout.json',layout)
                save(folder/'symbols.json',elf_symbols(kernel))
                report['builds'][letter] = {'scenario_integer':scenario,'build_exit':code,
                    'build_command':command,'build_cwd':str(source),'owned_stage':str(stage),
                    'kernel_sha256':sha(kernel.read_bytes())}
            for ram in (128,512):
                name = IDENTITIES[scenario-1]+'_'+str(ram)
                need(source_snapshot()==before,'source drift before guest')
                need(sha(Path(QEMU).read_bytes())==sha((out/'toolchain/qemu-system-i386.exe').read_bytes()),'QEMU drift')
                row = capture(kernel,out/name,ram,scenario,layout,out/'firmware/bios-256k.bin')
                report['guests'].append({'scenario':row['scenario'],'ram_mib':ram,
                    'scenario_integer':scenario,'overall':row['overall'],
                    'kernel_sha256':row['kernel_sha256'],'report':name+'/guest_report.json'})
                if row['overall']!='PASS':
                    report['failure_class']=row['failure_class']
                    raise RuntimeError('incomplete CPU capture or cleanup')
        report.update(overall='PASS',driver_exit=0)
    except Exception as exc:
        report.update(error=repr(exc))
        report.setdefault('failure_class','INFRASTRUCTURE_INCOMPLETE')
    finally:
        after = source_snapshot()
        save(out/'source_after.json',after)
        report['source_freeze_stable'] = before==after
        if before!=after:
            report.update(overall='FAIL',driver_exit=1,error='source drift')
        report['checks'] = [{'name':'source_freeze_stable','pass':before==after}]
        report['frozen_bytes'] = tree_pins(out,('report.json',))
        save(out/'report.json',report)
    if report['overall']=='PASS':
        try:
            validate(out,expected_source=before,require_full=args.scenario is None)
        except Exception as exc:
            # Preserve immutable report; failure is an additional exclusive artifact.
            save(out/'readback_failure.json',{'overall':'FAIL','error':repr(exc)})
            return 1
    print(json.dumps({'overall':report['overall'],'driver_exit':report['driver_exit'],
                      'report':str(out/'report.json')}))
    return report['driver_exit']


def main(argv=None):
    args = parse_args(argv)
    with RunnerLock():
        return run(args)


if __name__=='__main__':
    raise SystemExit(main())
