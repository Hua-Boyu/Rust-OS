//! Allocator-wide runtime payload pins, not generational caller authority.
use super::*;
use crate::multiboot::MmapEntry;

fn entries() -> [MmapEntry; 1] {
    [MmapEntry {
        size: 20,
        base_addr: 0x10000,
        length: 0x1000000,
        type_: 1,
    }]
}

fn fixture() -> (FrameAllocator, PageMap) {
    let mut fa = FrameAllocator::new();
    fa.init(&entries(), 0x90000, 0xa0000, 0xb0000);
    let pm = build_identity_map(&mut fa, 0x1010000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    (fa, pm)
}

#[test]
fn runtime_mapping_pin_refuses_free_of_ordinary_and_growth_payloads() {
    for growth in [false, true] {
        let (mut fa, mut pm) = fixture();
        let slot = GROWTH_START as u64;
        let payload = if growth {
            fa.claim_growth_frame(slot).unwrap()
        } else {
            fa.allocate().unwrap()
        };
        assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
        let before = *fa.stats();
        assert!(
            !fa.free(payload),
            "live runtime payload must remain allocated"
        );
        assert_eq!(fa.stats().free_frames, before.free_frames);
        assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
        assert_eq!(fa.stats().reserved_frames, before.reserved_frames);
        assert_eq!(fa.stats().invalid_frees, before.invalid_frees + 1);
        assert_eq!(fa.stats().double_frees, before.double_frees);
        assert_eq!(pm.translate(slot), Some(payload));
        assert!(pm.unmap(&mut fa, slot));
        assert!(!fa.runtime_pinned(payload));
        assert!(fa.free(payload));
        let restored = *fa.stats();
        for _ in 0..16 {
            let next = if growth {
                fa.claim_growth_frame(slot)
            } else {
                fa.allocate()
            }
            .unwrap();
            assert_eq!(next, payload);
            assert!(pm.map(&mut fa, slot, next, &KERNEL_PERMS));
            assert!(!fa.free(next));
            assert!(pm.unmap(&mut fa, slot));
            assert!(fa.free(next));
            assert_eq!(fa.stats().free_frames, restored.free_frames);
            assert_eq!(fa.stats().allocated_frames, restored.allocated_frames);
            assert_eq!(fa.stats().reserved_frames, restored.reserved_frames);
        }
    }
}

#[test]
fn runtime_mapping_pin_live_allocator_reset_is_nonmutating() {
    let (mut fa, mut pm) = fixture();
    let payload = fa.allocate().unwrap();
    let slot = GROWTH_START as u64;
    assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    let before = *fa.stats();
    let domain = fa.domain();
    fa.init(&entries(), 0x90000, 0xa0000, 0xb0000);
    assert!(!fa.init_with_reservations(&entries(), 0x90000, 0xa0000, 0xb0000, &[(2, 1)]));
    assert_eq!(fa.domain(), domain);
    assert!(fa.runtime_pinned(payload));
    assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
    assert_eq!(fa.stats().free_frames, before.free_frames);
    assert_eq!(fa.stats().reserved_frames, before.reserved_frames);
    assert!(!fa.free(payload));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.free(payload));
}

#[test]
fn runtime_mapping_pin_foreign_allocator_cannot_mutate_map() {
    let (_owner, mut pm) = fixture();
    let mut foreign = FrameAllocator::new();
    foreign.init(&entries(), 0x90000, 0xa0000, 0xb0000);
    // Acquire a live numeric address beyond this map's own structures.
    let payload = (0..8).map(|_| foreign.allocate().unwrap()).last().unwrap();
    let before = *foreign.stats();
    let slot = GROWTH_START as u64;
    assert!(!pm.map(&mut foreign, slot, payload, &KERNEL_PERMS));
    assert_eq!(foreign.stats().allocated_frames, before.allocated_frames);
    assert_eq!(pm.translate(slot), None);
    assert_eq!(pm.stats().maps, 0);
    assert_eq!(pm.stats().tlb_invalidation, 0);
}

#[test]
fn runtime_mapping_pin_cross_map_exclusion_and_boot_alias_preservation() {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let mut a = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let mut b = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let payload = fa.allocate().unwrap();
    let slot = GROWTH_START as u64;
    assert!(a.map(&mut fa, slot, payload, &KERNEL_PERMS));
    let before = *fa.stats();
    let tables = b.stats().page_tables;
    assert_eq!(b.tables[page_dir_index(slot)], 0);
    assert!(!b.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert_eq!(fa.stats().free_frames, before.free_frames);
    assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
    assert_eq!(b.stats().page_tables, tables);
    assert_eq!(read_entry(b.directory, page_dir_index(slot)), 0);
    assert_eq!(b.stats().maps, 0);
    assert_eq!(b.stats().tlb_invalidation, 0);
    // A borrowed boot identity alias in either map never owns the runtime pin.
    assert!(b.unmap(&mut fa, payload));
    assert!(a.unmap(&mut fa, payload));
    assert!(fa.runtime_pinned(payload));
    assert!(!fa.free(payload));
    assert_eq!(a.translate(slot), Some(payload));
    assert!(!b.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert!(a.unmap(&mut fa, slot));
    assert!(!fa.runtime_pinned(payload));
    assert!(b.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert!(b.unmap(&mut fa, slot));
    assert!(fa.free(payload));
}

#[test]
fn runtime_mapping_pin_foreign_unmap_and_release_leave_both_domains_intact() {
    let (mut fa, mut pm) = fixture();
    let payload = fa.allocate().unwrap();
    let slot = GROWTH_START as u64;
    assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    let mut foreign = FrameAllocator::new();
    assert!(foreign.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let before = *foreign.stats();
    let owner_allocated = fa.stats().allocated_frames;
    let before_tlb = pm.stats().tlb_invalidation;
    assert!(!pm.unmap(&mut foreign, slot));
    assert!(!pm.unmap(&mut foreign, payload));
    pm.release_unpublished_frames(&mut foreign);
    pm.release_unpublished_frames(&mut fa); // runtime mappings forbid this helper
    assert_eq!(foreign.stats().free_frames, before.free_frames);
    assert_eq!(foreign.stats().allocated_frames, before.allocated_frames);
    assert_eq!(foreign.stats().invalid_frees, before.invalid_frees);
    assert_eq!(foreign.stats().double_frees, before.double_frees);
    assert_eq!(fa.stats().allocated_frames, owner_allocated);
    assert_eq!(pm.stats().tlb_invalidation, before_tlb);
    assert_eq!(pm.translate(slot), Some(payload));
    assert!(fa.runtime_pinned(payload));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.free(payload));
}

#[test]
fn runtime_mapping_pin_inconsistent_runtime_mirrors_refuse_unmap() {
    for missing_local in [false, true] {
        let (mut fa, mut pm) = fixture();
        let payload = fa.allocate().unwrap();
        let slot = GROWTH_START as u64;
        assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
        let entry = pm.entry(slot);
        let before_tlb = pm.stats().tlb_invalidation;
        // Private test corruption, never a production mutation path.
        if missing_local {
            payload_set_bit(&mut pm.payload_bitmap, payload, false);
        } else {
            fa.set_runtime_pin(payload, false);
        }
        assert!(!pm.unmap(&mut fa, slot));
        assert_eq!(pm.entry(slot), entry);
        assert_eq!(pm.stats().tlb_invalidation, before_tlb);
        payload_set_bit(&mut pm.payload_bitmap, payload, true);
        fa.set_runtime_pin(payload, true);
        assert!(pm.unmap(&mut fa, slot));
        assert!(fa.free(payload));
    }
}

#[test]
fn runtime_mapping_pin_table_exhaustion_does_not_pin_caller_payload() {
    let mut fa = FrameAllocator::new();
    let mut inventory = entries();
    inventory[0].length = 4 * PAGE_SIZE as u64;
    assert!(fa.init(&inventory, 0x90000, 0xa0000, 0xb0000));
    let mut pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let payload = fa.allocate().unwrap();
    let held = fa.allocate().unwrap();
    assert_eq!(fa.stats().free_frames, 0);
    let slot = GROWTH_START as u64;
    assert!(!pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert!(!fa.runtime_pinned(payload));
    assert!(fa.free(held));
    assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.free(payload));
}

#[test]
fn runtime_mapping_pin_empty_reset_invalidates_previous_map_domain() {
    let (mut fa, mut old) = fixture();
    let old_domain = fa.domain();
    old.release_unpublished_frames(&mut fa);
    assert_eq!(fa.stats().allocated_frames, 0);
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    assert_ne!(fa.domain(), old_domain);
    let payload = fa.allocate().unwrap();
    let before = *fa.stats();
    assert!(!old.map(&mut fa, GROWTH_START as u64, payload, &KERNEL_PERMS));
    assert!(!old.unmap(&mut fa, payload));
    old.release_unpublished_frames(&mut fa);
    assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
    assert_eq!(fa.stats().free_frames, before.free_frames);
    assert_eq!(fa.stats().invalid_frees, before.invalid_frees);
    assert!(fa.free(payload));
}
