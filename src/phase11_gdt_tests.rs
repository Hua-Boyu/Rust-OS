use super::*;

// Decode bytes in architectural wire order, independently of encoder shifts.
fn check(base: u32, limit: u32, access: u8, flags: u8) {
    let raw = GdtSegment {
        base,
        limit,
        access_byte: access,
        flag: flags,
    }
    .as_u64();
    let b = raw.to_le_bytes();
    let decoded_base = u32::from_le_bytes([b[2], b[3], b[4], b[7]]);
    let decoded_limit = u32::from_le_bytes([b[0], b[1], b[6] & 15, 0]);
    assert_eq!(decoded_base, base, "base in {raw:#018x}");
    assert_eq!(decoded_limit, limit & 0xfffff, "limit in {raw:#018x}");
    assert_eq!(b[5], access, "access in {raw:#018x}");
    assert_eq!(b[6] & 0xf0, flags & 0xf0, "flags in {raw:#018x}");
    assert_eq!(b[5] & 15, access & 15, "type");
    assert_eq!((b[5] >> 4) & 1, (access >> 4) & 1, "system bit");
    assert_eq!((b[5] >> 5) & 3, (access >> 5) & 3, "DPL");
    assert_eq!(b[5] >> 7, access >> 7, "present");
}

#[test]
fn phase11_gdt_nonzero_base_does_not_contaminate_access() {
    check(0x12345678, 103, 0x89, 0);
}

#[test]
fn phase11_gdt_wire_fields_and_limit_boundaries() {
    for base in [
        0,
        1,
        0xffff,
        0x10000,
        0x01000000,
        0x80000000,
        0xfedcba98,
        u32::MAX,
    ] {
        for limit in [0, 1, 103, 0xffff, 0x10000, 0xfffff, u32::MAX] {
            for access in [0, 0x09, 0x89, 0xa9, 0xc9, 0xe9, 0x9b, 0xf3, 0xff] {
                for flags in [0, 0x10, 0x40, 0x80, 0xc0, 0xff] {
                    check(base, limit, access, flags);
                }
            }
        }
    }
}

#[test]
fn phase11_gdt_privilege_presence_and_tss_type() {
    for dpl in 0..=3 {
        let segment = GdtSegment::new(0x12345678, 103)
            .with_access_byte(AccessByte::Present)
            .with_access_byte(AccessByte::Accessed)
            .with_access_byte(AccessByte::Executable)
            .set_privilege(dpl)
            .unwrap();
        check(segment.base, segment.limit, 0x89 | (dpl << 5), 0);
        assert_eq!(segment.access_byte, 0x89 | (dpl << 5));
    }
    assert!(GdtSegment::new(0, 0).set_privilege(4).is_err());
    assert_eq!(
        create_gdt_entries(),
        [0, 0x00cf99000000ffff, 0x00cf93000000ffff]
    );
}
