use super::*;

// Boundary/oracle coverage supplements the independently recorded RED/GREEN
// regressions below; these do not require additional production changes.
#[test]
fn b11_growth_requires_complete_usable_frame_and_exact_valid_address() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    assert_eq!(fa.claim_growth_frame(g), None);
    let entries = [
        entry(g + 1, 3 * 4096 - 2, 1),
        entry(g + 3 * 4096, 0, 1),
        entry(g + 3 * 4096, u64::MAX, 1),
    ];
    fa.init(&entries, 0x10000, 0x20000, 0x21000);
    for addr in [
        g - 4096,
        g,
        g + 1,
        g + 8192,
        g + 12288,
        paging::GROWTH_END as u64,
        MAX_FRAME_ADDR,
        u64::MAX,
    ] {
        assert_eq!(fa.claim_growth_frame(addr), None, "address {addr:#x}");
    }
    assert_eq!(fa.claim_growth_frame(g + 4096), Some(g + 4096));
    assert_eq!(fa.stats().total_frames, 1);
    assert_eq!(fa.stats().allocated_frames, 1);
    assert_eq!(fa.stats().reserved_frames, 0);
}

#[test]
fn b11_reserved_overflow_denies_growth_to_end_without_wrapping() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(
        &[entry(g, 8192, 1), entry(g + 1, u64::MAX, 2)],
        0x10000,
        0x20000,
        0x21000,
    );
    assert_eq!(fa.claim_growth_frame(g), None);
    assert_eq!(fa.claim_growth_frame(g + 4096), None);
    assert_eq!(fa.stats().allocated_frames, 0);
}

#[test]
fn b11_exact_growth_denial_does_not_skip_to_later_eligible_frame() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(
        &[entry(g, 12288, 1), entry(g + 4096, 1, 2)],
        0x10000,
        0x20000,
        0x21000,
    );
    assert_eq!(fa.claim_growth_frame(g), Some(g));
    let before = *fa.stats();
    for _ in 0..3 {
        assert_eq!(fa.claim_growth_frame(g + 4096), None);
    }
    assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
    assert_eq!(fa.stats().reserved_frames, before.reserved_frames);
    // A caller explicitly asking for the later address can claim it, but
    // the failed contiguous request never returns or consumes that address.
    assert_eq!(fa.claim_growth_frame(g + 8192), Some(g + 8192));
}

#[test]
fn b11_general_pool_obeys_pins_kernel_vga_and_live_ownership() {
    let mut fa = FrameAllocator::new();
    let g = paging::GROWTH_START as u64;
    let entries = [
        entry(0, 4096, 1),
        entry(VGA_START, 4096, 1),
        entry(0x10000, 12288, 1),
        entry(g, 4096, 1),
    ];
    assert!(fa.init_with_reservations(
        &entries,
        0x30000,
        0x40000,
        0x41000,
        &[(0x10001, 0x10002), (0x10001, 0x10002)]
    ));
    for addr in [0, VGA_START, 0x10000, g, MAX_FRAME_ADDR, u64::MAX] {
        assert!(!fa.free(addr));
    }
    assert_eq!(fa.allocate(), Some(0x11000));
    assert_eq!(fa.allocate(), Some(0x12000));
    assert_eq!(fa.allocate(), None);
    assert!(!fa.free(0x11001));
    assert_eq!(fa.stats().allocated_frames, 2);
    assert!(fa.free(0x11000));
    assert!(!fa.free(0x11000));
    assert_eq!(fa.stats().double_frees, 1);
    assert_eq!(fa.allocate(), Some(0x11000));
    assert_eq!(
        fa.stats().total_frames,
        fa.stats().reserved_frames + fa.stats().allocated_frames + fa.stats().free_frames
    );
}

#[test]
fn b11_reservation_union_matches_independent_small_window_oracle() {
    let g = paging::GROWTH_START as u64;
    for seed in 0u64..48 {
        let spans = [
            (g + seed * 251 % 16384, g + seed * 251 % 16384 + seed % 8193),
            (g + 4095, g + 4097),
            (g + 8192, g + 8192),
        ];
        let usable = entry(g + seed % 2, 16384 - seed % 3, 1);
        let firmware = entry(g + seed * 137 % 16384, seed % 17, 2);
        let mut fa = FrameAllocator::new();
        assert!(fa.init_with_reservations(
            &[usable, usable, firmware, firmware],
            0x10000,
            0x20000,
            0x21000,
            &spans
        ));
        let mut count = 0;
        for i in 0..4 {
            let start = g + i * 4096;
            let end = start + 4096;
            let complete = start >= usable.base_addr && end <= usable.base_addr + usable.length;
            let blocked = (firmware.length != 0
                && start < firmware.base_addr + firmware.length
                && end > firmware.base_addr)
                || spans.iter().any(|&(a, b)| a < b && start < b && end > a);
            let expected = if complete && !blocked {
                count += 1;
                Some(start)
            } else {
                None
            };
            assert_eq!(
                fa.claim_growth_frame(start),
                expected,
                "seed {seed}, frame {i}"
            );
        }
        assert_eq!(fa.stats().allocated_frames, count);
        assert_eq!(fa.stats().free_frames, 0);
    }
}

#[test]
fn b11_empty_bootstrap_span_does_not_deny_growth() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(&[entry(g, 4096, 1)], 0x10000, g + 1, g + 1);
    assert_eq!(fa.claim_growth_frame(g), Some(g));
}

#[test]
fn b11_released_growth_frame_returns_to_growth_only_pool() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(&[entry(g, 8192, 1)], 0x10000, 0x20000, 0x21000);
    assert!(!fa.free(g), "never claimed is not releasable");
    assert_eq!(fa.claim_growth_frame(g), Some(g));
    assert_eq!(fa.claim_growth_frame(g), None);
    assert!(fa.free(g));
    assert!(
        !fa.is_free(g),
        "growth page is not general-purpose free capacity"
    );
    assert_eq!(fa.stats().reserved_frames, 2);
    assert_eq!(fa.stats().free_frames, 0);
    assert_eq!(fa.stats().allocated_frames, 0);
    assert!(!fa.free(g));
    assert_eq!(fa.stats().double_frees, 1);
    assert_eq!(
        fa.allocate(),
        None,
        "page tables must never consume growth pages"
    );
    assert_eq!(
        fa.claim_growth_frame(g),
        Some(g),
        "failed mapping rollback can retry"
    );
    assert!(fa.free(g));
}

#[test]
fn b11_explicit_boot_spans_deny_all_touched_frames_and_dedupe_accounting() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    let ranges = [
        (g + 4095, g + 4097),
        (g + 4096, g + 4097),
        (g + 8192, g + 8192),
    ];
    assert!(fa.init_with_reservations(&[entry(g, 12288, 1)], 0x10000, 0x20000, 0x21000, &ranges));
    assert_eq!(fa.stats().total_frames, 3);
    assert_eq!(fa.stats().reserved_frames, 3);
    assert_eq!(fa.claim_growth_frame(g), None);
    assert_eq!(fa.claim_growth_frame(g + 4096), None);
    assert_eq!(fa.claim_growth_frame(g + 8192), Some(g + 8192));
    assert_eq!(fa.stats().reserved_frames, 2);
    assert_eq!(fa.stats().allocated_frames, 1);
}

#[test]
fn b11_invalid_explicit_span_fails_closed_even_after_reinitialization() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(&[entry(g, 4096, 1)], 0x10000, 0x20000, 0x21000);
    assert!(!fa.init_with_reservations(
        &[entry(g, 4096, 1)],
        0x10000,
        0x20000,
        0x21000,
        &[(g + 1, g)]
    ));
    assert!(!fa.is_initialized());
    assert_eq!(fa.allocate(), None);
    assert_eq!(fa.claim_growth_frame(g), None);
    assert_eq!(fa.stats().allocated_frames, 0);
}

#[test]
fn b11_boot_and_bootstrap_heap_override_growth_reservation() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(
        &[entry(g, 4 * FRAME_SIZE as u64, 1)],
        g + 1,
        g + 8193,
        g + 8194,
    );
    assert_eq!(fa.claim_growth_frame(g), None);
    assert_eq!(
        fa.claim_growth_frame(g + 4096),
        None,
        "unaligned boot info spans two frames"
    );
    assert_eq!(
        fa.claim_growth_frame(g + 8192),
        None,
        "one byte of heap blocks whole frame"
    );
    assert_eq!(fa.claim_growth_frame(g + 12288), Some(g + 12288));
}

#[test]
fn b11_bootinfo_span_overflow_never_panics_or_wraps() {
    let g = paging::GROWTH_START as u64;
    let mut fa = FrameAllocator::new();
    fa.init(&[entry(g, 4096, 1)], u64::MAX - 1, 0x10000, 0x11000);
    assert_eq!(fa.claim_growth_frame(g), Some(g));
}

fn entry(base_addr: u64, length: u64, type_: u32) -> MmapEntry {
    MmapEntry {
        size: 20,
        base_addr,
        length,
        type_,
    }
}

#[test]
fn b11_competing_mmap_reservations_deny_growth_in_any_order() {
    let g = paging::GROWTH_START as u64;
    for kind in [0, 2, 3, 4, 5, u32::MAX] {
        for reverse in [false, true] {
            let mut entries = [entry(g, 3 * FRAME_SIZE as u64, 1), entry(g + 1, 1, kind)];
            if reverse {
                entries.reverse();
            }
            let mut fa = FrameAllocator::new();
            fa.init(&entries, 0x10000, 0x20000, 0x21000);
            let before = *fa.stats();
            assert_eq!(
                fa.claim_growth_frame(g),
                None,
                "type {kind}, reversed {reverse}"
            );
            assert_eq!(fa.stats().reserved_frames, before.reserved_frames);
            assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
            assert_eq!(
                fa.claim_growth_frame(g + FRAME_SIZE as u64),
                Some(g + FRAME_SIZE as u64)
            );
        }
    }
}
