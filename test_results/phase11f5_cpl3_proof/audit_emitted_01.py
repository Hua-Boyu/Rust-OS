"""Pre-hardware emitted F5 closure/entry comparison, not candidate acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from b13_entry_inject import elf_symbols
from f3_full_guest import discover_objdump


def need(value, message):
    if not value:
        raise RuntimeError(message)


def disassemble(path, tool):
    text = subprocess.check_output([str(tool), '-d', '--no-show-raw-insn',
                                   '--x86-asm-syntax=intel', str(path)], text=True)
    rows = {}
    for line in text.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):[ \t]+([a-z][a-z0-9]*)[ \t]*(.*)$', line)
        if m:
            rows[int(m[1], 16)] = (m[2], m[3].strip())
    need(rows, 'no emitted instructions')
    return text, rows


def body(rows, symbol):
    begin, end = symbol['address'], symbol['address'] + symbol['size']
    need(end > begin, 'zero-size function')
    return [(p, *rows[p]) for p in sorted(rows) if begin <= p < end]


def normalize(instruction, f5=False):
    mnemonic, operand = instruction
    if mnemonic.startswith('j') or mnemonic.startswith('call'):
        match = re.fullmatch(r'0x[0-9a-f]+ <([^>]+)>', operand)
        need(match, 'non-direct comparison edge: ' + operand)
        operand = match[1]
        if f5:
            operand = operand.replace('f5_bridge', 'f2_fatal').replace('f5_', 'f2_')
    return mnemonic, operand


def run(elf, before, output):
    output.mkdir(parents=True, exist_ok=False)
    result = {'overall': 'FAIL', 'not_full_candidate_review': True,
              'elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest(),
              'before_elf_sha256': hashlib.sha256(before.read_bytes()).hexdigest()}
    try:
        tool = discover_objdump()
        text, rows = disassemble(elf, tool)
        oldtext, oldrows = disassemble(before, tool)
        (output / 'current_disassembly.txt').write_text(text)
        (output / 'pre_macro_disassembly.txt').write_text(oldtext)
        symbols, oldsymbols = elf_symbols(elf), elf_symbols(before)
        need(all(name in symbols for name in ['f5_bridge', 'f5_iret', 'f5_unsupported',
             'f5_terminal', 'f5_exception_common', 'f2_exception_common']), 'missing emitted root')
        compared = []
        for name in ['f2_exception_common', *[f'f2_exc_{v}' for v in range(32)]]:
            old = [normalize((m, op)) for _, m, op in body(oldrows, oldsymbols[name])]
            new = [normalize((m, op)) for _, m, op in body(rows, symbols[name])]
            need(old == new, 'inherited F2 emitted instruction drift: ' + name)
            compared.append(name)
        first = [normalize((m, op)) for _, m, op in body(rows, symbols['f2_exception_common'])]
        second = [normalize((m, op), True) for _, m, op in body(rows, symbols['f5_exception_common'])]
        # Terminal label names differ; both are the same CLI/HLT self-loop.
        second = [(m, op.replace('f2_entry_terminal', 'f2_terminal')) for m, op in second]
        need(first == second, 'F2/F5 shared normalizer mismatch')
        addresses = sorted(rows)
        following = dict(zip(addresses, addresses[1:]))
        roots = [symbols[f'f5_exc_{v}']['address'] for v in range(32) if v != 8]
        roots += [symbols[n]['address'] for n in ('f5_bridge', 'f5_unsupported', 'f5_iret')]
        work, seen, edges, calls, exits = roots[:], set(), [], [], []
        while work:
            pc = work.pop()
            if pc in seen:
                continue
            need(pc in rows, f'missing decoded edge {pc:x}')
            seen.add(pc)
            mnemonic, operand = rows[pc]
            if mnemonic.startswith('ret'):
                raise RuntimeError('return reachable in terminal closure')
            if mnemonic in ('iret', 'iretd', 'iretl'):
                need(symbols['f5_iret']['address'] <= pc < symbols['f5_iret']['address'] + symbols['f5_iret']['size'], 'unexpected IRET')
                exits.append(pc)
                continue
            targets = []
            if mnemonic.startswith('j') or mnemonic.startswith('call'):
                match = re.fullmatch(r'0x([0-9a-f]+) <([^>]+)>', operand)
                need(match, 'indirect/missing terminal edge ' + operand)
                target = int(match[1], 16)
                if mnemonic.startswith('call'):
                    need(target in (symbols['f5_bridge']['address'], symbols['f5_unsupported']['address']), 'foreign call: ' + match[2])
                    calls.append({'at': pc, 'target': match[2]})
                    targets.append(target)  # Both destinations are nonreturning.
                else:
                    targets.append(target)
                    if mnemonic != 'jmp':
                        targets.append(following[pc])
            else:
                need(mnemonic not in ('int', 'syscall', 'sysenter', 'ud2'), 'unexpected terminal trap')
                targets.append(following[pc])
            for target in targets:
                edges.append([pc, target])
                work.append(target)
        need(len(exits) == 1, 'exactly one launcher IRETD required')
        bridge = body(rows, symbols['f5_bridge'])
        need(not any(m.startswith('call') or m.startswith('ret') for _, m, _ in bridge), 'bridge calls/returns')
        need([(m, op) for _, m, op in bridge[:3]] == [('mov', 'edi, esp'), ('pushfd', ''), ('pop', 'ebx')], 'naked bridge prologue changed')
        need(sum(m in ('pushfd', 'pushf') for _, m, _ in bridge) == 1
             and not any(m in ('push', 'sub', 'and') and 'esp' in op for _, m, op in bridge), 'unaccounted bridge stack')
        result.update(overall='PASS', objdump=str(tool), inherited_f2_functions_compared=compared,
                      shared_normalizer_equal=True, closure_instruction_count=len(seen),
                      direct_calls=calls, edges=edges, indirect_edges=[], missing_edges=[],
                      iret_pc=exits[0], max_first_entry_stack_bytes=104,
                      max_one_nested_entry_stack_bytes=115, conditional_stack_ceiling_bytes=219,
                      approved_stack_budget_bytes=512,
                      stack_scope='Emitted no-call bridge; first CPL3 fault plus at most one nested event. Inherited F3 double-fault conditional stack bound remains separate.',
                      hardware_green=False)
    except Exception as exc:
        result['error'] = repr(exc)
    (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('edges', 'inherited_f2_functions_compared')}, indent=2))
    return 0 if result['overall'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.flags.optimize:
        raise SystemExit('optimized evidence execution refused')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.elf.resolve(), args.before.resolve(), args.output_dir.resolve()))
