"""Read existing ELF section helper and selected disassembly; no builds/guests."""
from pathlib import Path
import hashlib, importlib.util, json, re, subprocess, sys
if sys.flags.optimize: raise RuntimeError('optimized evidence checks refused')
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('historical_resources',ROOT/'test_results/phase11/verify_checkpoint.py')
helpers=importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
kernel=ROOT/'target/target/debug/kernel'
current=helpers.sections(kernel.read_bytes()); baseline=helpers.sections((OUT/'baseline_kernel.elf').read_bytes())
report={'current':current,'baseline':baseline,'delta':{key:current[key]-baseline[key] for key in ['file_bytes','allocated_bytes','initialized_bytes','static_span_bytes']}}
report['section_delta']={name:current['allocated_sections'].get(name,{}).get('bytes',0)-baseline['allocated_sections'].get(name,{}).get('bytes',0) for name in sorted(set(current['allocated_sections'])|set(baseline['allocated_sections']))}
report['linker_limit']={'origin':0x200000,'bytes':4*1024*1024,'fits':current['static_span_bytes']<=4*1024*1024}
assert report['linker_limit']['fits']
path='/mnt/c/Users/iamsv/Documents/Rust-OS/target/target/debug/kernel'
nm=subprocess.run(['wsl','--exec','nm','-S','-C',path],capture_output=True,text=True,check=True,timeout=90)
report['target_owner_symbols']=[line for line in nm.stdout.splitlines() if any(x in line for x in ['memory::FRAME_ALLOC','stack_bottom','stack_top','KERNEL_START','KERNEL_END'])]
command=['wsl','--exec','objdump','-d','-C','--no-show-raw-insn',path]
r=subprocess.run(command,capture_output=True,text=True,check=True,timeout=90)
wanted=['kernel::memory::prepare','<kernel::memory::frame::FrameAllocator>::init','<kernel::memory::frame::FrameAllocator>::allocate_stamped','<kernel::memory::frame::FrameAllocator>::release_by_address','<kernel::memory::frame::FrameAllocator>::issue_allocation_id']
bodies={}; name=None
for line in r.stdout.splitlines():
    header=re.fullmatch(r'[0-9a-f]+ <(.+)>:',line)
    if header:
        name=header.group(1)
        if name in wanted: bodies[name]=[]
    elif name in wanted: bodies[name].append(line)
report['disassembly_command']=command
report['direct_frames']={}
for name,body in bodies.items():
    text='\n'.join(body)
    values=[int(x,16) for x in re.findall(r'\bsub\s+\$0x([0-9a-f]+),%esp',text)]
    report['direct_frames'][name]={'largest_single_esp_subtract':max(values,default=0),'stack_probe_reference':bool(re.search('__chkstk|__rust_probestack',text)),'prologue':body[:12]}
report['not_emitted_symbols']=[name for name in wanted if name not in bodies]
report['limitation']='Direct stack subtracts are not cumulative caller/IRQ high-water. FrameAllocator host size311560 measured separately; FRAME_ALLOC target symbol includes SpinMutex metadata. Lease-only APIs may be dead-stripped until production has ordinary lease callers.'
assert hashlib.sha256(kernel.read_bytes()).hexdigest()==current['sha256']
output=OUT/'resource_readback.json'
if output.exists(): raise RuntimeError('refuse evidence overwrite')
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
