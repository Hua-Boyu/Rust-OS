//! Detector controls live inside the owner module; no owner guard is exported.
// This feature belongs to the independently rooted B26 crate, not the kernel.
#![cfg(feature = "b26-observation")]

use super::*;
use crate::{ALLOCS, BACKING_ONLY, DEALLOCS, TEST_LOCK, WATCH};

fn observe_owner_only(frame: bool, allocate: bool) {
    let _serial = TEST_LOCK.lock().unwrap();
    BACKING_ONLY.store(false, Ordering::Relaxed);
    // Preallocate destruction's object before taking either owner guard.
    let layout = std::alloc::Layout::from_size_align(37, 8).unwrap();
    let existing = unsafe { std::alloc::alloc(layout) };
    assert!(!existing.is_null());
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    let map_guard = (!frame).then(|| PAGE_MAP.lock());
    let frame_guard = frame.then(|| FRAME_ALLOC.lock());
    assert_eq!(FRAME_ALLOC.is_locked(), frame);
    assert_eq!(PAGE_MAP.is_locked(), !frame);
    WATCH.store(true, Ordering::Relaxed);
    let allocated = if allocate {
        unsafe { std::alloc::alloc(layout) }
    } else {
        unsafe { std::alloc::dealloc(existing, layout) };
        core::ptr::null_mut()
    };
    WATCH.store(false, Ordering::Relaxed);
    drop(frame_guard);
    drop(map_guard);
    // Assert only after unlock, so failure formatting cannot affect observation.
    if allocate {
        assert!(!allocated.is_null());
        unsafe {
            std::alloc::dealloc(allocated, layout);
            std::alloc::dealloc(existing, layout);
        }
    }
    assert_eq!(ALLOCS.load(Ordering::Relaxed), usize::from(allocate));
    assert_eq!(DEALLOCS.load(Ordering::Relaxed), usize::from(!allocate));
}

#[test]
fn b26_page_map_only_attempt_is_not_classified_unlocked() {
    let _serial = TEST_LOCK.lock().unwrap();
    let layout = std::alloc::Layout::from_size_align(37, 8).unwrap();
    crate::ATTEMPTS.with(|count| count.set(0));
    crate::UNLOCKED_ATTEMPTS.with(|count| count.set(0));
    let owner = PAGE_MAP.lock();
    assert!(!FRAME_ALLOC.is_locked());
    crate::REFUSE_AT.with(|at| at.set(usize::MAX));
    let ptr = unsafe { std::alloc::alloc(layout) };
    crate::REFUSE_AT.with(|at| at.set(0));
    drop(owner);
    assert!(!ptr.is_null());
    unsafe { std::alloc::dealloc(ptr, layout) };
    assert_eq!(crate::ATTEMPTS.with(|count| count.get()), 1);
    assert_eq!(crate::UNLOCKED_ATTEMPTS.with(|count| count.get()), 0);
}

#[test]
fn b26_detector_observes_page_map_only_allocation() {
    observe_owner_only(false, true);
}

#[test]
fn b26_detector_observes_page_map_only_destruction() {
    observe_owner_only(false, false);
}

#[test]
fn b26_detector_observes_frame_only_allocation() {
    observe_owner_only(true, true);
}

#[test]
fn b26_detector_observes_frame_only_destruction() {
    observe_owner_only(true, false);
}
