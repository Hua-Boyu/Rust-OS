//! Virtual-page-zero admission: the boot identity map deliberately leaves the
//! null virtual page unmapped so null accesses fault. Ordinary runtime mapping
//! must not publish a replacement there either; physical-null rejection
//! (phase11a2) is a separate, already accepted invariant.
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
fn vpz_ordinary_map_at_virtual_zero_is_refused_without_side_effects() {
    let (mut fa, mut pm) = fixture();
    // The boot identity map never maps the null virtual page: null accesses fault.
    assert!(pm.translate(0).is_none());
    assert!(!pm.is_mapped(0));
    let lease = fa.allocate_owned().unwrap();
    let payload = lease.frame_addr();
    let fa_before = *fa.stats();
    let mapped_before = pm.stats().mapped_frames;
    let rejects_before = pm.stats().map_rejects;
    assert!(
        !pm.map(&mut fa, 0, payload, &KERNEL_PERMS),
        "virtual page zero must not accept an ordinary runtime mapping"
    );
    // Complete refusal: no allocator mutation, no pin, no publication.
    assert_eq!(fa.stats().free_frames, fa_before.free_frames);
    assert_eq!(fa.stats().allocated_frames, fa_before.allocated_frames);
    assert!(!fa.runtime_pinned(payload));
    assert!(pm.translate(0).is_none());
    assert!(!pm.is_mapped(0));
    assert_eq!(pm.stats().mapped_frames, mapped_before);
    assert_eq!(pm.stats().map_rejects, rejects_before + 1);
    // The caller still owns the payload and can release it exactly once.
    assert!(fa.release_frame(lease));
}

#[test]
fn vpz_unmap_at_virtual_zero_is_refused_without_side_effects() {
    let (mut fa, mut pm) = fixture();
    let fa_before = *fa.stats();
    let unmap_rejects_before = pm.stats().unmap_rejects;
    let tlb_before = pm.stats().tlb_invalidation;
    assert!(
        !pm.unmap(&mut fa, 0),
        "unmap of an absent null virtual page must be refused"
    );
    assert_eq!(fa.stats().free_frames, fa_before.free_frames);
    assert_eq!(pm.stats().unmap_rejects, unmap_rejects_before + 1);
    assert_eq!(pm.stats().tlb_invalidation, tlb_before);
    assert!(pm.translate(0).is_none());
}

#[test]
fn vpz_nonzero_growth_slots_still_admit_normally() {
    // Refusal must be exactly virtual page zero, not the managed window or
    // the growth window. Growth slots are unmapped at boot by design.
    let (mut fa, mut pm) = fixture();
    let lease = fa.allocate_owned().unwrap();
    let payload = lease.frame_addr();
    let slot = GROWTH_START as u64 + PAGE_SIZE as u64;
    assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert_eq!(pm.translate(slot), Some(payload));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.release_frame(lease));
}
