//! Pure, host-testable keyboard logic: PS/2 Set 1 scan-code decoding and the
//! ISR -> main-loop SPSC ring buffer. No asm, no ports, no allocation, so the
//! host test harness (tests_kernel/) can include this module via #[path].

use core::cell::UnsafeCell;
use core::sync::atomic::{AtomicUsize, Ordering};

// Set 1 key codes used by the shell (press codes; release = press + 0x80).
pub const KEY_BACKSPACE: u8 = 0x0E;
pub const KEY_ENTER: u8 = 0x1C;
pub const KEY_SHIFT_L: u8 = 0x2A;
pub const KEY_SHIFT_R: u8 = 0x36;
pub const KEY_CAPS_LOCK: u8 = 0x3A;

/// Set 1: a release code is the press code with bit 7 set.
pub fn is_release(sc: u8) -> bool {
    sc >= 0x80
}

/// Decode a Set 1 press code to a printable char, honouring shift and caps.
/// Returns None for release codes and unmapped keys.
/// NOTE: QWERTY rows are NOT alphabetical — a scan-code row must be decoded
/// through the actual key table, not `base + (sc - row_start)`.
pub fn decode_set1(sc: u8, shift: bool, caps: bool) -> Option<char> {
    if is_release(sc) {
        return None;
    }
    let base: u8 = match sc {
        // number row
        0x02 => b'1',
        0x03 => b'2',
        0x04 => b'3',
        0x05 => b'4',
        0x06 => b'5',
        0x07 => b'6',
        0x08 => b'7',
        0x09 => b'8',
        0x0A => b'9',
        0x0B => b'0',
        // top letter row (q w e r t y u i o p [ ])
        0x10 => b'q',
        0x11 => b'w',
        0x12 => b'e',
        0x13 => b'r',
        0x14 => b't',
        0x15 => b'y',
        0x16 => b'u',
        0x17 => b'i',
        0x18 => b'o',
        0x19 => b'p',
        0x1A => b'[',
        0x1B => b']',
        // home row (a s d f g h j k l)
        0x1E => b'a',
        0x1F => b's',
        0x20 => b'd',
        0x21 => b'f',
        0x22 => b'g',
        0x23 => b'h',
        0x24 => b'j',
        0x25 => b'k',
        0x26 => b'l',
        // bottom row (z x c v b n m)
        0x2C => b'z',
        0x2D => b'x',
        0x2E => b'c',
        0x2F => b'v',
        0x30 => b'b',
        0x31 => b'n',
        0x32 => b'm',
        0x29 => b'`',
        0x0C => b'-',
        0x39 => b' ',
        0x33 => b',',
        0x34 => b'.',
        0x35 => b'/',
        _ => return None,
    };
    let letter = sc >= 0x10 && sc <= 0x32;
    if shift {
        let shifted = match (sc, base) {
            (0x02, _) => b'!',
            (0x03, _) => b'@',
            (0x04, _) => b'#',
            (0x05, _) => b'$',
            (0x06, _) => b'%',
            (0x07, _) => b'^',
            (0x08, _) => b'&',
            (0x09, _) => b'*',
            (0x0A, _) => b'(',
            (0x0B, _) => b')',
            (0x0C, _) => b'_',
            _ => base.to_ascii_uppercase(),
        };
        return Some(shifted as char);
    }
    if letter && caps {
        return Some(base.to_ascii_uppercase() as char);
    }
    Some(base as char)
}

/// Modifier state, updated from raw scan codes (press events only).
pub struct Modifiers {
    pub shift: bool,
    pub caps: bool,
}

impl Modifiers {
    pub const fn new() -> Self {
        Self {
            shift: false,
            caps: false,
        }
    }

    /// Returns true if the scan code was a modifier event (consumed).
    /// Matches both press and release codes (code & 0x7F).
    pub fn apply(&mut self, sc: u8) -> bool {
        match sc & 0x7F {
            KEY_SHIFT_L | KEY_SHIFT_R => {
                self.shift = !is_release(sc);
                true
            }
            KEY_CAPS_LOCK if !is_release(sc) => {
                self.caps = !self.caps;
                true
            }
            _ => false,
        }
    }
}

/// Single-producer (ISR) / single-consumer (main loop) ring buffer of raw
/// scan codes. Fixed size, no allocation, no locks: the ISR only writes
/// `head`, the main loop only writes `tail`.
pub struct RingBuffer<const N: usize> {
    data: UnsafeCell<[u8; N]>,
    head: AtomicUsize,
    tail: AtomicUsize,
}

unsafe impl<const N: usize> Sync for RingBuffer<N> {}

/// The live ISR -> main-loop channel. Producer: keyboard ISR (src/interrupt.rs).
/// Consumer: shell (src/shell.rs).
pub static RING: RingBuffer<256> = RingBuffer::new();

impl<const N: usize> RingBuffer<N> {
    pub const fn new() -> Self {
        Self {
            data: UnsafeCell::new([0u8; N]),
            head: AtomicUsize::new(0),
            tail: AtomicUsize::new(0),
        }
    }

    /// Producer side (ISR). Returns false when full — the event is dropped,
    /// never blocks, never allocates.
    pub fn push(&self, b: u8) -> bool {
        let h = self.head.load(Ordering::Relaxed);
        let next = (h + 1) % N;
        if next == self.tail.load(Ordering::Relaxed) {
            return false; // full: drop, keep the ISR short
        }
        unsafe { (*self.data.get())[h] = b };
        self.head.store(next, Ordering::Release);
        true
    }

    /// Consumer side (main loop).
    pub fn pop(&self) -> Option<u8> {
        let t = self.tail.load(Ordering::Acquire);
        if t == self.head.load(Ordering::Acquire) {
            return None;
        }
        let b = unsafe { (*self.data.get())[t] };
        self.tail.store((t + 1) % N, Ordering::Release);
        Some(b)
    }

    pub fn len(&self) -> usize {
        let h = self.head.load(Ordering::Acquire);
        let t = self.tail.load(Ordering::Acquire);
        (h + N - t) % N
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}
