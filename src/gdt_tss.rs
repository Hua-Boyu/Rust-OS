//! One-shot, terminal-only classic i386 task-state installation.
//! Caller: CLI, retained stack mappings validated, all memory guards released.
//! No retry/rollback and no continuation to ordinary boot after publication.
#![cfg(not(test))]

use core::arch::{asm, global_asm};
use core::mem::{offset_of, size_of};
use core::ptr::{addr_of, addr_of_mut, read_volatile, write_volatile};

use crate::memory::paging::privileged::{
    EMERGENCY_TOP, KERNEL_CODE, KERNEL_DATA, TRANSITION_TOP, Tss, descriptor,
};

#[repr(C, align(8))]
pub(crate) struct F3Context {
    pub(crate) entries: [u64; 5],
    pub(crate) normal: Tss,
    pub(crate) emergency: Tss,
    pub(crate) observed_tr: u32,
    pub(crate) observed_esp: u32,
    pub(crate) observed_cr3: u32,
    pub(crate) observed_error: u32,
    attempt: u32,
}

// No references to this storage may survive hardware publication: LTR and task
// switching mutate descriptors/TSSes outside the Rust abstract machine.
#[unsafe(no_mangle)]
pub(crate) static mut f3_context: F3Context = F3Context {
    entries: [0, KERNEL_CODE, KERNEL_DATA, 0, 0],
    normal: Tss::new(),
    emergency: Tss::new(),
    observed_tr: 0,
    observed_esp: 0,
    observed_cr3: 0,
    observed_error: 0,
    attempt: 0,
};

const _: () = {
    assert!(size_of::<Tss>() == 104);
    assert!(core::mem::align_of::<Tss>() == 4);
    assert!(offset_of!(Tss, backlink) == 0);
    assert!(offset_of!(Tss, esp0) == 4);
    assert!(offset_of!(Tss, ss0) == 8);
    assert!(offset_of!(Tss, esp1) == 12);
    assert!(offset_of!(Tss, ss1) == 16);
    assert!(offset_of!(Tss, esp2) == 20);
    assert!(offset_of!(Tss, ss2) == 24);
    assert!(offset_of!(Tss, cr3) == 28);
    assert!(offset_of!(Tss, eip) == 32);
    assert!(offset_of!(Tss, eflags) == 36);
    assert!(offset_of!(Tss, eax) == 40);
    assert!(offset_of!(Tss, ecx) == 44);
    assert!(offset_of!(Tss, edx) == 48);
    assert!(offset_of!(Tss, ebx) == 52);
    assert!(offset_of!(Tss, esp) == 56);
    assert!(offset_of!(Tss, ebp) == 60);
    assert!(offset_of!(Tss, esi) == 64);
    assert!(offset_of!(Tss, edi) == 68);
    assert!(offset_of!(Tss, es) == 72);
    assert!(offset_of!(Tss, cs) == 76);
    assert!(offset_of!(Tss, ss) == 80);
    assert!(offset_of!(Tss, ds) == 84);
    assert!(offset_of!(Tss, fs) == 88);
    assert!(offset_of!(Tss, gs) == 92);
    assert!(offset_of!(Tss, ldt) == 96);
    assert!(offset_of!(Tss, trap) == 100);
    assert!(offset_of!(Tss, iomap) == 102);
    assert!(offset_of!(F3Context, entries) == 0);
    assert!(size_of::<F3Context>() + crate::gdt::EARLY_GDT_BYTES <= 4096);
};

global_asm!(
    include_str!("f3_entry.s"),
    observed_tr = const offset_of!(F3Context, observed_tr),
    observed_esp = const offset_of!(F3Context, observed_esp),
    observed_cr3 = const offset_of!(F3Context, observed_cr3),
    observed_error = const offset_of!(F3Context, observed_error),
    options(att_syntax)
);

unsafe extern "C" {
    fn f3_emergency_entry();
    fn f3_ready();
    fn f3_install_terminal();
}

#[repr(C, packed)]
struct Gdtr {
    limit: u16,
    base: u32,
}

fn cpu_profile(directory: u32) -> bool {
    let (cr0, cr3, cr4, flags): (u32, u32, u32, u32);
    unsafe {
        asm!("mov {value:e}, cr0", value = out(reg) cr0, options(nostack, preserves_flags));
        asm!("mov {value:e}, cr3", value = out(reg) cr3, options(nostack, preserves_flags));
        asm!("mov {value:e}, cr4", value = out(reg) cr4, options(nostack, preserves_flags));
        asm!("pushfd", "pop {value:e}", value = out(reg) flags, options(preserves_flags));
    }
    // Classic non-PAE/non-PSE supervisor paging, CET/VM86/IF/NT/IOPL off.
    directory != 0
        && directory & 0xfff == 0
        && cr3 == directory
        && cr0 & 0x8001_0001 == 0x8001_0001
        && cr4 & ((1 << 23) | (1 << 5) | (1 << 4)) == 0
        && flags & ((1 << 17) | (1 << 14) | (3 << 12) | (1 << 9)) == 0
}

fn selectors_valid() -> bool {
    let (cs, ss, ds, es, fs, gs): (u16, u16, u16, u16, u16, u16);
    unsafe {
        asm!("mov {0:x}, cs", out(reg) cs, options(nostack, preserves_flags));
        asm!("mov {0:x}, ss", out(reg) ss, options(nostack, preserves_flags));
        asm!("mov {0:x}, ds", out(reg) ds, options(nostack, preserves_flags));
        asm!("mov {0:x}, es", out(reg) es, options(nostack, preserves_flags));
        asm!("mov {0:x}, fs", out(reg) fs, options(nostack, preserves_flags));
        asm!("mov {0:x}, gs", out(reg) gs, options(nostack, preserves_flags));
    }
    cs == 8 && ss == 16 && ds == 16 && es == 16 && fs == 16 && gs == 16
}

fn task_register() -> u16 {
    let tr: u16;
    unsafe { asm!("str {0:x}", out(reg) tr, options(nostack, preserves_flags)) };
    tr
}

/// Permanently protected kernel image AND actual supervisor writable identity
/// PTE/PDE readback. No reference to map/owner storage escapes these scalar calls.
pub(crate) fn writable_kernel_identity(base: u32, bytes: usize) -> bool {
    let start = u64::from(base);
    let end = start + bytes as u64;
    // Kernel image retention is enforced by is_boot_critical/kernel_bounds,
    // separately from PageMap's firmware/module boot_pins inventory.
    let (kernel_start, kernel_end) = crate::memory::frame::kernel_bounds();
    if bytes == 0 || start < kernel_start || end > kernel_end || end > (1u64 << 32) {
        return false;
    }
    let mut page = start & !4095;
    while page < end {
        let Some(snapshot) = crate::memory::page_snapshot(page) else {
            return false;
        };
        let Some(perms) = snapshot.permissions else {
            return false;
        };
        if snapshot.physical_frame != Some(page) || !perms.present || !perms.writable || perms.user
        {
            return false;
        }
        page += 4096;
    }
    true
}

fn context_valid() -> bool {
    writable_kernel_identity(addr_of!(f3_context) as u32, size_of::<F3Context>())
}

fn normal_state() -> Tss {
    let mut tss = Tss::new();
    tss.esp0 = TRANSITION_TOP;
    tss.ss0 = 0x10;
    tss
}

fn emergency_state(directory: u32) -> Tss {
    let mut tss = Tss::new();
    tss.esp0 = EMERGENCY_TOP;
    tss.ss0 = 0x10;
    tss.cr3 = directory;
    tss.eip = f3_emergency_entry as *const () as u32;
    tss.eflags = 2;
    tss.esp = EMERGENCY_TOP;
    tss.es = 0x10;
    tss.cs = 0x08;
    tss.ss = 0x10;
    tss.ds = 0x10;
    tss.fs = 0x10;
    tss.gs = 0x10;
    tss
}

fn tss_matches(actual: *const Tss, expected: Tss) -> bool {
    // Both types have every byte initialized and no padding (asserted above).
    // Raw volatile reads only: neither a shared nor mutable static TSS borrow.
    let actual = actual.cast::<u8>();
    let expected = addr_of!(expected).cast::<u8>();
    let mut byte = 0;
    while byte < 104 {
        unsafe {
            if read_volatile(actual.add(byte)) != expected.add(byte).read() {
                return false;
            }
        }
        byte += 1;
    }
    true
}

fn cpu_readback(directory: u32) -> bool {
    if !cpu_profile(directory) || !selectors_valid() || task_register() != 0x18 || !context_valid()
    {
        return false;
    }
    let mut gdtr = Gdtr { limit: 0, base: 0 };
    unsafe {
        asm!("sgdt [{p:e}]", p = in(reg) addr_of_mut!(gdtr), options(nostack, preserves_flags));
        let entries = addr_of!(f3_context.entries).cast::<u64>();
        if gdtr.limit != 39 || gdtr.base != entries as u32 {
            return false;
        }
        // Exact busy normal / available emergency, full base, limit and flags.
        if read_volatile(entries) != 0
            || read_volatile(entries.add(1)) != KERNEL_CODE
            || read_volatile(entries.add(2)) != KERNEL_DATA
            || read_volatile(entries.add(3)) != descriptor(addr_of!(f3_context.normal) as u32, 0x8b)
            || read_volatile(entries.add(4))
                != descriptor(addr_of!(f3_context.emergency) as u32, 0x89)
        {
            return false;
        }
        tss_matches(addr_of!(f3_context.normal), normal_state())
            && tss_matches(addr_of!(f3_context.emergency), emergency_state(directory))
    }
}

/// Called once with CLI after stack ownership/mapping preparation and unlock.
/// False is a pre-publication refusal only. Any post-LGDT discrepancy diverges
/// through the bounded assembly terminal; no rollback, retry or busy clearing.
pub(crate) fn install(directory: u32) -> bool {
    if !cpu_profile(directory) || !selectors_valid() || !context_valid() {
        return false;
    }
    unsafe {
        if read_volatile(addr_of!(f3_context.attempt)) != 0 {
            return false;
        }
        write_volatile(addr_of_mut!(f3_context.attempt), 1);
    }
    if task_register() != 0 {
        return false;
    }
    unsafe {
        write_volatile(addr_of_mut!(f3_context.normal), normal_state());
        write_volatile(
            addr_of_mut!(f3_context.emergency),
            emergency_state(directory),
        );
        let entries = addr_of_mut!(f3_context.entries).cast::<u64>();
        write_volatile(entries, 0);
        write_volatile(entries.add(1), KERNEL_CODE);
        write_volatile(entries.add(2), KERNEL_DATA);
        write_volatile(
            entries.add(3),
            descriptor(addr_of!(f3_context.normal) as u32, 0x89),
        );
        write_volatile(
            entries.add(4),
            descriptor(addr_of!(f3_context.emergency) as u32, 0x89),
        );
        let gdtr = Gdtr {
            limit: 39,
            base: entries as u32,
        };
        asm!(
            "cli",
            "lgdt ({gdt})",
            "jmp $0x08, $2f",
            "2:",
            "mov $0x10, %ax",
            "mov %ax, %ds",
            "mov %ax, %es",
            "mov %ax, %fs",
            "mov %ax, %gs",
            "mov %ax, %ss",
            "mov $0x18, %ax",
            "ltr %ax",
            gdt = in(reg) addr_of!(gdtr),
            out("eax") _,
            options(att_syntax)
        );
    }
    if !cpu_readback(directory)
        || !crate::interrupt::install_double_fault_task_gate()
        || !verify(directory)
    {
        fail();
    }
    true
}

/// Only valid before any emergency task switch (which is permanently terminal).
pub(crate) fn verify(directory: u32) -> bool {
    cpu_readback(directory) && crate::interrupt::double_fault_task_gate_installed()
}

/// Final memory/owner validation and Sealed -> Terminal must precede this call.
pub(crate) fn ready() -> ! {
    unsafe { asm!("jmp {target}", target = sym f3_ready, options(noreturn, nostack)) }
}

/// No formatting, panic, locks or Rust cleanup on the terminal edge.
pub(crate) fn fail() -> ! {
    unsafe { asm!("jmp {target}", target = sym f3_install_terminal, options(noreturn, nostack)) }
}
