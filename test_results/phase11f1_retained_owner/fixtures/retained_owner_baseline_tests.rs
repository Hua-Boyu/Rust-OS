//! Runtime missing-policy probes against an isolated exact baseline snapshot.
//! Publication retention is deliberately NOT represented as a smoke seal.
use super::*;
use crate::multiboot::MmapEntry;

fn fixture() -> (FrameAllocator, PageMap) {
    let entries = [MmapEntry {
        size: 20,
        base_addr: 0x10000,
        length: 0x70000,
        type_: 1,
    }];
    let mut fa = FrameAllocator::new();
    assert!(fa.init(&entries, 0x90000, 0xa0000, 0xb0000));
    let pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES])
        .expect("baseline fixture identity map");
    (fa, pm)
}

// Reviewed baseline adapter only. Existing structure retention is NOT the
// missing irreversible F1 mutation freeze, and this calls no candidate API.
fn baseline_structure_retention_only(pm: &mut PageMap) {
    assert!(pm.retain_for_publication());
}

#[derive(Debug, PartialEq, Eq)]
struct Snapshot {
    capacity: [usize; 7],
    paging: [usize; 7],
    enabled: bool,
    directory: u64,
    domain: u32,
    retained: bool,
    window: u64,
    tables: Vec<u64>,
    pins: Vec<(bool, bool)>,
    entries: Vec<u32>,
    bitmap: Vec<u8>,
    lease_live: bool,
    frame_free: bool,
}

// Owned snapshots allocate only in this unlocked per-instance host fixture.
fn snapshot(fa: &FrameAllocator, pm: &PageMap, lease: &frame::FrameLease) -> Snapshot {
    let f = *fa.stats();
    let p = pm.stats();
    let mut entries = Vec::new();
    for index in 0..PAGE_DIR_ENTRIES {
        entries.push(read_entry(pm.directory, index));
    }
    for &table in &pm.tables {
        if table != 0 {
            for index in 0..PAGE_TABLE_ENTRIES {
                entries.push(read_entry(table, index));
            }
        }
    }
    Snapshot {
        capacity: [
            f.total_frames,
            f.reserved_frames,
            f.free_frames,
            f.allocated_frames,
            f.double_frees,
            f.invalid_frees,
            f.bitmap_frames,
        ],
        paging: [
            p.page_tables,
            p.mapped_frames,
            p.maps,
            p.map_rejects,
            p.unmaps,
            p.unmap_rejects,
            p.tlb_invalidation,
        ],
        enabled: p.enabled,
        directory: pm.directory,
        domain: pm.domain,
        retained: pm.retained,
        window: pm.window_end,
        tables: pm.tables.clone(),
        pins: (0..frame::MAX_FRAMES)
            .map(|i| {
                let addr = i as u64 * PAGE_SIZE as u64;
                (fa.runtime_pinned(addr), fa.structure_pinned(addr))
            })
            .collect(),
        entries,
        bitmap: pm.payload_bitmap.clone(),
        lease_live: fa.owns_live_lease(lease),
        frame_free: fa.is_free(lease.frame_addr()),
    }
}

#[test]
fn f1_missing_policy_baseline_retained_map_still_allows_owned_unmap() {
    let (mut fa, mut pm) = fixture();
    let lease = fa.allocate_owned().expect("ordinary payload acquisition");
    let addr = lease.frame_addr();
    let slot = GROWTH_START as u64;
    assert!(pm.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(addr));
    assert!(fa.runtime_pinned(addr));
    assert!(payload_bit(&pm.payload_bitmap, addr));
    assert!(fa.owns_live_lease(&lease));
    baseline_structure_retention_only(&mut pm);
    let before = snapshot(&fa, &pm, &lease);
    let released = pm.unmap_owned(&mut fa, slot, &lease);
    let after = snapshot(&fa, &pm, &lease);
    assert!(
        !released,
        "F1 MISSING POLICY: structure retention still permits owned unmap"
    );
    assert_eq!(after, before, "retained unmap must be state-atomic refusal");
}

#[test]
fn f1_missing_policy_baseline_retained_map_still_allows_unpublished_owned_release() {
    let (mut fa, mut pm) = fixture();
    let lease = fa
        .allocate_owned()
        .expect("ordinary unpublished acquisition");
    assert!(fa.owns_live_lease(&lease));
    assert!(!fa.is_free(lease.frame_addr()));
    assert!(!fa.runtime_pinned(lease.frame_addr()));
    assert!(!fa.structure_pinned(lease.frame_addr()));
    baseline_structure_retention_only(&mut pm);
    let probe = lease.duplicate_for_test();
    let before = snapshot(&fa, &pm, &lease);
    let released = fa.release_frame(probe);
    let after = snapshot(&fa, &pm, &lease);
    assert!(
        !released,
        "F1 MISSING POLICY: structure retention still permits unpublished owned release"
    );
    assert_eq!(
        after, before,
        "retained release must be state-atomic refusal"
    );
}

#[test]
fn f1_baseline_characterization_ordinary_map_unmap_release_remain_valid() {
    let (mut fa, mut pm) = fixture();
    let before = *fa.stats();
    let lease = fa.allocate_owned().expect("ordinary control acquisition");
    let addr = lease.frame_addr();
    let slot = GROWTH_START as u64;
    assert!(pm.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert!(fa.runtime_pinned(addr));
    assert!(pm.unmap_owned(&mut fa, slot, &lease));
    assert!(!fa.runtime_pinned(addr));
    assert!(fa.release_frame(lease));
    assert!(fa.is_free(addr));
    // Installing the runtime growth-slot table legitimately retains one frame.
    assert_eq!(fa.stats().allocated_frames, before.allocated_frames + 1);
    assert_eq!(fa.stats().free_frames + 1, before.free_frames);
    assert!(pm.release_unpublished_frames(&mut fa));
    assert_eq!(fa.stats().allocated_frames, 0);
}
