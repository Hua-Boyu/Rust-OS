//! F5 opt-in one-shot runtime. Inherited F3/F4 paths never select this module.
use super::retained_owner::{OWNER, STATE, admit_f5, prepare_f5_locked, seal_f5_locked};
use super::*;
use crate::f5_cpl3::*;
use core::arch::{asm, global_asm, naked_asm};
use core::mem::{offset_of, size_of};
use core::ptr::{addr_of, addr_of_mut, read_volatile, write_volatile};
use core::sync::atomic::Ordering;

// Assembly exclusively claims the latch. No Rust Atomic reference is aliased by
// non-atomic Rust stores; the emitted XCHG and terminal byte MOV are audited.
#[unsafe(no_mangle)]
static mut f5_latch: u32 = 0;
#[unsafe(no_mangle)]
static mut f5_expect: [u32; 7] = [0; 7]; // scenario,vector,error,EIP,CR2,CR3,entry
#[unsafe(no_mangle)]
static mut f5_record: [u32; 64] = [0; 64];
static PASS_A: [u8; 24] = *b"F5 A PASS CPL3 terminal\n";
static PASS_B: [u8; 24] = *b"F5 B PASS CPL3 terminal\n";
static PASS_C: [u8; 24] = *b"F5 C PASS CPL3 terminal\n";
static PASS_D: [u8; 24] = *b"F5 D PASS CPL3 terminal\n";
static PASS_E: [u8; 24] = *b"F5 E PASS CPL3 terminal\n";
static PASS_F: [u8; 24] = *b"F5 F PASS CPL3 terminal\n";
static FAIL: [u8; 22] = *b"F5 FAIL CPL3 terminal\n";

// Mechanically constrained separate F5 expansion, not literal source sharing.
// Closed complete-file derivation preserves the byte-pinned 68-byte F2 ABI.
global_asm!(include_str!("f5_exception_entry.s"),
    frame_size = const crate::exception_abi::FRAME_SIZE,
    vector_offset = const crate::exception_abi::VECTOR_OFFSET,
    options(att_syntax));
unsafe extern "C" {
    static f5_exception_entries: [u32; 32];
}
#[repr(C, packed)]
struct Idtr {
    limit: u16,
    base: u32,
}

fn install_gates() -> bool {
    let mut idtr = Idtr { limit: 0, base: 0 };
    unsafe {
        asm!("sidt [{p:e}]", p = in(reg) addr_of_mut!(idtr), options(nostack, preserves_flags));
    }
    if idtr.limit != 2047
        || !crate::interrupt::double_fault_task_gate_installed()
        || !crate::gdt_tss::writable_kernel_identity(idtr.base, 2048)
    {
        return false;
    }
    let (start, end) = frame::kernel_bounds();
    unsafe {
        let entries = addr_of!(f5_exception_entries).cast::<u32>();
        // Preflight every target before publishing any gate. All remain DPL0.
        for vector in 0..32 {
            if vector == 8 {
                continue;
            }
            let entry = read_volatile(entries.add(vector));
            if u64::from(entry) < start || u64::from(entry) >= end {
                return false;
            }
        }
        for vector in 0..32 {
            if vector == 8 {
                continue;
            }
            let entry = read_volatile(entries.add(vector));
            let gate = (idtr.base as *mut u32).add(vector * 2);
            let low = (entry & 0xffff) | (8 << 16);
            let high = (entry & 0xffff0000) | 0x8e00;
            write_volatile(gate, low);
            write_volatile(gate.add(1), high);
            if read_volatile(gate) != low || read_volatile(gate.add(1)) != high {
                return false;
            }
        }
    }
    crate::interrupt::double_fault_task_gate_installed()
}

#[unsafe(export_name = "f5_run_cpl3")]
#[unsafe(link_section = ".text.f4_contract")]
pub(crate) extern "C" fn run(scenario: u32) -> ! {
    unsafe {
        asm!("cli", "cld", options(nostack));
    }
    if !admit_f5(scenario) {
        f5_unsupported();
    }
    let directory = {
        let mut owner = OWNER.lock();
        let mut map = crate::memory::PAGE_MAP.lock();
        let mut fa = crate::memory::FRAME_ALLOC.lock();
        match map.as_mut() {
            Some(pm) => {
                if crate::memory::PAGING_ENABLED.load(Ordering::Acquire)
                    && prepare_f5_locked(&mut owner, pm, &mut fa, scenario)
                {
                    Some(pm.directory as u32)
                } else {
                    None
                }
            }
            _ => None,
        }
    };
    let Some(directory) = directory else {
        f5_unsupported();
    };
    if !crate::gdt_tss::install_f5(directory)
        || !crate::gdt_tss::verify(directory)
        || !crate::f5_gdt::install(directory)
        || !install_gates()
    {
        f5_unsupported();
    }
    for (base, bytes) in [
        (addr_of!(f5_latch) as u32, 4),
        (addr_of!(f5_expect) as u32, size_of::<[u32; 7]>()),
        (addr_of!(f5_record) as u32, size_of::<[u32; 64]>()),
    ] {
        if !crate::gdt_tss::writable_kernel_identity(base, bytes) {
            f5_unsupported();
        }
    }
    let valid = {
        let mut owner = OWNER.lock();
        let map = crate::memory::PAGE_MAP.lock();
        let fa = crate::memory::FRAME_ALLOC.lock();
        map.as_ref()
            .is_some_and(|pm| seal_f5_locked(&mut owner, pm, &fa))
    };
    if !valid || !crate::f5_gdt::verify(directory) {
        f5_unsupported();
    }
    let Some(row) = f5_row(scenario) else {
        f5_unsupported();
    };
    unsafe {
        let expect = addr_of_mut!(f5_expect).cast::<u32>();
        for (i, value) in [
            scenario,
            row.vector,
            row.error,
            row.fault_eip,
            row.cr2,
            directory,
            row.entry,
        ]
        .iter()
        .enumerate()
        {
            write_volatile(expect.add(i), *value);
        }
        // Same PIC mask protocol as existing IRQ controller setup, no allocation
        // or port ownership change. IF remains0 and every fixture is one vCPU.
        crate::io::ports::lockfree_outb(0x21, 0xff);
        crate::io::ports::lockfree_outb(0xa1, 0xff);
    }
    f5_iret()
}

#[unsafe(naked)]
#[unsafe(no_mangle)]
extern "C" fn f5_iret() -> ! {
    naked_asm!(
        "cli",
        "mov eax, dword ptr [f5_expect]",
        "cmp eax, 1",
        "jb f5_unsupported",
        "cmp eax, 6",
        "ja f5_unsupported",
        "dec eax",
        "shl eax, 6",
        "add eax, 0x40000100",
        "cmp eax, dword ptr [f5_expect + 24]",
        "jne f5_unsupported",
        // No kernel DS memory access after the USER segment loads.
        "mov edx, eax",
        "mov ax, 0x33",
        "mov ds, ax",
        "mov es, ax",
        "mov fs, ax",
        "mov gs, ax",
        "push 0x33",
        "push 0x40400000",
        "push 2",
        "push 0x2b",
        "push edx",
        ".global f5_before_iret",
        "f5_before_iret:",
        "iretd",
    );
}

#[unsafe(naked)]
#[unsafe(no_mangle)]
extern "C" fn f5_unsupported() -> ! {
    naked_asm!(
        "cli",
        "cld",
        "mov eax, 1",
        "xchg dword ptr [f5_latch], eax",
        "test eax, eax",
        "jnz f5_terminal",
        "jmp f5_fail_report"
    );
}

#[unsafe(naked)]
#[unsafe(no_mangle)]
extern "C" fn f5_bridge() -> ! {
    naked_asm!(include_str!("f5_bridge.s"),
        state = sym STATE,
        pass_a = sym PASS_A, pass_b = sym PASS_B, pass_c = sym PASS_C,
        pass_d = sym PASS_D, pass_e = sym PASS_E, pass_f = sym PASS_F,
        fail = sym FAIL,
        normal_esp0 = const offset_of!(crate::gdt_tss::F3Context, normal) + offset_of!(privileged::Tss, esp0),
        normal_ss0 = const offset_of!(crate::gdt_tss::F3Context, normal) + offset_of!(privileged::Tss, ss0),
        normal_iomap = const offset_of!(crate::gdt_tss::F3Context, normal) + offset_of!(privileged::Tss, iomap),
    );
}
