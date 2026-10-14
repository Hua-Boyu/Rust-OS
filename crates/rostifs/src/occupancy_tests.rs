extern crate std;
use super::*;
use crate::block::BlockError;
use std::cell::Cell;
use std::collections::BTreeSet;

std::thread_local! {
    static PROBES: Cell<usize> = const { Cell::new(0) };
}
pub(super) fn probe() {
    PROBES.with(|n| n.set(n.get() + 1));
}
struct NoIo;
impl BlockDevice for NoIo {
    fn sector_size(&self) -> usize {
        512
    }
    fn capacity_sectors(&self) -> usize {
        MAX_VOLUME_BLOCKS * SECTORS_PER_BLOCK
    }
    fn test_owned(&self) -> bool {
        false
    }
    fn read_sector(&mut self, _: usize, _: &mut [u8]) -> Result<(), BlockError> {
        panic!("diagnostics must not read")
    }
    fn write_sector(&mut self, _: usize, _: &[u8]) -> Result<(), BlockError> {
        panic!("diagnostics must not write")
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        panic!("diagnostics must not flush")
    }
}

#[test]
fn empty_mount_info_work_is_independent_of_volume_capacity() {
    let mut device = NoIo;
    let mut fs = RostiFs::new(&mut device);
    for total in [128, 1024, MAX_VOLUME_BLOCKS] {
        fs.sb.total_blocks = total as u32;
        PROBES.with(|n| n.set(0));
        let info = fs.mount_info();
        let probes = PROBES.with(Cell::get);
        assert_eq!(info.used_blocks, DATA_START as u32);
        assert_eq!(info.free_blocks, (total - DATA_START) as u32);
        assert!(probes <= 2 * MAX_INODES, "total={total} probes={probes}");
    }
}

#[test]
fn fully_fragmented_two_inventories_have_bounded_endpoint_work() {
    let mut device = NoIo;
    let mut fs = RostiFs::new(&mut device);
    for total in [1024, MAX_VOLUME_BLOCKS] {
        fs.sb.total_blocks = total as u32;
        for (bank, ns) in [&mut fs.nodes, &mut fs.previous].into_iter().enumerate() {
            for (i, n) in ns.iter_mut().enumerate() {
                n.start = (DATA_START + 4 * i + bank * 2) as u32;
                n.blocks = 1;
            }
        }
        PROBES.with(|n| n.set(0));
        let info = fs.mount_info();
        assert_eq!(info.used_blocks, (DATA_START + 2 * MAX_INODES) as u32);
        assert!(PROBES.with(Cell::get) <= (4 * MAX_INODES + 1) * (2 * MAX_INODES));
    }
}

#[test]
fn mount_info_matches_clipped_union_including_failed_mount_states() {
    let mut device = NoIo;
    let mut fs = RostiFs::new(&mut device);
    // Include unmounted/failed-remount inventories, clipped extents, duplicates,
    // adjacent intervals and cross-snapshot overlaps. No disjointness assumption.
    for total in [0, 7, 15, 128, 1024] {
        fs.sb.total_blocks = total;
        for seed in 0..64u32 {
            fs.nodes.fill(Inode::EMPTY);
            fs.previous.fill(Inode::EMPTY);
            for (bank, ns) in [&mut fs.nodes, &mut fs.previous].into_iter().enumerate() {
                for (i, n) in ns.iter_mut().enumerate().take(16) {
                    n.start = (seed * 17 + i as u32 * 11 + bank as u32 * 3) % 150;
                    n.blocks = (seed + i as u32 * 7) % 65;
                }
            }
            let mut union = BTreeSet::new();
            for n in fs.nodes.iter().chain(fs.previous.iter()) {
                for b in n.start..n.start + n.blocks {
                    if b >= DATA_START as u32 && b < total {
                        union.insert(b);
                    }
                }
            }
            let expected = DATA_START + union.len();
            PROBES.with(|n| n.set(0));
            let info = fs.mount_info();
            assert_eq!(
                info.used_blocks as usize, expected,
                "total={total} seed={seed}"
            );
            assert_eq!(info.free_blocks, total.saturating_sub(expected as u32));
            let probes = PROBES.with(Cell::get);
            // A bounded sweep can advance across at most two endpoints per extent.
            assert!(probes <= (4 * MAX_INODES + 1) * (2 * MAX_INODES));
        }
    }
}
