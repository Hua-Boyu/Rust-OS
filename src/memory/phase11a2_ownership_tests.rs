//! Phase 11A.2-A host oracle: physical-frame authority for runtime mapping.
//! These tests cannot establish real CPL3 execution or fault recovery.
use super::*;
use crate::multiboot::MmapEntry;

fn map_fixture() -> (FrameAllocator, PageMap) {
    let mut fa = FrameAllocator::new();
    fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x70000,
            type_: 1,
        }],
        0x90000,
        0xa0000,
        0xb0000,
    );
    let pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    (fa, pm)
}

#[test]
fn phase11a2_null_frame_mapping_is_rejected_without_side_effects() {
    let (mut fa, mut pm) = map_fixture();
    let before_free = fa.stats().free_frames;
    let before_tables = pm.stats().page_tables;
    let before_mapped = pm.stats().mapped_frames;
    let slot = GROWTH_START as u64;
    assert!(!pm.map(&mut fa, slot, 0, &KERNEL_PERMS));
    assert_eq!(fa.stats().free_frames, before_free);
    assert_eq!(pm.stats().page_tables, before_tables);
    assert_eq!(pm.stats().mapped_frames, before_mapped);
    assert_eq!(pm.stats().maps, 0);
    assert_eq!(pm.stats().tlb_invalidation, 0);
    assert_eq!(pm.stats().map_rejects, 1);
    assert_eq!(pm.entry(slot), None);
    assert_eq!(read_entry(pm.directory, page_dir_index(slot)), 0);
}

#[test]
fn phase11a2_free_pool_frame_alias_is_rejected() {
    // A frame that is currently in the free pool has no owner: mapping it
    // would let a later allocate() hand the same frame out a second time.
    let (mut fa, mut pm) = map_fixture();
    let frame = fa.allocate().unwrap();
    assert!(fa.free(frame));
    let before_free = fa.stats().free_frames;
    let before_mapped = pm.stats().mapped_frames;
    let slot = GROWTH_START as u64;
    assert!(!pm.map(&mut fa, slot, frame, &KERNEL_PERMS));
    assert_eq!(fa.stats().free_frames, before_free);
    assert_eq!(pm.stats().mapped_frames, before_mapped);
    assert_eq!(pm.stats().maps, 0);
    assert_eq!(pm.stats().tlb_invalidation, 0);
    assert_eq!(pm.stats().map_rejects, 1);
    assert_eq!(pm.entry(slot), None);
    // Re-acquiring the frame through the allocator restores ownership.
    let reacquired = fa.allocate().unwrap();
    assert_eq!(reacquired, frame);
    assert!(pm.map(&mut fa, slot, reacquired, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(reacquired));
}

#[test]
fn phase11a2_live_page_structure_alias_is_rejected_as_payload() {
    // The directory and live page tables are owned by the PageMap; mapping
    // them as payload would let the caller free or reuse them under the CPU.
    let (mut fa, mut pm) = map_fixture();
    let slot = GROWTH_START as u64;
    assert!(!pm.map(&mut fa, slot, pm.directory(), &KERNEL_PERMS));
    let table = pm.tables[page_dir_index(0x20000)];
    assert_ne!(table, 0);
    assert!(!pm.map(&mut fa, slot + 4096, table, &KERNEL_PERMS));
    assert_eq!(pm.stats().map_rejects, 2);
    assert_eq!(pm.stats().maps, 0);
    assert_eq!(pm.stats().tlb_invalidation, 0);
    assert_eq!(pm.entry(slot), None);
    assert_eq!(pm.entry(slot + 4096), None);
    // The live aliases themselves remain mapped and translate unchanged.
    assert_eq!(pm.translate(pm.directory()), Some(pm.directory()));
    assert_eq!(pm.translate(table), Some(table));
}

#[test]
fn phase11a2_growth_claimed_frame_maps_exactly_once_and_rolls_back() {
    // The heap growth path claims a reserved growth frame, maps it, and on
    // map rejection returns it to the growth-only reservation.
    let mut fa = FrameAllocator::new();
    fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x8000000,
            type_: 1,
        }],
        0x90000,
        0xa0000,
        0xb0000,
    );
    let mut pm = build_identity_map(
        &mut fa,
        GROWTH_START as u64,
        alloc::vec![0; PAGE_DIR_ENTRIES],
    )
    .unwrap();
    let before_reserved = fa.stats().reserved_frames;
    let slot = GROWTH_START as u64;
    let frame = fa.claim_growth_frame(slot).unwrap();
    assert_eq!(frame, slot);
    // The claimed frame is owned by the growth path, not the free pool.
    assert!(!fa.is_free(frame));
    assert!(pm.map(&mut fa, slot, frame, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(frame));
    // A second map of the same slot is a conflict, never an overwrite.
    assert!(!pm.map(&mut fa, slot, frame, &KERNEL_PERMS));
    // Unmap then free returns the frame to the growth reservation only.
    assert!(pm.unmap(slot));
    assert_eq!(pm.translate(slot), None);
    assert!(fa.free(frame));
    // The frame returns to the growth-only reservation, restoring the
    // reserved count that claim_growth_frame converted to allocated.
    assert_eq!(fa.stats().reserved_frames, before_reserved);
    let again = fa.claim_growth_frame(slot);
    assert_eq!(again, Some(slot));
}

#[test]
fn phase11a2_payload_frame_cannot_alias_two_active_slots() {
    // A caller-owned payload frame mapped at one slot must not be
    // referenced by a second active mapping at another slot.
    let (mut fa, mut pm) = map_fixture();
    let frame = fa.allocate().unwrap();
    let slot_a = GROWTH_START as u64;
    let slot_b = (GROWTH_START + 0x1000) as u64;
    assert!(pm.map(&mut fa, slot_a, frame, &KERNEL_PERMS));
    // Second slot with the same frame: rejected, no side effects.
    let before_tables = pm.stats().page_tables;
    assert!(!pm.map(&mut fa, slot_b, frame, &KERNEL_PERMS));
    assert_eq!(pm.stats().page_tables, before_tables);
    assert_eq!(pm.translate(slot_b), None);
    // Releasing the first reference permits re-mapping the frame elsewhere.
    assert!(pm.unmap(slot_a));
    assert!(pm.map(&mut fa, slot_b, frame, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot_b), Some(frame));
}

#[test]
fn phase11a2_unmapping_boot_alias_preserves_live_runtime_payload_reference() {
    let (mut fa, mut pm) = map_fixture();
    let frame = fa.allocate().unwrap();
    let slot_a = GROWTH_START as u64;
    let slot_b = slot_a + PAGE_SIZE as u64;
    assert_eq!(pm.translate(frame), Some(frame));
    assert!(pm.map(&mut fa, slot_a, frame, &KERNEL_PERMS));
    // The preexisting supervisor identity mapping is not the runtime owner.
    // Removing it must not release the runtime reference at slot_a.
    assert!(pm.unmap(frame));
    assert_eq!(pm.translate(slot_a), Some(frame));
    assert!(!pm.map(&mut fa, slot_b, frame, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot_b), None);
    assert!(pm.unmap(slot_a));
    assert!(pm.map(&mut fa, slot_b, frame, &KERNEL_PERMS));
}

#[test]
fn phase11a2_unmap_then_release_restores_allocator_ownership() {
    // A mapped payload frame must be returnable to the allocator after the
    // mapping stops referencing it, and remappable afterwards.
    let (mut fa, mut pm) = map_fixture();
    let frame = fa.allocate().unwrap();
    let slot = GROWTH_START as u64;
    assert!(pm.map(&mut fa, slot, frame, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(frame));
    // While mapped, the frame is not available to the allocator.
    assert!(!fa.is_free(frame));
    assert!(pm.unmap(slot));
    assert_eq!(pm.translate(slot), None);
    assert!(fa.free(frame));
    assert_eq!(pm.stats().unmaps, 1);
    assert!(fa.is_free(frame));
    // The released frame is free again and can be re-acquired and remapped.
    assert_eq!(fa.allocate(), Some(frame));
    assert!(pm.map(&mut fa, slot, frame, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(frame));
}

#[test]
fn phase11a2_reserved_and_uncovered_frames_cannot_enter_runtime_mapping() {
    // Independent byte-span fixture: each policy reservation intersects the
    // chosen page, including a one-byte pin and competing firmware coverage.
    // Boot identity aliases remain valid; runtime admission grants no ownership.
    for reserved in [0x20000u64, 0x30000, 0x40000, 0x50000, 0xb8000, 0x70000] {
        let mut fa = FrameAllocator::new();
        assert!(fa.init_with_reservations(
            &[
                MmapEntry {
                    size: 20,
                    base_addr: 0x10000,
                    length: 0x50000,
                    type_: 1
                },
                MmapEntry {
                    size: 20,
                    base_addr: 0x50001,
                    length: 1,
                    type_: 2
                },
            ],
            0x20000,
            0x30000,
            0x31000,
            &[(0x40001, 0x40002)],
        ));
        let mut pm =
            build_identity_map(&mut fa, 0x100000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
        let before = *fa.stats();
        let before_mapped = pm.stats().mapped_frames;
        let before_tables = pm.stats().page_tables;
        assert_eq!(pm.translate(reserved), Some(reserved));
        assert!(
            !pm.map(&mut fa, GROWTH_START as u64, reserved, &KERNEL_PERMS),
            "reserved/uncovered {reserved:#x}"
        );
        assert_eq!(fa.stats().free_frames, before.free_frames);
        assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
        assert_eq!(pm.stats().mapped_frames, before_mapped);
        assert_eq!(pm.stats().page_tables, before_tables);
        assert_eq!(pm.entry(GROWTH_START as u64), None);
        assert_eq!(pm.translate(reserved), Some(reserved));
    }
}
