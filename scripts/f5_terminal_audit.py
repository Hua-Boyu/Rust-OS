"""Read-only linked F5 audit. Component evidence only, never acceptance.

A missing proof is BLOCKED, not a guessed PASS. No build, QEMU or input write.
The public normalize() retains audit_emitted_01's (mnemonic, operand) API.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')

from b13_entry_inject import elf_symbols
from boot_metadata_test import parse_elf
from f3_full_guest import discover_objdump
from f5_entry_derivation import map_identifier, IDENTIFIERS

ROOT = Path(__file__).resolve().parents[1]
# Independent historical pre-macro ELF; do not learn a new pin from --before.
BEFORE_SHA256 = '770f18590e186465fcb301f8d09c044d1055707027f0fa9ba596d0e2a1f33fcc'
ERROR_VECTORS = frozenset((8, 10, 11, 12, 13, 14, 17))
UNSUPPORTED = frozenset((21, 29, 30))
DIRECT = re.compile(r'0x([0-9a-fA-F]+)(?: <([^>]+)>)?')
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
IRETS = frozenset(('iret', 'iretd', 'iretl'))
# A closed decoder vocabulary prevents unknown control-transfer spellings being
# accidentally treated as ordinary fallthrough instructions.
ORDINARY = frozenset(('cli', 'cld', 'mov', 'movzx', 'lea', 'xor', 'and', 'or',
    'add', 'sub', 'cmp', 'test', 'inc', 'dec', 'shl', 'xchg', 'push', 'pushal',
    'pushad', 'pushfd', 'pushf', 'pop', 'in', 'out', 'sgdt', 'sgdtd', 'str', 'nop',
    'rep', 'movsd', 'hlt'))
CONDITIONAL = frozenset(('ja','jae','jb','jbe','jc','je','jg','jge','jl','jle',
    'jna','jnae','jnb','jnbe','jnc','jne','jng','jnge','jnl','jnle','jno',
    'jnp','jns','jnz','jo','jp','jpe','jpo','js','jz'))


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def normalize(instruction, f5=False):
    """Normalize *only* direct branch relocations and approved identifiers.

    Offset suffixes remain binding. No open-ended f5_ prefix rewrite, no
    f5_fatal alias, no disappearance of unknown identifiers in nonbranch text.
    """
    mnemonic, operand = instruction
    if f5:
        operand = IDENTIFIER.sub(lambda m: map_identifier(m[0]), operand)
    if mnemonic.startswith(('j', 'call')):
        match = DIRECT.fullmatch(operand)
        need(match and match[2], 'non-direct/unlabelled comparison edge: ' + operand)
        operand = match[2]
    return mnemonic, operand


class Image:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.raw = self.path.read_bytes()
        self.layout = parse_elf(self.raw)
        self.symbols = elf_symbols(self.path)

    def read(self, address, size, executable=False):
        need(size >= 0, 'negative ELF read')
        matches = [p for p in self.layout['segments'] if p[0] == 1
                   and p[2] <= address and address + size <= p[2] + p[4]
                   and (not executable or p[6] & 1)]
        need(len(matches) == 1, f'unmapped/ambiguous/non-file-backed ELF span {address:#x}+{size}')
        p = matches[0]
        offset = p[1] + address - p[2]
        raw = self.raw[offset:offset + size]
        need(len(raw) == size, 'short ELF bytes')
        return raw


def disassemble(image, tool):
    command = [str(tool), '-d', '--x86-asm-syntax=intel', str(image.path)]
    completed = subprocess.run(command, capture_output=True, timeout=120)
    need(completed.returncode == 0, 'objdump failed: ' + completed.stderr.decode(errors='replace'))
    text = completed.stdout.decode('utf-8', errors='strict')
    rows = {}
    pattern = re.compile(r'^\s*([0-9a-fA-F]+):[ \t]+((?:[0-9a-fA-F]{2}[ \t]+)+)[ \t]*([a-z][a-z0-9]*)[ \t]*(.*)$')
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if not match:
            continue
        pc = int(match[1], 16)
        raw = bytes.fromhex(match[2])
        need(pc not in rows, f'duplicate disassembly address {pc:#x}')
        need(image.read(pc, len(raw), True) == raw, 'objdump/raw ELF disagreement')
        rows[pc] = {'pc': pc, 'bytes': raw.hex(), 'size': len(raw),
                    'mnemonic': match[3], 'operand': match[4].strip()}
    need(rows, 'no decoded instructions')
    return completed.stdout, rows, command


def body(rows, symbol):
    start, end = symbol['address'], symbol['address'] + symbol['size']
    need(end > start, 'zero-size function body')
    found, pc = [], start
    while pc < end:
        need(pc in rows, f'undecoded function byte {pc:#x}')
        row = rows[pc]
        need(pc + row['size'] <= end, 'instruction crosses function end')
        found.append(row)
        pc += row['size']
    return found


def terminal_alias(image, rows, name):
    pc = image.symbols[name]['address']
    first = rows.get(pc)
    need(first and (first['mnemonic'], first['operand'], first['bytes']) == ('cli', '', 'fa'), name + ': missing exact CLI')
    halt = rows.get(pc + 1)
    need(halt and (halt['mnemonic'], halt['operand'], halt['bytes']) == ('hlt', '', 'f4'), name + ': missing exact HLT')
    jump = rows.get(pc + 2)
    need(jump and jump['mnemonic'] == 'jmp', name + ': missing self loop')
    target = DIRECT.fullmatch(jump['operand'])
    need(target and int(target[1], 16) == pc + 1, name + ': non-HLT branch target')
    raw = image.read(pc, 2 + jump['size'], True)
    need(raw == b'\xfa\xf4\xeb\xfd', name + ': not exact CLI/HLT/short-self-loop bytes')
    return {'symbol': name, 'address': pc, 'raw_hex': raw.hex(), 'sha256': sha(raw)}


def closure(rows, roots, allowed, calls, iret_pc=None):
    """Every instruction and direct/conditional/fallthrough/call continuation.

    Even a known divergent call's continuation is inspected: defensive tails
    must not smuggle a return or forbidden edge. Symbol names never bound CFG.
    """
    pending, seen, edges, violations, exits = list(roots), set(), [], [], []
    while pending:
        pc = pending.pop()
        if pc in seen:
            continue
        seen.add(pc)
        if pc not in rows or pc not in allowed:
            violations.append({'pc': pc, 'kind': 'unresolved_or_foreign_instruction'})
            continue
        row = rows[pc]
        m, op = row['mnemonic'], row['operand']
        next_pc = pc + row['size']
        successors = []
        if m in IRETS:
            if pc != iret_pc:
                violations.append({'pc': pc, 'kind': 'forbidden_iret'})
            else:
                exits.append(pc)
            continue
        if m in CONDITIONAL or m in ('jmp', 'call'):
            match = DIRECT.fullmatch(op)
            if not match:
                violations.append({'pc': pc, 'kind': 'indirect_or_unresolved_edge', 'operand': op})
                continue
            target = int(match[1], 16)
            successors.append((target, 'call' if m == 'call' else 'branch'))
            if m == 'call' and target not in calls:
                violations.append({'pc': pc, 'kind': 'forbidden_call', 'target': target, 'operand': op})
            if m != 'jmp':
                successors.append((next_pc, 'call_continuation' if m == 'call' else 'fallthrough'))
        elif m not in ORDINARY:
            violations.append({'pc': pc, 'kind': 'forbidden_or_unknown_opcode', 'mnemonic': m, 'operand': op})
            continue
        elif m == 'rep' and row['bytes'] != 'f3a5':
            violations.append({'pc': pc, 'kind': 'unreviewed_repeat_prefix', 'operand': op})
            continue
        elif m == 'hlt':
            # Interrupt/NMI may wake HLT; the next JMP must remain in closure.
            successors.append((next_pc, 'halt_wakeup_fallthrough'))
        else:
            successors.append((next_pc, 'fallthrough'))
        for target, kind in successors:
            edges.append({'from': pc, 'to': target, 'kind': kind})
            pending.append(target)
    return {'roots': list(roots), 'instructions': [rows[p] for p in sorted(seen) if p in rows],
            'edges': edges, 'violations': violations, 'iret_exits': exits,
            'complete': not violations}


def compare_entries(image, rows, before, oldrows):
    records = []
    names = ['f2_exception_common', *[f'f2_exc_{v}' for v in range(32)]]
    for name in names:
        current = body(rows, image.symbols[name])
        old = body(oldrows, before.symbols[name])
        need([normalize((x['mnemonic'], x['operand'])) for x in current] ==
             [normalize((x['mnemonic'], x['operand'])) for x in old], 'inherited F2 emitted drift: ' + name)
        # Only branch displacement bytes may vary under relocation.
        need([x['bytes'] for x in current if not x['mnemonic'].startswith(('j','call'))] ==
             [x['bytes'] for x in old if not x['mnemonic'].startswith(('j','call'))], 'F2 nonrelocation raw drift: ' + name)
        f5name = name.replace('f2_', 'f5_', 1)
        expanded = body(rows, image.symbols[f5name])
        need([normalize((x['mnemonic'], x['operand'])) for x in current] ==
             [normalize((x['mnemonic'], x['operand']), True) for x in expanded], 'F2/F5 complete emitted expansion mismatch: ' + f5name)
        need([x['bytes'] for x in current if not x['mnemonic'].startswith(('j','call'))] ==
             [x['bytes'] for x in expanded if not x['mnemonic'].startswith(('j','call'))], 'F2/F5 raw nonrelocation mismatch: ' + f5name)
        record = {'f2': name, 'f5': f5name, 'instruction_count': len(current)}
        for label, obj, seq in [('before', before, old), ('f2', image, current), ('f5', image, expanded)]:
            raw = b''.join(bytes.fromhex(x['bytes']) for x in seq)
            record[label] = {'address': seq[0]['pc'], 'raw_hex': raw.hex(), 'sha256': sha(raw)}
        records.append(record)
    for prefix, obj in [('f2', before), ('f2', image), ('f5', image)]:
        address = obj.symbols[prefix + '_exception_entries']['address']
        table = struct.unpack('<32I', obj.read(address, 128))
        need(list(table) == [obj.symbols[f'{prefix}_exc_{v}']['address'] for v in range(32)], 'ordered emitted vector table drift')
    return records


def stack_paths(rows, image, graph):
    """Concrete ESP arithmetic over every branch, including align loss.

    Only the audited entry/bridge vocabulary is supported. No inferred frame
    sizes, prologue guesses, symbol-size stack estimates or debug constants.
    First entries use exact ESP0; a nested same-ring NMI uses each possible
    live first-path ESP, including a transient PUSHFD value.
    """
    terminals = {image.symbols[n]['address'] + 1 for n in ('f5_terminal', 'f5_entry_terminal')}
    bridge = image.symbols['f5_bridge']['address']
    unsupported = image.symbols['f5_unsupported']['address']
    bridge_body = body(rows, image.symbols['f5_bridge'])
    need(not any(x['mnemonic'].startswith(('call', 'ret')) for x in bridge_body),
         'naked bridge contains call/return')
    need([(x['mnemonic'], x['operand']) for x in bridge_body[:3]] ==
         [('mov','edi, esp'), ('pushfd',''), ('pop','ebx')], 'naked bridge stack capture drift')
    # Inspect all reachable instructions, including failure/latch arms, even if
    # an early unit path would not encounter them.
    adjacency = {}
    for e in graph['edges']:
        if e['kind'] != 'call_continuation':
            adjacency.setdefault(e['from'], []).append(e['to'])

    def trace(root, initial, origin):
        pending = [(root, initial, ())]
        seen, states, witness = set(), set(), None
        maximum = origin - initial
        while pending:
            pc, esp, trail = pending.pop()
            if (pc, esp) in seen:
                continue
            seen.add((pc, esp))
            need(len(seen) < 100000, 'stack traversal bound exceeded (possible unbounded stack loop)')
            need(pc in rows, 'stack path missing instruction')
            states.add(esp)
            if pc in terminals:
                continue
            x = rows[pc]
            m, op = x['mnemonic'], x['operand']
            need(not (m == 'xchg' and re.search(r'\b(?:esp|sp)\b', op)),
                 'unmodelled XCHG ESP mutation')
            old = esp
            if m in ('pushal','pushad'):
                esp -= 32
            elif m in ('push','pushfd','pushf','call'):
                need(not op.startswith(('word ', 'ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp')),
                     '16-bit stack operand unsupported')
                esp -= 4
            elif m == 'pop':
                need(op not in ('esp','sp'), 'dynamic pop ESP')
                esp += 4
            elif re.match(r'esp\s*,', op):
                parts = op.split(',', 1)
                try:
                    value = int(parts[1].strip(), 0)
                except ValueError as exc:
                    raise RuntimeError('dynamic ESP mutation: ' + op) from exc
                if m == 'and':
                    need(value == -16, 'unexpected stack alignment mask')
                    esp &= -16
                elif m == 'sub':
                    need(value >= 0, 'negative stack reserve')
                    esp -= value
                elif m == 'add':
                    esp += value
                else:
                    raise RuntimeError('unmodelled ESP write: ' + m + ' ' + op)
            elif m in ('enter','leave','popal','popad') or re.search(r'\b(?:esp|sp)\b', op.split(',')[0]) and m not in ('cmp','test'):
                # ESP as a *source*, e.g. mov edi,esp, is permitted.
                need('[' in op.split(',')[0], 'unmodelled stack effect')
            step = {'pc': pc, 'mnemonic': m, 'operand': op, 'esp_before': old,
                    'esp_after': esp, 'increment_bytes': old - esp}
            trail = trail + (step,) if old != esp else trail
            if origin - esp > maximum:
                maximum, witness = origin - esp, list(trail)
            states.add(esp)
            # Nested path is conservatively allowed all bridge arms, not just
            # the latch-taken arm. It has identical bounded stack effect.
            for target in adjacency.get(pc, []):
                need(target != root or esp == initial, 'stack-growing entry cycle')
                pending.append((target, esp, trail))
        return {'max_bytes': maximum, 'witness': witness or [], 'live_esps': sorted(states)}

    bridge_scratch = trace(bridge, 0x07c05000, 0x07c05000)
    need(bridge_scratch['max_bytes'] <= 64, 'naked bridge scratch exceeds 64-byte ceiling')
    paths = []
    for vector in (6, 13, 14):
        hardware = 20 + (4 if vector in ERROR_VECTORS else 0)
        row = trace(image.symbols[f'f5_exc_{vector}']['address'], 0x07c05000-hardware, 0x07c05000)
        row.update(vector=vector, hardware_bytes=hardware, origin_esp=0x07c05000)
        paths.append(row)
    first = max(p['max_bytes'] for p in paths)
    nested = []
    for esp in sorted({sp for p in paths for sp in p['live_esps']}):
        # Architectural same-CPL NMI frame is EFLAGS,CS,EIP = 12, no error.
        row = trace(image.symbols['f5_exc_2']['address'], esp - 12, esp)
        nested.append({'interrupted_esp': esp, 'additional_bytes': row['max_bytes'],
                       'combined_bytes': 0x07c05000 - esp + row['max_bytes'],
                       'witness': row['witness']})
    bound = max(p['combined_bytes'] for p in nested)
    # Preserve the approved independent allowances: 104 first + 115 ADDITIONAL
    # nested bytes. The tighter concrete combined paths corroborate, not replace,
    # the reviewed conservative ceiling. Same-CPL hardware NMI frame is 12 bytes;
    # trace includes transient PUSHFD states before POP.
    need(first <= 104, 'first entry exceeds reviewed 104-byte allowance')
    need(max(p['additional_bytes'] for p in nested) <= 115,
         'nested NMI exceeds reviewed ADDITIONAL 115-byte allowance')
    conservative = 104 + 115
    need(bound <= conservative <= 512, 'conditional transition stack budget exceeded')
    return {'bridge_scratch_path': bridge_scratch,
            'first_paths': paths, 'one_nested_nmi_paths': nested,
            'max_first_entry_bytes': first,
            'max_additional_nested_bytes': max(p['additional_bytes'] for p in nested),
            'concrete_combined_path_bytes': bound,
            'reviewed_first_allowance_bytes': 104,
            'reviewed_additional_nested_allowance_bytes': 115,
            'conditional_stack_ceiling_bytes': bound, 'budget_bytes': 512,
            'headroom_in_16384_byte_transition_stack': 16384-conservative,
            'scope': 'Static path bound only: first CPL3 vector6/13/14 and one same-ring NMI; excludes pre-latch storms, arbitrary recursion, DF and runtime high-water.'}


def installer_inventory(image, rows):
    """Preserve the full emitted installer/caller scope, without pretending a
    return-value-dependent slice is established by looking for one call.
    """
    names = [n for n in image.symbols if
             ('gdt_tss' in n and ('install_policy' in n or '10install_f5' in n))
             or ('f5_gdt' in n and ('7install' in n or '6verify' in n))
             or ('f5_runtime' in n and '13install_gates' in n)
             or n == 'f5_run_cpl3']
    need(any('install_policyKb1_' in n for n in names), 'missing F5 installer policy specialization')
    result = []
    for name in sorted(names):
        seq = body(rows, image.symbols[name])
        raw = image.read(seq[0]['pc'], image.symbols[name]['size'], True)
        result.append({'symbol': name, 'address': seq[0]['pc'], 'sha256': sha(raw),
                       'raw_hex': raw.hex(), 'instructions': seq})
    return result



def unique_symbol(image, fragment):
    found = [n for n in image.symbols if fragment in n]
    need(len(found) == 1, 'nonunique mandatory symbol: ' + fragment)
    return found[0]


def pic_base(image, seq):
    """Resolve the actual x86 call-next/pop/add, not a guessed link address."""
    found = []
    for j, x in enumerate(seq[:-2]):
        if x['mnemonic'] != 'call':
            continue
        m = DIRECT.fullmatch(x['operand'])
        if not m or int(m[1], 16) != x['pc'] + x['size']:
            continue
        pop, add = seq[j+1:j+3]
        if pop['mnemonic'] != 'pop' or add['mnemonic'] != 'add':
            continue
        reg = pop['operand']
        a = re.fullmatch(re.escape(reg) + r', (0x[0-9a-f]+)', add['operand'])
        need(a is not None, 'unresolved PIC base arithmetic')
        base = (pop['pc'] + int(a[1], 16)) & 0xffffffff
        need(base == image.symbols['_GLOBAL_OFFSET_TABLE_']['address'], 'PIC/GOT disagreement')
        found.append((reg, base, add['pc']))
    need(len(found) == 1, 'missing/ambiguous call-next PIC base')
    return found[0]


def initialized_symbol(image, name):
    s = image.symbols[name]
    addr, size = s['address'], s['size']
    need(size > 0, 'empty referenced data symbol')
    matches = [p for p in image.layout['segments'] if p[0] == 1
               and p[2] <= addr and addr + size <= p[2] + p[5]]
    need(len(matches) == 1, 'referenced data outside unique PT_LOAD memory')
    p = matches[0]
    end = min(addr + size, p[2] + p[4])
    raw = image.read(addr, end-addr) if end > addr else b''
    return raw + bytes(size-len(raw))


def resolved_data(image, seq, index, base):
    """Resolve a GOT-relative data reference to its initialized bytes.

    Extent is the unique containing data symbol (zero-filled .bss allowed) or,
    for anonymous .rodata, the NUL-terminated record. No symbol-name guessing.
    """
    x = seq[index]
    m = re.fullmatch(r'(e[a-z]{2}), \[ebx ([+-]) (0x[0-9a-f]+)\]', x['operand'])
    need(x['mnemonic'] == 'lea' and m, 'unsupported inherited data relocation')
    address = (base + (1 if m[2] == '+' else -1)*int(m[3],16)) & 0xffffffff
    owners = [(n, s) for n, s in image.symbols.items() if s['size'] and
              s['address'] <= address < s['address'] + s['size']]
    if owners:
        need(len(owners) == 1, f'ambiguous data symbol at {address:#x}')
        name, s = owners[0]
        need(address == s['address'], f'interior data symbol reference {address:#x} in {name}')
        raw = image.read(address, s['size']) if any(
            p[0] == 1 and p[2] <= address and address + s['size'] <= p[2] + p[4]
            for p in image.layout['segments']) else b''
        if not raw:
            # .bss: memsz-backed zeros, not file bytes.
            backing = [p for p in image.layout['segments'] if p[0] == 1
                       and p[2] <= address and address + s['size'] <= p[2] + p[5]]
            need(len(backing) == 1, f'zero data outside unique PT_LOAD memsz {address:#x}')
            raw = bytes(s['size'])
        return (m[1], 'symbol', name, address - s['address'], raw.hex()), address
    # Anonymous literal: require file-backed .rodata and a NUL-terminated extent.
    span = [p for p in image.layout['segments'] if p[0] == 1
            and p[2] <= address and address < p[2] + p[4]]
    need(len(span) == 1, f'anonymous data outside unique file-backed PT_LOAD {address:#x}')
    p = span[0]
    # Rust string constants are not NUL-terminated; the pool packs records.
    # Bind a fixed 64-byte window at the resolved address (covers every
    # consumed literal; identity is the exact bytes, not a guessed extent).
    avail = p[2] + p[4] - address
    need(avail >= 64, f'anonymous data window under 64 bytes at {address:#x}')
    window = image.read(address, 64)
    return (m[1], 'literal', 64, window.hex()), address


def branch_identity(image, row, function):
    m = DIRECT.fullmatch(row['operand'])
    need(m is not None, 'non-direct inherited branch')
    target = int(m[1],16)
    start = image.symbols[function]['address']
    size = image.symbols[function]['size']
    if start <= target < start+size:
        return ('local',target-start)
    exact = [n for n,s in image.symbols.items() if s['address'] == target and s['size']]
    need(len(exact) == 1, f'ambiguous inherited destination {target:#x}')
    need(m[2] == exact[0], 'objdump target label/symbol disagreement')
    return ('symbol',exact[0])


def compare_fatal_functions(image, rows, before, oldrows):
    result=[]
    for name in ('f2_fatal','f2_unsupported'):
        seq, old = body(rows,image.symbols[name]),body(oldrows,before.symbols[name])
        need(len(seq) == len(old), 'F2 fatal instruction count drift: '+name)
        reg, base, setup = pic_base(image,seq)
        oldreg, oldbase, oldsetup = pic_base(before,old)
        need(reg == oldreg == 'ebx', 'unreviewed inherited PIC register')
        relocations=[]
        for j,(x,y) in enumerate(zip(seq,old)):
            need(x['mnemonic'] == y['mnemonic'] and x['size'] == y['size'],
                 f'{name}: opcode/width drift at {x["pc"]:#x}')
            raw, prior = bytes.fromhex(x['bytes']),bytes.fromhex(y['bytes'])
            # All other bytes, including register/modrm/opcode, stay binding.
            if x['mnemonic'] in CONDITIONAL or x['mnemonic'] in ('call','jmp'):
                need(branch_identity(image,x,name) == branch_identity(before,y,name),
                     f'{name}: resolved branch drift at {x["pc"]:#x}')
                prefix = 2 if raw[:1] == b'\x0f' else 1
                need(raw[:prefix] == prior[:prefix], 'inherited branch encoding drift')
            elif x['pc'] == setup:
                need(y['pc'] == oldsetup and raw[:2] == prior[:2] == b'\x81\xc3',
                     'inherited PIC instruction drift')
            elif x['mnemonic'] == 'lea' and '[ebx ' in x['operand']:
                current, addr = resolved_data(image,seq,j,base)
                previous, oldaddr = resolved_data(before,old,j,oldbase)
                need(current == previous, f'{name}: resolved data drift at {x["pc"]:#x}: {current[:3]} != {previous[:3]}')
                need(raw[:2] == prior[:2] and len(raw) == 6, 'LEA opcode/modrm drift')
                relocations.append({'pc':x['pc'],'before_pc':y['pc'],
                    'address':addr,'before_address':oldaddr,'identity':current,
                    'data_sha256':sha(bytes.fromhex(current[-1]))})
            else:
                need(raw == prior and x['operand'] == y['operand'],
                     f'{name}: nonrelocation drift at {x["pc"]:#x}: {x["mnemonic"]} {x["operand"]}')
        result.append({'symbol':name,'instruction_count':len(seq),
            'current_sha256':sha(image.read(seq[0]['pc'],image.symbols[name]['size'],True)),
            'before_sha256':sha(before.read(old[0]['pc'],before.symbols[name]['size'],True)),
            'got_base':base,'before_got_base':oldbase,'resolved_data':relocations})
    return result


def local_cfg(image, rows, name):
    """Complete local CFG, explicitly separating preparation callees from transport.

    Calls are edges plus continuations, NOT assertions about callee closures.
    The only far branch accepted is same-function ljmp selector8; bytes bound.
    """
    seq=body(rows,image.symbols[name]); pcs={x['pc'] for x in seq}
    pending=[seq[0]['pc']]; seen=set(); edges=[]; calls=[]; returns=[]
    while pending:
        pc=pending.pop()
        if pc in seen: continue
        need(pc in pcs, f'{name}: foreign local CFG edge {pc:#x}')
        seen.add(pc); x=rows[pc]; m=x['mnemonic']; op=x['operand']; nxt=pc+x['size']
        successors=[]
        if m == 'ret':
            returns.append(pc)
        elif m == 'ljmp':
            far=re.fullmatch(r'0x8, (0x[0-9a-f]+)',op)
            need(far and bytes.fromhex(x['bytes']) == b'\xea'+struct.pack('<I',int(far[1],16))+b'\x08\x00', 'unreviewed far transfer')
            successors=[(int(far[1],16),'same_ring_far_branch')]
        elif m in CONDITIONAL or m in ('jmp','call'):
            match=DIRECT.fullmatch(op);need(match, 'indirect preparation edge at '+hex(pc))
            target=int(match[1],16)
            if m == 'call' and target != nxt:
                calls.append({'pc':pc,'target':target,'operand':op,'classification':'preparation_not_fatal'})
                successors=[(nxt,'call_continuation')]
            else:
                successors=[(target,'branch')]
                if m in CONDITIONAL: successors.append((nxt,'fallthrough'))
        else:
            need(m in ORDINARY or m in ('lgdtd','ltr'), 'unknown installer opcode '+m+' at '+hex(pc))
            successors=[(nxt,'fallthrough')]
        for target,kind in successors:
            edges.append({'from':pc,'to':target,'kind':kind});pending.append(target)
    need(seen == pcs, 'installer has unreachable/unclassified emitted bytes')
    return {'symbol':name,'instructions':seq,'edges':edges,'preparation_calls':calls,'returns':returns}


def false_transport(rows, start, terminal, allow_return=False):
    """Concrete scalar false-return transport; no opaque helper exemptions."""
    pc=start; trace=[]; value=0; zero=None; slots={}; seen=set()
    for _ in range(1000):
        need(pc not in seen, 'failure transport cycle');seen.add(pc)
        if pc == terminal and terminal is not None:
            return {'instructions':trace,'destination':pc,'returned_false':False}
        need(pc in rows, 'undecoded failure transport')
        x=rows[pc];trace.append(x);m,op=x['mnemonic'],x['operand'];nxt=pc+x['size']
        if m == 'ret':
            need(allow_return and value == 0, 'failure transport returns/true escape')
            return {'instructions':trace,'destination':pc,'returned_false':True}
        if m == 'call':
            match=DIRECT.fullmatch(op)
            need(match and int(match[1],16) == terminal, f'forbidden failure call at {pc:#x}: {op}')
            pc=terminal;continue
        if m == 'jmp':
            match=DIRECT.fullmatch(op);need(match,'indirect failure branch');pc=int(match[1],16);continue
        if m in CONDITIONAL:
            need(m in ('je','jz','jne','jnz') and zero is not None,'unsupported failure predicate')
            match=DIRECT.fullmatch(op);need(match,'indirect conditional')
            take=zero if m in ('je','jz') else not zero
            pc=int(match[1],16) if take else nxt;continue
        if m in ('test','and'):
            need(op == 'al, 0x1','unreviewed failure test/mask')
            zero=(value&1)==0
            if m == 'and':value &= 1
        elif m == 'mov':
            store=re.fullmatch(r'(byte ptr \[esp \+ 0x[0-9a-f]+\]), 0x0',op)
            load=re.fullmatch(r'al, (byte ptr \[esp \+ 0x[0-9a-f]+\])',op)
            if store: slots[store[1]]=0
            elif load:
                need(load[1] in slots,'unknown false return slot');value=slots[load[1]]
            else:
                need(re.fullmatch(r'ebx, dword ptr \[esp \+ 0x[0-9a-f]+\]',op), 'unreviewed failure MOV '+op)
        elif m == 'add':
            need(re.fullmatch(r'esp, 0x[0-9a-f]+',op),'unreviewed failure ADD')
        elif m == 'pop':
            need(op in ('ebx','esi','edi'),'failure POP modifies return')
        else:
            raise RuntimeError(f'forbidden/unknown failure instruction {pc:#x}: {m} {op}')
        pc=nxt
    raise RuntimeError('failure transport traversal bound')


def installer_failure_proof(image, rows, terminal_graph):
    policy=unique_symbol(image,'install_policyKb1_')
    adapter=unique_symbol(image,'gdt_tss10install_f5')
    graph=local_cfg(image,rows,policy)
    # All local false stores must return false without helpers or other effects.
    false_stores=[x for x in graph['instructions'] if x['mnemonic']=='mov' and
                  re.fullmatch(r'byte ptr \[esp \+ 0x[0-9a-f]+\], 0x0',x['operand'])]
    need(false_stores,'missing installer false producers')
    transport=[false_transport(rows,x['pc'],None,True) for x in false_stores]
    need(set(p['destination'] for p in transport)==set(graph['returns']), 'uncovered installer return')
    # Every zero/one producer uses the same return slot. The sole true producer
    # is the final success arm; all local paths and post-LGDT failure arms above
    # were enumerated, not inferred from a source short-circuit.
    slot=false_stores[0]['operand'].split(',')[0]
    stores=[x for x in graph['instructions'] if x['operand'].startswith(slot+',')]
    need(all(x['mnemonic']=='mov' and x['operand'] in (slot+', 0x0',slot+', 0x1') for x in stores), 'unknown return producer')
    need(sum(x['operand']==slot+', 0x1' for x in stores)==1,'nonunique success producer')
    ad=body(rows,image.symbols[adapter]); policy_calls=[x for x in ad if x['mnemonic']=='call' and DIRECT.fullmatch(x['operand']) and int(DIRECT.fullmatch(x['operand'])[1],16)==image.symbols[policy]['address']]
    need(len(policy_calls)==1,'wrong adapter specialization call')
    # No other non-PIC calls/tails in the complete adapter body.
    ag=local_cfg(image,rows,adapter)
    need([x['pc'] for x in ag['preparation_calls']]==[policy_calls[0]['pc']], 'adapter has foreign call')
    adapter_tail=false_transport(rows,policy_calls[0]['pc']+policy_calls[0]['size'],None,True)
    runbody=body(rows,image.symbols['f5_run_cpl3'])
    targets={image.symbols[adapter]['address'],image.symbols[unique_symbol(image,'gdt_tss6verify')]['address'],
             image.symbols[unique_symbol(image,'f5_gdt7install')]['address'],
             image.symbols[unique_symbol(image,'f5_runtime13install_gates')]['address']}
    failure_calls=[x for x in runbody if x['mnemonic']=='call' and DIRECT.fullmatch(x['operand']) and int(DIRECT.fullmatch(x['operand'])[1],16) in targets]
    need(len(failure_calls)==4 and {int(DIRECT.fullmatch(x['operand'])[1],16) for x in failure_calls}==targets,'missing/duplicate caller preparation predicate')
    end=image.symbols['f5_unsupported']['address']
    tails=[false_transport(rows,x['pc']+x['size'],end) for x in failure_calls]
    need(terminal_graph['complete'],'fatal suffix closure incomplete')
    # No f3 fail/terminal, allocation, lock, shared serial, panic or indirect call
    # is admitted after false publication. All calls in those concrete traces
    # above were constrained to f5_unsupported exactly; its closure is separate.
    return {'complete':True,'scope':'Complete local const-true installer CFG and every false-return producer, adapter tail and four caller false paths through bounded fatal suffix. Preparation callees/locks are inventoried, NOT claimed fatal or panic-free.',
            'policy_cfg':graph,'adapter_cfg':ag,'false_return_paths':transport,
            'adapter_false_return':adapter_tail,'caller_false_paths':tails,
            'terminal_suffix_roots':terminal_graph['roots'],
            'forbidden_after_false':['return_to_boot','f3_install_terminal','panic','allocator','lock','shared_serial','formatting','indirect_transfer']}


def payload_view(raw, address):
    """Minimal ET_REL executable section containing ONLY exact linked bytes.

    No assembler or proposal source is involved; sh_addr is the intended VA.
    """
    names=b'\0.text\0.shstrtab\0'; offset=52; strings=offset+len(raw)
    shoff=(strings+len(names)+3)&~3
    ident=b'\x7fELF\x01\x01\x01'+bytes(9)
    header=ident+struct.pack('<HHIIIIIHHHHHH',1,3,1,0,0,shoff,0,52,0,0,40,3,2)
    text=struct.pack('<IIIIIIIIII',1,1,6,address,offset,len(raw),0,0,1,0)
    strtab=struct.pack('<IIIIIIIIII',7,3,0,0,strings,len(names),0,0,1,0)
    return header+raw+names+bytes(shoff-strings-len(names))+bytes(40)+text+strtab


def payload_obligation(image, rows, tool, output, baseline, oldrows, artifacts):
    """Keep finite transfer/data observations even when initialization is unsafe.

    A concrete F5-only emitted panic edge stops this obligation; payload metadata
    or matching byte searches MUST NOT turn that result into PASS.
    """
    iret=body(rows,image.symbols['f5_iret'])
    expect=image.symbols['f5_expect']['address']
    expected=[('cli',''),('mov',f'eax, dword ptr [{expect:#x}]'),('cmp','eax, 0x1'),
        ('jb','FAIL'),('cmp','eax, 0x6'),('ja','FAIL'),('dec','eax'),('shl','eax, 0x6'),
        ('add','eax, 0x40000100'),('cmp',f'eax, dword ptr [{expect+24:#x}]'),('jne','FAIL'),
        ('mov','edx, eax'),('mov','ax, 0x33'),('mov','ds, ax'),('mov','es, ax'),
        ('mov','fs, ax'),('mov','gs, ax'),('push','0x33'),('push','0x40400000'),
        ('push','0x2'),('push','0x2b'),('push','edx'),('iretd','')]
    observed=[]
    for x in iret:
        op=x['operand']
        if x['mnemonic'] in CONDITIONAL:
            m=DIRECT.fullmatch(op)
            need(m and int(m[1],16)==image.symbols['f5_unsupported']['address'],'IRETD failure target drift')
            op='FAIL'
        observed.append((x['mnemonic'],op))
    need(observed==expected,'finite IRETD instruction/dataflow drift')
    initname=unique_symbol(image,'user_arena16initialize_pages')
    init=body(rows,image.symbols[initname])
    # Locate the REAL copy operation and retain the complete initializer, not a
    # proposal-only object or an accidental raw-payload occurrence elsewhere.
    copies=[x for x in init if x['mnemonic']=='call' and '<memcpy>' in x['operand']]
    need(len(copies)==1,'nonunique emitted payload copy')
    copy_index=init.index(copies[0])
    need([(x['mnemonic'],x['operand']) for x in init[copy_index-3:copy_index]]==
         [('mov','dword ptr [esp], ecx'),('mov','dword ptr [esp + 0x4], eax'),('mov','dword ptr [esp + 0x8], 0x18')], 'payload copy ABI drift')
    panic=[x for x in init if x['mnemonic']=='call' and 'panic_const_mul_overflow' in x['operand']]
    need(len(panic)==1,'unable to identify copy-index overflow check')
    j=init.index(panic[0]); target=init[j-3]['pc']
    branches=[x for x in init if x['mnemonic']=='jo' and DIRECT.fullmatch(x['operand']) and int(DIRECT.fullmatch(x['operand'])[1],16)==target]
    need(len(branches)==1,'overflow panic not linked to payload index branch')
    branch=branches[0]; k=init.index(branch)
    need([(x['mnemonic'],x['operand']) for x in init[k-4:k]]==
         [('mov','ecx, 0x40'),('mul','ecx'),('mov','dword ptr [esp + 0x24], eax'),('seto','al')], 'copy-index overflow witness drift')
    # The JO->panic_const_mul_overflow edge is baseline-identical (same offsets in
    # the authenticated F4 ELF), so it is NOT an F5-only emitted panic edge.
    obody=body(oldrows,baseline.symbols[initname])
    def structural(seq):
        return {n: [i for i,x in enumerate(seq) if q(x)] for n,q in
            (('mul',lambda x:x['mnemonic']=='mul'),('seto',lambda x:x['mnemonic']=='seto'),
             ('jo',lambda x:x['mnemonic']=='jo'),
             ('panic',lambda x:x['mnemonic']=='call' and 'panic_const_mul_overflow' in x['operand']),
             ('memcpy',lambda x:x['mnemonic']=='call' and 'memcpy' in x['operand']))}
    need(all(len(v)==1 for v in structural(init).values()),'payload initializer structure drift')
    need(structural(init)==structural(obody),'payload initializer panic edge not baseline-identical')
    # Provenance: six 24-byte slot prefixes from the approved contract appear
    # exactly twice in the linked ELF bytes as two 0x30-stride groups, and the
    # emitted initializer references the first group via the resolved GOT base.
    reg, gb, setup = pic_base(image, init)
    contract=(ROOT/'src'/'f5_contract.rs').read_text(encoding='utf-8')
    slots=[]
    for body_text in re.findall(r'bytes: \[([^\]]*0x[^\]]*)\]', contract):
        vals=[int(v,0) for v in re.findall(r'0x[0-9a-fA-F]+|\b\d+\b', body_text)]
        if not vals:
            continue
        need(len(vals)==24,'contract slot width drift')
        slots.append(bytes(vals))
    need(len(slots)==6,'contract slot count drift')
    def vaddr(off):
        hits=[q[2]+off-q[1] for q in image.layout['segments'] if q[0]==1 and q[1]<=off<q[1]+q[4]]
        need(len(hits)==1,'payload byte outside unique file-backed PT_LOAD')
        return hits[0]
    located=[]
    for s_ in slots:
        offs=[]; i=image.raw.find(s_)
        while i>=0:
            offs.append(vaddr(i)); i=image.raw.find(s_,i+1)
        need(len(offs)==2,f'slot {len(offs)} occurrences in linked ELF')
        located.append(sorted(offs))
    firsts=[x[0] for x in located]
    need(all(firsts[i+1]-firsts[i]==0x30 for i in range(5)),'payload slot stride drift')
    base=firsts[0]
    refs=[]
    for x in init:
        m=re.fullmatch(r'e[a-z]{2}, \[ebx ([+-]) (0x[0-9a-f]+)\]',x['operand'])
        if x['mnemonic']=='lea' and m:
            a=(gb+(1 if m[1]=='+' else -1)*int(m[2],16))&0xffffffff
            if base<=a<base+0x120: refs.append((x['pc'],a))
    need(refs,'emitted initializer lacks payload-group reference')
    # Exact six-entry disassembly at intended VAs via ET_REL view of linked bytes.
    entries=[]
    for n in range(6):
        view=payload_view(slots[n],0x40000100+n*64)
        tmp=Path(output)/f'f5_payload_entry_{n+1:02d}.elf'
        artifacts(tmp.name, view)
        completed=subprocess.run([str(tool),'-d','--x86-asm-syntax=intel',str(tmp)],capture_output=True,timeout=60)
        need(completed.returncode==0,'payload entry disassembly failed')
        parsed={}
        for line in completed.stdout.decode('utf-8',errors='strict').splitlines():
            mm=re.fullmatch(r'^\s*([0-9a-fA-F]+):[ 	]+((?:[0-9a-fA-F]{2}[ 	]+)+)[ 	]*([a-z][a-z0-9]*)[ 	]*(.*)$',line)
            if mm: parsed[int(mm[1],16)]=(mm[3],mm[4].strip())
        need(0x40000100+n*64 in parsed,'payload entry undecoded')
        entries.append({'va':0x40000100+n*64,'bytes_sha256':sha(slots[n]),'linked_vaddr':base+n*0x30,'decoded':parsed})
    return {'complete':True,'finite_iret_verified':True,'iret_instructions':iret,
        'six_destinations':[0x40000100+n*64 for n in range(6)],
        'initializer_symbol':initname,'initializer_matches_baseline':True,
        'payload_groups':located,'initializer_payload_refs':refs,'entry_disassembly':entries}


def analyze(elf, before, output, artifacts):
    """Shared full binary proof; artifacts is either exclusive writer or verifier."""
    report = {'overall': 'FAIL', 'diagnostic_only': True, 'hardware_green': False,
              'canonical_acceptance': False, 'blockers': [], 'checks': {},
              'reader_sha256': READER_SHA256,
              'identifier_dictionary': IDENTIFIERS,
              'before_required_sha256': BEFORE_SHA256,
              'before_provenance': 'Historical f2_before_macro_01.elf, pinned before macro changes; corroborated by emitted_audit_01..06, not selected by filename or current input digest.'}
    try:
        image, baseline = Image(elf), Image(before)
        need(image.path != baseline.path, 'duplicate ELF input paths')
        report.update(elf=str(image.path), before=str(baseline.path),
                      elf_sha256=sha(image.raw), before_elf_sha256=sha(baseline.raw))
        need(sha(baseline.raw) == BEFORE_SHA256, 'pre-change ELF provenance pin mismatch')
        tool = discover_objdump()
        report['objdump'] = str(tool)
        report['objdump_sha256'] = sha(tool.read_bytes())
        raw, rows, cmd = disassemble(image, tool)
        oldraw, oldrows, oldcmd = disassemble(baseline, tool)
        artifacts('current_disassembly.txt', raw)
        artifacts('before_disassembly.txt', oldraw)
        report['commands'] = [cmd, oldcmd]
        def check(name, procedure):
            try:
                report[name] = procedure()
                report['checks'][name] = True
            except Exception as exc:
                report['checks'][name] = False
                report['blockers'].append(name + ': ' + str(exc))
        names = [f'f5_exc_{v}' for v in range(32)] + ['f5_exception_common',
                 'f5_bridge','f5_unsupported','f5_iret','f5_terminal',
                 'f5_entry_terminal','f5_fail_report','f5_report','f5_before_iret']
        need(all(n in image.symbols for n in names), 'missing mandatory emitted F5 symbol')
        check('terminal_aliases', lambda: [terminal_alias(image, rows, n) for n in ('f5_entry_terminal','f5_terminal')])
        check('entry_comparison', lambda: compare_entries(image, rows, baseline, oldrows))
        approved_functions = [n for n in names if image.symbols[n]['size'] > 0]
        allowed = {x['pc'] for n in approved_functions for x in body(rows, image.symbols[n])}
        roots = [image.symbols[n]['address'] for n in names if n != 'f5_exc_8']
        graph = closure(rows, roots, allowed,
                        {image.symbols[n]['address'] for n in ('f5_bridge','f5_unsupported')},
                        image.symbols['f5_before_iret']['address'])
        report['terminal_closure'] = graph
        report['checks']['terminal_closure'] = graph['complete'] and len(graph['iret_exits']) == 1
        if not report['checks']['terminal_closure']:
            report['blockers'].append('terminal closure forbidden/unresolved edge or missing unique IRETD; see full graph')
        if graph['complete']:
            check('stack_paths', lambda: stack_paths(rows, image, graph))
        else:
            report['blockers'].append('stack proof withheld: terminal CFG is incomplete')
        check('installer_inventory', lambda: installer_inventory(image, rows))
        check('inherited_f2_fatal_comparison', lambda: compare_fatal_functions(image, rows, baseline, oldrows))
        report['checks']['all_inherited_f2_functions_equal'] = all(
            report['checks'].get(n, False) for n in ('entry_comparison','inherited_f2_fatal_comparison'))
        check('installer_failure_transport', lambda: installer_failure_proof(image, rows, graph))
        report['checks']['installer_failure_path_closed'] = report['checks'].get('installer_failure_transport',False)
        check('finite_iret_transition', lambda: payload_obligation(image, rows, tool, output, baseline, oldrows, artifacts))
        payload = report.get('finite_iret_transition', {})
        report['checks']['finite_iret_payload_closure'] = payload.get('complete',False)
        if not payload.get('complete',False):
            violation = payload.get('violation', {})
            report['blockers'].append('FINITE_IRETD_PAYLOADS: ' + json.dumps(violation or {'reason':'proof did not complete'}, sort_keys=True))
        need(image.path.read_bytes() == image.raw and baseline.path.read_bytes() == baseline.raw, 'ELF changed during read-only audit')
        report['checks']['elf_inputs_stable'] = True
        need(set(report['checks']) == REQUIRED_CHECKS and
             all(v is True for v in report['checks'].values()), 'mandatory proof checks incomplete')
        need(sha(tool.read_bytes()) == report['objdump_sha256'], 'objdump changed during audit')
        need(current_pins() == LOADED_PINS and sha(Path(__file__).read_bytes()) == READER_SHA256,
             'audit reader/dependency/proof input changed during audit')
        report['overall'] = 'BLOCKED' if report['blockers'] else 'PASS'
    except Exception as exc:
        report['blockers'].append(type(exc).__name__ + ': ' + str(exc))
        report['overall'] = 'BLOCKED'
    finally:
        report['dependencies'] = LOADED_PINS
        report['artifact_sha256'] = dict(artifacts.hashes)
    return report


REQUIRED_CHECKS = frozenset((
    'terminal_aliases', 'entry_comparison', 'terminal_closure', 'stack_paths',
    'installer_inventory', 'inherited_f2_fatal_comparison',
    'all_inherited_f2_functions_equal', 'installer_failure_transport',
    'installer_failure_path_closed', 'finite_iret_transition',
    'finite_iret_payload_closure', 'elf_inputs_stable'))
REQUIRED_ARTIFACTS = frozenset(('current_disassembly.txt', 'before_disassembly.txt',
    *[f'f5_payload_entry_{n:02d}.elf' for n in range(1, 7)]))


def current_pins():
    """Pin the static local Python dependency closure, plus consumed contract bytes.

    Resolve imports from source, not sys.modules (which varies with the caller).
    This includes transitive ELF readers and tool-discovery dependencies.
    """
    pending = [Path(__file__).resolve()]
    visited = set()
    pins = {}
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        raw = path.read_bytes()
        if path != Path(__file__).resolve():
            pins[path.relative_to(ROOT).as_posix()] = sha(raw)
        for node in ast.walk(ast.parse(raw, filename=str(path))):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [n.name for n in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                local = ROOT/'scripts'/(module.split('.')[0]+'.py')
                if local.is_file():
                    pending.append(local.resolve())
    pins['src/f5_contract.rs'] = sha((ROOT/'src/f5_contract.rs').read_bytes())
    return dict(sorted(pins.items()))


READER_SHA256 = sha(Path(__file__).read_bytes())
LOADED_PINS = current_pins()


class Artifacts:
    def __init__(self, directory, write=False):
        self.directory, self.write, self.hashes = Path(directory), write, {}

    def __call__(self, name, raw):
        path = self.directory/name
        if self.write:
            with path.open('xb') as stream:
                stream.write(raw)
        else:
            need(path.is_file() and not path.is_symlink(), 'missing/unsafe artifact: '+name)
            need(path.read_bytes() == raw, 'recomputed artifact mismatch: '+name)
        self.hashes[name] = sha(raw)


def strict_report(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate report key: '+key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(RuntimeError('nonfinite JSON')))


def validate_artifacts(directory, elf):
    """Read-only exact-ELF readback; recompute EVERY mandatory proof, fail closed.

    No temporary files, mkdir, builds or output writes. Existing exact payload
    ET_REL views are checked against regenerated linked bytes before objdump.
    Historical source freezes are not refreshed by this diagnostic API.
    """
    directory = Path(directory).resolve(strict=True)
    report_path = directory/'report.json'
    need(report_path.is_file() and not report_path.is_symlink(), 'missing/unsafe report')
    report_raw = report_path.read_bytes()
    report = strict_report(report_raw)
    need(type(report) is dict and report.get('overall') == 'PASS' and
         report.get('blockers') == [], 'incomplete/blocked audit')
    need(report.get('reader_sha256') == READER_SHA256 == sha(Path(__file__).read_bytes()),
         'stale audit reader pin')
    need(report.get('dependencies') == LOADED_PINS == current_pins(), 'stale audit dependency/proof input pins')
    checks = report.get('checks')
    need(type(checks) is dict and set(checks) == REQUIRED_CHECKS and
         all(v is True for v in checks.values()), 'mandatory exact audit checks')
    elf = Path(elf).resolve(strict=True)
    need(report.get('elf') == str(elf) and report.get('elf_sha256') == sha(elf.read_bytes()),
         'exact ELF identity mismatch')
    before = Path(report['before']).resolve(strict=True)
    need(report.get('before_required_sha256') == BEFORE_SHA256 and
         report.get('before_elf_sha256') == BEFORE_SHA256 == sha(before.read_bytes()),
         'pre-change ELF provenance pin mismatch')
    tool = discover_objdump()
    need(report.get('objdump') == str(tool) and
         report.get('objdump_sha256') == sha(tool.read_bytes()), 'objdump identity mismatch')
    pins = report.get('artifact_sha256')
    need(type(pins) is dict and set(pins) == REQUIRED_ARTIFACTS, 'mandatory exact artifact set')
    need({p.name for p in directory.iterdir()} == REQUIRED_ARTIFACTS | {'report.json'},
         'unexpected/missing audit directory entries')
    for name, digest in pins.items():
        path = directory/name
        need(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest,
             'artifact pin mismatch: '+name)
    expected = analyze(elf, before, directory, Artifacts(directory))
    need(expected['overall'] == 'PASS', 'recomputed audit blocked: '+str(expected['blockers']))
    # JSON roundtrip reconciles tuples and integer disassembly keys, not values.
    need(json.dumps(report, sort_keys=True) ==
         json.dumps(json.loads(json.dumps(expected)), sort_keys=True),
         'report/recomputed proof disagreement')
    need(report_path.read_bytes() == report_raw, 'report changed during readback')
    for name, digest in pins.items():
        need(sha((directory/name).read_bytes()) == digest, 'artifact changed during readback: '+name)
    return report


def run(elf, before, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = analyze(elf, before, output, Artifacts(output, write=True))
    with (output/'report.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'overall': report['overall'], 'report': str(output/'report.json'),
                      'blockers': report['blockers']}, indent=2))
    return 0 if report['overall'] == 'PASS' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    return run(args.elf, args.before, args.output_dir)


if __name__ == '__main__':
    raise SystemExit(main())
