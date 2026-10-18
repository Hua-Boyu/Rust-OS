"""Measure emitted target FrameAllocator DWARF size after production restoration."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
kernel=ROOT/'target/target/debug/kernel'
expected=json.loads((OUT/'candidate_checks.json').read_text())['kernel_sha256']
digest=hashlib.sha256(kernel.read_bytes()).hexdigest()
if digest!=expected: raise RuntimeError('production kernel not restored; do not measure fixture')
command=['wsl','--exec','readelf','--debug-dump=info','/mnt/c/Users/iamsv/Documents/Rust-OS/target/target/debug/kernel']
r=subprocess.run(command,capture_output=True,text=True,check=True,timeout=120)
sizes=[]; snippets=[]
for block in re.split(r'(?m)^\s*<\d+><[0-9a-f]+>:',r.stdout):
    if '(DW_TAG_structure_type)' in block and re.search(r'DW_AT_name[^\n]*:\s*FrameAllocator\s*$',block,re.M):
        match=re.search(r'DW_AT_byte_size\s*:\s*(0x[0-9a-f]+|[0-9]+)',block)
        if match:
            sizes.append(int(match.group(1),0)); snippets.append(block.splitlines()[:12])
if not sizes or len(set(sizes))!=1: raise RuntimeError('target layout missing or ambiguous: '+str(sizes))
size=sizes[0]
assert size<=320*1024
assert hashlib.sha256(kernel.read_bytes()).hexdigest()==digest
record={'kernel_sha256':digest,'command':command,'actual_exit':r.returncode,'FrameAllocator_target_bytes':size,'FrameAllocator_host_bytes':311560,'FRAME_ALLOC_target_mutex_owner_bytes':311532,'DWARF_matches':len(sizes),'snippets':snippets,'limitation':'Type layout, not runtime stack high-water. Production allocator is const static.'}
output=OUT/'target_layout.json'
if output.exists(): raise RuntimeError('refuse evidence overwrite')
output.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
