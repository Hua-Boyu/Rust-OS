"""Disassemble design data in a nonloadable ELF object; execute no payload."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from f3_full_guest import discover_objdump

out = ROOT / 'test_results/f5p01/design_bytes_02'
out.mkdir(parents=True, exist_ok=False)
design = (ROOT / 'test_results/phase11f5_cpl3_proof/design.md').read_bytes()
rows = []
image = bytearray(384)
for match in re.finditer(rb'^\|([A-F])(?: proposed)?\|(0x[0-9a-f]+)\|(0x[0-9a-f]+)\|([0-9a-f]+)\|', design, re.M):
    name, entry, fault, raw = match.groups()
    entry, fault, raw = int(entry, 16), int(fault, 16), bytes.fromhex(raw.decode())
    slot = ord(name.decode()) - ord('A')
    if entry != 0x40000100 + slot * 64 or fault != entry + 12 or len(raw) > 64:
        raise RuntimeError('invalid proposed slot layout')
    image[slot * 64:slot * 64 + len(raw)] = raw
    rows.append({'scenario': name.decode(), 'entry': entry, 'fault_eip': fault,
                 'bytes': raw.hex(), 'size': len(raw)})
if [row['scenario'] for row in rows] != list('ABCDEF'):
    raise RuntimeError('missing/duplicate design slots')
# ET_REL, no entrypoint/program headers: cannot be booted as an executable.
shstr = b'\x00.text\x00.shstrtab\x00'
text_at = 52
str_at = text_at + len(image)
sh_at = (str_at + len(shstr) + 3) & ~3
header = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01' + b'\x00' * 9,
                     1, 3, 1, 0, 0, sh_at, 0, 52, 0, 0, 40, 3, 2)
sections = bytes(40)
sections += struct.pack('<10I', 1, 1, 6, 0x40000100, text_at, len(image), 0, 0, 1, 0)
sections += struct.pack('<10I', 7, 3, 0, 0, str_at, len(shstr), 0, 0, 1, 0)
raw = header + image + shstr
raw += bytes(sh_at - len(raw)) + sections
obj = out / 'proposed_payload.o'
obj.write_bytes(raw)
command = [str(discover_objdump()), '-D', '--x86-asm-syntax=intel', str(obj)]
result = subprocess.run(command, capture_output=True, timeout=60)
(out / 'disassembly.txt').write_bytes(result.stdout)
(out / 'disassembly.stderr.txt').write_bytes(result.stderr)
report = {'scope': 'design-byte characterization; not kernel ELF or hardware execution',
          'command': command, 'exit_code': result.returncode, 'scenarios': rows,
          'design_sha256': hashlib.sha256(design).hexdigest(),
          'payload_executed': False, 'object_type': 'ET_REL with no program headers',
          'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in out.iterdir() if p.is_file()}}
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'exit_code': result.returncode, 'scenarios': len(rows), 'output': str(out)}))
raise SystemExit(result.returncode)
