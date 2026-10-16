use super::*;

#[test]
fn b26_validation_failure_returns_directory_and_table_frames_without_locked_drop() {
    let _serial = TEST_LOCK.lock().unwrap();
    let entries = [entry(0x10000, 8192)];
    BACKING_ONLY.store(true, Ordering::Relaxed);
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    WATCH.store(true, Ordering::Relaxed);
    let result = memory::prepare(&entries, 0x200000, 0x300000, 0x310000);
    WATCH.store(false, Ordering::Relaxed);
    BACKING_ONLY.store(false, Ordering::Relaxed);
    let missing = result.unwrap_err();
    assert_eq!(missing, "VGA framebuffer");
    assert!(memory::page_directory().is_none());
    assert!(!memory::FRAME_ALLOC.is_locked());
    let stats = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(
        stats.allocated_frames, 0,
        "unpublished map must return all owned frames"
    );
    assert_eq!(stats.free_frames, 2);
    assert_eq!(stats.invalid_frees, 0);
    assert_eq!(stats.double_frees, 0);
    assert_eq!(ALLOCS.load(Ordering::Relaxed), 0);
    assert_eq!(DEALLOCS.load(Ordering::Relaxed), 0);
}
