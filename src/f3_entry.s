# F3 dedicated hardware-task entry: no F2 frame, Rust prologue, or old-stack use.
.section .text
.code32
.global f3_emergency_entry
.type f3_emergency_entry,@function
f3_emergency_entry:
    cli
    cld
    # Snapshot entry ESP before any push/pop or alignment. CPU has already
    # pushed the #DF error word on this new task's independent stack.
    mov %esp,f3_context+{observed_esp}
    xor %eax,%eax
    str %ax
    mov %eax,f3_context+{observed_tr}
    mov %cr3,%eax
    mov %eax,f3_context+{observed_cr3}
    mov %ss:(%esp),%eax
    mov %eax,f3_context+{observed_error}
    mov $f3_df_message,%esi
    mov $12,%ebx
.Lf3_character:
    mov $100000,%ecx
    mov $0x3fd,%dx
.Lf3_poll:
    in %dx,%al
    test $0x20,%al
    jnz .Lf3_send
    dec %ecx
    jnz .Lf3_poll
    # Permanently unresponsive UART: bounded refusal, still controlled HLT.
    jmp f3_emergency_terminal
.Lf3_send:
    mov (%esi),%al
    mov $0x3f8,%dx
    out %al,%dx
    inc %esi
    dec %ebx
    jnz .Lf3_character
.global f3_emergency_terminal
.type f3_emergency_terminal,@function
f3_emergency_terminal:
    cli
    cld
.Lf3_emergency_halt:
    hlt
    jmp .Lf3_emergency_halt
.size f3_emergency_terminal,.-f3_emergency_terminal
.size f3_emergency_entry,.-f3_emergency_entry

# Separate terminal roots: an installer refusal is NOT a claimed #DF.
.global f3_install_terminal
.type f3_install_terminal,@function
f3_install_terminal:
    cli
    cld
.Lf3_install_halt:
    hlt
    jmp .Lf3_install_halt
.size f3_install_terminal,.-f3_install_terminal

.global f3_ready
.type f3_ready,@function
f3_ready:
    cli
    cld
.Lf3_ready_halt:
    hlt
    jmp .Lf3_ready_halt
.size f3_ready,.-f3_ready

.section .rodata
f3_df_message:
    .ascii "F3_DF_FATAL\n"
.if .-f3_df_message != 12
.error "F3 fatal literal size mismatch"
.endif
