"""Independent retained-byte supplement validator; no build/QEMU on import.
Raw F2 prefix is exactly 68 bytes. No same-ring optional-tail reads admitted.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
from f3_evidence import local, require, sha, strict_json, pin_tree, registers, hardware, descriptor, tss, CALL
from b13_entry_inject import elf_symbols, patch_registers

CASES = ('ss_nonpresent','nmi_ready','nmi_entry','nmi_output')
RAMS = (128,512)


def validate_prepared(folder):
    folder = Path(folder).resolve()
    from f3_supplemental import bounded_output
    bounded_output(folder)
    plan = strict_json(folder/'prepared.json')
    require(plan['schema'] == 'rosti.f3-supplement-prepared.v1','prepared schema')
    require(plan['prepared_dir'] == str(folder),'prepared ownership')
    require(plan['cases'] == list(CASES) and plan['rams'] == list(RAMS),'exact plan')
    require(plan['builds_or_qemu_executed'] is False,'prepare scope')
    require(plan['source_snapshot_excludes_tasklocal'] is True,'snapshot exclusion')
    pin_tree(folder,plan['prepared_pins'])
    before = strict_json(folder/'source_freeze_before.json')
    require(before == plan['source_sha256'] and before,'nonempty source freeze')
    authority = 'test_results/phase11f5_cpl3_proof/'
    allowed = {authority + name for name in (
        'design.md', 'harness_contract_01.json', 'entry_design_amendment_01.md',
        'design_inputs_03.json', 'entry_design_amendment_inputs_01.json',
        'reviews/design_review_03.json', 'reviews/entry_design_amendment_01.json',
        'f2_before_macro_01.elf')}
    require(all(not n.startswith('test_results/') or n in allowed
                or (n.startswith(authority) and n.endswith('.py')) for n in before),
            'unapproved supplement entered canonical source freeze')
    require({'src/main.rs','src/gdt_tss.rs','src/f3_entry.s','src/exception_entry.s','scripts/f3_gdt_guest.py','scripts/f3_evidence.py'} <= before.keys(),'source coverage')
    from f3_supplemental import ASM
    from f3_full_evidence import CANONICAL_SOURCES
    require(set(CANONICAL_SOURCES) <= before.keys(), 'canonical script coverage')
    for filename in ('f3_supplemental.py','f3_supplemental_evidence.py'):
        require(plan['prepared_pins'].get(filename) == before['scripts/'+filename] == sha((folder/filename).read_bytes()), 'copied script provenance')
    require((folder/'fixture_call.rs').read_bytes() == CALL,'real production entry call')
    require((folder/'fixture_assembly.rs').read_bytes() == ASM,'fixed supplemental assembly')
    for name,digest in before.items():
        require(sha(local(folder/'frozen_inputs',name).read_bytes()) == digest,'retained source '+name)
        copied = local(folder/'fixture/source',name)
        if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
            require(copied.is_file(), 'missing copied input '+name)
            raw = copied.read_bytes()
            if name == 'src/main.rs':
                require(raw.count(CALL) == 1 and raw.count(ASM) == 1,'unique fixture')
                stripped = raw.replace(CALL,b'',1).replace(ASM,b'',1)
                anchor = b'    // stub: enable ps2 & interrupts'
                require(raw == stripped.replace(anchor,CALL+anchor)+ASM,'exact injection location')
                raw = stripped
            require(sha(raw) == digest,'copied source drift '+name)
    review = strict_json(folder/'design_review.json')
    require(review['verdict'] == 'APPROVE' and review['blocker_count'] == 0,'design approval')
    require(sha((folder/'design.md').read_bytes()) == review['design_raw_sha256'],'design pin')
    # Ground the observer to the retained actual production assembly, not a
    # guessed symbol or debugger-made task state.
    f2 = (folder/'frozen_inputs/src/exception_entry.s').read_text()
    require('F2_STUB 2' in f2 and 'F2_STUB 12,1' in f2 and 'f2_normalized:' in f2,'actual F2 symbols')
    require('pushal' in f2 and '.if {frame_size} != 68' in f2,'actual F2 ABI')
    emergency = (folder/'frozen_inputs/src/f3_entry.s').read_text()
    require('f3_emergency_entry:' in emergency and 'out %al,%dx' in emergency,'production UART entry')
    return plan


def halt_site(kernel):
    symbols = elf_symbols(kernel)
    sites = [v for n,v in symbols.items() if n.endswith('exception_fatal4halt')]
    require(len(sites) == 1 and sites[0]['size'] == 4, 'unique emitted Rust fatal halt')
    address = sites[0]['address']
    raw = Path(kernel).read_bytes()
    phoff = struct.unpack_from('<I',raw,28)[0]
    entsize,count = struct.unpack_from('<HH',raw,42)
    matches = []
    for i in range(count):
        kind,offset,va,pa,filesz,memsz,flags,align = struct.unpack_from('<8I',raw,phoff+i*entsize)
        if kind == 1 and flags & 1 and va <= address and address+4 <= va+filesz:
            matches.append(raw[offset+address-va:offset+address-va+4])
    require(matches == [b'\xfa\xf4\xeb\xfd'], 'actual CLI HLT backward-loop bytes')
    return address


def validate_case(folder,symbols,case,ram,output_ip,row):
    folder = Path(folder)
    require(case in CASES and ram in RAMS,'case identity')
    checks = []
    def eq(name,actual,expected):
        checks.append({'name':name,'actual':actual,'expected':expected,'pass':actual == expected})
        require(actual == expected,name)
    def read(name):
        return (folder/name).read_bytes()
    def state(label):
        r = registers(read(label+'_register_packet.txt'))
        h = hardware(read(label+'_hardware.txt'))
        eq(label+'_EIP_QMP',h['EIP'],r['eip'])
        eq(label+'_CPL0_selectors',[r['cs'],r['ss']],[8,16])
        eq(label+'_IF0',r['eflags'] & 0x200,0)
        return r,h
    ready, initial = state('ready')
    base = symbols['f3_context']['address']
    eq('ready_EIP',ready['eip'],symbols['f3_ready']['address'])
    eq('ready_TR',initial['TR'],24)
    eq('ready_GDTR',list(initial['GDT']),[base,39])
    expected = bytes(8)+bytes.fromhex('ffff00000099cf00ffff00000093cf00')+descriptor(base+40,0x8b)+descriptor(base+144,0x89)
    eq('ready_raw_GDT',read('ready_gdt.bin').hex(),expected.hex())
    eq('normal_TSS',read('normal_tss.bin').hex(),tss(esp0=0x7c05000,ss0=16).hex())
    eq('emergency_TSS',read('emergency_tss.bin').hex(),tss(esp0=0x7c0a000,ss0=16,cr3=initial['CR3'],eip=symbols['f3_emergency_entry']['address'],eflags=2,esp=0x7c0a000,es=16,cs=8,ss=16,ds=16,fs=16,gs=16).hex())
    eq('IDT8_taskgate',read('idt8.bin').hex(),'0000200000850000')
    for vector in (2,12):
        ip = symbols['f2_exc_'+str(vector)]['address']
        gate = struct.pack('<HHHH',ip & 65535,8,0x8e << 8,ip >> 16)
        eq('IDT_actual_F2_'+str(vector),read('idt'+str(vector)+'.bin').hex(),gate.hex())
    before,bhw = state('before')
    normalized,nhw = state('normalized')
    terminal,thw = state('terminal')
    eq('actual_normalized_symbol',normalized['eip'],symbols['f2_normalized']['address'])
    eq('prefix_size',len(read('mandatory_prefix.bin')),68)
    frame = struct.unpack('<17I',read('mandatory_prefix.bin'))
    eq('frame_vector_error',list(frame[12:14]),[12,0x28] if case == 'ss_nonpresent' else [2,0])
    eq('saved_EIP',frame[14],before['eip'])
    # Exact pinned QEMU qemu32 behavior, not a native-NMI architecture claim:
    # seg_helper.c @0f12d445bd exception_is_fault(2) returns 1 and
    # do_interrupt_protected sets saved RF for non-INT delivery. #SS also sets RF.
    # Preserve every other bit (including NT at emergency-task entry).
    saved_flags = before['eflags'] | (1 << 16)
    eq('saved_CS_flags',list(frame[15:17]),[before['cs'],saved_flags])
    eq('same_ring_no_tail',normalized['esp']+68,before['esp'])
    eq('frame_selectors',list(frame[:4]),[before['gs'],before['fs'],before['es'],before['ds']])
    eq('frame_pushad',list(frame[4:12]),[before['edi'],before['esi'],before['ebp'],before['esp']-20,before['ebx'],before['edx'],before['ecx'],before['eax']])
    eq('CR3_preserved',[bhw['CR3'],nhw['CR3'],thw['CR3']],[initial['CR3']]*3)
    eq('controlled_terminal_HLT','HLT=1' in read('terminal_hardware.txt').decode(),True)
    halt = halt_site(folder.parent/'kernel.elf')
    eq('actual_Rust_halt_PC',terminal['eip'],halt+2)
    serial = read('serial.txt')
    eq('F2_terminal_literal',b'F2 fatal terminal\n' in serial,True)
    require(b'rosti>' not in serial,'shell continuation')
    trace = read('qemu.log').decode(errors='replace')
    require('Triple fault' not in trace and 'CPU Reset' not in trace,'reset/triple fault')
    events = [(int(v,16),int(e,16),int(ip,16)) for v,e,ip in re.findall(r'v=([0-9a-f]+) e=([0-9a-f]+) i=0 cpl=0 IP=0008:([0-9a-f]+)',trace)]
    require(any(v == (12 if case == 'ss_nonpresent' else 2) and e == (0x28 if case == 'ss_nonpresent' else 0) and ip == before['eip'] for v,e,ip in events),'actual CPU exception at checkpoint')
    emergency = case in ('nmi_entry','nmi_output')
    eq('terminal_task',[bhw['TR'],nhw['TR'],thw['TR']],[32 if emergency else 24]*3)
    if case == 'ss_nonpresent':
        eq('MOV_SS_fault_instruction',read('fault_instruction.bin').hex(),'8ed0')
        eq('fault_IP',before['eip'],symbols['f3s_ss_fault']['address'])
        eq('selected_AX',before['eax'] & 65535,0x28)
        eq('fixture_GDTR',list(bhw['GDT']),[symbols['f3s_gdt']['address'],47])
        eq('six_entry_GDT',read('fixture_gdt.bin').hex(),(expected+bytes.fromhex('ffff00000013cf00')).hex())
        eq('production_GDT_unchanged',read('production_gdt_after.bin').hex(),expected.hex())
        limit,gbase,tr,ilimit,ibase = struct.unpack('<HIHHI',read('fixture_wire.bin'))
        eq('actual_SGDT_STR_SIDT',[gbase,limit,tr,ibase,ilimit],[*bhw['GDT'],24,*initial['IDT']])
        eq('usable_ESP_preserved',before['esp'],ready['esp'])
        require(not any(v in (8,13) for v,e,ip in events),'GP/DF is not SS')
        eq('no_DF_marker',b'F3_DF_FATAL' in serial,False)
    elif not emergency:
        eq('NMI_before_entry_checkpoint',before['eip'],symbols['f3_ready']['address'])
        eq('NMI_bootstrap_stack',before['esp'],ready['esp'])
        require(not any(v == 8 for v,e,ip in events),'ready NMI is not DF')
        eq('no_DF_marker',b'F3_DF_FATAL' in serial,False)
    else:
        fault,fhw = state('fault')
        entry,ehw = state('entry')
        eq('bad_ESP',fault['esp'],0x7c01000)
        eq('fault_IP',fault['eip'],symbols['f3s_df_fault']['address'])
        eq('pre_DF_TR',fhw['TR'],24)
        eq('DF_actual_entry',entry['eip'],symbols['f3_emergency_entry']['address'])
        eq('DF_actual_TR',ehw['TR'],32)
        eq('DF_actual_new_ESP',entry['esp'],0x7c09ffc)
        eq('DF_actual_CR3',ehw['CR3'],initial['CR3'])
        eq('hardware_DF_error',read('df_error.bin').hex(),'00000000')
        post = bytearray(expected)
        post[37] = 0x8b
        eq('DF_busy_GDT',read('post_task_gdt.bin').hex(),post.hex())
        eq('DF_backlink',struct.unpack_from('<I',read('post_emergency_tss.bin'))[0],24)
        first = [i for i,e in enumerate(events) if e == (14,2,fault['eip'])]
        require(first and any(v == 8 and e == 0 and i > first[0] for i,(v,e,ip) in enumerate(events)),'genuine PF->delivery PF->DF')
        require(any('check_exception old: 0xe new 0xe' in line.lower() for line in trace.splitlines()),'PF during PF delivery trace')
        require(0x7c06000 <= normalized['esp'] < 0x7c0a000 and 0x7c06000 <= terminal['esp'] < 0x7c0a000,'NMI bounded emergency stack')
        if case == 'nmi_entry':
            eq('NMI_first_emergency_instruction',before['eip'],entry['eip'])
            eq('NMI_entry_ESP',before['esp'],entry['esp'])
        else:
            eq('NMI_emitted_output_checkpoint',before['eip'],output_ip)
            eq('NMI_actual_OUT_opcode',read('output_instruction.bin').hex(),'ee')
            eq('NMI_actual_UART_DX',before['edx'] & 65535,0x3f8)
            eq('completed_emergency_snapshots',list(struct.unpack('<4I',read('emergency_observed.bin'))),[32,0x7c09ffc,initial['CR3'],0])
        # No DF marker assertion here: NMI containment is distinct from DF PASS.
    glog = [json.loads(line) for line in (folder/'gdb.jsonl').read_text().splitlines()]
    qlog = [json.loads(line) for line in (folder/'qmp.jsonl').read_text().splitlines()]
    nmis = [x for x in qlog if x['command'] == 'inject-nmi']
    eq('QMP_NMI_count',len(nmis),0 if case == 'ss_nonpresent' else 1)
    if nmis:
        eq('QMP_NMI_accepted',nmis[0]['reply'],{})
        eq('QMP_NMI_no_args',nmis[0]['arguments'],{})
    # Bind every retained wire image to a logged actual memory read.
    for name,origin in row['memory_origins'].items():
        raw = read(name)
        eq('capture_length_'+name,len(raw),origin['size'])
        for off in range(0,len(raw),512):
            chunk = raw[off:off+512]
            require(any(x['command'] == f"m{origin['address']+off:x},{len(chunk):x}" and x['reply'] == chunk.hex() for x in glog),'unbound raw memory '+name)
    origins = row['memory_origins']
    expected_origins = {'ready_gdt.bin':(base,40),'normal_tss.bin':(base+40,104),'emergency_tss.bin':(base+144,104),'idt8.bin':(initial['IDT'][0]+64,8),'idt2.bin':(initial['IDT'][0]+16,8),'idt12.bin':(initial['IDT'][0]+96,8),'mandatory_prefix.bin':(normalized['esp'],68)}
    if case == 'ss_nonpresent':
        expected_origins.update({'fixture_gdt.bin':(symbols['f3s_gdt']['address'],48),'production_gdt_after.bin':(base,40),'fixture_wire.bin':(symbols['f3s_wire']['address'],14),'fault_instruction.bin':(before['eip'],2)})
    if emergency:
        expected_origins.update({'df_error.bin':(0x7c09ffc,4),'post_task_gdt.bin':(base,40),'post_emergency_tss.bin':(base+144,104)})
    if case == 'nmi_output':
        expected_origins.update({'output_instruction.bin':(output_ip,1),'emergency_observed.bin':(base+248,16)})
    eq('exact_memory_origins',origins,{n:{'address':a,'size':s} for n,(a,s) in expected_origins.items()})
    expected_checkpoints = {'ready','before','normalized','terminal'} | ({'fault','entry'} if emergency else set())
    eq('exact_checkpoint_inventory',sorted(row['checkpoints']),sorted(expected_checkpoints))
    for label,ip in row['checkpoints'].items():
        packet = read(label+'_register_packet.txt').decode()
        text = read(label+'_hardware.txt').decode()
        require(any(x['command'] == 'g' and x['reply'] == packet for x in glog),'unbound register packet')
        require(any(x['command'] == 'human-monitor-command' and x['arguments'] == {'command-line':'info registers'} and x['reply'].replace('\r\n','\n') == text.replace('\r\n','\n') for x in qlog),'unbound hardware state')
        require(registers(packet.encode())['eip'] == ip,'checkpoint manifest')
    writes = [(i,x) for i,x in enumerate(glog) if x['command'].startswith(('G','P','M','X'))]
    require(not any(x['command'].startswith(('P','M','X')) for _,x in writes),'forbidden debugger write')
    target = symbols['f3s_ss' if case == 'ss_nonpresent' else 'f3s_df']['address']
    eq('sole_EIP_mutation_count',len(writes),0 if case == 'nmi_ready' else 1)
    expected_mutations = [] if case == 'nmi_ready' else [{'registers':{'eip':target}}]
    eq('declared_EIP_only_mutations',row['debugger_mutations'],expected_mutations)
    for i,x in writes:
        require(i > 0 and glog[i-1]['command'] == 'g','register write preimage')
        expected_packet = patch_registers(glog[i-1]['reply'],{'eip':target})
        eq('EIP_write_exact_packet',x['command'],'G'+expected_packet)
        eq('EIP_write_ACK',x['reply'],'OK')
        require(i+1 < len(glog) and glog[i+1]['command'] == 'g' and glog[i+1]['reply'] == expected_packet,'EIP write complete readback')
    return checks


def validate_matrix(folder):
    folder = Path(folder).resolve()
    plan = validate_prepared(folder)
    report = strict_json(folder/'report.json')
    require(report['schema'] == 'rosti.f3-supplement.v1' and report['overall'] == 'SUPPLEMENTAL_RING0_GREEN' and type(report['driver_exit']) is int and report['driver_exit'] == 0,'not completed supplement')
    require(report['parent_authorized'] is True and report['full_f3_acceptance'] is False and report['hardware_cpl3'] is False,'scope')
    require(type(report['build_exit']) is int and report['build_exit'] == 0 and report['source_freeze_stable'] is True,'build/source freeze')
    require(report['source_sha256'] == plan['source_sha256'] == strict_json(folder/'source_freeze_after.json'),'frozen inputs changed')
    pin_tree(folder,report['frozen_bytes'])
    require(report['prepared_dir'] == str(folder), 'invocation ownership')
    source = folder/'fixture/source'
    require(report['build_cwd'] == str(source), 'build cwd')
    require(report['build_command'] == ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(folder/'fixture/build')], 'build command')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and not p.relative_to(folder).as_posix().startswith('fixture/build/') and p.relative_to(folder).as_posix() not in ('report.json','running.json','validation.json')}
    require(set(report['frozen_bytes']) == actual, 'unfrozen supplemental artifact')
    kernel = folder/'kernel.elf'
    require(sha(kernel.read_bytes()) == report['kernel_sha256'],'ELF pin')
    symbols = elf_symbols(kernel)
    # Independently derive OUT address from retained disassembly and verify its
    # opcode in actual ELF32 PT_LOAD bytes, not just the disassembler's text.
    text = (folder/'disassembly.txt').read_text()
    start,end = symbols['f3_emergency_entry']['address'],symbols['f3_emergency_terminal']['address']
    ips = []
    for line in text.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)$',line)
        if m and start <= int(m[1],16) < end and re.search(r'\bout[bwl]?\b',m[3]):
            require(bytes.fromhex(m[2]) == b'\xee','OUT opcode')
            ips.append(int(m[1],16))
    require(ips == [report['output_ip']],'unique actual emitted OUT')
    raw = kernel.read_bytes()
    phoff = struct.unpack_from('<I',raw,28)[0]
    entsize,count = struct.unpack_from('<HH',raw,42)
    mapped = []
    for i in range(count):
        kind,offset,va,pa,filesz,memsz,flags,align = struct.unpack_from('<8I',raw,phoff+i*entsize)
        if kind == 1 and va <= ips[0] < va+filesz:
            mapped.append(raw[offset+ips[0]-va])
    require(mapped == [0xee],'OUT address not bound to actual ELF')
    expected = [f'{case}_{ram}' for ram in RAMS for case in CASES]
    rows = report['scenarios']
    require([r['name'] for r in rows] == expected,'exact eight rows/order; no substitutes')
    totals = 0
    for row,name in zip(rows,expected):
        child = folder/name
        require(strict_json(child/'guest_report.json') == row,'row substitution')
        require(row['overall'] == 'PASS' and row['capture_complete'] is True,'incomplete row')
        require(row['qemu_exit_before_cleanup'] is None and row['cleanup_action'] == 'kill_owned_Popen' and row['owned_qemu_exited'] is True and type(row['qemu_exit']) is int and row['qemu_exit'] != 0,'owned process cleanup')
        require(type(row['owned_pid']) is int and row['owned_pid'] > 0,'owned PID')
        require(row['name'] == f"{row['case']}_{row['ram_mib']}",'row identity')
        require(type(row['ram_mib']) is int and row['ram_mib'] in RAMS and row['case'] in CASES, 'row identity types')
        argv = row['command']
        require(type(argv) is list and all(type(x) is str for x in argv), 'QEMU argv')
        require(argv and Path(argv[0]).is_absolute() and Path(argv[0]).name.lower() in ('qemu-system-i386.exe','qemu-system-i386'), 'QEMU executable')
        ram = str(row['ram_mib'])
        expected_argv = ['-kernel',str(kernel),'-cpu','qemu32','-m',ram,'-smp','1','-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot','-serial','file:'+str(child/'serial.txt'),'-d','int,guest_errors','-D',str(child/'qemu.log'),'-S','-gdb']
        require(argv[1:len(expected_argv)+1] == expected_argv, 'exact QEMU profile')
        require(len(argv) == len(expected_argv)+4 and re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',argv[-3]) and argv[-2] == '-qmp' and re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+,server=on,wait=off',argv[-1]), 'local QEMU endpoints')
        require(set(row['frozen_bytes']) == {p.relative_to(child).as_posix() for p in child.rglob('*') if p.is_file() and p.name != 'guest_report.json'}, 'unfrozen scenario artifact')
        require(report['frozen_bytes'].get(name+'/guest_report.json') == sha((child/'guest_report.json').read_bytes()), 'unfrozen child report')
        require(all(report['frozen_bytes'].get(name+'/'+p) == digest for p,digest in row['frozen_bytes'].items()), 'root child pin mismatch')
        require(argv[argv.index('-kernel')+1] == str(kernel) and argv[argv.index('-m')+1] == str(row['ram_mib']),'QEMU ELF/RAM')
        require(argv[argv.index('-cpu')+1] == 'qemu32' and argv[argv.index('-smp')+1] == '1','CPU profile')
        require(not any(a in argv for a in ('-drive','-hda','-cdrom','-bios')),'unexpected device/image')
        pin_tree(child,row['frozen_bytes'])
        checks = validate_case(child,symbols,row['case'],row['ram_mib'],report['output_ip'],row)
        require(checks == row['checks'] and checks and all(c['pass'] is True for c in checks),'raw assertions mismatch')
        totals += len(checks)
    return {'schema':'rosti.f3-supplement-validation.v1','overall':'SUPPLEMENTAL_RING0_GREEN',
            'guest_count':len(rows),'assertion_count':totals,'full_f3_acceptance':False,
            'hardware_cpl3':False,'limitations':['Supplement only; full acceptance requires validated minimal plus supplement.','QEMU qemu32 emulator only; saved NMI RF behavior is specific to QEMU 10.2 commit 0f12d445bd, not physical Intel/AMD proof.','No F5 CPL3/USER/IOPL proof.','No full stack high-water/sufficiency proof.','NMI entry means after hardware task switch, before first emergency instruction; not mid task-switch.','NMI output means before first emitted UART OUT; no complete DF marker promised.']}


def validate(report_path, expected_source_sha256):
    """Validate actual supplemental raw evidence, returning absolute immutable pins."""
    path = Path(report_path).resolve()
    require(path.name == 'report.json', 'aggregate filename')
    report = strict_json(path)
    require(type(expected_source_sha256) is dict and expected_source_sha256 and report['source_sha256'] == expected_source_sha256, 'external source freeze mismatch')
    result = validate_matrix(path.parent)
    result['pins'] = {str(local(path.parent,n)):d for n,d in report['frozen_bytes'].items()}
    result['pins'][str(path)] = sha(path.read_bytes())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-dir',type=Path,required=True)
    p.add_argument('--prepared-only',action='store_true')
    a = p.parse_args()
    if a.prepared_only:
        plan = validate_prepared(a.prepared_dir)
        print(json.dumps({'overall':'PREPARED_ONLY','builds_or_qemu_executed':False,'source_input_count':len(plan['source_sha256']),'case_count':len(CASES),'ram_mib':list(RAMS)}))
    else:
        print(json.dumps(validate_matrix(a.prepared_dir),indent=2))


if __name__ == '__main__':
    main()
