"""Complete bounded F4 Ring0 hardware matrix (six scenarios at 128/512 MiB).

Disposable short dist staging only. No production output writes, no CPL3.
Builds/boots only when explicitly invoked, never on import. Keep stdout outside
this invocation's frozen tree. Offline readback: python -B scripts/f4_evidence.py REPORT.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')

from b13_entry_inject import QEMU, elf_symbols
from f1_retained_guest import port, connect
from f2_exception_guest import source_snapshot, NAMES
from f3_gdt_guest import LoggedGdb, LoggedQmp
from f3_evidence import hardware, strict_json
from f4_dwarf import extract
from f4_evidence import (SCENARIOS, RAMS, DESIGN, REVIEW, DISPOSITION, DESIGN_SHA,
                         REVIEW_SHA, FAULTS, need, sha, tree_pins, transformations,
                         storage_symbols, decode_owner, validate_guest, validate)

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def inputs():
    """Canonical independently enumerated source set plus exact local dependencies."""
    snapshot = source_snapshot()
    for name in ('scripts/f4_arena_guest.py','scripts/f4_evidence.py','scripts/f4_dwarf.py','scripts/f4_ready_guest.py','scripts/f4_user_guest.py','scripts/f3_gdt_guest.py','scripts/f3_evidence.py','scripts/f2_exception_guest.py','scripts/f1_retained_guest.py','scripts/f1_capture.py','scripts/b13_entry_inject.py'):
        snapshot[name] = sha((ROOT/name).read_bytes())
    return dict(sorted(snapshot.items()))


def build_fixture(out, source_pins, variant):
    folder = out/'builds'/variant
    folder.mkdir(parents=True, exist_ok=False)
    report = {'variant':variant,'build_exit':None,'kernel_sha256':None}
    try:
        originals = {name:(out/'source'/name).read_bytes() for name in source_pins}
        transformed = transformations(originals,variant)
        changes = {n:raw for n,raw in transformed.items() if raw != originals[n]}
        save(folder/'transforms.json',{n:{'original_sha256':sha(originals[n]),'transformed_sha256':sha(raw)} for n,raw in changes.items()})
        for name, raw in changes.items():
            write(folder/'transformed'/name,raw)
        # Each variant is built in an independently owned short staging tree.
        # TemporaryDirectory removes it only after cargo returns; kernel/source
        # bytes needed for readback live under the immutable evidence tree.
        with tempfile.TemporaryDirectory(prefix='f4_',dir=ROOT/'dist') as tmp:
            stage = Path(tmp).resolve()
            source = stage/'s'
            source.mkdir()
            report['owned_stage'] = str(stage)
            for name,raw in transformed.items():
                if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
                    need(sha(originals[name]) == source_pins[name], 'retained source copy drift '+name)
                    write(source/name,raw)
            command = ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(stage/'b')]
            report.update(build_command=command,build_cwd=str(source))
            with (folder/'build.log').open('xb') as log:
                result = subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=600)
            report['build_exit'] = result.returncode
            need(result.returncode == 0, 'fixture build failed: '+variant)
            kernel = folder/'kernel.elf'
            shutil.copyfile(stage/'b/target/debug/kernel',kernel)
            report['kernel_sha256'] = sha(kernel.read_bytes())
            save(folder/'symbols.json',elf_symbols(kernel))
            save(folder/'target_layout.json',extract(kernel))
        report['stage_removed'] = not stage.exists()
        need(report['stage_removed'], 'short staging cleanup failed')
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        save(folder/'build_report.json',report)
    need(report.get('stage_removed') is True and report['build_exit'] == 0 and report['kernel_sha256'], 'incomplete build '+repr(report))
    return report


class Session:
    """One owned Popen; sockets are never closed until kill/wait is confirmed."""
    def __init__(self, kernel, output, ram, row):
        self.kernel, self.out, self.ram, self.row = kernel, output, ram, row
        self.symbols = elf_symbols(kernel)
        self.layout = strict_json(kernel.parent/'target_layout.json')
        self.stores = storage_symbols(self.symbols)
        self.sockets = []
        self.streams = []
        self.proc = None
        self.gdb = self.qmp = None
        self.deadline = time.monotonic()+180

    def open(self):
        gp,qp = port(),port()
        while gp == qp:
            qp = port()
        firmware = self.kernel.parents[2]/'firmware/bios-256k.bin'
        cmd = [str(QEMU),'-bios',str(firmware),'-kernel',str(self.kernel),'-cpu','qemu32','-m',str(self.ram),'-smp','1','-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot','-serial','file:'+str(self.out/'serial.txt'),'-d','int,guest_errors','-D',str(self.out/'qemu.log'),'-S','-gdb',f'tcp:127.0.0.1:{gp}','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off']
        self.row['command'] = cmd
        err = (self.out/'stderr.txt').open('xb')
        self.streams.append(err)
        glog = (self.out/'gdb.jsonl').open('x',encoding='utf-8')
        self.streams.append(glog)
        qlog = (self.out/'qmp.jsonl').open('x',encoding='utf-8')
        self.streams.append(qlog)
        self.proc = subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=err)
        self.row['owned_pid'] = self.proc.pid
        # Append each successful connection immediately: partial-connect failure
        # must not lose the GDB socket or release a still-owned guest.
        gs = connect(gp,self.proc,self.deadline)
        self.sockets.append(gs)
        qs = connect(qp,self.proc,self.deadline)
        self.sockets.append(qs)
        gs.settimeout(25)
        qs.settimeout(10)
        self.gdb, self.qmp = LoggedGdb(gs,glog), LoggedQmp(qs,qlog)
        self.gdb.deadline = self.qmp.deadline = self.deadline
        self.qmp.deadline_socket = qs
        self.gdb.command('?')
        self.row['qemu_version'] = self.qmp.call('query-version')

    def close(self):
        errors = []
        if self.proc is not None:
            self.row['qemu_exit_before_cleanup'] = self.proc.poll()
            self.row['cleanup_action'] = 'kill_owned_Popen' if self.proc.poll() is None else 'already_exited'
            try:
                if self.proc.poll() is None:
                    self.proc.kill()
                self.proc.wait(timeout=10)
            except Exception as exc:
                errors.append(repr(exc))
                # Independent final kill/wait; never detach or continue on fail.
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
                except Exception as retry:
                    errors.append(repr(retry))
            self.row.update(qemu_exit=self.proc.poll(),owned_qemu_exited=self.proc.poll() is not None)
        else:
            self.row.update(qemu_exit=None,owned_qemu_exited=False)
        # A cleanup failure is a failure even if the retry ultimately exits.
        # If no exit could be established, intentionally retain the connections
        # until interpreter teardown; closing a debugger first is not safe.
        if self.proc is None or self.proc.poll() is not None:
            if self.qmp is not None:
                try:
                    self.qmp.stream.close()
                except Exception as exc:
                    errors.append(repr(exc))
            for sock in self.sockets:
                try:
                    sock.close()
                except Exception as exc:
                    errors.append(repr(exc))
        for stream in reversed(self.streams):
            try:
                stream.close()
            except Exception as exc:
                errors.append(repr(exc))
        self.row['cleanup_errors'] = errors
        if errors or not self.row['owned_qemu_exited']:
            self.row['overall'] = 'FAIL'

    def stop(self, symbol, label):
        address = self.symbols[symbol]['address']
        need(self.gdb.command(f'Z1,{address:x},1') == 'OK','install hardware breakpoint '+symbol)
        reply = self.gdb.command('c')
        need(reply.startswith(('T05','S05')),'actual debugger stop '+symbol)
        packet = self.gdb.command('g')
        regs = dict(zip(NAMES,struct.unpack_from('<16I',bytes.fromhex(packet))))
        need(regs['eip'] == address and regs['cs'] == 8, 'exact Ring0 stopped EIP '+symbol)
        need(self.qmp.call('query-status')['running'] is False,'vCPU paused '+symbol)
        need(self.gdb.command(f'z1,{address:x},1') == 'OK','remove breakpoint '+symbol)
        self.capture(label,symbol,packet)
        return regs

    def physical(self, filename, address, size):
        need(type(address) is int and type(size) is int and address >= 4096 and size > 0 and address+size <= self.ram*1024*1024,'physical RAM capture bounds')
        path = self.out/filename
        need(not path.exists(),'capture overwrite refused')
        self.qmp.call('pmemsave',val=address,size=size,filename=path.as_posix())
        raw = path.read_bytes()
        need(len(raw) == size,'physical capture extent')
        return raw

    def virtual(self, filename, address, size):
        raw = b''.join(self.gdb.read(address+i,min(512,size-i)) for i in range(0,size,512))
        write(self.out/filename,raw)
        return raw

    def capture(self, label, symbol=None, packet=None):
        need(self.qmp.call('query-status')['running'] is False,'capture must be paused')
        packet = packet if packet is not None else self.gdb.command('g')
        write(self.out/(label+'_register_packet.txt'),packet.encode('ascii'))
        _,text = self.qmp.hardware()
        write(self.out/(label+'_hardware.txt'),text.encode('ascii'))
        hw = hardware(text.encode('ascii'))
        need(hw['CR4'] & (1<<21) == 0,'F4 SMAP must be zero')
        meta = {'symbol':symbol,'paused':True,'registers_stable':False,'directory':{'address':hw['CR3'],'size':4096},'tables':[],**self.stores}
        raw = self.physical(label+'_directory.bin',hw['CR3'],4096)
        need(raw == self.physical(label+'_directory_repeat.bin',hw['CR3'],4096),'stable raw directory')
        directory = struct.unpack('<1024I',raw)
        table_cache = {}
        for i,pde in enumerate(directory):
            if pde & 1:
                need(pde & 0x80 == 0,'ordinary non-PAE table')
                address = pde & 0xfffff000
                filename,repeat = f'{label}_table_{i:03d}.bin',f'{label}_table_{i:03d}_repeat.bin'
                data = self.physical(filename,address,4096)
                need(data == self.physical(repeat,address,4096),'stable table '+str(i))
                table_cache[i] = struct.unpack('<1024I',data)
                meta['tables'].append({'index':i,'address':address,'size':4096,'file':filename,'repeat':repeat})
        def identity(address,size):
            # Static metadata may straddle pages. Verify every physical alias
            # before using its virtual symbol value as a pmemsave address.
            need(size > 0,'nonzero metadata extent')
            for page in range(address & ~4095,(address+size+4095)&~4095,4096):
                dp = directory[page >> 22]
                need(dp & 0x87 == 3,'static metadata supervisor PDE')
                lp = table_cache[page >> 22][(page >> 12)&1023]
                need(lp & 0xfffff007 == page | 3,'static metadata physical identity')
        captures = {}
        for name,sym in self.stores.items():
            identity(sym['address'],sym['size'])
            data = self.physical(label+'_'+name+'.bin',sym['address'],sym['size'])
            need(data == self.physical(label+'_'+name+'_repeat.bin',sym['address'],sym['size']),'stable metadata '+name)
            captures[name] = data
        owner = decode_owner(captures['owner'],self.layout)
        for slot,key in (('arena_table','arena_table'),('payload','payload'),('user_stack','stack')):
            lease = owner['slots'][slot]
            # Uninitialized payload/sentinel bytes at capacity refusal are not
            # interpreted as USER content. Capture only complete arena staging.
            if owner['slots']['arena_table'] is not None and lease is not None:
                address = lease['addr']
                identity(address,4096)
                meta[key+'_address'] = address
                data = self.physical(label+'_'+key+'.bin',address,4096)
                need(data == self.physical(label+'_'+key+'_repeat.bin',address,4096),'stable staged page '+key)
        if hw['TR'] == 24 and hw['GDT'][1] == 39:
            base = hw['GDT'][0]
            for name,address,size in (('gdt',base,40),('normal_tss',base+40,104),('emergency_tss',base+144,104),('idt8',hw['IDT'][0]+64,8)):
                identity(address,size)
                self.physical(label+'_'+name+'.bin',address,size)
        need(self.gdb.command('g') == packet,'stopped registers changed during physical capture')
        meta['registers_stable'] = True
        save(self.out/(label+'_capture.json'),meta)

    def halt(self, fault=False):
        # No pending GDB continue response is left unread. QMP resumes only the
        # current Ring0 continuation, then pauses the actual terminal HLT.
        self.qmp.call('cont')
        limit = min(self.deadline,time.monotonic()+8)
        marker = b'F2 fatal terminal\n' if fault else b'F4 USER arena '
        while time.monotonic() < limit:
            need(self.proc.poll() is None,'guest exited before terminal')
            if (self.out/'serial.txt').exists() and marker in (self.out/'serial.txt').read_bytes():
                # Let the bounded lockfree terminal execute its next CLI/HLT.
                time.sleep(0.15)
                break
            time.sleep(0.02)
        self.qmp.call('stop')
        self.capture('terminal')
        need('HLT=1' in (self.out/'terminal_hardware.txt').read_text(),'actual terminal halt')


def guest(kernel, output, case, ram, variant):
    output.mkdir(exist_ok=False)
    row = {'scenario':case,'ram_mib':ram,'variant':variant,'kernel_sha256':sha(kernel.read_bytes()),'overall':'FAIL','capture_complete':False,'hardware_cpl3':False,'debugger_mutations':[],'checks':[],'cleanup_errors':[]}
    session = None
    try:
        session = Session(kernel,output,ram,row)
        session.open()
        session.stop('f4_fixture_entry','initial')
        session.virtual('cpuid.bin',session.symbols['f4_cpuid']['address'],80)
        if case == 'occupied_refusal':
            session.stop('f4_occupied_checkpoint','occupied')
            session.stop('f4_arena_terminal','refused')
            session.halt()
        elif case == 'capacity_refusal':
            session.stop('f4_capacity_checkpoint','capacity')
            session.stop('f4_arena_terminal','refused')
            session.halt()
        else:
            session.stop('f4_prepublication','pre')
            session.stop('f4_publication_authority','publish')
            session.stop('f4_arena_terminal','ready')
            if case in FAULTS:
                session.gdb.set_registers(eip=session.symbols['f4_select_'+case]['address'])
                row['debugger_mutations'] = session.gdb.mutations
                if case == 'code_write':
                    session.stop('f4_positive','positive')
                    session.virtual('positive_virtual.bin',0x403ff080,4)
                session.stop('f4_fault_'+case,'fault')
                instruction = FAULTS[case][2]
                session.virtual('fault_instruction.bin',session.symbols['f4_fault_'+case]['address'],len(instruction))
                normalized = session.stop('f2_normalized','normalized')
                session.virtual('mandatory_prefix.bin',normalized['esp'],68)
                session.halt(fault=True)
            else:
                session.halt()
        row.update(overall='PASS',capture_complete=True,checks=[{'name':n,'pass':True} for n in ('stopped_physical_capture_complete','CPL0_only','owned_terminal_retention')])
    except Exception as exc:
        row['error'] = repr(exc)
    finally:
        if session is not None:
            session.close()
        row['frozen_bytes'] = tree_pins(output,('guest_report.json',))
        if row['overall'] == 'PASS':
            try:
                validate_guest(output,row,session.layout,session.symbols)
                row['checks'].append({'name':'complete_offline_wire_and_owner_readback','pass':True})
            except Exception as exc:
                row.update(overall='FAIL',error='offline readback: '+repr(exc))
        save(output/'guest_report.json',row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    need(args.output_dir.is_absolute(),'absolute unique output directory required')
    out = args.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=False)
    report = {'schema':'rosti.f4-arena-matrix.v1','overall':'FAIL','driver_exit':2,'full_f4_matrix':False,'hardware_cpl3':False,'builds':{},'guests':[],'checks':[],'source_freeze_stable':False}
    before = None
    try:
        before = inputs()
        save(out/'source_before.json',before)
        for name,digest in before.items():
            raw = (ROOT/name).read_bytes()
            need(sha(raw) == digest,'source capture drift '+name)
            write(out/'source'/name,raw)
        for path,filename in ((DESIGN,'design.md'),(REVIEW,'design_review_02.json'),(DISPOSITION,'operator_disposition_01.json')):
            write(out/'authority'/filename,(ROOT/path).read_bytes())
        need(sha((out/'authority/design.md').read_bytes()) == DESIGN_SHA,'approved design drift')
        need(sha((out/'authority/design_review_02.json').read_bytes()) == REVIEW_SHA,'independent design review drift')
        approval = strict_json(out/'authority/design_review_02.json')
        need(approval['verdict'] == 'APPROVE' and approval['blocker_count'] == 0 and approval['design_raw_sha256'] == DESIGN_SHA,'design approval gate')
        need(bool(strict_json(out/'authority/operator_disposition_01.json')),'terminal retention disposition missing')
        need(sha((out/'authority/operator_disposition_01.json').read_bytes()) == approval['raw_sha256'][DISPOSITION], 'review-pinned operator disposition drift')
        bios_candidates = [QEMU.parent/'share/bios-256k.bin', QEMU.parent/'share/qemu/bios-256k.bin']
        bios = next((p for p in bios_candidates if p.is_file()), None)
        need(bios is not None, 'explicit QEMU BIOS unavailable')
        write(out/'firmware/bios-256k.bin', bios.read_bytes())
        write(out/'toolchain/qemu-system-i386.exe', QEMU.read_bytes())
        tools = {'qemu_path':str(QEMU),'qemu_sha256':sha(QEMU.read_bytes()),'bios_source':str(bios),'bios_sha256':sha(bios.read_bytes())}
        save(out/'toolchain.json',tools)
        for variant in ('normal','occupied_refusal','capacity_refusal'):
            need(inputs() == before,'source drift before fixture build')
            report['builds'][variant] = build_fixture(out,before,variant)
        for case in SCENARIOS:
            variant = case if case.endswith('_refusal') else 'normal'
            for ram in RAMS:
                need(inputs() == before,'source drift before guest')
                need(sha(QEMU.read_bytes()) == tools['qemu_sha256'] and sha(bios.read_bytes()) == tools['bios_sha256'], 'emulator/firmware drift')
                name = case+'_'+str(ram)
                row = guest(out/'builds'/variant/'kernel.elf',out/name,case,ram,variant)
                report['guests'].append({**{k:row[k] for k in ('scenario','ram_mib','variant','kernel_sha256','overall')},'report':name+'/guest_report.json'})
                need(row['overall'] == 'PASS','guest failed '+name+': '+row.get('error','cleanup failure'))
        report.update(overall='PASS',driver_exit=0,full_f4_matrix=True)
        report['checks'] = [{'name':'exact_twelve_complete_Ring0_scenarios','pass':True},{'name':'offline_wire_and_authority_readback','pass':True}]
    except Exception as exc:
        report.update(overall='FAIL',driver_exit=2,error=repr(exc))
    finally:
        try:
            after = inputs()
            save(out/'source_after.json',after)
            report['source_freeze_stable'] = before is not None and before == after
            need(report['source_freeze_stable'],'source input set/bytes drift')
        except Exception as exc:
            report.update(overall='FAIL',driver_exit=2,freeze_error=repr(exc))
        report['frozen_bytes'] = tree_pins(out,('report.json',))
        # Serialize once; do not overwrite a successful-looking report after a
        # late validator failure. The candidate is private until readback passes.
        candidate = out/'candidate_report.json'
        save(candidate,report)
        candidate.rename(out/'report.json')
        if report['overall'] == 'PASS':
            try:
                validate(out,expected_source=before,check_current=True)
            except Exception as exc:
                # Preserve the original candidate and produce a distinct,
                # nonzero failure record. Never silently replace evidence.
                (out/'report.json').rename(out/'rejected_candidate_report.json')
                report.update(overall='FAIL',driver_exit=2,full_f4_matrix=False,error='aggregate readback: '+repr(exc))
                report['frozen_bytes'] = tree_pins(out,('report.json',))
                save(out/'report.json',report)
        print(json.dumps({'overall':report['overall'],'driver_exit':report['driver_exit'],'output':str(out),'guests':len(report['guests']),'hardware_cpl3':False,'error':report.get('error')}))
    return report['driver_exit']


if __name__ == '__main__':
    raise SystemExit(main())
