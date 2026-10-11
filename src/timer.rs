//! PIT channel 0 system timer. Mode 1 (rate generator), 100 Hz from the
//! 1193182 Hz base clock. Pure divisor math is host-testable; port I/O is
//! gated out under test builds.

use crate::io::ports::lockfree_outb;

pub const PIT_BASE_HZ: u32 = 1_193_182;
pub const TIMER_HZ: u32 = 100;

/// PIT divisor for a target frequency. Returns None if the divisor does not
/// fit the 16-bit counter (PIT max divisor is 65535).
pub fn pit_divisor(hz: u32) -> Option<u16> {
    if hz == 0 {
        return None;
    }
    let d = PIT_BASE_HZ / hz;
    if d == 0 || d > 65535 {
        return None;
    }
    Some(d as u16)
}

pub fn init() {
    #[cfg(test)]
    return;
    #[allow(unreachable_code)]
    unsafe {
        let div = pit_divisor(TIMER_HZ).expect("valid PIT divisor");
        lockfree_outb(0x43, 0x36); // cmd: channel 0, lolo, mode 1, binary
        lockfree_outb(0x40, div as u8);
        lockfree_outb(0x40, (div >> 8) as u8);
    }
}

/// Monotonic tick counter, incremented by the timer ISR (IRQ0 / vector 0x20).
static TICKS: core::sync::atomic::AtomicU32 = core::sync::atomic::AtomicU32::new(0);

pub fn isr_timer() {
    TICKS.fetch_add(1, core::sync::atomic::Ordering::Relaxed);
}

pub fn ticks() -> u32 {
    TICKS.load(core::sync::atomic::Ordering::Relaxed)
}

pub fn uptime_secs() -> u32 {
    ticks() / TIMER_HZ
}
