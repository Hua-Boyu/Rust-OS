use crate::io::ports::{lockfree_inb, lockfree_outb};

// COM1 at 0x3F8. Minimal 16550 init + polled write; used as the observable
// debug channel for the QEMU boot smoke test (VGA text buffer reads through
// the QEMU monitor are unreliable because 0xB8000 is a VRAM window).
const COM1: u16 = 0x3F8;

pub fn init() {
    unsafe {
        // scratch-register loopback test: skip init if no serial device
        lockfree_outb(COM1 + 7, 0xA5);
        if lockfree_inb(COM1 + 7) != 0xA5 {
            return;
        }

        // enter config mode (LCR bit 7), set divisor 1 (9600 baud), leave config mode
        lockfree_outb(COM1 + 3, 0x80);
        lockfree_outb(COM1, 0x01); // DLL low
        lockfree_outb(COM1 + 1, 0x00); // DLL high
        lockfree_outb(COM1 + 3, 0x03); // 8N1

        // enable FIFO (bit 1 of FCR), then loopback mode for the test above is
        // already done; normal operation
        lockfree_outb(COM1 + 2, 0x01);
    }
}

pub fn putc(ch: u8) {
    unsafe {
        // wait for transmitter holding register empty (LSR bit 5), bounded
        let mut remaining = 100000u32;
        while remaining != 0 {
            if lockfree_inb(COM1 + 5) & 0x20 != 0 {
                lockfree_outb(COM1, ch);
                return;
            }
            remaining = remaining.wrapping_sub(1);
        }
    }
}

pub fn puts(s: &str) {
    for ch in s.bytes() {
        putc(ch);
    }
}

pub struct SerialWriter;

impl core::fmt::Write for SerialWriter {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        puts(s);
        Ok(())
    }
}
