# F5-only mechanically constrained expansion of the accepted F2 normalizer.
# Not literal source sharing: f5_entry_derivation.py validates the complete
# ordered lexical expansion against byte-pinned src/exception_entry.s.
# Both terminal aliases require separate exact linked-ELF proof.
.section .text
.macro F5_STUB vector, error=0, unsupported=0
.global f5_exc_\vector
.type f5_exc_\vector,@function
f5_exc_\vector:
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
    call f5_unsupported
    jmp f5_terminal
.else
.if !\error
    push $0
.endif
    push $\vector
    jmp f5_exception_common
.endif
.size f5_exc_\vector,.-f5_exc_\vector
.endm
F5_STUB 0
F5_STUB 1
F5_STUB 2
F5_STUB 3
F5_STUB 4
F5_STUB 5
F5_STUB 6
F5_STUB 7
F5_STUB 8,1
F5_STUB 9
F5_STUB 10,1
F5_STUB 11,1
F5_STUB 12,1
F5_STUB 13,1
F5_STUB 14,1
F5_STUB 15
F5_STUB 16
F5_STUB 17,1
F5_STUB 18
F5_STUB 19
F5_STUB 20
F5_STUB 21,0,1
F5_STUB 22
F5_STUB 23
F5_STUB 24
F5_STUB 25
F5_STUB 26
F5_STUB 27
F5_STUB 28
F5_STUB 29,0,1
F5_STUB 30,0,1
F5_STUB 31

.global f5_exception_common
.type f5_exception_common,@function
f5_exception_common:
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
.global f5_normalized
f5_normalized:
    mov %esp,%eax
    and $-16,%esp
    sub $12,%esp
    push %eax
    call f5_bridge
.global f5_entry_terminal
f5_entry_terminal:
    cli
1:  hlt
    jmp 1b
.size f5_exception_common,.-f5_exception_common

# Bind the PUSHAD/segment construction to the Rust compile-time layout,
# identical assertions to the F2 file.
.if {frame_size} != 68
.error "F5 frame size mismatch"
.endif
.if {vector_offset} != 48
.error "F5 normalized vector offset mismatch"
.endif
.section .rodata
.balign 4
.global f5_exception_entries
f5_exception_entries:
.long f5_exc_0,f5_exc_1,f5_exc_2,f5_exc_3,f5_exc_4,f5_exc_5,f5_exc_6,f5_exc_7
.long f5_exc_8,f5_exc_9,f5_exc_10,f5_exc_11,f5_exc_12,f5_exc_13,f5_exc_14,f5_exc_15
.long f5_exc_16,f5_exc_17,f5_exc_18,f5_exc_19,f5_exc_20,f5_exc_21,f5_exc_22,f5_exc_23
.long f5_exc_24,f5_exc_25,f5_exc_26,f5_exc_27,f5_exc_28,f5_exc_29,f5_exc_30,f5_exc_31
