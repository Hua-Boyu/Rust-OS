// Host-side unit tests for the kernel's pure algorithms.
// The kernel is a no_std/no_main i686 binary and cannot host its own test
// harness, so this crate includes the testable modules via #[path]; privileged
// asm! blocks in those modules are cfg-gated out under test builds.
// This crate is a host test harness, not a non-test kernel library.
#![cfg(test)]
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

#[path = "../../src/memory/mod.rs"]
pub mod memory;

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

#[path = "../../src/fs_commands.rs"]
pub mod fs_commands;

#[path = "../../src/fd.rs"]
pub mod fd;

#[path = "../../src/block.rs"]
pub mod block;
#[cfg(test)]
mod block_tests;

// interrupt.rs is not included here: the x86-interrupt ABI cannot compile on
// the host target. IDT gate encoding is tested via the mirror below.

extern crate alloc;

#[path = "../../src/fs/mod.rs"]
pub mod fs;
#[cfg(test)]
mod fs_tests;

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

// ---- Physical frame allocator tests ----

fn mmap_entry(base: u64, length: u64, type_: u32) -> multiboot::MmapEntry {
    multiboot::MmapEntry {
        size: 20,
        base_addr: base,
        length,
        type_,
    }
}

#[test]
fn frame_of_alignment() {
    assert_eq!(memory::frame::FrameAllocator::frame_of(0), Some(0));
    assert_eq!(memory::frame::FrameAllocator::frame_of(4095), Some(0));
    assert_eq!(memory::frame::FrameAllocator::frame_of(4096), Some(1));
    assert_eq!(memory::frame::FrameAllocator::frame_of(4097), Some(1));
    assert_eq!(memory::frame::FrameAllocator::frame_of(0xB8000), Some(184));
    // above the managed window
    assert_eq!(
        memory::frame::FrameAllocator::frame_of(256 * 1024 * 1024),
        None
    );
}

#[test]
fn frame_allocator_reserves_vga_bootinfo_and_bump() {
    let mut fa = memory::frame::FrameAllocator::new();
    // Usable range 0x10000..0x14000 (4 frames), plus a range covering VGA.
    let entries = [
        mmap_entry(0x10000, 0x4000, 1),
        mmap_entry(0xB8000, 0x4000, 1), // frames 46..47: VGA overlaps frame 46
    ];
    // bootinfo at 0x11000 (frame 17), bump segment 0x12000..0x13000 (frame 18).
    fa.init(&entries, 0x11000, 0x12000, 0x13000);
    assert!(fa.is_initialized());
    // frames 16..19 (range 1) + 184..187 (range 2) = 8
    assert_eq!(fa.stats().total_frames, 8);
    // reserved: frame 17 (bootinfo), 18 (bump), 184..187 (all overlap VGA) = 6
    assert_eq!(fa.stats().reserved_frames, 6);
    assert_eq!(fa.stats().free_frames, 2);
    // reserved frames must never be handed out
    assert!(!fa.is_free(0x11000));
    assert!(!fa.is_free(0x12000));
    assert!(!fa.is_free(0xB8000));
    // free frames are allocatable, in ascending frame order
    assert_eq!(fa.allocate(), Some(0x10000)); // frame 16
    assert_eq!(fa.allocate(), Some(0x13000)); // frame 19
    assert_eq!(fa.allocate(), None); // exhausted, no wraparound
}

#[test]
fn frame_allocator_overlapping_ranges_dedup() {
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [
        mmap_entry(0x10000, 0x4000, 1),
        mmap_entry(0x11000, 0x4000, 1), // overlaps frames 17..19
    ];
    fa.init(&entries, 0x200000, 0x300000, 0x31000);
    // union = frames 16..20 = 5, not 8
    assert_eq!(fa.stats().total_frames, 5);
    assert_eq!(fa.stats().free_frames, 5);
}

#[test]
fn frame_allocator_non_usable_never_free() {
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [
        mmap_entry(0x10000, 0x2000, 1), // frames 16,17 usable
        mmap_entry(0x12000, 0x2000, 2), // ACPI reclaim: reserved
    ];
    fa.init(&entries, 0x200000, 0x300000, 0x31000);
    assert_eq!(fa.stats().total_frames, 2);
    // type-2 frames (18,19) are outside usable coverage but counted reserved
    assert_eq!(fa.stats().reserved_frames, 2);
    assert_eq!(fa.stats().free_frames, 2);
    assert!(!fa.is_free(0x12000));
    assert_eq!(fa.allocate(), Some(0x10000));
    assert_eq!(fa.allocate(), Some(0x11000));
    assert_eq!(fa.allocate(), None);
}

#[test]
fn frame_allocator_alloc_free_cycle_and_rejects() {
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [mmap_entry(0x10000, 0x2000, 1)];
    fa.init(&entries, 0x200000, 0x300000, 0x31000);

    let f = fa.allocate().unwrap();
    assert_eq!(f, 0x10000);
    assert_eq!(fa.stats().allocated_frames, 1);

    // double free rejected
    assert!(fa.free(f));
    assert_eq!(fa.stats().allocated_frames, 0);
    assert!(!fa.free(f));
    assert_eq!(fa.stats().double_frees, 1);

    // freeing a reserved frame rejected
    assert!(!fa.free(0x12000)); // never covered by any usable range
    assert_eq!(fa.stats().invalid_frees, 1);

    // reallocation returns the lowest free frame
    assert_eq!(fa.allocate(), Some(0x10000));
    assert!(fa.free(0x10000));

    // repeated cycles keep stats consistent
    for _ in 0..10 {
        let a = fa.allocate().unwrap();
        assert!(fa.free(a));
    }
    assert_eq!(fa.stats().free_frames, 2);
    assert_eq!(fa.stats().allocated_frames, 0);
}

#[test]
fn frame_allocator_exhaustion() {
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [mmap_entry(0x10000, 0x2000, 1)];
    fa.init(&entries, 0x200000, 0x300000, 0x31000);
    assert_eq!(fa.allocate(), Some(0x10000));
    assert_eq!(fa.allocate(), Some(0x11000));
    assert_eq!(fa.allocate(), None);
    assert_eq!(fa.stats().free_frames, 0);
    // freeing restores capacity
    assert!(fa.free(0x10000));
    assert_eq!(fa.allocate(), Some(0x10000));
}

// ---- Paging tests ----

#[test]
fn frame_free_rejects_reserved_unaligned_and_out_of_bounds() {
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&[mmap_entry(0x10000, 0x4000, 1)], 0x11000, 0x12000, 0x13000);
    assert!(!fa.free(0x11000), "bootloader frame must remain reserved");
    assert!(!fa.free(0x12000), "heap frame must remain reserved");
    let allocated = fa.allocate().unwrap();
    assert!(
        !fa.free(allocated + 1),
        "unaligned free must not release a frame"
    );
    assert!(!fa.free(memory::frame::MAX_FRAME_ADDR));
    assert!(!fa.is_free(allocated));
    assert_eq!(fa.stats().allocated_frames, 1);
    assert_eq!(fa.stats().invalid_frees, 4);
}

#[test]
fn paging_entry_encoding() {
    let e = memory::paging::entry_value(0x200000);
    assert_eq!(e, 0x200000 | 0x3); // present + writable
    assert_eq!(memory::paging::page_dir_index(0x200000), 0);
    assert_eq!(memory::paging::page_dir_index(4 << 22), 4);
    assert_eq!(memory::paging::page_table_index(0x201000), 513); // 0x201 & 0x3FF
}

#[test]
fn paging_error_code_decode() {
    let f = memory::paging::decode_error_code(0b101);
    assert!(f.present && !f.write && f.user);
    let f = memory::paging::decode_error_code(0b010);
    assert!(!f.present && f.write && !f.user);
    let f = memory::paging::decode_error_code(0);
    assert!(!f.present && !f.write && !f.user);
}

#[test]
fn paging_identity_map_build_and_validate() {
    let mut fa = memory::frame::FrameAllocator::new();
    // window 0xC0000 covers VGA; bootinfo inside the window
    let entries = [mmap_entry(0x10000, 0xB0000, 1)];
    fa.init(&entries, 0x10000, 0x11000, 0x12000);
    let pm = memory::paging::build_identity_map(&mut fa, 0xC0000, alloc::vec![0u64; 1024])
        .expect("build");
    // directory + 1 page table allocated from managed frames
    assert_eq!(pm.stats().page_tables, 1);
    assert_eq!(pm.stats().mapped_frames, 0xC0000 / 4096 - 1); // null page absent
    // required regions (test dummy kernel at 0, VGA, bootinfo) all mapped
    let missing =
        memory::paging::validate_mapping(&pm, &memory::required_regions(&entries, 0x10000));
    assert!(missing.is_empty());
    assert!(pm.is_mapped(0xB8000));
    assert!(pm.is_mapped(0x10000));
    assert!(!pm.is_mapped(0xC0000)); // outside window
}

#[test]
fn paging_validate_reports_missing_region() {
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [mmap_entry(0x10000, 0x2000, 1)];
    fa.init(&entries, 0x200000, 0x300000, 0x31000);
    let pm = memory::paging::build_identity_map(&mut fa, 0x12000, alloc::vec![0u64; 1024])
        .expect("build");
    let missing =
        memory::paging::validate_mapping(&pm, &memory::required_regions(&entries, 0x200000));
    assert!(missing.contains(&"VGA framebuffer"));
    assert!(!missing.contains(&"usable mmap range"));
}

#[test]
fn paging_build_fails_on_exhaustion() {
    let mut fa = memory::frame::FrameAllocator::new();
    // only one frame free: enough for the directory, not for a page table
    let entries = [mmap_entry(0x10000, 0x1000, 1)];
    fa.init(&entries, 0x200000, 0x300000, 0x31000);
    assert!(
        memory::paging::build_identity_map(&mut fa, 0xC0000, alloc::vec![0u64; 1024]).is_none()
    );
    assert_eq!(
        fa.stats().free_frames,
        1,
        "failed page-table build must return its frames"
    );
}

#[test]
fn frame_usable_pages_are_complete_and_reserved_entries_override() {
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [
        mmap_entry(0x10001, 0x4FFE, 1),
        mmap_entry(0x12010, 1, 2),
        mmap_entry(0x13000, 0x1000, 3),
        mmap_entry(u64::MAX - 8, 32, 1),
    ];
    fa.init(&entries, 0x200000, 0x300000, 0x310000);
    assert!(!fa.is_free(0x10000), "partial starting page");
    assert!(!fa.is_free(0x14000), "partial ending page");
    assert!(
        !fa.is_free(0x12000),
        "reserved entry overrides usable overlap"
    );
    assert!(!fa.is_free(0x13000), "ACPI entry overrides usable overlap");
    assert_eq!(fa.allocate(), Some(0x11000));
    assert_eq!(fa.allocate(), None);
}

#[test]
fn paging_window_covers_ram_above_frame_allocator_cap() {
    let entries = [mmap_entry(0x100000, 511 * 1024 * 1024, 1)];
    assert_eq!(memory::managed_window_end(&entries), 512 * 1024 * 1024);
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&entries, 0x10000, 0x100000, 0x200000);
    let pm = memory::paging::build_identity_map(
        &mut fa,
        memory::managed_window_end(&entries),
        alloc::vec![0u64; 1024],
    )
    .unwrap();
    assert!(pm.is_mapped(511 * 1024 * 1024));
    assert!(
        memory::paging::validate_mapping(&pm, &memory::required_regions(&entries, 0x10000))
            .is_empty()
    );
}

#[test]
fn mmap_usable_block_rejects_empty_and_overflowing_ranges() {
    let mut bytes = Vec::new();
    for entry in [
        mmap_entry(0x10000, 0, 1),
        mmap_entry(0x10000, u64::MAX, 1),
        mmap_entry(0x200000, 0x400000, 1),
    ] {
        bytes.extend_from_slice(&20u32.to_le_bytes());
        bytes.extend_from_slice(&entry.base_addr.to_le_bytes());
        bytes.extend_from_slice(&entry.length.to_le_bytes());
        bytes.extend_from_slice(&entry.type_.to_le_bytes());
    }
    assert_eq!(
        { multiboot::find_usable_block(&bytes).unwrap().base_addr },
        0x200000
    );
}

#[test]
fn bump_alloc_rejects_arithmetic_overflow() {
    let allocator = utils::mutex::SpinMutex::new(allocator::BumpAlloc {
        start: 0x1000,
        end: usize::MAX,
        next: usize::MAX - 8,
        allocs: 0,
    });
    assert!(unsafe { allocator.alloc(Layout::from_size_align(16, 16).unwrap()) }.is_null());
    assert_eq!(allocator.lock().allocs, 0);
}

#[test]
fn bootstrap_heap_is_page_aligned_and_bounded() {
    let (start, end) = allocator::bootstrap_heap_bounds();
    assert_eq!(start % 4096, 0);
    assert_eq!(end - start, 1024 * 1024);
}

#[test]
fn paging_null_page_is_absent() {
    let entries = [mmap_entry(0x10000, 0x10000, 1)];
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&entries, 0x30000, 0x40000, 0x50000);
    let pm = memory::paging::build_identity_map(&mut fa, 0x20000, alloc::vec![0u64; 1024]).unwrap();
    assert!(!pm.is_mapped(0));
    assert!(pm.is_mapped(0x1000));
}

#[test]
fn paging_validation_checks_partial_tail_page() {
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&[mmap_entry(0x10000, 0x2000, 1)], 0x20000, 0x30000, 0x40000);
    let pm = memory::paging::build_identity_map(&mut fa, 0x2000, alloc::vec![0u64; 1024]).unwrap();
    assert_eq!(
        memory::paging::validate_mapping(&pm, &[(0x1FFF, 0x2001, "tail")]),
        ["tail"]
    );
    assert!(!pm.is_mapped(1u64 << 32));
}

#[test]
fn frame_reserved_range_overflow_is_conservative() {
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(
        &[
            mmap_entry(0x10000, 0x2000, 1),
            mmap_entry(0x11000, u64::MAX, 2),
        ],
        0x200000,
        0x300000,
        0x400000,
    );
    assert_eq!(fa.allocate(), Some(0x10000));
    assert_eq!(fa.allocate(), None);
}

// ---- Phase 5: virtual memory map/unmap/translate tests ----

#[test]
fn paging_map_unmap_translate_and_rejects() {
    let entries = [mmap_entry(0x10000, 0xB0000, 1)];
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&entries, 0x10000, 0x11000, 0x12000);
    let mut pm = memory::paging::build_identity_map(&mut fa, 0xC0000, alloc::vec![0u64; 1024])
        .expect("build");

    // Map a free frame into the growth window.
    let frame = fa.allocate().unwrap();
    let slot = memory::paging::GROWTH_START as u64;
    assert!(pm.map(&mut fa, slot, frame, &memory::paging::KERNEL_PERMS));
    assert!(pm.is_mapped(slot as u64));
    assert_eq!(pm.translate(slot as u64), Some(frame));

    // Duplicate mapping rejected (existing page never overwritten).
    assert!(!pm.map(&mut fa, slot, frame, &memory::paging::KERNEL_PERMS));
    assert_eq!(pm.stats().map_rejects, 1);

    // Unaligned virtual or physical address rejected.
    assert!(!pm.map(&mut fa, slot + 1, frame, &memory::paging::KERNEL_PERMS));
    assert!(!pm.map(&mut fa, slot, frame + 1, &memory::paging::KERNEL_PERMS));
    assert_eq!(pm.stats().map_rejects, 3);

    // Read-only permissions are stored and reported.
    let ro = memory::paging::PagePerms {
        present: true,
        writable: false,
        user: false,
        nx_supported: false,
    };
    let f2 = fa.allocate().unwrap();
    assert!(pm.map(&mut fa, slot + 4096, f2, &ro));
    let p = pm.permissions(slot + 4096).expect("perms");
    assert!(p.present && !p.writable && !p.user && !p.nx_supported);

    // Unmap works; unmapping an absent page is rejected.
    assert!(pm.unmap(slot));
    assert!(!pm.is_mapped(slot as u64));
    assert_eq!(pm.translate(slot), None);
    assert!(!pm.unmap(slot));
    assert_eq!(pm.stats().unmap_rejects, 1);

    // Boot-critical regions cannot be unmapped.
    assert!(!pm.unmap(0xB8000));
    assert_eq!(pm.stats().unmap_rejects, 2);

    // TLB invalidation counted on every successful change (2 maps + 1 unmap).
    assert_eq!(pm.stats().tlb_invalidation, 3);
}

#[test]
fn paging_map_rejects_out_of_window_and_unaligned_translate() {
    let entries = [mmap_entry(0x10000, 0x10000, 1)];
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&entries, 0x20000, 0x30000, 0x40000);
    let mut pm = memory::paging::build_identity_map(&mut fa, 0x20000, alloc::vec![0u64; 1024])
        .expect("build");
    let frame = fa.allocate().unwrap();
    // Outside the managed window and outside the growth window: rejected.
    assert!(!pm.map(&mut fa, 0x100000, frame, &memory::paging::KERNEL_PERMS));
    // Physical frame above the frame cap: rejected.
    assert!(!pm.map(
        &mut fa,
        memory::paging::GROWTH_START as u64,
        memory::frame::MAX_FRAME_ADDR,
        &memory::paging::KERNEL_PERMS
    ));
    assert_eq!(pm.stats().map_rejects, 2);
    // Unaligned translate returns None.
    assert_eq!(pm.translate(0x10001), None);
}

#[test]
fn heap_growth_maps_one_page_on_demand() {
    // Usable range must cover the growth window: growth maps identity frames
    // inside it (virtual == physical).
    let entries = [mmap_entry(0x10000, 0x800000, 1)];
    assert!(memory::prepare(&entries, 0x20000, 0x30000, 0x40000).is_ok());
    let slot = memory::paging::GROWTH_START;
    let pm = memory::page_map_ref().expect("page map");
    // Growth window pages are unmapped until growth maps them.
    assert!(!pm.is_mapped(slot as u64));
    let frame = memory::heap_grow_frame(slot).expect("growth frame");
    assert_eq!(frame, slot as u64); // identity: virtual == physical
    assert!(pm.is_mapped(slot as u64));
    assert_eq!(pm.translate(slot as u64), Some(frame));
    // Claiming the same frame twice is rejected.
    assert!(
        memory::FRAME_ALLOC
            .lock()
            .claim_growth_frame(slot as u64)
            .is_none()
    );
    // Second growth page maps independently.
    let f2 = memory::heap_grow_frame(slot + 4096).expect("growth frame 2");
    assert_eq!(pm.translate((slot + 4096) as u64), Some(f2));
}

#[test]
fn fault_decode_includes_fetch_bit() {
    let f = memory::paging::decode_error_code(0b10000);
    assert!(f.fetch && !f.present && !f.write && !f.user);
    let f = memory::paging::decode_error_code(0b10011);
    assert!(f.present && f.write && !f.user && f.fetch);
}

// ---- Phase 5: dynamic kernel heap tests ----

#[test]
fn heap_alloc_free_reuse_and_stats() {
    let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
    heap.lock().add_region(0x100000, 0x101000); // 4 KiB region

    let l1 = Layout::from_size_align(64, 8).unwrap();
    let p1 = unsafe { heap.alloc(l1) };
    assert!(!p1.is_null());
    assert_eq!(p1 as usize, 0x100008); // 8-byte header before payload

    let s = heap.lock().stats;
    assert_eq!(s.capacity, 4096);
    assert_eq!(s.used, 72);
    assert_eq!(s.live_allocs, 1);
    assert_eq!(s.free, 4096 - 72);

    unsafe { heap.dealloc(p1, l1) };
    let s = heap.lock().stats;
    assert_eq!(s.used, 0);
    assert_eq!(s.live_allocs, 0);
    assert_eq!(s.free_blocks, 1);
    assert_eq!(s.free, 4096);

    // Freed memory is reused: same address on reallocation.
    let p2 = unsafe { heap.alloc(l1) };
    assert_eq!(p2 as usize, p1 as usize);
    unsafe { heap.dealloc(p2, l1) };
}

#[test]
fn heap_alignment_and_fragmentation() {
    let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
    heap.lock().add_region(0x200000, 0x201000);

    // Small odd-size alloc, then a 16-byte-aligned alloc: payload must be
    // aligned to 16 even though the header sits at the region start.
    let small = Layout::from_size_align(3, 1).unwrap();
    let p1 = unsafe { heap.alloc(small) };
    assert_eq!(p1 as usize, 0x200008);
    let aligned = Layout::from_size_align(8, 16).unwrap();
    let p2 = unsafe { heap.alloc(aligned) };
    assert_eq!(p2 as usize % 16, 0);
    assert_eq!(p2 as usize, 0x200020); // header at 0x200018, payload aligned

    unsafe { heap.dealloc(p1, small) };
    unsafe { heap.dealloc(p2, aligned) };
    // p1's block (11 bytes incl. header) is fragmented separately; p2's
    // block merges with the tail remainder.
    let s = heap.lock().stats;
    assert_eq!(s.live_allocs, 0);
    assert_eq!(s.free_blocks, 2);
    assert_eq!(s.waste, 13); // prefix before the aligned header (0x200013 -> 0x200020)
}

#[test]
fn heap_coalesces_adjacent_free_blocks() {
    let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
    heap.lock().add_region(0x300000, 0x300100); // 256 bytes

    let a = Layout::from_size_align(64, 1).unwrap();
    let b = Layout::from_size_align(64, 1).unwrap();
    let p1 = unsafe { heap.alloc(a) };
    let p2 = unsafe { heap.alloc(b) };
    assert_eq!(p2 as usize, p1 as usize + 72); // adjacent blocks

    unsafe { heap.dealloc(p2, b) };
    unsafe { heap.dealloc(p1, a) }; // reverse order: must coalesce
    let s = heap.lock().stats;
    assert_eq!(s.free_blocks, 1);
    assert_eq!(s.largest_free, 256);
}

#[test]
fn heap_oom_and_invalid_dealloc_are_safe() {
    let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
    heap.lock().add_region(0x400000, 0x400040); // 64 bytes: one 32-byte alloc fits

    let ok = Layout::from_size_align(24, 1).unwrap();
    let p = unsafe { heap.alloc(ok) };
    assert!(!p.is_null());

    // Exhausted: null, counted, no panic.
    let big = Layout::from_size_align(64, 1).unwrap();
    assert!(unsafe { heap.alloc(big) }.is_null());
    assert_eq!(heap.lock().stats.failed_allocs, 1);

    // Foreign pointer (never allocated): header garbage rejected.
    let foreign = (0x400030) as *mut u8;
    unsafe { heap.dealloc(foreign, ok) };
    assert_eq!(heap.lock().stats.invalid_deallocs, 1);

    // The live allocation is still valid and can be freed.
    unsafe { heap.dealloc(p, ok) };
    let s = heap.lock().stats;
    assert_eq!(s.live_allocs, 0);
}

#[test]
fn heap_growth_disabled_in_host_tests_and_stats_are_consistent() {
    let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
    // Growth is disabled in host tests (grow_next = 0): OOM without hang.
    let l = Layout::from_size_align(16, 1).unwrap();
    assert!(unsafe { heap.alloc(l) }.is_null()); // no regions at all
    let s = heap.lock().stats;
    assert_eq!(s.failed_allocs, 1);
    assert_eq!(s.growth_pages, 0);
    assert_eq!(s.used + s.free, s.capacity); // accounting invariant
}

// ---- Phase 5 performance baseline (recorded, not optimized) ----

#[cfg(test)]
mod maintenance_measurements;

#[test]
fn perf_baseline_records_latencies() {
    use core::alloc::Layout;
    // Isolated instances: host tests run in parallel, so global state is unsafe here.
    let mut fa = memory::frame::FrameAllocator::new();
    let entries = [mmap_entry(0x10000, 0x800000, 1)];
    fa.init(&entries, 0x10000, 0x11000, 0x12000);
    let mut pm = memory::paging::build_identity_map(&mut fa, 0xC0000, alloc::vec![0u64; 1024])
        .expect("build");

    // Frame allocation latency: 1000 allocations.
    let t0 = std::time::Instant::now();
    let mut frames = Vec::new();
    for _ in 0..1000 {
        frames.push(fa.allocate().expect("frame"));
    }
    let frame_alloc_ns = t0.elapsed().as_nanos() as f64 / 1000.0;
    let t1 = std::time::Instant::now();
    for f in &frames {
        fa.free(*f);
    }
    let frame_free_ns = t1.elapsed().as_nanos() as f64 / 1000.0;

    // Map/unmap latency in the growth window (1000 ops each).
    let t2 = std::time::Instant::now();
    for i in 0..1000 {
        let v = memory::paging::GROWTH_START as u64 + i * 4096;
        assert!(pm.map(&mut fa, v, v, &memory::paging::KERNEL_PERMS));
    }
    let map_ns = t2.elapsed().as_nanos() as f64 / 1000.0;
    let t3 = std::time::Instant::now();
    for i in 0..1000 {
        assert!(pm.unmap(memory::paging::GROWTH_START as u64 + i * 4096));
    }
    let unmap_ns = t3.elapsed().as_nanos() as f64 / 1000.0;

    // Heap alloc/dealloc latency: 1000 mixed-size ops on an isolated heap.
    // Region must cover the workload (~1.2 MB) so alloc never returns null.
    let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
    heap.lock().add_region(0x1000000, 0x1000000 + 4096 * 512);
    let sizes = [8usize, 64, 256, 1024, 4096];
    let t4 = std::time::Instant::now();
    let mut ptrs = Vec::new();
    for &s in sizes.iter().cycle().take(1000) {
        let p = unsafe { heap.alloc(Layout::from_size_align(s, 8).unwrap()) };
        assert!(!p.is_null(), "heap must not OOM on a sized region");
        ptrs.push(p);
    }
    let heap_alloc_ns = t4.elapsed().as_nanos() as f64 / 1000.0;
    let t5 = std::time::Instant::now();
    for (i, &p) in ptrs.iter().enumerate() {
        unsafe { heap.dealloc(p, Layout::from_size_align(sizes[i % 5], 8).unwrap()) };
    }
    let heap_free_ns = t5.elapsed().as_nanos() as f64 / 1000.0;

    // Fragmentation under a representative checkerboard workload:
    // allocate 500 blocks, free every other one.
    let mut small = Vec::new();
    for _ in 0..500 {
        small.push(unsafe { heap.alloc(Layout::from_size_align(48, 8).unwrap()) });
    }
    for (i, &p) in small.iter().enumerate() {
        if i % 2 == 0 {
            unsafe { heap.dealloc(p, Layout::from_size_align(48, 8).unwrap()) };
        }
    }
    let frag = heap.lock().stats;
    // 250 isolated freed blocks (each separated by a live neighbour) plus the
    // large tail remainder = 251 free blocks.
    assert_eq!(
        frag.free_blocks, 251,
        "checkerboard leaves 250 isolated + tail"
    );

    std::println!(
        "PERF BASELINE ns/op: frame_alloc {:.1} frame_free {:.1} map {:.1} unmap {:.1}          heap_alloc {:.1} heap_free {:.1}; checkerboard: {} free blocks, waste {} bytes",
        frame_alloc_ns,
        frame_free_ns,
        map_ns,
        unmap_ns,
        heap_alloc_ns,
        heap_free_ns,
        frag.free_blocks,
        frag.waste
    );
}

#[cfg(test)]
mod b18_inventory_tests;

#[cfg(test)]
mod b18_outcome_tests;
