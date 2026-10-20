"""Runtime RED: observe actual live segment state after LLVM ISR CLD.
The first oracle passed; this one checks missing kernel-selector normalization
at the first ordinary function call inside the real baseline #UD handler.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from b13_entry_inject import Gdb, QEMU, elf_symbols
from f1_retained_guest import port, connect
from f1_capture import Qmp
OUT = Path(__file__).resolve().parent / 'runtime_red_02'
OUT.mkdir(exist_ok=False)
kernel = OUT.parent / 'runtime_red_01/kernel.elf'
previous = json.loads((OUT.parent / 'runtime_red_01/report.json').read_text())
if hashlib.sha256(kernel.read_bytes()).hexdigest() != previous['kernel_sha256'] or previous['build_exit'] != 0:
    raise RuntimeError('baseline build identity')
symbols = elf_symbols(kernel)
name, symbol = next((n,v) for n,v in symbols.items() if n.endswith('9isr_exc06'))
objdump = 'C:/Users/iamsv/.rustup/toolchains/nightly-2025-02-17-x86_64-pc-windows-msvc/lib/rustlib/x86_64-pc-windows-msvc/bin/llvm-objdump.exe'
dis = subprocess.check_output([objdump, '-d', '--disassemble-symbols='+name, str(kernel)], text=True)
(OUT / 'isr_disassembly.txt').write_text(dis)
lines = dis.splitlines()
cld_index = next(i for i,line in enumerate(lines) if re.search(r'\bcld\b',line))
next_line = lines[cld_index+1]
address = int(re.match(r'\s*([0-9a-f]+):',next_line).group(1),16)
if 'call' not in next_line:
    raise RuntimeError('unexpected compiler prologue; inspect before adapting')
gp, qp = port(), port()
argv = [str(QEMU), '-kernel', str(kernel), '-cpu', 'qemu32', '-m', '128', '-smp', '1', '-machine', 'pc', '-display', 'none', '-nic', 'none', '-monitor', 'none', '-no-reboot', '-serial', 'file:'+str(OUT/'serial.txt'), '-d','int,guest_errors','-D',str(OUT/'qemu.log'),'-S','-gdb',f'tcp:127.0.0.1:{gp}','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off']
report = {'status':'SETUP','build_exit':previous['build_exit'],'kernel_sha256':previous['kernel_sha256'],'command':argv,'entry_symbol':name,'entry_address':symbol['address'],'post_cld_pre_call_address':address,'oracle':'live DS/ES/FS/GS must be normalized to kernel data0x10 before calling Rust/C helpers','cpu_mode':'32-bit protected Ring0; no CPL3'}
proc = None
sockets = []
try:
    with (OUT/'qemu_stderr.txt').open('wb') as log:
        proc = subprocess.Popen(argv,stdout=subprocess.DEVNULL,stderr=log)
    report['owned_pid']=proc.pid
    deadline=time.monotonic()+20
    gs,qs=connect(gp,proc,deadline),connect(qp,proc,deadline)
    sockets=[gs,qs]
    gs.settimeout(20)
    qs.settimeout(10)
    gdb,qmp=Gdb(gs),Qmp(qs)
    gdb.command('?')
    if gdb.command(f'Z1,{address:x},1')!='OK':
        raise RuntimeError('breakpoint rejected')
    report['stop_reply']=gdb.command('c')
    fields,hw=qmp.hardware()
    (OUT/'hardware.txt').write_text(hw)
    raw=gdb.command('g')
    (OUT/'register_packet.txt').write_text(raw)
    names=('eax','ecx','edx','ebx','esp','ebp','esi','edi','eip','eflags','cs','ss','ds','es','fs','gs')
    regs=dict(zip(names,struct.unpack_from('<16I',bytes.fromhex(raw))))
    report.update(registers=regs,hardware=fields,query_status=qmp.call('query-status'))
    serial=(OUT/'serial.txt').read_text(errors='replace')
    report['checks']={'trigger_reached':'F2RED TRIGGER Ring0 UD null-segments DF1' in serial,'actual_UD_handler_post_cld':regs['eip']==address,'saved_CS_origin_ring0':regs['cs']&3==0,'DF_clear_before_call':regs['eflags']&0x400==0,'kernel_data_selectors_before_call':all(regs[x]==0x10 for x in ('ds','es','fs','gs'))}
    report['status']='PASS' if all(report['checks'].values()) else 'RUNTIME_RED'
finally:
    if proc is not None:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        report.update(qemu_exit=proc.returncode,owned_qemu_exited=proc.poll() is not None)
    for sock in sockets:
        sock.close()
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
assert report['checks']['trigger_reached'] and report['checks']['actual_UD_handler_post_cld'], 'invalid RED setup'
assert report['checks']['kernel_data_selectors_before_call'], 'exception entry must install kernel DS/ES/FS/GS before ordinary Rust/C calls; observed '+str({x:regs[x] for x in ('ds','es','fs','gs')})
