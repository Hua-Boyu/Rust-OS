//! Independent wire-format fixtures: no production encoders or physical reads.
use crate::memory::frame::FrameAllocator;
use crate::multiboot::inventory::{self, BootError, Inventory};

const ROOT: u64 = 0x5000;
const MAP: u64 = 0x6000;
const TABLE: u64 = 0x20000;
const KERNEL: (u64, u64) = (0x100000, 0x180000);

fn put(bytes: &mut [u8], offset: usize, value: u32) {
    bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}
fn entry(base: u64, length: u64, kind: u32, extension: usize) -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&(20 + extension as u32).to_le_bytes());
    bytes.extend_from_slice(&base.to_le_bytes());
    bytes.extend_from_slice(&length.to_le_bytes());
    bytes.extend_from_slice(&kind.to_le_bytes());
    bytes.resize(24 + extension, 0xa5);
    bytes
}
struct Physical {
    regions: Vec<(u64, Vec<u8>)>,
    reads: Vec<(u64, usize)>,
}
impl Physical {
    fn new() -> Self {
        let mut header = vec![0; 88];
        put(&mut header, 0, 1 << 6);
        let mut f = Self {
            regions: vec![(ROOT, header)],
            reads: Vec::new(),
        };
        f.map(entry(0, 0x2000000, 1, 0));
        f
    }
    fn field(&mut self, offset: usize, value: u32) {
        put(&mut self.regions[0].1, offset, value);
    }
    fn flags(&mut self, flags: u32) {
        self.field(0, flags | (1 << 6));
    }
    fn map(&mut self, bytes: Vec<u8>) {
        self.field(44, bytes.len() as u32);
        self.field(48, MAP as u32);
        self.regions.retain(|(start, _)| *start != MAP);
        self.regions.push((MAP, bytes));
    }
    fn add(&mut self, start: u64, bytes: &[u8]) {
        self.regions.push((start, bytes.to_vec()));
    }
    fn modules(&mut self, descriptors: &[(u32, u32, u32, u32)]) {
        self.flags(1 << 3);
        self.field(20, descriptors.len() as u32);
        self.field(24, TABLE as u32);
        let mut bytes = Vec::new();
        for &(a, b, c, d) in descriptors {
            for word in [a, b, c, d] {
                bytes.extend_from_slice(&word.to_le_bytes());
            }
        }
        self.add(TABLE, &bytes);
    }
    fn read(&mut self, start: u64, out: &mut [u8]) -> Result<(), BootError> {
        self.reads.push((start, out.len()));
        let end = start
            .checked_add(out.len() as u64)
            .ok_or(BootError::Address)?;
        // Missing backing is never silently synthesized as zero-filled RAM.
        let (base, bytes) = self
            .regions
            .iter()
            .find(|(base, bytes)| *base <= start && end <= *base + bytes.len() as u64)
            .ok_or(BootError::Truncated)?;
        let offset = (start - base) as usize;
        out.copy_from_slice(&bytes[offset..offset + out.len()]);
        Ok(())
    }
    fn parse(&mut self) -> Result<Inventory, BootError> {
        inventory::parse(inventory::MAGIC, ROOT, KERNEL, |a, b| self.read(a, b))
    }
}
fn error(result: Result<Inventory, BootError>, expected: BootError) {
    assert_eq!(result.err(), Some(expected));
}

#[test]
fn magic_rejection_never_calls_source() {
    error(
        inventory::parse(0, ROOT, KERNEL, |_, _| panic!("bad magic read")),
        BootError::Magic,
    );
}
#[test]
fn root_bounds_rejected_before_read() {
    for root in [0, 4095, 0xa0000 - 87, 0xa0000, u64::MAX - 40] {
        error(
            inventory::parse(inventory::MAGIC, root, KERNEL, |_, _| {
                panic!("invalid root read")
            }),
            BootError::Address,
        );
    }
    error(
        inventory::parse(inventory::MAGIC, ROOT, (ROOT, ROOT + 88), |_, _| {
            panic!("kernel read")
        }),
        BootError::Address,
    );
}
#[test]
fn missing_header_is_truncated() {
    let mut f = Physical::new();
    f.regions[0].1.truncate(87);
    error(f.parse(), BootError::Truncated);
    assert_eq!(f.reads, [(ROOT, 88)]);
}
#[test]
fn malformed_and_unsupported_flags_rejected() {
    for flags in [
        0,
        (1 << 6) | (1 << 31),
        (1 << 6) | (3 << 4),
        (1 << 6) | (1 << 8),
        (1 << 6) | (1 << 12),
    ] {
        let mut f = Physical::new();
        f.field(0, flags);
        error(f.parse(), BootError::Flags);
    }
}
#[test]
fn grub_vga_text_framebuffer_is_bounded_and_pinned() {
    let mut f = Physical::new();
    f.regions[0].1.resize(116, 0);
    f.flags(1 << 12);
    f.field(88, 0xb8000);
    f.field(96, 160);
    f.field(100, 80);
    f.field(104, 25);
    f.regions[0].1[108] = 16;
    f.regions[0].1[109] = 2;
    let inv = f.parse().expect("GRUB text framebuffer is supported");
    assert!(inv.reservations.contains(&(ROOT, ROOT + 116)));
    assert!(inv.reservations.contains(&(0xb8000, 0xb8fa0)));
}

#[test]
fn zero_length_reserved_records_do_not_deny_metadata_or_module_bytes() {
    let mut f = Physical::new();
    let mut map = entry(0, 0x2000000, 1, 0);
    for start in [TABLE + 1, 0x300001, 0x400001] {
        map.extend(entry(start, 0, 2, 0));
    }
    f.map(map);
    f.modules(&[(0x300000, 0x301000, 0x400000, 0)]);
    f.add(0x400000, b"module\0");
    assert!(f.parse().is_ok(), "empty spans cannot overlap live bytes");
}

#[test]
fn mmap_pointer_bounds_precede_callback() {
    for pointer in [0, 4095, 0xa0000 - 23, 0xfffffff0] {
        let mut f = Physical::new();
        f.field(48, pointer);
        error(f.parse(), BootError::Address);
        assert_eq!(f.reads, [(ROOT, 88)]);
    }
}
#[test]
fn mmap_length_limits_precede_callback() {
    for length in [0, 128 * 256 + 1, u32::MAX] {
        let mut f = Physical::new();
        f.field(44, length);
        error(f.parse(), BootError::Limit);
        assert_eq!(f.reads, [(ROOT, 88)]);
    }
}
#[test]
fn missing_mmap_backing_is_not_implicitly_zero() {
    let mut f = Physical::new();
    f.regions[1].1.pop();
    error(f.parse(), BootError::Truncated);
}
#[test]
fn mmap_variable_records_keep_full_width_fields() {
    let mut f = Physical::new();
    let mut map = entry(0, 0x2000000, 1, 12);
    map.extend(entry(0x1_0000_1234, 0x2_0000_5678, 2, 4));
    f.map(map);
    let inv = f.parse().unwrap();
    assert_eq!(inv.entries.len(), 2);
    let e = inv.entries[1];
    let (base, len, kind, size) = (e.base_addr, e.length, e.type_, e.size);
    assert_eq!(
        (base, len, kind, size),
        (0x1_0000_1234, 0x2_0000_5678, 2, 24)
    );
}
#[test]
fn mmap_rejects_malformed_sizes_trailing_fragments_and_overflow() {
    for size in [0, 19, 21, u32::MAX] {
        let mut f = Physical::new();
        let mut map = entry(0, 0x2000000, 1, 0);
        put(&mut map, 0, size);
        f.map(map);
        error(f.parse(), BootError::Map);
    }
    for n in 1..4 {
        let mut f = Physical::new();
        let mut map = entry(0, 0x2000000, 1, 0);
        map.extend(vec![0; n]);
        f.map(map);
        error(f.parse(), BootError::Truncated);
    }
    let mut f = Physical::new();
    f.map(entry(u64::MAX - 3, 4, 1, 0));
    error(f.parse(), BootError::Address);
}
#[test]
fn mmap_requires_nonempty_usable_record() {
    for (length, kind) in [(0, 1), (4096, 2), (4096, 3)] {
        let mut f = Physical::new();
        f.map(entry(0x1000, length, kind, 0));
        error(f.parse(), BootError::Map);
    }
}
#[test]
fn mmap_record_count_boundary() {
    for count in [128, 129] {
        let mut f = Physical::new();
        f.map(entry(0, 0x2000000, 1, 0).repeat(count));
        if count == 128 {
            assert_eq!(f.parse().unwrap().entries.len(), 128);
        } else {
            error(f.parse(), BootError::Limit);
        }
    }
}
#[test]
fn bootstrap_map_and_header_can_be_firmware_reserved() {
    let mut f = Physical::new();
    let mut map = entry(0, 0x2000000, 1, 0);
    map.extend(entry(ROOT, 0x2000, 2, 0));
    f.map(map);
    let inv = f.parse().unwrap();
    assert!(inv.reservations.contains(&(ROOT, ROOT + 88)));
    assert!(inv.reservations.contains(&(MAP, MAP + 48)));
}
#[test]
fn module_count_limit_precedes_table_access() {
    let mut f = Physical::new();
    f.flags(1 << 3);
    f.field(20, 33);
    f.field(24, 0);
    error(f.parse(), BootError::Limit);
    assert_eq!(f.reads.len(), 2);
}
#[test]
fn zero_modules_does_not_dereference_null_table() {
    let mut f = Physical::new();
    f.flags(1 << 3);
    assert!(f.parse().unwrap().modules.is_empty());
    assert_eq!(f.reads.len(), 2);
}
#[test]
fn maximum_modules_accepted_without_reading_payloads() {
    let mut f = Physical::new();
    let descriptors: Vec<_> = (0..32)
        .map(|i| (0x200000 + i * 0x2000, 0x201000 + i * 0x2000, 0, 0))
        .collect();
    f.modules(&descriptors);
    let inv = f.parse().unwrap();
    assert_eq!(inv.modules.len(), 32);
    assert_eq!(f.reads.len(), 34); // header, map, exactly 32 descriptors
}
#[test]
fn module_table_must_be_backed_and_inside_validated_ram() {
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0, 0)]);
    f.regions.last_mut().unwrap().1.truncate(15);
    error(f.parse(), BootError::Truncated);
    for address in [0, 4095, 0xfffffff8, 0x100000, 0x800000, 0xdffff8, 0x3000000] {
        let mut f = Physical::new();
        f.modules(&[(0x300000, 0x301000, 0, 0)]);
        f.field(24, address);
        error(f.parse(), BootError::Address);
        assert_eq!(f.reads.len(), 2);
    }
}
#[test]
fn module_invalid_end_reserved_word_and_null_rejected() {
    for descriptor in [
        (0x300000, 0x300000, 0, 0),
        (0x301000, 0x300000, 0, 0),
        (0x300000, 0x301000, 0, 1),
        (0, 4096, 0, 0),
    ] {
        let mut f = Physical::new();
        f.modules(&[descriptor]);
        assert!(f.parse().is_err());
    }
}
#[test]
fn module_denied_for_kernel_growth_and_unknown_ram() {
    for (a, b) in [
        (0x100000, 0x101000),
        (0x17ffff, 0x180001),
        (0x7fffff, 0x800001),
        (0xdfffff, 0xe00001),
        (0x3000000, 0x3001000),
    ] {
        let mut f = Physical::new();
        f.modules(&[(a, b, 0, 0)]);
        error(f.parse(), BootError::Address);
    }
}
#[test]
fn reserved_map_record_wins_for_module_table_payload_and_string() {
    for reserved in [TABLE, 0x300000, 0x400000] {
        for reverse in [false, true] {
            let mut f = Physical::new();
            let usable = entry(0, 0x2000000, 1, 0);
            let deny = entry(reserved, 1, 2, 0);
            f.map(if reverse {
                [deny, usable].concat()
            } else {
                [usable, deny].concat()
            });
            f.modules(&[(0x300000, 0x301000, 0x400000, 0)]);
            f.add(0x400000, b"name\0");
            error(f.parse(), BootError::Address);
            assert!(!f.reads.iter().any(|&(a, _)| a == reserved));
        }
    }
}
#[test]
fn module_overlaps_previous_module_or_boot_metadata_rejected() {
    for (a, b) in [
        (ROOT as u32, ROOT as u32 + 1),
        (MAP as u32, MAP as u32 + 1),
        (TABLE as u32, TABLE as u32 + 1),
        (0x300fff, 0x302000),
    ] {
        let mut f = Physical::new();
        f.modules(&[(0x300000, 0x301000, 0, 0), (a, b, 0, 0)]);
        error(f.parse(), BootError::Module);
    }
}
#[test]
fn adjacent_modules_are_not_overlaps() {
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0, 0), (0x301000, 0x302000, 0, 0)]);
    assert_eq!(f.parse().unwrap().modules.len(), 2);
}
#[test]
fn module_overlap_with_own_name_or_later_metadata_rejected() {
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0x300000, 0)]);
    f.add(0x300000, b"x\0");
    error(f.parse(), BootError::Module);
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0, 0)]);
    f.flags((1 << 3) | (1 << 7));
    f.field(52, 1);
    f.field(56, 0x300fff);
    error(f.parse(), BootError::Module);
}
#[test]
fn command_and_loader_strings_reserve_terminators() {
    let mut f = Physical::new();
    f.flags((1 << 2) | (1 << 9));
    f.field(16, 0x300000);
    f.field(64, 0x400000);
    f.add(0x300000, b"args\0");
    f.add(0x400000, b"\0");
    let inv = f.parse().unwrap();
    assert!(inv.reservations.contains(&(0x300000, 0x300005)));
    assert!(inv.reservations.contains(&(0x400000, 0x400001)));
}
#[test]
fn null_required_strings_rejected_but_null_module_name_optional() {
    for (bit, off) in [(2, 16), (9, 64)] {
        let mut f = Physical::new();
        f.flags(1 << bit);
        f.field(off, 0);
        error(f.parse(), BootError::Address);
        assert_eq!(f.reads.len(), 2);
    }
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0, 0)]);
    assert!(f.parse().is_ok());
}
#[test]
fn string_missing_backing_and_unterminated_bound() {
    let mut f = Physical::new();
    f.flags(1 << 2);
    f.field(16, 0x300000);
    f.add(0x300000, b"x");
    error(f.parse(), BootError::Truncated);
    let mut f = Physical::new();
    f.flags(1 << 2);
    f.field(16, 0x300000);
    f.add(0x300000, &vec![b'x'; 4097]);
    error(f.parse(), BootError::String);
    assert_eq!(f.reads.len(), 4098);
    assert!(!f.reads.iter().any(|&(a, _)| a == 0x301000));
}
#[test]
fn final_permitted_string_byte_can_be_terminator() {
    let mut f = Physical::new();
    f.flags(1 << 2);
    f.field(16, 0x300000);
    let mut bytes = vec![b'x'; 4096];
    bytes[4095] = 0;
    f.add(0x300000, &bytes);
    assert!(
        f.parse()
            .unwrap()
            .reservations
            .contains(&(0x300000, 0x301000))
    );
}
#[test]
fn string_stops_before_kernel_growth_or_reserved_byte() {
    for boundary in [KERNEL.0, 0x800000, 0x300001] {
        let mut f = Physical::new();
        f.flags(1 << 2);
        f.field(16, (boundary - 1) as u32);
        f.add(boundary - 1, b"x\0");
        if boundary == 0x300001 {
            let mut m = entry(0, 0x2000000, 1, 0);
            m.extend(entry(boundary, 1, 2, 0));
            f.map(m);
        }
        error(f.parse(), BootError::Address);
        assert!(!f.reads.iter().any(|&(a, _)| a == boundary));
    }
}
#[test]
fn optional_metadata_spans_reserved_and_overflow_rejected() {
    let mut f = Physical::new();
    f.flags((1 << 7) | (1 << 5) | (1 << 10) | (1 << 11));
    for (off, value) in [
        (52, 32),
        (56, 0x300000),
        (28, 4),
        (32, 16),
        (36, 0x310000),
        (68, 0x320000),
        (72, 0x330000),
        (76, 0x340000),
    ] {
        f.field(off, value);
    }
    let inv = f.parse().unwrap();
    for range in [
        (0x300000, 0x300020),
        (0x310000, 0x310040),
        (0x320000, 0x320014),
        (0x330000, 0x330200),
        (0x340000, 0x340100),
    ] {
        assert!(inv.reservations.contains(&range));
    }
    assert_eq!(f.reads.len(), 2); // opaque spans validated/reserved, not dereferenced
    let mut f = Physical::new();
    f.flags(1 << 5);
    f.field(28, u32::MAX);
    f.field(32, u32::MAX);
    f.field(36, 0x300000);
    error(f.parse(), BootError::Address);
}
#[test]
fn absent_flags_do_not_follow_garbage_optional_pointers() {
    let mut f = Physical::new();
    for offset in [
        16, 20, 24, 28, 32, 36, 40, 52, 56, 60, 64, 68, 72, 76, 80, 84,
    ] {
        f.field(offset, u32::MAX);
    }
    assert!(f.parse().is_ok());
    assert_eq!(f.reads, [(ROOT, 88), (MAP, 24)]);
}

#[test]
fn aout_symbol_sizes_are_summed_in_full_width() {
    let mut f = Physical::new();
    f.flags(1 << 4);
    f.field(28, 24);
    f.field(32, 32);
    f.field(36, 0x300000);
    assert!(
        f.parse()
            .unwrap()
            .reservations
            .contains(&(0x300000, 0x30003c))
    );
    let mut f = Physical::new();
    f.flags(1 << 4);
    f.field(28, u32::MAX);
    f.field(32, u32::MAX);
    f.field(36, 0x300000);
    error(f.parse(), BootError::Address);
}

#[test]
fn aout_leading_size_word_and_final_partial_page_are_reserved() {
    let mut f = Physical::new();
    f.flags(1 << 4);
    f.field(28, 24);
    f.field(32, 32);
    f.field(36, 0x300fc8);
    let inv = f.parse().unwrap();
    assert!(inv.reservations.contains(&(0x300fc8, 0x301004)));
    let mut frames = FrameAllocator::new();
    assert!(frames.init_with_reservations(
        &inv.entries,
        ROOT,
        0x600000,
        0x700000,
        &inv.reservations
    ));
    assert!(!frames.is_free(0x301000));
}

#[test]
fn aout_final_size_word_intersections_and_reserved_field_are_rejected() {
    for (start, reserved) in [(0x7fffc8, false), (0x300fc8, true)] {
        let mut f = Physical::new();
        f.flags(1 << 4);
        f.field(28, 24);
        f.field(32, 32);
        f.field(36, start);
        if reserved {
            let mut map = entry(0, 0x2000000, 1, 0);
            map.extend(entry(0x301000, 1, 2, 0));
            f.map(map);
        }
        error(f.parse(), BootError::Address);
    }
    let mut f = Physical::new();
    f.flags(1 << 4);
    f.field(28, 24);
    f.field(32, 32);
    f.field(36, 0x300000);
    f.field(40, 1);
    error(f.parse(), BootError::Flags);
}

#[test]
fn bootstrap_upper_boundary_is_exclusive_not_last_byte() {
    let mut f = Physical::new();
    f.regions[0].0 = 0xa0000 - 88;
    let inv =
        inventory::parse(inventory::MAGIC, 0xa0000 - 88, KERNEL, |a, b| f.read(a, b)).unwrap();
    assert!(inv.reservations.contains(&(0xa0000 - 88, 0xa0000)));
    let mut f = Physical::new();
    f.field(48, 0xa0000 - 24);
    f.regions[1].0 = 0xa0000 - 24;
    assert!(
        f.parse()
            .unwrap()
            .reservations
            .contains(&(0xa0000 - 24, 0xa0000))
    );
}

#[test]
fn module_cannot_bridge_a_gap_between_usable_records() {
    let mut f = Physical::new();
    let mut map = entry(0, 0xa0000, 1, 0);
    map.extend(entry(0x300000, 4096, 1, 0));
    map.extend(entry(0x302000, 4096, 1, 0));
    f.map(map);
    f.modules(&[(0x300000, 0x303000, 0, 0)]);
    error(f.parse(), BootError::Address);
}

#[test]
fn vbe_interface_is_pinned_or_entire_feature_rejected() {
    // Multiboot v1 bytes 82/84/86 are u16 segment/offset/length.
    // Accepting bit 11 must not silently free this third VBE-owned span.
    let mut f = Physical::new();
    f.flags(1 << 11);
    f.field(72, 0x330000);
    f.field(76, 0x340000);
    f.regions[0].1[82..84].copy_from_slice(&0x9000u16.to_le_bytes());
    f.regions[0].1[84..86].copy_from_slice(&0x0fffu16.to_le_bytes());
    f.regions[0].1[86..88].copy_from_slice(&0x1002u16.to_le_bytes());
    if let Ok(inv) = f.parse() {
        assert!(
            inv.reservations
                .iter()
                .any(|&(a, b)| a <= 0x90fff && b >= 0x92001),
            "accepted VBE interface must remain pinned until reboot"
        );
    }
}

#[test]
fn accepted_inventory_pins_every_partial_frame_after_source_dropped() {
    let inv = {
        let mut f = Physical::new();
        f.modules(&[(0x300fff, 0x302001, 0x400fff, 0)]);
        f.add(0x400fff, b"name\0");
        f.parse().unwrap()
    };
    let mut frames = FrameAllocator::new();
    assert!(frames.init_with_reservations(
        &inv.entries,
        ROOT,
        0x600000,
        0x700000,
        &inv.reservations
    ));
    for &(start, end) in &inv.reservations {
        for page in (start / 4096..=(end - 1) / 4096).map(|p| p * 4096) {
            assert!(
                !frames.is_free(page),
                "inventory frame {page:#x} must be pinned"
            );
            assert!(!frames.free(page), "pinned frame must not be releasable");
        }
    }
    assert!(
        frames.is_free(0x303000),
        "adjacent unreserved RAM remains usable"
    );
    let free = frames.stats().free_frames;
    for _ in 0..free {
        let page = frames.allocate().unwrap();
        assert!(
            inv.reservations
                .iter()
                .all(|&(a, b)| page + 4096 <= a || page >= b)
        );
    }
    assert_eq!(frames.allocate(), None);
}

#[test]
fn initramfs_owned_label_and_span_survive_source_drop() {
    let inv = {
        let mut f = Physical::new();
        f.modules(&[(0x300fff, 0x302001, 0x400fff, 0)]);
        f.add(0x400fff, b"rosti.initramfs\0");
        f.parse().unwrap()
    };
    let selected = inv.select_initramfs().unwrap().unwrap();
    assert_eq!(selected.range, (0x300fff, 0x302001));
    assert_eq!(selected.name.as_str(), Some("rosti.initramfs"));
    assert_eq!(inv.modules, [selected.range]);
    assert_eq!(inv.module_descriptors.len(), 1);
    assert!(
        inv.reservations
            .contains(&(0x400fff, 0x400fff + b"rosti.initramfs\0".len() as u64))
    );
    let mut frames = FrameAllocator::new();
    assert!(frames.init_with_reservations(
        &inv.entries,
        ROOT,
        0x600000,
        0x700000,
        &inv.reservations
    ));
    for &(a, b) in &inv.reservations {
        for page in a / 4096..=(b - 1) / 4096 {
            assert!(!frames.is_free(page * 4096));
            assert!(!frames.free(page * 4096));
        }
    }
    while let Some(page) = frames.allocate() {
        assert!(
            inv.reservations
                .iter()
                .all(|&(a, b)| page + 4096 <= a || page >= b)
        );
    }
}

#[test]
fn initramfs_absent_and_nonexact_labels_are_ignored() {
    assert!(
        Physical::new()
            .parse()
            .unwrap()
            .select_initramfs()
            .unwrap()
            .is_none()
    );
    for name in [
        None,
        Some(&b"\0"[..]),
        Some(&b"other\0"[..]),
        Some(&b"ROSTI.INITRAMFS\0"[..]),
        Some(&b"rosti.initramfs args\0"[..]),
        Some(&b"rosti.initramfs/\0"[..]),
        Some(&b"rosti.initramfs\xff\0"[..]),
        Some(&b"rosti.initramfs\n\0"[..]),
    ] {
        let mut f = Physical::new();
        f.modules(&[(
            0x300000,
            0x301000,
            if name.is_some() { 0x400000 } else { 0 },
            0,
        )]);
        if let Some(bytes) = name {
            f.add(0x400000, bytes);
        }
        let inv = f.parse().unwrap();
        assert!(inv.select_initramfs().unwrap().is_none());
    }
}

#[test]
fn initramfs_mixed_modules_select_exact_match_in_any_position() {
    for position in 0..3 {
        let mut f = Physical::new();
        let mut descriptors = [
            (0x300000, 0x301000, 0, 0),
            (0x302000, 0x303000, 0x400000, 0),
            (0x304000, 0x305000, 0x401000, 0),
        ];
        descriptors.swap(2, position);
        f.modules(&descriptors);
        f.add(0x400000, b"other\0");
        f.add(0x401000, b"rosti.initramfs\0");
        let inv = f.parse().unwrap();
        assert_eq!(
            inv.select_initramfs().unwrap().unwrap().range,
            (0x304000, 0x305000)
        );
        assert_eq!(inv.module_descriptors.len(), inv.modules.len());
        for (descriptor, range) in inv.module_descriptors.iter().zip(&inv.modules) {
            assert_eq!(&descriptor.range, range);
        }
    }
    // Inline name storage: no pointer-sized String or per-name heap backing.
    assert_eq!(core::mem::size_of::<inventory::ModuleName>(), 64);
    assert!(core::mem::size_of::<inventory::ModuleDescriptor>() <= 80);
}

#[test]
fn initramfs_oversized_name_still_validates_every_metadata_byte() {
    let mut f = Physical::new();
    let boundary = 0x400000 + inventory::MAX_MODULE_NAME as u64 + 1;
    let mut map = entry(0, 0x2000000, 1, 0);
    map.extend(entry(boundary, 1, 2, 0));
    f.map(map);
    f.modules(&[(0x300000, 0x301000, 0x400000, 0)]);
    f.add(0x400000, &vec![b'x'; 4096]);
    error(f.parse(), BootError::Address);
    assert!(!f.reads.iter().any(|&(a, _)| a == boundary));
}

#[test]
fn initramfs_duplicate_exact_labels_rejected_in_either_order() {
    for reverse in [false, true] {
        let mut f = Physical::new();
        let mut descriptors = [
            (0x300000, 0x301000, 0x400000, 0),
            (0x302000, 0x303000, 0x401000, 0),
        ];
        if reverse {
            descriptors.reverse();
        }
        f.modules(&descriptors);
        f.add(0x400000, b"rosti.initramfs\0");
        f.add(0x401000, b"rosti.initramfs\0");
        let inv = f.parse().unwrap();
        assert_eq!(inv.select_initramfs().err(), Some(BootError::Module));
    }
}

#[test]
fn initramfs_name_bounds_never_select_a_truncated_prefix() {
    use inventory::MAX_MODULE_NAME;
    for len in [MAX_MODULE_NAME, MAX_MODULE_NAME + 1, 4095] {
        let mut f = Physical::new();
        let mut name = vec![b'x'; len];
        name[..b"rosti.initramfs".len()].copy_from_slice(b"rosti.initramfs");
        name.push(0);
        f.modules(&[(0x300000, 0x301000, 0x400000, 0)]);
        f.add(0x400000, &name);
        let inv = f.parse().unwrap();
        assert!(inv.select_initramfs().unwrap().is_none());
        assert_eq!(
            inv.module_descriptors[0].name.as_str().is_some(),
            len == MAX_MODULE_NAME
        );
        assert!(
            inv.reservations
                .contains(&(0x400000, 0x400000 + name.len() as u64))
        );
    }
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0x400000, 0)]);
    f.add(0x400000, &vec![b'x'; 4096]);
    error(f.parse(), BootError::String);
}

#[test]
fn initramfs_required_label_metadata_keeps_validation_fail_closed() {
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0x400000, 0)]);
    f.add(0x400000, b"rosti.initramfs"); // missing NUL must not select
    error(f.parse(), BootError::Truncated);
    for pointer in [0x100000, 0x800000, 0x3000000] {
        let mut f = Physical::new();
        f.modules(&[(0x300000, 0x301000, pointer, 0)]);
        error(f.parse(), BootError::Address);
        assert!(!f.reads.iter().any(|&(a, _)| a == pointer as u64));
    }
    let mut f = Physical::new();
    f.modules(&[(0x300000, 0x301000, 0x300000, 0)]);
    f.add(0x300000, b"rosti.initramfs\0");
    error(f.parse(), BootError::Module);
}
