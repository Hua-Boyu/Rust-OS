"""Exact source/literal/emitted full-closure checks. Does not build or run QEMU."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
if sys.flags.optimize: raise RuntimeError('optimized verification refused')
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from phase6_verify import source_snapshot,predecessor_contract,F3_PREDECESSOR_GATES,F4_GATES
from collections import Counter
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
report={'overall':'FAIL','scope':'Source/raw ELF/emitted serial contract, not guest execution or independent approval'}
try:
    graph=json.loads((BASE/'correction_green_02/closure.json').read_bytes())
    elf=BASE/'correction_green_02/kernel.elf'
    need(sha(elf)==graph['elf_sha256'],'ELF mismatch')
    need(graph['result']=='GREEN' and not graph['forbidden'] and not graph['unresolved'],'not full closure GREEN')
    blocks=list(graph['closure'].values())
    root=next(b for b in blocks if '11f4_terminal' in b['name'])
    emitter=next(b for b in blocks if '18f4_terminal_serial' in b['name'])
    marker=next(b for b in blocks if b['name']=='f4_arena_terminal')
    need(len(blocks)==4,'unexpected closure dependency')
    need(any(i['bytes']=='c6 01 03' and i['op']=='movb' for i in root['instructions']),'exact Terminal byte MOV')
    ins=emitter['instructions']; code=[(i['op'],i['args'].split(' #')[0].strip()) for i in ins if i['op']!='int3']
    need(not any(op.startswith('call') for op,arg in code),'emitter calls')
    need([i['bytes'] for i in marker['instructions'][:3]]==['fa','f4','eb fc'],'terminal marker code drift')
    joined='\n'.join(i['line'] for i in ins)
    for fragment in ('$0x22, %edi','$0x186a0, %ecx','$0x3fd, %dx','inb\t%dx, %al','$0x20, %al','decl\t%ecx','movb\t(%esi), %al','$0x3f8, %dx','outb\t%al, %dx','incl\t%esi','decl\t%edi'):
        need(fragment in joined,'missing emitted protocol '+fragment)
    old=(ROOT/'test_results/f4p04/source/src/memory/retained_owner.rs').read_bytes()
    source=(ROOT/'src/memory/retained_owner.rs').read_bytes()
    messages=[b'F4 USER arena PASS Ring0 terminal\n',b'F4 USER arena FAIL Ring0 terminal\n']
    raw=elf.read_bytes()
    # ELF32 little-endian PT_LOAD virtual read, no dependence on normalized text.
    phoff=struct.unpack_from('<I',raw,28)[0]; phsize,phnum=struct.unpack_from('<HH',raw,42)
    segments=[struct.unpack_from('<8I',raw,phoff+i*phsize) for i in range(phnum)]
    def readva(address,size):
        candidates=[p for p in segments if p[0]==1 and p[2]<=address and address+size<=p[2]+p[4]]
        need(len(candidates)==1,'static literal not uniquely file-backed')
        p=candidates[0]; offset=p[1]+address-p[2]; return raw[offset:offset+size]
    # PIC call-next + ADD EBX gives GOT base; both LEAs choose the static literals.
    pic=next(e for e in graph['edges'] if e['from']==graph['root'] and e['kind']=='pic_call_next')
    add=next(i for i in root['instructions'] if i['op']=='addl' and i['args'].startswith('$0x') and ', %ebx' in i['args'])
    got=pic['target']+int(re.match(r'\$0x([0-9a-f]+)',add['args'])[1],16)
    lea=[i for i in root['instructions'] if i['op']=='leal' and '(%eax), %eax' in i['args']]
    need(len(lea)==2,'exact success/failure selection')
    observed=[]
    for i in lea:
        offset=int(re.match(r'(-?0x[0-9a-f]+)\(%eax\)',i['args'])[1],16)
        observed.append(readva(got+offset,34))
    need(Counter(observed)==Counter(messages),'emitted literal bytes not equivalent')
    for message in messages:
        escaped=message.replace(b'\n',b'\\n')
        need(b'"'+escaped+b'"' in old and b'b"'+escaped+b'"' in source,'original/new bytes')
        need(len(message)==34,'fixed array length')
    before=json.loads((ROOT/'test_results/f4p04/source_before.json').read_bytes())
    current=source_snapshot()
    delta={p:[before.get(p),current.get(p)] for p in before.keys()|current.keys() if before.get(p)!=current.get(p)}
    need(set(delta)=={'src/memory/retained_owner.rs'},'unexplained freeze delta')
    predecessor_contract()
    need(len(F3_PREDECESSOR_GATES)==70 and len(F4_GATES)==2,'gate count')
    report.update(overall='PASS',source_sha256=current,source_pin_count=len(current),source_delta=delta,
        elf_sha256=sha(elf),graph_sha256=sha(BASE/'correction_green_02/closure.json'),
        closure={'blocks':len(blocks),'edges':len(graph['edges']),'forbidden':0,'unresolved':0},
        bytes=[{'hex':m.hex(),'length':len(m)} for m in observed],
        serial_protocol={'THR':0x3f8,'LSR':0x3fd,'THRE':0x20,'width_bits':8,'polls_per_byte':100000,'byte_count':34,'max_polls':3400000,'timeout_policy':'drop current byte and advance, identical to shared driver'},
        machine_code={b['name']:b['instructions'] for b in blocks},
        gates=list(F3_PREDECESSOR_GATES)+list(F4_GATES),reader_sha256=sha(__file__))
except Exception as exc: report['error']=repr(exc)
with (BASE/'terminal_contract_02.json').open('x',encoding='utf8',newline='\n') as f: json.dump(report,f,indent=2); f.write('\n')
print(json.dumps({k:report.get(k) for k in ('overall','source_pin_count','source_delta','closure','bytes','error')},indent=2))
raise SystemExit(0 if report['overall']=='PASS' else 1)
