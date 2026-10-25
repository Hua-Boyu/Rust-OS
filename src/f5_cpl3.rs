//! F5 terminal CPL3 isolation proof: pure contract definitions.
//! One-shot Ring-3 entry followed by a kernel-owned exception report and halt.
//! No scheduler, syscalls, recovery, PAE/NX or general userland.
//! Target-only launcher/bridge/reporting must be verified separately from these
//! shared scalar contracts; passing host tests is not CPL3 hardware evidence.

pub use crate::memory::paging::f5_contract::*;

pub fn f5_saved_eflags_ok(observed: u32) -> bool {
    (observed & !F5_EFLAGS_AF_MASK) == (F5_SAVED_EFLAGS_AF0 & !F5_EFLAGS_AF_MASK)
}

pub fn f5_saved_selector_ok(raw: u32, expected: u16) -> bool {
    // CPU selector-slot padding (high 16 bits of the 32-bit pushed slot) is
    // recorded raw but never constrained; only the architectural low16 compares.
    (raw & 0xffff) == u32::from(expected)
}

pub fn f5_pf_error_ok(observed: u32, expected: u32) -> bool {
    // Full 32-bit equality: RSVD, I/D, PK, SS and every unsupported bit zero.
    observed == expected
}

/// Gate mandatory-frame reads before dereferencing a candidate pointer.
/// The only admitted first cross-ring frame is exactly ESP0 - 76.
pub fn f5_frame_address_ok(address: u32) -> bool {
    address & 3 == 0 && F5_TSS_ESP0.checked_sub(address) == Some(F5_FRAME_BYTES as u32)
}

/// Scalar reference oracle for the assembly gate, not a pointer-reading API.
/// A caller must validate the address before constructing a frame reference.
/// Never inspect optional SS/ESP for a nested, unsupported or same-ring frame.
pub fn f5_tail_allowed(first: bool, frame: &crate::exception_abi::ExceptionFrame) -> bool {
    first && matches!(frame.vector, 6 | 13 | 14) && f5_saved_selector_ok(frame.cs, F5_USER_CS)
}

/// Closed expected-state predicate, independently compared to emitted bridge
/// instructions and CPU captures. This helper never dereferences USER memory.
pub fn f5_frame_matches(
    scenario: u32,
    address: u32,
    first: bool,
    frame: &crate::exception_abi::ExceptionFrame,
    tail: Option<(u32, u32)>,
    cr2: u32,
) -> bool {
    let Some(row) = f5_row(scenario) else {
        return false;
    };
    if !f5_frame_address_ok(address) || !f5_tail_allowed(first, frame) {
        return false;
    }
    let Some((old_esp, old_ss)) = tail else {
        return false;
    };
    frame.gs == u32::from(F5_USER_DS)
        && frame.fs == u32::from(F5_USER_DS)
        && frame.es == u32::from(F5_USER_DS)
        && frame.ds == u32::from(F5_USER_DS)
        && frame.eax == u32::from(F5_USER_CS)
        && frame.ebx == F5_SENTINEL_EBX
        && address.checked_add(F5_VECTOR_OFFSET as u32) == Some(frame.pushad_esp)
        && frame.vector == row.vector
        && frame.error == row.error
        && frame.eip == row.fault_eip
        && f5_saved_eflags_ok(frame.eflags)
        && old_esp == F5_USER_ESP
        && f5_saved_selector_ok(old_ss, F5_USER_DS)
        && (row.vector != 14 || cr2 == row.cr2)
}

/// Effective classic non-PAE, 4KiB-leaf mapping predicate for scenario C.
/// Both levels must be present; either supervisor level denies USER reads.
/// Large-page PDEs are outside the admitted profile.
pub fn f5_present_supervisor(pde: u32, pte: u32) -> bool {
    pde & 0x81 == 1 && pte & 1 == 1 && (pde & 4 == 0 || pte & 4 == 0)
}
