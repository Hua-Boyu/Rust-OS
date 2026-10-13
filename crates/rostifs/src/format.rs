//! Version 1: block 0 reserved; roots 1/2; two 2-block metadata banks 3/5;
//! data starts at 7. All integers explicitly little endian. CRC32C covers
//! entire padded metadata/data and root bytes 0..4092. No native disk structs.
pub const SECTOR_SIZE: usize = 512;
pub const FS_BLOCK_SIZE: usize = 4096;
pub const SECTORS_PER_BLOCK: usize = 8;
pub const FORMAT_VERSION: u32 = 1;
pub const MAGIC: &[u8; 8] = b"ROSTIFS\x01";
pub const MAX_INODES: usize = 64;
pub const MAX_NAME_LEN: usize = 60;
pub const MAX_PATH_LEN: usize = 256;
pub const MAX_ENTRIES_PER_DIR: usize = MAX_INODES - 1;
pub const MAX_FILE_BYTES: usize = 64 * FS_BLOCK_SIZE;
pub const MAX_VOLUME_BLOCKS: usize = 65536;
pub const INODE_WIRE_SIZE: usize = 128;
pub const METADATA_BLOCKS: usize = 2;
pub const DATA_START: usize = 7;
pub const TYPE_FILE: u8 = 1;
pub const TYPE_DIR: u8 = 2;
pub fn put_u32(b: &mut [u8], o: usize, v: u32) {
    b[o..o + 4].copy_from_slice(&v.to_le_bytes());
}
pub fn put_u64(b: &mut [u8], o: usize, v: u64) {
    b[o..o + 8].copy_from_slice(&v.to_le_bytes());
}
pub fn get_u32(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
pub fn get_u64(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Superblock {
    pub fs_id: u64,
    pub generation: u64,
    pub total_blocks: u32,
    pub bank: u32,
    pub metadata_crc: [u32; METADATA_BLOCKS],
}
impl Superblock {
    pub fn encode(&self, b: &mut [u8; FS_BLOCK_SIZE]) {
        b.fill(0);
        b[..8].copy_from_slice(MAGIC);
        put_u32(b, 8, FORMAT_VERSION);
        put_u32(b, 12, FS_BLOCK_SIZE as u32);
        put_u32(b, 16, self.total_blocks);
        put_u32(b, 20, self.bank);
        put_u64(b, 24, self.fs_id);
        put_u64(b, 32, self.generation);
        for i in 0..METADATA_BLOCKS {
            put_u32(b, 40 + i * 4, self.metadata_crc[i]);
        }
        put_u32(b, 48, 0); // fixed root inode
        put_u32(b, 52, DATA_START as u32); // extent-inventory allocation boundary
        let crc = crate::checksum::crc32c(&b[..4092]);
        put_u32(b, 4092, crc);
    }
    pub fn decode(
        b: &[u8; FS_BLOCK_SIZE],
        bank: usize,
        capacity: usize,
    ) -> Result<Self, crate::vfs::FsError> {
        use crate::vfs::FsError::*;
        if &b[..8] != MAGIC {
            return Err(CorruptVolume);
        }
        if get_u32(b, 8) != FORMAT_VERSION {
            return Err(UnsupportedVersion);
        }
        if get_u32(b, 4092) != crate::checksum::crc32c(&b[..4092])
            || get_u32(b, 12) != 4096
            || get_u32(b, 20) != bank as u32
            || get_u32(b, 48) != 0
            || get_u32(b, 52) != DATA_START as u32
            || b[56..4092].iter().any(|&x| x != 0)
        {
            return Err(CorruptVolume);
        }
        let total = get_u32(b, 16) as usize;
        if !(DATA_START..=MAX_VOLUME_BLOCKS).contains(&total)
            || total.checked_mul(8) != Some(capacity)
        {
            return Err(CorruptVolume);
        }
        Ok(Self {
            fs_id: get_u64(b, 24),
            generation: get_u64(b, 32),
            total_blocks: total as u32,
            bank: bank as u32,
            metadata_crc: [get_u32(b, 40), get_u32(b, 44)],
        })
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Inode {
    pub generation: u32,
    pub kind: u8,
    pub parent: u8,
    pub name_len: u8,
    pub size: u32,
    pub start: u32,
    pub blocks: u32,
    pub data_crc: u32,
    pub name: [u8; MAX_NAME_LEN],
}
impl Inode {
    pub const EMPTY: Self = Self {
        generation: 0,
        kind: 0,
        parent: 0,
        name_len: 0,
        size: 0,
        start: 0,
        blocks: 0,
        data_crc: 0,
        name: [0; MAX_NAME_LEN],
    };
    pub fn encode(&self, b: &mut [u8]) {
        b.fill(0);
        put_u32(b, 0, self.generation);
        b[4] = self.kind;
        b[5] = self.parent;
        b[6] = self.name_len;
        put_u32(b, 8, self.size);
        put_u32(b, 12, self.start);
        put_u32(b, 16, self.blocks);
        put_u32(b, 20, self.data_crc);
        b[24..84].copy_from_slice(&self.name);
    }
    pub fn decode(b: &[u8]) -> Result<Self, crate::vfs::FsError> {
        if b[7] != 0 || b[84..].iter().any(|&x| x != 0) {
            return Err(crate::vfs::FsError::CorruptVolume);
        }
        let mut n = Self::EMPTY;
        n.generation = get_u32(b, 0);
        n.kind = b[4];
        n.parent = b[5];
        n.name_len = b[6];
        n.size = get_u32(b, 8);
        n.start = get_u32(b, 12);
        n.blocks = get_u32(b, 16);
        n.data_crc = get_u32(b, 20);
        n.name.copy_from_slice(&b[24..84]);
        Ok(n)
    }
}
pub(crate) fn valid_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= MAX_NAME_LEN
        && s != "."
        && s != ".."
        && !s.chars().any(|c| c.is_control() || c == '/' || c == '\\')
}
