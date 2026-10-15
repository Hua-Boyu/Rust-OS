// GNU cpio -o -H newc fixture embedded verbatim (512 bytes), not a
// production writer roundtrip. SHA256 of the original:
// 09a3400294a66f28f2a09e3a83a8678b1d2509703b3ad145e5f1d217b2820c3e.
use super::*;
use alloc::{format, vec, vec::Vec};

pub(crate) fn gnu_fixture() -> Vec<u8> {
    let mut bytes = b"07070100311F28000081FF000003E8000003E8000000016AD0B8DE0000000B000000000000004600000000000000000000000A00000000hello.txt\x00hello rosti\x0007070100000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000B00000000TRAILER!!!\x00\x00\x00\x00".to_vec();
    bytes.resize(512, 0);
    bytes
}
// Adversarial fixtures serialize the standard field *sequence*, independently
// of parser offsets. Both name and payload padding belong to each record.
pub(crate) fn append(out: &mut Vec<u8>, mode: u32, name: &[u8], data: &[u8]) {
    out.extend_from_slice(b"070701");
    for value in [
        7,
        mode,
        1000,
        1000,
        1,
        123,
        data.len() as u32,
        0,
        0,
        0,
        0,
        (name.len() + 1) as u32,
        0,
    ] {
        out.extend_from_slice(format!("{:08x}", value).as_bytes());
    }
    out.extend_from_slice(name);
    out.push(0);
    while out.len() % 4 != 0 {
        out.push(0);
    }
    out.extend_from_slice(data);
    while out.len() % 4 != 0 {
        out.push(0);
    }
}
pub(crate) fn fixture(records: &[(u32, &[u8], &[u8])]) -> Vec<u8> {
    let mut out = Vec::new();
    for &(mode, name, data) in records {
        append(&mut out, mode, name, data);
    }
    append(&mut out, 0, b"TRAILER!!!", b"");
    out
}
fn set_field(bytes: &mut [u8], off: usize, value: u32) {
    bytes[off..off + 8].copy_from_slice(format!("{:08X}", value).as_bytes());
}
#[test]
fn independent_gnu_newc_parses() {
    let bytes = gnu_fixture();
    let archive = parse(&bytes).unwrap();
    assert_eq!(archive.entries.len(), 1);
    let e = archive.entries[0];
    assert_eq!(&e.name[..e.name_len as usize], b"hello.txt");
    assert_eq!((e.dir, e.offset, e.size), (false, 120, 11));
    assert_eq!(&bytes[120..131], b"hello rosti");
    assert_eq!(archive.total_bytes, 512);
}
#[test]
fn every_name_and_payload_padding_residue() {
    for n in 1..=8 {
        for size in 0..=8 {
            let name = vec![b'a'; n];
            let payload: Vec<u8> = (0..size).map(|i| i as u8 + 1).collect();
            let bytes = fixture(&[(0o100600, &name, &payload), (0o100755, b"last", b"z")]);
            let a = parse(&bytes).unwrap();
            assert_eq!(a.entries.len(), 2);
            let e = a.entries[0];
            assert_eq!(e.offset as usize, (110 + n + 1 + 3) & !3);
            assert_eq!(&bytes[e.offset as usize..e.offset as usize + size], payload);
            let e = a.entries[1];
            assert_eq!(&bytes[e.offset as usize..][..1], b"z");
        }
    }
}
#[test]
fn truncation_all_required_bytes_and_missing_trailer() {
    let bytes = fixture(&[(0o100644, b"abc", b"123")]);
    for cut in 0..bytes.len() {
        assert!(parse(&bytes[..cut]).is_err(), "cut {cut}");
    }
    let mut no_trailer = Vec::new();
    append(&mut no_trailer, 0o100644, b"f", b"x");
    assert_eq!(parse(&no_trailer), Err(ArchiveError::Truncated));
}
#[test]
fn magic_all_hex_fields_and_check() {
    let original = fixture(&[(0o100644, b"f", b"x")]);
    for magic in [b"070702", b"070707", b"000000"] {
        let mut bytes = original.clone();
        bytes[..6].copy_from_slice(magic);
        assert_eq!(parse(&bytes), Err(ArchiveError::Magic));
    }
    for i in 0..13 {
        let mut bytes = original.clone();
        bytes[6 + 8 * i] = b'g';
        assert_eq!(parse(&bytes), Err(ArchiveError::Field));
    }
    let mut bytes = original;
    set_field(&mut bytes, 102, 1);
    assert_eq!(parse(&bytes), Err(ArchiveError::Field));
}
#[test]
fn trailer_complete_consumption_and_padding() {
    let minimal = fixture(&[]);
    assert!(parse(&minimal).unwrap().entries.is_empty());
    for block in [512, 1024] {
        let mut bytes = minimal.clone();
        bytes.resize(block, 0);
        assert!(parse(&bytes).is_ok());
        bytes[block - 1] = 1;
        assert_eq!(parse(&bytes), Err(ArchiveError::Trailer));
    }
    for (off, val) in [(54, 1), (14, 0o100644)] {
        let mut bytes = minimal.clone();
        set_field(&mut bytes, off, val);
        assert_eq!(parse(&bytes), Err(ArchiveError::Trailer));
    }
    let mut twice = minimal.clone();
    twice.extend_from_slice(&minimal);
    assert_eq!(parse(&twice), Err(ArchiveError::Trailer));
    let mut wrong = Vec::new();
    append(&mut wrong, 0, b"TRAILER", b"");
    assert!(parse(&wrong).is_err());
}
#[test]
fn corrupt_name_payload_and_trailer_padding() {
    let original = fixture(&[(0o100644, b"ab", b"x")]);
    // name 110..113, name pad 113..116, payload 116, data pad 117..120.
    for off in [113, 114, 115, 117, 118, 119, original.len() - 1] {
        let mut bytes = original.clone();
        bytes[off] = 1;
        assert_eq!(parse(&bytes), Err(ArchiveError::Alignment));
    }
    let mut bytes = original.clone();
    bytes[112] = b'x';
    assert_eq!(parse(&bytes), Err(ArchiveError::Path));
    let mut bytes = original;
    bytes[110] = 0;
    assert_eq!(parse(&bytes), Err(ArchiveError::Path));
}
#[test]
fn canonical_paths_and_root_directory() {
    let invalid: &[&[u8]] = &[
        b"", b"/abs", b"./a", b"a//b", b"a/", b"a/../b", b"..", b"a/./b", b"a\x1b", b"a\x7f",
        b"a\x80", b"a\0b",
    ];
    for name in invalid {
        assert_eq!(
            parse(&fixture(&[(0o100644, name, b"")])),
            Err(ArchiveError::Path)
        );
    }
    assert_eq!(
        parse(&fixture(&[(0o40700, b".", b"")])),
        Err(ArchiveError::Path)
    );
    assert_eq!(
        parse(&fixture(&[(0o100644, b".", b"")])),
        Err(ArchiveError::Path)
    );
    assert!(parse(&fixture(&[(0o100644, &vec![b'a'; MAX_NAME], b"")])).is_ok());
    assert_eq!(
        parse(&fixture(&[(0o100644, &vec![b'a'; MAX_NAME + 1], b"")])),
        Err(ArchiveError::Path)
    );
    let path = [
        vec![b'a'; 63],
        vec![b'b'; 63],
        vec![b'c'; 63],
        vec![b'd'; 63],
    ]
    .join(&b'/');
    assert_eq!(path.len(), MAX_PATH - 1);
    assert!(parse(&fixture(&[(0o100644, &path, b"")])).is_ok());
    let mut longer = path;
    longer.extend_from_slice(b"/e");
    assert_eq!(
        parse(&fixture(&[(0o100644, &longer, b"")])),
        Err(ArchiveError::Path)
    );
}
#[test]
fn duplicates_and_conflicting_file_prefixes_both_orders() {
    assert_eq!(
        parse(&fixture(&[(0o40755, b"a", b""), (0o40700, b"a", b"")])),
        Err(ArchiveError::Duplicate)
    );
    for records in [
        vec![(0o100644, &b"a"[..], &b""[..]), (0o100644, b"a/b", b"")],
        vec![(0o100644, &b"a/b"[..], &b""[..]), (0o100644, b"a", b"")],
    ] {
        assert_eq!(parse(&fixture(&records)), Err(ArchiveError::Path));
    }
    assert!(parse(&fixture(&[(0o100644, b"a/b", b""), (0o40755, b"a", b"")])).is_ok());
}
#[test]
fn unsupported_types_hardlinks_and_directory_payload() {
    for mode in [0o120777, 0o20666, 0o60666, 0o10644, 0o140666, 0xFFFF_FFFF] {
        assert_eq!(
            parse(&fixture(&[(mode, b"a", b"")])),
            Err(ArchiveError::Type)
        );
    }
    for links in [0, 2, u32::MAX] {
        let mut bytes = fixture(&[(0o100777, b"a", b"")]);
        set_field(&mut bytes, 38, links);
        assert_eq!(parse(&bytes), Err(ArchiveError::Type));
    }
    assert_eq!(
        parse(&fixture(&[(0o40755, b"a", b"x")])),
        Err(ArchiveError::Size)
    );
}
#[test]
fn size_count_and_input_limits() {
    let bytes = fixture(&[(0o100644, b"a", &vec![42; MAX_FILE_SIZE])]);
    assert!(parse(&bytes).is_ok());
    assert_eq!(
        parse(&fixture(&[(0o100644, b"a", &vec![42; MAX_FILE_SIZE + 1])])),
        Err(ArchiveError::Size)
    );
    let mut bytes = fixture(&[]);
    bytes.resize(MAX_ARCHIVE_BYTES, 0);
    assert!(parse(&bytes).is_ok());
    bytes.push(0);
    assert_eq!(parse(&bytes), Err(ArchiveError::Limit));
    let mut bytes = Vec::new();
    for i in 0..MAX_ENTRIES {
        append(&mut bytes, 0o100644, format!("f{i}").as_bytes(), b"");
    }
    let mut full = bytes.clone();
    append(&mut full, 0, b"TRAILER!!!", b"");
    assert_eq!(parse(&full).unwrap().entries.len(), MAX_ENTRIES);
    append(&mut bytes, 0o100644, b"extra", b"");
    append(&mut bytes, 0, b"TRAILER!!!", b"");
    assert_eq!(parse(&bytes), Err(ArchiveError::Limit));
    let mut huge = fixture(&[(0o100644, b"a", b"")]);
    set_field(&mut huge, 54, u32::MAX);
    assert_eq!(parse(&huge), Err(ArchiveError::Size));
    set_field(&mut huge, 94, u32::MAX);
    assert_eq!(parse(&huge), Err(ArchiveError::Path));
}
#[test]
fn malformed_byte_mutation_corpus_never_panics() {
    let original = gnu_fixture();
    for i in 0..original.len() {
        for byte in [0, 0x7f, 0xff] {
            let mut bytes = original.clone();
            bytes[i] = byte;
            let _ = parse(&bytes);
        }
    }
}
#[test]
fn fallible_index_reservation() {
    let bytes = gnu_fixture();
    assert_eq!(parse_inner(&bytes, true), Err(ArchiveError::OutOfMemory));
    assert!(parse_inner(&bytes, false).is_ok());
}
#[test]
fn first_error_latch_is_isolated_from_parallel_parser_tests() {
    let latch = AtomicU8::new(0);
    assert_eq!(
        record_into(&latch, ArchiveError::Duplicate),
        ArchiveError::Duplicate
    );
    record_into(&latch, ArchiveError::Magic);
    assert_eq!(
        decode(latch.load(Ordering::Acquire)),
        Some(ArchiveError::Duplicate)
    );
}
