//! Scripted bus executes the actual ATA state machine without privileged I/O.
use crate::block::*;
use std::collections::VecDeque;

struct FakeBus {
    words: [u16; 256],
    sector: [u8; SECTOR_SIZE],
    events: Vec<(char, u16, u8)>,
    status: u8,
    command_status: u8,
    completion_status: u8,
    flush_status: u8,
    flush_busy_polls: usize,
    command: u8,
    script: VecDeque<u8>,
    signature: u8,
}
impl FakeBus {
    fn new(capacity: u32, model: &str) -> Self {
        let mut words = [0; 256];
        words[49] = 1 << 9;
        words[60] = capacity as u16;
        words[61] = (capacity >> 16) as u16;
        let mut padded = [b' '; 40];
        padded[..model.len()].copy_from_slice(model.as_bytes());
        for i in 0..20 {
            words[27 + i] = u16::from_be_bytes([padded[i * 2], padded[i * 2 + 1]]);
        }
        Self {
            words,
            sector: [0; SECTOR_SIZE],
            events: Vec::new(),
            status: 0x40,
            command_status: STATUS_DRQ,
            completion_status: 0x40,
            flush_status: 0x40,
            flush_busy_polls: 0,
            command: 0,
            script: VecDeque::new(),
            signature: 0,
        }
    }
    fn writes(&self) -> Vec<(u16, u8)> {
        self.events
            .iter()
            .filter(|e| e.0 == 'w')
            .map(|e| (e.1, e.2))
            .collect()
    }
}
impl AtaBus for FakeBus {
    fn inb(&mut self, port: u16) -> u8 {
        self.events.push(('r', port, 0));
        if port == PORT_STATUS {
            self.script.pop_front().unwrap_or(self.status)
        } else if port == PORT_LBA_MID {
            self.signature
        } else {
            0
        }
    }
    fn outb(&mut self, port: u16, val: u8) {
        self.events.push(('w', port, val));
        if port == PORT_STATUS {
            self.command = val;
            if val == CMD_FLUSH && self.flush_busy_polls != 0 {
                self.script
                    .extend(std::iter::repeat_n(STATUS_BSY, self.flush_busy_polls));
                self.script.push_back(self.flush_status);
            }
            self.status = if val == CMD_FLUSH {
                self.flush_status
            } else {
                self.command_status
            };
        }
    }
    fn ins_sector(&mut self, _: u16, buf: &mut [u8]) -> Result<(), BlockError> {
        if self.command == CMD_IDENTIFY {
            for (i, w) in self.words.iter().enumerate() {
                buf[2 * i..2 * i + 2].copy_from_slice(&w.to_le_bytes());
            }
        } else {
            buf.copy_from_slice(&self.sector);
        }
        self.status = self.completion_status;
        Ok(())
    }
    fn outs_sector(&mut self, _: u16, data: &[u8]) -> Result<(), BlockError> {
        self.sector.copy_from_slice(data);
        self.status = self.completion_status;
        Ok(())
    }
    fn io_wait(&mut self) {
        self.events.push(('d', 0, 0));
    }
}
fn device(owned: bool) -> AtaDevice<FakeBus> {
    AtaDevice::identify(FakeBus::new(8, "QEMU HARDDISK"), PRIMARY_BASE, 0, owned).unwrap()
}
#[test]
fn protocol_drq_is_bit_three_not_ready_bit_six() {
    assert_eq!(STATUS_DRQ, 0x08);
    assert_eq!(
        poll_status(&mut || 0x40, STATUS_DRQ, 3),
        Err(BlockError::Timeout)
    );
}
#[test]
fn identify_reads_capacity_and_model() {
    let d = AtaDevice::identify(
        FakeBus::new(65552, "1234567890123456789012345678901234567890"),
        PRIMARY_BASE,
        0,
        false,
    )
    .unwrap();
    assert_eq!(d.capacity_sectors(), 65552);
    assert_eq!(d.model(), "1234567890123456789012345678901234567890");
    assert_eq!(d.sector_size(), 512);
    assert!(!d.test_owned());
}
#[test]
fn unsupported_addressing_is_rejected() {
    for (cap, lba) in [(0, true), (8, false), (0x10000001, true)] {
        let mut b = FakeBus::new(cap, "X");
        if !lba {
            b.words[49] = 0;
        }
        assert_eq!(
            AtaDevice::identify(b, PRIMARY_BASE, 0, false).err(),
            Some(BlockError::UnsupportedAddressing)
        );
    }
}
#[test]
fn non_512_logical_sectors_are_rejected() {
    let mut b = FakeBus::new(8, "X");
    b.words[106] = 0x5000;
    b.words[117] = 2048;
    assert_eq!(
        AtaDevice::identify(b, PRIMARY_BASE, 0, false).err(),
        Some(BlockError::UnsupportedAddressing)
    );
}
#[test]
fn atapi_signature_is_rejected() {
    let mut b = FakeBus::new(8, "X");
    b.signature = 0x14;
    assert_eq!(
        AtaDevice::identify(b, PRIMARY_BASE, 0, false).err(),
        Some(BlockError::UnsupportedAddressing)
    );
}
#[test]
fn identify_missing_device_status_zero() {
    for status in [0, 0xff] {
        let mut b = FakeBus::new(8, "X");
        b.command_status = status;
        assert_eq!(
            AtaDevice::identify(b, PRIMARY_BASE, 0, false).err(),
            Some(BlockError::NoDevice)
        );
    }
}
#[test]
fn identify_busy_then_error_is_device_error() {
    let mut b = FakeBus::new(8, "X");
    b.script = VecDeque::from([STATUS_BSY | STATUS_ERR, STATUS_ERR]);
    assert_eq!(
        AtaDevice::identify(b, PRIMARY_BASE, 0, false).err(),
        Some(BlockError::DeviceError(STATUS_ERR))
    );
}
#[test]
fn identify_poll_is_bounded() {
    let mut b = FakeBus::new(8, "X");
    b.command_status = STATUS_BSY;
    assert_eq!(
        AtaDevice::identify(b, PRIMARY_BASE, 0, false).err(),
        Some(BlockError::Timeout)
    );
}
#[test]
fn floating_bus_and_device_fault_are_not_ready() {
    for want in [0, STATUS_DRQ] {
        for status in [0, 0xff] {
            assert_eq!(
                poll_status(&mut || status, want, 3),
                Err(BlockError::NoDevice)
            );
        }
        assert_eq!(
            poll_status(&mut || STATUS_DF, want, 3),
            Err(BlockError::DeviceError(STATUS_DF))
        );
    }
    assert_eq!(
        poll_status(&mut || STATUS_DRQ, 0, 3),
        Err(BlockError::Timeout)
    );
}
#[test]
fn slave_select_uses_bit_four() {
    let mut d = AtaDevice::identify(FakeBus::new(8, "X"), PRIMARY_BASE, 1, false).unwrap();
    assert!(d.bus().writes().contains(&(PORT_DRIVE, 0xb0)));
    d.read_sector(1, &mut [0; 512]).unwrap();
    assert!(d.bus().writes().contains(&(PORT_DRIVE, 0xf0)));
}
#[test]
fn select_and_command_have_four_alternate_status_reads() {
    let mut d = device(true);
    d.read_sector(1, &mut [0; 512]).unwrap();
    d.write_sector(1, &[0; 512]).unwrap();
    let es = &d.bus().events;
    for (i, e) in es.iter().enumerate() {
        if e.0 == 'w' && (e.1 == PORT_DRIVE || e.1 == PORT_STATUS) {
            assert!(es[i + 1..i + 5].iter().all(|e| *e == ('r', 0x3f6, 0)));
        }
    }
    assert!(d.bus().writes().contains(&(0x3f6, 2)));
    assert!(es.iter().any(|e| e.0 == 'd'));
}
#[test]
fn lba_encoding_and_bounds() {
    assert_eq!(lba_registers(0), Ok((0, 0, 0, 0xe0)));
    assert_eq!(lba_registers(0x1234567), Ok((0x67, 0x45, 0x23, 0xe1)));
    assert_eq!(lba_registers(MAX_LBA_28), Ok((255, 255, 255, 0xef)));
    assert_eq!(lba_registers(MAX_LBA_28 + 1), Err(BlockError::OutOfRange));
}
#[test]
fn ramdisk_roundtrip_and_bounds() {
    let mut d = RamDisk::new_test();
    let mut pattern = [0; 512];
    marker_pattern(&mut pattern);
    d.write_sector(63, &pattern).unwrap();
    let mut out = [0; 512];
    d.read_sector(63, &mut out).unwrap();
    assert_eq!(pattern, out);
    assert_eq!(d.read_sector(64, &mut out), Err(BlockError::OutOfRange));
    assert_eq!(
        d.read_sector(0, &mut [0; 4]),
        Err(BlockError::BufferSizeMismatch)
    );
    assert_eq!(d.stats().bytes_transferred, 1024);
}
#[test]
fn writes_are_refused_without_test_ownership() {
    let mut d = RamDisk::new();
    assert_eq!(d.write_sector(1, &[0; 512]), Err(BlockError::Protected));
    assert_eq!(d.stats().protected_denials, 1);
    let mut d = device(false);
    assert_eq!(d.write_sector(1, &[0; 512]), Err(BlockError::Protected));
    assert_eq!(d.stats().writes, 0);
    d.read_sector(1, &mut [0; 512]).unwrap();
}
#[test]
fn write_denials_do_not_touch_bus_and_sector_zero_is_reserved() {
    for owned in [true, false] {
        let mut d = device(owned);
        let before = d.bus().events.len();
        assert_eq!(
            d.write_sector(if owned { 0 } else { 1 }, &[0; 512]),
            Err(BlockError::Protected)
        );
        assert_eq!(d.bus().events.len(), before);
    }
    let mut d = RamDisk::new_test();
    assert_eq!(d.write_sector(0, &[0; 512]), Err(BlockError::Protected));
    assert!(d.test_owned());
}
#[test]
fn ata_read_polls_drq_then_transfers() {
    let mut d = device(false);
    let mut pattern = [0; 512];
    marker_pattern(&mut pattern);
    d.bus_mut().sector = pattern;
    let mut out = [0; 512];
    d.read_sector(7, &mut out).unwrap();
    assert_eq!(out, pattern);
    assert_eq!(d.stats().reads, 1);
}
#[test]
fn ata_read_timeout_counts_and_device_stays_usable() {
    let mut d = device(false);
    d.bus_mut().command_status = STATUS_BSY;
    assert_eq!(d.read_sector(1, &mut [0; 512]), Err(BlockError::Timeout));
    assert_eq!(d.stats().timeouts, 1);
    d.bus_mut().status = 0x40;
    d.bus_mut().command_status = STATUS_DRQ;
    d.read_sector(1, &mut [0; 512]).unwrap();
}
#[test]
fn writes_flush_cache_before_success() {
    let mut d = device(true);
    d.write_sector(1, &[0x42; 512]).unwrap();
    assert_eq!(d.bus().sector, [0x42; 512]);
    let cmds: Vec<_> = d
        .bus()
        .writes()
        .iter()
        .filter(|(p, _)| *p == PORT_STATUS)
        .map(|(_, v)| *v)
        .collect();
    assert_eq!(cmds, vec![CMD_IDENTIFY, CMD_WRITE, CMD_FLUSH]);
    assert_eq!(d.stats().writes, 1);
}
#[test]
fn explicit_flush_barrier_issues_command_and_reports_failure() {
    let mut d = device(true);
    BlockDevice::flush(&mut d).unwrap();
    assert!(d.bus().writes().contains(&(PORT_STATUS, CMD_FLUSH)));
    d.bus_mut().flush_status = STATUS_ERR;
    assert_eq!(
        BlockDevice::flush(&mut d),
        Err(BlockError::DeviceError(STATUS_ERR))
    );
    assert_eq!(d.stats().writes, 0);
    let mut unprobed = AtaDevice::new(FakeBus::new(8, "X"), PRIMARY_BASE, 0, false);
    assert_eq!(BlockDevice::flush(&mut unprobed), Err(BlockError::NoDevice));
    assert!(unprobed.bus().events.is_empty());
    assert_eq!(
        BlockDevice::flush(&mut RamDisk::new()),
        Err(BlockError::UnsupportedAddressing)
    );
}
#[test]
fn asynchronous_flush_can_exceed_old_poll_budget_but_is_still_bounded() {
    let mut d = device(true);
    d.bus_mut().flush_busy_polls = 8192;
    BlockDevice::flush(&mut d).unwrap();
    assert!(d.bus().script.is_empty());
    d.write_sector(1, &[0x55; 512]).unwrap();
    assert_eq!(d.stats().writes, 1);
    assert_eq!(d.stats().timeouts, 0);
    d.bus_mut().flush_status = STATUS_BSY;
    assert_eq!(BlockDevice::flush(&mut d), Err(BlockError::Timeout));
    assert_eq!(d.stats().timeouts, 1);
    assert!(POLL_LIMIT <= 100_000);
}
#[test]
fn completion_drq_or_fault_prevents_success_and_flush() {
    for status in [STATUS_DRQ, STATUS_DF, STATUS_ERR] {
        for write in [true, false] {
            let mut d = device(true);
            d.bus_mut().completion_status = status;
            let result = if write {
                d.write_sector(1, &[0; 512])
            } else {
                d.read_sector(1, &mut [0; 512])
            };
            assert_eq!(
                result,
                Err(if status == STATUS_DRQ {
                    BlockError::Timeout
                } else {
                    BlockError::DeviceError(status)
                })
            );
            assert_eq!(d.stats().reads + d.stats().writes, 0);
            assert!(!d.bus().writes().contains(&(PORT_STATUS, CMD_FLUSH)));
        }
    }
}
#[test]
fn flush_failure_is_reported_without_success_counter() {
    let mut d = device(true);
    d.bus_mut().flush_status = STATUS_ERR;
    assert_eq!(
        d.write_sector(1, &[0; 512]),
        Err(BlockError::DeviceError(STATUS_ERR))
    );
    assert_eq!(d.stats().writes, 0);
    assert_eq!(d.stats().device_errors, 1);
}
#[test]
fn out_of_range_and_buffer_errors_do_not_touch_bus() {
    let mut d = device(true);
    let before = d.bus().events.len();
    for lba in [8, MAX_LBA_28 + 1, usize::MAX] {
        assert_eq!(
            d.read_sector(lba, &mut [0; 512]),
            Err(BlockError::OutOfRange)
        );
        assert_eq!(d.write_sector(lba, &[0; 512]), Err(BlockError::OutOfRange));
    }
    assert_eq!(
        d.write_sector(1, &[0; 4]),
        Err(BlockError::BufferSizeMismatch)
    );
    assert_eq!(d.bus().events.len(), before);
}
#[test]
fn ownership_probe_revokes_on_missing_magic_or_failed_read() {
    let mut d = device(true);
    assert!(!d.probe_test_owned());
    d.bus_mut().sector[..TEST_DISK_MAGIC.len()].copy_from_slice(TEST_DISK_MAGIC);
    assert!(d.probe_test_owned());
    d.bus_mut().command_status = STATUS_ERR;
    assert!(!d.probe_test_owned());
}
#[test]
fn channel_reservation_failure_is_atomic() {
    for conflict in [PRIMARY_BASE + 3, 0x3f6] {
        let mut alloc = Box::new(crate::io::ports::PortAllocator::new());
        let p = alloc.allocate(conflict).unwrap();
        assert!(acquire_channel(&mut alloc, PRIMARY_BASE).is_none());
        assert!(alloc.allocate(PRIMARY_BASE).is_some());
        drop(p);
        assert!(acquire_channel(&mut alloc, PRIMARY_BASE).is_some());
        assert!(acquire_channel(&mut alloc, PRIMARY_BASE).is_none());
    }
    let mut alloc = Box::new(crate::io::ports::PortAllocator::new());
    assert_eq!(
        acquire_channel(&mut alloc, SECONDARY_BASE).unwrap()[8],
        0x376
    );
    assert!(acquire_channel(&mut alloc, 0xffff).is_none());
    assert!(!alloc.reserve_permanent(&[1, 1]));
    assert!(alloc.allocate(1).is_some());
}
#[test]
fn block_layer_is_bounded_and_unprobed_device_has_no_bus_access() {
    assert!(core::mem::size_of::<RamDisk>() <= 32768 + 128);
    assert!(POLL_LIMIT <= 100000);
    assert!(MAX_TRANSFER_SECTORS <= 64);
    let mut d = AtaDevice::new(FakeBus::new(8, "X"), PRIMARY_BASE, 0, false);
    assert_eq!(d.read_sector(0, &mut [0; 512]), Err(BlockError::NoDevice));
    assert!(d.bus().events.is_empty());
}
