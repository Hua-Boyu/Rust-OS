//! Real F5 owner/install transactions; irreversible subcases use exact-one children.
use super::f4_user_arena_tests::{fixture, isolated, snapshot};
use super::retained_owner::{
    OWNER, PREPARING, SEALED, STATE, admit_f5, capacity, prepare_f4_locked, prepare_f5_locked,
    seal_f5_locked,
};
use super::user_arena::{self as arena, observation};
use super::*;
use core::sync::atomic::Ordering;

fn child(name: &str, cases: usize) -> Option<usize> {
    let prefix = module_path!().split_once("::").unwrap().1;
    isolated(&format!("{prefix}::{name}"), cases)
}

fn expected_image(f5: bool) -> [u8; PAGE_SIZE] {
    let mut image = [0; PAGE_SIZE];
    image[..4].copy_from_slice(&[0x0f, 0x0b, 0xeb, 0xfc]);
    image[2048..2059].copy_from_slice(b"F4-RO-DATA\0");
    if f5 {
        let snippets = [
            "31c0668cc868dec0175a5bfd0f0b0f0b",
            "31c0668cc868dec0175a5bfdc605000800407e0f0b",
            "31c0668cc868dec0175a5bfd8b0d0010c0070f0b",
            "31c0668cc868dec0175a5bfdf40f0b",
            "31c0668cc868dec0175a5bfde6800f0b",
            "31c0668cc868dec0175a5bfd8b0d00e03f400f0b",
        ];
        for (slot, text) in snippets.iter().enumerate() {
            for i in 0..text.len() / 2 {
                image[256 + slot * 64 + i] =
                    u8::from_str_radix(&text[i * 2..i * 2 + 2], 16).unwrap();
            }
        }
    }
    image
}

#[test]
fn before_publication_payload_copy_exact() {
    if child("before_publication_payload_copy_exact", 1).is_none() {
        return;
    }
    let expected = expected_image(true);
    let (mut fa, mut pm) = fixture();
    observation::enable();
    assert!(admit_f5(1));
    let (code, stack, table) = {
        let mut owner = OWNER.lock();
        assert!(prepare_f5_locked(&mut owner, &mut pm, &mut fa, 1));
        assert!(arena::valid(&pm, &fa, &owner));
        (
            owner.payload.as_ref().unwrap().frame_addr(),
            owner.user_stack.as_ref().unwrap().frame_addr(),
            owner.arena_table.as_ref().unwrap().frame_addr(),
        )
    };
    let o = observation::take();
    assert_eq!((o.code_address, o.stack_address), (code, stack));
    assert_eq!(o.initialized_code, expected);
    assert_eq!(o.code, expected);
    assert_eq!(o.initialized_stack, [0; PAGE_SIZE]);
    assert_eq!(o.stack, [0; PAGE_SIZE]);
    assert_eq!(o.count, 8);
    assert_eq!(o.prepublication_code, expected);
    assert_eq!(o.prepublication_stack, [0; PAGE_SIZE]);
    let code_leaf = code as u32 | 5 | ENTRY_RUNTIME_PAYLOAD;
    let stack_leaf = stack as u32 | 7 | ENTRY_RUNTIME_PAYLOAD;
    assert_eq!(
        o.events,
        [
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 12],
            [2, 0, 0, 0, 1, 0, 0, 0, 0, 1, 12],
            [3, 0, 0, 0, 1, 1, 0, 0, 0, 1, 12],
            [4, 0, 0, 0, 1, 1, 1, 0, 0, 1, 12],
            [5, 0, 0, 0, 1, 1, 1, 1, 1, 1, 12],
            [6, 0, code_leaf, 0, 1, 1, 1, 1, 1, 1, 12],
            [7, 0, code_leaf, stack_leaf, 1, 1, 1, 1, 1, 1, 12],
            [8, 0, code_leaf, stack_leaf, 1, 1, 1, 1, 1, 1, 12],
        ]
    );
    assert_eq!(read_entry(pm.directory, 256), table as u32 | 7);
    assert_eq!(read_entry(table, 1022), 0);
    assert_eq!(read_entry(table, 1), 0);
}

#[test]
fn default_f4_image_bytes_unchanged() {
    let Some(case) = child("default_f4_image_bytes_unchanged", 2) else {
        return;
    };
    let f5 = case == 1;
    let expected = expected_image(f5);
    let baseline = expected_image(false);
    let (mut fa, mut pm) = fixture();
    observation::enable();
    assert!(admit_f5(1));
    {
        let mut owner = OWNER.lock();
        assert!(if f5 {
            prepare_f5_locked(&mut owner, &mut pm, &mut fa, 1)
        } else {
            prepare_f4_locked(&mut owner, &mut pm, &mut fa)
        });
    }
    let o = observation::take();
    assert_eq!(o.initialized_code, expected);
    assert_eq!(o.initialized_stack, [0; PAGE_SIZE]);
    for i in 0..PAGE_SIZE {
        if !f5 || !(256..640).contains(&i) {
            assert_eq!(o.code[i], baseline[i]);
        }
    }
}

#[test]
fn twelve_frame_state_preservation() {
    if child("twelve_frame_state_preservation", 1).is_none() {
        return;
    }
    let (mut fa, mut pm) = fixture();
    let before = capacity(&fa);
    let cr3 = pm.directory;
    observation::enable();
    assert!(admit_f5(6));
    let mut addresses = [0; 12];
    {
        let mut owner = OWNER.lock();
        assert!(prepare_f5_locked(&mut owner, &mut pm, &mut fa, 6));
        assert_eq!(owner.capture[1], 12);
        assert_eq!(STATE.load(Ordering::Acquire), PREPARING);
        for (i, lease) in core::iter::once(&owner.payload)
            .chain(core::iter::once(&owner.sentinel))
            .chain(owner.transition.iter())
            .chain(owner.emergency.iter())
            .chain(core::iter::once(&owner.user_stack))
            .chain(core::iter::once(&owner.arena_table))
            .flatten()
            .enumerate()
        {
            assert!(fa.owns_live_lease(lease));
            addresses[i] = lease.frame_addr();
        }
        assert!(seal_f5_locked(&mut owner, &pm, &fa));
        assert!(!seal_f5_locked(&mut owner, &pm, &fa));
    }
    addresses.sort_unstable();
    assert!(addresses.windows(2).all(|p| p[0] != p[1]));
    assert_eq!(capacity(&fa), [before[0] - 12, before[1] + 12, before[2]]);
    assert_eq!(pm.directory, cr3);
    assert_eq!(STATE.load(Ordering::Acquire), SEALED);
    let sealed = snapshot(&fa, &pm);
    assert!(!admit_f5(1));
    assert!(fa.allocate_owned().is_none());
    assert!(!fa.init(&[], 0, 0, 0));
    {
        let owner = OWNER.lock();
        for (address, lease) in [
            (arena::START, owner.payload.as_ref().unwrap()),
            (arena::STACK, owner.user_stack.as_ref().unwrap()),
        ] {
            assert!(!pm.unmap_owned(&mut fa, address, lease));
            assert!(!fa.release_frame(lease.duplicate_for_test()));
        }
        assert!(arena::valid(&pm, &fa, &owner));
    }
    assert_eq!(snapshot(&fa, &pm), sealed);
    let _ = observation::take();
}

#[test]
fn invalid_scenario_preflight_refusal() {
    let Some(case) = child("invalid_scenario_preflight_refusal", 6) else {
        return;
    };
    let invalid = [0, 7, 8, 255, 65535, u32::MAX][case];
    let (mut fa, mut pm) = fixture();
    observation::enable();
    let before = snapshot(&fa, &pm);
    assert_eq!(STATE.load(Ordering::Acquire), 0);
    assert!(!admit_f5(invalid));
    {
        let mut owner = OWNER.lock();
        let capture = owner.capture;
        let arena_capture = owner.arena_capture;
        let ranges = owner.future_ranges;
        assert!(!prepare_f5_locked(&mut owner, &mut pm, &mut fa, invalid));
        assert_eq!(
            (owner.capture, owner.arena_capture, owner.future_ranges),
            (capture, arena_capture, ranges)
        );
        assert!(owner.payload.is_none() && owner.sentinel.is_none());
        assert!(
            owner
                .transition
                .iter()
                .chain(owner.emergency.iter())
                .all(Option::is_none)
        );
        assert!(owner.user_stack.is_none() && owner.arena_table.is_none());
    }
    assert_eq!(snapshot(&fa, &pm), before);
    assert_eq!(STATE.load(Ordering::Acquire), 0);
    let o = observation::take();
    assert_eq!((o.code_address, o.stack_address, o.count), (0, 0, 0));
    assert_eq!(o.code, [0xa5; PAGE_SIZE]);
    assert_eq!(o.stack, [0xa5; PAGE_SIZE]);
}
