//! Counted volatile-RAM COW workloads; not physical disk or guest throughput.
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
}
impl Counts {
    fn reset(&self) {
        self.reads.set(0);
        self.writes.set(0);
        self.flushes.set(0);
    }
}
struct Disk {
    bytes: Vec<u8>,
    counts: Rc<Counts>,
}
impl BlockDevice for Disk {
    fn sector_size(&self) -> usize {
        512
    }
    fn capacity_sectors(&self) -> usize {
        self.bytes.len() / 512
    }
    fn test_owned(&self) -> bool {
        true
    }
    fn read_sector(&mut self, lba: usize, out: &mut [u8]) -> Result<(), BlockError> {
        let call = self.counts.reads.get();
        self.counts.reads.set(call + 1);
        if self.counts.fail_read.get() == Some(call) {
            return Err(BlockError::Rejected);
        }
        out.copy_from_slice(
            self.bytes
                .get(lba * 512..(lba + 1) * 512)
                .ok_or(BlockError::OutOfRange)?,
        );
        Ok(())
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if lba < 8 {
            return Err(BlockError::Protected);
        }
        self.bytes
            .get_mut(lba * 512..(lba + 1) * 512)
            .ok_or(BlockError::OutOfRange)?
            .copy_from_slice(data);
        self.counts.writes.set(self.counts.writes.get() + 1);
        Ok(())
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        self.counts.flushes.set(self.counts.flushes.get() + 1);
        Ok(())
    }
}
fn fixture() -> (Disk, Rc<Counts>, Vec<u8>) {
    let counts = Rc::new(Counts::default());
    let mut disk = Disk {
        bytes: vec![0; 128 * 4096],
        counts: counts.clone(),
    };
    RostiFs::format(&mut disk, 0xc02).unwrap();
    let data: Vec<u8> = (0..8193).map(|i| (i % 251) as u8).collect();
    {
        let mut fs = RostiFs::mount(&mut disk).unwrap();
        let id = fs.create_file(NodeId::ROOT, "sample").unwrap();
        fs.replace(id, &data).unwrap();
    }
    (disk, counts, data)
}

#[test]
fn fully_supplied_old_bytes_need_no_preservation_read() {
    for (offset, size, reads) in [
        (0, 8193, 0),
        (0, 4096, 16),
        (4096, 4097, 8),
        (8192, 1, 16),
        (1, 8192, 8),
        (4095, 2, 24),
        (8193, 4, 24),
        (9000, 4, 24),
    ] {
        let (mut disk, counts, mut expected) = fixture();
        let payload = vec![0xe3; size];
        {
            let mut fs = RostiFs::mount(&mut disk).unwrap();
            let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
            counts.reset();
            assert_eq!(fs.write(id, offset, &payload), Ok(size));
            assert_eq!(counts.reads.get(), reads, "offset={offset} size={size}");
            assert_eq!(counts.writes.get(), 48);
            assert_eq!(counts.flushes.get(), 3);
        }
        expected.resize(expected.len().max(offset + size), 0);
        expected[offset..offset + size].copy_from_slice(&payload);
        let fs = RostiFs::mount(&mut disk).unwrap(); // validates both roots and complete padded CRCs
        let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
        let mut out = vec![0; expected.len()];
        assert_eq!(fs.read(id, 0, &mut out), Ok(out.len()));
        assert_eq!(out, expected);
    }
}

#[test]
fn every_required_preservation_read_failure_keeps_old_tree() {
    // First block wholly supplied; second/third blocks must be preserved.
    for fail in 0..16 {
        let (mut disk, counts, expected) = fixture();
        {
            let mut fs = RostiFs::mount(&mut disk).unwrap();
            let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
            counts.reset();
            counts.fail_read.set(Some(fail));
            assert_eq!(fs.write(id, 0, &[0xee; 4096]), Err(FsError::DeviceIo));
            counts.fail_read.set(None);
            let mut out = vec![0; expected.len()];
            assert_eq!(fs.read(id, 0, &mut out), Ok(out.len()));
            assert_eq!(out, expected);
            // The supplied first COW block was already written: do not allow
            // another mutation until remount resolves the ambiguous I/O state.
            assert_eq!(fs.write(id, 0, b"retry"), Err(FsError::DeviceIo));
        }
        let fs = RostiFs::mount(&mut disk).unwrap();
        let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
        let mut out = vec![0; expected.len()];
        assert_eq!(fs.read(id, 0, &mut out), Ok(out.len()));
        assert_eq!(out, expected);
    }
}

#[test]
fn truncate_preserves_prefix_and_zeroes_reextended_tail() {
    let (mut disk, counts, data) = fixture();
    {
        let mut fs = RostiFs::mount(&mut disk).unwrap();
        let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
        fs.truncate(id, 4097).unwrap();
        counts.reset();
        fs.truncate(id, 8193).unwrap();
        assert_eq!(counts.reads.get(), 16);
    }
    let fs = RostiFs::mount(&mut disk).unwrap();
    let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
    let mut out = vec![0; 8193];
    fs.read(id, 0, &mut out).unwrap();
    assert_eq!(&out[..4097], &data[..4097]);
    assert!(out[4097..].iter().all(|&b| b == 0));
}

#[test]
#[ignore]
fn measured_preservation_workloads() {
    for (name, offset, size) in [
        ("full", 0, 8193),
        ("first_block", 0, 4096),
        ("unaligned", 1, 8192),
        ("partial", 4095, 2),
    ] {
        let (mut disk, counts, _) = fixture();
        let mut fs = RostiFs::mount(&mut disk).unwrap();
        let id = fs.lookup(NodeId::ROOT, "sample").unwrap();
        let payload = vec![0xe3; size];
        for _ in 0..10 {
            fs.write(id, offset, &payload).unwrap();
        }
        for sample in 0..9 {
            counts.reset();
            let start = Instant::now();
            for _ in 0..100 {
                fs.write(id, offset, &payload).unwrap();
            }
            let ns = start.elapsed().as_nanos();
            println!(
                "C02 name={name} sample={sample} ops=100 ns={ns} reads={} writes={} flushes={}",
                counts.reads.get(),
                counts.writes.get(),
                counts.flushes.get()
            );
            assert_eq!(counts.writes.get(), 4800);
            assert_eq!(counts.flushes.get(), 300);
        }
    }
}
