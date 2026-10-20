//! Irreversible cases run in exact-one fresh libtest children, never by reset.
use super::*;
use crate::multiboot::MmapEntry;

pub(super) fn child(name: &str) -> bool {
    let prefix = module_path!().split_once("::").unwrap().1;
    let identity = format!("{prefix}::{name}");
    child_identity(&identity)
}

pub(in crate::memory) fn child_identity(identity: &str) -> bool {
    if std::env::var("ROSTI_F1_EXACT_CHILD").ok().as_deref() == Some(identity) {
        return true;
    }
    let output = std::process::Command::new(std::env::current_exe().unwrap())
        .args([identity, "--exact", "--test-threads=1", "--nocapture"])
        .env("ROSTI_F1_EXACT_CHILD", identity)
        .output()
        .unwrap();
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.status.success(), "{identity}: {text}");
    assert!(
        text.contains("test result: ok. 1 passed; 0 failed; 0 ignored;"),
        "{identity}: {text}"
    );
    false
}

fn fixture() -> (FrameAllocator, PageMap) {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x70000,
            type_: 1
        }],
        0x90000,
        0xa0000,
        0xb0000
    ));
    let mut pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    assert!(enable_paging(&mut pm));
    *MODEL_CPU.lock() = CpuState {
        cr0: 0x80010000,
        cr3: pm.directory as u32,
        cr4: 0,
        cs: 8,
    };
    (fa, pm)
}

fn snapshot(fa: &FrameAllocator, maps: &[&PageMap]) -> (Vec<u64>, Vec<u64>) {
    let frame = fa.exact_state_for_retained_test();
    let mut pages = Vec::new();
    for pm in maps {
        pages.extend([
            pm.directory,
            pm.domain as u64,
            pm.retained as u64,
            pm.window_end,
        ]);
        pages.extend([
            pm.stats.page_tables as u64,
            pm.stats.mapped_frames as u64,
            pm.stats.enabled as u64,
            pm.stats.maps as u64,
            pm.stats.map_rejects as u64,
            pm.stats.unmaps as u64,
            pm.stats.unmap_rejects as u64,
            pm.stats.tlb_invalidation as u64,
        ]);
        pages.extend(pm.tables.iter().copied());
        pages.extend(pm.payload_bitmap.iter().map(|&b| b as u64));
        for &(a, b) in &pm.boot_pins {
            pages.extend([a, b]);
        }
        for page in
            core::iter::once(pm.directory).chain(pm.tables.iter().copied().filter(|&p| p != 0))
        {
            pages.extend((0..PAGE_DIR_ENTRIES).map(|i| read_entry(page, i) as u64));
        }
    }
    (frame, pages)
}

#[test]
fn one_shot_preparation_retains_exact_two_within_policy() {
    if !child("one_shot_preparation_retains_exact_two_within_policy") {
        return;
    }
    let (mut fa, pm) = fixture();
    let before = capacity(&fa);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(prepare_locked(&mut owner, &pm, &mut fa));
    assert_eq!(owner.capture[1], 2);
    assert_eq!(capacity(&fa), [before[0] - 2, before[1] + 2, before[2]]);
    assert!(fa.owns_live_lease(owner.payload.as_ref().unwrap()));
    assert!(fa.owns_live_lease(owner.sentinel.as_ref().unwrap()));
    assert_ne!(
        owner.payload.as_ref().unwrap().frame_addr(),
        owner.sentinel.as_ref().unwrap().frame_addr()
    );
    assert_eq!(owner.future_ranges, [[0; 4]; 3]);
    assert_eq!(MANIFEST.iter().map(|x| x.0 as usize).sum::<usize>(), 12);
    drop(owner);
    assert!(!try_admit());
    assert_eq!(STATE.load(Ordering::Acquire), SEALED);
}

#[test]
fn first_allocation_failure_retains_zero_and_consumes_attempt() {
    if !child("first_allocation_failure_retains_zero_and_consumes_attempt") {
        return;
    }
    let (mut fa, pm) = fixture();
    while fa.allocate_owned().is_some() {}
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(!prepare_locked(&mut owner, &pm, &mut fa));
    assert!(owner.payload.is_none() && owner.sentinel.is_none());
    assert_eq!(owner.capture[0], 2);
    drop(owner);
    assert!(!try_admit());
    assert_eq!(STATE.load(Ordering::Acquire), TERMINAL);
}

#[test]
fn second_allocation_failure_retains_exact_payload() {
    if !child("second_allocation_failure_retains_exact_payload") {
        return;
    }
    let (mut fa, pm) = fixture();
    while fa.stats().free_frames > 1 {
        assert!(fa.allocate_owned().is_some());
    }
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(!prepare_locked(&mut owner, &pm, &mut fa));
    assert_eq!(owner.capture[0], 4);
    assert_eq!(owner.capture[1], 1);
    assert!(fa.owns_live_lease(owner.payload.as_ref().unwrap()));
    assert!(owner.sentinel.is_none());
    assert!(!fa.release_frame(owner.payload.as_ref().unwrap().duplicate_for_test()));
}

#[test]
fn alias_failure_retains_current_identity() {
    if !child("alias_failure_retains_current_identity") {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let candidate = fa.allocate_owned().unwrap();
    let address = candidate.frame_addr();
    assert!(fa.release_frame(candidate));
    let table = pm.tables[page_dir_index(address)];
    write_entry(table, page_table_index(address), 0);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(!prepare_locked(&mut owner, &pm, &mut fa));
    assert_eq!(owner.capture[0], 3);
    assert_eq!(owner.capture[1], 1);
    assert_eq!(owner.payload.as_ref().unwrap().frame_addr(), address);
    assert!(fa.owns_live_lease(owner.payload.as_ref().unwrap()));
}

#[test]
fn wrong_hardware_identity_fails_before_acquisition() {
    if !child("wrong_hardware_identity_fails_before_acquisition") {
        return;
    }
    let (mut fa, pm) = fixture();
    MODEL_CPU.lock().cr3 += 4096;
    let before = capacity(&fa);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(!prepare_locked(&mut owner, &pm, &mut fa));
    assert_eq!(owner.capture[0], 1);
    assert_eq!(capacity(&fa), before);
    assert!(owner.payload.is_none() && owner.sentinel.is_none());
}

#[test]
fn sealed_mutation_matrix_and_alternate_cr3_preserve_exact_state() {
    if !child("sealed_mutation_matrix_and_alternate_cr3_preserve_exact_state") {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut alternate =
        build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    assert!(alternate.retain_for_publication());
    // Nonvacuity: real unsealed writer paths succeed and observe writes.
    let writes = MODEL_WRITES.load(Ordering::Relaxed);
    assert!(enable_paging(&mut alternate));
    assert!(flush_tlb(&mut alternate));
    assert_eq!(MODEL_WRITES.load(Ordering::Relaxed), writes + 2);
    assert!(enable_paging(&mut pm));
    let unmapped = fa.allocate_owned().unwrap();
    let mapped = fa.allocate_owned().unwrap();
    let slot = GROWTH_START as u64;
    assert!(pm.map_owned(&mut fa, slot, &mapped, &KERNEL_PERMS));
    assert!(try_admit());
    assert!(prepare_locked(&mut OWNER.lock(), &pm, &mut fa));
    let before = snapshot(&fa, &[&pm, &alternate]);
    let cpu = hardware();
    let writes = MODEL_WRITES.load(Ordering::Relaxed);
    assert!(!fa.release_frame(unmapped.duplicate_for_test()));
    assert!(!fa.free(unmapped.frame_addr()));
    assert!(fa.allocate_owned().is_none());
    assert!(fa.allocate().is_none());
    assert!(
        fa.claim_growth_frame((GROWTH_START + PAGE_SIZE) as u64)
            .is_none()
    );
    assert!(!fa.init(&[], 0, 0, 0));
    assert!(!fa.init_with_reservations(&[], 0, 0, 0, &[(2, 1)]));
    for pinned in [false, true] {
        assert!(!fa.set_runtime_pin(mapped.frame_addr(), pinned));
        assert!(!fa.set_structure_pin(pm.directory, pinned));
    }
    assert!(!pm.map_owned(&mut fa, slot + PAGE_SIZE as u64, &unmapped, &KERNEL_PERMS));
    assert!(!pm.map_growth_claim(&mut fa, slot + PAGE_SIZE as u64));
    assert!(!pm.unmap_owned(&mut fa, slot, &mapped));
    assert!(!pm.map(
        &mut fa,
        slot + PAGE_SIZE as u64,
        unmapped.frame_addr(),
        &KERNEL_PERMS
    ));
    assert!(!pm.unmap(&mut fa, slot));
    assert!(!alternate.release_unpublished_frames(&mut fa));
    assert!(!alternate.retain_for_publication());
    assert!(!enable_paging(&mut alternate));
    assert!(!flush_tlb(&mut alternate));
    assert_eq!(MODEL_WRITES.load(Ordering::Relaxed), writes);
    assert!(hardware() == cpu);
    assert!(build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).is_none());
    assert!(crate::memory::prepare(&[], 0, 0, 0).is_err());
    assert!(crate::memory::heap_grow_frame(GROWTH_START).is_none());
    assert_eq!(snapshot(&fa, &[&pm, &alternate]), before);
    STATE.store(TERMINAL, Ordering::Release);
    assert!(!try_admit());
    assert!(!fa.release_frame(unmapped.duplicate_for_test()));
    assert!(!pm.unmap_owned(&mut fa, slot, &mapped));
    assert_eq!(snapshot(&fa, &[&pm, &alternate]), before);
}

#[test]
fn ordinary_unsealed_mapping_release_preserves_behavior() {
    let (mut fa, mut pm) = fixture();
    let lease = fa.allocate_owned().unwrap();
    assert!(pm.map_owned(&mut fa, GROWTH_START as u64, &lease, &KERNEL_PERMS));
    assert!(pm.unmap_owned(&mut fa, GROWTH_START as u64, &lease));
    assert!(fa.release_frame(lease));
}

#[test]
fn final_identity_failure_retains_two_and_never_seals() {
    if !child("final_identity_failure_retains_two_and_never_seals") {
        return;
    }
    let (mut fa, pm) = fixture();
    let before = capacity(&fa);
    MODEL_FAIL_FINAL.store(true, Ordering::Relaxed);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(!prepare_locked(&mut owner, &pm, &mut fa));
    assert_eq!(owner.capture[0], 6);
    assert_eq!(owner.capture[1], 2);
    assert_eq!(capacity(&fa), [before[0] - 2, before[1] + 2, before[2]]);
    assert!(fa.owns_live_lease(owner.payload.as_ref().unwrap()));
    assert!(fa.owns_live_lease(owner.sentinel.as_ref().unwrap()));
    assert_eq!(STATE.load(Ordering::Acquire), TERMINAL);
    assert!(!try_admit());
}

#[cfg(feature = "b26-observation")]
fn observe_smoke_only(allocate: bool) {
    use crate::{ALLOCS, BACKING_ONLY, DEALLOCS, TEST_LOCK, WATCH};
    let _serial = TEST_LOCK.lock().unwrap();
    BACKING_ONLY.store(false, Ordering::Relaxed);
    let layout = std::alloc::Layout::from_size_align(37, 8).unwrap();
    let existing = unsafe { std::alloc::alloc(layout) };
    assert!(!existing.is_null());
    ALLOCS.store(0, Ordering::Relaxed);
    DEALLOCS.store(0, Ordering::Relaxed);
    let owner = OWNER.lock();
    WATCH.store(true, Ordering::Relaxed);
    let pointer = if allocate {
        unsafe { std::alloc::alloc(layout) }
    } else {
        unsafe { std::alloc::dealloc(existing, layout) };
        core::ptr::null_mut()
    };
    WATCH.store(false, Ordering::Relaxed);
    drop(owner);
    if allocate {
        assert!(!pointer.is_null());
        unsafe {
            std::alloc::dealloc(pointer, layout);
            std::alloc::dealloc(existing, layout);
        }
    }
    assert_eq!(ALLOCS.load(Ordering::Relaxed), usize::from(allocate));
    assert_eq!(DEALLOCS.load(Ordering::Relaxed), usize::from(!allocate));
}

#[cfg(feature = "b26-observation")]
#[test]
fn b26_detector_observes_smoke_only_allocation() {
    observe_smoke_only(true);
}

#[cfg(feature = "b26-observation")]
#[test]
fn b26_detector_observes_smoke_only_destruction() {
    observe_smoke_only(false);
}
