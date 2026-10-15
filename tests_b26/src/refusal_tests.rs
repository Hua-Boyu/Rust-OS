use super::*;

fn refused_prepare(fail_at: usize) {
    let _serial = TEST_LOCK.lock().unwrap();
    let entries = [entry(0x10000, 0x400000)];
    memory::FRAME_ALLOC
        .lock()
        .init(&entries, 0x200000, 0x300000, 0x310000);
    let before = *memory::FRAME_ALLOC.lock().stats();
    ATTEMPTS.with(|count| count.set(0));
    REFUSE_AT.with(|at| at.set(fail_at));
    let result = memory::prepare(&entries, 0x200000, 0x300000, 0x310000);
    REFUSE_AT.with(|at| at.set(0));
    let attempts = ATTEMPTS.with(|count| count.get());
    assert_eq!(
        result,
        Err(if fail_at == 1 {
            "boot pin backing allocation failed"
        } else {
            "page table backing allocation failed"
        })
    );
    assert!(memory::page_map_ref().is_none());
    assert!(!memory::FRAME_ALLOC.is_locked());
    let after = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(after.allocated_frames, before.allocated_frames);
    assert_eq!(after.free_frames, before.free_frames);
    assert_eq!(after.reserved_frames, before.reserved_frames);
    assert_eq!(after.invalid_frees, before.invalid_frees);
    assert_eq!(after.double_frees, before.double_frees);
    assert_eq!(
        attempts, fail_at,
        "refusal must not allocate fallback diagnostics"
    );
}

#[test]
fn b26_r3_pin_backing_refusal_has_no_fallback_allocation_or_frame_mutation() {
    refused_prepare(1);
}

#[test]
fn b26_r3_table_backing_refusal_has_no_fallback_allocation_or_frame_mutation() {
    refused_prepare(2);
}
