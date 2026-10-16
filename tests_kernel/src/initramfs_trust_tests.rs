use crate::initramfs::initramfs_tests::{fixture, gnu_fixture};
use crate::initramfs_trust::{TrustError, sha256, verify};

#[test]
fn independent_expected_digest_is_required() {
    let bytes = gnu_fixture();
    let expected = digest("09a3400294a66f28f2a09e3a83a8678b1d2509703b3ad145e5f1d217b2820c3e");
    let archive = verify(&bytes, &expected).unwrap();
    assert_eq!(archive.total_bytes, bytes.len());
    assert_eq!(archive.entries.len(), 1);
    for i in 0..32 {
        let mut wrong = expected;
        wrong[i] ^= 1;
        assert_eq!(verify(&bytes, &wrong), Err(TrustError::DigestMismatch));
    }
}

#[test]
fn oversize_rejected_before_digest_work() {
    let bytes = vec![0; crate::initramfs::MAX_ARCHIVE_BYTES + 1];
    assert_eq!(
        verify(&bytes, &[0; 32]),
        Err(TrustError::Structure(crate::initramfs::ArchiveError::Limit))
    );
}

fn digest(hex: &str) -> [u8; 32] {
    assert_eq!(hex.len(), 64);
    core::array::from_fn(|i| u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16).unwrap())
}

#[test]
fn sha256_known_vectors() {
    for (bytes, expected) in [
        (
            &b""[..],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        (
            &b"abc"[..],
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        ),
        (
            &b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"[..],
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
        ),
    ] {
        assert_eq!(sha256(bytes), digest(expected));
    }
    assert_eq!(
        sha256(&vec![b'a'; 1_000_000]),
        digest("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")
    );
}

#[test]
fn every_exact_gnu_archive_byte_is_authenticated() {
    let bytes = gnu_fixture();
    let expected = digest("09a3400294a66f28f2a09e3a83a8678b1d2509703b3ad145e5f1d217b2820c3e");
    // Includes every header/name/data/trailer/alignment/final-padding byte.
    for i in 0..bytes.len() {
        let mut changed = bytes.clone();
        changed[i] ^= 1;
        assert_eq!(
            verify(&changed, &expected),
            Err(TrustError::DigestMismatch),
            "byte {i}"
        );
    }
}

#[test]
fn final_zero_padding_length_is_authenticated_not_trimmed() {
    let bytes = gnu_fixture();
    let expected = sha256(&bytes);
    let mut longer = bytes.clone();
    longer.push(0);
    assert!(crate::initramfs::parse(&longer).is_ok());
    assert_eq!(verify(&longer, &expected), Err(TrustError::DigestMismatch));
    assert_eq!(
        verify(&bytes[..511], &expected),
        Err(TrustError::DigestMismatch)
    );
    assert!(verify(&longer, &sha256(&longer)).is_ok());
}

#[test]
fn empty_input_with_correct_digest_is_not_an_archive() {
    assert_eq!(
        verify(b"", &sha256(b"")),
        Err(TrustError::Structure(
            crate::initramfs::ArchiveError::Truncated
        ))
    );
    let empty = fixture(&[]);
    assert!(verify(&empty, &sha256(&empty)).unwrap().entries.is_empty());
}

#[test]
fn correct_digest_does_not_bypass_required_byte_truncation() {
    let bytes = fixture(&[(0o100644, b"abc", b"123")]);
    for cut in 0..bytes.len() {
        let truncated = &bytes[..cut];
        assert!(
            matches!(
                verify(truncated, &sha256(truncated)),
                Err(TrustError::Structure(_))
            ),
            "cut {cut}"
        );
    }
}

#[test]
fn correct_digest_does_not_bypass_structural_validation() {
    use crate::initramfs::ArchiveError as E;
    let good = gnu_fixture();
    for (at, value, error) in [
        (0, b'X', E::Magic),
        (102, b'1', E::Field),
        (131, 1, E::Alignment),
        (good.len() - 1, 1, E::Trailer),
    ] {
        let mut bad = good.clone();
        bad[at] = value;
        assert_eq!(
            verify(&bad, &sha256(&bad)),
            Err(TrustError::Structure(error))
        );
    }
    for (bytes, error) in [
        (
            fixture(&[(0o100644, b"a", b""), (0o100644, b"a", b"")]),
            E::Duplicate,
        ),
        (fixture(&[(0o100644, b"../x", b"")]), E::Path),
        (fixture(&[(0o120777, b"link", b"target")]), E::Type),
    ] {
        assert_eq!(
            verify(&bytes, &sha256(&bytes)),
            Err(TrustError::Structure(error))
        );
    }
}

#[test]
fn concatenated_archives_are_rejected_even_with_correct_digest() {
    let mut bytes = gnu_fixture();
    bytes.extend(gnu_fixture());
    assert_eq!(
        verify(&bytes, &sha256(&bytes)),
        Err(TrustError::Structure(
            crate::initramfs::ArchiveError::Trailer
        ))
    );
}

#[test]
fn exact_maximum_archive_length_is_accepted() {
    let mut bytes = gnu_fixture();
    bytes.resize(crate::initramfs::MAX_ARCHIVE_BYTES, 0);
    assert_eq!(
        verify(&bytes, &sha256(&bytes)).unwrap().total_bytes,
        bytes.len()
    );
    bytes.push(0);
    assert_eq!(
        verify(&bytes, &sha256(&bytes)),
        Err(TrustError::Structure(crate::initramfs::ArchiveError::Limit))
    );
}
