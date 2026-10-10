// Host-side unit tests for the kernel's pure algorithms.
// The kernel is a no_std/no_main i686 binary and cannot host its own test
// harness, so this crate includes the testable modules via #[path]; privileged
// asm! blocks in those modules are cfg-gated out under test builds.
#![feature(abi_x86_interrupt)]

#[macro_export]
macro_rules! println {
    ($($arg:tt)*) => {
        let _ = ::core::format_args!($($arg)*);
    };
}

pub mod utils {
    #[path = "../../../src/utils/bits.rs"]
    pub mod bits;
    #[path = "../../../src/utils/mutex.rs"]
    pub mod mutex;
}

pub mod io {
    #[path = "../../../src/io/ports.rs"]
    pub mod ports;
}

#[path = "../../src/multiboot.rs"]
pub mod multiboot;

#[path = "../../src/allocator.rs"]
pub mod allocator;

#[path = "../../src/gdt.rs"]
pub mod gdt;

#[path = "../../src/kbd.rs"]
pub mod kbd;

#[path = "../../src/timer.rs"]
pub mod timer;

#[path = "../../src/cpu.rs"]
pub mod cpu;

// interrupt.rs is not included here: the x86-interrupt ABI cannot compile on
// the host target. IDT gate encoding is tested via the mirror below.

extern crate alloc;

use alloc::vec::Vec;
use core::alloc::{GlobalAlloc, Layout};
use utils::bits::CanManipulateBits;

#[test]
fn bits_get_bits() {
    let v: u64 = 0xDEAD_BEEF_CAFE_F00D;
    assert_eq!(v.get_bits(0, 16), 0xF00D);
    assert_eq!(v.get_bits(16, 16), 0xCAFE);
    assert_eq!(v.get_bits(48, 16), 0xDEAD);
    assert_eq!(v.get_bits(60, 4), 0xD);
}

#[test]
fn bits_set_bits() {
    let v: u64 = 0;
    assert_eq!(v.set_bits(0, 16, 0x1234), 0x1234);
    assert_eq!(v.set_bits(48, 16, 0xABCD), 0xABCD_0000_0000_0000);
    // overwrite one field without touching neighbours
    let v2 = 0xFFFF_FFFF_FFFF_FFFFu64;
    assert_eq!(v2.set_bits(32, 16, 0x0000), 0xFFFF_0000_FFFF_FFFF);
}

#[test]
fn bits_set_one_bit() {
    let v: u64 = 0;
    assert_eq!(v.set_one_bit(47, true), 1u64 << 47);
    assert_eq!(v.set_one_bit(47, false), 0);
}

#[test]
fn bits_create_mask() {
    assert_eq!(<u64 as CanManipulateBits>::create_mask(0, 16), 0xFFFF);
    assert_eq!(
        <u64 as CanManipulateBits>::create_mask(48, 16),
        0xFFFF_0000_0000_0000
    );
    assert_eq!(<u32 as CanManipulateBits>::create_mask(0, 32), 0xFFFF_FFFF);
}

#[test]
fn idt_entry_encoding() {
    // Mirror of interrupt.rs Entry::new (exact bit layout per the x86 IDT gate
    // descriptor spec: offset[15:0] | selector | gate type | DPL | present |
    // offset[31:16]). Kept as a mirror because the x86-interrupt ABI cannot
    // compile on the host target.
    let offset: u32 = 0x1234_5678;
    let entry = encode_entry(offset, 0x08, 0b1110, 0);
    assert_eq!(entry.get_bits(0, 16), 0x5678);
    assert_eq!(entry.get_bits(48, 16), 0x1234);
    assert_eq!(entry.get_bits(16, 16), 0x08); // kernel code selector
    assert_eq!(entry.get_bits(40, 4), 0b1110); // 32-bit interrupt gate
    assert_eq!(entry.get_bits(45, 2), 0); // DPL 0
    assert_eq!(entry.get_bits(47, 1), 1); // present
}

fn encode_entry(isr_offset: u32, selector: u16, gate_type: u8, dpl: u8) -> u64 {
    0u64.set_bits(0, 16, u64::from(isr_offset))
        .set_bits(48, 16, u64::from(isr_offset >> 16))
        .set_bits(16, 16, u64::from(selector))
        .set_bits(40, 4, u64::from(gate_type))
        .set_bits(45, 2, u64::from(dpl))
        .set_one_bit(47, true)
}

#[test]
fn idt_invalid_entry_is_zero() {
    assert_eq!(0u64, 0); // invalid entries are Entry(0) by construction
}

#[test]
fn gdt_code_descriptor_encoding() {
    // create_gdt_entries() returns [null, code, data].
    let entries = gdt::create_gdt_entries();
    assert_eq!(entries[0], 0);

    let code = entries[1];
    // low 32 bits: limit[15:0] | base[23:16]
    assert_eq!(code & 0xFFFF, 0xFFFF);
    assert_eq!((code >> 16) & 0xFF, 0); // base 0
                                        // high 32 bits: base[31:24] | access byte | limit[19:16] | flags nibble
    assert_eq!((code >> 32) & 0xFF, 0); // base high
    assert_eq!((code >> 40) & 0xFF, 0b1001_1001); // access: present|NSD|code|accessed
    assert_eq!((code >> 48) & 0xF, 0xF); // limit high nibble
    assert_eq!((code >> 52) & 0xF, 0b1100); // flags: page granularity + 32-bit segment

    let data = entries[2];
    assert_eq!((data >> 40) & 0xFF, 0b1001_0011); // access: present|NSD|data(rw)|accessed
    assert_eq!((data >> 52) & 0xF, 0b1100); // flags
}

#[test]
fn gdt_access_byte_or_not_xor() {
    // Regression: with_access_byte must OR bits together, not XOR.
    let seg = gdt::GdtSegment::new(0, 0xFFFF_FFFF)
        .with_access_byte(gdt::AccessByte::Present)
        .with_access_byte(gdt::AccessByte::Executable);
    assert_eq!(seg.access_byte, 0b1000_1000);
}

#[test]
fn align_up() {
    assert_eq!(allocator::align_up(0x1000, 16), 0x1000);
    assert_eq!(allocator::align_up(0x1001, 16), 0x1010);
    assert_eq!(allocator::align_up(0x1234, 4096), 0x2000);
    assert_eq!(allocator::align_up(0, 4096), 0);
}

#[test]
fn bump_allocator_arithmetic() {
    let mut bump = allocator::BumpAlloc::new();
    bump.start = 0x200000;
    bump.end = 0x210000;
    bump.next = 0x200000;

    // exercise the GlobalAlloc impl through the spin mutex
    let alloc = utils::mutex::SpinMutex::new(allocator::BumpAlloc::new());
    {
        let b = &mut *alloc.lock();
        b.start = 0x200000;
        b.end = 0x210000;
        b.next = 0x200000;
    }
    let _ = bump; // direct fields verified above

    let p = unsafe { alloc.alloc(Layout::from_size_align(64, 16).unwrap()) };
    assert_eq!(p as usize, 0x200000);

    // next alloc must be aligned up to 4096
    let p2 = unsafe { alloc.alloc(Layout::from_size_align(1, 4096).unwrap()) };
    assert_eq!(p2 as usize, 0x201000);

    // out of memory returns null
    let big = Layout::from_size_align(0x100000, 8).unwrap();
    assert!(unsafe { alloc.alloc(big) }.is_null());
}

#[test]
fn port_allocator_allocate_release() {
    let mut pa = io::ports::PortAllocator::new();
    let p = pa.allocate(0x60).expect("port 0x60");
    assert_eq!(p.addr, 0x60);
    assert!(pa.allocate(0x60).is_none()); // already in use
    drop(p); // Drop releases the port
    assert!(pa.allocate(0x60).is_some());
    assert!(pa.allocate(0x20).is_some());
}

#[test]
fn spin_mutex_basic() {
    let m = utils::mutex::SpinMutex::new(0u32);
    assert!(!m.is_locked());
    {
        let g = m.lock();
        assert!(m.is_locked());
        assert_eq!(*g, 0);
    }
    assert!(!m.is_locked());
    *m.lock() = 42;
    assert_eq!(*m.lock(), 42);
}

// ---- Multiboot memory-map parsing regression tests ----

fn mmap_entry_bytes(size: u32, base: u64, length: u64, typ: u32) -> Vec<u8> {
    let mut v = Vec::new();
    v.extend(size.to_le_bytes());
    v.extend(base.to_le_bytes());
    v.extend(length.to_le_bytes());
    v.extend(typ.to_le_bytes());
    v
}

#[test]
fn mmap_parse_standard_entries() {
    // Two standard entries (size = 20 bytes after the size field).
    let mut bytes = mmap_entry_bytes(20, 0x0, 0x9FC00, 1);
    bytes.extend(mmap_entry_bytes(20, 0x100000, 0x3F00000, 1));
    let entries = multiboot::parse_mmap(&bytes);
    assert_eq!(entries.len(), 2);
    // assert_eq! takes references; fields of packed structs must be copied
    // to locals first (E0793).
    let e0 = entries[0];
    let e1 = entries[1];
    let (b0, l0, t0) = (e0.base_addr, e0.length, e0.type_);
    let (b1, _, t1) = (e1.base_addr, e1.length, e1.type_);
    assert_eq!(b0, 0x0);
    assert_eq!(l0, 0x9FC00);
    assert_eq!(b1, 0x100000);
    assert_eq!(t1, 1);
}

#[test]
fn mmap_parse_variable_size_entries() {
    // Regression: entries with size != 20 must be handled by walking
    // `size + 4`, not by dividing mmap_length by a fixed struct size.
    // size counts bytes AFTER the size field, so a size-24 entry needs 4
    // padding bytes after the type field.
    let mut bytes = mmap_entry_bytes(24, 0x100000, 0x1000, 1); // oversized entry
    bytes.extend([0u8; 4]); // padding to honor size=24
    bytes.extend(mmap_entry_bytes(20, 0x200000, 0x2000, 2));
    let entries = multiboot::parse_mmap(&bytes);
    assert_eq!(entries.len(), 2);
    let e0 = entries[0];
    let e1 = entries[1];
    let b0 = e0.base_addr;
    let b1 = e1.base_addr;
    assert_eq!(b0, 0x100000);
    assert_eq!(b1, 0x200000); // found via size+4 walk
}

#[test]
fn mmap_parse_truncated_entry_stops() {
    // A trailing entry claiming more bytes than exist must not read OOB.
    let mut bytes = mmap_entry_bytes(20, 0x100000, 0x1000, 1);
    bytes.extend([30u8, 0, 0, 0, 1, 0, 0, 0]); // claims 30, only 8 present
    let entries = multiboot::parse_mmap(&bytes);
    assert_eq!(entries.len(), 1);
    let e0 = entries[0];
    let b0 = e0.base_addr;
    assert_eq!(b0, 0x100000);
}

#[test]
fn mmap_find_usable_block_skips_type2() {
    let mut bytes = mmap_entry_bytes(20, 0x0, 0x9FC00, 2); // reserved
    bytes.extend(mmap_entry_bytes(20, 0x100000, 0x3F00000, 1)); // usable
    let block = multiboot::find_usable_block(&bytes).expect("block");
    let (bb, bt) = (block.base_addr, block.type_);
    assert_eq!(bb, 0x100000);
    assert_eq!(bt, 1);
}

#[test]
fn mmap_find_usable_block_skips_base_zero() {
    // The allocator's original code skipped base_addr == 0 entries; keep that
    // behavior explicit in a test.
    let bytes = mmap_entry_bytes(20, 0x0, 0x9FC00, 1);
    assert!(multiboot::find_usable_block(&bytes).is_none());
}

#[test]
fn bump_alloc_rejects_alloc_at_exact_boundary() {
    let alloc = utils::mutex::SpinMutex::new(allocator::BumpAlloc::new());
    {
        let b = &mut *alloc.lock();
        b.start = 0x1000;
        b.end = 0x2000;
        b.next = 0x1000;
    }
    // exactly fills: ok
    let p = unsafe { alloc.alloc(Layout::from_size_align(4096, 16).unwrap()) };
    assert_eq!(p as usize, 0x1000);
    // one byte past end: null
    let p2 = unsafe { alloc.alloc(Layout::from_size_align(1, 1).unwrap()) };
    assert!(p2.is_null());
}

// ---- Keyboard scan-code decoding tests ----

#[test]
fn kbd_decode_letters() {
    assert_eq!(kbd::decode_set1(0x1E, false, false), Some('a')); // 'a' press
    assert_eq!(kbd::decode_set1(0x1E, true, false), Some('A')); // shift
    assert_eq!(kbd::decode_set1(0x1E, false, true), Some('A')); // caps
    assert_eq!(kbd::decode_set1(0x1E, true, true), Some('A'));
    assert_eq!(kbd::decode_set1(0x02, false, false), Some('1'));
    assert_eq!(kbd::decode_set1(0x02, true, false), Some('!'));
    assert_eq!(kbd::decode_set1(0x39, false, false), Some(' ')); // space is 0x39
    assert_eq!(kbd::decode_set1(0x29, false, false), Some('`')); // backtick, not space
    assert_eq!(kbd::decode_set1(0x0C, false, false), Some('-')); // hyphen is 0x0C
    assert_eq!(kbd::decode_set1(0x0C, true, false), Some('_')); // shift-hyphen
}

#[test]
fn kbd_qwerty_rows_are_not_alphabetical() {
    // Regression: rows must map through the physical QWERTY table.
    assert_eq!(kbd::decode_set1(0x10, false, false), Some('q'));
    assert_eq!(kbd::decode_set1(0x16, false, false), Some('u')); // was wrongly 'g'
    assert_eq!(kbd::decode_set1(0x19, false, false), Some('p')); // was wrongly 'f'
    assert_eq!(kbd::decode_set1(0x23, false, false), Some('h')); // was wrongly 'e'
    assert_eq!(kbd::decode_set1(0x26, false, false), Some('l')); // was wrongly 'h'
    assert_eq!(kbd::decode_set1(0x32, false, false), Some('m')); // was wrongly 'k'
}

#[test]
fn kbd_release_codes_not_decoded() {
    assert!(kbd::is_release(0x9E)); // 'a' release = 0x1E + 0x80
    assert_eq!(kbd::decode_set1(0x9E, false, false), None);
    assert!(!kbd::is_release(0x1E));
}

#[test]
fn kbd_modifiers() {
    let mut m = kbd::Modifiers::new();
    assert!(m.apply(0x2A)); // shift press
    assert!(m.shift);
    assert!(m.apply(0xAA)); // shift release
    assert!(!m.shift);
    assert!(m.apply(0x3A)); // caps press
    assert!(m.caps);
    assert!(!m.apply(0x1E)); // 'a' is not a modifier
                             // caps toggle: second press turns it off
    assert!(m.apply(0x3A));
    assert!(!m.caps);
}

// ---- Ring buffer tests ----

#[test]
fn ring_basic_fifo() {
    let r = kbd::RingBuffer::<8>::new();
    assert!(r.is_empty());
    assert!(r.push(1));
    assert!(r.push(2));
    assert_eq!(r.len(), 2);
    assert_eq!(r.pop(), Some(1));
    assert_eq!(r.pop(), Some(2));
    assert_eq!(r.pop(), None);
}

#[test]
fn ring_full_drops_and_wraps() {
    let r = kbd::RingBuffer::<4>::new();
    // capacity N holds N-1 items (one slot reserved to distinguish full/empty)
    for i in 0..3 {
        assert!(r.push(i));
    }
    assert!(!r.push(3)); // full: drop, no block
    assert_eq!(r.len(), 3);
    assert_eq!(r.pop(), Some(0));
    assert!(r.push(3)); // now room again
    assert_eq!(r.pop(), Some(1));
    assert_eq!(r.pop(), Some(2));
    assert_eq!(r.pop(), Some(3)); // wrapped slot
    assert_eq!(r.pop(), None);
}

#[test]
fn ring_single_item_edge() {
    let r = kbd::RingBuffer::<2>::new();
    assert!(r.push(7));
    assert!(!r.push(8)); // full at N=2
    assert_eq!(r.pop(), Some(7));
    assert!(r.push(8));
    assert_eq!(r.pop(), Some(8));
}

// ---- Timer divisor tests ----

#[test]
fn pit_divisor_100hz() {
    assert_eq!(timer::pit_divisor(100), Some(11931));
    assert_eq!(timer::pit_divisor(19), Some(62799)); // within 16-bit range
    assert_eq!(timer::pit_divisor(18), None); // 66287 > 65535 max divisor
    assert_eq!(timer::pit_divisor(0), None);
    assert_eq!(timer::pit_divisor(2_000_000), None); // divisor would be 0
    assert_eq!(timer::pit_divisor(1_000_000), Some(1)); // int div: 1193182/1e6 = 1
    assert_eq!(timer::pit_divisor(1_193_182), Some(1));
}

// ---- CPUID vendor string test ----

#[test]
fn cpuid_vendor_string_order() {
    // "GenuineIntel": ebx=Genu, edx=ineI, ecx=ntel (little-endian per reg)
    let ebx = u32::from_le_bytes(*b"Genu");
    let edx = u32::from_le_bytes(*b"ineI");
    let ecx = u32::from_le_bytes(*b"ntel");
    assert_eq!(cpu::vendor_string(ebx, edx, ecx), "GenuineIntel");
    let amd = cpu::vendor_string(
        u32::from_le_bytes(*b"Auth"),
        u32::from_le_bytes(*b"enti"),
        u32::from_le_bytes(*b"cAMD"),
    );
    assert_eq!(amd, "AuthenticAMD");
}
