"""Check proposed payload decoding at each actual entry, not through padding."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
base = ROOT / 'test_results/f5p01/design_bytes_02'
out = ROOT / 'test_results/f5p01/design_entries_04'
out.mkdir(parents=True, exist_ok=False)
proposal = json.loads((base / 'report.json').read_text())
obj = base / 'proposed_payload.o'
rows = []
for row in proposal['scenarios']:
    command = [proposal['command'][0], '-d', '--x86-asm-syntax=intel',
               '--start-address=' + hex(row['entry']),
               '--stop-address=' + hex(row['entry'] + row['size']), str(obj)]
    result = subprocess.run(command, capture_output=True, timeout=30)
    (out / (row['scenario'] + '.txt')).write_bytes(result.stdout + result.stderr)
    text = result.stdout.decode('utf-8', errors='strict')
    instructions = []
    for match in re.finditer(r'^[ \t]*([0-9a-f]+):[ \t]+((?:[0-9a-f]{2}[ \t]+)+)[ \t]*([a-z][a-z0-9]*)[ \t]*([^\r\n]*)$', text, re.M):
        instructions.append({'address': int(match[1], 16), 'bytes': bytes.fromhex(match[2]).hex(),
                             'mnemonic': match[3], 'operands': match[4].strip()})
    raw = ''.join(i['bytes'] for i in instructions)
    ops = [i['mnemonic'] for i in instructions]
    expected_fault = {'A': 'ud2', 'B': 'mov', 'C': 'mov', 'D': 'hlt', 'E': 'out', 'F': 'mov'}[row['scenario']]
    checks = {'tool_exit_zero': result.returncode == 0,
              'exact_all_instruction_bytes': raw == row['bytes'],
              'exact_prologue_and_fault': ops == ['xor', 'mov', 'push', 'pop', 'std', expected_fault, 'ud2'],
              'intended_fault_address': len(instructions) == 7 and instructions[5]['address'] == row['fault_eip']}
    rows.append({'scenario': row['scenario'], 'command': command,
                 'instructions': instructions, 'checks': checks, 'overall': 'PASS' if all(checks.values()) else 'FAIL'})
report = {'scope': 'nonexecuting proposal disassembly; not hardware GREEN or kernel ELF audit',
          'design_sha256': proposal['design_sha256'],
          'overall': 'PASS' if all(r['overall'] == 'PASS' for r in rows) else 'FAIL',
          'rows': rows, 'payload_executed': False,
          'note': 'Linear decode of the whole padded block in design_bytes_02 can cross odd padding into later entries; this independent per-entry decode avoids that artifact.',
          'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}}
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'overall': report['overall'], 'scenarios': len(rows), 'output': str(out)}))
raise SystemExit(0 if report['overall'] == 'PASS' else 1)
