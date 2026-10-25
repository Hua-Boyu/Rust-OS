//! Pure shared F5 contracts; CPU installation and emitted bridge remain guest obligations.
use crate::exception_abi::{FRAME_SIZE, VECTOR_OFFSET};
use crate::f5_cpl3 as f5;

#[test]
fn descriptor_extension_preserves_tss_slots() {
    assert_eq!(f5::F5_GDT_ENTRIES * 8 - 1, f5::F5_GDTR_LIMIT as usize);
    assert_eq!(f5::F5_TR, 0x18);
    assert_eq!(f5::F5_TSS_SS0, 0x10);
    assert_eq!(f5::F5_USER_CODE, 0x00cf_fb00_0000_ffff);
    assert_eq!(f5::F5_USER_DATA, 0x00cf_f300_0000_ffff);
    // Actual byte-for-byte copy of slots 0..4 is a runtime/hardware obligation.
}

#[test]
fn user_selectors_have_dpl3_rpl3() {
    for (descriptor, selector, slot) in [
        (f5::F5_USER_CODE, f5::F5_USER_CS, 5),
        (f5::F5_USER_DATA, f5::F5_USER_DS, 6),
    ] {
        assert_eq!((descriptor >> 45) & 3, 3);
        assert_eq!(selector, (slot << 3) | 3);
        assert_eq!(selector & 4, 0);
    }
}

#[test]
fn payload_bytes_and_fault_offsets() {
    // Independent byte strings from approved proposal03, including fallback UD2.
    let expected: [&[u8]; 6] = [
        &[0x0f, 0x0b, 0x0f, 0x0b],
        &[0xc6, 0x05, 0x00, 0x08, 0x00, 0x40, 0x7e, 0x0f, 0x0b],
        &[0x8b, 0x0d, 0x00, 0x10, 0xc0, 0x07, 0x0f, 0x0b],
        &[0xf4, 0x0f, 0x0b],
        &[0xe6, 0x80, 0x0f, 0x0b],
        &[0x8b, 0x0d, 0x00, 0xe0, 0x3f, 0x40, 0x0f, 0x0b],
    ];
    for (row, suffix) in f5::F5_ROWS.iter().zip(expected) {
        assert_eq!(&row.bytes[..12], &f5::F5_PROLOGUE);
        assert_eq!(&row.bytes[12..12 + suffix.len()], suffix);
        assert!(row.bytes[12 + suffix.len()..].iter().all(|&b| b == 0));
        assert_eq!(row.fault_eip, row.entry + 12);
    }
    assert_eq!(f5::F5_ROWS[1].bytes[18], 0x7e);
    assert_eq!(f5::F5_RO_DATA_BYTE, 0x46);
}

#[test]
fn fixed_payload_fits_owned_page() {
    assert_eq!(f5::F5_PAYLOAD_BYTES, 6 * f5::F5_SLOT_BYTES);
    assert!(f5::F5_PAYLOAD_OFFSET as usize + f5::F5_PAYLOAD_BYTES < 2048);
    for (i, row) in f5::F5_ROWS.iter().enumerate() {
        assert_eq!(row.entry, 0x4000_0100 + i as u32 * 64);
        assert!(row.bytes.len() <= f5::F5_SLOT_BYTES);
    }
}

#[test]
fn iret_flags_and_stack_contract() {
    assert_eq!(f5::F5_ENTRY_EFLAGS, 2);
    assert_eq!(f5::F5_USER_ESP, 0x4040_0000);
    assert_eq!(f5::F5_TSS_ESP0, 0x07c0_5000);
    assert_eq!(f5::F5_OLD_SS_OFFSET, f5::F5_OLD_ESP_OFFSET + 4);
    assert_eq!(f5::F5_EIP_OFFSET + 4, f5::F5_CS_OFFSET);
    assert_eq!(f5::F5_CS_OFFSET + 4, f5::F5_EFLAGS_OFFSET);
    assert_eq!(f5::F5_EFLAGS_OFFSET + 4, f5::F5_OLD_ESP_OFFSET);
}

#[test]
fn mandatory_prefix_and_conditional_tail() {
    assert_eq!(f5::F5_PREFIX_BYTES, FRAME_SIZE);
    assert_eq!(f5::F5_VECTOR_OFFSET, VECTOR_OFFSET);
    assert_eq!(f5::F5_FRAME_BYTES, FRAME_SIZE + 8);
    assert_eq!(f5::F5_OLD_ESP_OFFSET, FRAME_SIZE);
    assert_eq!(f5::F5_OLD_SS_OFFSET, FRAME_SIZE + 4);
    // PUSHAD's saved ESP value is frame_pointer+48, not offset28's distance
    // from ESP0. Offset28 identifies the word containing that value.
    assert_eq!(f5::F5_PUSHAD_ESP_OFFSET, 28);
    for cs in [0x2b, 0xabcd_002b] {
        assert!(f5::f5_saved_selector_ok(cs, f5::F5_USER_CS));
    }
    for cs in [8, 0x28, 0xffff_0033] {
        assert!(!f5::f5_saved_selector_ok(cs, f5::F5_USER_CS));
    }
    let mut frame = good_frame(1);
    assert!(f5::f5_tail_allowed(true, &frame));
    assert!(!f5::f5_tail_allowed(false, &frame));
    frame.cs = 8;
    assert!(!f5::f5_tail_allowed(true, &frame));
    frame.cs = 0x2b;
    for vector in [2, 8, 21, 29, 30, 32, u32::MAX] {
        frame.vector = vector;
        assert!(!f5::f5_tail_allowed(true, &frame));
    }
    let address = f5::F5_TSS_ESP0 - f5::F5_FRAME_BYTES as u32;
    assert!(f5::f5_frame_address_ok(address));
    for bad in [0, address - 4, address + 1, address + 4, u32::MAX] {
        assert!(!f5::f5_frame_address_ok(bad));
    }
}

fn good_frame(scenario: u32) -> crate::exception_abi::ExceptionFrame {
    let row = f5::f5_row(scenario).unwrap();
    crate::exception_abi::ExceptionFrame {
        gs: 0x33,
        fs: 0x33,
        es: 0x33,
        ds: 0x33,
        eax: 0x2b,
        ebx: 0x5a17_c0de,
        pushad_esp: f5::F5_TSS_ESP0 - f5::F5_FRAME_BYTES as u32 + 48,
        vector: row.vector,
        error: row.error,
        eip: row.fault_eip,
        cs: 0x2b,
        eflags: 0x10446,
        ..Default::default()
    }
}

#[test]
fn exact_exception_oracles() {
    let expected = [
        (6, 0, 0),
        (14, 7, 0x4000_0800),
        (14, 5, 0x07c0_1000),
        (13, 0, 0),
        (13, 0, 0),
        (14, 4, 0x403f_e000),
    ];
    for (i, (row, oracle)) in f5::F5_ROWS.iter().zip(expected).enumerate() {
        assert_eq!((row.vector, row.error, row.cr2), oracle);
        let scenario = i as u32 + 1;
        let address = f5::F5_TSS_ESP0 - f5::F5_FRAME_BYTES as u32;
        for flags in [0x10446, 0x10456] {
            let mut frame = good_frame(scenario);
            frame.cs |= 0xabcd_0000;
            frame.eflags = flags;
            assert!(f5::f5_frame_matches(
                scenario,
                address,
                true,
                &frame,
                Some((0x4040_0000, 0xcafe_0033)),
                row.cr2
            ));
            frame.eflags &= !0x10000;
            assert!(!f5::f5_frame_matches(
                scenario,
                address,
                true,
                &frame,
                Some((0x4040_0000, 0x33)),
                row.cr2
            ));
        }
        let frame = good_frame(scenario);
        assert!(!f5::f5_frame_matches(
            scenario,
            address,
            false,
            &frame,
            Some((0x4040_0000, 0x33)),
            row.cr2
        ));
        assert!(!f5::f5_frame_matches(
            scenario, address, true, &frame, None, row.cr2
        ));
        if row.vector == 14 {
            assert!(!f5::f5_frame_matches(
                scenario,
                address,
                true,
                &frame,
                Some((0x4040_0000, 0x33)),
                row.cr2 ^ 4096
            ));
        }
    }
    assert!(f5::f5_saved_eflags_ok(0x10446));
    assert!(f5::f5_saved_eflags_ok(0x10456));
    assert!(!f5::f5_saved_eflags_ok(0x446));
    assert!(!f5::f5_saved_eflags_ok(0x456));
    assert!(f5::f5_saved_selector_ok(0xcafe_0033, f5::F5_USER_DS));
    assert!(!f5::f5_saved_selector_ok(0xcafe_0032, f5::F5_USER_DS));
}

#[test]
fn supervisor_presence_is_not_assumed() {
    // Require both presence bits; either supervisor level denies USER.
    for (pde, pte, expected) in [
        (3, 3, true),
        (7, 3, true),
        (3, 7, true),
        (7, 7, false),
        (0, 3, false),
        (3, 0, false),
        (0x83, 3, false),
    ] {
        assert_eq!(f5::f5_present_supervisor(pde, pte), expected);
    }
    assert_eq!(f5::F5_ROWS[2].error, 5);
    assert_eq!(f5::F5_ROWS[1].error, 7);
    assert_eq!(f5::F5_ROWS[5].error, 4);
    assert_eq!(f5::F5_ROWS[2].cr2, 0x07c0_1000);
}

#[test]
fn terminal_latch_refuses_resume() {
    // Initial admission range checks only; actual once-latch is not yet built.
    for scenario in 1..=6 {
        assert!(f5::f5_admissible(scenario));
        assert_eq!(f5::f5_row(scenario).unwrap().id as u32, scenario);
    }
    for scenario in [0, 7, 8, 255, 65535, u32::MAX] {
        assert!(!f5::f5_admissible(scenario));
        assert!(f5::f5_row(scenario).is_none());
    }
}

#[test]
fn wrong_origin_or_reserved_error_bits_fail() {
    for cs in [8, 16, 0x28, 0x33] {
        assert!(!f5::f5_saved_selector_ok(cs, f5::F5_USER_CS));
    }
    for expected in [0, 4, 5, 7] {
        assert!(f5::f5_pf_error_ok(expected, expected));
        for bit in 3..32 {
            assert!(!f5::f5_pf_error_ok(expected | (1 << bit), expected));
        }
    }
}
