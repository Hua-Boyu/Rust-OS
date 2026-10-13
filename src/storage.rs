//! Main-context shared ATA ownership. Separate lightweight views serialize
//! diagnostic and filesystem I/O through the same device, never aliasing an
//! `&mut AtaDevice`. No ISR may acquire this mutex; the I/O path allocates no
//! memory and never calls back into the filesystem or descriptor subsystem.
use crate::block::{AtaDevice, BlockDevice, BlockError, BlockStats, PortBus};
use crate::utils::mutex::SpinMutex;

pub static DISK: SpinMutex<AtaDevice<PortBus>> = SpinMutex::new(AtaDevice::new(
    PortBus::new([0; 9]),
    crate::block::PRIMARY_BASE,
    0,
    false,
));

pub struct DiskView {
    model: [u8; 40],
    model_len: usize,
}
impl DiskView {
    pub fn new() -> Self {
        let disk = DISK.lock();
        let mut model = [0; 40];
        let model_len = disk.model().len().min(model.len());
        model[..model_len].copy_from_slice(&disk.model().as_bytes()[..model_len]);
        Self { model, model_len }
    }
}
impl BlockDevice for DiskView {
    fn sector_size(&self) -> usize {
        512
    }
    fn capacity_sectors(&self) -> usize {
        DISK.lock().capacity_sectors()
    }
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        DISK.lock().read_sector(lba, buf)
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        DISK.lock().write_sector(lba, data)
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        DISK.lock().flush()
    }
    fn test_owned(&self) -> bool {
        DISK.lock().test_owned()
    }
    fn stats(&self) -> BlockStats {
        DISK.lock().stats()
    }
    fn model(&self) -> &str {
        core::str::from_utf8(&self.model[..self.model_len]).unwrap_or("")
    }
}

/// Portable filesystem view: storage errors remain errors, never successful
/// durability barriers. ATA already flushes each sector; the explicit barrier
/// also flushes outstanding writes at each filesystem commit boundary.
pub struct FsDisk;
fn portable(error: BlockError) -> rostifs::block::BlockError {
    // Retain the actual ATA failure in the allocation-free recovery channel;
    // the portable API intentionally abstracts bus-specific status registers.
    use core::fmt::Write;
    let _ = writeln!(
        crate::io::serial::SerialWriter,
        "ROSTI: filesystem block I/O failed: {}",
        error
    );
    use rostifs::block::BlockError as E;
    match error {
        BlockError::OutOfRange => E::OutOfRange,
        BlockError::BufferSizeMismatch => E::BufferSizeMismatch,
        BlockError::Protected => E::Protected,
        _ => E::Rejected,
    }
}
impl rostifs::block::BlockDevice for FsDisk {
    fn sector_size(&self) -> usize {
        512
    }
    fn capacity_sectors(&self) -> usize {
        DISK.lock().capacity_sectors()
    }
    fn read_sector(
        &mut self,
        lba: usize,
        buf: &mut [u8],
    ) -> Result<(), rostifs::block::BlockError> {
        DISK.lock().read_sector(lba, buf).map_err(portable)
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), rostifs::block::BlockError> {
        DISK.lock().write_sector(lba, data).map_err(portable)
    }
    fn flush(&mut self) -> Result<(), rostifs::block::BlockError> {
        DISK.lock().flush().map_err(portable)
    }
    fn test_owned(&self) -> bool {
        DISK.lock().test_owned()
    }
}
