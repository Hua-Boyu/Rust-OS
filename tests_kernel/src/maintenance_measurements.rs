//! Explicit investigative measurements, not release performance thresholds.
use super::*;

#[test]
#[ignore]
fn measured_frame_scan_states() {
    for (name, held) in [("sparse", 0), ("dense", 1000)] {
        for sample in 0..9 {
            let mut fa = memory::frame::FrameAllocator::new();
            fa.init(
                &[mmap_entry(0x10000, 0x800000, 1)],
                0x10000,
                0x11000,
                0x12000,
            );
            for _ in 0..held {
                fa.allocate().unwrap();
            }
            let start = std::time::Instant::now();
            for _ in 0..100 {
                let frame = fa.allocate().unwrap();
                assert!(fa.free(frame));
            }
            std::println!(
                "C04 state={name} sample={sample} ops=100 ns={}",
                start.elapsed().as_nanos()
            );
        }
    }
    for sample in 0..9 {
        let mut fa = memory::frame::FrameAllocator::new();
        fa.init(
            &[mmap_entry(0x10000, 0x800000, 1)],
            0x10000,
            0x11000,
            0x12000,
        );
        while fa.allocate().is_some() {}
        let before_allocated = fa.stats().allocated_frames;
        let start = std::time::Instant::now();
        for _ in 0..100 {
            assert_eq!(fa.allocate(), None);
        }
        std::println!(
            "C04 state=exhausted sample={sample} ops=100 ns={}",
            start.elapsed().as_nanos()
        );
        assert_eq!(fa.stats().allocated_frames, before_allocated);
        assert_eq!(fa.stats().free_frames, 0);
    }
}

#[test]
#[ignore]
fn measured_heap_capacity_loss() {
    for (name, size, align) in [("aligned", 8, 16), ("tiny_tail", 4081, 1)] {
        let heap = utils::mutex::SpinMutex::new(allocator::KernelHeap::new());
        heap.lock().add_region(0x200000, 0x201000);
        let before = heap.lock().stats;
        let layout = Layout::from_size_align(size, align).unwrap();
        let ptr = unsafe { heap.alloc(layout) };
        assert!(!ptr.is_null());
        assert_eq!(ptr as usize % align, 0);
        unsafe { heap.dealloc(ptr, layout) };
        let after = heap.lock().stats;
        assert_eq!(after.used, 0);
        assert_eq!(after.live_allocs, 0);
        assert_eq!(after.capacity, before.capacity);
        std::println!(
            "C05 state={name} before_free={} after_free={} stranded={} waste={}",
            before.free,
            after.free,
            before.free - after.free,
            after.waste
        );
        // Observational only: do not turn the known loss into a required contract.
        // Future reclamation work must add a RED exact-restoration regression.
    }
}
