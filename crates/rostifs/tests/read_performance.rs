//! Real portable-core reads on a counted RAM device. Host time is not ATA latency.
#![cfg(feature = "host-tools")]
use rostifs::{
    block::{BlockDevice, BlockError},
    engine::RostiFs,
    vfs::{FsError, NodeId, Vfs},
};
use std::{cell::Cell, rc::Rc, time::Instant};

#[derive(Default)]
struct Counts {
    reads: Cell<usize>,
    writes: Cell<usize>,
    flushes: Cell<usize>,
    fail_read: Cell<Option<usize>>,
    sector_override: Cell<Option<usize>>,
    capacity_override: Cell<Option<usize>>,
}
struct Disk {
    bytes: Vec<u8>,
    counts: Rc<Counts>,
}
impl BlockDevice for Disk {
    fn sector_size(&self) -> usize {
        self.counts.sector_override.get().unwrap_or(512)
    }
    fn capacity_sectors(&self) -> usize {
        self.counts
            .capacity_override
            .get()
            .unwrap_or(self.bytes.len() / 512)
    }
    fn test_owned(&self) -> bool {
        true
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        self.counts.flushes.set(self.counts.flushes.get() + 1);
        Ok(()) // Volatile RAM model, never a production implementation.
    }
    fn read_sector(&mut self, lba: usize, out: &mut [u8]) -> Result<(), BlockError> {
        let call = self.counts.reads.get();
        self.counts.reads.set(call + 1);
        if self.counts.fail_read.get() == Some(call) {
            return Err(BlockError::Rejected);
        }
        if out.len() != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        let start = lba.checked_mul(512).ok_or(BlockError::OutOfRange)?;
        let end = start.checked_add(512).ok_or(BlockError::OutOfRange)?;
        out.copy_from_slice(self.bytes.get(start..end).ok_or(BlockError::OutOfRange)?);
        Ok(())
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if data.len() != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        if lba < 8 {
            return Err(BlockError::Protected);
        }
        let start = lba.checked_mul(512).ok_or(BlockError::OutOfRange)?;
        let end = start.checked_add(512).ok_or(BlockError::OutOfRange)?;
        self.bytes
            .get_mut(start..end)
            .ok_or(BlockError::OutOfRange)?
            .copy_from_slice(data);
        self.counts.writes.set(self.counts.writes.get() + 1);
        Ok(())
    }
}
fn fixture() -> (Disk, Rc<Counts>, Vec<u8>) {
    let counts = Rc::new(Counts::default());
    let mut disk = Disk {
        bytes: vec![0; 128 * 4096],
        counts: counts.clone(),
    };
    RostiFs::format(&mut disk, 0x95b).unwrap();
    let data: Vec<u8> = (0..8193).map(|i| (i % 251) as u8).collect();
    {
        let mut fs = RostiFs::mount(&mut disk).unwrap();
        let id = fs.create_file(NodeId::ROOT, "sample").unwrap();
        fs.replace(id, &data).unwrap();
    }
    (disk, counts, data)
}

#[test]
fn read_boundaries_eof_and_device_errors() {
    let (mut disk, counts, data) = fixture();
    let fs = RostiFs::mount(&mut disk).unwrap();
    let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
    for offset in [0, 1, 510, 511, 512, 513, 4095, 4096, 8192, 8193, usize::MAX] {
        for size in [0, 1, 64, 128, 512, 513, 4096, 8194] {
            let mut out = vec![0xa5; size];
            let count = size.min(data.len().saturating_sub(offset));
            let got = fs.read(id, offset, &mut out).unwrap();
            assert_eq!(got, count);
            if count > 0 {
                assert_eq!(&out[..got], &data[offset..offset + got]);
            }
            assert!(out[got..].iter().all(|&x| x == 0xa5));
        }
    }
    counts.reads.set(0);
    counts.fail_read.set(Some(0));
    assert_eq!(fs.read(id, 0, &mut [0; 64]), Err(FsError::DeviceIo));
    counts.fail_read.set(None);
    assert_eq!(fs.read(id, 0, &mut [0; 64]), Ok(64));
    counts.reads.set(0);
    counts.fail_read.set(Some(1));
    assert_eq!(fs.read(id, 511, &mut [0; 2]), Err(FsError::DeviceIo));
}

#[test]
fn read_transfers_only_intersecting_sectors() {
    let (mut disk, counts, data) = fixture();
    let fs = RostiFs::mount(&mut disk).unwrap();
    let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
    for (offset, size, sectors) in [
        (0, 64, 1),
        (511, 2, 2),
        (4095, 2, 2),
        (0, 4096, 8),
        (8192, 100, 1),
        (8193, 1, 0),
        (usize::MAX, 1, 0),
    ] {
        counts.reads.set(0);
        counts.writes.set(0);
        counts.flushes.set(0);
        let mut out = vec![0; size];
        let got = fs.read(id, offset, &mut out).unwrap();
        if got != 0 {
            assert_eq!(&out[..got], &data[offset..offset + got]);
        }
        assert_eq!(counts.reads.get(), sectors, "offset={offset} size={size}");
        assert_eq!(counts.writes.get(), 0);
        assert_eq!(counts.flushes.get(), 0);
    }
}

#[test]
fn changed_geometry_is_rejected_before_read_io() {
    let (mut disk, counts, _) = fixture();
    let fs = RostiFs::mount(&mut disk).unwrap();
    let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
    counts.reads.set(0);
    counts.sector_override.set(Some(1024));
    for size in [64, 4096] {
        assert_eq!(fs.read(id, 0, &mut vec![0; size]), Err(FsError::DeviceIo));
        assert_eq!(counts.reads.get(), 0);
    }
    counts.sector_override.set(None);
    counts.capacity_override.set(Some(8));
    for size in [64, 4096] {
        assert_eq!(fs.read(id, 0, &mut vec![0; size]), Err(FsError::DeviceIo));
        assert_eq!(counts.reads.get(), 0);
    }
    counts.capacity_override.set(None);
    assert_eq!(fs.read(id, 0, &mut [0; 64]), Ok(64));
}

#[test]
fn every_mixed_read_sector_failure_releases_borrows_and_recovers() {
    let (mut disk, counts, data) = fixture();
    let fs = RostiFs::mount(&mut disk).unwrap();
    let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
    // Partial prefix, complete aligned block and final partial sector.
    // Caller buffers may contain an already copied prefix after DeviceIo.
    let mut out = vec![0; data.len() - 511];
    for failure in 0..17 {
        counts.reads.set(0);
        counts.fail_read.set(Some(failure));
        assert_eq!(fs.read(id, 511, &mut out), Err(FsError::DeviceIo));
        assert_eq!(counts.reads.get(), failure + 1);
        counts.fail_read.set(None);
        assert_eq!(fs.read(id, 511, &mut out), Ok(out.len()));
        assert_eq!(&out, &data[511..]);
    }
}

#[test]
#[ignore = "explicit serial host microbenchmark, not a correctness gate"]
fn measured_read_workloads() {
    let (mut disk, counts, data) = fixture();
    let fs = RostiFs::mount(&mut disk).unwrap();
    let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
    for size in [64, 128, 512, 4096] {
        let mut out = vec![0; size];
        // Warm-up is identical for every candidate and excluded from samples.
        for _ in 0..100 {
            fs.read(id, 0, &mut out).unwrap();
        }
        for sample in 0..9 {
            counts.reads.set(0);
            counts.writes.set(0);
            counts.flushes.set(0);
            let start = Instant::now();
            for _ in 0..2000 {
                assert_eq!(
                    fs.read(id, 0, std::hint::black_box(&mut out)).unwrap(),
                    size
                );
                std::hint::black_box(&out);
            }
            let ns = start.elapsed().as_nanos();
            assert_eq!(&out, &data[..size]);
            println!(
                "ROSTI_PERF {{\"size\":{size},\"sample\":{sample},\"operations\":2000,\"host_ns\":{ns},\"reads\":{},\"writes\":{},\"flushes\":{}}}",
                counts.reads.get(),
                counts.writes.get(),
                counts.flushes.get()
            );
        }
    }
}
