//! Runtime table accessibility is distinct from B19 ownership authority.
//! These host checks validate the gate before a physical write, not CPU faults.
use super::*;
use crate::multiboot::MmapEntry;

fn fixture() -> (FrameAllocator, PageMap, u64, u64) {
    let mut fa = FrameAllocator::new();
    fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x70000,
            type_: 1,
        }],
        0x90000,
        0xa0000,
        0xb0000,
    );
    let pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let payload = fa.allocate().unwrap();
    let candidate = fa.allocate().unwrap();
    assert!(fa.free(candidate));
    (fa, pm, payload, candidate)
}

fn assert_refused(fa: &mut FrameAllocator, pm: &mut PageMap, payload: u64, candidate: u64) {
    let before = *fa.stats();
    let before_tables = pm.stats().page_tables;
    let before_mapped = pm.stats().mapped_frames;
    let before_tlb = pm.stats().tlb_invalidation;
    let before_maps = pm.stats().maps;
    let before_rejects = pm.stats().map_rejects;
    let slot = GROWTH_START as u64;
    // A host mirror would otherwise conceal the missing physical write alias.
    MIRROR.with(|m| {
        m.borrow_mut().remove(&candidate);
    });
    for rejects in 1..=2 {
        assert!(!pm.map(fa, slot, payload, &KERNEL_PERMS));
        assert_eq!(fa.stats().free_frames, before.free_frames);
        assert_eq!(fa.stats().allocated_frames, before.allocated_frames);
        assert_eq!(fa.stats().reserved_frames, before.reserved_frames);
        assert_eq!(fa.stats().invalid_frees, before.invalid_frees);
        assert_eq!(fa.stats().double_frees, before.double_frees);
        assert_eq!(pm.stats().page_tables, before_tables);
        assert_eq!(pm.stats().mapped_frames, before_mapped);
        assert_eq!(pm.stats().tlb_invalidation, before_tlb);
        assert_eq!(pm.stats().map_rejects, before_rejects + rejects);
        assert_eq!(pm.stats().maps, before_maps);
        assert_eq!(pm.entry(slot), None);
        assert_eq!(read_entry(pm.directory, page_dir_index(slot)), 0);
        assert!(!payload_bit(&pm.payload_bitmap, payload));
        assert!(!fa.runtime_pinned(payload));
        assert!(!fa.is_free(payload));
        MIRROR.with(|m| assert!(!m.borrow().contains_key(&candidate)));
    }
    assert_eq!(fa.allocate(), Some(candidate));
    assert!(fa.free(candidate));
}

#[test]
fn runtime_table_removed_identity_alias_is_rejected_without_writes() {
    let (mut fa, mut pm, payload, candidate) = fixture();
    assert!(pm.unmap(&mut fa, candidate));
    assert_refused(&mut fa, &mut pm, payload, candidate);
    assert!(fa.free(payload));
}

#[test]
fn runtime_table_nonidentity_alias_is_rejected_without_writes() {
    let (mut fa, mut pm, payload, candidate) = fixture();
    let base = pm.tables[page_dir_index(candidate)];
    write_entry(base, page_table_index(candidate), entry_value(payload));
    assert_eq!(pm.translate(candidate), Some(payload));
    assert_refused(&mut fa, &mut pm, payload, candidate);
    assert_eq!(pm.translate(candidate), Some(payload));
}

#[test]
fn runtime_table_readonly_alias_at_either_level_is_rejected_without_writes() {
    for directory_level in [false, true] {
        let (mut fa, mut pm, payload, candidate) = fixture();
        let (base, index) = if directory_level {
            (pm.directory, page_dir_index(candidate))
        } else {
            (
                pm.tables[page_dir_index(candidate)],
                page_table_index(candidate),
            )
        };
        let original = read_entry(base, index);
        write_entry(base, index, original & !ENTRY_WRITABLE);
        assert_eq!(pm.translate(candidate), Some(candidate));
        assert!(!pm.permissions(candidate).unwrap().writable);
        assert_refused(&mut fa, &mut pm, payload, candidate);
        assert_eq!(read_entry(base, index), original & !ENTRY_WRITABLE);
    }
}

#[test]
fn runtime_table_user_accessible_alias_is_rejected_without_writes() {
    let (mut fa, mut pm, payload, candidate) = fixture();
    let dir = page_dir_index(candidate);
    let base = pm.tables[dir];
    write_entry(
        base,
        page_table_index(candidate),
        entry_value(candidate) | ENTRY_USER,
    );
    let directory_entry = read_entry(pm.directory, dir);
    write_entry(pm.directory, dir, directory_entry | ENTRY_USER);
    assert!(pm.permissions(candidate).unwrap().user);
    assert_refused(&mut fa, &mut pm, payload, candidate);
}

#[test]
fn runtime_table_restored_identity_alias_allows_retry() {
    let (mut fa, mut pm, payload, candidate) = fixture();
    let base = pm.tables[page_dir_index(candidate)];
    let index = page_table_index(candidate);
    let original = read_entry(base, index);
    assert!(pm.unmap(&mut fa, candidate));
    assert_refused(&mut fa, &mut pm, payload, candidate);
    // Test-only restoration of the exact prior boot PTE, not a production bypass.
    write_entry(base, index, original);
    let slot = GROWTH_START as u64;
    assert!(pm.map(&mut fa, slot, payload, &KERNEL_PERMS));
    assert_eq!(pm.tables[page_dir_index(slot)], candidate);
    assert_eq!(pm.translate(slot), Some(payload));
    assert!(
        !pm.unmap(&mut fa, candidate),
        "live table alias remains protected"
    );
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.free(payload));
}
