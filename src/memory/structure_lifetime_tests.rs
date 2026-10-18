//! Unpublished cleanup must revoke its numeric structure authority.
use super::*;
use crate::multiboot::MmapEntry;

fn allocator() -> FrameAllocator {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x100000,
            type_: 1,
        }],
        0x200000,
        0x300000,
        0x310000,
    ));
    fa
}

fn build(fa: &mut FrameAllocator) -> PageMap {
    build_identity_map(fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap()
}

fn accounting(fa: &FrameAllocator) -> [usize; 6] {
    let s = fa.stats();
    [
        s.total_frames,
        s.free_frames,
        s.reserved_frames,
        s.allocated_frames,
        s.invalid_frees,
        s.double_frees,
    ]
}

#[test]
fn structure_cleanup_repeated_release_cannot_free_reused_map_backing() {
    let mut fa = allocator();
    let initial = accounting(&fa);
    let mut old = build(&mut fa);
    let old_directory = old.directory();
    old.release_unpublished_frames(&mut fa);
    assert_eq!(accounting(&fa), initial);
    for _ in 0..32 {
        let mut current = build(&mut fa);
        assert_eq!(
            current.directory(),
            old_directory,
            "exercise actual frame reuse"
        );
        let before = accounting(&fa);
        old.release_unpublished_frames(&mut fa);
        assert_eq!(
            accounting(&fa),
            before,
            "stale cleanup released another map's backing"
        );
        assert!(fa.structure_pinned(current.directory()));
        assert_eq!(current.translate(0x10000), Some(0x10000));
        current.release_unpublished_frames(&mut fa);
        assert_eq!(accounting(&fa), initial);
    }
}

#[test]
fn structure_cleanup_cpu_activated_map_cannot_release_structures() {
    let mut fa = allocator();
    let mut pm = build(&mut fa);
    enable_paging(&mut pm);
    let before = accounting(&fa);
    assert!(!pm.release_unpublished_frames(&mut fa));
    assert_eq!(accounting(&fa), before);
    assert!(fa.structure_pinned(pm.directory()));
    assert_eq!(pm.translate(0x10000), Some(0x10000));
}

#[test]
fn structure_cleanup_inconsistent_role_refuses_before_any_release() {
    for fault in 0..4 {
        let mut fa = allocator();
        let initial = accounting(&fa);
        let mut pm =
            build_identity_map(&mut fa, 0xc00000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
        let structures = [pm.directory(), pm.tables[0], pm.tables[1], pm.tables[2]];
        let target = match fault {
            0 => structures[0],
            1 => structures[1],
            _ => structures[3], // late failure after multiple valid candidates
        };
        if fault == 3 {
            fa.set_runtime_pin(target, true); // private role-conflict injection
        } else {
            fa.set_structure_pin(target, false); // private missing-role injection
        }
        let before = accounting(&fa);
        assert!(!pm.release_unpublished_frames(&mut fa));
        assert_eq!(accounting(&fa), before);
        for frame in structures {
            assert!(fa.is_live_allocation(frame));
            assert_eq!(fa.structure_pinned(frame), fault == 3 || frame != target);
        }
        assert_eq!(pm.translate(0x10000), Some(0x10000));
        fa.set_runtime_pin(target, false);
        fa.set_structure_pin(target, true);
        assert!(pm.release_unpublished_frames(&mut fa));
        assert_eq!(accounting(&fa), initial);
        for frame in structures {
            assert!(fa.is_free(frame));
            assert!(!fa.structure_pinned(frame));
            assert!(!fa.runtime_pinned(frame));
        }
    }
}

#[test]
fn structure_cleanup_publication_and_cr3_reload_retain_backing() {
    for reload in [false, true] {
        let mut fa = allocator();
        let mut pm = build(&mut fa);
        let before = accounting(&fa);
        if reload {
            assert!(flush_tlb(&mut pm));
        } else {
            assert!(pm.retain_for_publication());
            assert!(pm.retain_for_publication());
        }
        assert!(!pm.release_unpublished_frames(&mut fa));
        assert_eq!(accounting(&fa), before);
        assert!(fa.structure_pinned(pm.directory()));
        assert_eq!(pm.translate(0x10000), Some(0x10000));
    }
}

#[test]
fn structure_cleanup_released_map_cannot_observe_mutate_or_activate_reused_frames() {
    let mut fa = allocator();
    let initial = accounting(&fa);
    let mut old = build(&mut fa);
    let table_storage = (old.tables.as_ptr(), old.tables.capacity());
    let payload_storage = (old.payload_bitmap.as_ptr(), old.payload_bitmap.capacity());
    assert!(old.release_unpublished_frames(&mut fa));
    assert_eq!((old.tables.as_ptr(), old.tables.capacity()), table_storage);
    assert_eq!(
        (old.payload_bitmap.as_ptr(), old.payload_bitmap.capacity()),
        payload_storage
    );
    let mut current = build(&mut fa);
    let payload = fa.allocate().unwrap();
    let before = accounting(&fa);
    assert_eq!(old.directory(), 0);
    assert_eq!(old.translate(0x10000), None);
    assert!(old.permissions(0x10000).is_none());
    assert!(!old.pinned_identity_span(0x10000, 0x11000));
    assert!(!old.map(&mut fa, GROWTH_START as u64, payload, &KERNEL_PERMS));
    assert!(!old.unmap(&mut fa, 0x10000));
    assert!(!old.retain_for_publication());
    assert!(!enable_paging(&mut old));
    assert!(!flush_tlb(&mut old));
    assert!(!old.release_unpublished_frames(&mut fa));
    assert_eq!(accounting(&fa), before);
    assert_eq!(current.translate(0x10000), Some(0x10000));
    assert!(fa.free(payload));
    assert!(current.release_unpublished_frames(&mut fa));
    assert_eq!(accounting(&fa), initial);
}
