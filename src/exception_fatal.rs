//! Fatal CPU exceptions only. IRQ compiler ABI and PIC dispatch stay unchanged.
use crate::exception_abi::{ExceptionFrame, FatalLatch, FrameKind, frame_kind, supported_profile};
use crate::io::serial::putc;
use core::arch::{asm, global_asm};
use core::sync::atomic::{AtomicU32, Ordering};

global_asm!(include_str!("exception_entry.s"),
    frame_size = const crate::exception_abi::FRAME_SIZE,
    vector_offset = const crate::exception_abi::VECTOR_OFFSET,
    options(att_syntax));
unsafe extern "C" {
    pub static f2_exception_entries: [u32; 32];
}
static FATAL: FatalLatch = FatalLatch::new();
static PAGE_FAULT_COUNT: AtomicU32 = AtomicU32::new(0);
static LAST_PAGE_FAULT_CODE: AtomicU32 = AtomicU32::new(0);
static LAST_PAGE_FAULT_CR2: AtomicU32 = AtomicU32::new(0);

pub fn page_fault_count() -> u32 {
    PAGE_FAULT_COUNT.load(Ordering::Relaxed)
}
pub fn last_page_fault() -> Option<crate::memory::paging::PageFaultInfo> {
    if page_fault_count() == 0 {
        None
    } else {
        let mut info =
            crate::memory::paging::decode_error_code(LAST_PAGE_FAULT_CODE.load(Ordering::Relaxed));
        info.cr2 = LAST_PAGE_FAULT_CR2.load(Ordering::Relaxed);
        Some(info)
    }
}

// Fatal literals only. Avoid debug-core slice iterator precondition/panic
// machinery: a valid &str supplies exactly len readable bytes, without any
// optional frame read, heap operation, formatting machinery or lock edge.
fn puts(text: &str) {
    let mut cursor = text.as_ptr();
    let mut remaining = text.len();
    while remaining != 0 {
        let byte: u8;
        unsafe {
            asm!("mov {0}, byte ptr [{1:e}]", out(reg_byte) byte, in(reg) cursor, options(readonly, nostack, preserves_flags));
        }
        putc(byte);
        cursor = cursor.wrapping_add(1);
        remaining = remaining.wrapping_sub(1);
    }
}

fn hex(value: u32, mut digits: u32) {
    puts("0x");
    let mut shifted = if digits == 2 {
        value << 24
    } else if digits == 4 {
        value << 16
    } else {
        value
    };
    while digits != 0 {
        digits = digits.wrapping_sub(1);
        let n = ((shifted >> 28) & 15) as u8;
        shifted <<= 4;
        putc(if n < 10 {
            b'0'.wrapping_add(n)
        } else {
            b'a'.wrapping_add(n).wrapping_sub(10)
        });
    }
}
fn boolean(value: bool) {
    puts(if value { "true" } else { "false" });
}
fn halt() -> ! {
    unsafe {
        asm!("cli", options(nomem, nostack));
        loop {
            asm!("hlt", options(nomem, nostack));
        }
    }
}

/// Separate unsupported path: receives a software vector, NO CPU frame pointer.
#[unsafe(no_mangle)]
extern "C" fn f2_unsupported(vector: u32) -> ! {
    if !FATAL.enter() {
        halt();
    }
    puts("CPU exception unsupported vector ");
    hex(vector, 2);
    puts("; frame not decoded\n");
    halt()
}

/// # Safety
/// Only exception_entry.s calls this, with its aligned initialized mandatory
/// 68-byte prefix on a usable kernel stack. No optional tail is referenced.
#[unsafe(no_mangle)]
extern "C" fn f2_fatal(f: &ExceptionFrame) -> ! {
    // First Rust operation claims the latch. Delivery/stub faults before this
    // point are NOT protected. #DF on a bad stack still requires F3 strategy.
    if !FATAL.enter() {
        halt();
    }
    let cr2: u32;
    let cr0: u32;
    let cr4: u32;
    let cs: u16;
    let ss: u16;
    let flags: u32;
    unsafe {
        asm!("mov {0:e}, cr2", out(reg) cr2, options(nomem, nostack, preserves_flags));
        asm!("mov {0:e}, cr0", out(reg) cr0, options(nomem, nostack, preserves_flags));
        asm!("mov {0:e}, cr4", out(reg) cr4, options(nomem, nostack, preserves_flags));
        asm!("mov {0:x}, cs", out(reg) cs, options(nomem, nostack, preserves_flags));
        asm!("mov {0:x}, ss", out(reg) ss, options(nomem, nostack, preserves_flags));
        asm!("pushfd", "pop {0:e}", out(reg) flags, options(preserves_flags));
    }
    if !supported_profile(cr0, cr4, flags, cs as u32, ss as u32) {
        puts("CPU exception unsupported execution profile\n");
        halt();
    }

    if frame_kind(f.vector) == FrameKind::Unsupported {
        // Defense against erroneous future wiring; no unsupported tail decoded.
        halt();
    }
    if f.vector == 14 {
        let mut info = crate::memory::paging::decode_error_code(f.error);
        info.cr2 = cr2;
        // swap accepts every Ordering; debug-core store's invalid-order panic
        // branch would otherwise pull the generic panic/VGA path into this ABI.
        LAST_PAGE_FAULT_CODE.swap(f.error, Ordering::Relaxed);
        LAST_PAGE_FAULT_CR2.swap(cr2, Ordering::Relaxed);
        PAGE_FAULT_COUNT.fetch_add(1, Ordering::Relaxed);
        puts("page fault: code ");
        hex(f.error, 4);
        puts(" present=");
        boolean(info.present);
        puts(" write=");
        boolean(info.write);
        puts(" user=");
        boolean(info.user);
        puts(" fetch=");
        boolean(info.fetch);
        puts(" cr2=");
        hex(cr2, 8);
        puts(" rip=");
        hex(f.eip, 8);
        putc(b'\n');
    } else if f.vector == 13 {
        puts("general fault: error=");
        hex(f.error, 8);
        puts(" ring=");
        putc(b'0'.wrapping_add((f.cs & 3) as u8));
        puts(" rip=");
        hex(f.eip, 8);
        putc(b'\n');
    } else {
        puts("CPU exception vector ");
        hex(f.vector, 2);
        if f.vector == 8 {
            puts(" error=");
            hex(f.error, 8);
            puts(" #DF saved CS/EIP undefined; usable-stack delivery only");
        }
        putc(b'\n');
    }
    puts("F2 fatal terminal\n");
    halt()
}
