use super::*;

#[test]
fn b26_r3_prepare_validation_needs_only_two_fallible_backing_allocations() {
    let _serial = TEST_LOCK.lock().unwrap();
    let entries = [entry(0x10000, 8192)];
    UNLOCKED_ATTEMPTS.with(|count| count.set(0));
    ATTEMPTS.with(|count| count.set(0));
    REFUSE_AT.with(|at| at.set(usize::MAX));
    let result = memory::prepare(&entries, 0x200000, 0x300000, 0x310000);
    REFUSE_AT.with(|at| at.set(0));
    let allocations = UNLOCKED_ATTEMPTS.with(|count| count.get());
    assert_eq!(result, Err("VGA framebuffer"));
    assert!(memory::page_directory().is_none());
    let stats = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(stats.allocated_frames, 0);
    assert_eq!(stats.free_frames, 2);
    assert_eq!(stats.invalid_frees, 0);
    assert_eq!(stats.double_frees, 0);
    assert_eq!(
        allocations, 2,
        "validation and its diagnostics must not allocate"
    );
}
