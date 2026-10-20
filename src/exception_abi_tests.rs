use super::*;

#[test]
fn fixed_prefix_all_offsets() {
    assert_eq!(core::mem::size_of::<ExceptionFrame>(), 68);
    assert_eq!(core::mem::align_of::<ExceptionFrame>(), 4);
    let offsets = [
        core::mem::offset_of!(ExceptionFrame, gs),
        core::mem::offset_of!(ExceptionFrame, fs),
        core::mem::offset_of!(ExceptionFrame, es),
        core::mem::offset_of!(ExceptionFrame, ds),
        core::mem::offset_of!(ExceptionFrame, edi),
        core::mem::offset_of!(ExceptionFrame, esi),
        core::mem::offset_of!(ExceptionFrame, ebp),
        core::mem::offset_of!(ExceptionFrame, pushad_esp),
        core::mem::offset_of!(ExceptionFrame, ebx),
        core::mem::offset_of!(ExceptionFrame, edx),
        core::mem::offset_of!(ExceptionFrame, ecx),
        core::mem::offset_of!(ExceptionFrame, eax),
        core::mem::offset_of!(ExceptionFrame, vector),
        core::mem::offset_of!(ExceptionFrame, error),
        core::mem::offset_of!(ExceptionFrame, eip),
        core::mem::offset_of!(ExceptionFrame, cs),
        core::mem::offset_of!(ExceptionFrame, eflags),
    ];
    assert_eq!(
        offsets,
        [
            0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64
        ]
    );
}

#[test]
fn exhaustive_three_way_vector_profile() {
    let errors = [8, 10, 11, 12, 13, 14, 17];
    let unsupported = [21, 29, 30];
    for vector in 0..32 {
        let expected = if errors.contains(&vector) {
            FrameKind::HardwareError
        } else if unsupported.contains(&vector) {
            FrameKind::Unsupported
        } else {
            FrameKind::NoError
        };
        assert_eq!(frame_kind(vector), expected, "vector {vector}");
    }
    assert_eq!(frame_kind(32), FrameKind::Unsupported);
    assert_eq!(frame_kind(u32::MAX), FrameKind::Unsupported);
}

#[test]
fn same_ring_scalar_esp_has_no_tail_access() {
    let f = ExceptionFrame {
        vector: 6,
        cs: 8,
        pushad_esp: 0x1030,
        ..Default::default()
    };
    assert_eq!(f.same_ring_esp(0x1000), Some(0x1044));
    assert_eq!(f.same_ring_esp(u32::MAX - 67), None);
    assert_eq!(f.synthetic_transition_tail(&[]), None);
    assert_eq!(f.synthetic_transition_tail(&[0xdead, 0xbeef]), None);
}

#[test]
fn synthetic_other_ring_decoder_is_bounded() {
    let f = ExceptionFrame {
        vector: 14,
        cs: 0x1234_001b,
        ..Default::default()
    };
    assert_eq!(f.origin(), Some(3));
    assert_eq!(f.same_ring_esp(0x1000), None);
    for words in [&[][..], &[1][..], &[1, 2, 3][..]] {
        assert_eq!(f.synthetic_transition_tail(words), None);
    }
    assert_eq!(
        f.synthetic_transition_tail(&[0x4000, 0xffff_0023]),
        Some((0x4000, 0x23))
    );
}

#[test]
fn double_fault_and_unsupported_have_no_origin() {
    for vector in [8, 21, 29, 30, 32] {
        let f = ExceptionFrame {
            vector,
            cs: 0x1b,
            ..Default::default()
        };
        assert_eq!(f.origin(), None);
        assert_eq!(f.synthetic_transition_tail(&[1, 2]), None);
        assert_eq!(f.same_ring_esp(0x1000), None);
    }
}

#[test]
fn fatal_latch_first_entry_only() {
    let latch = FatalLatch::new();
    assert!(latch.enter());
    assert!(!latch.enter());
    assert!(!latch.enter());
    assert!(FatalLatch::new().enter());
}

#[test]
fn observed_profile_fails_closed() {
    assert!(supported_profile(0x8001_0011, 0, 2, 8, 16));
    for bit in [0, 16, 31] {
        assert!(!supported_profile(0x8001_0011 & !(1 << bit), 0, 2, 8, 16));
    }
    for cr4 in [1 << 5, 1 << 23] {
        assert!(!supported_profile(0x8001_0011, cr4, 2, 8, 16));
    }
    assert!(!supported_profile(0x8001_0011, 0, 1 << 17, 8, 16));
    assert!(!supported_profile(0x8001_0011, 0, 2, 0x1b, 16));
    assert!(!supported_profile(0x8001_0011, 0, 2, 8, 0x23));
}
