use super::*;

#[test]
fn b26_failed_builder_clears_released_slots_before_retry() {
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 4 * 4096)], 0x200000, 0x300000, 0x310000);
    for length in [0, 1023, 1025] {
        let mut invalid = vec![0; length];
        assert!(
            memory::paging::build_identity_map_in_place(&mut fa, 0x1000000, &mut invalid).is_none()
        );
        assert_eq!(fa.stats().allocated_frames, 0);
        assert_eq!(fa.stats().free_frames, 4);
    }
    let mut stale = vec![0; memory::paging::PAGE_DIR_ENTRIES];
    stale[0] = 0x10000;
    assert!(memory::paging::build_identity_map_in_place(&mut fa, 0x1000000, &mut stale).is_none());
    assert_eq!(stale[0], 0x10000);
    assert_eq!(fa.stats().allocated_frames, 0);
    assert_eq!(fa.stats().free_frames, 4);
    let mut tables = vec![0; memory::paging::PAGE_DIR_ENTRIES];
    assert!(memory::paging::build_identity_map_in_place(&mut fa, 0x1000000, &mut tables).is_none());
    assert!(
        tables.iter().all(|&frame| frame == 0),
        "rollback must clear returned frame ownership"
    );
    let held = [fa.allocate().unwrap(), fa.allocate().unwrap()];
    assert!(memory::paging::build_identity_map_in_place(&mut fa, 0x1000000, &mut tables).is_none());
    assert_eq!(fa.stats().allocated_frames, 2);
    assert_eq!(fa.stats().free_frames, 2);
    assert_eq!(fa.stats().double_frees, 0);
    assert_eq!(fa.stats().invalid_frees, 0);
    assert!(held.iter().all(|&frame| !fa.is_free(frame)));
    assert!(tables.iter().all(|&frame| frame == 0));
}
