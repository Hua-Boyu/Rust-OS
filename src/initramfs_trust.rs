//! Authenticate exact, complete module bytes before structural parsing.
//!
//! `expected` MUST come from an independent trusted kernel/build input, never
//! from this archive, a companion untrusted module, or a boot-time self-hash.
//! The digest covers every byte supplied: headers, names, payload, trailer and
//! all alignment/final zero padding. There is no canonicalization or exclusion.
//! The caller must hold an immutable owned snapshot through verify and import;
//! the returned index is not a capability for subsequently changed bytes.
use crate::initramfs::{self, Archive, ArchiveError};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum TrustError {
    DigestMismatch,
    Structure(ArchiveError),
}

pub(crate) fn verify(bytes: &[u8], expected: &[u8; 32]) -> Result<Archive, TrustError> {
    // Refuse unbounded hashing before inspecting content or allocating an index.
    if bytes.len() > initramfs::MAX_ARCHIVE_BYTES {
        return Err(TrustError::Structure(ArchiveError::Limit));
    }
    let actual = sha256(bytes);
    // Fixed-length comparison via subtle (no first-differing-byte early exit).
    // Length, parsing and the final accept/reject branch are not constant-time.
    if !bool::from(actual.ct_eq(expected)) {
        return Err(TrustError::DigestMismatch);
    }
    initramfs::parse(bytes).map_err(TrustError::Structure)
}

pub(crate) fn sha256(bytes: &[u8]) -> [u8; 32] {
    Sha256::digest(bytes).into()
}
