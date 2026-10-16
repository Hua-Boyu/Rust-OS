//! Trusted build policy, not module-supplied metadata.
//!
//! SHA-256 of every byte of the deterministic newc archive built from system/,
//! including headers, names, data, trailer and all padding. No bytes excluded.
//! Updating system/ requires an explicit reviewed digest update and kernel rebuild.
//! This authenticates the archive only if this kernel image is itself trusted;
//! it is not hardware secure boot or comprehensive verified boot.
pub(crate) const EXPECTED_SHA256: [u8; 32] = [
    0x8f, 0xf3, 0xbf, 0xdc, 0x92, 0x5e, 0x1b, 0x0e, 0x60, 0x44, 0x1b, 0x07, 0x2f, 0x4c, 0x4c, 0x0c,
    0x4f, 0x6b, 0x16, 0xf6, 0x8d, 0xfc, 0xe0, 0xc0, 0xff, 0x50, 0xbb, 0x60, 0x9d, 0x64, 0xa6, 0xa7,
];
