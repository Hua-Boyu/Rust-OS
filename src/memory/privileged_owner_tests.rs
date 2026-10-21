//! Fresh-process tests of real F3 extension of the existing one-shot owner.
use super::retained_owner::{
    CpuState, MODEL_CPU, OWNER, PREPARING, RetainedOwner, SEALED, STATE, TERMINAL, capacity,
    prepare_f3_locked, try_admit,
};
use super::*;
use crate::multiboot::MmapEntry;
use core::sync::atomic::Ordering;

fn child(name: &str) -> bool {
    let prefix = module_path!().split_once("::").unwrap().1;
    super::retained_owner::tests::child_identity(&format!("{prefix}::{name}"))
}

fn fixture() -> (FrameAllocator, PageMap) {
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
                base_addr: super::privileged::TRANSITION_GUARD as u64,
                length: 0x400000,
                type_: 1
            },
        ],
        0x90000,
        0xa0000,
        0xb0000,
    ));
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

#[test]
fn f3_owner_ten_frames_stay_preparing_until_cpu_install() {
    if !child("f3_owner_ten_frames_stay_preparing_until_cpu_install") {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let before = capacity(&fa);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(prepare_f3_locked(&mut owner, &mut pm, &mut fa));
    assert_eq!(STATE.load(Ordering::Acquire), PREPARING);
    assert_eq!(owner.capture[1], 10);
    assert_eq!(capacity(&fa), [before[0] - 10, before[1] + 10, before[2]]);
    assert!(pm.privileged_stacks_valid(&fa, &owner.transition, &owner.emergency));
    assert_eq!(owner.future_ranges[0], [0; 4]);
    assert_eq!(
        owner.future_ranges[1],
        [0x07c01000, 0x07c05000, 0x07c00000, 1]
    );
    assert_eq!(
        owner.future_ranges[2],
        [0x07c06000, 0x07c0a000, 0x07c05000, 1]
    );
    assert!(core::mem::size_of::<RetainedOwner>() < 4096);
    assert!(!try_admit());
    STATE.store(SEALED, Ordering::Release);
    let address = owner.transition[0].as_ref().unwrap().frame_addr();
    assert!(!fa.free(address));
    assert!(!pm.unmap(&mut fa, 0x07c01000));
}

#[test]
fn f3_owner_partial_oom_retains_every_acquired_lease_terminally() {
    if !child("f3_owner_partial_oom_retains_every_acquired_lease_terminally") {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let mut held = Vec::new();
    while let Some(lease) = fa.allocate_owned() {
        held.push(lease);
    }
    // Return exactly five accessible low frames: baseline2 + transition3.
    for _ in 0..5 {
        assert!(fa.release_frame(held.remove(0)));
    }
    let before = capacity(&fa);
    assert!(try_admit());
    let mut owner = OWNER.lock();
    assert!(!prepare_f3_locked(&mut owner, &mut pm, &mut fa));
    assert_eq!(STATE.load(Ordering::Acquire), TERMINAL);
    assert_eq!(owner.capture[1], 5);
    assert_eq!(capacity(&fa), [0, before[1] + 5, before[2]]);
    assert!(
        owner
            .payload
            .as_ref()
            .is_some_and(|x| fa.owns_live_lease(x))
    );
    assert!(
        owner
            .sentinel
            .as_ref()
            .is_some_and(|x| fa.owns_live_lease(x))
    );
    assert_eq!(owner.transition.iter().flatten().count(), 3);
    assert_eq!(owner.emergency.iter().flatten().count(), 0);
    for lease in owner.transition.iter().flatten() {
        assert!(fa.owns_live_lease(lease));
    }
    assert!(!try_admit());
    assert!(!pm.privileged_reserved);
    assert!(fa.allocate_owned().is_none());
}
