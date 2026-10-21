use super::*;
use crate::multiboot::MmapEntry;

fn fixture() -> (
    FrameAllocator,
    PageMap,
    [Option<frame::FrameLease>; 4],
    [Option<frame::FrameLease>; 4],
) {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
        &[
            MmapEntry {
                size: 20,
                base_addr: 0x10000,
                length: 0x70000,
                type_: 1
            },
            MmapEntry {
                size: 20,
                base_addr: TRANSITION_GUARD as u64,
                length: 0x400000,
                type_: 1
            },
        ],
        0x90000,
        0xa0000,
        0xb0000
    ));
    let mut pm = build_identity_map(&mut fa, 0x8000000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    assert!(enable_paging(&mut pm));
    let mut transition = [const { None }; 4];
    let mut emergency = [const { None }; 4];
    for slot in transition.iter_mut().chain(emergency.iter_mut()) {
        *slot = fa.allocate_owned();
        assert!(slot.is_some());
    }
    (fa, pm, transition, emergency)
}

#[test]
fn f3_descriptor_wire_bytes_preserve_kernel_selectors() {
    assert_eq!(
        KERNEL_CODE.to_le_bytes(),
        [0xff, 0xff, 0, 0, 0, 0x99, 0xcf, 0]
    );
    assert_eq!(
        KERNEL_DATA.to_le_bytes(),
        [0xff, 0xff, 0, 0, 0, 0x93, 0xcf, 0]
    );
    for base in [0, 0x12345678, 0xfedcba98, u32::MAX] {
        for access in [0x89, 0x8b] {
            let bytes = descriptor(base, access).to_le_bytes();
            assert_eq!(
                u32::from_le_bytes([bytes[2], bytes[3], bytes[4], bytes[7]]),
                base
            );
            assert_eq!(&bytes[0..2], &[103, 0]);
            assert_eq!(bytes[5], access);
            assert_eq!(bytes[6], 0);
        }
    }
}

#[test]
fn f3_tss_layout_and_absent_io_bitmap() {
    assert_eq!(core::mem::size_of::<Tss>(), 104);
    assert_eq!(core::mem::align_of::<Tss>(), 4);
    assert_eq!(core::mem::offset_of!(Tss, esp0), 4);
    assert_eq!(core::mem::offset_of!(Tss, ss0), 8);
    assert_eq!(core::mem::offset_of!(Tss, cr3), 28);
    assert_eq!(core::mem::offset_of!(Tss, eip), 32);
    assert_eq!(core::mem::offset_of!(Tss, esp), 56);
    assert_eq!(core::mem::offset_of!(Tss, cs), 76);
    assert_eq!(core::mem::offset_of!(Tss, ss), 80);
    assert_eq!(core::mem::offset_of!(Tss, ldt), 96);
    assert_eq!(core::mem::offset_of!(Tss, trap), 100);
    assert_eq!(core::mem::offset_of!(Tss, iomap), 102);
    let tss = Tss::new();
    assert_eq!(tss.iomap, 104);
    assert_eq!(tss.trap, 0);
    assert_eq!(tss.backlink, 0);
    assert_eq!(tss.esp0, 0);
    assert!(u32::from(tss.iomap) > 103);
    assert_eq!(TRANSITION_TOP - TRANSITION_BASE, 4 * PAGE_SIZE as u32);
    assert_eq!(EMERGENCY_TOP - EMERGENCY_BASE, 4 * PAGE_SIZE as u32);
    assert_eq!(TRANSITION_BASE - TRANSITION_GUARD, PAGE_SIZE as u32);
    assert_eq!(EMERGENCY_BASE - EMERGENCY_GUARD, PAGE_SIZE as u32);
    assert_eq!(page_dir_index(TRANSITION_GUARD as u64), 31);
    assert_eq!(page_dir_index((EMERGENCY_TOP - 1) as u64), 31);
    assert_eq!(TRANSITION_TOP & 15, 0);
    assert_eq!(EMERGENCY_TOP & 15, 0);
    assert_eq!(1 + 1 + 1 + 4 + 4 + 1, 12);
}

#[test]
fn f3_eight_owned_pages_two_absent_guards_and_no_new_table() {
    let (mut fa, mut pm, transition, emergency) = fixture();
    let frames = fa.stats().allocated_frames;
    let tables = pm.stats.page_tables;
    let mapped = pm.stats.mapped_frames;
    assert!(pm.install_privileged_stacks(&mut fa, &transition, &emergency));
    assert!(pm.privileged_stacks_valid(&fa, &transition, &emergency));
    assert_eq!(fa.stats().allocated_frames, frames);
    assert_eq!(pm.stats.page_tables, tables);
    assert_eq!(pm.stats.mapped_frames, mapped - 2);
    assert!(fa.is_free(TRANSITION_GUARD as u64));
    assert!(fa.is_free(EMERGENCY_GUARD as u64));
    for i in 0..10 {
        let va = TRANSITION_GUARD as u64 + (i * PAGE_SIZE) as u64;
        assert!(pm.privileged_slot(va));
        assert!(!pm.unmap(&mut fa, va));
    }
    assert!(!pm.install_privileged_stacks(&mut fa, &transition, &emergency));
    assert!(pm.privileged_stacks_valid(&fa, &transition, &emergency));
    let other = fa.allocate_owned().unwrap();
    assert!(!pm.map_owned(&mut fa, TRANSITION_GUARD as u64, &other, &KERNEL_PERMS));
    assert!(!pm.map_owned(&mut fa, TRANSITION_BASE as u64, &other, &KERNEL_PERMS));
    for lease in transition.iter().chain(emergency.iter()).flatten() {
        assert!(fa.owns_live_lease(lease));
        assert!(fa.runtime_pinned(lease.frame_addr()));
        assert!(!fa.free(lease.frame_addr()));
    }
}

#[test]
fn f3_conflict_and_missing_lease_refuse_before_any_pte_write() {
    let (mut fa, mut pm, mut transition, emergency) = fixture();
    let base = pm.tables[31];
    let original = (0..10)
        .map(|i| read_entry(base, page_table_index(TRANSITION_GUARD as u64) + i))
        .collect::<Vec<_>>();
    let lost = transition[3].take();
    let before = fa.stats().allocated_frames;
    assert!(!pm.install_privileged_stacks(&mut fa, &transition, &emergency));
    assert!(!pm.privileged_reserved);
    assert_eq!(
        (0..10)
            .map(|i| read_entry(base, page_table_index(TRANSITION_GUARD as u64) + i))
            .collect::<Vec<_>>(),
        original
    );
    transition[3] = lost;
    write_entry(
        base,
        page_table_index(TRANSITION_GUARD as u64),
        ENTRY_PRESENT | ENTRY_USER,
    );
    assert!(!pm.install_privileged_stacks(&mut fa, &transition, &emergency));
    assert!(!pm.privileged_reserved);
    assert_eq!(fa.stats().allocated_frames, before);
    for lease in transition.iter().chain(emergency.iter()).flatten() {
        assert!(!fa.runtime_pinned(lease.frame_addr()));
    }
}

#[test]
fn f3_old_guard_physical_candidate_refused_before_table_write() {
    let (mut fa, mut pm, transition, emergency) = fixture();
    assert!(pm.install_privileged_stacks(&mut fa, &transition, &emergency));
    // Remove a completely empty growth table in this host-only model so the
    // real runtime constructor must inspect its next physical candidate.
    let dir = page_dir_index(GROWTH_START as u64);
    let old = pm.tables[dir];
    assert!((0..PAGE_TABLE_ENTRIES).all(|i| read_entry(old, i) == 0));
    pm.tables[dir] = 0;
    write_entry(pm.directory, dir, 0);
    pm.stats.page_tables -= 1;
    assert!(fa.set_structure_pin(old, false));
    assert!(fa.free(old));
    // Exhaust only the bounded pre-guard first-fit prefix, retaining legitimate
    // leases outside memory-owner locks in this host-only oracle.
    let mut prefix = Vec::new();
    while fa.is_free(TRANSITION_GUARD as u64) {
        let lease = fa.allocate_owned().unwrap();
        if lease.frame_addr() == TRANSITION_GUARD as u64 {
            assert!(fa.release_frame(lease));
            break;
        }
        prefix.push(lease);
    }
    assert_eq!(pm.translate(TRANSITION_GUARD as u64), None);
    let payload = &prefix[0];
    let slot = GROWTH_START as u64;
    let frames = fa.stats().allocated_frames;
    let tables = pm.stats.page_tables;
    assert!(!pm.map_owned(&mut fa, slot, payload, &KERNEL_PERMS));
    assert_eq!(fa.stats().allocated_frames, frames);
    assert_eq!(pm.stats.page_tables, tables);
    assert_eq!(pm.entry(slot), None);
    assert!(fa.is_free(TRANSITION_GUARD as u64));
    assert!(!fa.runtime_pinned(payload.frame_addr()));
}
