#![no_std]
#![no_main]

use core::arch::{global_asm, naked_asm};
use core::panic::PanicInfo;

// Link the production source unchanged. Only this standalone fixture changes ELF entry.
global_asm!(include_str!("../../src/boot.s"), options(att_syntax));
global_asm!(
    r#"
.section .data
b13_case: .long 0
.section .text
.global b13_handoff
b13_handoff:
    cli
    mov $0x90000, %esp
    add b13_case, %esp
    mov $0x2badb002, %eax
    mov $0x12345678, %ebx
    std
    // STI's interrupt shadow covers the JMP; _start must execute CLI first.
    sti
    jmp _start
.global b13_sink
b13_sink:
    mov 4(%esp), %eax
    xor 8(%esp), %eax
    ret
"#,
    options(att_syntax)
);

// No compiler prologue may hide the actual C-ABI entry stack or flags.
#[unsafe(naked)]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn kernel_main(_magic: u32, _info: *const u8) -> ! {
    naked_asm!(
        r#"
    mov %esp, %ecx
    and $15, %ecx
    cmp $12, %ecx
    jne 2f
    pushfl
    pop %ecx
    test $0x600, %ecx
    jne 2f
    cmpl $0x2badb002, 4(%esp)
    jne 2f
    cmpl $0x12345678, 8(%esp)
    jne 2f
    cmp $0x2badb002, %eax
    jne 2f
    cmp $0x12345678, %ebx
    jne 2f
    mov $0xe9, %dx
    mov $80, %al
    out %al, %dx
    incl b13_case
    cmpl $16, b13_case
    jb b13_handoff
    mov $0xf4, %dx
    mov $0x10, %eax
    out %eax, %dx
1:  cli
    hlt
    jmp 1b
2:  mov $0xe9, %dx
    mov $70, %al
    out %al, %dx
    mov $0xf4, %dx
    mov $0x11, %eax
    out %eax, %dx
    jmp 1b
"#,
        options(att_syntax)
    );
}

unsafe extern "C" {
    fn b13_sink(a: u32, b: u32) -> u32;
}

// Retain an ordinary compiler-generated, non-tail extern-C call for ABI inspection.
#[unsafe(no_mangle)]
#[inline(never)]
pub unsafe extern "C" fn b13_abi_probe(a: u32, b: u32) -> u32 {
    b13_sink(a, b).wrapping_add(1)
}

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    loop {
        core::hint::spin_loop();
    }
}
