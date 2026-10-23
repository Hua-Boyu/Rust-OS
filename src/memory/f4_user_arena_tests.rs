//! F4 contract against real leases, retained ownership and page-table mirrors.
//! Every mutating case starts in a fresh exact-one libtest process; no reset.
use super::retained_owner::{
    CpuState, MODEL_CPU, OWNER, PREPARING, RetainedOwner, SEALED, STATE, TERMINAL, capacity,
    prepare_arena_locked, prepare_f3_locked, prepare_f4_locked, try_admit,
};
use super::user_arena::{self as arena, LAYOUT, Layout};
use super::*;
use crate::multiboot::MmapEntry;
use core::sync::atomic::Ordering;

pub(super) fn isolated(identity: &str, cases: usize) -> Option<usize> {
    if std::env::var("ROSTI_F4_CHILD").ok().as_deref() == Some(identity) {
        let case: usize = std::env::var("ROSTI_F4_CASE").unwrap().parse().unwrap();
        assert!(case < cases);
        return Some(case);
    }
    for case in 0..cases {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([identity, "--exact", "--test-threads=1", "--nocapture"])
            .env("ROSTI_F4_CHILD", identity)
            .env("ROSTI_F4_CASE", case.to_string())
            .output()
            .unwrap();
        let text = format!(
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(output.status.success(), "{identity} case {case}: {text}");
        assert!(
            text.contains("test result: ok. 1 passed; 0 failed; 0 ignored;"),
            "{identity} case {case}: {text}"
        );
    }
    None
}

fn child(name: &str, cases: usize) -> Option<usize> {
    let prefix = module_path!().split_once("::").unwrap().1;
    isolated(&format!("{prefix}::{name}"), cases)
}

pub(super) fn allocator() -> FrameAllocator {
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
                base_addr: privileged::TRANSITION_GUARD as u64,
                length: 0x400000,
                type_: 1
            },
        ],
        0x90000,
        0xa0000,
        0xb0000
    ));
    fa
}

pub(super) fn fixture() -> (FrameAllocator, PageMap) {
    let mut fa = allocator();
    let mut pm = build_identity_map(&mut fa, 0x8000000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    assert!(enable_paging(&mut pm));
    *MODEL_CPU.lock() = CpuState {
        cr0: 0x80010011,
        cr3: pm.directory as u32,
        cr4: 0,
        cs: 8,
    };
    (fa, pm)
}

fn full_owner(owner: &mut RetainedOwner, pm: &mut PageMap, fa: &mut FrameAllocator) {
    assert!(try_admit());
    assert!(prepare_f3_locked(owner, pm, fa));
    owner.user_stack = Some(fa.allocate_owned().unwrap());
    owner.arena_table = Some(fa.allocate_owned().unwrap());
    owner.capture[1] += 2;
    assert_eq!(owner.capture[1], 12);
    assert!(arena::preflight_map(pm, fa, LAYOUT));
}

fn leases(owner: &RetainedOwner) -> impl Iterator<Item = &frame::FrameLease> {
    core::iter::once(&owner.payload)
        .chain(core::iter::once(&owner.sentinel))
        .chain(owner.transition.iter())
        .chain(owner.emergency.iter())
        .chain(core::iter::once(&owner.user_stack))
        .chain(core::iter::once(&owner.arena_table))
        .flatten()
}

// Full allocator ledger/bitmaps/diagnostics plus every mirror word and all
// PageMap metadata, including vector backing capacities. Never used under WATCH.
pub(super) fn snapshot(fa: &FrameAllocator, pm: &PageMap) -> (Vec<u64>, Vec<u64>) {
    let mut pages = alloc::vec![
        pm.directory,
        pm.domain as u64,
        pm.retained as u64,
        pm.window_end,
        pm.privileged_reserved as u64,
        pm.user_arena_reserved as u64,
        pm.stats.page_tables as u64,
        pm.stats.mapped_frames as u64,
        pm.stats.enabled as u64,
        pm.stats.maps as u64,
        pm.stats.map_rejects as u64,
        pm.stats.unmaps as u64,
        pm.stats.unmap_rejects as u64,
        pm.stats.tlb_invalidation as u64,
        pm.tables.len() as u64,
        pm.tables.capacity() as u64,
        pm.payload_bitmap.len() as u64,
        pm.payload_bitmap.capacity() as u64,
        pm.boot_pins.len() as u64,
        pm.boot_pins.capacity() as u64
    ];
    pages.extend(pm.tables.iter().copied());
    pages.extend(pm.payload_bitmap.iter().map(|&v| v as u64));
    for &(a, b) in &pm.boot_pins {
        pages.extend([a, b]);
    }
    MIRROR.with(|m| {
        let mirror = m.borrow();
        pages.push(mirror.len() as u64);
        for (&address, words) in mirror.iter() {
            pages.extend([address, words.len() as u64, words.capacity() as u64]);
            pages.extend(words.iter().map(|&v| v as u64));
        }
    });
    (fa.exact_state_for_retained_test(), pages)
}

fn owner_snapshot(owner: &RetainedOwner, fa: &FrameAllocator) -> Vec<u64> {
    let mut out = alloc::vec![STATE.load(Ordering::Acquire) as u64];
    for slot in core::iter::once(&owner.payload)
        .chain(core::iter::once(&owner.sentinel))
        .chain(owner.transition.iter())
        .chain(owner.emergency.iter())
        .chain(core::iter::once(&owner.user_stack))
        .chain(core::iter::once(&owner.arena_table))
    {
        out.push(slot.as_ref().map_or(0, |l| l.frame_addr()));
        out.push(slot.as_ref().is_some_and(|l| fa.owns_live_lease(l)) as u64);
    }
    out.extend(owner.capture.iter().map(|&v| v as u64));
    out.extend(owner.arena_capture.iter().map(|&v| v as u64));
    out.extend(owner.future_ranges.iter().flatten().map(|&v| v as u64));
    out
}

fn refuses(pm: &mut PageMap, fa: &mut FrameAllocator, owner: &RetainedOwner, layout: Layout) {
    let before = snapshot(fa, pm);
    let retained = owner_snapshot(owner, fa);
    assert!(!arena::install(pm, fa, owner, layout));
    assert_eq!(snapshot(fa, pm), before);
    assert_eq!(owner_snapshot(owner, fa), retained);
}

#[test]
fn layout_preserves_fixed_ceiling() {
    assert!(LAYOUT.valid());
    assert_eq!(
        (arena::START, arena::END, arena::GUARD, arena::STACK),
        (0x40000000, 0x40400000, 0x403fe000, 0x403ff000)
    );
    assert_eq!(arena::END - arena::START, 1024 * PAGE_SIZE as u64);
    assert_eq!(arena::STACK + PAGE_SIZE as u64, arena::END);
    assert_eq!(arena::GUARD + PAGE_SIZE as u64, arena::STACK);
    assert_eq!(12 * PAGE_SIZE, 49152);
    assert_eq!(2 * PAGE_SIZE, 8192);
    assert!(core::mem::size_of::<RetainedOwner>() < 4096);
    assert_eq!(arena::PREFIX, [0x0f, 0x0b, 0xeb, 0xfc]);
    assert_eq!(arena::DATA, b"F4-RO-DATA\0");
}

#[test]
fn publishes_exact_two_owned_user_leaves() {
    if child("publishes_exact_two_owned_user_leaves", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let before = capacity(&fa);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(prepare_f4_locked(&mut owner, &mut pm, &mut fa));
    assert_eq!(STATE.load(Ordering::Acquire), PREPARING);
    assert_eq!(capacity(&fa), [before[0] - 12, before[1] + 12, before[2]]);
    assert_eq!(leases(&owner).count(), 12);
    let mut addresses: Vec<_> = leases(&owner)
        .map(|l| {
            assert!(fa.owns_live_lease(l));
            l.frame_addr()
        })
        .collect();
    addresses.sort_unstable();
    addresses.dedup();
    assert_eq!(addresses.len(), 12);
    assert!(arena::valid(&pm, &fa, &owner));
    let code = owner.payload.as_ref().unwrap().frame_addr();
    let stack = owner.user_stack.as_ref().unwrap().frame_addr();
    let table = owner.arena_table.as_ref().unwrap().frame_addr();
    assert_eq!(read_entry(pm.directory, 256), table as u32 | 7);
    assert_eq!(
        read_entry(table, 0),
        code as u32 | 5 | ENTRY_RUNTIME_PAYLOAD
    );
    assert_eq!(
        read_entry(table, 1023),
        stack as u32 | 7 | ENTRY_RUNTIME_PAYLOAD
    );
    let mut users = Vec::new();
    for dir in 0..1024 {
        let raw = read_entry(pm.directory, dir);
        if dir != 256 {
            assert_eq!(raw & ENTRY_USER, 0);
        }
        let t = pm.tables[dir];
        if t == 0 {
            continue;
        }
        for i in 0..1024 {
            let leaf = read_entry(t, i);
            if leaf & ENTRY_USER != 0 {
                users.push((dir, i));
            }
        }
    }
    assert_eq!(users, [(256, 0), (256, 1023)]);
    assert!(fa.structure_pinned(table) && !fa.runtime_pinned(table));
    assert!(fa.runtime_pinned(code) && fa.runtime_pinned(stack));
    assert!(payload_bit(&pm.payload_bitmap, code) && payload_bit(&pm.payload_bitmap, stack));
    assert!(!fa.runtime_pinned(owner.sentinel.as_ref().unwrap().frame_addr()));
}

#[test]
fn refuses_foreign_and_stale_leases() {
    if child("refuses_foreign_and_stale_leases", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    // Keep a second ~320 KiB allocator and its debug construction temporaries
    // off this libtest thread's stack. This is host fixture storage only, not
    // a larger kernel stack/resource ceiling or a forged ownership token.
    let mut foreign = std::thread::spawn(|| Box::new(allocator())).join().unwrap();
    assert_ne!(foreign.domain(), fa.domain());
    let foreign_lease = foreign.allocate_owned().unwrap();
    let legitimate = owner.user_stack.replace(foreign_lease).unwrap();
    assert!(!arena::new_frame(
        &pm,
        &fa,
        owner.user_stack.as_ref().unwrap()
    ));
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    let foreign_lease = owner.user_stack.replace(legitimate).unwrap();
    assert!(foreign.release_frame(foreign_lease));
    let stale = owner.user_stack.take().unwrap();
    assert!(fa.release_frame(stale.duplicate_for_test()));
    let current = fa.allocate_owned().unwrap();
    assert_eq!(current.frame_addr(), stale.frame_addr());
    assert!(fa.owns_live_lease(&current));
    assert!(!fa.owns_live_lease(&stale));
    owner.user_stack = Some(stale);
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    owner.user_stack = Some(current);
    assert!(arena::new_frame(
        &pm,
        &fa,
        owner.user_stack.as_ref().unwrap()
    ));
}

#[test]
fn refuses_reserved_structure_and_duplicate_frames() {
    if child("refuses_reserved_structure_and_duplicate_frames", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    let code = owner.payload.as_ref().unwrap().frame_addr();
    pm.boot_pins.push((code, code + PAGE_SIZE as u64));
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    pm.boot_pins.pop();
    for structure in [true, false] {
        if structure {
            assert!(fa.set_structure_pin(code, true));
        } else {
            assert!(fa.set_runtime_pin(code, true));
        }
        refuses(&mut pm, &mut fa, &owner, LAYOUT);
        if structure {
            assert!(fa.set_structure_pin(code, false));
        } else {
            assert!(fa.set_runtime_pin(code, false));
        }
    }
    payload_set_bit(&mut pm.payload_bitmap, code, true);
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    payload_set_bit(&mut pm.payload_bitmap, code, false);
    let duplicate = owner.payload.as_ref().unwrap().duplicate_for_test();
    let saved = owner.user_stack.replace(duplicate).unwrap();
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    owner.user_stack = Some(saved);
    let duplicate = owner.user_stack.as_ref().unwrap().duplicate_for_test();
    let saved = owner.arena_table.replace(duplicate).unwrap();
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    owner.arena_table = Some(saved);
}

#[test]
fn refuses_occupied_directory_without_promotion() {
    if child("refuses_occupied_directory_without_promotion", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    for dir in [256, 257] {
        for raw in [
            ENTRY_PRESENT,
            pm.tables[0] as u32 | 3,
            pm.tables[0] as u32 | 7,
        ] {
            write_entry(pm.directory, dir, raw);
            refuses(&mut pm, &mut fa, &owner, LAYOUT);
            assert_eq!(read_entry(pm.directory, dir), raw);
            write_entry(pm.directory, dir, 0);
        }
        pm.tables[dir] = pm.tables[0];
        refuses(&mut pm, &mut fa, &owner, LAYOUT);
        pm.tables[dir] = 0;
    }
}

#[test]
fn refuses_unaligned_outside_and_overflow_ranges() {
    if child("refuses_unaligned_outside_and_overflow_ranges", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    for field in 0..4 {
        for value in [
            0,
            1,
            arena::START - 4096,
            arena::END + 4096,
            1u64 << 32,
            u64::MAX,
            u64::MAX - 4095,
        ] {
            let mut layout = LAYOUT;
            match field {
                0 => layout.start = value,
                1 => layout.end = value,
                2 => layout.guard = value,
                _ => layout.stack = value,
            }
            assert!(!layout.valid());
            refuses(&mut pm, &mut fa, &owner, layout);
        }
    }
}

#[test]
fn rejects_unexpected_user_supervisor_inventory() {
    if child("rejects_unexpected_user_supervisor_inventory", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    let original = read_entry(pm.directory, 0);
    for raw in [
        original | ENTRY_USER,
        original | (1 << 7),
        original & !ENTRY_WRITABLE,
        (pm.tables[1] as u32) | 3,
        0,
    ] {
        write_entry(pm.directory, 0, raw);
        refuses(&mut pm, &mut fa, &owner, LAYOUT);
    }
    write_entry(pm.directory, 0, original);
    let table = pm.tables[1];
    for index in [0, 1023] {
        let original = read_entry(table, index);
        for raw in [original | ENTRY_USER, ENTRY_USER] {
            write_entry(table, index, raw);
            refuses(&mut pm, &mut fa, &owner, LAYOUT);
        }
        write_entry(table, index, original);
    }
    let old_window = pm.window_end;
    pm.window_end = arena::START + 4096;
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    pm.window_end = old_window;
    let domain = pm.domain;
    pm.domain = domain.wrapping_add(1);
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    pm.domain = domain;
}

#[test]
fn refuses_inaccessible_table_and_payload_aliases() {
    if child("refuses_inaccessible_table_and_payload_aliases", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    for address in [
        owner.payload.as_ref().unwrap().frame_addr(),
        owner.user_stack.as_ref().unwrap().frame_addr(),
        owner.arena_table.as_ref().unwrap().frame_addr(),
        pm.directory,
        pm.tables[1],
    ] {
        let table = pm.tables[page_dir_index(address)];
        let index = page_table_index(address);
        let original = read_entry(table, index);
        for raw in [
            0,
            original & !ENTRY_WRITABLE,
            original | ENTRY_USER,
            ((address + 4096) as u32) | 3,
        ] {
            write_entry(table, index, raw);
            refuses(&mut pm, &mut fa, &owner, LAYOUT);
        }
        write_entry(table, index, original);
    }
}

#[test]
fn preserves_state_on_preflight_refusal() {
    if child("preserves_state_on_preflight_refusal", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    // All checked accounting additions are preflight, before byte/pin mutation.
    for field in 0..4 {
        let slot = match field {
            0 => &mut pm.stats.page_tables,
            1 => &mut pm.stats.mapped_frames,
            2 => &mut pm.stats.maps,
            _ => &mut pm.stats.tlb_invalidation,
        };
        let old = *slot;
        *slot = usize::MAX;
        refuses(&mut pm, &mut fa, &owner, LAYOUT);
        match field {
            0 => pm.stats.page_tables = old,
            1 => pm.stats.mapped_frames = old,
            2 => pm.stats.maps = old,
            _ => pm.stats.tlb_invalidation = old,
        }
    }
    pm.user_arena_reserved = true;
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    pm.user_arena_reserved = false;
    let absent = owner.arena_table.take();
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    owner.arena_table = absent;
    assert!(arena::install(&mut pm, &mut fa, &owner, LAYOUT));
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
}

#[test]
fn retains_bounded_prefix_on_acquisition_failure() {
    let Some(stage) = child("retains_bounded_prefix_on_acquisition_failure", 5) else {
        return;
    };
    let (mut fa, mut pm) = fixture();
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(prepare_f3_locked(&mut owner, &mut pm, &mut fa));
    // Stages: first stack denied, table denied, stack alias inaccessible,
    // table alias inaccessible, checked-accounting late prepublication refusal.
    let mut held = Vec::new();
    if stage <= 1 {
        while let Some(l) = fa.allocate_owned() {
            held.push(l);
        }
        if stage == 1 {
            assert!(fa.release_frame(held.remove(0)));
        }
    } else if stage <= 3 {
        let first = fa.allocate_owned().unwrap();
        let second = fa.allocate_owned().unwrap();
        let address = if stage == 2 {
            first.frame_addr()
        } else {
            second.frame_addr()
        };
        assert!(fa.release_frame(first));
        assert!(fa.release_frame(second));
        let table = pm.tables[page_dir_index(address)];
        write_entry(table, page_table_index(address), 0);
    } else {
        pm.stats.maps = usize::MAX;
    }
    let before = capacity(&fa);
    assert!(!prepare_arena_locked(&mut owner, &mut pm, &mut fa));
    let prefix = [10, 11, 11, 12, 12][stage];
    assert_eq!(owner.capture[1], prefix);
    assert_eq!(owner.capture[0], [13, 14, 19, 15, 15][stage]);
    assert_eq!(leases(&owner).count(), prefix as usize);
    assert_eq!(
        capacity(&fa),
        [
            before[0] - (prefix as usize - 10),
            before[1] + (prefix as usize - 10),
            before[2]
        ]
    );
    for lease in leases(&owner) {
        assert!(fa.owns_live_lease(lease));
    }
    assert_eq!(STATE.load(Ordering::Acquire), TERMINAL);
    assert_eq!(read_entry(pm.directory, 256), 0);
    assert_eq!(pm.tables[256], 0);
    assert!(!pm.user_arena_reserved);
    for dir in 0..1024 {
        assert_eq!(read_entry(pm.directory, dir) & ENTRY_USER, 0);
    }
    let before = snapshot(&fa, &pm);
    assert!(!try_admit());
    for lease in leases(&owner) {
        assert!(!fa.release_frame(lease.duplicate_for_test()));
    }
    assert!(fa.allocate_owned().is_none());
    assert!(!prepare_arena_locked(&mut owner, &mut pm, &mut fa));
    assert_eq!(snapshot(&fa, &pm), before);
    assert_eq!(owner.capture[1], prefix);
}

#[test]
fn seal_blocks_unmap_release_retry_and_cr3_switch() {
    if child("seal_blocks_unmap_release_retry_and_cr3_switch", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut alternate =
        build_identity_map(&mut fa, 0x8000000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(prepare_f4_locked(&mut owner, &mut pm, &mut fa));
    STATE.store(SEALED, Ordering::Release);
    let before = snapshot(&fa, &pm);
    let cpu = *MODEL_CPU.lock();
    for (address, lease) in [
        (arena::START, owner.payload.as_ref().unwrap()),
        (arena::STACK, owner.user_stack.as_ref().unwrap()),
    ] {
        assert!(!pm.unmap_owned(&mut fa, address, lease));
        assert!(!pm.unmap(&mut fa, address));
        assert!(!fa.release_frame(lease.duplicate_for_test()));
    }
    assert!(!fa.release_frame(owner.arena_table.as_ref().unwrap().duplicate_for_test()));
    assert!(!try_admit());
    assert!(!enable_paging(&mut alternate));
    assert!(!flush_tlb(&mut alternate));
    assert!(!flush_tlb(&mut pm));
    assert!(*MODEL_CPU.lock() == cpu);
    assert_eq!(snapshot(&fa, &pm), before);
    refuses(&mut pm, &mut fa, &owner, LAYOUT);
    assert!(arena::valid(&pm, &fa, &owner));
}

#[test]
fn effective_permissions_and_guards_match_contract() {
    if child("effective_permissions_and_guards_match_contract", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut owner = OWNER.lock();
    full_owner(&mut owner, &mut pm, &mut fa);
    let supervisor: Vec<_> = pm
        .tables
        .iter()
        .copied()
        .enumerate()
        .filter(|&(_, t)| t != 0)
        .map(|(dir, t)| {
            (
                dir,
                read_entry(pm.directory, dir),
                (0..1024).map(|i| read_entry(t, i)).collect::<Vec<_>>(),
            )
        })
        .collect();
    assert!(arena::install(&mut pm, &mut fa, &owner, LAYOUT));
    for (dir, pde, words) in supervisor {
        assert_eq!(read_entry(pm.directory, dir), pde);
        for (i, word) in words.into_iter().enumerate() {
            assert_eq!(read_entry(pm.tables[dir], i), word);
        }
    }
    for (address, writable) in [
        (arena::START, false),
        (arena::START + 2048, false),
        (arena::STACK, true),
    ] {
        let p = pm.permissions(address).unwrap();
        assert!(p.present && p.user);
        assert_eq!(p.writable, writable);
        assert!(!p.nx_supported);
    }
    for i in 1..1023 {
        assert_eq!(pm.entry(arena::START + i * 4096), Some(0));
    }
    for address in [
        arena::GUARD,
        arena::START + 4096,
        arena::END,
        privileged::TRANSITION_GUARD as u64,
        privileged::EMERGENCY_GUARD as u64,
    ] {
        assert!(!pm.is_mapped(address));
    }
    assert_eq!(read_entry(pm.directory, 257), 0);
    for lease in leases(&owner) {
        let p = pm.permissions(lease.frame_addr()).unwrap();
        assert!(p.present && p.writable && !p.user);
    }
    // Effective permission intersection is real, not a leaf-only oracle.
    let pde = read_entry(pm.directory, 256);
    for mask in [!ENTRY_USER, !ENTRY_WRITABLE, !ENTRY_PRESENT] {
        write_entry(pm.directory, 256, pde & mask);
        let p = pm.permissions(arena::STACK).unwrap();
        if mask == !ENTRY_USER {
            assert!(!p.user);
        }
        if mask == !ENTRY_WRITABLE {
            assert!(!p.writable);
        }
        if mask == !ENTRY_PRESENT {
            assert!(!p.present && !p.user && !p.writable);
        }
    }
    write_entry(pm.directory, 256, pde);
    assert!(arena::valid(&pm, &fa, &owner));
}
