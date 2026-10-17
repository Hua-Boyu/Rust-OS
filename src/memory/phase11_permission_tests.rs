//! Host-only architectural oracle: the CPU intersects PDE and PTE rights.
//! These tests cannot establish real CPL3 execution or fault recovery.
use super::*;
use crate::multiboot::MmapEntry;

fn map_fixture() -> (FrameAllocator, PageMap) {
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
    (fa, pm)
}

#[test]
fn phase11_permissions_intersect_both_paging_levels() {
    let (_, pm) = map_fixture();
    let page = 0x20000;
    let dir = page_dir_index(page);
    let idx = page_table_index(page);
    let table = pm.tables[dir];
    // Independent enumeration of every P/RW/US combination at each level.
    // No production permission helper is used to compute the expected result.
    for parent in 0..8 {
        for leaf in 0..8 {
            write_entry(pm.directory, dir, table as u32 | parent);
            write_entry(table, idx, page as u32 | leaf);
            let actual = pm.permissions(page).unwrap();
            let present = parent % 2 == 1 && leaf % 2 == 1;
            let writable = present && parent / 2 % 2 == 1 && leaf / 2 % 2 == 1;
            let user = present && parent / 4 % 2 == 1 && leaf / 4 % 2 == 1;
            assert_eq!(actual.present, present, "parent={parent} leaf={leaf}");
            assert_eq!(actual.writable, writable, "parent={parent} leaf={leaf}");
            assert_eq!(actual.user, user, "parent={parent} leaf={leaf}");
            assert!(!actual.nx_supported);
            assert_eq!(pm.is_mapped(page), present);
            assert_eq!(pm.translate(page), if present { Some(page) } else { None });
        }
    }
}

#[test]
fn phase11_unowned_user_map_is_rejected_before_table_allocation() {
    let (mut fa, mut pm) = map_fixture();
    let before_free = fa.stats().free_frames;
    let before_tables = pm.stats().page_tables;
    let before_mapped = pm.stats().mapped_frames;
    let before_maps = pm.stats().maps;
    let before_tlb = pm.stats().tlb_invalidation;
    let slot = GROWTH_START as u64; // fixture has no table in this PDE
    let request = PagePerms {
        user: true,
        ..KERNEL_PERMS
    };
    assert!(!pm.map(&mut fa, slot, 0x70000, &request));
    assert_eq!(fa.stats().free_frames, before_free);
    assert_eq!(pm.stats().page_tables, before_tables);
    assert_eq!(pm.stats().mapped_frames, before_mapped);
    assert_eq!(pm.stats().maps, before_maps);
    assert_eq!(pm.stats().tlb_invalidation, before_tlb);
    assert_eq!(pm.stats().map_rejects, 1);
    assert_eq!(pm.entry(slot), None);
    assert_eq!(read_entry(pm.directory, page_dir_index(slot)), 0);
}

#[test]
fn phase11_nonpresent_map_is_rejected_without_side_effects() {
    let (mut fa, mut pm) = map_fixture();
    let before_free = fa.stats().free_frames;
    let before_tables = pm.stats().page_tables;
    let before_mapped = pm.stats().mapped_frames;
    let slot = GROWTH_START as u64;
    let request = PagePerms {
        present: false,
        ..KERNEL_PERMS
    };
    assert!(!pm.map(&mut fa, slot, 0x70000, &request));
    assert_eq!(fa.stats().free_frames, before_free);
    assert_eq!(pm.stats().page_tables, before_tables);
    assert_eq!(pm.stats().mapped_frames, before_mapped);
    assert_eq!(pm.stats().maps, 0);
    assert_eq!(pm.stats().tlb_invalidation, 0);
    assert_eq!(pm.stats().map_rejects, 1);
    assert_eq!(pm.entry(slot), None);
    assert_eq!(read_entry(pm.directory, page_dir_index(slot)), 0);
}

#[test]
fn phase11_identity_maps_remain_supervisor_at_128_and_512_mib() {
    for mib in [128u64, 512] {
        let mut fa = FrameAllocator::new();
        fa.init(
            &[MmapEntry {
                size: 20,
                base_addr: 0x10000,
                length: 0x900000,
                type_: 1,
            }],
            0x400000,
            0x500000,
            0x600000,
        );
        let end = mib * 1024 * 1024;
        let mut pm = build_identity_map(&mut fa, end, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
        for page in (0..end).step_by(PAGE_SIZE) {
            let p = pm.permissions(page).unwrap();
            assert!(!p.user, "user identity page at {page:#x}, {mib} MiB");
            assert_eq!(pm.entry(page).unwrap() & ENTRY_USER, 0);
            assert_eq!(
                read_entry(pm.directory, page_dir_index(page)) & ENTRY_USER,
                0
            );
            assert_eq!(p.present, page != 0 && !in_growth_window(page));
            assert_eq!(p.writable, p.present);
            assert!(!p.nx_supported);
        }
        // Supervisor-only aliases and growth must stay denied to user.
        assert_eq!(
            fa.claim_growth_frame(GROWTH_START as u64),
            Some(GROWTH_START as u64)
        );
        assert!(pm.map(
            &mut fa,
            GROWTH_START as u64,
            GROWTH_START as u64,
            &KERNEL_PERMS
        ));
        assert!(!pm.permissions(GROWTH_START as u64).unwrap().user);
        assert!(pm.permissions(end).is_none());
        assert!(pm.permissions(1u64 << 32).is_none());
    }
}

#[test]
fn phase11_rejected_requests_preserve_existing_table_and_mapping() {
    let (mut fa, mut pm) = map_fixture();
    let page = 0x20000;
    let before_entry = pm.entry(page);
    let before_directory = read_entry(pm.directory, page_dir_index(page));
    let before_free = fa.stats().free_frames;
    let before_mapped = pm.stats().mapped_frames;
    for request in [
        PagePerms {
            user: true,
            ..KERNEL_PERMS
        },
        PagePerms {
            present: false,
            ..KERNEL_PERMS
        },
    ] {
        assert!(!pm.map(&mut fa, page, 0x70000, &request));
        assert_eq!(pm.entry(page), before_entry);
        assert_eq!(
            read_entry(pm.directory, page_dir_index(page)),
            before_directory
        );
        assert_eq!(fa.stats().free_frames, before_free);
        assert_eq!(pm.stats().mapped_frames, before_mapped);
        assert_eq!(pm.stats().maps, 0);
        assert_eq!(pm.stats().tlb_invalidation, 0);
    }
    assert_eq!(pm.stats().map_rejects, 2);
}
