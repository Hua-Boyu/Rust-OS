//! Safe reboot mechanisms, in order of preference:
//!   1. 8042 keyboard controller reset command (0x64 <- 0x00) — the classic
//!      PC reset path, works on SeaBIOS machines and QEMU.
//!   2. Triple fault via a null IDT — guaranteed CPU reset on any x86.
//! Never returns.

use crate::io::ports::lockfree_outb;

pub fn reboot() -> ! {
    unsafe {
        // Mechanism 1: 8042 reset.
        lockfree_outb(0x64, 0x00);
        crate::io::ports::io_wait();

        // Mechanism 2: triple fault. Load a null IDT and trigger a fault;
        // fault handling while the IDT is invalid escalates to shutdown ->
        // CPU reset. Interrupts must be enabled for the int to fire.
        let idtr: [u8; 6] = [0; 6]; // limit 0, base 0
        core::arch::asm!("lidt ({})", in(reg) idtr.as_ptr(), options(att_syntax));
        core::arch::asm!("int $3", options(att_syntax));

        // If we somehow survive, spin with interrupts disabled.
        core::arch::asm!("cli", options(att_syntax));
        loop {
            core::arch::asm!("hlt", options(att_syntax));
        }
    }
}
