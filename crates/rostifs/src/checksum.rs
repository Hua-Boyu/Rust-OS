//! CRC32C (Castagnoli) — the documented RostiFS metadata checksum.
//! Table-free bitwise implementation: small static footprint, host-testable.
//! CRC32C detects accidental corruption; it is NOT a cryptographic integrity
//! guarantee (no signed images or Merkle trees are claimed in v0.1).

pub fn crc32c(data: &[u8]) -> u32 {
    !update(0xFFFF_FFFF, data)
}

pub(crate) fn update(mut crc: u32, data: &[u8]) -> u32 {
    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            if crc & 1 != 0 {
                crc = (crc >> 1) ^ 0x82F6_3B78;
            } else {
                crc >>= 1;
            }
        }
    }
    crc
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crc32c_known_vectors() {
        // Standard CRC32C check value for "123456789".
        assert_eq!(crc32c(b"123456789"), 0xE306_9283);
        assert_eq!(crc32c(b""), 0);
        assert_eq!(crc32c(b"a"), 0xC1D0_4330);
    }
}
