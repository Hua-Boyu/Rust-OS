//! F5-only GDT extension. Never selected by inherited F3/F4 entry paths.
//! CLI, valid retained CR3/stacks, and released owner guards are prerequisites.
//! No second LTR: copy the live busy normal descriptor and available emergency
//! descriptor verbatim, preserving the CPU's cached normal TSS and task gate.
#![cfg(all(not(test), target_os = "none"))]

use crate::f5_cpl3::{F5_GDTR_LIMIT, F5_TR, F5_USER_CODE, F5_USER_DATA};
use crate::gdt_tss::f3_context;
use crate::memory::paging::privileged::{TRANSITION_TOP, Tss, descriptor};
use core::arch::asm;
use core::mem::size_of;
use core::ptr::{addr_of, addr_of_mut, read_volatile, write_volatile};

#[repr(C, align(8))]
struct Extension {
    entries: [u64; 7],
    attempted: u32,
}

// Hardware-visible descriptor bytes are only accessed through raw pointers.
#[unsafe(no_mangle)]
static mut f5_gdt: Extension = Extension {
    entries: [0; 7],
    attempted: 0,
};

#[repr(C, packed)]
struct Gdtr {
    limit: u16,
    base: u32,
}

fn read_gdtr() -> Gdtr {
    let mut value = Gdtr { limit: 0, base: 0 };
    unsafe {
        asm!("sgdt [{p:e}]", p = in(reg) addr_of_mut!(value), options(nostack, preserves_flags));
    }
    value
}

fn cpu_matches(directory: u32) -> bool {
    let (cr0, cr3, cr4, flags): (u32, u32, u32, u32);
    let (cs, ss, ds, es, fs, gs, tr): (u16, u16, u16, u16, u16, u16, u16);
    unsafe {
        asm!("mov {0:e}, cr0", out(reg) cr0, options(nostack, preserves_flags));
        asm!("mov {0:e}, cr3", out(reg) cr3, options(nostack, preserves_flags));
        asm!("mov {0:e}, cr4", out(reg) cr4, options(nostack, preserves_flags));
        asm!("pushfd", "pop {0:e}", out(reg) flags, options(preserves_flags));
        asm!("mov {0:x}, cs", out(reg) cs, options(nostack, preserves_flags));
        asm!("mov {0:x}, ss", out(reg) ss, options(nostack, preserves_flags));
        asm!("mov {0:x}, ds", out(reg) ds, options(nostack, preserves_flags));
        asm!("mov {0:x}, es", out(reg) es, options(nostack, preserves_flags));
        asm!("mov {0:x}, fs", out(reg) fs, options(nostack, preserves_flags));
        asm!("mov {0:x}, gs", out(reg) gs, options(nostack, preserves_flags));
        asm!("str {0:x}", out(reg) tr, options(nostack, preserves_flags));
    }
    directory != 0
        && directory & 4095 == 0
        && cr3 == directory
        && cr0 & 0x8001_0001 == 0x8001_0001
        && cr4 & ((1 << 4) | (1 << 5) | (1 << 21) | (1 << 23)) == 0
        && flags & ((1 << 9) | (3 << 12) | (1 << 14) | (1 << 17)) == 0
        && cs == 8
        && ss == 16
        && ds == 16
        && es == 16
        && fs == 16
        && gs == 16
        && tr == F5_TR
}

/// Invoke only after ordinary F3 installation and verification. Refusals are
/// terminal to the F5 caller; this never rolls back or authorizes a retry.
pub(crate) fn install(directory: u32) -> bool {
    if !crate::gdt_tss::verify(directory)
        || !cpu_matches(directory)
        || !crate::gdt_tss::writable_kernel_identity(
            addr_of!(f5_gdt) as u32,
            size_of::<Extension>(),
        )
    {
        return false;
    }
    unsafe {
        if read_volatile(addr_of!(f5_gdt.attempted)) != 0 {
            return false;
        }
        write_volatile(addr_of_mut!(f5_gdt.attempted), 1);
        let source = addr_of!(f3_context.entries).cast::<u64>();
        let target = addr_of_mut!(f5_gdt.entries).cast::<u64>();
        for i in 0..5 {
            write_volatile(target.add(i), read_volatile(source.add(i)));
        }
        write_volatile(target.add(5), F5_USER_CODE);
        write_volatile(target.add(6), F5_USER_DATA);
        let gdtr = Gdtr {
            limit: F5_GDTR_LIMIT,
            base: target as u32,
        };
        // Slots0..4 and their bases/limits are unchanged. CS/data caches remain
        // valid; TR keeps its existing cache. A second LTR would #GP on busy TSS.
        asm!("lgdt [{p:e}]", p = in(reg) addr_of!(gdtr), options(nostack, preserves_flags));
    }
    verify(directory)
}

/// Validate the extension, not F3's original-GDTR predicate after LGDT.
/// Hardware-backed captures must additionally corroborate descriptor caches.
pub(crate) fn verify(directory: u32) -> bool {
    if !cpu_matches(directory) || !crate::interrupt::double_fault_task_gate_installed() {
        return false;
    }
    let gdtr = read_gdtr();
    if gdtr.limit != F5_GDTR_LIMIT || gdtr.base != addr_of!(f5_gdt) as u32 {
        return false;
    }
    unsafe {
        if read_volatile(addr_of!(f5_gdt.attempted)) != 1 {
            return false;
        }
        let old = addr_of!(f3_context.entries).cast::<u64>();
        let new = addr_of!(f5_gdt.entries).cast::<u64>();
        for i in 0..5 {
            if read_volatile(new.add(i)) != read_volatile(old.add(i)) {
                return false;
            }
        }
        read_volatile(new.add(3)) == descriptor(addr_of!(f3_context.normal) as u32, 0x8b)
            && read_volatile(new.add(4)) == descriptor(addr_of!(f3_context.emergency) as u32, 0x89)
            && read_volatile(new.add(5)) == F5_USER_CODE
            && read_volatile(new.add(6)) == F5_USER_DATA
            && read_volatile(addr_of!(f3_context.normal.esp0)) == TRANSITION_TOP
            && read_volatile(addr_of!(f3_context.normal.ss0)) == 0x10
            && read_volatile(addr_of!(f3_context.normal.iomap)) == size_of::<Tss>() as u16
    }
}

const _: () = assert!(size_of::<[u64; 7]>() - 1 == F5_GDTR_LIMIT as usize);
