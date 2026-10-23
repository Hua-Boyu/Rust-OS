//! Independently rooted B26 F4 controls. Parent gates this whole module with
//! b26-observation. Existing detector allocation/destruction self-controls stay
//! unchanged; these observe the real transaction, with no layout exemptions.
use super::f4_user_arena_tests::{fixture, isolated, snapshot};
use super::retained_owner::{
    OWNER, STATE, TERMINAL, capacity, prepare_arena_locked, prepare_f3_locked, prepare_f4_locked,
    try_admit,
};
use super::user_arena::{self as arena};
use super::*;
use crate::{ALLOCS, BACKING_ONLY, DEALLOCS, TEST_LOCK, WATCH};
use core::sync::atomic::Ordering;

fn child(name: &str, cases: usize) -> Option<usize> {
    let prefix = module_path!().split_once("::").unwrap().1;
    isolated(&format!("{prefix}::{name}"), cases)
}

// Finite low candidate pool only. Never overwrite an existing directory/table
// mirror, even while observation is off; construction already filled those.
fn preseed() -> Vec<(u64, usize, usize)> {
    MIRROR.with(|m| {
        let mut mirror = m.borrow_mut();
        for address in (0x10000u64..0x80000).step_by(PAGE_SIZE) {
            mirror
                .entry(address)
                .or_insert_with(|| alloc::vec![0; PAGE_TABLE_ENTRIES]);
        }
        let mut backing: Vec<_> = mirror
            .iter()
            .map(|(&address, words)| (address, words.as_ptr() as usize, words.capacity()))
            .collect();
        backing.sort_unstable_by_key(|v| v.0);
        backing
    })
}

fn backing_unchanged(before: &[(u64, usize, usize)]) {
    MIRROR.with(|m| {
        let mirror = m.borrow();
        assert_eq!(mirror.len(), before.len());
        for &(address, pointer, capacity) in before {
            let words = mirror.get(&address).unwrap();
            assert_eq!(words.as_ptr() as usize, pointer);
            assert_eq!(words.capacity(), capacity);
            assert_eq!(words.len(), PAGE_TABLE_ENTRIES);
        }
    });
}

fn install_globals(fa: &mut FrameAllocator, pm: PageMap) {
    // Transfer fixture ownership before observation, without another large
    // by-value allocator argument/debug temporary on the libtest stack.
    // These are the actual owners consulted by the inherited detector.
    assert!(crate::memory::PAGE_MAP.lock().is_none());
    *crate::memory::PAGE_MAP.lock() = Some(pm);
    core::mem::swap(&mut *crate::memory::FRAME_ALLOC.lock(), fa);
}

fn begin() {
    BACKING_ONLY.store(false, Ordering::Relaxed);
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    WATCH.store(true, Ordering::Relaxed);
}

fn end() -> (usize, usize) {
    WATCH.store(false, Ordering::Relaxed);
    (
        ALLOCS.load(Ordering::Relaxed),
        DEALLOCS.load(Ordering::Relaxed),
    )
}

fn observed_success() {
    let _serial = TEST_LOCK.lock().unwrap();
    let (mut fa, pm) = fixture();
    let before = capacity(&fa);
    let backing = preseed();
    install_globals(&mut fa, pm);
    assert!(try_admit());
    let (ok, counts) = {
        let mut owner = OWNER.lock();
        let mut map = crate::memory::PAGE_MAP.lock();
        let mut frames = crate::memory::FRAME_ALLOC.lock();
        assert!(crate::memory::ownership_locks_held());
        begin();
        let ok = prepare_f4_locked(&mut owner, map.as_mut().unwrap(), &mut frames);
        let counts = end();
        (ok, counts)
    };
    assert!(ok);
    assert_eq!(
        counts,
        (0, 0),
        "all-layout F4 allocation/destruction under actual owners"
    );
    backing_unchanged(&backing);
    let owner = OWNER.lock();
    let map = crate::memory::PAGE_MAP.lock();
    let frames = crate::memory::FRAME_ALLOC.lock();
    assert_eq!(owner.capture[1], 12);
    assert_eq!(
        capacity(&frames),
        [before[0] - 12, before[1] + 12, before[2]]
    );
    assert!(arena::valid(map.as_ref().unwrap(), &frames, &owner));
}

#[test]
fn b26_f4_no_allocation_under_owner_map_frame_locks() {
    if child("b26_f4_no_allocation_under_owner_map_frame_locks", 1).is_none() {
        return;
    }
    observed_success();
}

#[test]
fn b26_f4_no_destruction_under_owner_map_frame_locks() {
    if child("b26_f4_no_destruction_under_owner_map_frame_locks", 1).is_none() {
        return;
    }
    observed_success();
}

#[test]
fn b26_f4_refusal_has_no_fallback() {
    let Some(stage) = child("b26_f4_refusal_has_no_fallback", 2) else {
        return;
    };
    let _serial = TEST_LOCK.lock().unwrap();
    let (mut fa, mut pm) = fixture();
    let backing = preseed();
    assert!(try_admit());
    {
        let mut owner = OWNER.lock();
        assert!(prepare_f3_locked(&mut owner, &mut pm, &mut fa));
    }
    // Exactly zero or one new frame is available: stack denial or table denial.
    // Deliberately hold every other real lease; no fake allocator responses.
    let mut held = Vec::new();
    while let Some(lease) = fa.allocate_owned() {
        held.push(lease);
    }
    if stage == 1 {
        assert!(fa.release_frame(held.remove(0)));
    }
    let before = capacity(&fa);
    install_globals(&mut fa, pm);
    let (ok, counts) = {
        let mut owner = OWNER.lock();
        let mut map = crate::memory::PAGE_MAP.lock();
        let mut frames = crate::memory::FRAME_ALLOC.lock();
        assert!(crate::memory::ownership_locks_held());
        begin();
        let ok = prepare_arena_locked(&mut owner, map.as_mut().unwrap(), &mut frames);
        let counts = end();
        (ok, counts)
    };
    assert!(!ok);
    assert_eq!(
        counts,
        (0, 0),
        "exhaustion must not allocate fallback or destroy backing"
    );
    backing_unchanged(&backing);
    let mut owner = OWNER.lock();
    let mut map = crate::memory::PAGE_MAP.lock();
    let mut frames = crate::memory::FRAME_ALLOC.lock();
    let pm = map.as_mut().unwrap();
    assert_eq!(STATE.load(Ordering::Acquire), TERMINAL);
    assert_eq!(owner.capture[1], 10 + stage as u32);
    assert_eq!(owner.capture[0], if stage == 0 { 13 } else { 14 });
    assert_eq!(capacity(&frames), [0, before[1] + stage, before[2]]);
    assert_eq!(read_entry(pm.directory, 256), 0);
    assert_eq!(pm.tables[256], 0);
    assert!(!pm.user_arena_reserved);
    assert!(owner.arena_table.is_none());
    assert_eq!(owner.user_stack.is_some(), stage == 1);
    if let Some(lease) = owner.user_stack.as_ref() {
        assert!(frames.owns_live_lease(lease));
    }
    for dir in 0..1024 {
        assert_eq!(read_entry(pm.directory, dir) & ENTRY_USER, 0);
    }
    let retained = snapshot(&frames, pm);
    begin();
    let retry = prepare_arena_locked(&mut owner, pm, &mut frames);
    let release = owner
        .user_stack
        .as_ref()
        .is_some_and(|l| frames.release_frame(l.duplicate_for_test()));
    let allocate = frames.allocate_owned().is_some();
    let counts = end();
    assert!(!retry && !release && !allocate && !try_admit());
    assert_eq!(counts, (0, 0));
    assert_eq!(snapshot(&frames, pm), retained);
}
