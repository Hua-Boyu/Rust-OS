"""Fail-closed F3 minimal Ring-0 evidence reader; not full F3 acceptance.

No guest launch/build on import. Recompute wire assertions from retained bytes,
not from PASS flags. #SS and pre/during-entry NMI remain explicitly unverified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

RAMS = (128, 512)
SCENARIOS = ('ready', 'transition_guard_pf', 'emergency_guard_pf',
             'exhausted_esp_ud2_df', 'exhausted_esp_pf_df')
REQUIRED = tuple(f'{case}_{ram}' for ram in RAMS for case in SCENARIOS)
PLANNED = {'ss': 'NOT_VERIFIED: no reviewed usable-stack segment-limit fixture',
           'nmi_timing': 'NOT_VERIFIED: no tested before/during task-entry/output fixture'}
NAMES = ('eax','ecx','edx','ebx','esp','ebp','esi','edi','eip','eflags','cs','ss','ds','es','fs','gs')
CALL = b'    // F3_GREEN_CALL_BEGIN\n    memory::run_gdt_tss();\n    // F3_GREEN_CALL_END\n'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key '+key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def local(root, name):
    require(isinstance(name, str) and name and '\\' not in name, 'bad artifact name')
    p = Path(name)
    require(not p.is_absolute() and '..' not in p.parts and ':' not in name, 'artifact escape')
    target = (root/p).resolve()
    require(target.is_relative_to(root.resolve()), 'artifact symlink escape')
    return target


def pin_tree(root, pins):
    require(type(pins) is dict and bool(pins), 'empty byte pins')
    for name, digest in pins.items():
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'bad SHA256')
        require(sha(local(root, name).read_bytes()) == digest, 'frozen byte drift '+name)


def registers(raw):
    data = bytes.fromhex(raw.decode('ascii').strip())
    require(len(data) >= 64, 'short register packet')
    return dict(zip(NAMES, struct.unpack_from('<16I', data)))


def hardware(raw):
    text = raw.decode('ascii')
    fields = {n:int(v,16) for n,v in re.findall(r'\b(CR0|CR2|CR3|CR4|EIP|EFL)=([0-9a-fA-F]+)', text)}
    require(set(fields) == {'CR0','CR2','CR3','CR4','EIP','EFL'}, 'missing CPU controls')
    for name in ('GDT','IDT'):
        m = re.search(name+r'=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)', text)
        require(m is not None, 'missing '+name)
        fields[name] = tuple(int(v,16) for v in m.groups())
    m = re.search(r'\bTR\s*=([0-9a-fA-F]+)', text)
    require(m is not None, 'missing raw TR')
    fields['TR'] = int(m.group(1),16)
    require('CPL=0' in text and fields['EFL'] & 0x200 == 0, 'CPL/IF')
    require(fields['CR0'] & 0x80010001 == 0x80010001, 'CR0 profile')
    require(fields['CR4'] & ((1<<23)|0x30) == 0 and 'EFER=0000000000000000' in text, 'CPU profile')
    require(fields['CR3'] != 0 and fields['CR3'] % 4096 == 0, 'CR3')
    return fields


def descriptor(base, access):
    return struct.pack('<Q', 103 | ((base & 65535)<<16) | (((base>>16)&255)<<32) |
                       (access<<40) | (((base>>24)&255)<<56))


def tss(**updates):
    raw = bytearray(104)
    offsets = {'esp0':4,'ss0':8,'cr3':28,'eip':32,'eflags':36,'esp':56,
               'es':72,'cs':76,'ss':80,'ds':84,'fs':88,'gs':92}
    for name, value in updates.items():
        struct.pack_into('<I', raw, offsets[name], value)
    struct.pack_into('<H', raw, 102, 104)
    return bytes(raw)


def ready_assertions(read, symbols):
    """read(name)->bytes, ELF symbol map -> actual-value checks or ValueError."""
    checks = []
    def eq(name, actual, expected):
        checks.append({'name':name, 'actual':actual, 'expected':expected, 'pass':actual == expected})
        require(actual == expected, name)
    regs = registers(read('f3_ready_register_packet.txt'))
    hw = hardware(read('ready_hardware.txt'))
    base = symbols['f3_context']['address']
    eq('ready_eip', regs['eip'], symbols['f3_ready']['address'])
    eq('QMP_eip', hw['EIP'], regs['eip'])
    eq('GDTR', list(hw['GDT']), [base,39])
    eq('actual_TR', hw['TR'], 24)
    eq('selectors', [regs[n] for n in ('cs','ss','ds','es','fs','gs')], [8,16,16,16,16,16])
    eq('IF_DF', regs['eflags'] & 0x600, 0)
    expected_gdt = bytes(8)+bytes.fromhex('ffff00000099cf00ffff00000093cf00')+descriptor(base+40,0x8b)+descriptor(base+144,0x89)
    eq('raw_GDT', read('cpu_gdt.bin').hex(), expected_gdt.hex())
    eq('normal_TSS', read('normal_tss.bin').hex(), tss(esp0=0x7c05000,ss0=16).hex())
    eq('emergency_TSS', read('emergency_tss.bin').hex(), tss(esp0=0x7c0a000,ss0=16,cr3=hw['CR3'],eip=symbols['f3_emergency_entry']['address'],eflags=2,esp=0x7c0a000,es=16,cs=8,ss=16,ds=16,fs=16,gs=16).hex())
    eq('IDT8_taskgate', read('idt8.bin').hex(), '0000200000850000')
    glimit,gbase,tr,ilimit,ibase = struct.unpack('<HIHHI',read('sgdt_str_sidt.bin'))
    eq('SGDT_STR_SIDT', [gbase,glimit,tr,ibase,ilimit], [base,39,24,*hw['IDT']])
    require(hw['IDT'][1] >= 8*9-1, 'IDT extent')
    directory = struct.unpack('<1024I',read('directory.bin'))
    table = struct.unpack('<1024I',read('stack_table.bin'))
    pde = directory[31]
    eq('PDE31_supervisor_RW_nonlarge',pde & 0x87,3)
    # The capture manifest binds physical origins, not merely identical bytes.
    capture = json.loads(read('physical_capture.json'))
    eq('directory_origin',capture['directory'],hw['CR3'])
    eq('table_origin',capture['stack_table'],pde & 0xfffff000)
    frames = []
    for i in range(10):
        pte = table[i]
        if i in (0,5):
            eq(f'guard_{i}_absent',pte & 1,0)
        else:
            eq(f'stack_{i}_supervisor_RW',pte & 7,3)
            require(pte & 0xfffff000 != 0, 'zero stack frame')
            frames.append(pte & 0xfffff000)
    eq('unique_stack_frames',len(set(frames)),8)
    # Noncontiguous is permitted, not required. Physical identity aliases must
    # remain supervisor RW; capture their actual PDE/PTE pairs separately.
    aliases = json.loads(read('stack_aliases.json'))
    eq('alias_frames',[a['physical'] for a in aliases],frames)
    for i, alias in enumerate(aliases):
        eq(f'alias_{i}_PDE',alias['pde'],directory[frames[i]>>22])
        apa = alias['pde'] & 0xfffff000
        alias_raw = read('stack_table.bin') if apa == capture['stack_table'] else read(f'alias_table_{apa:08x}.bin')
        eq(f'alias_{i}_wire_PTE',alias['pte'],struct.unpack_from('<I',alias_raw,((frames[i]>>12)&1023)*4)[0])
        eq(f'alias_{i}_PDE_flags',alias['pde'] & 0x87,3)
        eq(f'alias_{i}_PTE',alias['pte'] & 0xfffff007,frames[i] | 3)
    eq('context_attempt',struct.unpack('<I',read('context_attempt.bin'))[0],1)
    return checks, regs, hw


def scenario_assertions(read, symbols, case):
    checks, ready, initial = ready_assertions(read,symbols)
    def eq(name,actual,expected):
        checks.append({'name':name,'actual':actual,'expected':expected,'pass':actual == expected})
        require(actual == expected,name)
    terminal_bytes = read('terminal_hardware.txt')
    terminal = hardware(terminal_bytes)
    eq('terminal_CR3_preserved',terminal['CR3'],initial['CR3'])
    eq('terminal_HLT', 'HLT=1' in terminal_bytes.decode('ascii'), True)
    trace = read('qemu.log').decode('ascii',errors='replace')
    serial = read('serial.txt')
    require('Triple fault' not in trace and 'CPU Reset' not in trace, 'fault/reset')
    require(b'rosti>' not in serial, 'shell continuation')
    if case == 'ready':
        eq('ready_terminal_TR',terminal['TR'],24)
        eq('no_DF_marker',b'F3_DF_FATAL' in serial,False)
        return checks
    before = registers(read('fault_register_packet.txt'))
    eq('fault_EIP',before['eip'],symbols['f3_fault_'+case]['address'])
    eq('fault_IF0',before['eflags'] & 0x200,0)
    first = 6 if case == 'exhausted_esp_ud2_df' else 14
    events = [(int(v,16),int(e,16),int(ip,16)) for v,e,ip in re.findall(r'v=([0-9a-f]+) e=([0-9a-f]+) i=0 cpl=0 IP=0008:([0-9a-f]+)',trace)]
    fault_error = 0 if first == 6 else 2
    first_indices = [i for i,(v,e,ip) in enumerate(events) if v == first and e == fault_error and ip == before['eip']]
    require(first_indices,'missing genuine initial fault')
    if case.endswith('_df'):
        require(any(v == 8 and e == 0 and i > first_indices[0] and any(pv == 14 for pv,pe,pip in events[first_indices[0]:i]) for i,(v,e,ip) in enumerate(events)),'missing ordered fault/PF/DF chain')
        eq('exhausted_actual_ESP',before['esp'],0x7c01000)
        raw = registers(read('emergency_entry_register_packet.txt'))
        entryhw = hardware(read('emergency_entry_hardware.txt'))
        eq('task_entry_EIP',raw['eip'],symbols['f3_emergency_entry']['address'])
        eq('task_entry_QMP_EIP',entryhw['EIP'],raw['eip'])
        eq('task_entry_TR',entryhw['TR'],32)
        eq('task_entry_ESP',raw['esp'],0x7c0a000-4)
        eq('task_entry_CS_SS',[raw['cs'],raw['ss']],[8,16])
        eq('task_entry_CR3',entryhw['CR3'],initial['CR3'])
        eq('task_entry_error',struct.unpack('<I',read('emergency_error.bin'))[0],0)
        eq('emergency_snapshot',list(struct.unpack('<4I',read('emergency_observed.bin'))),[32,0x7c0a000-4,initial['CR3'],0])
        eq('emergency_busy',read('post_task_gdt.bin')[37],0x8b)
        eq('normal_still_busy',read('post_task_gdt.bin')[29],0x8b)
        eq('task_backlink',struct.unpack_from('<I',read('post_emergency_tss.bin'))[0],24)
        eq('terminal_TR',terminal['TR'],32)
        require(0x7c06000 <= int(re.search(r'ESP=([0-9a-fA-F]+)',terminal_bytes.decode()).group(1),16) < 0x7c0a000,'terminal emergency stack')
        eq('exact_DF_marker_lines',serial.splitlines(keepends=True).count(b'F3_DF_FATAL\n'),1)
        require(b'F2 fatal terminal' not in serial,'ordinary fatal substituted')
        require(any(v == 8 and e == 0 for v,e,ip in events),'missing hardware DF')
        require(any(v == 14 for v,e,ip in events),'missing delivery PF')
    else:
        guard = 0x7c00000 if case == 'transition_guard_pf' else 0x7c05000
        frame = struct.unpack('<17I',read('mandatory_prefix.bin'))
        eq('guard_PF_frame',[frame[12],frame[13],frame[14]],[14,2,before['eip']])
        eq('guard_CR2',hardware(read('normalized_hardware.txt'))['CR2'],guard)
        eq('usable_stack_frame',registers(read('normalized_register_packet.txt'))['esp']+68,before['esp'])
        eq('ordinary_TR',terminal['TR'],24)
        eq('no_DF',any(v == 8 for v,e,ip in events),False)
        eq('F2_terminal_marker',b'F2 fatal terminal\n' in serial,True)
        eq('no_DF_marker',b'F3_DF_FATAL' in serial,False)
    return checks


def verify_capture_origins(folder, symbols, case, ram):
    """Bind retained wire images to logged actual addresses and CPU stops."""
    glog = [json.loads(line) for line in (folder/'gdb.jsonl').read_text().splitlines()]
    qlog = [json.loads(line) for line in (folder/'qmp.jsonl').read_text().splitlines()]
    def memory(filename, address, length):
        raw = (folder/filename).read_bytes()
        require(len(raw) == length,'memory image size '+filename)
        for offset in range(0,length,512):
            n = min(512,length-offset)
            require(any(item['command'] == f'm{address+offset:x},{n:x}' and item['reply'] == raw[offset:offset+n].hex() for item in glog),'unbound memory capture '+filename)
    def physical(filename, address):
        require(4096 <= address and address+4096 <= ram*1024*1024,'physical RAM extent')
        require(any(item['command'] == 'pmemsave' and item['arguments'] == {'val':address,'size':4096,'filename':(folder/filename).as_posix()} for item in qlog),'unbound physical capture '+filename)
    hw = hardware((folder/'ready_hardware.txt').read_bytes())
    base = symbols['f3_context']['address']
    for filename,address,length in [('cpu_gdt.bin',base,40),('normal_tss.bin',base+40,104),('emergency_tss.bin',base+144,104),('context_attempt.bin',base+264,4),('idt8.bin',hw['IDT'][0]+64,8),('sgdt_str_sidt.bin',symbols['f3_wire_probe']['address'],14)]:
        memory(filename,address,length)
    directory = struct.unpack('<1024I',(folder/'directory.bin').read_bytes())
    table = struct.unpack('<1024I',(folder/'stack_table.bin').read_bytes())
    physical('directory.bin',hw['CR3'])
    physical('stack_table.bin',directory[31] & 0xfffff000)
    for i in (1,2,3,4,6,7,8,9):
        frame = table[i] & 0xfffff000
        require(4096 <= frame and frame+4096 <= ram*1024*1024,'stack frame RAM extent')
        apa = directory[frame>>22] & 0xfffff000
        if apa != directory[31] & 0xfffff000:
            physical(f'alias_table_{apa:08x}.bin',apa)
    owners = strict_json(folder/'owner_capture.json')
    expected = {n:s for n,s in symbols.items() if 'retained_owner' in n and ('OWNER' in n or 'STATE' in n)}
    require(expected and len(owners) == len(expected) and {o['symbol'] for o in owners} == set(expected),'owner inventory')
    for item in owners:
        sym = expected[item['symbol']]
        require(item['address'] == sym['address'] and item['size'] == sym['size'] and 0 < sym['size'] <= 4096,'owner symbol identity')
        memory(item['file'],sym['address'],sym['size'])
        if 'STATE' in item['symbol']:
            require((folder/item['file']).read_bytes() == b'\x03','owner not Terminal')
    if case.endswith('_df'):
        memory('emergency_error.bin',0x7c0a000-4,4)
        memory('emergency_observed.bin',base+248,16)
        memory('post_task_gdt.bin',base,40)
        memory('post_emergency_tss.bin',base+144,104)
    elif case != 'ready':
        memory('mandatory_prefix.bin',registers((folder/'normalized_register_packet.txt').read_bytes())['esp'],68)
    for filename in ('ready_hardware.txt','terminal_hardware.txt')+ (('emergency_entry_hardware.txt',) if case.endswith('_df') else (('normalized_hardware.txt',) if case != 'ready' else ())):
        text = (folder/filename).read_text()
        require(any(item['command'] == 'human-monitor-command' and item['arguments'] == {'command-line':'info registers'} and item['reply'].replace('\r\n','\n') == text for item in qlog),'unbound CPU observation '+filename)
    for filename in ('f3_ready_register_packet.txt','fault_register_packet.txt')+(('emergency_entry_register_packet.txt',) if case.endswith('_df') else (('normalized_register_packet.txt',) if case != 'ready' else ())):
        packet = (folder/filename).read_text()
        require(any(item['command'] == 'g' and item['reply'] == packet for item in glog),'unbound register observation '+filename)


def validate_matrix(report, folder):
    """Validate exact minimal matrix, provenance, owned cleanup and byte pins.

    Raises ValueError/IOError on malformed evidence. This does NOT admit #SS,
    NMI timing, full F3 acceptance, CPL3, or stack-sufficiency claims.
    """
    folder = Path(folder).resolve()
    require(report['schema'] == 'rosti.f3-minimal-ring0.v1', 'schema')
    require(report['overall'] == 'MINIMAL_RING0_GREEN' and type(report['driver_exit']) is int and report['driver_exit'] == 0 and type(report['build_exit']) is int and report['build_exit'] == 0,'not completed GREEN')
    require(report['invocation_dir'] == str(folder),'aggregate invocation ownership')
    require(report['full_f3_acceptance'] is False and report['hardware_cpl3'] is False,'scope inflation')
    require(report['planned_only'] == PLANNED,'unverified obligations missing')
    require(report['source_freeze_stable'] is True,'unstable source')
    pin_tree(folder, report['frozen_bytes'])
    before = strict_json(folder/'source_freeze_before.json')
    after = strict_json(folder/'source_freeze_after.json')
    require(before == after and type(before) is dict and len(before) > 0,'freeze mismatch')
    require(report['source_input_count'] == len(before),'source count')
    require(report['source_sha256'] == before,'source pins mismatch')
    mandatory_sources = {'src/main.rs','src/gdt.rs','src/gdt_tss.rs','src/f3_entry.s','src/interrupt.rs','src/memory/mod.rs','src/memory/paging.rs','src/memory/retained_owner.rs','scripts/f3_gdt_guest.py','scripts/f3_evidence.py','scripts/test_f3_evidence.py','Cargo.toml','Cargo.lock','target.json','linker.ld','rust-toolchain.toml','.cargo/config.toml'}
    require(mandatory_sources <= before.keys(),'missing canonical source inputs')
    for name,digest in before.items():
        require(sha(local(folder/'frozen_inputs',name).read_bytes()) == digest,'retained input drift '+name)
        require(report['frozen_bytes'].get('frozen_inputs/'+name) == digest,'unfrozen source input '+name)
    require(sha((folder/'driver.py').read_bytes()) == before['scripts/f3_gdt_guest.py'],'driver provenance')
    require(sha((folder/'validator.py').read_bytes()) == before['scripts/f3_evidence.py'],'validator provenance')
    source = folder/'fixture/source'
    for name,digest in before.items():
        if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
            raw = local(source,name).read_bytes()
            require(report['frozen_bytes'].get('fixture/source/'+name) == sha(raw),'unfrozen copied source '+name)
            if name == 'src/main.rs':
                call,assembly = (folder/'fixture_call.rs').read_bytes(),(folder/'fixture_assembly.rs').read_bytes()
                from f3_gdt_guest import green_assembly
                require(call == CALL and assembly == green_assembly() and raw.count(call) == 1 and raw.count(assembly) == 1,'fixture delimiters/bytes')
                changed = raw
                raw = raw.replace(call,b'',1).replace(assembly,b'',1)
                anchor = b'    // stub: enable ps2 & interrupts'
                require(raw.count(anchor) == 1 and changed == raw.replace(anchor,call+anchor)+assembly,'postpaging fixture position')
                require(report['stripping_equality'] is True and report['original_main_sha256'] == digest and report['injected_main_sha256'] == sha(changed) and report['assembly_sha256'] == sha(assembly) and report['call_sha256'] == sha(call),'fixture provenance fields')
            require(sha(raw) == digest,'copied canonical source drift '+name)
    command = report['build_command']
    require(command == ['cargo','+nightly','build','--locked','--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(folder/'fixture/build')],'build command')
    require(report['build_cwd'] == str(source),'build cwd')
    require(sha((folder/'kernel.elf').read_bytes()) == report['kernel_sha256'],'kernel pin')
    from b13_entry_inject import elf_symbols
    symbols = elf_symbols(folder/'kernel.elf')
    rows = report['scenarios']
    require(type(rows) is list and len(rows) == len(REQUIRED),'matrix count')
    require([r['name'] for r in rows] == list(REQUIRED),'missing/duplicate/substitute matrix row')
    required_root = {'source_freeze_before.json','source_freeze_after.json','kernel.elf','build.log','fixture_call.rs','fixture_assembly.rs','driver.py','validator.py','design_review.json','design.md'}
    require(required_root <= report['frozen_bytes'].keys(),'missing root byte pins')
    review = strict_json(folder/'design_review.json')
    require(review['verdict'] == 'APPROVE' and review['blocker_count'] == 0,'review')
    require(sha((folder/'design.md').read_bytes()) == review['design_raw_sha256'],'review design pin')
    for row, name in zip(rows,REQUIRED):
        case,ram = name.rsplit('_',1)
        require(row['case'] == case and type(row['ram_mib']) is int and row['ram_mib'] == int(ram),'row identity')
        child = local(folder,name)
        stored = strict_json(child/'guest_report.json')
        require(stored == row,'row report substitution')
        require(row['overall'] == 'PASS' and row['capture_complete'] is True,'incomplete row')
        require(type(row['owned_pid']) is int and row['owned_pid'] > 0,'owned PID')
        require(row['qemu_exit_before_cleanup'] is None and row['cleanup_action'] == 'kill_owned_Popen' and row['owned_qemu_exited'] is True and type(row['qemu_exit']) is int and row['qemu_exit'] != 0,'owned cleanup')
        require(row['kernel_sha256'] == report['kernel_sha256'],'row kernel')
        argv = row['command']
        require(type(argv) is list and all(type(x) is str for x in argv),'QEMU argv')
        require(argv and Path(argv[0]).is_absolute() and Path(argv[0]).name.lower() in ('qemu-system-i386.exe','qemu-system-i386'),'QEMU executable identity')
        expected = ['-kernel',str(folder/'kernel.elf'),'-cpu','qemu32','-m',ram,'-smp','1','-machine','pc','-display','none','-nic','none','-monitor','none','-no-reboot','-serial','file:'+str(child/'serial.txt'),'-d','int,guest_errors','-D',str(child/'qemu.log'),'-S','-gdb']
        require(argv[1:len(expected)+1] == expected,'QEMU command profile')
        require(len(argv) == len(expected)+4 and re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',argv[-3]) and argv[-2] == '-qmp' and re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+,server=on,wait=off',argv[-1]),'QEMU local endpoints')
        pin_tree(child,row['frozen_bytes'])
        files = set(row['frozen_bytes'])
        actual_files = {p.relative_to(child).as_posix() for p in child.rglob('*') if p.is_file() and p.name != 'guest_report.json'}
        require(files == actual_files,'unfrozen scenario artifact')
        common = {'sgdt_str_sidt.bin','owner_capture.json','f3_ready_register_packet.txt','ready_hardware.txt','cpu_gdt.bin','normal_tss.bin','emergency_tss.bin','idt8.bin','directory.bin','stack_table.bin','physical_capture.json','stack_aliases.json','context_attempt.bin','terminal_hardware.txt','qemu.log','serial.txt','gdb.jsonl','qmp.jsonl','stderr.txt'}
        if case != 'ready':
            common |= {'fault_register_packet.txt'}
        if case.endswith('_df'):
            common |= {'emergency_entry_register_packet.txt','emergency_entry_hardware.txt','emergency_error.bin','emergency_observed.bin','post_task_gdt.bin','post_emergency_tss.bin'}
        elif case != 'ready':
            common |= {'mandatory_prefix.bin','normalized_hardware.txt','normalized_register_packet.txt'}
        require(common <= files,'missing scenario frozen pins')
        require(all(f'{name}/{p}' in report['frozen_bytes'] and report['frozen_bytes'][f'{name}/{p}'] == digest for p,digest in row['frozen_bytes'].items()),'root/scenario pin mismatch')
        require(f'{name}/guest_report.json' in report['frozen_bytes'],'unfrozen guest report')
        mutations = row['debugger_mutations']
        expected_mutations = [{'registers':{'eip':symbols['f3_trigger_'+case]['address']}}]
        require(mutations == expected_mutations,'unauthorized debugger mutation')
        log = [json.loads(line) for line in (child/'gdb.jsonl').read_text().splitlines()]
        writes = [x for x in log if x['command'].startswith(('G','P','M','X'))]
        require(len(writes) == len(expected_mutations) and all(x['command'].startswith('G') and x['reply'] == 'OK' for x in writes),'debugger transcript mutation mismatch')
        if writes:
            from b13_entry_inject import patch_registers
            original_packet = (child/'f3_ready_register_packet.txt').read_text()
            expected_packet = patch_registers(original_packet,{'eip':symbols['f3_trigger_'+case]['address']})
            require(writes[0]['command'] == 'G'+expected_packet,'redirect changed non-EIP register')
        verify_capture_origins(child,symbols,case,row['ram_mib'])
        checks = scenario_assertions(lambda p: local(child,p).read_bytes(),symbols,case)
        require(json.dumps(row['checks'],sort_keys=True) == json.dumps(checks,sort_keys=True) and bool(checks) and all(c['pass'] is True for c in checks),'actual-value checks mismatch')
    return {'schema':'rosti.f3-evidence-validation.v1','overall':'PASS_MINIMAL_ONLY','scenario_count':len(rows),'full_f3_acceptance':False,'planned_only':PLANNED}


def validate(report_path, expected_source_sha256):
    """Parent integration API: externally frozen source, absolute byte pins.

    A success admits only REQUIRED's minimal Ring-0 matrix. Full F3 acceptance
    remains false because genuine #SS and NMI timing are not verified here.
    """
    path = Path(report_path).resolve()
    report = strict_json(path)
    require(type(expected_source_sha256) is dict and expected_source_sha256 and report['source_sha256'] == expected_source_sha256,'external source freeze mismatch')
    result = validate_matrix(report,path.parent)
    result['pins'] = {str(local(path.parent,name)):digest for name,digest in report['frozen_bytes'].items()}
    result['pins'][str(path)] = sha(path.read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_matrix(strict_json(args.report),args.report.parent),indent=2))
        return 0
    except (ValueError,KeyError,TypeError,OSError,IndexError,struct.error) as exc:
        print(json.dumps({'overall':'FAIL','error':str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
