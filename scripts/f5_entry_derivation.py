"""Closed complete-file F5 lexical derivation under entry amendment 01.

This proves constrained expansion, NOT literal source sharing or ELF semantics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if sys.flags.optimize:
    raise RuntimeError('optimized evidence execution refused')

F2_SHA256 = 'a43dd7a8bb0db3bce288237d89705b2be4ef95723fa28de78fb1e87708423c60'
# Literal dictionary from authenticated entry_design_amendment_01.md section 2.4.
IDENTIFIERS = {
    'f5_bridge': 'f2_fatal', 'f5_entry_terminal': 'f2_terminal',
    'f5_terminal': 'f2_terminal', 'f5_unsupported': 'f2_unsupported',
    'f5_exception_common': 'f2_exception_common', 'f5_normalized': 'f2_normalized',
    'f5_exception_entries': 'f2_exception_entries', 'f5_exc_': 'f2_exc_',
    'F5_STUB': 'F2_STUB',
    **{f'f5_exc_{v}': f'f2_exc_{v}' for v in range(32)},
}
STRINGS = {'"F5 frame size mismatch"': '"F2 frame size mismatch"',
           '"F5 normalized vector offset mismatch"': '"F2 normalized vector offset mismatch"'}
TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z_0-9]*')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def map_identifier(name):
    if name in IDENTIFIERS:
        return IDENTIFIERS[name]
    need(not name.startswith(('f5_', 'F5')), 'unknown F5 identifier: ' + name)
    return name


def lexical(raw, f5=False):
    text = raw.decode('ascii', errors='strict')
    # No splitlines(): only CR and LF are permitted line separators.
    lines = [line.strip(' \t') for line in re.split(r'\r\n|\r|\n', text)]
    lines = [line for line in lines if line and not line.startswith('#')]
    def replace(match):
        value = match[0]
        if value.startswith('"'):
            return STRINGS.get(value, value)
        return map_identifier(value)
    return [TOKEN.sub(replace, line) for line in lines] if f5 else lines


def compare_bytes(f2, f5):
    # Binding before any parsing, including lexical diagnostic parsing.
    need(sha(f2) == F2_SHA256, 'wrong accepted F2 raw SHA256')
    first, second = lexical(f2), lexical(f5, True)
    if first != second:
        i = next((i for i, (a, b) in enumerate(zip(first, second)) if a != b), min(len(first), len(second)))
        raise RuntimeError('ordered complete-file derivation mismatch at retained line ' + str(i+1)
                           + ': expected=' + repr(first[i:i+1]) + ' actual=' + repr(second[i:i+1])
                           + ' lengths=' + repr((len(first), len(second))))
    vectors = [line for line in first if re.match(r'F2_STUB [0-9]', line)]
    need(len(vectors) == 32 and [int(re.match(r'F2_STUB ([0-9]+)', line)[1]) for line in vectors] == list(range(32)), 'vector completeness/order')
    return {'overall': 'PASS', 'f2_raw_sha256': sha(f2), 'f5_raw_sha256': sha(f5),
            'literal_source_shared': False, 'mechanically_constrained_expansion': True,
            'identifier_dictionary': IDENTIFIERS, 'diagnostic_strings': STRINGS,
            'compared_line_count': len(first), 'ordered_vector_definitions': vectors,
            'ordered_table_lines': [line for line in first if line.startswith('.long ')],
            'f2_sequence_sha256': sha('\n'.join(first).encode('ascii')),
            'mapped_f5_sequence_sha256': sha('\n'.join(second).encode('ascii')),
            'both_terminal_alias_elf_proofs_required_separately': True}


def validate(root, pins):
    root = Path(root).resolve()
    names = ('src/exception_entry.s', 'src/f5_exception_entry.s', 'scripts/f5_entry_derivation.py')
    need(type(pins) is dict and all(n in pins for n in names), 'missing mandatory source/validator pins')
    paths = [(root/n).resolve(strict=True) for n in names]
    need(len(set(paths)) == len(paths), 'duplicate input paths')
    for name, path in zip(names, paths):
        need(path.is_relative_to(root) and not (root/name).is_symlink(), 'invalid source path')
        need(re.fullmatch('[0-9a-f]{64}', pins[name]) is not None and sha(path.read_bytes()) == pins[name], 'stale source/validator pin: ' + name)
    result = compare_bytes(paths[0].read_bytes(), paths[1].read_bytes())
    result['validator_sha256'] = sha(paths[2].read_bytes())
    result['source_paths'] = list(names)
    return result


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        need(name not in result, 'duplicate input path/key: ' + name)
        result[name] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'refuse evidence overwrite')
    try:
        manifest = json.loads(args.manifest.read_bytes(), object_pairs_hook=unique_object)
        result = validate(args.root, manifest.get('pins', manifest))
    except Exception as exc:
        result = {'overall': 'FAIL', 'error': repr(exc)}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
