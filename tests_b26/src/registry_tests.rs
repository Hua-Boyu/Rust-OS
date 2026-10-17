use super::*;

#[test]
fn b26_registry_backing_is_retained_on_rollback_and_moved_on_success() {
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 2 * 4096)], 0x200000, 0x300000, 0x310000);
    let mut tables = vec![0; memory::paging::PAGE_DIR_ENTRIES];
    let mut pins = vec![(0x20000, 0x21000)];
    let mut bitmap = vec![0; memory::paging::PAYLOAD_BITMAP_BYTES];
    let pointer = bitmap.as_ptr();
    let capacity = bitmap.capacity();
    // Directory + first table fit; the second table fails. All backing must
    // remain with the caller until its frame guard can be released.
    assert!(
        memory::paging::build_identity_map_with_backing_in_place(
            &mut fa,
            0x400001,
            &mut tables,
            &mut pins,
            &mut bitmap,
        )
        .is_none()
    );
    assert_eq!(bitmap.as_ptr(), pointer);
    assert_eq!(bitmap.capacity(), capacity);
    assert!(bitmap.iter().all(|&byte| byte == 0));
    assert!(tables.iter().all(|&table| table == 0));
    assert_eq!(pins, [(0x20000, 0x21000)]);
    assert_eq!(fa.stats().allocated_frames, 0);
    assert_eq!(fa.stats().free_frames, 2);
    let pm = memory::paging::build_identity_map_with_backing_in_place(
        &mut fa,
        0x20000,
        &mut tables,
        &mut pins,
        &mut bitmap,
    )
    .unwrap();
    assert_eq!(bitmap.capacity(), 0);
    assert_eq!(tables.capacity(), 0);
    assert_eq!(pins.capacity(), 0);
    assert_eq!(pm.translate(0x10000), Some(0x10000));
    assert_eq!(fa.stats().allocated_frames, 2);
    assert_eq!(fa.stats().invalid_frees, 0);
    assert_eq!(fa.stats().double_frees, 0);
}

#[test]
fn b26_registry_invalid_backing_is_rejected_before_frame_mutation() {
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 2 * 4096)], 0x200000, 0x300000, 0x310000);
    let mut tables = vec![0; memory::paging::PAGE_DIR_ENTRIES];
    let mut pins = Vec::new();
    for length in [
        0,
        memory::paging::PAYLOAD_BITMAP_BYTES - 1,
        memory::paging::PAYLOAD_BITMAP_BYTES + 1,
    ] {
        let mut bitmap = vec![0; length];
        assert!(
            memory::paging::build_identity_map_with_backing_in_place(
                &mut fa,
                0x20000,
                &mut tables,
                &mut pins,
                &mut bitmap,
            )
            .is_none()
        );
        assert_eq!(fa.stats().allocated_frames, 0);
        assert_eq!(fa.stats().free_frames, 2);
        assert_eq!(bitmap.len(), length);
    }
    let mut bitmap = vec![0; memory::paging::PAYLOAD_BITMAP_BYTES];
    bitmap[0] = 1;
    assert!(
        memory::paging::build_identity_map_with_backing_in_place(
            &mut fa,
            0x20000,
            &mut tables,
            &mut pins,
            &mut bitmap,
        )
        .is_none()
    );
    assert_eq!(bitmap[0], 1);
    assert_eq!(fa.stats().allocated_frames, 0);
    assert_eq!(fa.stats().free_frames, 2);
}
