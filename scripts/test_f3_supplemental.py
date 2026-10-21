"""Self-contained synthetic byte models; NEVER hardware evidence or execution."""
import contextlib
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import f3_evidence as base
import f3_supplemental as guest
import f3_supplemental_evidence as ev
import test_f3_evidence as models

HALT = 0x220000
OUT = 0x200280


def symbols():
    syms = models.symbols()
    syms.update({name:{'address':address,'size':4} for name,address in {
        'f2_exc_2':0x210100,'f2_exc_12':0x210200,'f2_normalized':0x210300,
        'f3s_ss':0x210400,'f3s_ss_fault':0x210500,'f3s_df':0x210600,
        'f3s_df_fault':0x210700,'f3s_gdt':0x230000,'f3s_wire':0x230100,
        'f3_emergency_terminal':0x200300,'unit_exception_fatal4halt':HALT}.items()})
    return syms


def kernel_model():
    raw = bytearray(256)
    struct.pack_into('<I',raw,28,52)
    struct.pack_into('<HH',raw,42,32,2)
    struct.pack_into('<8I',raw,52,1,128,HALT,HALT,4,4,5,4096)
    struct.pack_into('<8I',raw,84,1,144,OUT,OUT,1,1,5,4096)
    raw[128:132] = b'\xfa\xf4\xeb\xfd'
    raw[144] = 0xee
    return bytes(raw)


def case_model(folder, case, ram):
    """Fabricate explicitly labeled unit bytes plus independently checked logs."""
    syms = symbols()
    emergency = case in ('nmi_entry','nmi_output')
    ready = syms['f3_ready']['address']
    ip = syms['f3s_ss_fault']['address'] if case == 'ss_nonpresent' else (OUT if case == 'nmi_output' else (syms['f3_emergency_entry']['address'] if emergency else ready))
    esp = 0x7c09ffc if emergency else 0x400000
    gdt = bytes(8)+bytes.fromhex('ffff00000099cf00ffff00000093cf00')+base.descriptor(models.BASE+40,0x8b)+base.descriptor(models.BASE+144,0x89)
    data = {'ready_gdt.bin':gdt,'normal_tss.bin':base.tss(esp0=0x7c05000,ss0=16),
            'emergency_tss.bin':base.tss(esp0=0x7c0a000,ss0=16,cr3=models.CR3,eip=syms['f3_emergency_entry']['address'],eflags=2,esp=0x7c0a000,es=16,cs=8,ss=16,ds=16,fs=16,gs=16),
            'idt8.bin':bytes.fromhex('0000200000850000'),'serial.txt':b'F2 fatal terminal\n',
            'stderr.txt':b'UNIT MODEL ONLY; NO QEMU RAN'}
    origins = {'ready_gdt.bin':(models.BASE,40),'normal_tss.bin':(models.BASE+40,104),
               'emergency_tss.bin':(models.BASE+144,104),'idt8.bin':(models.IDT+64,8),
               'idt2.bin':(models.IDT+16,8),'idt12.bin':(models.IDT+96,8),
               'mandatory_prefix.bin':(esp-68,68)}
    for v in (2,12):
        a=syms['f2_exc_'+str(v)]['address']
        data['idt'+str(v)+'.bin']=struct.pack('<HHHH',a & 65535,8,0x8e00,a >> 16)
    states = {'ready':(ready,0x400000,24),'before':(ip,esp,32 if emergency else 24),
              'normalized':(syms['f2_normalized']['address'],esp-68,32 if emergency else 24),
              'terminal':(HALT+2,esp-128,32 if emergency else 24)}
    events = []
    if case == 'ss_nonpresent':
        data.update({'fixture_gdt.bin':gdt+bytes.fromhex('ffff00000013cf00'),
                     'production_gdt_after.bin':gdt,'fixture_wire.bin':struct.pack('<HIHHI',47,syms['f3s_gdt']['address'],24,2047,models.IDT),'fault_instruction.bin':b'\x8e\xd0'})
        origins.update({'fixture_gdt.bin':(syms['f3s_gdt']['address'],48),'production_gdt_after.bin':(models.BASE,40),'fixture_wire.bin':(syms['f3s_wire']['address'],14),'fault_instruction.bin':(ip,2)})
    if emergency:
        fault=syms['f3s_df_fault']['address']
        states.update(fault=(fault,0x7c01000,24),entry=(syms['f3_emergency_entry']['address'],0x7c09ffc,32))
        data.update({'df_error.bin':bytes(4),'post_task_gdt.bin':gdt[:37]+b'\x8b'+gdt[38:],
                     'post_emergency_tss.bin':struct.pack('<I',24)+data['emergency_tss.bin'][4:]})
        origins.update({'df_error.bin':(0x7c09ffc,4),'post_task_gdt.bin':(models.BASE,40),'post_emergency_tss.bin':(models.BASE+144,104)})
        events = [(14,2,fault),(14,2,fault),(8,0,fault)]
    if case == 'nmi_output':
        data.update({'output_instruction.bin':b'\xee','emergency_observed.bin':struct.pack('<4I',32,0x7c09ffc,models.CR3,0)})
        origins.update({'output_instruction.bin':(OUT,1),'emergency_observed.bin':(models.BASE+248,16)})
    for label,(pc,sp,tr) in states.items():
        packet=bytearray.fromhex(models.packet(pc,sp).decode())
        if label == 'before':
            struct.pack_into('<I',packet,0,0x28 if case == 'ss_nonpresent' else 0)
            struct.pack_into('<I',packet,8,0x3f8 if case == 'nmi_output' else 0)
        data[label+'_register_packet.txt']=packet.hex().encode()
        hw=models.hw(pc,tr,sp,halted=label == 'terminal')
        if case == 'ss_nonpresent' and label != 'ready':
            hw=hw.replace(f'GDT= {models.BASE:08x} 00000027'.encode(),f'GDT= {syms["f3s_gdt"]["address"]:08x} 0000002f'.encode())
        data[label+'_hardware.txt']=hw
    before=base.registers(data['before_register_packet.txt'])
    frame=[before[n] for n in ('gs','fs','es','ds','edi','esi','ebp')]+[esp-20]+[before[n] for n in ('ebx','edx','ecx','eax')]+[12 if case == 'ss_nonpresent' else 2,0x28 if case == 'ss_nonpresent' else 0,ip,8,before['eflags'] | 0x10000]
    data['mandatory_prefix.bin']=struct.pack('<17I',*frame)
    events.append((12 if case == 'ss_nonpresent' else 2,0x28 if case == 'ss_nonpresent' else 0,ip))
    data['qemu.log']=('check_exception old: 0xe new 0xe\n'+''.join(f'v={v:02x} e={e:04x} i=0 cpl=0 IP=0008:{pc:08x}\n' for v,e,pc in events)).encode()
    glog=[]; qlog=[]
    for label in states:
        glog.append({'command':'g','reply':data[label+'_register_packet.txt'].decode()})
        qlog.append({'command':'human-monitor-command','arguments':{'command-line':'info registers'},'reply':data[label+'_hardware.txt'].decode()})
    mutations=[]
    if case != 'nmi_ready':
        target=syms['f3s_ss' if case == 'ss_nonpresent' else 'f3s_df']['address']
        old=data['ready_register_packet.txt'].decode()
        changed=ev.patch_registers(old,{'eip':target})
        glog += [{'command':'g','reply':old},{'command':'G'+changed,'reply':'OK'},{'command':'g','reply':changed}]
        mutations=[{'registers':{'eip':target}}]
    if case != 'ss_nonpresent':
        qlog.append({'command':'inject-nmi','arguments':{},'reply':{}})
    for name,(a,size) in origins.items():
        glog.append({'command':f'm{a:x},{size:x}','reply':data[name].hex()})
    import json
    data['gdb.jsonl']=''.join(json.dumps(x)+'\n' for x in glog).encode()
    data['qmp.jsonl']=''.join(json.dumps(x)+'\n' for x in qlog).encode()
    for name,raw in data.items(): models.write(folder/name,raw)
    row={'name':f'{case}_{ram}','case':case,'ram_mib':ram,'overall':'PASS','capture_complete':True,
         'owned_pid':1234,'qemu_exit_before_cleanup':None,'cleanup_action':'kill_owned_Popen','owned_qemu_exited':True,'qemu_exit':1,
         'debugger_mutations':mutations,'checkpoints':{n:v[0] for n,v in states.items()},
         'memory_origins':{n:{'address':a,'size':s} for n,(a,s) in origins.items()},'output_ip':OUT,
         'command':['C:/UNIT_MODEL/qemu-system-i386.exe','-kernel',str(folder.parent/'kernel.elf'),'-cpu','qemu32','-m',str(ram),'-smp','1','-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot','-serial','file:'+str(folder/'serial.txt'),'-d','int,guest_errors','-D',str(folder/'qemu.log'),'-S','-gdb','tcp:127.0.0.1:12345','-qmp','tcp:127.0.0.1:12346,server=on,wait=off']}
    row['checks']=ev.validate_case(folder,syms,case,ram,OUT,row)
    row['frozen_bytes']=models.pins(folder)
    models.dump(folder/'guest_report.json',row)
    return row


def matrix_model(folder, source_bytes):
    folder.mkdir(parents=True,exist_ok=True)
    snapshot={n:base.sha(raw) for n,raw in source_bytes.items()}
    for name,raw in source_bytes.items():
        models.write(folder/'frozen_inputs'/name,raw)
        if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
            if name == 'src/main.rs': raw=raw.replace(b'    // stub: enable ps2 & interrupts',base.CALL+b'    // stub: enable ps2 & interrupts')+guest.ASM
            models.write(folder/'fixture/source'/name,raw)
    for name in ('f3_supplemental.py','f3_supplemental_evidence.py'): models.write(folder/name,source_bytes['scripts/'+name])
    models.write(folder/'fixture_call.rs',base.CALL); models.write(folder/'fixture_assembly.rs',guest.ASM)
    models.write(folder/'design.md',b'UNIT MODEL ONLY')
    models.dump(folder/'design_review.json',{'verdict':'APPROVE','blocker_count':0,'design_raw_sha256':base.sha(b'UNIT MODEL ONLY')})
    models.dump(folder/'source_freeze_before.json',snapshot)
    plan={'schema':'rosti.f3-supplement-prepared.v1','prepared_dir':str(folder),'cases':list(ev.CASES),'rams':list(ev.RAMS),'builds_or_qemu_executed':False,'source_snapshot_excludes_tasklocal':True,'source_sha256':snapshot,'prepared_pins':models.pins(folder)}
    models.dump(folder/'prepared.json',plan)
    models.dump(folder/'source_freeze_after.json',snapshot)
    models.write(folder/'kernel.elf',kernel_model())
    models.write(folder/'build.log',b'UNIT MODEL ONLY; NO BUILD RAN')
    models.write(folder/'disassembly.txt',f'{OUT:x}: ee out %al,%dx\n'.encode())
    source=folder/'fixture/source'
    report={'schema':'rosti.f3-supplement.v1','overall':'SUPPLEMENTAL_RING0_GREEN','driver_exit':0,'build_exit':0,'build_cwd':str(source),
            'build_command':['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(folder/'fixture/build')],
            'parent_authorized':True,'full_f3_acceptance':False,'hardware_cpl3':False,'source_freeze_stable':True,'source_sha256':snapshot,'prepared_dir':str(folder),'kernel_sha256':base.sha(kernel_model()),'output_ip':OUT,'scenarios':[]}
    for ram in ev.RAMS:
        for case in ev.CASES: report['scenarios'].append(case_model(folder/f'{case}_{ram}',case,ram))
    report['frozen_bytes']=models.pins(folder)
    models.dump(folder/'report.json',report)
    return report


class SupplementalTests(unittest.TestCase):
    def test_finish_terminal_uses_qmp_not_unreachable_assembly(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/'serial.txt').write_bytes(b'F2 fatal terminal\n')
            qmp=Mock(); proc=Mock(); proc.poll.return_value=None; state=Mock()
            with patch.object(guest.time,'sleep'):
                guest.finish_terminal(qmp,proc,folder,state)
            self.assertEqual(qmp.call.call_args_list, [unittest.mock.call('cont'),unittest.mock.call('stop')])
            state.assert_called_once_with('terminal')

    def test_output_ownership_absolute_and_no_escape(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(guest,'ROOT',Path(tmp)):
            for p in (Path('relative'),Path(tmp),Path(tmp)/'scripts'/'bad'):
                with self.subTest(path=p), self.assertRaises(ValueError): guest.bounded_output(p)
            self.assertEqual(guest.bounded_output(Path(tmp)/'test_results'/'owned'),Path(tmp)/'test_results'/'owned')

    def test_halt_elf_bytes_and_mutation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ev,'elf_symbols',return_value=symbols()):
            p=Path(tmp)/'kernel.elf'; p.write_bytes(kernel_model())
            self.assertEqual(ev.halt_site(p),HALT)
            raw=bytearray(p.read_bytes()); raw[129]=0x90; p.write_bytes(raw)
            with self.assertRaises(ValueError): ev.halt_site(p)

    def test_halt_rejects_nonexecutable_segment_and_wrong_symbol_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'kernel.elf'; raw=bytearray(kernel_model())
            struct.pack_into('<I',raw,52+24,4); p.write_bytes(raw)
            with patch.object(ev,'elf_symbols',return_value=symbols()), self.assertRaises(ValueError):ev.halt_site(p)
            p.write_bytes(kernel_model()); syms=symbols(); syms['unit_exception_fatal4halt']['size']=3
            with patch.object(ev,'elf_symbols',return_value=syms), self.assertRaises(ValueError):ev.halt_site(p)

    def test_terminal_diagnostic_timeout_and_hlt_zero_refuse(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp, patch.object(ev,'elf_symbols',return_value=symbols()):
            folder=Path(tmp); (folder/'serial.txt').write_bytes(b'')
            qmp=Mock(); proc=Mock(); proc.poll.return_value=None
            with patch.object(guest.time,'monotonic',side_effect=[0,6]), self.assertRaisesRegex(ValueError,'timeout'):
                guest.finish_terminal(qmp,proc,folder,Mock())
            (folder/'kernel.elf').write_bytes(kernel_model()); child=folder/'nmi_ready_128'
            row=case_model(child,'nmi_ready',128)
            p=child/'terminal_hardware.txt'; p.write_bytes(p.read_bytes().replace(b'HLT=1',b'HLT=0'))
            with self.assertRaisesRegex(ValueError,'HLT'):ev.validate_case(child,symbols(),'nmi_ready',128,OUT,row)

    def test_raw_models_and_24_mutations(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ev,'elf_symbols',return_value=symbols()):
            folder=Path(tmp); (folder/'kernel.elf').write_bytes(kernel_model())
            for case in ev.CASES:
                child=folder/(case+'_128'); row=case_model(child,case,128)
                self.assertGreater(len(row['checks']),40)
                for name in ('idt2.bin','idt12.bin','mandatory_prefix.bin','normal_tss.bin','ready_gdt.bin','terminal_register_packet.txt'):
                    p=child/name; original=p.read_bytes(); changed=bytearray(original); changed[0]^=1; p.write_bytes(changed)
                    try:
                        with self.subTest(case=case,file=name), self.assertRaises((ValueError,UnicodeError)):
                            ev.validate_case(child,symbols(),case,128,OUT,row)
                    finally: p.write_bytes(original)


if __name__ == '__main__': unittest.main()
