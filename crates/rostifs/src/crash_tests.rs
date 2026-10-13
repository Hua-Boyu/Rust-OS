extern crate std;
include!("additional_tests.rs");
use crate::{block::*, engine::RostiFs, format::*, vfs::*};
use std::{
    format,
    string::{String, ToString},
    vec,
    vec::Vec,
};
#[derive(Clone, Debug)]
enum Event {
    Write(usize, [u8; 512]),
    Flush,
}
#[derive(Clone)]
struct Disk {
    durable: Vec<u8>,
    live: Vec<u8>,
    pending: Vec<(usize, [u8; 512])>,
    events: Vec<Event>,
    fail: Option<(usize, usize)>,
    owned: bool,
    sector: usize,
    fail_read: Option<usize>,
}
impl Disk {
    fn blank(blocks: usize) -> Self {
        let mut bytes = vec![0; blocks * 4096];
        bytes[..14].copy_from_slice(b"ROSTI-TESTDISK");
        Self {
            durable: bytes.clone(),
            live: bytes,
            pending: vec![],
            events: vec![],
            fail: None,
            owned: true,
            sector: 512,
            fail_read: None,
        }
    }
    fn crash(&mut self) {
        self.live = self.durable.clone();
        self.pending.clear();
        self.fail = None;
        self.events.clear();
    }
    fn checkpoint(&mut self) {
        self.events.clear();
    }
    fn fault(&mut self) -> Option<usize> {
        let n = self.events.len();
        self.fail
            .and_then(|(at, tear)| if at == n { Some(tear) } else { None })
    }
}
impl BlockDevice for Disk {
    fn sector_size(&self) -> usize {
        self.sector
    }
    fn capacity_sectors(&self) -> usize {
        self.live.len() / 512
    }
    fn test_owned(&self) -> bool {
        self.owned
    }
    fn read_sector(&mut self, lba: usize, out: &mut [u8]) -> Result<(), BlockError> {
        if self.fail_read == Some(lba) {
            return Err(BlockError::Rejected);
        }
        if out.len() != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        let raw = self
            .live
            .get(lba * 512..(lba + 1) * 512)
            .ok_or(BlockError::OutOfRange)?;
        out.copy_from_slice(raw);
        Ok(())
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if !self.owned {
            return Err(BlockError::Protected);
        }
        if data.len() != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        if let Some(tear) = self.fault() {
            let take = tear.min(512);
            self.durable[lba * 512..lba * 512 + take].copy_from_slice(&data[..take]);
            return Err(if take == 0 {
                BlockError::Rejected
            } else {
                BlockError::Torn
            });
        }
        let mut raw = [0; 512];
        raw.copy_from_slice(data);
        self.live[lba * 512..(lba + 1) * 512].copy_from_slice(data);
        self.pending.push((lba, raw));
        self.events.push(Event::Write(lba, raw));
        Ok(())
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        if self.fault().is_some() {
            return Err(BlockError::Rejected);
        }
        for (lba, raw) in self.pending.drain(..) {
            self.durable[lba * 512..(lba + 1) * 512].copy_from_slice(&raw);
        }
        self.events.push(Event::Flush);
        Ok(())
    }
}
fn fresh(blocks: usize) -> Disk {
    let mut d = Disk::blank(blocks);
    RostiFs::format(&mut d, 0x123456789abcdef0).unwrap();
    d.checkpoint();
    d
}
fn contents(fs: &RostiFs<'_>, id: NodeId) -> Vec<u8> {
    let mut out = vec![0; fs.metadata(id).unwrap().size];
    assert_eq!(fs.read(id, 0, &mut out).unwrap(), out.len());
    out
}
fn snapshot(fs: &RostiFs<'_>) -> Vec<(String, NodeKind, Vec<u8>)> {
    fn walk(fs: &RostiFs<'_>, id: NodeId, v: &mut Vec<(String, NodeKind, Vec<u8>)>) {
        let mut p = [0; 256];
        let len = fs.path(id, &mut p).unwrap();
        let kind = fs.metadata(id).unwrap().kind;
        v.push((
            std::str::from_utf8(&p[..len]).unwrap().to_string(),
            kind,
            if kind == NodeKind::File {
                contents(fs, id)
            } else {
                vec![]
            },
        ));
        if kind == NodeKind::Directory {
            fs.list(id, &mut |_, child, _| walk(fs, child, v)).unwrap();
        }
    }
    let mut out = vec![];
    walk(fs, fs.root(), &mut out);
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}
fn baseline() -> Disk {
    let mut d = fresh(80);
    {
        let mut fs = RostiFs::mount(&mut d).unwrap();
        let a = fs.create_file(NodeId::ROOT, "a").unwrap();
        fs.replace(a, &vec![0x41; 5000]).unwrap();
        let b = fs.create_file(NodeId::ROOT, "b").unwrap();
        fs.replace(b, b"untouched").unwrap();
        let sub = fs.create_dir(NodeId::ROOT, "d").unwrap();
        let c = fs.create_file(sub, "c").unwrap();
        fs.replace(c, b"nested").unwrap();
        fs.create_dir(NodeId::ROOT, "empty").unwrap();
        fs.create_file(NodeId::ROOT, "sentinel").unwrap();
    }
    d.checkpoint();
    d
}
fn operation(fs: &mut RostiFs<'_>, op: usize) -> Result<(), FsError> {
    let r = NodeId::ROOT;
    let a = fs.lookup(r, "a")?;
    match op {
        0 => fs.replace(a, &vec![0x42; 7000]),
        1 => fs.append(a, b"append").map(|_| ()),
        2 => fs.truncate(a, 100),
        3 => fs.truncate(a, 9000),
        4 => fs.truncate(a, 0),
        5 => fs.create_file(r, "d/new").map(|_| ()),
        6 => fs.create_dir(r, "d/newdir").map(|_| ()),
        7 => fs.remove_file(r, "a"),
        8 => fs.remove_file(r, "d/c"),
        9 => fs.write(a, 4500, &vec![0x63; 900]).map(|_| ()),
        10 => fs.remove_dir(r, "empty"),
        _ => unreachable!(),
    }
}
#[test]
fn every_sector_rejected_torn_and_every_flush_failed_recovers_old_or_new() {
    let base = baseline();
    let old = snapshot(&RostiFs::mount(&mut base.clone()).unwrap());
    let mut cases = 0;
    for op in 0..11 {
        let mut success = base.clone();
        {
            let mut fs = RostiFs::mount(&mut success).unwrap();
            operation(&mut fs, op).unwrap();
        }
        let events = success.events.len();
        let new = snapshot(&RostiFs::mount(&mut success).unwrap());
        for at in 0..events {
            for tear in [0, 1, 32, 255, 256, 511, 512] {
                let mut d = base.clone();
                d.fail = Some((at, tear));
                {
                    let mut fs = RostiFs::mount(&mut d).unwrap();
                    assert_eq!(operation(&mut fs, op), Err(FsError::DeviceIo));
                    assert_eq!(
                        fs.create_file(NodeId::ROOT, "poison"),
                        Err(FsError::DeviceIo)
                    );
                    assert_eq!(snapshot(&fs), old);
                }
                d.crash();
                let fs = RostiFs::mount(&mut d).unwrap();
                let got = snapshot(&fs);
                assert!(got == old || got == new, "op {op} event {at} tear {tear}");
                cases += 1;
            }
        }
    }
    std::println!("rejected/torn/flush crash cases={cases}");
}
#[test]
fn every_event_crash_with_reordered_pending_subsets() {
    let base = baseline();
    let old = snapshot(&RostiFs::mount(&mut base.clone()).unwrap());
    let mut cases = 0;
    for op in 0..11 {
        let mut success = base.clone();
        {
            let mut fs = RostiFs::mount(&mut success).unwrap();
            operation(&mut fs, op).unwrap();
        }
        let new = snapshot(&RostiFs::mount(&mut success).unwrap());
        let trace = success.events.clone();
        let mut durable = base.durable.clone();
        let mut pending: Vec<(usize, [u8; 512])> = vec![];
        for cut in 0..=trace.len() {
            for mode in 0..6 {
                let mut bytes = durable.clone();
                for (j, (lba, raw)) in pending.iter().rev().enumerate() {
                    if match mode {
                        0 => false,
                        1 => true,
                        2 => j % 2 == 0,
                        3 => j % 2 == 1,
                        4 => j == 0,
                        _ => j == pending.len() / 2,
                    } {
                        bytes[*lba * 512..(*lba + 1) * 512].copy_from_slice(raw);
                    }
                }
                let mut d = base.clone();
                d.live = bytes.clone();
                d.durable = bytes;
                let got = snapshot(&RostiFs::mount(&mut d).unwrap());
                assert!(got == old || got == new, "op {op} cut {cut} subset {mode}");
                cases += 1;
            }
            if cut < trace.len() {
                match &trace[cut] {
                    Event::Write(lba, raw) => pending.push((*lba, *raw)),
                    Event::Flush => {
                        for (lba, raw) in pending.drain(..) {
                            durable[lba * 512..(lba + 1) * 512].copy_from_slice(&raw);
                        }
                    }
                }
            }
        }
    }
    std::println!("reordered pending crash cases={cases}");
}
#[test]
fn nested_directories_handles_and_full_name_boundary() {
    let mut d = fresh(80);
    let mut fs = RostiFs::mount(&mut d).unwrap();
    let dir = fs.create_dir(NodeId::ROOT, "one").unwrap();
    let sub = fs.create_dir(dir, "two").unwrap();
    let name = "x".repeat(MAX_NAME_LEN);
    let a = fs.create_file(sub, &name).unwrap();
    fs.replace(a, b"abc ").unwrap();
    fs.create_file(NodeId::ROOT, "unrelated").unwrap();
    assert_eq!(contents(&fs, a), b"abc ");
    assert_eq!(fs.lookup(sub, &name), Ok(a));
    assert_eq!(
        fs.create_file(sub, &"x".repeat(MAX_NAME_LEN + 1)),
        Err(FsError::InvalidPath)
    );
    let mut p = [0; 256];
    let n = fs.path(a, &mut p).unwrap();
    assert_eq!(&p[..n], format!("/one/two/{name}").as_bytes());
    assert_eq!(
        fs.remove_dir(NodeId::ROOT, "one"),
        Err(FsError::DirectoryNotEmpty)
    );
    fs.remove_file(sub, &name).unwrap();
    assert_eq!(fs.metadata(a), Err(FsError::NotFound));
    let next = fs.create_file(sub, "replacement").unwrap();
    assert_ne!(a, next);
    assert_eq!(fs.metadata(a), Err(FsError::NotFound));
    fs.remove_file(sub, "replacement").unwrap();
    fs.remove_dir(dir, "two").unwrap();
    fs.remove_dir(NodeId::ROOT, "one").unwrap();
    assert_eq!(fs.metadata(dir), Err(FsError::NotFound));
    drop(fs);
    d.crash();
    RostiFs::mount(&mut d).unwrap();
}
#[test]
fn sparse_writes_append_truncate_and_bounds() {
    let mut d = fresh(220);
    let mut fs = RostiFs::mount(&mut d).unwrap();
    let a = fs.create_file(NodeId::ROOT, "a").unwrap();
    fs.write(a, 4094, b"abcd").unwrap();
    let expected = [vec![0; 4094], b"abcd".to_vec()].concat();
    assert_eq!(contents(&fs, a), expected);
    fs.append(a, b"ef").unwrap();
    fs.truncate(a, 4095).unwrap();
    fs.truncate(a, 4102).unwrap();
    let mut expected = expected[..4095].to_vec();
    expected.resize(4102, 0);
    assert_eq!(contents(&fs, a), expected);
    assert_eq!(fs.write(a, usize::MAX, b"x"), Err(FsError::FileTooLarge));
    assert_eq!(
        fs.truncate(a, MAX_FILE_BYTES + 1),
        Err(FsError::FileTooLarge)
    );
    fs.replace(a, &vec![7; MAX_FILE_BYTES]).unwrap();
    assert_eq!(contents(&fs, a), vec![7; MAX_FILE_BYTES]);
    fs.replace(a, &[]).unwrap();
    assert_eq!(contents(&fs, a), vec![]);
}
#[test]
fn paths_are_semantic_and_creation_names_strict() {
    let mut d = fresh(20);
    let mut fs = RostiFs::mount(&mut d).unwrap();
    let a = fs.create_file(NodeId::ROOT, "file").unwrap();
    for p in ["file/..", "file/.", "file/"] {
        assert_eq!(fs.lookup(NodeId::ROOT, p), Err(FsError::NotADirectory));
    }
    assert_eq!(fs.lookup(NodeId::ROOT, "/../../"), Ok(NodeId::ROOT));
    for p in ["", ".", "..", "/", "x/", "x\n", "x\0", "x\\y", "\u{0085}"] {
        assert_eq!(fs.create_file(NodeId::ROOT, p), Err(FsError::InvalidPath));
    }
    assert_eq!(fs.list(a, &mut |_, _, _| {}), Err(FsError::NotADirectory));
    assert_eq!(
        fs.read(NodeId::ROOT, 0, &mut [0; 1]),
        Err(FsError::IsADirectory)
    );
    assert_eq!(fs.metadata(NodeId::new(255, 0)), Err(FsError::NotFound));
}
#[test]
fn metadata_capacity_and_disk_full_preserve_old_state() {
    let mut d = fresh(9);
    let mut fs = RostiFs::mount(&mut d).unwrap();
    let a = fs.create_file(NodeId::ROOT, "a").unwrap();
    fs.replace(a, b"one").unwrap();
    fs.replace(a, b"two").unwrap();
    assert_eq!(fs.replace(a, b"three"), Err(FsError::FilesystemFull));
    assert_eq!(contents(&fs, a), b"two");
    fs.create_file(NodeId::ROOT, "checkpoint").unwrap();
    fs.replace(a, b"three").unwrap();
    for i in 2..MAX_INODES - 1 {
        fs.create_file(NodeId::ROOT, &format!("n{i}")).unwrap();
    }
    assert_eq!(fs.stats().nodes, MAX_INODES);
    assert_eq!(
        fs.create_file(NodeId::ROOT, "full"),
        Err(FsError::FilesystemFull)
    );
    fs.remove_file(NodeId::ROOT, "n2").unwrap();
    fs.create_file(NodeId::ROOT, "reused").unwrap();
    let mut count = 0;
    fs.list(NodeId::ROOT, &mut |_, _, _| count += 1).unwrap();
    assert_eq!(count, MAX_ENTRIES_PER_DIR);
}
#[test]
fn deterministic_random_model_and_repeated_remount() {
    let mut d = fresh(120);
    let mut expected = vec![];
    let id = {
        let mut fs = RostiFs::mount(&mut d).unwrap();
        fs.create_file(NodeId::ROOT, "a").unwrap()
    };
    let mut seed = 0x123456789u64;
    for step in 0..240 {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        let mut fs = RostiFs::mount(&mut d).unwrap();
        assert_eq!(fs.lookup(NodeId::ROOT, "a"), Ok(id));
        match seed % 4 {
            0 => {
                let len = (seed as usize >> 8) % 10000;
                fs.truncate(id, len).unwrap();
                expected.resize(len, 0);
            }
            1 => {
                let pos = (seed as usize >> 8) % 9000;
                let data = vec![step as u8; (seed as usize >> 20) % 500];
                fs.write(id, pos, &data).unwrap();
                if !data.is_empty() {
                    expected.resize(expected.len().max(pos + data.len()), 0);
                    expected[pos..pos + data.len()].copy_from_slice(&data);
                }
            }
            2 => {
                let data = vec![step as u8; (seed as usize >> 8) % 12000];
                fs.replace(id, &data).unwrap();
                expected = data;
            }
            _ => {
                let data = [step as u8; 17];
                fs.append(id, &data).unwrap();
                expected.extend_from_slice(&data);
            }
        }
        assert_eq!(contents(&fs, id), expected);
        drop(fs);
        d.crash();
    }
}
// Forge structure with correct CRCs: corruption detection must not depend only on CRC.
fn forge(d: &mut Disk, mut edit: impl FnMut(&mut [u8])) {
    for bank in 0..2 {
        let root_off = (1 + bank) * 4096;
        let mut root = [0; 4096];
        root.copy_from_slice(&d.live[root_off..root_off + 4096]);
        let mut sb = Superblock::decode(&root, bank, d.capacity_sectors()).unwrap();
        for page in 0..2 {
            let off = (3 + bank * 2 + page) * 4096;
            edit(&mut d.live[off..off + 4096]);
            sb.metadata_crc[page] = crate::checksum::crc32c(&d.live[off..off + 4096]);
        }
        sb.encode(&mut root);
        d.live[root_off..root_off + 4096].copy_from_slice(&root);
    }
    d.durable = d.live.clone();
}
#[test]
fn corrupt_references_overlap_names_cycles_and_free_records_rejected() {
    let base = baseline();
    for case in 0..12 {
        let mut d = base.clone();
        forge(&mut d, |page| {
            if page[128 + 4] != TYPE_FILE {
                return;
            }
            let a = 128;
            match case {
                0 => put_u32(page, a + 12, 1),
                1 => put_u32(page, a + 12, u32::MAX),
                2 => put_u32(page, a + 16, u32::MAX),
                3 => page[a + 5] = 255,
                4 => page[a + 5] = 1,
                5 => page[a + 6] = 61,
                6 => page[a + 24] = b'/',
                7 => page[a + 24] = 0xff,
                8 => {
                    page[2 * 128 + 24] = b'a';
                    page[2 * 128 + 6] = 1;
                }
                9 => {
                    let start = get_u32(page, a + 12);
                    put_u32(page, 2 * 128 + 12, start);
                }
                10 => page[31 * 128 + 24] = 1,
                _ => page[3 * 128 + 5] = 3,
            }
        });
        assert!(
            matches!(RostiFs::mount(&mut d), Err(FsError::CorruptVolume)),
            "case {case}"
        );
    }
}
#[test]
fn roots_metadata_data_corruption_fallback_and_both_bad() {
    let base = baseline();
    for block in 1..7 {
        let mut d = base.clone();
        d.live[block * 4096 + 200] ^= 1;
        assert!(RostiFs::mount(&mut d).is_ok());
    }
    let mut d = base.clone();
    d.live[4096] ^= 1;
    d.live[8192] ^= 1;
    assert!(matches!(
        RostiFs::mount(&mut d),
        Err(FsError::CorruptVolume)
    ));
    let mut d = base.clone();
    d.live[DATA_START * 4096] ^= 1;
    assert!(matches!(
        RostiFs::mount(&mut d),
        Err(FsError::CorruptVolume)
    ));
}
#[test]
fn version_geometry_marker_and_checked_translation() {
    let mut d = fresh(20);
    let marker = d.live[..4096].to_vec();
    {
        let mut fs = RostiFs::new(&mut d);
        fs.mount_in_place().unwrap();
        fs.create_dir(NodeId::ROOT, "d").unwrap();
    }
    assert_eq!(d.live[..4096], marker);
    assert_eq!(
        d.block_first_sector(usize::MAX),
        Err(BlockError::OutOfRange)
    );
    assert_eq!(d.block_first_sector(0), Err(BlockError::OutOfRange));
    assert_eq!(d.block_first_sector(19), Ok(152));
    d.live.truncate(159 * 512);
    assert_eq!(d.block_first_sector(19), Err(BlockError::OutOfRange));
    assert!(RostiFs::mount(&mut d).is_err());
    let mut d = fresh(20);
    for bank in 0..2 {
        put_u32(&mut d.live, (1 + bank) * 4096 + 8, 2);
    }
    assert!(matches!(
        RostiFs::mount(&mut d),
        Err(FsError::UnsupportedVersion)
    ));
    d.owned = false;
    let before = d.live.clone();
    assert_eq!(RostiFs::format(&mut d, 3), Err(FsError::InvalidPath));
    assert_eq!(d.live, before);
    d.sector = 4096;
    assert_eq!(d.block_first_sector(1), Err(BlockError::BufferSizeMismatch));
}
#[test]
fn listing_callback_can_reenter_read_without_aliasing() {
    let mut d = fresh(20);
    let mut fs = RostiFs::mount(&mut d).unwrap();
    let id = fs.create_file(NodeId::ROOT, "a").unwrap();
    fs.replace(id, b"abc").unwrap();
    fs.list(NodeId::ROOT, &mut |_, child, _| {
        assert_eq!(contents(&fs, child), b"abc")
    })
    .unwrap();
}
#[test]
fn fixed_memory_measurement() {
    std::println!(
        "RostiFs bytes={} inode bytes={}",
        core::mem::size_of::<RostiFs<'_>>(),
        core::mem::size_of::<Inode>()
    );
    assert!(core::mem::size_of::<RostiFs<'_>>() <= 23000);
}
