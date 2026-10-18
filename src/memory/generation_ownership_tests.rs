//! Generation ownership probes. Forged duplicates are cfg(test)-only authority,
//! not evidence that production callers can duplicate leases or of CPU lifetime.
use super::*;
use crate::multiboot::MmapEntry;

// Inference is ambiguous if either forbidden trait is ever implemented.
const _: fn() = || {
    trait NotCopy<A> {
        fn check() {}
    }
    impl<T: ?Sized> NotCopy<()> for T {}
    impl<T: ?Sized + Copy> NotCopy<u8> for T {}
    let _ = <frame::FrameLease as NotCopy<_>>::check;
    trait NotClone<A> {
        fn check() {}
    }
    impl<T: ?Sized> NotClone<()> for T {}
    impl<T: ?Sized + Clone> NotClone<u8> for T {}
    let _ = <frame::FrameLease as NotClone<_>>::check;
};

fn entries() -> [MmapEntry; 1] {
    [MmapEntry {
        size: 20,
        base_addr: 0x10000,
        length: 0x70000,
        type_: 1,
    }]
}

fn lease_fixture() -> (FrameAllocator, PageMap) {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    (fa, pm)
}

fn capacity(fa: &FrameAllocator) -> (usize, usize, usize) {
    let s = fa.stats();
    (s.free_frames, s.allocated_frames, s.reserved_frames)
}

fn transfer_lease(lease: frame::FrameLease) -> frame::FrameLease {
    lease
}

#[test]
fn generation_safe_stale_lease_cannot_release_reused_frame() {
    let (mut fa, _) = lease_fixture();
    let baseline = capacity(&fa);
    let lease = fa.allocate_owned().unwrap();
    let stale = lease.duplicate_for_test();
    let addr = lease.frame_addr();
    assert!(fa.release_frame(lease));
    let current = fa.allocate_owned().unwrap();
    assert_eq!(current.frame_addr(), addr);
    let before = capacity(&fa);
    assert!(
        !fa.release_frame(stale),
        "BLOCKER: stale lease released reused frame"
    );
    assert_eq!(capacity(&fa), before);
    assert!(!fa.is_free(addr));
    assert!(fa.release_frame(current));
    assert!(fa.is_free(addr));
    assert_eq!(capacity(&fa), baseline);
}

#[test]
fn generation_safe_double_release_of_lease_is_refused() {
    let (mut fa, _) = lease_fixture();
    let baseline = capacity(&fa);
    let lease = fa.allocate_owned().unwrap();
    let duplicate = lease.duplicate_for_test();
    let addr = lease.frame_addr();
    assert!(fa.release_frame(lease));
    assert!(
        !fa.release_frame(duplicate),
        "BLOCKER: release succeeded twice"
    );
    assert!(fa.is_free(addr));
    assert_eq!(capacity(&fa), baseline);
}

#[test]
fn generation_safe_lease_transfer_then_release() {
    let (mut fa, _) = lease_fixture();
    let baseline = capacity(&fa);
    let lease = fa.allocate_owned().unwrap();
    let addr = lease.frame_addr();
    assert!(fa.release_frame(transfer_lease(lease)));
    assert!(fa.is_free(addr));
    assert_eq!(capacity(&fa), baseline);
}

#[test]
fn generation_safe_foreign_domain_lease_is_refused() {
    let (mut fa, _) = lease_fixture();
    let mut foreign = FrameAllocator::new();
    assert!(foreign.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    let lease = fa.allocate_owned().unwrap();
    let addr = lease.frame_addr();
    let before = capacity(&fa);
    let foreign_before = capacity(&foreign);
    assert!(!foreign.release_frame(lease.duplicate_for_test()));
    assert_eq!(capacity(&fa), before);
    assert_eq!(capacity(&foreign), foreign_before);
    assert!(!fa.is_free(addr));
    assert!(fa.release_frame(lease));
    assert!(fa.is_free(addr));
}

#[test]
fn generation_safe_mapped_lease_release_is_refused_until_unmapped() {
    let (mut fa, mut pm) = lease_fixture();
    let lease = fa.allocate_owned().unwrap();
    let addr = lease.frame_addr();
    let slot = GROWTH_START as u64;
    assert!(pm.map(&mut fa, slot, addr, &KERNEL_PERMS));
    let before = capacity(&fa);
    assert!(!fa.release_frame(lease.duplicate_for_test()));
    assert_eq!(capacity(&fa), before);
    assert!(pm.is_mapped(slot));
    assert!(!fa.is_free(addr));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.release_frame(lease));
    assert!(!pm.is_mapped(slot));
    assert!(fa.is_free(addr));
}

#[test]
fn generation_safe_rejected_map_preserves_lease() {
    let (mut fa, mut pm) = lease_fixture();
    let slot = GROWTH_START as u64;
    let first = fa.allocate_owned().unwrap();
    let second = fa.allocate_owned().unwrap();
    assert!(pm.map(&mut fa, slot, first.frame_addr(), &KERNEL_PERMS));
    let before = capacity(&fa);
    assert!(!pm.map(&mut fa, slot, second.frame_addr(), &KERNEL_PERMS));
    assert_eq!(capacity(&fa), before);
    assert_eq!(pm.stats().map_rejects, 1);
    assert!(!fa.is_free(second.frame_addr()));
    let second_addr = second.frame_addr();
    assert!(fa.release_frame(second));
    assert!(fa.is_free(second_addr));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.release_frame(first));
}

#[test]
fn generation_safe_repeated_allocate_release_cycles_keep_state() {
    let (mut fa, _) = lease_fixture();
    let baseline = capacity(&fa);
    for _ in 0..8 {
        let lease = fa.allocate_owned().unwrap();
        let stale = lease.duplicate_for_test();
        let addr = lease.frame_addr();
        assert!(fa.release_frame(lease));
        let current = fa.allocate_owned().unwrap();
        assert_eq!(current.frame_addr(), addr);
        let before = capacity(&fa);
        assert!(!fa.release_frame(stale));
        assert_eq!(capacity(&fa), before);
        assert!(!fa.is_free(addr));
        assert!(fa.release_frame(current));
        assert_eq!(capacity(&fa), baseline);
    }
}

#[test]
fn generation_safe_reset_with_live_lease_is_refused() {
    let (mut fa, _) = lease_fixture();
    let lease = fa.allocate_owned().unwrap();
    let addr = lease.frame_addr();
    let before = capacity(&fa);
    assert!(!fa.init(&entries(), 0x90000, 0xa0000, 0xb0000));
    assert_eq!(capacity(&fa), before);
    assert!(!fa.is_free(addr));
    assert!(fa.release_frame(lease));
    assert!(fa.is_free(addr));
}
