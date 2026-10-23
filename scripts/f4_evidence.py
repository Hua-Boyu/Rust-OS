"""Offline, fail-closed F4 Ring0 matrix readback. Never builds or launches a guest.

All layout offsets come from the exact retained ELF through f4_dwarf.extract.
This establishes the bounded F4 Ring0 contract, NOT CPL3 or canonical acceptance.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')

from b13_entry_inject import elf_symbols
from f3_evidence import hardware, registers, strict_json, local, descriptor, tss
from f4_dwarf import extract
from f4_ready_guest import ASM as READY_ASM, CALL

SCENARIOS = ('ready', 'code_write', 'lower_guard', 'unused_hole', 'occupied_refusal', 'capacity_refusal')
RAMS = (128, 512)
REQUIRED = tuple((s, r) for s in SCENARIOS for r in RAMS)
DESIGN_SHA = 'ea0a49eda8784d358995d556046adfa89ca9d4bafd89070765816c6aedf086ee'
REVIEW_SHA = '719aa78173cff2c8dcca7b91c5cb8e21b1e466a3bbb9520c6e2e774c5ea12ce7'
DESIGN = 'test_results/phase11f4_user_arena/design.md'
REVIEW = 'test_results/phase11f4_user_arena/reviews/design_review_02.json'
DISPOSITION = 'test_results/phase11f4_user_arena/operator_disposition_01.json'
FIELDS = ('gs','fs','es','ds','edi','esi','ebp','pushad_esp','ebx','edx','ecx','eax','vector','error','eip','cs','eflags')
SLOTS = ('payload', 'sentinel', 'transition0', 'transition1', 'transition2', 'transition3', 'emergency0', 'emergency1', 'emergency2', 'emergency3', 'user_stack', 'arena_table')
FAULTS = {'code_write': (0x40000000, 3, bytes.fromhex('c7050000004078563412')), 'lower_guard': (0x403fe000, 0, bytes.fromhex('a100e03f40')), 'unused_hole': (0x40001000, 0, bytes.fromhex('a100100040'))}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def u32(raw, offset=0):
    return struct.unpack_from('<I', raw, offset)[0]


def words(raw):
    need(len(raw) == 4096, 'page capture size')
    return struct.unpack('<1024I', raw)


def checkpoint(name):
    return ('    #[cfg(all(not(test), target_os = "none"))]\n    unsafe { core::arch::asm!(".global '+name+'", ".set '+name+', .", options(nostack)); }\n').encode()


def assembly(variant):
    need(variant in ('normal', 'occupied_refusal', 'capacity_refusal'), 'fixture variant')
    tail = b'4:\n jmp f4_run_user_arena\n'
    need(READY_ASM.count(tail) == 1, 'CPUID assembly anchor')
    entry = '''4:
.global f4_fixture_entry
f4_fixture_entry:
'''
    if variant == 'occupied_refusal':
        # Actual CPU fixture write, never a debugger memory/control write.
        entry += ''' mov %cr3,%eax
 mov (%eax),%edx
 and $0xfffffffb,%edx
 mov %edx,1024(%eax)
.global f4_occupied_checkpoint
f4_occupied_checkpoint:
'''
    entry += ' jmp f4_run_user_arena\n'
    asm = READY_ASM.replace(tail, entry.encode())
    probes = '''
core::arch::global_asm!(r#"
.section .text
.global f4_select_code_write
f4_select_code_write:
 cli
 cld
 movl $0x5a17c0de,0x403ff080
 movl 0x403ff080,%eax
.global f4_positive
f4_positive:
 nop
.global f4_fault_code_write
f4_fault_code_write:
 movl $0x12345678,0x40000000
 ud2
.global f4_select_lower_guard
f4_select_lower_guard:
 cli
 cld
.global f4_fault_lower_guard
f4_fault_lower_guard:
 movl 0x403fe000,%eax
 ud2
.global f4_select_unused_hole
f4_select_unused_hole:
 cli
 cld
.global f4_fault_unused_hole
f4_fault_unused_hole:
 movl 0x40001000,%eax
 ud2
"#, options(att_syntax));
'''.encode()
    return asm + probes


def transformations(originals, variant):
    """Explicit byte transforms, also independently reapplied during readback."""
    result = dict(originals)
    anchor = b'    // stub: enable ps2 & interrupts'
    main = originals['src/main.rs']
    need(main.count(anchor) == 1, 'postpaging anchor')
    result['src/main.rs'] = main.replace(anchor, CALL + anchor) + assembly(variant)
    arena = originals['src/memory/user_arena.rs']
    fence = b'    compiler_fence(Ordering::Release);'
    need(arena.count(fence) == 1, 'last-publication fence anchor')
    result['src/memory/user_arena.rs'] = arena.replace(fence, checkpoint('f4_publication_authority') + fence)
    if variant == 'capacity_refusal':
        owner = originals['src/memory/retained_owner.rs']
        allocation = b'    owner.user_stack = fa.allocate_owned();'
        need(owner.count(allocation) == 1, 'first-new-F4 allocation anchor')
        result['src/memory/retained_owner.rs'] = owner.replace(allocation, checkpoint('f4_capacity_checkpoint') + b'    owner.user_stack = None; // F4 fixture deterministic denial, NOT physical OOM')
    need(result['src/main.rs'].replace(CALL, b'', 1).replace(assembly(variant), b'', 1) == main, 'main stripping equality')
    need(result['src/memory/user_arena.rs'].replace(checkpoint('f4_publication_authority'), b'', 1) == arena, 'publication checkpoint stripping equality')
    if variant == 'capacity_refusal':
        injected = checkpoint('f4_capacity_checkpoint') + b'    owner.user_stack = None; // F4 fixture deterministic denial, NOT physical OOM'
        need(result['src/memory/retained_owner.rs'].replace(injected, allocation, 1) == owner, 'denial transform stripping equality')
    return result


def tree_pins(root, exclude=()):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and p.relative_to(root).as_posix() not in exclude}


def verify_pins(root, pins, exclude=()):
    need(type(pins) is dict and bool(pins), 'missing pins')
    for name, digest in pins.items():
        need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'malformed digest')
        need(not local(root, name).is_symlink(), 'symlink artifact')
        need(sha(local(root, name).read_bytes()) == digest, 'pin mismatch: ' + name)
    need(tree_pins(root, exclude) == pins, 'unlisted/substituted artifacts')


def symbol_one(symbols, predicate):
    found = [(n, s) for n, s in symbols.items() if predicate(n)]
    need(len(found) == 1, 'ambiguous/missing symbol: ' + repr([n for n, _ in found]))
    return found[0][1]


def storage_symbols(symbols):
    return {
        'owner': symbol_one(symbols, lambda n: 'retained_owner' in n and '5OWNER' in n),
        'state': symbol_one(symbols, lambda n: 'retained_owner' in n and '5STATE' in n),
        'allocator': symbol_one(symbols, lambda n: 'memory' in n and '11FRAME_ALLOC' in n),
    }


def decode_owner(raw, layout):
    start = layout['owner_inner_offset']
    fields = layout['RetainedOwner']['fields']
    option, lease = layout['OptionFrameLease'], layout['FrameLease']['fields']
    need(len(raw) == layout['OwnerMutex']['size'], 'owner mutex extent')
    def slot(offset):
        base = start + offset
        discr = u32(raw, base + option['discriminant_offset'])
        need(discr in (0, 1), 'Option discriminant')
        if discr == 0:
            return None
        base += option['lease_offset']
        return {'addr': struct.unpack_from('<Q', raw, base + lease['addr'])[0], 'id': u32(raw, base + lease['id']), 'domain': u32(raw, base + lease['domain'])}
    slots = {}
    for name in SLOTS:
        array = re.fullmatch('(transition|emergency)([0-3])', name)
        offset = fields[array[1]] + int(array[2]) * option['size'] if array else fields[name]
        slots[name] = slot(offset)
    return {'slots': slots, 'capture': struct.unpack_from('<16I', raw, start + fields['capture']), 'arena_capture': struct.unpack_from('<16I', raw, start + fields['arena_capture']), 'domain': u32(raw, start + fields['allocator_domain']), 'capacity_before': struct.unpack_from('<3I', raw, start + fields['capacity_before']), 'capacity_after': struct.unpack_from('<3I', raw, start + fields['capacity_after'])}


def decode_allocator(raw, layout):
    need(len(raw) == layout['AllocatorMutex']['size'], 'allocator mutex extent')
    return memoryview(raw)[layout['allocator_inner_offset']:]


def allocator_stats(raw, layout):
    raw = decode_allocator(raw, layout)
    off = layout['FrameAllocator']['fields']['stats']
    return {n: u32(raw, off + o) for n, o in layout['FrameStats']['fields'].items()}


def authority(owner, allocator, layout, expected_count, phase):
    fa = decode_allocator(allocator, layout)
    fields = layout['FrameAllocator']['fields']
    domain = u32(fa, fields['domain'])
    need(fa[fields['initialized']] == 1 and domain != 0, 'initialized allocator domain')
    present = {n: v for n, v in owner['slots'].items() if v is not None}
    need(tuple(present) == SLOTS[:expected_count], 'exact retained acquired prefix')
    need(len({l['addr'] for l in present.values()}) == expected_count, 'duplicate retained frame')
    need(len({l['id'] for l in present.values()}) == expected_count, 'duplicate allocation identity')
    if expected_count:
        need(owner['domain'] == domain, 'owner allocator domain')
    for name, lease in present.items():
        addr, ident = lease['addr'], lease['id']
        need(4096 <= addr < 256*1024*1024 and addr % 4096 == 0 and ident != 0 and lease['domain'] == domain, 'live lease identity ' + name)
        index = addr // 4096
        need(u32(fa, fields['alloc_id'] + index*4) == ident, 'FA live alloc_id ' + name)
        def bit(field):
            return bool(fa[fields[field] + index//8] & (1 << (index % 8)))
        need(bit('covered') and not bit('ncov') and not bit('free') and bit('ever'), 'FA allocation eligibility ' + name)
        runtime = name.startswith(('transition', 'emergency')) or (phase in ('publish','ready','positive','fault','normalized','terminal') and expected_count == 12 and name in ('payload','user_stack'))
        structure = expected_count == 12 and name == 'arena_table' and phase in ('publish','ready','positive','fault','normalized','terminal')
        need(bit('runtime_pins') == runtime and bit('structure_pins') == structure, 'FA role pins ' + name + '/' + phase)
    return present


def snapshot_assertions(root, label, row, layout, symbols, expected_count):
    read = lambda n: local(root, n).read_bytes()
    meta = strict_json(root / (label + '_capture.json'))
    regs = registers(read(label + '_register_packet.txt'))
    hw = hardware(read(label + '_hardware.txt'))
    need(hw['CR4'] & (1 << 21) == 0 and regs['cs'] == 8 and regs['ss'] == 16, 'SMAP0/CPL0')
    need(hw['EIP'] == regs['eip'] and hw['EFL'] == regs['eflags'], 'hardware/RSP disagreement')
    if meta['symbol'] is not None:
        need(regs['eip'] == symbols[meta['symbol']]['address'], 'exact stopped EIP')
    need(meta['paused'] is True and meta['registers_stable'] is True, 'stopped capture authority')
    stores = storage_symbols(symbols)
    for key, sym in stores.items():
        need(meta[key] == sym, 'metadata symbol origin')
    directory = words(read(label + '_directory.bin'))
    need(read(label + '_directory.bin') == read(label + '_directory_repeat.bin'), 'stable directory')
    need(meta['directory'] == {'address': hw['CR3'], 'size': 4096}, 'directory origin')
    tables = {}
    expected_indices = [i for i, p in enumerate(directory) if p & 1]
    need([t['index'] for t in meta['tables']] == expected_indices, 'complete directory/table inventory')
    for t in meta['tables']:
        i, pde = t['index'], directory[t['index']]
        need(pde & 0x80 == 0 and t['address'] == pde & 0xfffff000 and t['size'] == 4096, 'physical table origin')
        raw = read(t['file'])
        need(raw == read(t['repeat']), 'stable table capture')
        tables[i] = words(raw)
    for p in directory:
        need(p & 1 or p == 0, 'nonpresent PDE exact zero')
    owner = decode_owner(read(label + '_owner.bin'), layout)
    allocator = read(label + '_allocator.bin')
    for name in ('owner','allocator','state'):
        need(read(label+'_'+name+'.bin') == read(label+'_'+name+'_repeat.bin'), 'stable metadata '+name)
        need(stores[name]['size'] == (layout['OwnerMutex']['size'] if name == 'owner' else layout['AllocatorMutex']['size'] if name == 'allocator' else 1), 'exact target symbol/type size')
    fa = decode_allocator(allocator, layout)
    af = layout['FrameAllocator']['fields']
    def fa_bit(field, pa):
        index = pa//4096
        need(0 < index < 65536, 'managed paging structure')
        return bool(fa[af[field]+index//8] & (1 << (index%8)))
    # Actual directory/table structures must themselves be live allocator
    # structure pins, not just numbers with supervisor-looking flags.
    for pa in {hw['CR3']} | {p & 0xfffff000 for p in directory if p & 1}:
        need(fa_bit('structure_pins',pa) and not fa_bit('runtime_pins',pa) and not fa_bit('free',pa) and u32(fa,af['alloc_id']+(pa//4096)*4) != 0, 'live retained paging structure authority')
    leases = authority(owner, allocator, layout, expected_count, label)
    need(len(read(label + '_state.bin')) == stores['state']['size'] == 1, 'state latch size')
    def alias(pa):
        dp = directory[pa >> 22]
        need(dp & 0x87 == 3, 'supervisor RW alias PDE')
        lp = tables[pa >> 22][(pa >> 12) & 1023]
        need(lp & 0xfffff007 == pa | 3, 'supervisor RW identity PTE')
    for lease in leases.values():
        alias(lease['addr'])
    alias(hw['CR3'])
    for i in tables:
        alias(directory[i] & 0xfffff000)
    for i, table in tables.items():
        if i != 256 or expected_count != 12 or label in ('initial','pre'):
            need(directory[i] & 4 == 0 and all(p & 4 == 0 for p in table), 'supervisor USER promotion')
    published = expected_count == 12 and label not in ('initial','pre','publish')
    if expected_count == 12:
        code, stack, table = [leases[n]['addr'] for n in ('payload','user_stack','arena_table')]
        need(directory[257] == 0, 'upper arena boundary')
        arena = words(read(label + '_arena_table.bin'))
        need(meta['arena_table_address'] == table, 'retained arena-table origin')
        if label == 'pre':
            need(directory[256] == 0 and arena == (0,)*1024, 'unpublished unpinned initial staging')
        else:
            expected = [0]*1024
            expected[0], expected[1023] = code | 0x205, stack | 0x207
            need(all((p & ~0x60 if e else p) == e for p, e in zip(arena, expected)), 'exact owned two-leaf arena')
            need(directory[256] & ~0x20 == (table | 7 if published else 0), 'last PDE publication')
        pattern = bytearray(4096)
        pattern[:4], pattern[2048:2059] = bytes.fromhex('0f0bebfc'), b'F4-RO-DATA\0'
        need(read(label + '_payload.bin') == pattern, 'complete code/data page')
        stack_pattern = bytearray(4096)
        if row['scenario'] == 'code_write' and label in ('positive','fault','normalized','terminal'):
            struct.pack_into('<I', stack_pattern, 128, 0x5a17c0de)
        need(read(label + '_stack.bin') == stack_pattern, 'complete stack page / positive control readback')
        need(meta['payload_address'] == code and meta['stack_address'] == stack, 'payload physical origins')
        # Actual F3 mappings, retained lease identity and guard slots.
        for j, name in enumerate(SLOTS[2:10]):
            index = j + 1 if j < 4 else j + 2
            need(tables[31][index] & 0xfffff007 == leases[name]['addr'] | 3, 'F3 stack physical identity')
        need(tables[31][0] == tables[31][5] == 0, 'F3 guards')
        if published:
            need(hw['TR'] == 24 and hw['GDT'] == (symbols['f3_context']['address'],39), 'unchanged F3 GDT/TR')
            base = symbols['f3_context']['address']
            need(read(label + '_gdt.bin') == bytes(8)+bytes.fromhex('ffff00000099cf00ffff00000093cf00')+descriptor(base+40,0x8b)+descriptor(base+144,0x89), 'exact five-entry GDT')
            need(read(label + '_normal_tss.bin') == tss(esp0=0x7c05000,ss0=16), 'normal TSS')
            need(read(label + '_emergency_tss.bin') == tss(esp0=0x7c0a000,ss0=16,cr3=hw['CR3'],eip=symbols['f3_emergency_entry']['address'],eflags=2,esp=0x7c0a000,es=16,cs=8,ss=16,ds=16,fs=16,gs=16), 'emergency TSS')
            need(read(label + '_idt8.bin') == bytes.fromhex('0000200000850000'), 'F3 task gate')
    return {'hw': hw, 'regs': regs, 'directory': directory, 'tables': tables, 'owner': owner, 'leases': leases, 'stats': allocator_stats(allocator, layout), 'state': read(label + '_state.bin')[0]}


def preserve(before, after, allow_f3=False, occupied=False):
    need(before['hw']['CR3'] == after['hw']['CR3'], 'CR3 changed')
    for i, (a,b) in enumerate(zip(before['directory'], after['directory'])):
        if i == 256:
            continue
        need(a & ~0x20 == b & ~0x20, 'supervisor directory drift')
    for i, old in before['tables'].items():
        if i == 256 and occupied:
            continue
        new = after['tables'][i]
        for j, (a,b) in enumerate(zip(old,new)):
            if allow_f3 and i == 31 and j < 10:
                continue
            need(a & ~0x60 == b & ~0x60, 'supervisor PTE drift')


def transport_assertions(root, row, symbols):
    """Bind saved packets and physical origins to the complete protocol logs."""
    glog = [json.loads(line) for line in (root/'gdb.jsonl').read_text().splitlines()]
    qlog = [json.loads(line) for line in (root/'qmp.jsonl').read_text().splitlines()]
    need(glog and qlog, 'empty transport logs')
    allowed_qmp = {'qmp_capabilities','query-version','query-status','human-monitor-command','pmemsave','cont','stop'}
    need(all(e['command'] in allowed_qmp for e in qlog), 'unexpected QMP mutation')
    need(all(e['arguments'] == {'command-line':'info registers'} for e in qlog if e['command'] == 'human-monitor-command'), 'HMP mutation')
    need([e['reply'] for e in qlog if e['command'] == 'query-version'] == [row['qemu_version']], 'QEMU version transport binding')
    pmem = {}
    for e in qlog:
        if e['command'] == 'pmemsave':
            args = e['arguments']
            filename = args['filename']
            need(filename not in pmem and e['reply'] == {}, 'duplicate/failed physical capture')
            pmem[filename] = (args['val'],args['size'])
    def origin(file, address, size):
        need(pmem.get((root/file).as_posix()) == (address,size), 'QMP physical-origin binding '+file)
        need(len((root/file).read_bytes()) == size and address >= 4096 and address+size <= row['ram_mib']*1024*1024, 'physical-origin RAM extent')
    expected_symbols = {'initial':'f4_fixture_entry','pre':'f4_prepublication','publish':'f4_publication_authority','ready':'f4_arena_terminal','positive':'f4_positive','fault':'f4_fault_'+row['scenario'],'normalized':'f2_normalized','occupied':'f4_occupied_checkpoint','capacity':'f4_capacity_checkpoint','refused':'f4_arena_terminal','terminal':None}
    case = row['scenario']
    labels = ['initial','occupied' if case == 'occupied_refusal' else 'capacity','refused','terminal'] if case.endswith('_refusal') else ['initial','pre','publish','ready']+(['positive'] if case == 'code_write' else [])+(['fault','normalized'] if case in FAULTS else [])+['terminal']
    need({p.name.removesuffix('_capture.json') for p in root.glob('*_capture.json')} == set(labels), 'exact capture checkpoint set')
    requests = []
    for label in labels:
        meta = strict_json(root/(label+'_capture.json'))
        need(meta['symbol'] == expected_symbols[label], 'checkpoint identity substitution')
        packet = (root/(label+'_register_packet.txt')).read_text()
        need(sum(e['command'] == 'g' and e['reply'] == packet for e in glog) >= 2, 'stopped register read/readback log')
        hw = (root/(label+'_hardware.txt')).read_bytes().decode('ascii')
        need(any(e['command'] == 'human-monitor-command' and e['reply'] == hw for e in qlog), 'raw hardware log binding')
        origin(label+'_directory.bin',meta['directory']['address'],4096)
        origin(label+'_directory_repeat.bin',meta['directory']['address'],4096)
        for t in meta['tables']:
            need(t['file'] == f'{label}_table_{t["index"]:03d}.bin' and t['repeat'] == f'{label}_table_{t["index"]:03d}_repeat.bin', 'table filename identity')
            origin(t['file'],t['address'],4096)
            origin(t['repeat'],t['address'],4096)
        for n in ('owner','allocator','state'):
            for suffix in ('.bin','_repeat.bin'):
                origin(label+'_'+n+suffix,meta[n]['address'],meta[n]['size'])
        for n in ('arena_table','payload','stack'):
            if n+'_address' in meta:
                for suffix in ('.bin','_repeat.bin'):
                    origin(label+'_'+n+suffix,meta[n+'_address'],4096)
        fields = hardware(hw.encode('ascii'))
        if fields['TR'] == 24 and fields['GDT'][1] == 39:
            base = fields['GDT'][0]
            for n,address,size in (('gdt',base,40),('normal_tss',base+40,104),('emergency_tss',base+144,104),('idt8',fields['IDT'][0]+64,8)):
                origin(label+'_'+n+'.bin',address,size)
        if meta['symbol']:
            address = symbols[meta['symbol']]['address']
            requests.append(f'Z1,{address:x},1')
    need([e['command'] for e in glog if e['command'].startswith('Z')] == requests, 'actual ordered execute-breakpoint schedule')
    need(all(e['reply'] == 'OK' for e in glog if e['command'].startswith(('Z','z'))), 'breakpoint acknowledgement')
    continues = [e for e in glog if e['command'] == 'c']
    need(len(continues) == len(requests) and all(e['reply'].startswith(('T05','S05')) for e in continues), 'actual stopped continue replies')
    need(all(e['command'] in ('?','g','c') or e['command'].startswith(('m','Z1,','z1,','G')) for e in glog), 'unexpected GDB command')
    return True


def validate_guest(root, row, layout, symbols):
    need(row['overall'] == 'PASS' and row['capture_complete'] is True and row['owned_qemu_exited'] is True and type(row['qemu_exit']) is int, 'failed/incomplete guest/cleanup')
    need(row['cleanup_errors'] == [] and row['hardware_cpl3'] is False, 'cleanup/CPL3')
    need(row['checks'] and all(c['pass'] is True for c in row['checks']), 'empty/failed checks')
    verify_pins(root, row['frozen_bytes'], ('guest_report.json',))
    transport_assertions(root, row, symbols)
    case = row['scenario']
    initial = snapshot_assertions(root, 'initial', row, layout, symbols, 0)
    need(initial['state'] == 0 and initial['directory'][256] == initial['directory'][257] == 0, 'fresh initial state')
    cpuid = struct.unpack('<20I', (root/'cpuid.bin').read_bytes())
    need(cpuid[0] >= 1 and (cpuid[0] >= 7 or cpuid[8:12] == (0,)*4) and (cpuid[12] >= 0x80000001 or cpuid[16:20] == (0,)*4), 'CPUID gating')
    logs = [json.loads(line) for line in (root/'gdb.jsonl').read_text().splitlines()]
    writes = [l for l in logs if l['command'].startswith(('G','P','M','X'))]
    expected_redirects = 1 if case in FAULTS else 0
    need(len(writes) == expected_redirects and len(row['debugger_mutations']) == expected_redirects, 'unexpected debugger writes')
    if writes:
        need(writes[0]['command'].startswith('G') and writes[0]['reply'] == 'OK', 'only EIP fixture selection allowed')
        before = (root/'ready_register_packet.txt').read_text().strip()
        data = bytearray.fromhex(before)
        struct.pack_into('<I', data, 32, symbols['f4_select_'+case]['address'])
        need(writes[0]['command'] == 'G'+data.hex(), 'non-EIP debugger mutation')
        need(row['debugger_mutations'] == [{'registers': {'eip': symbols['f4_select_'+case]['address']}}], 'redirect identity')
    if case in ('occupied_refusal','capacity_refusal'):
        count = 0 if case == 'occupied_refusal' else 10
        before_label = 'occupied' if count == 0 else 'capacity'
        pre = snapshot_assertions(root, before_label, row, layout, symbols, count)
        terminal = snapshot_assertions(root, 'terminal', row, layout, symbols, count)
        preserve(pre, terminal, occupied=count == 0)
        need(pre['directory'][256] == terminal['directory'][256], 'refusal changes exact target PDE')
        # Physical images remain available byte-for-byte. Only CPU A/D updates
        # in unrelated supervisor translations may differ across execution.
        need(all(a & ~0x20 == b & ~0x20 for a,b in zip(pre['directory'],terminal['directory'])), 'refusal changes directory beyond CPU A')
        need(all(all(a & ~0x60 == b & ~0x60 for a,b in zip(table,terminal['tables'][i])) for i,table in pre['tables'].items()), 'refusal changes tables beyond CPU AD')
        need(pre['stats'] == terminal['stats'], 'refusal changes capacity')
        need(pre['leases'] == terminal['leases'], 'refusal changes leases')
        need(terminal['state'] == 3 and terminal['owner']['capture'][0] == (12 if count == 0 else 13) and terminal['owner']['capture'][1] == count and terminal['owner']['capture'][15] == 3, 'exact terminal retained prefix/refusal code')
        if count == 0:
            need(pre['directory'][256] & 7 == 3 and pre['directory'][256] == pre['directory'][0] & ~4, 'controlled supervisor occupied PDE')
        else:
            need(pre['directory'][256] == 0 and pre['owner']['capture'][1] == 10, 'denial after F3 before first new allocation')
        need(b'F4 USER arena FAIL Ring0 terminal\n' in (root/'serial.txt').read_bytes(), 'exact refusal diagnostic')
    else:
        pre = snapshot_assertions(root,'pre',row,layout,symbols,12)
        publish = snapshot_assertions(root,'publish',row,layout,symbols,12)
        ready = snapshot_assertions(root,'ready',row,layout,symbols,12)
        need(pre['state'] == publish['state'] == 1 and ready['state'] == 3, 'prepare/terminal state sequence')
        need(pre['leases'] == publish['leases'] == ready['leases'], 'ownership precedes publication')
        preserve(initial,pre,allow_f3=True)
        preserve(pre,publish)
        preserve(publish,ready)
        need(pre['stats'] == publish['stats'] == ready['stats'], 'commit no allocation')
        need(initial['stats']['free_frames']-ready['stats']['free_frames'] == 12 and ready['stats']['allocated_frames']-initial['stats']['allocated_frames'] == 12 and initial['stats']['reserved_frames'] == ready['stats']['reserved_frames'], 'actual retained twelve-frame capacity delta')
        cap = ready['owner']['arena_capture']
        need(cap[0:5] == (0,12,ready['leases']['payload']['addr'],ready['leases']['user_stack']['addr'],ready['leases']['arena_table']['addr']) and cap[14:16] == (1,2), 'production ready scalar capture')
        need(cap[11]-cap[12] == 2 and cap[12] == ready['stats']['free_frames'] and cap[13] == ready['stats']['allocated_frames'], 'new F4 capacity diagnostics')
        if case == 'code_write':
            positive = snapshot_assertions(root,'positive',row,layout,symbols,12)
            need(positive['regs']['eax'] == 0x5a17c0de, 'actual CPU RW USER stack load')
            need((root/'positive_virtual.bin').read_bytes() == struct.pack('<I',0x5a17c0de), 'stopped virtual RW readback')
        if case in FAULTS:
            fault = snapshot_assertions(root,'fault',row,layout,symbols,12)
            normalized = snapshot_assertions(root,'normalized',row,layout,symbols,12)
            cr2, error, instruction = FAULTS[case]
            need((root/'fault_instruction.bin').read_bytes() == instruction, 'exact fault instruction')
            need(fault['regs']['eip'] == symbols['f4_fault_'+case]['address'], 'fault instruction EIP')
            raw = (root/'mandatory_prefix.bin').read_bytes()
            need(len(raw) == 68, 'F2 mandatory68')
            frame = dict(zip(FIELDS,struct.unpack('<17I',raw)))
            need(frame['vector'] == 14 and frame['error'] == error and frame['cs'] == 8 and frame['eip'] == fault['regs']['eip'] and frame['eflags'] == fault['regs']['eflags'] | (1<<16), 'exact CPU PF frame')
            need(normalized['hw']['CR2'] == cr2, 'fault CR2')
            need(normalized['regs']['esp']+68 == fault['regs']['esp'] and frame['pushad_esp'] == normalized['regs']['esp']+48, 'same-CPL F2 geometry')
            need(all(frame[n] == fault['regs'][n] for n in ('eax','ebx','ecx','edx','esi','edi','ebp','ds','es','fs','gs')), 'F2 saved registers')
            need(normalized['regs']['eflags'] & 0x600 == 0 and all(normalized['regs'][n] == 16 for n in ('ds','es','fs','gs')), 'F2 normalization')
            trace = (root/'qemu.log').read_text(errors='replace')
            need(re.search(r'v=0e e=0*'+format(error,'x')+r' i=0 cpl=0 IP=0008:0*'+format(fault['regs']['eip'],'x')+r'\b',trace), 'real CPU PF trace')
            need(b'F2 fatal terminal\n' in (root/'serial.txt').read_bytes(), 'F2 terminal')
        terminal = snapshot_assertions(root,'terminal',row,layout,symbols,12)
        preserve(ready,terminal)
        need(terminal['leases'] == ready['leases'] and terminal['stats'] == ready['stats'] and terminal['state'] == 3, 'terminal retention')
        need(b'F4 USER arena PASS Ring0 terminal\n' in (root/'serial.txt').read_bytes() and b'F4 USER arena FAIL' not in (root/'serial.txt').read_bytes(), 'production success')
    need('HLT=1' in (root/'terminal_hardware.txt').read_text(), 'actual terminal HLT')
    trace = (root/'qemu.log').read_text(errors='replace')
    need('Triple fault' not in trace and not re.search(r'cpl=[123]\b|v=08\b', trace), 'no CPL3/double/triple fault')
    need(b'rosti>' not in (root/'serial.txt').read_bytes(), 'no shell return')
    return True


def validate_matrix_rows(rows):
    need(type(rows) is list and Counter((r['scenario'],r['ram_mib']) for r in rows) == Counter(REQUIRED), 'exact twelve-scenario multiset')
    return True


def validate(path, expected_source=None, check_current=False):
    """Return every validated artifact/source pin; raise on any incomplete matrix."""
    root = Path(path).resolve()
    if root.is_file():
        need(root.name == 'report.json', 'aggregate filename')
        root = root.parent
    report = strict_json(root/'report.json')
    need(report['schema'] == 'rosti.f4-arena-matrix.v1' and report['overall'] == 'PASS' and report['driver_exit'] == 0 and report['full_f4_matrix'] is True and report['hardware_cpl3'] is False, 'matrix outcome')
    verify_pins(root, report['frozen_bytes'], ('report.json',))
    before, after = strict_json(root/'source_before.json'), strict_json(root/'source_after.json')
    need(before == after and report['source_freeze_stable'] is True and bool(before), 'source drift')
    if expected_source is not None:
        need(before == expected_source, 'substituted source snapshot')
    for name, digest in before.items():
        need(re.fullmatch('[0-9a-f]{64}',digest) and sha(local(root/'source',name).read_bytes()) == digest, 'retained source pin '+name)
        if check_current:
            need(sha(local(Path(__file__).resolve().parents[1],name).read_bytes()) == digest, 'current source drift '+name)
    need(sha((root/'authority/design.md').read_bytes()) == DESIGN_SHA and sha((root/'authority/design_review_02.json').read_bytes()) == REVIEW_SHA, 'approved design/review identity')
    review = strict_json(root/'authority/design_review_02.json')
    need(review['verdict'] == 'APPROVE' and review['blocker_count'] == 0 and review['design_raw_sha256'] == DESIGN_SHA, 'design approval')
    disposition = strict_json(root/'authority/operator_disposition_01.json')
    need(disposition['status'] == 'EXPLICIT_USER_AUTHORIZATION_RECEIVED' and disposition['user_response'] == 'Authorize bounded terminal retention; revise design and obtain fresh independent approval', 'operator disposition')
    need(sha((root/'authority/operator_disposition_01.json').read_bytes()) == review['raw_sha256'][DISPOSITION], 'review-pinned operator disposition')
    tools = strict_json(root/'toolchain.json')
    need(sha((root/'toolchain/qemu-system-i386.exe').read_bytes()) == tools['qemu_sha256'] and sha((root/'firmware/bios-256k.bin').read_bytes()) == tools['bios_sha256'], 'emulator/firmware pins')
    if check_current:
        need(sha(Path(tools['qemu_path']).read_bytes()) == tools['qemu_sha256'], 'current QEMU drift')
    layouts, symbol_maps = {}, {}
    originals = {name:local(root/'source',name).read_bytes() for name in before}
    need(set(report['builds']) == {'normal','occupied_refusal','capacity_refusal'}, 'build variant set')
    for variant, build in report['builds'].items():
        folder = root/'builds'/variant
        need(build['build_exit'] == 0 and build['variant'] == variant, 'build outcome')
        kernel = folder/'kernel.elf'
        need(sha(kernel.read_bytes()) == build['kernel_sha256'], 'exact ELF')
        actual_layout = extract(kernel)
        need(actual_layout == strict_json(folder/'target_layout.json'), 'DWARF layouts not from exact ELF')
        need(actual_layout['OwnerMutex']['size']+13 <= 4096, 'target owner metadata bound')
        symbols = elf_symbols(kernel)
        need(symbols['f3_context']['size'] <= 4096, 'target F3 descriptor bound')
        need(symbols == strict_json(folder/'symbols.json'), 'substituted symbol map')
        transformed = transformations(originals, variant)
        changes = {n:v for n,v in transformed.items() if v != originals[n]}
        manifest = strict_json(folder/'transforms.json')
        need(set(manifest) == set(changes), 'explicit transform membership')
        for name, raw in changes.items():
            need(local(folder/'transformed',name).read_bytes() == raw and manifest[name] == {'original_sha256': before[name], 'transformed_sha256': sha(raw)}, 'fixture stripping/equality '+name)
        layouts[variant], symbol_maps[variant] = actual_layout, symbols
    rows = report['guests']
    validate_matrix_rows(rows)
    for row in rows:
        name = row['scenario']+'_'+str(row['ram_mib'])
        need(row['report'] == name+'/guest_report.json', 'invocation-owned immediate child')
        child = strict_json(root/row['report'])
        need({k: child[k] for k in ('scenario','ram_mib','overall','variant','kernel_sha256')} == {k: row[k] for k in ('scenario','ram_mib','overall','variant','kernel_sha256')}, 'aggregate/child linkage')
        variant = row['scenario'] if row['scenario'].endswith('_refusal') else 'normal'
        need(row['variant'] == variant and row['kernel_sha256'] == report['builds'][variant]['kernel_sha256'], 'scenario fixture identity')
        cmd = child['command']
        need(cmd[0] == tools['qemu_path'], 'QEMU executable identity')
        for flag, val in (('-bios',str(root/'firmware/bios-256k.bin')),('-machine','pc'),('-display','none'),('-nic','none'),('-monitor','none'),('-d','int,guest_errors'),('-D',str(root/name/'qemu.log')),('-kernel',str(root/'builds'/variant/'kernel.elf')),('-cpu','qemu32'),('-m',str(row['ram_mib'])),('-smp','1'),('-serial','file:'+str(root/name/'serial.txt'))):
            need(cmd.count(flag) == 1 and cmd[cmd.index(flag)+1] == val, 'exact QEMU operand '+flag)
        need('-cdrom' not in cmd and '-S' in cmd and '-no-reboot' in cmd, 'ELF boot profile')
        validate_guest(root/name,child,layouts[variant],symbol_maps[variant])
    need(report['checks'] and all(c['pass'] is True for c in report['checks']), 'aggregate checks')
    return {str(root/name): digest for name,digest in report['frozen_bytes'].items()} | {str(root/'report.json'): sha((root/'report.json').read_bytes())}


def validate_aggregate(path, expected_source):
    """Canonical acceptance API: exact source snapshot and twelve hardware cases."""
    need(type(expected_source) is dict and bool(expected_source), 'expected canonical source snapshot required')
    pins = validate(path, expected_source=expected_source)
    return {'overall': 'PASS', 'scenario_count': len(REQUIRED), 'pins': pins}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--check-current-source', action='store_true')
    args = parser.parse_args()
    try:
        pins = validate(args.report, check_current=args.check_current_source)
        print(json.dumps({'overall':'PASS','scenarios':len(REQUIRED),'validated_pins':len(pins),'hardware_cpl3':False}))
        return 0
    except Exception as exc:
        print(json.dumps({'overall':'FAIL','error':repr(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
