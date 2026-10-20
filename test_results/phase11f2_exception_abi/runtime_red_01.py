"""Runtime RED: fatal #UD with legal null data selectors on Ring0 entry.
Copies accepted production inputs and injects only a disposable trigger.
No canonical source/build output is modified. Expected Python exit1 is evidence,
not GREEN. A compiler failure is never reported as runtime RED.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'runtime_red_01'
OUT.mkdir(exist_ok=False)
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
recovery = json.loads((OUT.parent / 'recovery_01.json').read_text())
source_hashes = recovery['accepted_source_sha256']
report = {'status': 'SETUP', 'runtime_executed': False, 'hardware_cpl3': False}
asm = b'''\n// F2_RED_DISPOSABLE_BEGIN\nglobal_asm!(r#"
.section .text
.global f2_red_trigger
.type f2_red_trigger,@function
f2_red_trigger:
    cli
    xor %eax,%eax
    mov %ax,%ds
    mov %ax,%es
    mov %ax,%fs
    mov %ax,%gs
    mov $0x11112222,%eax
    mov $0x33334444,%ebx
    mov $0x55556666,%ecx
    mov $0x77778888,%edx
    mov $0x9999aaaa,%esi
    mov $0xbbbbcccc,%edi
    mov $0xddddeeee,%ebp
    std
.global f2_red_fault_site
f2_red_fault_site:
    ud2
    cli
1:  hlt
    jmp 1b
"#, options(att_syntax));
unsafe extern "C" { fn f2_red_trigger() -> !; }
// F2_RED_DISPOSABLE_END\n'''
call = b'''    // F2_RED_CALL_BEGIN\n    io::serial::puts("F2RED TRIGGER Ring0 UD null-segments DF1\\n");\n    unsafe { f2_red_trigger(); }\n    // F2_RED_CALL_END\n'''
with tempfile.TemporaryDirectory(prefix='f2red_', dir=ROOT / 'dist') as temp:
    stage = Path(temp)
    source = stage / 'source'
    source.mkdir()
    copied = {}
    for name, digest in source_hashes.items():
        if name.startswith(('src/', 'crates/', 'system/')) or name in ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', 'target.json', 'linker.ld', '.cargo/config.toml'):
            raw = (ROOT / name).read_bytes()
            if sha(raw) != digest:
                raise RuntimeError('accepted source drift: ' + name)
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            copied[name] = digest
    main = source / 'src/main.rs'
    original = main.read_bytes()
    anchor = b'    // stub: enable ps2 & interrupts'
    if original.count(anchor) != 1:
        raise RuntimeError('nonunique trigger anchor')
    changed = original.replace(anchor, call + anchor) + asm
    if changed.replace(call, b'', 1).replace(asm, b'', 1) != original:
        raise RuntimeError('body stripping mismatch')
    main.write_bytes(changed)
    command = ['cargo', '+nightly', 'build', '--locked', '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(stage / 'build')]
    with (OUT / 'build.log').open('wb') as log:
        result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    report.update(build_command=command, build_cwd=str(source), build_exit=result.returncode, copied=copied, original_main_sha256=sha(original), injected_main_sha256=sha(changed), asm_sha256=sha(asm), call_sha256=sha(call))
    save('report.json', report)
    if result.returncode != 0:
        raise RuntimeError('COMPILE FAILURE, not runtime RED')
    kernel = stage / 'build/target/debug/kernel'
    retained = OUT / 'kernel.elf'
    shutil.copyfile(kernel, retained)
    qemu = Path('C:/Program Files/qemu/qemu-system-i386.exe')
    argv = [str(qemu), '-kernel', str(kernel), '-cpu', 'qemu32', '-m', '128', '-smp', '1', '-machine', 'pc', '-display', 'none', '-nic', 'none', '-monitor', 'none', '-no-reboot', '-serial', 'file:' + str(OUT / 'serial.txt'), '-d', 'int,guest_errors', '-D', str(OUT / 'qemu.log')]
    with (OUT / 'qemu_stderr.txt').open('wb') as log:
        proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=log)
        report.update(qemu_pid=proc.pid, qemu_command=argv, runtime_executed=True, kernel_sha256=sha(retained.read_bytes()), cpu_mode='32-bit protected Ring0, non-PAE paging', trigger='legal null DS/ES/FS/GS, DF1, UD2', expected_vector=6, expected_hardware_error_code=False)
        try:
            proc.wait(timeout=8)
            report['exit_reason'] = 'QEMU spontaneous exit (no-reboot; inspect trace)'
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
            report['exit_reason'] = 'owned timeout kill/wait after bounded observation'
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
    text = (OUT / 'serial.txt').read_text(errors='replace')
    trace = (OUT / 'qemu.log').read_text(errors='replace')
    checks = {'trigger_reached': 'F2RED TRIGGER Ring0 UD null-segments DF1' in text, 'fatal_ud_reported': 'CPU exception vector 0x06' in text, 'no_double_fault': 'v=08' not in trace, 'no_shell_return': 'rosti>' not in text, 'owned_qemu_exited': proc.poll() is not None}
    report.update(checks=checks, qemu_exit=proc.returncode, status='PASS' if all(checks.values()) else 'RUNTIME_RED', failed_assertions=[k for k,v in checks.items() if not v])
    save('report.json', report)
    print(json.dumps({k:v for k,v in report.items() if k != 'copied'},indent=2))
    if not checks['trigger_reached']:
        raise RuntimeError('fixture failed before trigger, not valid RED')
    assert all(checks.values()), 'fatal #UD must normalize legal null data selectors before Rust: ' + ', '.join(report['failed_assertions'])
