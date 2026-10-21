"""Pure Python unit models ONLY: no cargo, QEMU, sockets, or runtime evidence.

Synthetic wire images below exercise malformed-evidence rejection. They are not
and must never be retained or described as actual guest success evidence.
"""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import f3_evidence as ev
from b13_entry_inject import patch_registers
from f3_gdt_guest import green_assembly

BASE, CR3, IDT, TABLE, ALIAS = 0x200000, 0x300000, 0x210000, 0x301000, 0x302000


def symbols():
    names = ['f3_context','f3_ready','f3_emergency_entry','f3_wire_probe']
    names += ['f3_'+prefix+'_'+case for case in ev.SCENARIOS for prefix in ('trigger','fault')]
    result = {name:{'address':BASE+i*0x100,'size':32} for i,name in enumerate(names)}
    result['test_retained_owner_OWNER'] = {'address':BASE+0x3000,'size':16}
    result['test_retained_owner_STATE'] = {'address':BASE+0x4000,'size':1}
    return result


def packet(eip, esp=0x400000):
    values = dict.fromkeys(ev.NAMES,0)
    values.update(eip=eip,esp=esp,eflags=2,cs=8,ss=16,ds=16,es=16,fs=16,gs=16)
    return struct.pack('<16I',*(values[n] for n in ev.NAMES)).hex().encode()


def hw(eip, tr=24, esp=0x400000, cr2=0, halted=False):
    return (f'EIP={eip:08x} ESP={esp:08x} EFL=00000002 CPL=0 HLT={int(halted)}\n'
            f'CR0=80010001 CR2={cr2:08x} CR3={CR3:08x} CR4=00000000\n'
            f'GDT= {BASE:08x} 00000027\nIDT= {IDT:08x} 000007ff\n'
            f'TR ={tr:04x} 00000000 00000067 00008900\nEFER=0000000000000000\n').encode()


def wire_model(case, syms):
    """Explicit fabricated unit model, never an execution result."""
    ready = syms['f3_ready']['address']
    fault = syms['f3_fault_'+case]['address']
    gdt = bytes(8)+bytes.fromhex('ffff00000099cf00ffff00000093cf00')+ev.descriptor(BASE+40,0x8b)+ev.descriptor(BASE+144,0x89)
    directory,table,alias = [0]*1024,[0]*1024,[0]*1024
    directory[31],directory[1] = TABLE|3,ALIAS|3
    aliases = []
    for ordinal,i in enumerate((1,2,3,4,6,7,8,9)):
        frame = 0x500000+ordinal*8192
        table[i] = frame|3
        alias[(frame>>12)&1023] = frame|3
        aliases.append({'physical':frame,'pde':ALIAS|3,'pte':frame|3})
    model = {'f3_ready_register_packet.txt':packet(ready), 'ready_hardware.txt':hw(ready),
             'cpu_gdt.bin':gdt,'normal_tss.bin':ev.tss(esp0=0x7c05000,ss0=16),
             'emergency_tss.bin':ev.tss(esp0=0x7c0a000,ss0=16,cr3=CR3,eip=syms['f3_emergency_entry']['address'],eflags=2,esp=0x7c0a000,es=16,cs=8,ss=16,ds=16,fs=16,gs=16),
             'idt8.bin':bytes.fromhex('0000200000850000'),
             'sgdt_str_sidt.bin':struct.pack('<HIHHI',39,BASE,24,2047,IDT),
             'directory.bin':struct.pack('<1024I',*directory),'stack_table.bin':struct.pack('<1024I',*table),
             f'alias_table_{ALIAS:08x}.bin':struct.pack('<1024I',*alias),
             'physical_capture.json':json.dumps({'directory':CR3,'stack_table':TABLE}).encode(),
             'stack_aliases.json':json.dumps(aliases).encode(),'context_attempt.bin':struct.pack('<I',1),
             'serial.txt':b'', 'qemu.log':b'', 'stderr.txt':b'',
             'fault_register_packet.txt':packet(fault,0x7c01000 if case.endswith('_df') else 0x400000),
             'terminal_hardware.txt':hw(fault,halted=True)}
    if case.endswith('_df'):
        first = 6 if case == 'exhausted_esp_ud2_df' else 14
        model['qemu.log'] = (f'v={first:02x} e=0000 i=0 cpl=0 IP=0008:{fault:08x}\nv=0e e=0002 i=0 cpl=0 IP=0008:{fault:08x}\nv=08 e=0000 i=0 cpl=0 IP=0008:{fault:08x}\n').encode()
        model['serial.txt'] = b'F3_DF_FATAL\n'
        model['emergency_entry_register_packet.txt'] = packet(syms['f3_emergency_entry']['address'],0x7c09ffc)
        model['emergency_entry_hardware.txt'] = hw(syms['f3_emergency_entry']['address'],32,0x7c09ffc)
        model['emergency_error.bin'] = bytes(4)
        model['emergency_observed.bin'] = struct.pack('<4I',32,0x7c09ffc,CR3,0)
        model['post_task_gdt.bin'] = gdt[:37]+b'\x8b'+gdt[38:]
        model['post_emergency_tss.bin'] = struct.pack('<I',24)+model['emergency_tss.bin'][4:]
        model['terminal_hardware.txt'] = hw(syms['f3_emergency_entry']['address'],32,0x7c09ffc,halted=True)
    elif case != 'ready':
        guard = 0x7c00000 if case == 'transition_guard_pf' else 0x7c05000
        frame = [0]*17
        frame[12:15] = [14,2,fault]
        model['mandatory_prefix.bin'] = struct.pack('<17I',*frame)
        model['normalized_register_packet.txt'] = packet(fault,0x400000-68)
        model['normalized_hardware.txt'] = hw(fault,cr2=guard)
        model['serial.txt'] = b'F2 fatal terminal\n'
        model['qemu.log'] = f'v=0e e=0002 i=0 cpl=0 IP=0008:{fault:08x}\n'.encode()
    return model


def write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)


def dump(path, value):
    write(path,(json.dumps(value,indent=2)+'\n').encode())


def pins(folder, exclude=()):
    return {p.relative_to(folder).as_posix():ev.sha(p.read_bytes()) for p in sorted(folder.rglob('*')) if p.is_file() and p.name not in exclude}


def transcripts(folder, model, syms, case):
    glog,qlog = [],[]
    def mem(name,addr):
        raw = model[name]
        for i in range(0,len(raw),512):
            glog.append({'command':f'm{addr+i:x},{len(raw[i:i+512]):x}','reply':raw[i:i+512].hex()})
    for n,a in [('cpu_gdt.bin',BASE),('normal_tss.bin',BASE+40),('emergency_tss.bin',BASE+144),('context_attempt.bin',BASE+264),('idt8.bin',IDT+64),('sgdt_str_sidt.bin',syms['f3_wire_probe']['address'])]:
        mem(n,a)
    owners = []
    for i,(name,sym) in enumerate((n,s) for n,s in syms.items() if 'retained_owner' in n):
        filename = f'owner_{i}.bin'
        model[filename] = b'\x03' if 'STATE' in name else bytes(sym['size'])
        owners.append({'symbol':name,'address':sym['address'],'size':sym['size'],'file':filename})
        mem(filename,sym['address'])
    model['owner_capture.json'] = json.dumps(owners).encode()
    if case.endswith('_df'):
        for n,a in [('emergency_error.bin',0x7c09ffc),('emergency_observed.bin',BASE+248),('post_task_gdt.bin',BASE),('post_emergency_tss.bin',BASE+144)]:
            mem(n,a)
    elif case != 'ready':
        mem('mandatory_prefix.bin',0x400000-68)
    for name,raw in list(model.items()):
        if name.endswith('_hardware.txt'):
            qlog.append({'command':'human-monitor-command','arguments':{'command-line':'info registers'},'reply':raw.decode()})
        if name.endswith('_register_packet.txt'):
            glog.append({'command':'g','reply':raw.decode()})
    for name,pa in [('directory.bin',CR3),('stack_table.bin',TABLE),(f'alias_table_{ALIAS:08x}.bin',ALIAS)]:
        qlog.append({'command':'pmemsave','arguments':{'val':pa,'size':4096,'filename':(folder/name).as_posix()},'reply':{}})
    glog.append({'command':'G'+patch_registers(model['f3_ready_register_packet.txt'].decode(),{'eip':syms['f3_trigger_'+case]['address']}),'reply':'OK'})
    model['gdb.jsonl'] = ('\n'.join(map(json.dumps,glog))+'\n').encode()
    model['qmp.jsonl'] = ('\n'.join(map(json.dumps,qlog))+'\n').encode()


def matrix_model(folder):
    """Temporary model includes a NON-ELF kernel; ELF reader is mocked in tests."""
    syms = symbols()
    source = folder/'fixture/source'
    input_names = ('src/main.rs','src/gdt.rs','src/gdt_tss.rs','src/f3_entry.s','src/interrupt.rs','src/memory/mod.rs','src/memory/paging.rs','src/memory/retained_owner.rs','scripts/f3_gdt_guest.py','scripts/f3_evidence.py','scripts/test_f3_evidence.py','Cargo.toml','Cargo.lock','target.json','linker.ld','rust-toolchain.toml','.cargo/config.toml')
    snapshot = {}
    for name in input_names:
        raw = ('UNIT MODEL ONLY '+name+'\n').encode()
        if name == 'src/main.rs':
            raw += b'    // stub: enable ps2 & interrupts\n'
        snapshot[name] = ev.sha(raw)
        write(folder/'frozen_inputs'/name,raw)
        if not name.startswith('scripts/'):
            if name == 'src/main.rs':
                anchor = b'    // stub: enable ps2 & interrupts'
                raw = raw.replace(anchor,ev.CALL+anchor)+green_assembly()
            write(source/name,raw)
    dump(folder/'source_freeze_before.json',snapshot)
    dump(folder/'source_freeze_after.json',snapshot)
    write(folder/'driver.py',(folder/'frozen_inputs/scripts/f3_gdt_guest.py').read_bytes())
    write(folder/'validator.py',(folder/'frozen_inputs/scripts/f3_evidence.py').read_bytes())
    write(folder/'fixture_call.rs',ev.CALL)
    write(folder/'fixture_assembly.rs',green_assembly())
    write(folder/'kernel.elf',b'UNIT MODEL ONLY - NOT ELF OR EXECUTABLE')
    write(folder/'build.log',b'UNIT MODEL ONLY - NO BUILD RAN')
    write(folder/'design.md',b'UNIT MODEL ONLY')
    dump(folder/'design_review.json',{'verdict':'APPROVE','blocker_count':0,'design_raw_sha256':ev.sha(b'UNIT MODEL ONLY')})
    report = {'schema':'rosti.f3-minimal-ring0.v1','overall':'MINIMAL_RING0_GREEN','driver_exit':0,'build_exit':0,
              'full_f3_acceptance':False,'hardware_cpl3':False,'planned_only':ev.PLANNED.copy(),
              'source_freeze_stable':True,'source_input_count':len(snapshot),'source_sha256':snapshot,
              'build_command':['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(folder/'fixture/build')],
              'build_cwd':str(source),'kernel_sha256':ev.sha((folder/'kernel.elf').read_bytes()),'scenarios':[]}
    report.update(invocation_dir=str(folder),stripping_equality=True,original_main_sha256=snapshot['src/main.rs'],injected_main_sha256=ev.sha((source/'src/main.rs').read_bytes()),assembly_sha256=ev.sha(green_assembly()),call_sha256=ev.sha(ev.CALL))
    for name in ev.REQUIRED:
        case,ram = name.rsplit('_',1)
        child = folder/name
        child.mkdir()
        model = wire_model(case,syms)
        transcripts(child,model,syms,case)
        for file,raw in model.items():
            write(child/file,raw)
        row = {'name':name,'case':case,'ram_mib':int(ram),'overall':'PASS','capture_complete':True,
               'owned_pid':1234,'qemu_exit_before_cleanup':None,'cleanup_action':'kill_owned_Popen','owned_qemu_exited':True,'qemu_exit':1,
               'kernel_sha256':report['kernel_sha256'],
               'command':['C:/unit-model/qemu-system-i386.exe','-kernel',str(folder/'kernel.elf'),'-cpu','qemu32','-m',ram,'-smp','1','-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot','-serial','file:'+str(child/'serial.txt'),'-d','int,guest_errors','-D',str(child/'qemu.log'),'-S','-gdb','tcp:127.0.0.1:12345','-qmp','tcp:127.0.0.1:12346,server=on,wait=off'],
               'debugger_mutations':[{'registers':{'eip':syms['f3_trigger_'+case]['address']}}],
               'checks':ev.scenario_assertions(model.__getitem__,syms,case),'frozen_bytes':pins(child)}
        dump(child/'guest_report.json',row)
        report['scenarios'].append(row)
    report['frozen_bytes'] = pins(folder)
    return report,syms


class WireEvidenceTests(unittest.TestCase):
    def test_all_scenario_wire_models(self):
        syms = symbols()
        for case in ev.SCENARIOS:
            with self.subTest(case=case):
                checks = ev.scenario_assertions(wire_model(case,syms).__getitem__,syms,case)
                self.assertTrue(checks)
                self.assertTrue(all(c['actual'] == c['expected'] and c['pass'] is True for c in checks))

    def test_ready_rejects_wire_corruption(self):
        syms = symbols()
        for name,offset in [('cpu_gdt.bin',29),('normal_tss.bin',4),('emergency_tss.bin',28),('idt8.bin',5),('sgdt_str_sidt.bin',6),('stack_table.bin',4)]:
            with self.subTest(name=name):
                data = wire_model('ready',syms)
                raw = bytearray(data[name]); raw[offset] ^= 4
                data[name] = bytes(raw)
                with self.assertRaises(ValueError):
                    ev.ready_assertions(data.__getitem__,syms)

    def test_df_rejects_false_marker_error_tr_and_reset(self):
        syms = symbols()
        case = 'exhausted_esp_pf_df'
        controls = {'serial.txt':b'F3_DF_FATAL impostor\n','emergency_error.bin':struct.pack('<I',1),
                    'emergency_entry_hardware.txt':hw(syms['f3_emergency_entry']['address'],24,0x7c09ffc),
                    'qemu.log':b'CPU Reset\n'}
        for name,raw in controls.items():
            with self.subTest(name=name):
                model = wire_model(case,syms); model[name] = raw
                with self.assertRaises(ValueError):
                    ev.scenario_assertions(model.__getitem__,syms,case)

    def test_assembly_uses_real_faults_no_int8_or_fake_ready(self):
        asm = green_assembly()
        self.assertIn(b'ud2',asm)
        self.assertIn(b'mov $0x07c01000,%esp',asm)
        self.assertIn(b'str f3_wire_probe+6',asm)
        self.assertNotIn(b'int $8',asm)
        self.assertNotIn(b'f3_ready:',asm)
        self.assertNotIn(b'f3_probe',asm)
        self.assertEqual(asm.count(b'F3_GREEN_ASM_BEGIN'),1)


class MatrixEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='f3_UNIT_MODEL_')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.report,self.syms = matrix_model(self.folder)
        self.mock = patch('b13_entry_inject.elf_symbols',return_value=self.syms)
        self.mock.start(); self.addCleanup(self.mock.stop)

    def validate(self, report=None):
        return ev.validate_matrix(self.report if report is None else report,self.folder)

    def reseal(self, report):
        for row in report['scenarios']:
            child = self.folder/row['name']
            row['frozen_bytes'] = pins(child,('guest_report.json',))
            dump(child/'guest_report.json',row)
        report['frozen_bytes'] = pins(self.folder,('report.json',))

    def test_external_source_api_and_absolute_pins(self):
        dump(self.folder/'report.json',self.report)
        result = ev.validate(self.folder/'report.json',self.report['source_sha256'])
        self.assertEqual(result['scenario_count'],10)
        self.assertTrue(result['pins'])
        self.assertTrue(all(Path(p).is_absolute() for p in result['pins']))
        with self.assertRaises(ValueError):
            ev.validate(self.folder/'report.json',{'impostor':'0'*64})

    def test_complete_exact_minimal_model(self):
        result = self.validate()
        self.assertEqual(result['scenario_count'],10)
        self.assertEqual(result['overall'],'PASS_MINIMAL_ONLY')
        self.assertFalse(result['full_f3_acceptance'])

    def test_missing_duplicate_substitute_wrong_ram_and_zero_rows(self):
        for mode in ('missing','duplicate','substitute','wrong_ram','zero'):
            with self.subTest(mode=mode):
                report = copy.deepcopy(self.report)
                if mode == 'missing': report['scenarios'].pop()
                elif mode == 'duplicate': report['scenarios'][-1] = report['scenarios'][0]
                elif mode == 'substitute': report['scenarios'][0]['name'] = 'impostor_128'
                elif mode == 'wrong_ram': report['scenarios'][0]['ram_mib'] = 512
                else: report['scenarios'] = []
                with self.assertRaises(ValueError): self.validate(report)

    def test_missing_and_malformed_pins_refuse(self):
        for mode in ('empty','bad_hash','escape','missing_kernel'):
            with self.subTest(mode=mode):
                report = copy.deepcopy(self.report)
                if mode == 'empty': report['frozen_bytes'] = {}
                elif mode == 'bad_hash': report['frozen_bytes']['kernel.elf'] = 'not-a-digest'
                elif mode == 'escape': report['frozen_bytes']['../outside'] = '0'*64
                else: del report['frozen_bytes']['kernel.elf']
                with self.assertRaises(ValueError): self.validate(report)

    def test_modified_frozen_byte_refuses(self):
        write(self.folder/'ready_128/cpu_gdt.bin',bytes(40))
        with self.assertRaises(ValueError): self.validate()

    def test_zero_checks_impostor_cleanup_and_command_refuse(self):
        for field,value in [('checks',[]),('owned_pid',0),('owned_qemu_exited',False),('qemu_exit_before_cleanup',0),('command',['fake']),('debugger_mutations',[])]:
            with self.subTest(field=field):
                report = copy.deepcopy(self.report)
                report['scenarios'][0][field] = value
                self.reseal(report)
                with self.assertRaises(ValueError): self.validate(report)

    def test_full_acceptance_and_planned_success_inflation_refuse(self):
        for key,value in [('full_f3_acceptance',True),('hardware_cpl3',True),('planned_only',{'ss':'PASS','nmi_timing':'PASS'}),('build_exit',1),('source_freeze_stable',False)]:
            with self.subTest(key=key):
                report = copy.deepcopy(self.report); report[key] = value
                with self.assertRaises(ValueError): self.validate(report)

    def test_duplicate_json_key_refuses(self):
        write(self.folder/'bad.json',b'{"overall":"FAIL","overall":"PASS"}')
        with self.assertRaises(ValueError): ev.strict_json(self.folder/'bad.json')

    def test_real_elf_reader_refuses_unit_model(self):
        self.mock.stop()
        with self.assertRaises(ValueError): self.validate()


if __name__ == '__main__':
    unittest.main()
