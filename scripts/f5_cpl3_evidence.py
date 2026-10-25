"""Strict standalone F5 raw-evidence readback. No build or guest launch.

A component report is never a full matrix. Hashes bind bytes, not authenticity of
an emulator: fabricated evidence is not established as hardware by this reader.
The terminal audit integration supplies validate_artifacts(directory, elf).
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
from f3_evidence import registers, strict_json, descriptor, tss
from f4_dwarf import extract
from f4_evidence import (storage_symbols, decode_owner, authority, allocator_stats,
                         decode_allocator, SLOTS, words, u32)

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ('f5_cpl3_A_entry','f5_cpl3_B_ro_write','f5_cpl3_C_supervisor_read',
              'f5_cpl3_D_hlt','f5_cpl3_E_io_denied','f5_cpl3_F_guard_read')
RAMS = (128,512)
REQUIRED = tuple((s,r) for s in IDENTITIES for r in RAMS)
DESIGN_SHA = '6b0b3a9324576b0fa148fa415fcaea23fe33a8e5f655da608e8ea56794a1791c'
CONTRACT_SHA = '91984e72662a74558e34e7a158a045984762ed7534fd68ad8be3f3fa005d3df7'
F2_SHA = 'a43dd7a8bb0db3bce288237d89705b2be4ef95723fa28de78fb1e87708423c60'
AUTHORITY = 'test_results/phase11f5_cpl3_proof/'
FAULTS = ((6,0,None),(14,7,0x40000800),(14,5,0x07c01000),
          (13,0,None),(13,0,None),(14,4,0x403fe000))
SNIPPETS = ('31c0668cc868dec0175a5bfd0f0b0f0b',
            '31c0668cc868dec0175a5bfdc605000800407e0f0b',
            '31c0668cc868dec0175a5bfd8b0d0010c0070f0b',
            '31c0668cc868dec0175a5bfdf40f0b',
            '31c0668cc868dec0175a5bfde6800f0b',
            '31c0668cc868dec0175a5bfd8b0d00e03f400f0b')
LABELS = ('initial','before_iret','user_entry','before_fault','bridge','terminal')


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def local(root, name):
    need(type(name) is str and name and '\\' not in name and ':' not in name
         and all(ord(c)>=32 and ord(c)!=127 for c in name), 'invalid local artifact name')
    path = Path(name)
    need(not path.is_absolute() and '..' not in path.parts and path.as_posix()==name,
         'noncanonical artifact path')
    target = root/path
    for parent in (target,*target.parents):
        need(not parent.is_symlink(),'symlink artifact')
        if parent == root:
            break
    need(target.resolve().is_relative_to(root.resolve()),'artifact escape')
    return target


def tree_pins(root, exclude=()):
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink(),'symlink in artifact tree')
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name not in exclude:
                result[name] = sha(path.read_bytes())
    return result


def verify_pins(root, pins, exclude=()):
    need(type(pins) is dict and bool(pins),'missing artifact pins')
    for name,digest in pins.items():
        need(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest),'malformed digest')
        need(sha(local(root,name).read_bytes())==digest,'artifact hash '+name)
    need(tree_pins(root,exclude)==pins,'unlisted/missing artifacts')


def check_authority(source):
    need(sha(local(source,AUTHORITY+'design.md').read_bytes())==DESIGN_SHA,'design raw pin')
    need(sha(local(source,AUTHORITY+'harness_contract_01.json').read_bytes())==CONTRACT_SHA,'harness raw pin')
    need(sha(local(source,'src/exception_entry.s').read_bytes())==F2_SHA,'accepted F2 raw pin')
    contract = strict_json(local(source,AUTHORITY+'harness_contract_01.json'))
    need(contract['design_sha256']==DESIGN_SHA and contract['rams']==list(RAMS)
         and contract['scenario_identities']==list(IDENTITIES),'closed authority contract')
    need(local(source,AUTHORITY+'entry_design_amendment_01.md').is_file(),'missing entry amendment')
    return True


def image():
    result = bytearray(4096)
    result[:4] = bytes.fromhex('0f0bebfc')
    result[2048:2059] = b'F4-RO-DATA\0'
    for i,snippet in enumerate(SNIPPETS):
        raw = bytes.fromhex(snippet)
        result[256+64*i:256+64*i+len(raw)] = raw
    return bytes(result)


def hardware(raw):
    text = raw.decode('ascii')
    result = {}
    for name in ('CR0','CR2','CR3','CR4','EIP','EFL'):
        values = re.findall(r'\b'+name+r'=([0-9a-fA-F]+)',text)
        need(len(values)==1,'unique CPU '+name)
        result[name] = int(values[0],16)
    for name in ('GDT','IDT'):
        values = re.findall(name+r'=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
        need(len(values)==1,'unique '+name)
        result[name] = [int(v,16) for v in values[0]]
    for name in ('TR','CPL','HLT'):
        values = re.findall(r'\b'+name+r'\s*=([0-9a-fA-F]+)',text)
        need(len(values)==1,'unique '+name)
        result[name] = int(values[0],16)
    need(result['CR0']&0x80010001==0x80010001 and result['CR4']&0x00a00030==0
         and 'EFER=0000000000000000' in text,'unsupported CPU profile')
    need(result['CR3']>=4096 and result['CR3']%4096==0,'CR3 geometry')
    return result


def cached_context(raw, user=False, user_data=False, tss_base=None):
    text=raw.decode('ascii')
    for name in ('CS','SS','DS','ES','FS','GS'):
        matches=re.findall(r'\b'+name+r'\s*=([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
        need(len(matches)==1,'unique cached '+name)
        actual=tuple(int(v,16) for v in matches[0])
        is_user=user or user_data and name not in ('CS','SS')
        selector=(0x2b if name=='CS' else 0x33) if is_user else (8 if name=='CS' else 16)
        attrs=(0x00cffb00 if name=='CS' else 0x00cff300) if is_user else (0x00cf9900 if name=='CS' else 0x00cf9300)
        need(actual==(selector,0,0xffffffff,attrs),'exact cached segment '+name)
    if tss_base is not None:
        matches=re.findall(r'\bTR\s*=([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
        need(len(matches)==1 and tuple(int(v,16) for v in matches[0])==(24,tss_base,103,0x8900),'unchanged cached normal TSS')
    return True


def validate_matrix_rows(rows, selected=None):
    need(selected is None or type(selected) is int and 1<=selected<=6,'component integer')
    need(type(rows) is list,'matrix rows')
    for row in rows:
        need(type(row) is dict and type(row.get('ram_mib')) is int
             and type(row.get('scenario_integer')) is int,'matrix row types')
        scenario = row['scenario_integer']
        need(1<=scenario<=6 and row['scenario']==IDENTITIES[scenario-1],'scenario identity')
    expected = REQUIRED if selected is None else tuple((IDENTITIES[selected-1],r) for r in RAMS)
    need([(r['scenario'],r['ram_mib']) for r in rows]==list(expected),'exact ordered matrix')
    need(Counter((r['scenario'],r['ram_mib']) for r in rows)==Counter(expected),'matrix multiplicity')
    return True


def validate_audit(directory, elf, before):
    """Read-only exact-ELF hook; never accept a self-declared audit PASS alone."""
    need(sha(Path(before).read_bytes())=='770f18590e186465fcb301f8d09c044d1055707027f0fa9ba596d0e2a1f33fcc','audit historical baseline bytes')
    audit_record=strict_json(Path(directory)/'report.json')
    need(audit_record.get('overall')=='PASS' and audit_record.get('blockers')==[]
         and audit_record.get('before')==str(Path(before).resolve())
         and audit_record.get('checks') and all(v is True for v in audit_record['checks'].values()),'incomplete/blocked audit')
    from f5_terminal_audit import validate_artifacts
    result = validate_artifacts(Path(directory),Path(elf))
    need(type(result) is dict and result.get('overall')=='PASS'
         and result.get('elf_sha256')==sha(Path(elf).read_bytes()),'exact ELF audit readback')
    return result


def records(raw, scenario, cr3, before_flags):
    need(type(scenario) is int and 1<=scenario<=6 and len(raw)==256,'record extent/scenario')
    record = struct.unpack('<64I',raw)
    vector,error,cr2 = FAULTS[scenario-1]
    pc = 0x4000010c+(scenario-1)*64
    frame = record[16:35]
    need(record[:3]==(0x46354350,scenario,1),'kernel-owned success record')
    need(record[3:5]==(0x07c04fb4,0x07c04f9c) and frame[7]==record[3]+48,'exact frame/bridge geometry')
    need(frame[:4]==(0x33,)*4 and frame[8]==0x5a17c0de and frame[11]==0x2b,'saved segments/sentinels')
    need(frame[12:15]==(vector,error,pc),'exact full-width exception oracle')
    need(frame[15]&65535==0x2b and frame[17]==0x40400000 and frame[18]&65535==0x33,'cross-ring tail')
    need(frame[16] in (0x10446,0x10456) and frame[16]==before_flags|0x10000,'RF1 and AF-only saved flags')
    need(record[7]==cr3 and (vector!=14 or record[6]==cr2),'record CR3/CR2')
    need(record[5]&0x80010001==0x80010001 and record[8]&0x00a00030==0,'record CPU profile')
    need(record[10:16]==(8,16,16,16,16,16) and record[9]&0x600==0,'live normalized kernel context')
    need(struct.unpack_from('<H',raw,140)[0]==55 and record[37:41]==(24,0x07c05000,16,104),'GDTR/TR/TSS record')
    need(raw[146:148]==b'\0\0' and raw[164:]==bytes(92),'record unused bytes')
    return record,frame


class Transport:
    """Exact read-only transport and immutable physical/virtual byte origins."""
    def __init__(self, root, row):
        self.root,self.row = root,row
        self.g = self.lines(root/'gdb.jsonl')
        self.q = self.lines(root/'qmp.jsonl')
        need(all(type(e.get('seq')) is int for e in self.g+self.q),'transport sequence integer types')
        self.events=sorted(self.g+self.q,key=lambda e:e['seq'])
        need([e['seq'] for e in self.events]==list(range(1,len(self.events)+1)), 'complete unique cross-transport sequence')
        need(all(type(e['started_ns']) is int and type(e['ended_ns']) is int
                 and e['started_ns']<=e['ended_ns'] for e in self.events),'transport timestamps')
        need(all(a['ended_ns']<=b['started_ns'] for a,b in zip(self.events,self.events[1:])), 'transport causal order')
        self.windows={}
        self.physical = {}
        self.physical_events = {}
        for e in self.g:
            c = e['command']
            need(c in ('?','g','c') or re.fullmatch(r'(?:m[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,1)',c),
                 'forbidden GDB write/command')
            need(type(e['reply']) is str and not e['reply'].startswith('E'),'failed RSP')
        allowed = {'qmp_capabilities','query-version','query-status','human-monitor-command','pmemsave','cont','stop'}
        for e in self.q:
            need(e['command'] in allowed,'forbidden QMP command')
            if e['command']=='human-monitor-command':
                need(e['arguments']=={'command-line':'info registers'},'HMP mutation')
            if e['command']=='pmemsave':
                a=e['arguments']; name=a['filename']
                need(name not in self.physical and e['reply']=={},'duplicate/failed pmemsave')
                self.physical[name]=(a['val'],a['size'])
                self.physical_events[name]=e
        need([e['reply'] for e in self.q if e['command']=='query-version']==[row['qemu_version']], 'QEMU version')
        self.used=set()

    @staticmethod
    def lines(path):
        rows=[]
        for line in path.read_text(encoding='utf-8').splitlines():
            def pairs(items):
                d={}
                for k,v in items:
                    need(k not in d,'duplicate transport JSON key')
                    d[k]=v
                return d
            rows.append(json.loads(line,object_pairs_hook=pairs,parse_constant=lambda x: need(False,x)))
        need(rows,'missing protocol log')
        return rows

    def origin(self,name,address,size):
        need(type(address) is int and type(size) is int and address>=4096 and size>0
             and address+size<=self.row['ram_mib']*1024*1024,'physical RAM extent')
        path=self.root/name
        need(self.physical.get(path.as_posix())==(address,size),'pmemsave origin '+name)
        label=next((label for label in ('initial','before_iret','terminal') if name.startswith(label+'_')),None)
        need(label in self.windows,'physical checkpoint identity')
        low,high=self.windows[label]
        need(low<self.physical_events[path.as_posix()]['seq']<high,'stopped physical capture causal window')
        raw=path.read_bytes()
        need(len(raw)==size,'physical capture extent '+name)
        self.used.add(path.as_posix())
        return raw

    def virtual(self,name,address,size):
        raw=(self.root/name).read_bytes()
        need(len(raw)==size,'virtual extent '+name)
        chunks=[]
        for offset in range(0,size,512):
            count=min(512,size-offset)
            label={'iret_words.bin':'before_iret','fault_instruction.bin':'before_fault',
                   'mandatory_frame.bin':'bridge','bridge_call.bin':'bridge',
                   'stable_halt.bin':'stable','stable_record.bin':'stable'}[name]
            if label=='stable':
                low=next(e['seq'] for e in self.q if e['command']=='stop')
                high=len(self.events)+1
            else:
                low,high=self.windows[label]
            replies=[e['reply'] for e in self.g if e['command']==f'm{address+offset:x},{count:x}'
                     and low<e['seq']<high]
            piece=raw[offset:offset+count]
            need(piece.hex() in replies,'RSP byte origin '+name)
            chunks.append(piece)
        return b''.join(chunks)

    def checkpoint(self,label,address,cpl):
        raw=(self.root/(label+'_register_packet.txt')).read_bytes()
        packet=raw.decode('ascii')
        need(sum(e['command']=='g' and e['reply']==packet for e in self.g)>=(2 if label in ('initial','before_iret','terminal') else 1),'register packet log binding')
        matches=[e for e in self.g if e['command']==f'Z1,{address:x},1']
        need(len(matches)==1,'unique checkpoint breakpoint')
        low=matches[0]['seq']
        high=min((e['seq'] for e in self.g if e['command'].startswith('Z1,') and e['seq']>low),default=len(self.events)+1)
        self.windows[label]=(low,high)
        events=[e for e in self.events if low<e['seq']<high]
        need(any(e['command']=='query-status' and e['reply']['running'] is False for e in events),'checkpoint paused acknowledgement')
        need(any(e['command']=='g' and e['reply']==packet for e in events),'checkpoint packet causal binding')
        regs=registers(raw)
        hwraw=(self.root/(label+'_hardware.txt')).read_bytes()
        hw=hardware(hwraw)
        need(any(e['command']=='human-monitor-command' and e['reply']==hwraw.decode('ascii') for e in events),'HMP raw binding')
        need(regs['eip']==hw['EIP']==address and hw['CPL']==cpl and regs['cs']&3==cpl
             and regs['eflags']==hw['EFL'],'stopped CPU/RSP disagreement')
        return regs,hw

    def finish(self,addresses):
        expected=[]
        for address in addresses:
            expected.extend((f'Z1,{address:x},1','c',f'z1,{address:x},1'))
        events=[e for e in self.g if e['command']=='c' or e['command'].startswith(('Z','z'))]
        need([e['command'] for e in events]==expected,'ordered breakpoint/continue/remove schedule')
        need(all(e['reply'].startswith(('T05','S05')) if e['command']=='c' else e['reply']=='OK' for e in events),'stop/breakpoint acknowledgement')
        need(set(self.physical)==self.used,'unvalidated physical dump')
        commands=[e['command'] for e in self.q]
        need(commands.count('cont')==commands.count('stop')==1,'one stable terminal window')
        cont=commands.index('cont'); stop=commands.index('stop')
        need(cont<stop and all(c!='pmemsave' for c in commands[cont:]),'stable observation ordering')
        start_event=self.q[cont]; stop_event=self.q[stop]
        need(stop_event['started_ns']-start_event['ended_ns']>=200000000,'actual timed stable interval')
        need(start_event['seq']>max(e['seq'] for e in self.g if e['command'].startswith('z1,')), 'breakpoints removed before stable interval')
        need(not any(e['command']=='c' or e['command'].startswith('Z1,') for e in self.g if e['seq']>start_event['seq']),'no USER resumption')
        need(any(e['command']=='query-status' and e['reply']['running'] is False for e in self.q[stop+1:]),'stable CPU stop')


def validate_gdt_storage(data, hw, symbols, initial=False):
    """Separate Extension's 64-byte storage from its 56-byte CPU table.

    src/f5_gdt.rs repr(C, align(8)): entries@0, attempted:u32@56,
    tail padding@60. The emitted Extension DWARF confirms size64/offset56;
    the static is in zero-initialized .bss and install writes only the fields,
    never the padding. Thus all four padding bytes must remain zero, not be
    discarded as unspecified descriptor bytes.
    """
    raw = data['f5_gdt']
    need(symbols['f5_gdt']['size'] == 64 and len(raw) == 64,
         'F5 Extension storage extent')
    need(u32(raw, 56) == (0 if initial else 1), 'F5 GDT attempted lifecycle')
    need(raw[60:64] == bytes(4), 'F5 GDT zero-initialized padding')
    if initial:
        need(raw[:56] == bytes(56), 'initial unpublished F5 descriptors')
    else:
        base = symbols['f3_context']['address']
        old = (bytes(8) + bytes.fromhex('ffff00000099cf00ffff00000093cf00')
               + descriptor(base+40, 0x8b) + descriptor(base+144, 0x89))
        need(hw['GDT'] == [symbols['f5_gdt']['address'], 55] and hw['TR'] == 24,
             'F5 GDTR/TR')
        need(data['gdt'] == old + struct.pack('<QQ', 0x00cffb000000ffff, 0x00cff3000000ffff)
             and data['f3_context'][:40] == old and raw[:56] == data['gdt'],
             'exact preserved old40/new16 GDT bytes')
    return True


def snapshot(root,label,hw,layout,symbols,transport,initial=False):
    meta=strict_json(root/(label+'_capture.json'))
    need(meta['controls']==hw and meta['capture_stable'] is True,'snapshot control binding')
    def physical(name,address,size,repeat=False):
        raw=transport.origin(label+'_'+name+'.bin',address,size)
        if repeat:
            need(raw==transport.origin(label+'_'+name+'_repeat.bin',address,size),'stable bytes '+name)
        return raw
    directory=words(physical('directory',hw['CR3'],4096,True))
    indices=[i for i,pde in enumerate(directory) if pde&1]
    need(meta['table_indices']==indices,'full table inventory')
    tables={}
    for i,pde in enumerate(directory):
        if pde&1:
            need(pde&0x80==0,'unsupported large page')
            tables[i]=words(physical(f'table_{i:03d}',pde&0xfffff000,4096,True))
        else:
            need(pde==0,'nonpresent PDE nonzero')
    def mapping(va):
        pde=directory[va>>22]
        need(pde&1,'absent required PDE')
        return pde,tables[va>>22][(va>>12)&1023]
    def identity(address,size):
        for page in range(address&~4095,(address+size+4095)&~4095,4096):
            pde,pte=mapping(page)
            need(pde&0x87==3 and pte&0xfffff007==page|3,'supervisor identity mapping')
    stores={**storage_symbols(symbols),**{n:symbols[n] for n in ('f3_context','f5_gdt','f5_record','f5_expect','f5_latch')}}
    need(meta['symbols']==stores,'exact ELF metadata symbols')
    data={}
    for name,sym in stores.items():
        identity(sym['address'],sym['size'])
        data[name]=physical(name,sym['address'],sym['size'],True)
    need(stores['owner']['size']==layout['OwnerMutex']['size'] and stores['allocator']['size']==layout['AllocatorMutex']['size']
         and stores['state']['size']==1 and stores['f5_record']['size']==256 and stores['f5_gdt']['size']==64,'target storage extents')
    need(data['owner'][layout['OwnerMutex']['fields']['lock']]==0
         and data['allocator'][layout['AllocatorMutex']['fields']['lock']]==0,'owner/allocator guards released')
    owner=decode_owner(data['owner'],layout)
    need(meta['decoded_owner']==json.loads(json.dumps(owner)),'decoded owner metadata')
    leases=authority(owner,data['allocator'],layout,0 if initial else 12,'initial' if initial else 'terminal')
    for i,table in tables.items():
        if i!=256 or initial:
            need(directory[i]&4==0 and all(p&4==0 for p in table),'supervisor USER escalation')
    fa=decode_allocator(data['allocator'],layout)
    fields=layout['FrameAllocator']['fields']
    for pa in {hw['CR3']}|{directory[i]&0xfffff000 for i in tables}:
        identity(pa,4096)
        idx=pa//4096
        need(0<idx<65536 and fa[fields['structure_pins']+idx//8]&(1<<(idx%8))
             and not fa[fields['runtime_pins']+idx//8]&(1<<(idx%8))
             and not fa[fields['free']+idx//8]&(1<<(idx%8))
             and u32(fa,fields['alloc_id']+idx*4)!=0,'paging structure authority')
    for lease in leases.values():
        identity(lease['addr'],4096)
    if not initial:
        table=leases['arena_table']['addr']
        need(directory[256]&~0x20==table|7 and directory[257]==0,'owned USER PDE')
        expected=[0]*1024
        expected[0]=leases['payload']['addr']|0x205
        expected[1023]=leases['user_stack']['addr']|0x207
        need(all((p&~0x60 if e else p)==e for p,e in zip(tables[256],expected)),'exact arena/guards')
        for j,name in enumerate(SLOTS[2:10]):
            index=j+1 if j<4 else j+2
            need(tables[31][index]&0xfffff007==leases[name]['addr']|3,'TSS stack lease mapping')
        need(tables[31][0]==tables[31][5]==0,'TSS stack guards')
        for slot,name in (('payload','code'),('user_stack','stack')):
            data[name]=physical(name,leases[slot]['addr'],4096,True)
        need(data['code']==image(),'complete fixed F5 image')
    else:
        need(directory[256]==directory[257]==0,'initial unpublished arena')
    gbase,glimit=hw['GDT']; ibase,ilimit=hw['IDT']
    need(glimit<4096 and 255<=ilimit<4096,'bounded descriptors')
    identity(gbase,glimit+1); identity(ibase,ilimit+1)
    data['gdt']=physical('gdt',gbase,glimit+1)
    data['idt']=physical('idt',ibase,ilimit+1)
    validate_gdt_storage(data, hw, symbols, initial=initial)
    if not initial:
        base=symbols['f3_context']['address']
        for slot,name,offset in ((3,'normal_tss',40),(4,'emergency_tss',144)):
            raw=data['gdt'][slot*8:slot*8+8]
            tbase=int.from_bytes(raw[2:4],'little')|raw[4]<<16|raw[7]<<24
            need(tbase==base+offset,'actual descriptor TSS base')
            identity(tbase,104)
            data[name]=physical(name,tbase,104)
        need(data['normal_tss']==tss(esp0=0x07c05000,ss0=16),'exact normal TSS/IO bitmap denial')
        need(data['emergency_tss']==tss(esp0=0x07c0a000,ss0=16,cr3=hw['CR3'],eip=symbols['f3_emergency_entry']['address'],eflags=2,esp=0x07c0a000,es=16,cs=8,ss=16,ds=16,fs=16,gs=16),'unchanged emergency TSS')
        for vector in range(32):
            gate=data['idt'][8*vector:8*vector+8]
            if vector==8:
                need(gate==bytes.fromhex('0000200000850000'),'unchanged DF task gate')
            else:
                low,selector,zero,attrs,high=struct.unpack('<HHBBH',gate)
                need(low|(high<<16)==symbols['f5_exc_'+str(vector)]['address'] and selector==8 and zero==0 and attrs==0x8e,'F5 DPL0 gate '+str(vector))
        text=(root/(label+'_hardware.txt')).read_text(encoding='ascii')
        match=re.search(r'\bTR\s*=0018\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
        need(match and int(match[1],16)==base+40 and int(match[2],16)==103 and int(match[3],16)&0xff00==0x8900,'live cached TSS base/limit/type')
    return {'data':data,'owner':owner,'leases':leases,'directory':directory,'tables':tables,
            'stats':allocator_stats(data['allocator'],layout),'state':data['state'][0]}


def validate_guest(root,row,layout,symbols):
    need(row['overall']=='PASS' and row['capture_complete'] is True and row['hardware_cpl3'] is True
         and row['owned_qemu_exited'] is True and type(row['owned_pid']) is int and row['owned_pid']>0
         and type(row['qemu_exit']) is int and row['qemu_exit_before_cleanup'] is None
         and row['cleanup_errors']==[] and row['debugger_mutations']==[],'incomplete guest/process cleanup')
    need(type(row['checks']) is list and row['checks'] and all(c['pass'] is True for c in row['checks']),'empty/failed checks')
    verify_pins(root,row['frozen_bytes'],('guest_report.json',))
    scenario=row['scenario_integer']; entry=0x40000100+(scenario-1)*64
    need(type(scenario) is int and 1<=scenario<=6 and row['scenario']==IDENTITIES[scenario-1],'guest scenario')
    transport=Transport(root,row)
    addresses=(symbols['f5_fixture_initial']['address'],symbols['f5_before_iret']['address'],entry,
               entry+12,symbols['f5_bridge']['address'],symbols['f5_terminal']['address'])
    cp={label:transport.checkpoint(label,address,3 if label in ('user_entry','before_fault') else 0)
        for label,address in zip(LABELS,addresses)}
    need(row['snapshots']=={label:strict_json(root/(label+'_capture.json')) for label in ('initial','before_iret','terminal')},'row snapshot linkage')
    need({p.name.removesuffix('_capture.json') for p in root.glob('*_capture.json')}=={'initial','before_iret','terminal'},'snapshot membership')
    need(type(row['ram_mib']) is int and row['ram_mib'] in RAMS,'RAM identity')
    initial=snapshot(root,'initial',cp['initial'][1],layout,symbols,transport,True)
    before=snapshot(root,'before_iret',cp['before_iret'][1],layout,symbols,transport)
    final=snapshot(root,'terminal',cp['terminal'][1],layout,symbols,transport)
    need(initial['state']==0 and before['state']==2 and final['state']==3,'DORMANT->Sealed->Terminal state')
    for i,(a,b) in enumerate(zip(initial['directory'],before['directory'])):
        if i!=256:
            need((a^b)&~0x20==0,'initial supervisor directory preservation')
    for i,table in initial['tables'].items():
        need(i in before['tables'],'initial table lost')
        for j,(a,b) in enumerate(zip(table,before['tables'][i])):
            if i==31 and j<10:
                continue
            need((a^b)&~0x60==0,'initial supervisor PTE preservation')
    need(set(before['tables'])==set(initial['tables'])|{256},'only retained arena table added')
    need(initial['stats']['free_frames']-before['stats']['free_frames']==12
         and before['stats']['allocated_frames']-initial['stats']['allocated_frames']==12
         and initial['stats']['reserved_frames']==before['stats']['reserved_frames'],'actual twelve-frame capacity delta')
    oldcap=before['owner']['capacity_before']; newcap=before['owner']['capacity_after']
    need(oldcap==(initial['stats']['free_frames'],initial['stats']['allocated_frames'],initial['stats']['reserved_frames'])
         and newcap==(before['stats']['free_frames'],before['stats']['allocated_frames'],before['stats']['reserved_frames']),'owner raw capacity diagnostics')
    cap=before['owner']['arena_capture']
    need(cap[:5]==(0,12,before['leases']['payload']['addr'],before['leases']['user_stack']['addr'],before['leases']['arena_table']['addr'])
         and cap[14:16]==(1,2) and cap[11]-cap[12]==2 and cap[12:14]==newcap[:2],'sealed owner arena diagnostics')
    need(initial['data']['idt'][256:]==before['data']['idt'][256:],'inherited external IDT gates')
    need(before['stats']==final['stats'] and before['leases']==final['leases'],'terminal retained capacity/identities')
    for n in ('owner','allocator','normal_tss','emergency_tss','gdt','idt','f3_context','f5_expect'):
        need(before['data'][n]==final['data'][n],'retained invariant '+n)
    need(before['data']['f5_record']==bytes(256) and before['data']['f5_latch']==bytes(4)
         and final['data']['f5_latch']==struct.pack('<I',1),'one-shot report latch')
    need(before['data']['stack']==bytes(4096) and final['data']['stack']==bytes(4092)+struct.pack('<I',0x5a17c0de),'full USER stack cookie only')
    need(before['tables'].keys()==final['tables'].keys(),'paging inventory drift')
    for old,new,mask in ((before['directory'],final['directory'],0x20),
                         *((before['tables'][i],final['tables'][i],0x60) for i in before['tables'])):
        need(all((a^b)&~mask==0 for a,b in zip(old,new)),'non-A/D page-table mutation')
    need(len({hw['CR3'] for _,hw in cp.values()})==1,'CR3 checkpoint drift')
    need(len({(hw['CR0'],hw['CR4']) for _,hw in cp.values()})==1,'CPU protection-control drift')
    for label,(_,hw) in cp.items():
        if label=='initial':
            continue
        need(hw['GDT']==cp['before_iret'][1]['GDT'] and hw['IDT']==cp['before_iret'][1]['IDT'] and hw['TR']==24,'retained descriptor caches')
        cached_context((root/(label+'_hardware.txt')).read_bytes(),user=label in ('user_entry','before_fault'),
                       user_data=label=='before_iret',tss_base=symbols['f3_context']['address']+40)
    for label in ('user_entry','before_fault'):
        regs,hw=cp[label]
        need(regs['cs']==0x2b and regs['ss']==0x33 and regs['esp']==0x40400000
             and all(regs[n]==0x33 for n in ('ds','es','fs','gs')),'actual USER selectors/stack')
    for label in ('before_iret','terminal'):
        regs=cp[label][0]
        need(regs['cs']==8 and regs['ss']==16 and regs['eflags']&0x600==0,'live kernel selectors/flags')
    need(all(cp['before_iret'][0][n]==0x33 for n in ('ds','es','fs','gs'))
         and all(cp['terminal'][0][n]==16 for n in ('ds','es','fs','gs')),'live selector transition')
    user=cp['user_entry'][0]; fault=cp['before_fault'][0]; bridge=cp['bridge'][0]
    need(user['eflags']==2 and fault['eflags'] in (0x446,0x456) and fault['eax']==0x2b
         and fault['ebx']==0x5a17c0de,'entry/prefault flags and sentinels')
    need(transport.virtual('iret_words.bin',cp['before_iret'][0]['esp'],20)==struct.pack('<5I',entry,0x2b,2,0x40400000,0x33),'five actual IRETD operands')
    need(transport.virtual('fault_instruction.bin',entry+12,len(bytes.fromhex(SNIPPETS[scenario-1]))-12)==bytes.fromhex(SNIPPETS[scenario-1])[12:],'fault opcode/fallback bytes')
    frame_raw=transport.virtual('mandatory_frame.bin',0x07c04fb4,76)
    need(bridge['esp']==0x07c04f9c and bridge['esp']%16==12
         and u32(transport.virtual('bridge_call.bin',bridge['esp'],8),4)==0x07c04fb4,'raw C-call frame argument/alignment')
    need(bridge['cs']==8 and bridge['ss']==16 and all(bridge[n]==16 for n in ('ds','es','fs','gs'))
         and bridge['eflags']&0x600==0,'live bridge normalization')
    record,frame=records(final['data']['f5_record'],scenario,cp['terminal'][1]['CR3'],fault['eflags'])
    need(final['data']['f5_record'][64:140]==frame_raw,'record vs actual mandatory frame')
    need(u32(final['data']['f5_record'],142)==symbols['f5_gdt']['address'],'record GDTR base')
    for index,name in ((4,'edi'),(5,'esi'),(6,'ebp'),(8,'ebx'),(9,'edx'),(10,'ecx'),(11,'eax')):
        need(frame[index]==fault[name],'actual saved GPR '+name)
    hw=cp['terminal'][1]
    need(record[5:9]==(hw['CR0'],hw['CR2'],hw['CR3'],hw['CR4']),'record vs actual terminal controls')
    expect=struct.unpack('<7I',final['data']['f5_expect'])
    vector,error,cr2=FAULTS[scenario-1]
    need(expect==(scenario,vector,error,entry+12,cr2 or 0,hw['CR3'],entry),'kernel-owned expectation')
    trace=(root/'qemu.log').read_bytes()
    events=re.findall(rb'v=([0-9a-f]+) e=([0-9a-f]+) i=([01]) cpl=3 IP=002b:([0-9a-f]+)',trace)
    need(len(events)==1 and tuple(int(x,16) for x in events[0])==(vector,error,0,entry+12),'unique actual CPL3 exception trace')
    need(b'Triple fault' not in trace and not re.search(rb'v=08\b',trace),'double/triple fault')
    serial=(root/'serial.txt').read_bytes(); marker=f'F5 {chr(64+scenario)} PASS CPL3 terminal\n'.encode()
    need(serial.endswith(marker) and serial.count(marker)==1 and serial.count(b'F5 ')==1
         and b'rosti>' not in serial and b'FAIL CPL3' not in serial,'unique kernel terminal marker/no shell return')
    need((root/'serial_before_stable.bin').read_bytes()==serial
         and (root/'trace_before_stable.bin').read_bytes()==trace,'stable output/exception history')
    stable_raw=(root/'stable_terminal_hardware.txt').read_bytes(); stable=hardware(stable_raw)
    need(any(e['command']=='human-monitor-command' and e['reply']==stable_raw.decode('ascii') for e in transport.q),'stable raw hardware binding')
    cached_context(stable_raw,tss_base=symbols['f3_context']['address']+40)
    need(stable['CR0']==hw['CR0'] and stable['CR4']==hw['CR4'] and stable['GDT']==hw['GDT'] and stable['IDT']==hw['IDT'],'stable protection/descriptor controls')
    need(stable['CPL']==0 and stable['HLT']==1 and stable['EFL']&0x600==0
         and stable['CR3']==hw['CR3'] and stable['EIP']==symbols['f5_terminal']['address']+2,'stable HLT IF0/nonresumption')
    need(transport.virtual('stable_halt.bin',stable['EIP']-1,3)==b'\xf4\xeb\xfd','CLI/HLT back-edge bytes')
    need(transport.virtual('stable_record.bin',symbols['f5_record']['address'],256)==final['data']['f5_record'],'stable record')
    need(type(row['stable_interval_seconds']) in (int,float) and row['stable_interval_seconds']>=0.2,'bounded stable interval')
    transport.finish(addresses)
    return True


def validate(path,expected_source=None,check_current=False,require_full=True):
    root=Path(path).resolve()
    if root.is_file():
        need(root.name=='report.json','aggregate filename')
        root=root.parent
    report=strict_json(root/'report.json')
    need(report['schema']=='rosti.f5-cpl3-matrix.v1' and report['overall']=='PASS'
         and type(report['driver_exit']) is int and report['driver_exit']==0
         and report['not_canonical_acceptance'] is True,'aggregate outcome')
    selected=report['selected_scenario']
    need(report['full_f5_matrix'] is (selected is None),'full/component mismatch')
    need(not require_full or selected is None,'partial component is not full twelve-row proof')
    validate_matrix_rows(report['guests'],selected)
    verify_pins(root,report['frozen_bytes'],('report.json',))
    before=strict_json(root/'source_before.json'); after=strict_json(root/'source_after.json')
    need(type(before) is dict and bool(before) and before==after and report['source_freeze_stable'] is True,'source freeze')
    if expected_source is not None:
        need(before==expected_source,'canonical source substitution')
    need(tree_pins(root/'source')==before,'retained source membership/hashes')
    check_authority(root/'source')
    for name,digest in before.items():
        if check_current:
            need(sha(local(ROOT,name).read_bytes())==digest,'current source drift '+name)
    for name in ('scripts/f5_cpl3_guest.py','scripts/f5_cpl3_evidence.py','scripts/f5_terminal_audit.py'):
        need(name in before,'missing driver/validator/audit freeze')
        need(sha(local(ROOT,name).read_bytes())==before[name],'reader/tool source identity '+name)
    originals={n:local(root/'source',n).read_bytes() for n in before}
    # Import only after pinning executing helper bytes; no guest is launched here.
    from f5_cpl3_guest import transformations
    validate_audit(root/'production/emitted',root/'production/kernel.elf',root/'authority/f2_before_macro_01.elf')
    tools=strict_json(root/'toolchain.json')
    need(sha((root/'toolchain/qemu-system-i386.exe').read_bytes())==tools['qemu_sha256']
         and sha((root/'firmware/bios-256k.bin').read_bytes())==tools['bios_sha256'],'toolchain/firmware bytes')
    if check_current:
        need(sha(Path(tools['qemu_path']).read_bytes())==tools['qemu_sha256'],'current emulator drift')
    scenarios=range(1,7) if selected is None else (selected,)
    need(set(report['builds'])=={chr(64+s) for s in scenarios},'build scenario membership')
    layouts={}; symbols={}
    for scenario in scenarios:
        letter=chr(64+scenario); folder=root/'builds'/letter; build=report['builds'][letter]
        need(build['scenario_integer']==scenario and type(build['build_exit']) is int and build['build_exit']==0,'fixture build outcome')
        stage=Path(build['owned_stage'])
        need(stage.is_absolute() and stage.parent==ROOT/'dist' and stage.name.startswith('f5_'),'owned short fixture stage identity')
        expected=['cargo','+nightly','build','--locked','--manifest-path',str(stage/'s/Cargo.toml'),'--target-dir',str(stage/'b')]
        need(build['build_command']==expected and build['build_cwd']==str(stage/'s'),'exact staged build operands')
        transformed=transformations(originals,scenario)
        changes={n:r for n,r in transformed.items() if r!=originals[n]}
        manifest=strict_json(folder/'transforms.json')
        need(set(manifest)==set(changes)=={'src/main.rs'},'fixture transform membership')
        for n,raw in changes.items():
            need(local(folder/'transformed',n).read_bytes()==raw
                 and manifest[n]=={'original_sha256':before[n],'transformed_sha256':sha(raw)},'fixture source pin/stripping')
        elf=folder/'kernel.elf'
        need(sha(elf.read_bytes())==build['kernel_sha256'],'fixture ELF pin')
        validate_audit(folder/'emitted',elf,root/'authority/f2_before_macro_01.elf')
        layouts[scenario]=extract(elf); symbols[scenario]=elf_symbols(elf)
        need(layouts[scenario]==strict_json(folder/'target_layout.json')
             and symbols[scenario]==strict_json(folder/'symbols.json'),'exact ELF DWARF/symbol readback')
    for row in report['guests']:
        scenario=row['scenario_integer']; ram=row['ram_mib']; letter=chr(64+scenario)
        name=IDENTITIES[scenario-1]+'_'+str(ram)
        need(row['report']==name+'/guest_report.json','invocation-owned immediate child')
        child=strict_json(local(root,row['report']))
        need(all(row[k]==child[k] for k in ('scenario','scenario_integer','ram_mib','overall','kernel_sha256')),'aggregate-child linkage')
        need(child['kernel_sha256']==report['builds'][letter]['kernel_sha256'],'child fixture ELF linkage')
        command=child['command']; folder=root/name
        expected_flags={'-bios':str(root/'firmware/bios-256k.bin'),'-kernel':str(root/'builds'/letter/'kernel.elf'),
            '-cpu':'qemu32','-m':str(ram),'-smp':'1','-machine':'pc','-display':'none','-nic':'none',
            '-monitor':'none','-serial':'file:'+str(folder/'serial.txt'),'-d':'int,guest_errors','-D':str(folder/'qemu.log')}
        need(type(command) is list and command[0]==tools['qemu_path'],'QEMU executable identity')
        for flag,value in expected_flags.items():
            need(command.count(flag)==1 and command[command.index(flag)+1]==value,'exact QEMU operand '+flag)
        allowed=set(expected_flags)|{'-no-reboot','-S','-gdb','-qmp'}
        need(all(not arg.startswith('-') or arg in allowed for arg in command[1:]),'unexpected QEMU option')
        need(command.count('-S')==command.count('-no-reboot')==1,'start-paused/no-reboot profile')
        for flag,pattern in (('-gdb',r'tcp:127\.0\.0\.1:[0-9]+'),('-qmp',r'tcp:127\.0\.0\.1:[0-9]+,server=on,wait=off')):
            need(command.count(flag)==1 and re.fullmatch(pattern,command[command.index(flag)+1]),'loopback transport identity')
        expected_command=[tools['qemu_path'],'-bios',expected_flags['-bios'],'-kernel',expected_flags['-kernel'],
            '-cpu','qemu32','-m',str(ram),'-smp','1','-machine','pc','-display','none','-nic','none',
            '-monitor','none','-no-reboot','-serial',expected_flags['-serial'],'-d','int,guest_errors',
            '-D',expected_flags['-D'],'-S','-gdb',command[command.index('-gdb')+1],
            '-qmp',command[command.index('-qmp')+1]]
        need(command==expected_command,'exact complete QEMU argv')
        gport=int(command[command.index('-gdb')+1].rsplit(':',1)[1])
        qport=int(command[command.index('-qmp')+1].split(':')[-1].split(',')[0])
        need(0<gport<=65535 and 0<qport<=65535 and gport!=qport,'distinct loopback ports')
        validate_guest(folder,child,layouts[scenario],symbols[scenario])
    need(report['checks'] and all(c['pass'] is True for c in report['checks']),'aggregate check rows')
    return {str(root/n):digest for n,digest in report['frozen_bytes'].items()}|{str(root/'report.json'):sha((root/'report.json').read_bytes())}


def validate_aggregate(path,expected_source):
    need(type(expected_source) is dict and bool(expected_source),'canonical source snapshot required')
    pins=validate(path,expected_source,require_full=True)
    return {'overall':'PASS','scenario_count':12,'pins':pins}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('report',type=Path)
    parser.add_argument('--check-current-source',action='store_true')
    parser.add_argument('--allow-component',action='store_true')
    args=parser.parse_args(argv)
    try:
        pins=validate(args.report,check_current=args.check_current_source,require_full=not args.allow_component)
        print(json.dumps({'overall':'PASS','validated_pins':len(pins),'canonical_acceptance':False}))
        return 0
    except Exception as exc:
        print(json.dumps({'overall':'FAIL','error':repr(exc)}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
