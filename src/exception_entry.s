# F2 fatal-only ABI. All stack-relative memory uses SS, including null-DS entry.
.section .text
.macro F2_STUB vector, error=0, unsupported=0
.global f2_exc_\vector
.type f2_exc_\vector,@function
f2_exc_\vector:
    cli
.if \unsupported
    cld
    mov $0x10,%eax
    mov %ax,%ds
    mov %ax,%es
    mov %ax,%fs
    mov %ax,%gs
    and $-16,%esp
    sub $12,%esp
    push $\vector
    call f2_unsupported
    jmp f2_terminal
.else
.if !\error
    push $0
.endif
    push $\vector
    jmp f2_exception_common
.endif
.size f2_exc_\vector,.-f2_exc_\vector
.endm
F2_STUB 0
F2_STUB 1
F2_STUB 2
F2_STUB 3
F2_STUB 4
F2_STUB 5
F2_STUB 6
F2_STUB 7
F2_STUB 8,1
F2_STUB 9
F2_STUB 10,1
F2_STUB 11,1
F2_STUB 12,1
F2_STUB 13,1
F2_STUB 14,1
F2_STUB 15
F2_STUB 16
F2_STUB 17,1
F2_STUB 18
F2_STUB 19
F2_STUB 20
F2_STUB 21,0,1
F2_STUB 22
F2_STUB 23
F2_STUB 24
F2_STUB 25
F2_STUB 26
F2_STUB 27
F2_STUB 28
F2_STUB 29,0,1
F2_STUB 30,0,1
F2_STUB 31

.global f2_exception_common
.type f2_exception_common,@function
f2_exception_common:
    cli
    cld
    pushal
    xor %eax,%eax
    mov %ds,%ax
    push %eax
    mov %es,%ax
    push %eax
    mov %fs,%ax
    push %eax
    mov %gs,%ax
    push %eax
    mov $0x10,%eax
    mov %ax,%ds
    mov %ax,%es
    mov %ax,%fs
    mov %ax,%gs
.global f2_normalized
f2_normalized:
    mov %esp,%eax
    and $-16,%esp
    sub $12,%esp
    push %eax
    call f2_fatal
.global f2_terminal
f2_terminal:
    cli
1:  hlt
    jmp 1b
.size f2_exception_common,.-f2_exception_common

# Bind the PUSHAD/segment construction to the Rust compile-time layout.
.if {frame_size} != 68
.error "F2 frame size mismatch"
.endif
.if {vector_offset} != 48
.error "F2 normalized vector offset mismatch"
.endif
.section .rodata
.balign 4
.global f2_exception_entries
f2_exception_entries:
.long f2_exc_0,f2_exc_1,f2_exc_2,f2_exc_3,f2_exc_4,f2_exc_5,f2_exc_6,f2_exc_7
.long f2_exc_8,f2_exc_9,f2_exc_10,f2_exc_11,f2_exc_12,f2_exc_13,f2_exc_14,f2_exc_15
.long f2_exc_16,f2_exc_17,f2_exc_18,f2_exc_19,f2_exc_20,f2_exc_21,f2_exc_22,f2_exc_23
.long f2_exc_24,f2_exc_25,f2_exc_26,f2_exc_27,f2_exc_28,f2_exc_29,f2_exc_30,f2_exc_31
