//! Phase 8: bounded block-device layer behind a filesystem-independent interface.
//!
//! Contract (documented in ARCHITECTURE.md):
//! - `BlockDevice` is the only interface the future RostiFS backend will see;
//!   it knows nothing about ATA, ports or the descriptor layer.
//! - 28-bit LBA only (stated limit: LBA48, DMA and interrupt-driven I/O are
//!   NOT claimed). Sector size is fixed at 512 bytes.
//! - Every poll is bounded by `POLL_LIMIT` iterations; missing devices, busy,
//!   error and DRQ states are distinguished with explicit typed errors. No
//!   unbounded waits, no allocation on any block path.
//! - Block work runs only in main context. ISRs must not touch ports, the
//!   port allocator or this subsystem. Lock order: port allocator (acquire
//!   once, then release) -> block device; the block path never re-enters the
//!   port allocator, the heap or the frame allocator.
//! - Persistence is a property of the backend, not of this layer: RAM disks
//!   are volatile test fixtures; only a real device survives reset.

use core::fmt;

pub const SECTOR_SIZE: usize = 512;
/// Stated 28-bit addressing limit. LBA48 is not implemented or claimed.
pub const MAX_LBA_28: usize = (1 << 28) - 1;
/// Finite status-read budget, not a millisecond timeout: virtual port 0x80 is
/// not a real-time delay. 4,000 reads expired before asynchronous writeback
/// flush completion on GRUB/QEMU; retain a hard 100,000-read upper bound.
pub const POLL_LIMIT: usize = 100_000;
/// Stated transfer limit: single-sector operations, at most this many sectors
/// per logical transfer. Multi-sector batching is not implemented or claimed.
pub const MAX_TRANSFER_SECTORS: usize = 64;

// Primary channel ports (secondary channel is base 0x170; ports are base+offset).
pub const PRIMARY_BASE: u16 = 0x1F0;
pub const SECONDARY_BASE: u16 = 0x170;

pub const PORT_DATA: u16 = 0x1F0;
pub const PORT_ERROR: u16 = 0x1F1;
pub const PORT_SECTOR: u16 = 0x1F2;
pub const PORT_LBA_LO: u16 = 0x1F3;
pub const PORT_LBA_MID: u16 = 0x1F4;
pub const PORT_LBA_HI: u16 = 0x1F5;
pub const PORT_DRIVE: u16 = 0x1F6;
pub const PORT_STATUS: u16 = 0x1F7;

// Status register bits (ATA).
pub const STATUS_ERR: u8 = 0x01;
pub const STATUS_DRQ: u8 = 0x08;
pub const STATUS_BSY: u8 = 0x80;
pub const STATUS_DF: u8 = 0x20;

// Commands.
pub const CMD_READ: u8 = 0x20;
pub const CMD_WRITE: u8 = 0x30;
pub const CMD_IDENTIFY: u8 = 0xEC;
pub const CMD_FLUSH: u8 = 0xE7;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BlockError {
    NoDevice,
    Timeout,
    /// Device answered with ERR set; the raw status byte is preserved.
    DeviceError(u8),
    OutOfRange,
    BufferSizeMismatch,
    UnsupportedAddressing,
    /// Write refused: the media is not explicitly test-owned.
    Protected,
}

impl fmt::Display for BlockError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NoDevice => f.write_str("no device"),
            Self::Timeout => f.write_str("poll timeout"),
            Self::DeviceError(s) => write!(f, "device error (status {:#04x})", s),
            Self::OutOfRange => f.write_str("LBA out of range"),
            Self::BufferSizeMismatch => f.write_str("buffer size mismatch"),
            Self::UnsupportedAddressing => f.write_str("unsupported ATA addressing or sector size"),
            Self::Protected => f.write_str("write refused: media not test-owned"),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct BlockStats {
    pub reads: usize,
    pub writes: usize,
    pub timeouts: usize,
    pub device_errors: usize,
    pub no_device: usize,
    pub bytes_transferred: usize,
    pub protected_denials: usize,
}

impl BlockStats {
    pub const fn new() -> Self {
        Self {
            reads: 0,
            writes: 0,
            timeouts: 0,
            device_errors: 0,
            no_device: 0,
            bytes_transferred: 0,
            protected_denials: 0,
        }
    }
}

/// Filesystem-independent block interface. The future RostiFS backend depends
/// only on this trait, never on ATA internals.
pub trait BlockDevice {
    fn sector_size(&self) -> usize;
    fn capacity_sectors(&self) -> usize;
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError>;
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError>;
    fn stats(&self) -> BlockStats;
    /// True only for explicitly test-owned media (sector 0 carries the
    /// documented magic). Writes are refused on any other device.
    fn test_owned(&self) -> bool;
    /// Explicit ordering barrier. Backends without a verified flush operation
    /// must fail rather than advertise durable transactions.
    fn flush(&mut self) -> Result<(), BlockError> {
        Err(BlockError::UnsupportedAddressing)
    }
    fn model(&self) -> &str {
        ""
    }
}

/// Writes are only permitted on explicitly test-owned media. The harness's
/// virtual disk images carry this documented magic at the start of sector 0;
/// a real user disk is refused. This is the safety rule that keeps the
/// diagnostic commands from ever touching host or guest data disks.
pub const TEST_DISK_MAGIC: &[u8] = b"ROSTI-TESTDISK";

pub fn is_test_disk(sector0: &[u8]) -> bool {
    sector0.starts_with(TEST_DISK_MAGIC)
}

/// Deterministic write-verification pattern (sector 1 is the persistence
/// sector; sector 0 carries the ownership magic).
pub const TEST_MARKER: u8 = 0xA5;

pub fn marker_pattern(out: &mut [u8]) {
    for (i, b) in out.iter_mut().enumerate() {
        *b = TEST_MARKER ^ (i as u8);
    }
}

/// Acquire the eight channel ports through the port allocator. The guard must
/// be released before any block operation (lock order: port allocator ->
/// block device; the block path never re-enters the allocator). Ports remain
/// owned by the kernel for its lifetime.
pub fn acquire_channel(alloc: &mut crate::io::ports::PortAllocator, base: u16) -> Option<[u16; 9]> {
    if base != PRIMARY_BASE && base != SECONDARY_BASE {
        return None;
    }
    let mut ports = [0u16; 9];
    for (i, port) in ports[..8].iter_mut().enumerate() {
        *port = base + i as u16;
    }
    ports[8] = base + 0x206;
    if alloc.reserve_permanent(&ports) {
        Some(ports)
    } else {
        None
    }
}

/// Bounded status poll. Pure and host-testable: the caller supplies the read
/// closure (a real port in the kernel, a scripted device in tests).
/// `want == 0` means "ready when neither BSY nor ERR is set"; otherwise the
/// `want` bit must be set. A status of 0 while waiting for a bit means the
/// device is absent (dead bus reads 0).
pub fn poll_status(read: &mut dyn FnMut() -> u8, want: u8, limit: usize) -> Result<u8, BlockError> {
    for _ in 0..limit {
        let status = read();
        if status == 0 || status == 0xff {
            return Err(BlockError::NoDevice);
        }
        if status & STATUS_BSY != 0 {
            continue;
        }
        if status & (STATUS_ERR | STATUS_DF) != 0 {
            return Err(BlockError::DeviceError(status));
        }
        if want == 0 && status & STATUS_DRQ == 0 {
            return Ok(status);
        }
        if status == 0 {
            return Err(BlockError::NoDevice);
        }
        if status & want != 0 {
            return Ok(status);
        }
    }
    Err(BlockError::Timeout)
}

/// 28-bit LBA register encoding for the primary master drive. Checked.
pub fn lba_registers(lba: usize) -> Result<(u8, u8, u8, u8), BlockError> {
    if lba > MAX_LBA_28 {
        return Err(BlockError::OutOfRange);
    }
    Ok((
        (lba & 0xFF) as u8,
        ((lba >> 8) & 0xFF) as u8,
        ((lba >> 16) & 0xFF) as u8,
        0xE0 | ((lba >> 24) & 0x0F) as u8,
    ))
}

/// IDENTIFY model string (words 27..=46, each word's two characters are
/// byte-swapped on the wire). Internal spaces are preserved; trailing padding
/// is trimmed. Writes into a caller-provided buffer; no allocation.
pub fn decode_model(words: &[u16], out: &mut [u8]) -> usize {
    if words.len() < 47 {
        return 0;
    }
    let mut len = 0;
    for w in 27..=46 {
        let hi = ((words[w] >> 8) & 0xFF) as u8;
        let lo = (words[w] & 0xFF) as u8;
        for c in [hi, lo] {
            if c == 0 {
                continue;
            }
            if len < out.len() {
                out[len] = c;
                len += 1;
            }
        }
    }
    while len > 0 && out[len - 1] == b' ' {
        len -= 1;
    }
    len
}

/// Volatile test backend only (host tests and the QEMU harness fixture).
/// Static storage, no allocation; explicitly NOT a persistence claim.
pub const RAM_DISK_SECTORS: usize = 64;
pub struct RamDisk {
    data: [u8; RAM_DISK_SECTORS * SECTOR_SIZE],
    stats: BlockStats,
}

impl RamDisk {
    pub const fn new() -> Self {
        Self {
            data: [0; RAM_DISK_SECTORS * SECTOR_SIZE],
            stats: BlockStats {
                reads: 0,
                writes: 0,
                timeouts: 0,
                device_errors: 0,
                no_device: 0,
                bytes_transferred: 0,
                protected_denials: 0,
            },
        }
    }

    /// Test-owned disk: sector 0 carries the documented magic so the shell
    /// can prove writes are landing on harness media, never a real device.
    pub fn new_test() -> Self {
        let mut d = Self::new();
        d.data[..TEST_DISK_MAGIC.len()].copy_from_slice(TEST_DISK_MAGIC);
        d
    }
}

impl BlockDevice for RamDisk {
    fn sector_size(&self) -> usize {
        SECTOR_SIZE
    }
    fn capacity_sectors(&self) -> usize {
        RAM_DISK_SECTORS
    }
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        if buf.len() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        if lba >= self.capacity_sectors() {
            return Err(BlockError::OutOfRange);
        }
        let start = lba * SECTOR_SIZE;
        buf.copy_from_slice(&self.data[start..start + SECTOR_SIZE]);
        self.stats.reads = self.stats.reads.saturating_add(1);
        self.stats.bytes_transferred = self.stats.bytes_transferred.saturating_add(SECTOR_SIZE);
        Ok(())
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if data.len() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        if lba >= self.capacity_sectors() {
            return Err(BlockError::OutOfRange);
        }
        if !self.test_owned() || lba == 0 {
            self.stats.protected_denials = self.stats.protected_denials.saturating_add(1);
            return Err(BlockError::Protected);
        }
        let start = lba * SECTOR_SIZE;
        self.data[start..start + SECTOR_SIZE].copy_from_slice(data);
        self.stats.writes = self.stats.writes.saturating_add(1);
        self.stats.bytes_transferred = self.stats.bytes_transferred.saturating_add(SECTOR_SIZE);
        Ok(())
    }
    fn stats(&self) -> BlockStats {
        self.stats
    }
    fn test_owned(&self) -> bool {
        is_test_disk(&self.data[..TEST_DISK_MAGIC.len()])
    }
}

/// Port access abstraction so the ATA protocol logic is host-testable against
/// a scripted device before any privileged asm is trusted.
pub trait AtaBus {
    fn inb(&mut self, port: u16) -> u8;
    fn outb(&mut self, port: u16, val: u8);
    /// Transfer one sector (256 words) from the data register into buf.
    fn ins_sector(&mut self, data_port: u16, buf: &mut [u8]) -> Result<(), BlockError>;
    /// Transfer one sector (256 words) from data to the data register.
    fn outs_sector(&mut self, data_port: u16, data: &[u8]) -> Result<(), BlockError>;
    fn io_wait(&mut self);
}

/// Real bus: lockfree port I/O, safe only in main context (never an ISR).
/// Ports must be acquired through the port allocator before constructing this,
/// and the allocator guard must be released before any output formatting.
#[cfg(not(test))]
pub struct PortBus {
    ports: [u16; 9],
}

#[cfg(not(test))]
impl PortBus {
    pub const fn new(ports: [u16; 9]) -> Self {
        Self { ports }
    }
}

#[cfg(not(test))]
impl AtaBus for PortBus {
    fn inb(&mut self, port: u16) -> u8 {
        assert!(self.ports.contains(&port), "ATA port not reserved");
        unsafe { crate::io::ports::lockfree_inb(port) }
    }
    fn outb(&mut self, port: u16, val: u8) {
        assert!(self.ports.contains(&port), "ATA port not reserved");
        unsafe { crate::io::ports::lockfree_outb(port, val) }
    }
    fn ins_sector(&mut self, data_port: u16, buf: &mut [u8]) -> Result<(), BlockError> {
        if buf.len() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        assert_eq!(data_port, self.ports[0], "ATA data port not reserved");
        for i in 0..SECTOR_SIZE / 2 {
            let word = unsafe { crate::io::ports::lockfree_inw(data_port) };
            buf[2 * i] = (word & 0xFF) as u8;
            buf[2 * i + 1] = (word >> 8) as u8;
        }
        Ok(())
    }
    fn outs_sector(&mut self, data_port: u16, data: &[u8]) -> Result<(), BlockError> {
        if data.len() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        assert_eq!(data_port, self.ports[0], "ATA data port not reserved");
        for i in 0..SECTOR_SIZE / 2 {
            let word = u16::from_le_bytes([data[2 * i], data[2 * i + 1]]);
            unsafe { crate::io::ports::lockfree_outw(data_port, word) }
        }
        Ok(())
    }
    fn io_wait(&mut self) {
        unsafe { crate::io::ports::io_wait() }
    }
}

#[cfg(not(test))]
impl AtaDevice<PortBus> {
    /// Attach the ports acquired through the port allocator (guard released
    /// before this is called). Only valid for the real bus.
    pub fn rebind_ports(&mut self, ports: [u16; 9]) {
        self.bus = PortBus::new(ports);
    }
}

pub struct AtaDevice<B: AtaBus> {
    bus: B,
    base: u16,
    drive: u8,
    capacity: usize,
    model: [u8; 40],
    model_len: usize,
    stats: BlockStats,
    /// Set only for explicitly test-owned media (harness-created disk images
    /// carrying the documented magic). The kernel never sets this for real
    /// user disks, so writes are refused on them.
    test_owned: bool,
}

impl<B: AtaBus> AtaDevice<B> {
    pub const fn new(bus: B, base: u16, drive: u8, test_owned: bool) -> Self {
        Self {
            bus,
            base,
            drive,
            capacity: 0,
            model: [0; 40],
            model_len: 0,
            stats: BlockStats::new(),
            test_owned: cfg!(test) && test_owned,
        }
    }

    /// IDENTIFY with a finite timeout. Distinguishes missing devices (status
    /// stays 0), busy, error and DRQ states.
    pub fn identify(bus: B, base: u16, drive: u8, test_owned: bool) -> Result<Self, BlockError> {
        let mut dev = Self::new(bus, base, drive, test_owned);
        dev.probe()?;
        Ok(dev)
    }

    /// Run IDENTIFY on an already-constructed device (boot-time probe).
    pub fn probe(&mut self) -> Result<(), BlockError> {
        if self.drive > 1 {
            return Err(BlockError::OutOfRange);
        }
        self.capacity = 0;
        self.model_len = 0;
        self.test_owned &= cfg!(test);
        let base = self.base;
        let drive = self.drive;
        let bus = &mut self.bus;
        bus.outb(base + 0x206, 0x02); // nIEN: polled PIO, no ATA IRQs
        bus.outb(base + 6, 0xA0 | (drive << 4));
        for _ in 0..4 {
            bus.inb(base + 0x206);
        }
        for offset in 2..=5 {
            bus.outb(base + offset, 0);
        }
        bus.outb(base + 7, CMD_IDENTIFY);
        for _ in 0..4 {
            bus.inb(base + 0x206);
        }
        let status = poll_status(
            &mut || {
                let s = bus.inb(base + 7);
                bus.io_wait();
                s
            },
            STATUS_DRQ,
            POLL_LIMIT,
        )?;
        if bus.inb(base + 4) != 0 || bus.inb(base + 5) != 0 {
            return Err(BlockError::UnsupportedAddressing);
        }
        if status & STATUS_DRQ == 0 {
            return Err(BlockError::NoDevice);
        }
        let mut words = [0u16; 256];
        let mut buf = [0u8; SECTOR_SIZE];
        bus.ins_sector(base, &mut buf)?;
        for i in 0..256 {
            words[i] = u16::from_le_bytes([buf[2 * i], buf[2 * i + 1]]);
        }
        self.delay();
        self.poll_and_count(0)?;
        let capacity = ((words[61] as usize) << 16) | words[60] as usize;
        if words[49] & (1 << 9) == 0
            || capacity == 0
            || capacity > MAX_LBA_28 + 1
            || (words[106] & 0xc000 == 0x4000
                && words[106] & (1 << 12) != 0
                && ((words[118] as u32) << 16 | words[117] as u32) != 256)
        {
            return Err(BlockError::UnsupportedAddressing);
        }
        self.capacity = capacity;
        self.model_len = decode_model(&words, &mut self.model);
        Ok(())
    }

    pub fn model(&self) -> &str {
        core::str::from_utf8(&self.model[..self.model_len]).unwrap_or("")
    }

    /// Read sector 0 and mark the device test-owned only if it carries the
    /// documented harness magic. A real user disk is never writable.
    pub fn probe_test_owned(&mut self) -> bool {
        let mut buf = [0u8; SECTOR_SIZE];
        self.test_owned = self.read_sector(0, &mut buf).is_ok() && is_test_disk(&buf);
        self.test_owned
    }

    /// Test-visible bus handle (host tests assert scripted state through it).
    #[cfg(test)]
    pub fn bus(&self) -> &B {
        &self.bus
    }

    #[cfg(test)]
    pub fn bus_mut(&mut self) -> &mut B {
        &mut self.bus
    }

    fn delay(&mut self) {
        for _ in 0..4 {
            self.bus.inb(self.base + 0x206);
        }
    }

    fn validate_lba(&self, lba: usize) -> Result<(), BlockError> {
        if self.capacity == 0 {
            return Err(BlockError::NoDevice);
        }
        if lba > MAX_LBA_28 || lba >= self.capacity {
            return Err(BlockError::OutOfRange);
        }
        Ok(())
    }

    fn select(&mut self, lba: usize) -> Result<(), BlockError> {
        let (lo, mid, hi, drive) = lba_registers(lba)?;
        self.validate_lba(lba)?;
        self.poll_and_count(0)?;
        self.bus.outb(self.base + 6, drive | (self.drive << 4));
        self.delay();
        self.poll_and_count(0)?;
        self.bus.outb(self.base + 2, 1);
        self.bus.outb(self.base + 3, lo);
        self.bus.outb(self.base + 4, mid);
        self.bus.outb(self.base + 5, hi);
        Ok(())
    }

    fn poll_and_count(&mut self, want: u8) -> Result<(), BlockError> {
        let base = self.base;
        let bus = &mut self.bus;
        match poll_status(
            &mut || {
                let s = bus.inb(base + 7);
                bus.io_wait();
                s
            },
            want,
            POLL_LIMIT,
        ) {
            Ok(_) => Ok(()),
            Err(BlockError::Timeout) => {
                self.stats.timeouts = self.stats.timeouts.saturating_add(1);
                Err(BlockError::Timeout)
            }
            Err(BlockError::DeviceError(s)) => {
                self.stats.device_errors = self.stats.device_errors.saturating_add(1);
                Err(BlockError::DeviceError(s))
            }
            Err(BlockError::NoDevice) => {
                self.stats.no_device = self.stats.no_device.saturating_add(1);
                Err(BlockError::NoDevice)
            }
            Err(e) => Err(e),
        }
    }

    pub fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        if buf.len() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        self.select(lba)?;
        self.bus.outb(self.base + 7, CMD_READ);
        self.delay();
        self.poll_and_count(STATUS_DRQ)?;
        self.bus.ins_sector(self.base, buf)?;
        self.delay();
        self.poll_and_count(0)?;
        self.stats.reads = self.stats.reads.saturating_add(1);
        self.stats.bytes_transferred = self.stats.bytes_transferred.saturating_add(SECTOR_SIZE);
        Ok(())
    }

    pub fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if data.len() != SECTOR_SIZE {
            return Err(BlockError::BufferSizeMismatch);
        }
        self.validate_lba(lba)?;
        if !self.test_owned || lba == 0 {
            self.stats.protected_denials = self.stats.protected_denials.saturating_add(1);
            return Err(BlockError::Protected);
        }
        self.select(lba)?;
        self.bus.outb(self.base + 7, CMD_WRITE);
        self.delay();
        self.poll_and_count(STATUS_DRQ)?;
        self.bus.outs_sector(self.base, data)?;
        self.delay();
        // Success means data phase completed AND volatile drive cache flushed.
        self.poll_and_count(0)?;
        self.bus.outb(self.base + 7, CMD_FLUSH);
        self.delay();
        self.poll_and_count(0)?;
        self.stats.writes = self.stats.writes.saturating_add(1);
        self.stats.bytes_transferred = self.stats.bytes_transferred.saturating_add(SECTOR_SIZE);
        Ok(())
    }

    pub fn stats(&self) -> BlockStats {
        self.stats
    }

    /// Main-context ATA CACHE FLUSH barrier with bounded completion polling.
    pub fn flush(&mut self) -> Result<(), BlockError> {
        self.validate_lba(0)?;
        self.poll_and_count(0)?;
        self.bus.outb(self.base + 7, CMD_FLUSH);
        self.delay();
        self.poll_and_count(0)
    }
}

impl<B: AtaBus> BlockDevice for AtaDevice<B> {
    fn flush(&mut self) -> Result<(), BlockError> {
        AtaDevice::flush(self)
    }
    fn sector_size(&self) -> usize {
        SECTOR_SIZE
    }
    fn capacity_sectors(&self) -> usize {
        self.capacity
    }
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        AtaDevice::read_sector(self, lba, buf)
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        AtaDevice::write_sector(self, lba, data)
    }
    fn stats(&self) -> BlockStats {
        self.stats
    }
    fn test_owned(&self) -> bool {
        self.test_owned
    }
    fn model(&self) -> &str {
        self.model()
    }
}

#[cfg(test)]
mod counter_tests {
    use super::*;

    #[test]
    fn long_lived_transfer_counters_saturate_instead_of_panicking() {
        let mut disk = RamDisk::new_test();
        disk.stats.reads = usize::MAX;
        disk.stats.writes = usize::MAX;
        disk.stats.bytes_transferred = usize::MAX - 1;
        disk.stats.protected_denials = usize::MAX;
        disk.read_sector(1, &mut [0; 512]).unwrap();
        disk.write_sector(1, &[0x5a; 512]).unwrap();
        assert_eq!(disk.write_sector(0, &[0; 512]), Err(BlockError::Protected));
        assert_eq!(disk.stats.reads, usize::MAX);
        assert_eq!(disk.stats.writes, usize::MAX);
        assert_eq!(disk.stats.bytes_transferred, usize::MAX);
        assert_eq!(disk.stats.protected_denials, usize::MAX);
    }
}
