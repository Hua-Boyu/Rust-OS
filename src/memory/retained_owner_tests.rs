//! Live F1 policy oracle. The original runtime RED used a deficient retain-only
//! adapter; the same assertions now invoke the real private preparation path.
use super::*;
use crate::multiboot::MmapEntry;

fn baseline_retention_adapter(pm: &mut PageMap, fa: &mut FrameAllocator) {
    assert!(retained_owner::seal_for_test(pm, fa));
}

#[test]
fn sealed_release_and_unmap_preserve_live_ownership() {
    if !retained_owner::tests::child_identity(
        "memory::paging::retained_owner_tests::sealed_release_and_unmap_preserve_live_ownership",
    ) {
        return;
    }
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x70000,
            type_: 1,
        }],
        0x90000,
        0xa0000,
        0xb0000,
    ));
    let mut pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let retained = fa.allocate_owned().unwrap();
    let mapped = fa.allocate_owned().unwrap();
    let slot = GROWTH_START as u64;
    assert!(pm.map_owned(&mut fa, slot, &mapped, &KERNEL_PERMS));
    baseline_retention_adapter(&mut pm, &mut fa);
    assert!(fa.owns_live_lease(&retained));
    assert!(!fa.runtime_pinned(retained.frame_addr()));
    assert!(!fa.structure_pinned(retained.frame_addr()));
    assert!(fa.owns_live_lease(&mapped));
    assert!(fa.runtime_pinned(mapped.frame_addr()));
    let retained_address = retained.frame_addr();
    let mapped_address = mapped.frame_addr();
    let before_capacity = (fa.stats().free_frames, fa.stats().allocated_frames);
    let before_entry = pm.entry(slot);
    let before_directory = read_entry(pm.directory, page_dir_index(slot));
    let released = fa.release_frame(retained.duplicate_for_test());
    let unmapped = pm.unmap_owned(&mut fa, slot, &mapped);
    eprintln!(
        "LIVE_F1_RED retained={retained_address:#x} mapped={mapped_address:#x} \
         before_capacity={before_capacity:?} before_pte={before_entry:?} \
         before_pde={before_directory:#x} released={released} unmapped={unmapped} \
         retained_live={} retained_free={} mapped_live={} mapped_pin={} after_pte={:?} \
         after_capacity=({}, {})",
        fa.owns_live_lease(&retained),
        fa.is_free(retained_address),
        fa.owns_live_lease(&mapped),
        fa.runtime_pinned(mapped_address),
        pm.entry(slot),
        fa.stats().free_frames,
        fa.stats().allocated_frames,
    );
    assert!(
        !released && !unmapped,
        "F1 missing joint seal: retained live frame release/unmap must be refused"
    );
    assert!(fa.owns_live_lease(&retained));
    assert!(!fa.is_free(retained_address));
    assert!(fa.owns_live_lease(&mapped));
    assert!(fa.runtime_pinned(mapped_address));
    assert_eq!(pm.entry(slot), before_entry);
    assert_eq!(
        read_entry(pm.directory, page_dir_index(slot)),
        before_directory
    );
    assert_eq!(
        (fa.stats().free_frames, fa.stats().allocated_frames),
        before_capacity
    );
}
