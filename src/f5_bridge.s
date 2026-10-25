# Naked F5 bridge. No Rust prologue, calls, indirect edges or USER dereferences.
# record: 0 magic,4 scenario,8 status,12 frame,16 bridgeESP,20 CR0,24 CR2,
# 28 CR3,32 CR4,36 liveflags,40..60 CS/SS/DS/ES/FS/GS,
# 64..139 exact76 frame bytes,140 GDTR6,148 TR,152..160 ESP0/SS0/iomap.
mov edi, esp
pushfd
pop ebx
cli
mov eax, 1
xchg dword ptr [f5_latch], eax
test eax, eax
jnz f5_terminal
mov dword ptr [f5_record], 0x46354350
mov eax, dword ptr [f5_expect]
mov dword ptr [f5_record + 4], eax
cmp eax, 1
jb f5_fail_report
cmp eax, 6
ja f5_fail_report
mov dword ptr [f5_record + 16], edi
mov dword ptr [f5_record + 36], ebx
test ebx, 0x600
jnz f5_fail_report
cmp edi, 0x07c04f9c
jne f5_fail_report
mov esi, dword ptr [esp + 4]
mov dword ptr [f5_record + 12], esi
cmp esi, 0x07c04fb4
jne f5_fail_report
# Address/alignment exact before any frame read; CS low16 before tail read.
cmp word ptr [esi + 60], 0x2b
jne f5_fail_report
mov eax, dword ptr [esi + 48]
cmp eax, 6
je 2f
cmp eax, 13
je 2f
cmp eax, 14
jne f5_fail_report
2:
# Fixed19-word copy only after cross-ring origin and supported-vector checks.
cld
lea edi, [f5_record + 64]
mov ecx, 19
rep movsd
mov esi, dword ptr [f5_record + 12]
cmp dword ptr [esi], 0x33
jne f5_fail_report
cmp dword ptr [esi + 4], 0x33
jne f5_fail_report
cmp dword ptr [esi + 8], 0x33
jne f5_fail_report
cmp dword ptr [esi + 12], 0x33
jne f5_fail_report
lea eax, [esi + 48]
cmp dword ptr [esi + 28], eax
jne f5_fail_report
cmp dword ptr [esi + 32], 0x5a17c0de
jne f5_fail_report
cmp dword ptr [esi + 44], 0x2b
jne f5_fail_report
mov eax, dword ptr [f5_expect + 4]
cmp dword ptr [esi + 48], eax
jne f5_fail_report
mov eax, dword ptr [f5_expect + 8]
cmp dword ptr [esi + 52], eax
jne f5_fail_report
mov eax, dword ptr [f5_expect + 12]
cmp dword ptr [esi + 56], eax
jne f5_fail_report
mov eax, dword ptr [esi + 64]
and eax, 0xffffffef
cmp eax, 0x10446
jne f5_fail_report
cmp dword ptr [esi + 68], 0x40400000
jne f5_fail_report
cmp word ptr [esi + 72], 0x33
jne f5_fail_report
mov eax, cr0
mov dword ptr [f5_record + 20], eax
and eax, 0x80010001
cmp eax, 0x80010001
jne f5_fail_report
mov eax, cr2
mov dword ptr [f5_record + 24], eax
cmp dword ptr [f5_expect + 4], 14
jne 3f
cmp eax, dword ptr [f5_expect + 16]
jne f5_fail_report
3:
mov eax, cr3
mov dword ptr [f5_record + 28], eax
cmp eax, dword ptr [f5_expect + 20]
jne f5_fail_report
mov eax, cr4
mov dword ptr [f5_record + 32], eax
test eax, 0x00a00030
jnz f5_fail_report
xor eax, eax
mov ax, cs
mov dword ptr [f5_record + 40], eax
cmp eax, 8
jne f5_fail_report
mov ax, ss
mov dword ptr [f5_record + 44], eax
cmp eax, 16
jne f5_fail_report
mov ax, ds
mov dword ptr [f5_record + 48], eax
cmp eax, 16
jne f5_fail_report
mov ax, es
mov dword ptr [f5_record + 52], eax
cmp eax, 16
jne f5_fail_report
mov ax, fs
mov dword ptr [f5_record + 56], eax
cmp eax, 16
jne f5_fail_report
mov ax, gs
mov dword ptr [f5_record + 60], eax
cmp eax, 16
jne f5_fail_report
sgdt [f5_record + 140]
cmp word ptr [f5_record + 140], 55
jne f5_fail_report
lea eax, [f5_gdt]
cmp dword ptr [f5_record + 142], eax
jne f5_fail_report
xor eax, eax
str ax
mov dword ptr [f5_record + 148], eax
cmp eax, 0x18
jne f5_fail_report
mov eax, dword ptr [f3_context + {normal_esp0}]
mov dword ptr [f5_record + 152], eax
cmp eax, 0x07c05000
jne f5_fail_report
mov eax, dword ptr [f3_context + {normal_ss0}]
mov dword ptr [f5_record + 156], eax
cmp eax, 16
jne f5_fail_report
movzx eax, word ptr [f3_context + {normal_iomap}]
mov dword ptr [f5_record + 160], eax
cmp eax, 104
jne f5_fail_report
mov dword ptr [f5_record + 8], 1
mov ebp, 24
mov eax, dword ptr [f5_expect]
cmp eax, 1
je 4f
cmp eax, 2
je 5f
cmp eax, 3
je 6f
cmp eax, 4
je 7f
cmp eax, 5
je 8f
lea esi, [{pass_f}]
jmp f5_report
4: lea esi, [{pass_a}]
jmp f5_report
5: lea esi, [{pass_b}]
jmp f5_report
6: lea esi, [{pass_c}]
jmp f5_report
7: lea esi, [{pass_d}]
jmp f5_report
8: lea esi, [{pass_e}]
jmp f5_report
.global f5_fail_report
f5_fail_report:
mov dword ptr [f5_record + 8], 2
lea esi, [{fail}]
mov ebp, 22
.global f5_report
f5_report:
# Release-ordered x86 atomic byte MOV through AtomicU8::as_ptr's storage;
# inherited Acquire readers remain atomic. Same ordering argument as F4.
mov byte ptr [{state}], 3
# Fixed22/24-byte literals,100000 polls per byte; drop-on-timeout like F4.
9:
mov ecx, 100000
mov dx, 0x3fd
10:
in al, dx
test al, 0x20
jnz 11f
dec ecx
jnz 10b
jmp 12f
11:
mov al, byte ptr [esi]
mov dx, 0x3f8
out dx, al
12:
inc esi
dec ebp
jnz 9b
.global f5_terminal
f5_terminal:
cli
13:
hlt
jmp 13b
