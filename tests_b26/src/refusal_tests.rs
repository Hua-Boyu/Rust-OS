use super::*;

fn refused_prepare(fail_at: usize) {
    let _serial = TEST_LOCK.lock().unwrap();
    let entries = [entry(0x10000, 0x400000)];
    memory::FRAME_ALLOC
        .lock()
        .init(&entries, 0x200000, 0x300000, 0x310000);
    let before = *memory::FRAME_ALLOC.lock().stats();
    ATTEMPTS.with(|count| count.set(0));
    UNLOCKED_ATTEMPTS.with(|count| count.set(0));
    BACKING_ONLY.store(false, Ordering::Relaxed);
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    WATCH.store(true, Ordering::Relaxed);
    REFUSE_AT.with(|at| at.set(fail_at));
    let result = memory::prepare(&entries, 0x200000, 0x300000, 0x310000);
    REFUSE_AT.with(|at| at.set(0));
    WATCH.store(false, Ordering::Relaxed);
    assert_eq!(UNLOCKED_ATTEMPTS.with(|count| count.get()), fail_at);
    assert!(!owner_locks_held());
    assert_eq!(ALLOCS.load(Ordering::Relaxed), 0);
    assert_eq!(DEALLOCS.load(Ordering::Relaxed), 0);
    let attempts = ATTEMPTS.with(|count| count.get());
    assert_eq!(
        result,
        Err(match fail_at {
            1 => "boot pin backing allocation failed",
            2 => "page table backing allocation failed",
            3 => "payload registry backing allocation failed",
            _ => unreachable!(),
        })
    );
    assert!(memory::page_directory().is_none());
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
fn b26_owner_rejection_paths_never_allocate_or_destroy_under_either_guard() {
    let _serial = TEST_LOCK.lock().unwrap();
    let entries = [entry(0x10000, 0x400000)];
    assert!(memory::page_directory().is_none());
    memory::FRAME_ALLOC
        .lock()
        .init(&entries, 0x200000, 0x300000, 0x310000);
    let held = memory::FRAME_ALLOC.lock().allocate().unwrap();
    let before = *memory::FRAME_ALLOC.lock().stats();
    // Neither rejection builds host mirrors: observe ALL layouts, including
    // destruction after FRAME_ALLOC is released but PAGE_MAP remains owned.
    BACKING_ONLY.store(false, Ordering::Relaxed);
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    WATCH.store(true, Ordering::Relaxed);
    let growth = memory::heap_grow_frame(memory::GROWTH_START);
    let prepare = memory::prepare(&entries, 0x200000, 0x300000, 0x310000);
    WATCH.store(false, Ordering::Relaxed);
    assert!(!owner_locks_held());
    assert_eq!(ALLOCS.load(Ordering::Relaxed), 0);
    assert_eq!(DEALLOCS.load(Ordering::Relaxed), 0);
    assert_eq!(growth, None);
    assert_eq!(prepare, Err("frame allocator initialization refused"));
    assert!(memory::page_directory().is_none());
    let after = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(after.allocated_frames, before.allocated_frames);
    assert_eq!(after.free_frames, before.free_frames);
    assert_eq!(after.reserved_frames, before.reserved_frames);
    assert_eq!(after.invalid_frees, before.invalid_frees);
    assert_eq!(after.double_frees, before.double_frees);
    assert!(memory::FRAME_ALLOC.lock().free(held));
}

#[test]
fn b26_r3_pin_backing_refusal_has_no_fallback_allocation_or_frame_mutation() {
    refused_prepare(1);
}

#[test]
fn b26_r3_table_backing_refusal_has_no_fallback_allocation_or_frame_mutation() {
    refused_prepare(2);
}

#[test]
fn b26_phase11a2_registry_backing_refusal_has_no_fallback_allocation_or_frame_mutation() {
    refused_prepare(3);
}
