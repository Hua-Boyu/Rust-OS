// Multiboot constants
.set MB_ALIGN, 1<<0
.set MB_MEMINFO, 1<<1
.set MB_FLAGS, MB_ALIGN | MB_MEMINFO
.set MB_MAGIC, 0x1BADB002
.set MB_CHECKSUM, -(MB_MAGIC + MB_FLAGS)

// Multiboot header
// "aw" flags make the section SHF_ALLOC so lld places it at the start of the
// image (within the first 8192 bytes the bootloader scans) and inside the
// PT_LOAD segment.
.section .multiboot, "aw"
.align 4
.long MB_MAGIC
.long MB_FLAGS
.long MB_CHECKSUM

// Allocate 16kb stack with 16-byte alignment
.section .bss
.align 16
stack_bottom:
    .skip 16384 // 16kb stack
stack_top:

// Entry point to the kernel
.section .text
.global _start
.type _start, @function
_start:
    // multiboot specifies that we boot into 32-bit protected mode
    // Keep IRQs masked until Rust has installed the descriptor tables and PIC.
    cli
    // Multiboot leaves DF undefined; the i686 Rust/C ABI requires it clear.
    cld

    // setup the stack
    mov $stack_top, %esp

    // Provide 16-byte pre-CALL alignment (target data-layout S128), even though
    // the current soft-float i686-none compiler may use only 4-byte alignment.
    // Reserve 8 bytes before the two 4-byte args; callee entry ESP is 12 mod 16.
    sub $8, %esp

    // push multiboot info as args to kernel_main
    // reversed calling order: last argument first
    push %ebx // addr of multiboot info struct
    push %eax // multiboot magic number

    // enter the kernel
    call kernel_main

    // put the computer into a loop if kernel exits
    cli
1:
    hlt
    jmp 1b

// set size of _start symbol to current location - starting location
.size _start, . - _start
