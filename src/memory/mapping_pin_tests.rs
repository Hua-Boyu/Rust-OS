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

// Owned snapshots deliberately include diagnostic counters and all installed
// entries, not just map()'s return value or the destination translation.
fn shared_frame_state(fa: &FrameAllocator) -> ([usize; 7], Vec<u64>, Vec<u64>) {
    let s = fa.stats();
    let mut runtime = Vec::new();
    let mut structures = Vec::new();
    for index in 0..frame::MAX_FRAMES {
        let addr = (index * PAGE_SIZE) as u64;
        if fa.runtime_pinned(addr) {
            runtime.push(addr);
        }
        if fa.structure_pinned(addr) {
            structures.push(addr);
        }
    }
    (
        [
            s.total_frames,
            s.free_frames,
            s.allocated_frames,
            s.reserved_frames,
            s.invalid_frees,
            s.double_frees,
            s.bitmap_frames,
        ],
        runtime,
        structures,
    )
}

#[derive(Debug, PartialEq, Eq)]
struct SharedMapState {
    // map_rejects and unmap_rejects are the only permitted refusal deltas.
    counters: [usize; 7],
    enabled: bool,
    directory: Vec<u32>,
    tables: Vec<(u64, Vec<u32>)>,
    payloads: Vec<u8>,
}

fn shared_map_state(pm: &PageMap) -> SharedMapState {
    let s = pm.stats();
    SharedMapState {
        counters: [
            s.page_tables,
            s.mapped_frames,
            s.maps,
            s.map_rejects,
            s.unmaps,
            s.unmap_rejects,
            s.tlb_invalidation,
        ],
        enabled: s.enabled,
        directory: (0..PAGE_DIR_ENTRIES)
            .map(|i| read_entry(pm.directory, i))
            .collect(),
        tables: pm
            .tables
            .iter()
            .map(|&table| {
                let entries = if table == 0 {
                    Vec::new()
                } else {
                    (0..PAGE_TABLE_ENTRIES)
                        .map(|i| read_entry(table, i))
                        .collect()
                };
                (table, entries)
            })
            .collect(),
        payloads: pm.payload_bitmap.clone(),
    }
}

/// CHARACTERIZATION A: exclusive runtime ownership, not shared references.
#[test]
fn shared_mapping_same_and_cross_map_refusal_is_state_atomic() {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let baseline = shared_frame_state(&fa);
    let mut a = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let mut b = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let lease = fa.allocate_owned().unwrap();
    let payload = lease.frame_addr();
    let slot_a = GROWTH_START as u64;
    let slot_b = slot_a + PAGE_SIZE as u64;
    let slot_cross = slot_a + (1 << 22);
    assert!(a.map(&mut fa, slot_a, payload, &KERNEL_PERMS));
    assert_eq!(a.translate(slot_a), Some(payload));
    assert!(fa.runtime_pinned(payload));
    assert!(payload_bit(&a.payload_bitmap, payload));
    assert!(!payload_bit(&b.payload_bitmap, payload));
    let frames = shared_frame_state(&fa);
    let mut original = shared_map_state(&a);
    let other = shared_map_state(&b);
    assert_eq!(a.entry(slot_b), Some(0));
    assert!(!a.map(&mut fa, slot_b, payload, &KERNEL_PERMS));
    original.counters[3] += 1;
    assert_eq!(shared_frame_state(&fa), frames);
    assert_eq!(shared_map_state(&a), original);
    assert_eq!(shared_map_state(&b), other);
    assert_eq!(b.entry(slot_cross), None);
    assert_eq!(read_entry(b.directory, page_dir_index(slot_cross)), 0);
    assert!(!b.map(&mut fa, slot_cross, payload, &KERNEL_PERMS));
    let mut other = other;
    other.counters[3] += 1;
    assert_eq!(shared_frame_state(&fa), frames);
    assert_eq!(shared_map_state(&a), original);
    assert_eq!(shared_map_state(&b), other);
    assert_eq!(a.translate(slot_a), Some(payload));
    assert!(a.unmap(&mut fa, slot_a));
    assert!(!fa.runtime_pinned(payload));
    assert!(!payload_bit(&a.payload_bitmap, payload));
    assert!(fa.release_frame(lease));
    // Existing unpublished-fixture cleanup, never CPU-loaded map teardown.
    assert!(a.release_unpublished_frames(&mut fa));
    assert!(b.release_unpublished_frames(&mut fa));
    assert_eq!(shared_frame_state(&fa), baseline);
}

/// CHARACTERIZATION B: exhausted table backing must permit a valid retry.
#[test]
fn shared_mapping_table_failure_then_retry_preserves_lease_and_capacity() {
    let mut fa = FrameAllocator::new();
    let mut inventory = entries();
    inventory[0].length = 4 * PAGE_SIZE as u64;
    assert!(fa.init(&inventory, 0x90000, 0xa0000, 0xb0000));
    let baseline = shared_frame_state(&fa);
    let mut pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let mapped_baseline = pm.stats().mapped_frames;
    let lease = fa.allocate_owned().unwrap();
    let payload = lease.frame_addr();
    let held = fa.allocate_owned().unwrap();
    assert_eq!(fa.stats().free_frames, 0);
    let slot = GROWTH_START as u64;
    let frames = shared_frame_state(&fa);
    let mut map = shared_map_state(&pm);
    assert_eq!(pm.entry(slot), None);
    assert!(!pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    map.counters[3] += 1;
    assert_eq!(shared_frame_state(&fa), frames);
    assert_eq!(shared_map_state(&pm), map);
    assert!(fa.is_live_allocation(payload));
    assert!(!fa.runtime_pinned(payload));
    assert!(!payload_bit(&pm.payload_bitmap, payload));
    assert!(fa.release_frame(held));
    assert_eq!(fa.stats().free_frames, 1);
    assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(payload));
    assert_eq!(
        pm.entry(slot),
        Some(payload as u32 | ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_RUNTIME_PAYLOAD)
    );
    assert!(fa.runtime_pinned(payload));
    assert!(payload_bit(&pm.payload_bitmap, payload));
    assert_eq!(fa.stats().free_frames, 0);
    assert_eq!(fa.stats().allocated_frames, 4);
    assert_eq!(pm.stats().page_tables, 2);
    assert_eq!(pm.stats().mapped_frames, mapped_baseline + 1);
    assert_eq!(pm.stats().maps, 1);
    assert_eq!(pm.stats().tlb_invalidation, 1);
    assert!(pm.unmap(&mut fa, slot));
    assert_eq!(pm.entry(slot), Some(0));
    assert!(!fa.runtime_pinned(payload));
    assert!(!payload_bit(&pm.payload_bitmap, payload));
    assert_eq!(pm.stats().mapped_frames, mapped_baseline);
    assert_eq!(pm.stats().unmaps, 1);
    assert_eq!(pm.stats().tlb_invalidation, 2);
    assert!(fa.release_frame(lease));
    assert!(pm.release_unpublished_frames(&mut fa));
    assert_eq!(shared_frame_state(&fa), baseline);
}

/// CHARACTERIZATION C: retained lease, absent old slot and foreign domain.
/// This does not authenticate arbitrary same-slot numeric replacements.
#[test]
fn shared_mapping_retained_lease_remap_refuses_old_and_foreign_unmap() {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let baseline = shared_frame_state(&fa);
    let mut pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let mapped_baseline = pm.stats().mapped_frames;
    let lease = fa.allocate_owned().unwrap();
    let payload = lease.frame_addr();
    let slot_a = GROWTH_START as u64;
    let slot_b = slot_a + PAGE_SIZE as u64;
    assert!(pm.map(&mut fa, slot_a, payload, &KERNEL_PERMS));
    assert!(pm.unmap(&mut fa, slot_a));
    assert_eq!(pm.entry(slot_a), Some(0));
    assert!(!fa.runtime_pinned(payload));
    assert!(!payload_bit(&pm.payload_bitmap, payload));
    assert!(fa.is_live_allocation(payload));
    assert_eq!(lease.frame_addr(), payload);
    assert!(pm.map(&mut fa, slot_b, payload, &KERNEL_PERMS));
    let frames = shared_frame_state(&fa);
    let mut map = shared_map_state(&pm);
    assert!(!pm.unmap(&mut fa, slot_a));
    map.counters[5] += 1;
    assert_eq!(shared_frame_state(&fa), frames);
    assert_eq!(shared_map_state(&pm), map);
    let mut foreign = FrameAllocator::new();
    assert!(foreign.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let foreign_before = shared_frame_state(&foreign);
    assert!(!pm.unmap(&mut foreign, slot_b));
    map.counters[5] += 1;
    assert_eq!(shared_frame_state(&foreign), foreign_before);
    assert_eq!(shared_frame_state(&fa), frames);
    assert_eq!(shared_map_state(&pm), map);
    assert_eq!(pm.translate(slot_b), Some(payload));
    assert_eq!(
        pm.entry(slot_b),
        Some(payload as u32 | ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_RUNTIME_PAYLOAD)
    );
    assert!(fa.runtime_pinned(payload));
    assert!(payload_bit(&pm.payload_bitmap, payload));
    assert!(pm.unmap(&mut fa, slot_b));
    assert_eq!(pm.entry(slot_b), Some(0));
    assert!(!fa.runtime_pinned(payload));
    assert!(!payload_bit(&pm.payload_bitmap, payload));
    assert_eq!(pm.stats().maps, 2);
    assert_eq!(pm.stats().unmaps, 2);
    assert_eq!(pm.stats().map_rejects, 0);
    assert_eq!(pm.stats().unmap_rejects, 2);
    assert_eq!(pm.stats().tlb_invalidation, 4);
    assert_eq!(pm.stats().mapped_frames, mapped_baseline);
    assert!(fa.release_frame(lease));
    assert!(pm.release_unpublished_frames(&mut fa));
    assert_eq!(shared_frame_state(&fa), baseline);
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
