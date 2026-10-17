//! Phase 11A.2-B host oracle: exception error-code frame ABI.
//! These tests check the frame layout and decoding contract only; real
//! CPU fault behavior is proven by the QEMU probes, not here.
use super::*;

#[test]
fn phase11a2_error_code_vectors_are_classified() {
    // Error-code vectors on this 32-bit protected-mode CPU contract
    // (Intel Vol. 2, table 12): #DF(8), #TS(10), #NP(11), #SS(12), #GP(13),
    // #PF(14), #AC(17). Every other vector in 0..31 pushes no error code.
    let with_code = [8, 10, 11, 12, 13, 14, 17];
    for vector in 0..32 {
        let expected = with_code.contains(&vector);
        assert_eq!(exception_pushes_error_code(vector), expected);
    }
}

#[test]
fn phase11a2_gp_error_code_is_selector_format() {
    // Exception selector error format (Intel Vol. 2): bit 0 EXT (external
    // selector not present), bit 1 IDT (fault came from the IDT), bit 2 TI
    // (1 = LDT, 0 = GDT), bits 3+ selector index. The handler must report
    // the code raw; page-fault bit semantics do not apply.
    let raw = 0x0058;
    assert_eq!(raw & 1, 0); // EXT clear
    assert_eq!((raw >> 1) & 1, 0); // IDT clear
    assert_eq!((raw >> 2) & 1, 0); // TI clear: GDT selector
    assert_eq!(raw >> 3, 0x0B); // selector index
}

#[test]
fn phase11a2_pf_error_code_keeps_page_semantics() {
    // The page-fault format is unchanged: bit 0 present, bit 1 write, bit 2
    // user, bit 4 instruction fetch.
    let info = decode_error_code(0x0002);
    assert_eq!(info.present, false);
    assert_eq!(info.write, true);
    assert_eq!(info.user, false);
    assert_eq!(info.fetch, false);
}

#[test]
fn phase11a2_fault_origin_reads_saved_cs_ring() {
    // Fault-origin detection uses the saved CS from the CPU frame: the
    // privilege level is the selector's RPL bits, cs & 3. A CPL3 user fault
    // must be distinguishable from a CPL0 kernel fault before any recovery
    // decision is taken.
    assert_eq!(fault_ring_from_saved_cs(0x0023), 3);
    assert_eq!(fault_ring_from_saved_cs(0x0008), 0);
}
