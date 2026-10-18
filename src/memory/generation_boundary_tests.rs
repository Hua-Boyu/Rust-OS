//! Module-internal fault injection; never production token construction APIs.
use super::*;

fn entries() -> [MmapEntry; 1] {
    [MmapEntry {
        size: 20,
        base_addr: 0x10000,
        length: 0x1000000,
        type_: 1,
    }]
}

fn fixture() -> FrameAllocator {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    fa
}

fn capacity(fa: &FrameAllocator) -> (usize, usize, usize) {
    (
        fa.stats.free_frames,
        fa.stats.allocated_frames,
        fa.stats.reserved_frames,
    )
}

#[test]
fn generation_boundary_structure_pin_refuses_matching_lease() {
    let mut fa = fixture();
    let lease = fa.allocate_owned().unwrap();
    let addr = lease.addr;
    let frame = FrameAllocator::frame_of(addr).unwrap();
    let id = lease.id;
    fa.set_structure_pin(addr, true);
    let before = capacity(&fa);
    assert!(!fa.release_frame(lease.duplicate_for_test()));
    assert_eq!(capacity(&fa), before);
    assert_eq!(fa.alloc_id[frame], id);
    assert!(fa.structure_pinned(addr));
    assert!(!fa.is_free(addr));
    fa.set_structure_pin(addr, false);
    assert!(fa.release_frame(lease));
    assert_eq!(fa.alloc_id[frame], 0);
}

#[test]
fn generation_boundary_reset_preserves_issuer_and_rejects_old_domain() {
    let mut fa = fixture();
    let lease = fa.allocate_owned().unwrap();
    let stale = lease.duplicate_for_test();
    let old_id = lease.id;
    assert!(fa.release_frame(lease));
    let next = fa.next_id;
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    assert_eq!(fa.next_id, next);
    let current = fa.allocate_owned().unwrap();
    assert_eq!(current.addr, stale.addr);
    assert!(current.id > old_id);
    assert_ne!(current.domain, stale.domain);
    let before = capacity(&fa);
    assert!(!fa.release_frame(stale));
    assert_eq!(capacity(&fa), before);
    assert!(!fa.is_free(current.addr));
    assert!(fa.release_frame(current));
}

#[test]
fn generation_boundary_exhaustion_survives_reset_without_capacity_loss() {
    let mut fa = fixture();
    fa.next_id = u32::MAX;
    let last = fa.allocate_owned().unwrap();
    let before = capacity(&fa);
    for _ in 0..2 {
        assert!(fa.allocate_owned().is_none());
        assert!(fa.allocate().is_none());
        assert_eq!(capacity(&fa), before);
    }
    assert!(fa.release_frame(last));
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let reset = capacity(&fa);
    assert_eq!(fa.next_id, 0);
    assert!(fa.allocate_owned().is_none());
    assert!(fa.allocate().is_none());
    assert_eq!(capacity(&fa), reset);
}

#[test]
fn generation_boundary_growth_claim_has_no_ordinary_identity() {
    let mut fa = fixture();
    let addr = paging::GROWTH_START as u64;
    assert_eq!(fa.claim_growth_frame(addr), Some(addr));
    let frame = FrameAllocator::frame_of(addr).unwrap();
    assert_eq!(fa.alloc_id[frame], 0);
    let before = capacity(&fa);
    for id in [0, 1, u32::MAX] {
        assert!(!fa.release_frame(FrameLease {
            addr,
            id,
            domain: fa.domain
        }));
        assert_eq!(capacity(&fa), before);
        assert!(fa.is_live_allocation(addr));
    }
    assert!(fa.free(addr));
    assert!(!fa.is_free(addr));
    assert_eq!(fa.claim_growth_frame(addr), Some(addr));
    assert!(fa.free(addr));
}

#[test]
fn generation_boundary_malformed_lease_preserves_current_owner() {
    let mut fa = fixture();
    let current = fa.allocate_owned().unwrap();
    let before = capacity(&fa);
    for addr in [current.addr + 1, MAX_FRAME_ADDR, u64::MAX] {
        assert!(!fa.release_frame(FrameLease {
            addr,
            id: current.id,
            domain: current.domain
        }));
        assert_eq!(capacity(&fa), before);
        assert!(!fa.is_free(current.addr));
    }
    assert!(fa.release_frame(current));
}

#[test]
fn generation_boundary_static_ledger_budget() {
    assert_eq!(core::mem::size_of::<[u32; MAX_FRAMES]>(), 262_144);
    let size = core::mem::size_of::<FrameAllocator>();
    assert!(
        size <= 320 * 1024,
        "allocator exceeded bounded static budget"
    );
    std::eprintln!(
        "FrameAllocator host bytes={size}; ledger bytes=262144; host thread stack uses toolchain default"
    );
}
