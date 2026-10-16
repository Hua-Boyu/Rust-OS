//! Separate binary: allocator instrumentation must not affect the shared test root.
#![cfg(test)]
#![allow(dead_code)]

extern crate alloc;

use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

#[macro_export]
macro_rules! println {
    ($($arg:tt)*) => { let _ = ::core::format_args!($($arg)*); };
}

pub mod utils {
    pub mod bits {
        include!(concat!(env!("CARGO_MANIFEST_DIR"), "/../src/utils/bits.rs"));
    }
    pub mod mutex {
        include!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../src/utils/mutex.rs"
        ));
    }
}
// Wire input only; independent of concurrent boot-inventory work.
pub mod multiboot {
    #[derive(Clone, Copy)]
    #[repr(C, packed)]
    pub struct MmapEntry {
        pub size: u32,
        pub base_addr: u64,
        pub length: u64,
        pub type_: u32,
    }
}
#[path = "../../src/memory/mod.rs"]
pub mod memory;

#[path = "validation_tests.rs"]
mod b26_validation;
mod growth_tests;
mod refusal_tests;
mod retry_tests;
mod validation_allocation_tests;

struct ObservedAllocator;
// Observe only the invoking test thread. Other parallel tests and the Rust
// harness may allocate while this thread owns FRAME_ALLOC; those unrelated
// operations do not represent a frame -> heap acquisition on the owner path.
std::thread_local! {
    static WATCH_LOCAL: core::cell::Cell<bool> = const { core::cell::Cell::new(false) };
    // Refuse exactly one allocation, then count any unsafe fallback attempts
    // while allowing them so the regression reports a failure, not host abort.
    static REFUSE_AT: core::cell::Cell<usize> = const { core::cell::Cell::new(0) };
    static ATTEMPTS: core::cell::Cell<usize> = const { core::cell::Cell::new(0) };
    static UNLOCKED_ATTEMPTS: core::cell::Cell<usize> = const { core::cell::Cell::new(0) };
}
struct Watch;
static WATCH: Watch = Watch;
impl Watch {
    fn load(&self, _: Ordering) -> bool {
        WATCH_LOCAL.try_with(|flag| flag.get()).unwrap_or(false)
    }
    fn store(&self, value: bool, _: Ordering) {
        WATCH_LOCAL.with(|flag| flag.set(value));
    }
}
static BACKING_ONLY: AtomicBool = AtomicBool::new(false);
static TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn watched(layout: Layout) -> bool {
    WATCH.load(Ordering::Relaxed)
        && memory::FRAME_ALLOC.is_locked()
        && (!BACKING_ONLY.load(Ordering::Relaxed)
            || layout.size() == memory::paging::PAGE_DIR_ENTRIES * size_of::<u64>()
            || layout.size() == size_of::<&str>())
}
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static DEALLOCS: AtomicUsize = AtomicUsize::new(0);
#[global_allocator]
static ALLOCATOR: ObservedAllocator = ObservedAllocator;

unsafe impl GlobalAlloc for ObservedAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let refuse = REFUSE_AT
            .try_with(|at| {
                if at.get() == 0 {
                    return false;
                }
                if !memory::FRAME_ALLOC.is_locked() {
                    UNLOCKED_ATTEMPTS.with(|count| count.set(count.get() + 1));
                }
                ATTEMPTS.with(|count| {
                    let next = count.get() + 1;
                    count.set(next);
                    next == at.get()
                })
            })
            .unwrap_or(false);
        if refuse {
            return core::ptr::null_mut();
        }
        if watched(layout) {
            ALLOCS.fetch_add(1, Ordering::Relaxed);
        }
        unsafe { System.alloc(layout) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        if watched(layout) {
            DEALLOCS.fetch_add(1, Ordering::Relaxed);
        }
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[test]
fn b26_prepare_directory_exhaustion_never_enters_heap_under_frame_guard() {
    let _serial = TEST_LOCK.lock().unwrap();
    BACKING_ONLY.store(false, Ordering::Relaxed);
    // No available frames: no host-only MIRROR allocation can obscure the result.
    // Watch every allocation/deallocation, not merely the known Vec layouts.
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    WATCH.store(true, Ordering::Relaxed);
    let result = memory::prepare(&[], 0x200000, 0x300000, 0x310000);
    WATCH.store(false, Ordering::Relaxed);
    assert_eq!(result, Err("frame exhaustion during page table build"));
    assert!(!memory::FRAME_ALLOC.is_locked());
    let stats = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(stats.allocated_frames, 0);
    assert_eq!(stats.free_frames, 0);
    assert_eq!(stats.invalid_frees, 0);
    assert_eq!(stats.double_frees, 0);
    assert_eq!(
        (
            ALLOCS.load(Ordering::Relaxed),
            DEALLOCS.load(Ordering::Relaxed)
        ),
        (0, 0),
        "heap allocation AND destruction must happen after releasing the frame guard"
    );
}

fn entry(base_addr: u64, length: u64) -> multiboot::MmapEntry {
    multiboot::MmapEntry {
        size: 20,
        base_addr,
        length,
        type_: 1,
    }
}

#[test]
fn b26_prepare_partial_exhaustion_restores_frames_and_unlocks_before_vec_ops() {
    let _serial = TEST_LOCK.lock().unwrap();
    // The cfg(test) page-table MIRROR allocates host-only HashMaps/Vecs. Watch
    // actual production table/error backing layouts here, not mirror storage.
    // Directory exhaustion above independently watches ALL heap operations.
    BACKING_ONLY.store(true, Ordering::Relaxed);
    for available in 1..=4 {
        let entries = [entry(0x10000, available * 4096), entry(0x1000000, 1)];
        ALLOCS.store(0, Ordering::Relaxed);
        DEALLOCS.store(0, Ordering::Relaxed);
        WATCH.store(true, Ordering::Relaxed);
        let result = memory::prepare(&entries, 0x200000, 0x300000, 0x310000);
        WATCH.store(false, Ordering::Relaxed);
        assert_eq!(result, Err("frame exhaustion during page table build"));
        assert!(!memory::FRAME_ALLOC.is_locked());
        let stats = *memory::FRAME_ALLOC.lock().stats();
        assert_eq!(stats.allocated_frames, 0, "{available} initial frames");
        assert_eq!(stats.free_frames, available as usize);
        assert_eq!(stats.invalid_frees, 0);
        assert_eq!(stats.double_frees, 0);
        assert_eq!(ALLOCS.load(Ordering::Relaxed), 0);
        assert_eq!(DEALLOCS.load(Ordering::Relaxed), 0);
    }
    BACKING_ONLY.store(false, Ordering::Relaxed);
}

#[test]
fn b26_borrowed_builder_retains_failure_backing_and_transfers_on_success() {
    let _serial = TEST_LOCK.lock().unwrap();
    let mut fa = memory::frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 2 * 4096)], 0x200000, 0x300000, 0x310000);
    for window in [0, (1u64 << 32) + 1, 0x400001] {
        let mut tables = vec![0; memory::paging::PAGE_DIR_ENTRIES];
        let ptr = tables.as_ptr();
        let cap = tables.capacity();
        assert!(
            memory::paging::build_identity_map_in_place(&mut fa, window, &mut tables).is_none()
        );
        assert_eq!(tables.as_ptr(), ptr);
        assert_eq!(tables.len(), memory::paging::PAGE_DIR_ENTRIES);
        assert_eq!(tables.capacity(), cap);
        assert_eq!(fa.stats().allocated_frames, 0);
        assert_eq!(fa.stats().free_frames, 2);
        assert_eq!(fa.stats().invalid_frees, 0);
        assert_eq!(fa.stats().double_frees, 0);
    }
    let mut tables = vec![0; memory::paging::PAGE_DIR_ENTRIES];
    let pm = memory::paging::build_identity_map_in_place(&mut fa, 0x20000, &mut tables).unwrap();
    assert_eq!(
        tables.capacity(),
        0,
        "success moves, rather than copies, backing"
    );
    assert_eq!(fa.stats().allocated_frames, 2);
    assert_eq!(fa.stats().free_frames, 0);
    assert_eq!(pm.stats().page_tables, 1);
    assert_eq!(pm.stats().mapped_frames, 31);
    assert_eq!(pm.translate(0), None);
    assert_eq!(pm.translate(0x10000), Some(0x10000));
    assert_eq!(pm.translate(0x20000), None);
}
