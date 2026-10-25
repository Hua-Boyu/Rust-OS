"""Disposable single-scenario F5 CPU probe; no canonical acceptance claim."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from b13_entry_inject import QEMU, elf_symbols
from f1_retained_guest import port, connect
from f2_exception_guest import source_snapshot, NAMES
from f3_gdt_guest import LoggedGdb, LoggedQmp
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
    (out / (label + '_hardware.txt')).write_text(text, encoding='ascii')
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


def capture(kernel, out, ram, scenario, layout):
    out.mkdir()
    symbols = elf_symbols(kernel)
    stores = storage_symbols(symbols)
    row = {'overall':'FAIL','scenario':IDENTITIES[scenario-1], 'scenario_integer':scenario,
           'ram_mib':ram, 'kernel_sha256':sha(kernel.read_bytes()), 'hardware_cpl3':False,
           'capture_complete':False, 'owned_qemu_exited':False,'checks':[],
           'debugger_mutations':[],'snapshots':{}}
    proc, sockets, streams = None, [], []
    def check(name, value):
        row['checks'].append({'name':name,'pass':bool(value)})
        need(value,name)
    try:
        gp, qp = port(), port()
        while gp == qp:
            qp = port()
        command = [str(QEMU),'-kernel',str(kernel),'-cpu','qemu32','-m',str(ram),'-smp','1',
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
        gdb, qmp = LoggedGdb(gs,glog), LoggedQmp(qs,qlog)
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
                need(lease is not None,'owned '+slot)
                identity(lease['addr'],4096)
                data[labelname] = physical(label+'_'+labelname+'.bin',lease['addr'],4096)
            gdtbase, limit = controls['GDT']
            identity(gdtbase,limit+1)
            data['gdt'] = memory(label+'_gdt.bin',gdtbase,limit+1)
            idtbase, idtlimit = controls['IDT']
            identity(idtbase,idtlimit+1)
            data['idt'] = memory(label+'_idt.bin',idtbase,idtlimit+1)
            for slot, role in [(3,'normal_tss'),(4,'emergency_tss')]:
                descriptor = data['gdt'][slot*8:slot*8+8]
                base = int.from_bytes(descriptor[2:4],'little') | descriptor[4]<<16 | descriptor[7]<<24
                identity(base,104)
                data[role] = memory(label+'_'+role+'.bin',base,104)
            meta = {'controls':controls,'decoded_owner':owner,'symbols':allstores,
                    'table_indices':list(tables),'capture_stable':True}
            save(out/(label+'_capture.json'),meta)
            row['snapshots'][label] = meta
            need(gdb.command('g') == (out/(label+'_register_packet.txt')).read_text(),'register stability')
            return data

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
        check('IRET_five_words',gdb.read(before_regs['esp'],20)==struct.pack('<5I',entry,0x2b,2,0x40400000,0x33))
        user_regs,user_cpu = stop(entry,'user_entry',3)
        check('hardware_CPL3_entry',user_cpu['CPL']==3 and user_regs['cs']==0x2b and user_regs['ss']==0x33
              and user_regs['esp']==0x40400000 and user_regs['eflags']==2)
        check('USER_segments',all(user_regs[n]==0x33 for n in ('ds','es','fs','gs')))
        check('retained_CR3_USER',user_cpu['CR3']==before_cpu['CR3'])
        row['hardware_cpl3']=True
        faultpc = entry+FAULTS[scenario-1][3]
        fault_regs,fault_cpu = stop(faultpc,'before_fault',3)
        check('actual_prefault_sentinels',fault_regs['eax']==0x2b and fault_regs['ebx']==0x5a17c0de
              and fault_regs['esp']==0x40400000 and fault_regs['eflags'] == 0x446)
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
        # All execute breakpoints are removed. Let the CPU enter its real HLT.
        qmp.call('cont')
        time.sleep(0.2)
        qmp.call('stop')
        until = time.monotonic()+5
        while qmp.call('query-status')['running']:
            need(time.monotonic()<until,'stable-stop deadline')
        stable = cpu(qmp,out,'stable_terminal')
        check('stable_actual_HLT_IF0',stable['CPL']==0 and stable['HLT']==1 and stable['EFL']&0x200==0
              and gdb.read(stable['EIP']-1,1)==b'\xf4')
        check('no_resume_or_duplicate_output',gdb.read(symbols['f5_record']['address'],256)==record_before
              and (out/'serial.txt').read_bytes()==serial)
        check('read_only_debugger',gdb.mutations==[])
        row.update(overall='PASS',capture_complete=True,debugger_mutations=gdb.mutations)
    except Exception as exc:
        row['error']=repr(exc)
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
        if errors or not row['owned_qemu_exited']: row['overall']='FAIL'
        save(out/'guest_report.json',row)
    return row


def main(argv=None):
    if sys.flags.optimize: raise SystemExit('optimized evidence execution refused')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',choices=tuple('ABCDEF'),required=True)
    parser.add_argument('--ram',type=int,choices=(128,512),required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    need(args.output_dir.is_absolute(),'absolute output required')
    out=args.output_dir.resolve()
    need(out.is_relative_to(ROOT/'test_results'),'task evidence directory required')
    out.mkdir(parents=True,exist_ok=False)
    scenario=ord(args.scenario)-64
    before=source_snapshot()
    report={'overall':'FAIL','driver_exit':1,'not_canonical_acceptance':True,
            'scenario':IDENTITIES[scenario-1],'ram_mib':args.ram,'source_sha256':before,
            'driver_sha256':sha(Path(__file__).read_bytes()),'build_exit':None}
    save(out/'source_before.json',before)
    try:
        # A copied fixture may add only this fixed call/probe; no user bytes,
        # EIP, page-table or permission writes through the debugger.
        call=b'    // F5_PROBE_CALL_BEGIN\n    unsafe { f5_fixture_baseline_probe(); }\n    // F5_PROBE_CALL_END\n'
        need(BASE_ASM.count(END)==1,'fixture CPUID tail')
        tail=f'4:\n and $-16,%esp\n sub $12,%esp\n push ${scenario}\n call f5_run_cpl3\n'.encode()
        assembly=BASE_ASM.replace(END,tail).replace(b'f4_',b'f5_fixture_')
        with tempfile.TemporaryDirectory(prefix='f5_',dir=ROOT/'dist') as temporary:
            stage=Path(temporary).resolve();source=stage/'s';source.mkdir()
            report['owned_stage']=str(stage)
            for name,digest in before.items():
                if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
                    raw=(ROOT/name).read_bytes();need(sha(raw)==digest,'source copy drift')
                    target=source/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            target=source/'src/main.rs';original=target.read_bytes();anchor=b'    // stub: enable ps2 & interrupts'
            need(original.count(anchor)==1,'main fixture anchor')
            changed=original.replace(anchor,call+anchor)+assembly
            need(changed.replace(call,b'',1).replace(assembly,b'',1)==original,'fixture stripping equality')
            target.write_bytes(changed)
            (out/'fixture_call.rs').write_bytes(call);(out/'fixture_assembly.rs').write_bytes(assembly)
            report.update(original_main_sha256=sha(original),injected_main_sha256=sha(changed),stripping_equality=True)
            command=['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(stage/'b')]
            report.update(build_command=command,build_cwd=str(source))
            with (out/'build.log').open('xb') as stream:
                result=subprocess.run(command,cwd=source,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
            report['build_exit']=result.returncode;need(result.returncode==0,'fixture build is not hardware failure')
            kernel=out/'kernel.elf';shutil.copyfile(stage/'b/target/debug/kernel',kernel)
            report['kernel_sha256']=sha(kernel.read_bytes())
            audit_path=Path(__file__).with_name('audit_emitted_01.py')
            spec=importlib.util.spec_from_file_location('f5_task_audit',audit_path);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
            old=Path(__file__).with_name('f2_before_macro_01.elf')
            need(sha(old.read_bytes())=='770f18590e186465fcb301f8d09c044d1055707027f0fa9ba596d0e2a1f33fcc','pre-macro ELF pin')
            need(audit.run(kernel,old,out/'emitted')==0,'emitted pre-hardware audit')
            layout=extract(kernel);save(out/'target_layout.json',layout)
            row=capture(kernel,out/'guest',args.ram,scenario,layout)
            report['guest']=row
            need(row['overall']=='PASS' and row['owned_qemu_exited'],'incomplete CPU proof or cleanup')
            report.update(overall='PASS',driver_exit=0)
    except Exception as exc:
        report['error']=repr(exc)
    finally:
        after=source_snapshot();save(out/'source_after.json',after)
        report['source_freeze_stable']=before==after
        if before!=after: report.update(overall='FAIL',driver_exit=1,error='source drift')
        report['frozen_bytes']={p.relative_to(out).as_posix():sha(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file()}
        save(out/'report.json',report)
        print(json.dumps({k:report.get(k) for k in ('overall','driver_exit','scenario','ram_mib','build_exit','source_freeze_stable','error')},indent=2))
    return report['driver_exit']


if __name__=='__main__':
    raise SystemExit(main())
