//! Checked 4KiB/512-byte translation. Successful flush must durably order all
//! preceding writes; implementors must not supply a no-op flush.
use crate::format::{FS_BLOCK_SIZE, SECTOR_SIZE, SECTORS_PER_BLOCK};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BlockError {
    OutOfRange,
    BufferSizeMismatch,
    Protected,
    Rejected,
    Torn,
}
impl core::fmt::Display for BlockError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{self:?}")
    }
}
pub trait BlockDevice {
    fn sector_size(&self) -> usize;
    fn capacity_sectors(&self) -> usize;
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError>;
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError>;
    fn test_owned(&self) -> bool;
    fn flush(&mut self) -> Result<(), BlockError>;
    fn block_first_sector(&self, block: usize) -> Result<usize, BlockError> {
        if self.sector_size() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        let first = block
            .checked_mul(SECTORS_PER_BLOCK)
            .ok_or(BlockError::OutOfRange)?;
        let end = first
            .checked_add(SECTORS_PER_BLOCK)
            .ok_or(BlockError::OutOfRange)?;
        if block == 0 || end > self.capacity_sectors() {
            return Err(BlockError::OutOfRange);
        }
        Ok(first)
    }
    fn read_block(&mut self, block: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        if buf.len() != FS_BLOCK_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        let first = self.block_first_sector(block)?;
        for s in 0..SECTORS_PER_BLOCK {
            self.read_sector(first + s, &mut buf[s * SECTOR_SIZE..(s + 1) * SECTOR_SIZE])?;
        }
        Ok(())
    }
    fn write_block(&mut self, block: usize, buf: &[u8]) -> Result<(), BlockError> {
        if buf.len() != FS_BLOCK_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        let first = self.block_first_sector(block)?;
        if !self.test_owned() {
            return Err(BlockError::Protected);
        }
        for s in 0..SECTORS_PER_BLOCK {
            self.write_sector(first + s, &buf[s * SECTOR_SIZE..(s + 1) * SECTOR_SIZE])?;
        }
        Ok(())
    }
}
