use super::{frame::FrameAllocator, paging};
use crate::multiboot::MmapEntry;

#[test]
fn module_access_requires_every_page_identity_mapped_and_pinned() {
    let mut fa = FrameAllocator::new();
    let entries = [MmapEntry {
        size: 20,
        base_addr: 0x10000,
        length: 0x100000,
        type_: 1,
    }];
    fa.init(&entries, 0x10000, 0x11000, 0x12000);
    let mut tables = alloc::vec![0u64; 1024];
    let mut pins = alloc::vec![(0x40000, 0x42000)];
    let mut pm =
        paging::build_identity_map_with_pins_in_place(&mut fa, 0x110000, &mut tables, &mut pins)
            .unwrap();
    assert!(pm.pinned_identity_span(0x40001, 0x42000));
    assert!(!pm.pinned_identity_span(0x3ffff, 0x41000));
    assert!(!pm.pinned_identity_span(0x40001, 0x42001));
    assert!(!pm.pinned_identity_span(0, 1));
    assert!(!pm.pinned_identity_span(0x40000, 0x40000));
    assert!(!pm.pinned_identity_span(0x42000, 0x40000));
    assert!(!pm.pinned_identity_span(0x40000, u64::MAX));
    assert!(!pm.unmap(&mut fa, 0x40000));
    assert!(!pm.unmap(&mut fa, 0x41000));
}

#[test]
fn pins_alone_do_not_grant_missing_or_nonidentity_access() {
    let mut fa = FrameAllocator::new();
    let entries = [MmapEntry {
        size: 20,
        base_addr: 0x10000,
        length: 0x1000000,
        type_: 1,
    }];
    fa.init(&entries, 0x10000, 0x11000, 0x12000);
    let mut tables = alloc::vec![0u64; 1024];
    let slot = paging::GROWTH_START as u64;
    let mut pins = alloc::vec![(slot, slot + 4096)];
    let mut pm =
        paging::build_identity_map_with_pins_in_place(&mut fa, 0x1010000, &mut tables, &mut pins)
            .unwrap();
    assert!(!pm.pinned_identity_span(slot, slot + 1));
    let other = fa.allocate().unwrap();
    assert_ne!(slot, other);
    assert!(pm.map(&mut fa, slot, other, &paging::KERNEL_PERMS));
    assert!(!pm.pinned_identity_span(slot, slot + 1));
    assert!(!pm.unmap(&mut fa, slot));
}
