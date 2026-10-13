use crate::fd::{FdError, FdTable, Rights};
use crate::fs::{FsError, MountedFs, NodeId, NodeKind, RamFs, Vfs};
use alloc::boxed::Box;
use rostifs::block::{BlockDevice, BlockError};
struct MemoryDevice {
    bytes: alloc::vec::Vec<u8>,
}
impl MemoryDevice {
    fn blank() -> Self {
        Self {
            bytes: alloc::vec![0; 128 * 4096],
        }
    }
}
impl BlockDevice for MemoryDevice {
    fn sector_size(&self) -> usize {
        512
    }
    fn capacity_sectors(&self) -> usize {
        self.bytes.len() / 512
    }
    fn test_owned(&self) -> bool {
        true
    }
    fn flush(&mut self) -> Result<(), BlockError> {
        Ok(())
    } // RAM host model only
    fn read_sector(&mut self, lba: usize, buf: &mut [u8]) -> Result<(), BlockError> {
        if buf.len() != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        let start = lba.checked_mul(512).ok_or(BlockError::OutOfRange)?;
        let end = start.checked_add(512).ok_or(BlockError::OutOfRange)?;
        buf.copy_from_slice(self.bytes.get(start..end).ok_or(BlockError::OutOfRange)?);
        Ok(())
    }
    fn write_sector(&mut self, lba: usize, data: &[u8]) -> Result<(), BlockError> {
        if data.len() != 512 {
            return Err(BlockError::BufferSizeMismatch);
        }
        if lba == 0 {
            return Err(BlockError::Protected);
        }
        let start = lba.checked_mul(512).ok_or(BlockError::OutOfRange)?;
        let end = start.checked_add(512).ok_or(BlockError::OutOfRange)?;
        self.bytes
            .get_mut(start..end)
            .ok_or(BlockError::OutOfRange)?
            .copy_from_slice(data);
        Ok(())
    }
}
#[test]
fn corrupt_portable_mount_has_no_ram_namespace_side_effects() {
    let backend = Box::leak(Box::new(crate::fs::RostiBackend::new(Box::leak(Box::new(
        MemoryDevice::blank(),
    )))));
    let mut fs = MountedFs::new();
    let before = fs.stats();
    assert_eq!(fs.mount_rosti(backend), Err(FsError::CorruptVolume));
    assert_eq!(fs.stats(), before);
    assert!(fs.persistent_info().is_none());
    assert_eq!(fs.lookup(NodeId::ROOT, "/mnt"), Err(FsError::NotFound));
}
#[test]
fn portable_backend_in_place_mount_routes_real_core_and_reports_memory() {
    let mut device = MemoryDevice::blank();
    rostifs::engine::RostiFs::format(&mut device, 0x10203040).unwrap();
    let backend = Box::leak(Box::new(crate::fs::RostiBackend::new(Box::leak(Box::new(
        device,
    )))));
    backend.mount_in_place().unwrap();
    let mut fs = MountedFs::new();
    fs.mount_backend(backend).unwrap();
    let root = NodeId::ROOT;
    let disk = fs.lookup(root, "/mnt/rosti").unwrap();
    let dir = fs.create_dir(disk, "dir").unwrap();
    let file = fs.create_file(dir, "file").unwrap();
    fs.replace(file, b"portable").unwrap();
    fs.write(file, 8, b" core").unwrap();
    let mut buf = [0; 32];
    let n = fs.read(file, 0, &mut buf).unwrap();
    assert_eq!(&buf[..n], b"portable core");
    assert_eq!(fs.lookup(dir, "../../.."), Ok(root));
    assert_eq!(fs.lookup(dir, "file/.."), Err(FsError::NotADirectory));
    let mut fd = FdTable::new();
    let handle = fd
        .open(&fs, dir, "file", Rights::new(Rights::READ))
        .unwrap();
    assert_eq!(
        fd.write(&mut fs, handle, b"denied"),
        Err(FdError::PermissionDenied)
    );
    assert_eq!(fs.unmount(&mut fd, root), Err(FsError::Busy));
    fs.remove_file(dir, "file").unwrap();
    let replacement = fs.create_file(dir, "file").unwrap();
    assert_ne!(replacement, file);
    assert_eq!(
        fd.read(&fs, handle, &mut buf),
        Err(FdError::Fs(FsError::NotFound))
    );
    fd.close(handle).unwrap();
    let info = fs.persistent_info().unwrap();
    assert_eq!(info.fs_id, 0x10203040);
    assert_eq!(Some(info), fs.disk_info());
    std::println!(
        "mount memory host: core={} adapter={} router_bindings={} heap_payload={}",
        core::mem::size_of::<rostifs::engine::RostiFs>(),
        core::mem::size_of::<crate::fs::RostiBackend>(),
        info.metadata_bytes - core::mem::size_of::<crate::fs::RostiBackend>(),
        fs.stats().allocated_bytes
    );
    assert!(info.metadata_bytes > core::mem::size_of::<rostifs::engine::RostiFs>());
    assert_eq!(fs.stats().allocated_bytes, 0);
}

fn mounted() -> MountedFs<RamFs> {
    let mut fs = MountedFs::new();
    fs.mount_backend(Box::leak(Box::new(RamFs::new()))).unwrap();
    fs
}
#[test]
fn absent_mount_preserves_ram_accounting_and_no_directories() {
    let fs = MountedFs::<RamFs>::new();
    assert_eq!(fs.stats(), RamFs::new().stats());
    assert_eq!(fs.lookup(NodeId::ROOT, "/mnt"), Err(FsError::NotFound));
    assert_eq!(core::mem::size_of::<NodeId>(), 8);
}
#[test]
fn mount_traversal_cwd_dotdot_and_file_types() {
    let mut fs = mounted();
    let root = NodeId::ROOT;
    let disk = fs.lookup(root, "/mnt/rosti").unwrap();
    let sub = fs.create_dir(disk, "sub").unwrap();
    let file = fs.create_file(sub, "f").unwrap();
    assert_eq!(fs.lookup(sub, "../sub/f"), Ok(file));
    assert_eq!(fs.lookup(disk, "../../"), Ok(root));
    assert_eq!(fs.lookup(sub, "../../.."), Ok(root));
    assert_eq!(
        fs.lookup(root, "/mnt/rosti/sub/f/.."),
        Err(FsError::NotADirectory)
    );
    assert_eq!(fs.lookup(file, ".."), Err(FsError::NotADirectory));
    assert_eq!(
        fs.lookup(root, "/mnt/rosti/sub/f/"),
        Err(FsError::NotADirectory)
    );
    assert_eq!(
        fs.create_file(root, "/mnt/rosti/sub/f/../bad"),
        Err(FsError::NotADirectory)
    );
    let mut buf = [0; 256];
    let n = fs.path(sub, &mut buf).unwrap();
    assert_eq!(&buf[..n], b"/mnt/rosti/sub");
    let n = fs.path(disk, &mut buf).unwrap();
    assert_eq!(&buf[..n], b"/mnt/rosti");
}
#[test]
fn ram_and_mounted_identities_never_alias() {
    let mut fs = mounted();
    let root = NodeId::ROOT;
    let ram = fs.create_file(root, "same").unwrap();
    let disk = fs.create_file(root, "/mnt/rosti/same").unwrap();
    assert_ne!(ram, disk);
    fs.replace(ram, b"ram").unwrap();
    fs.replace(disk, b"disk").unwrap();
    let mut buf = [0; 8];
    let n = fs.read(ram, 0, &mut buf).unwrap();
    assert_eq!(&buf[..n], b"ram");
    let n = fs.read(disk, 0, &mut buf).unwrap();
    assert_eq!(&buf[..n], b"disk");
    fs.truncate(disk, 2).unwrap();
    assert_eq!(fs.metadata(disk).unwrap().size, 2);
}
#[test]
fn removal_routes_after_crossing_back_to_ram() {
    let mut fs = mounted();
    let root = NodeId::ROOT;
    let disk = fs.lookup(root, "/mnt/rosti").unwrap();
    fs.create_file(root, "ram").unwrap();
    fs.remove_file(disk, "../../ram").unwrap();
    assert_eq!(fs.lookup(root, "ram"), Err(FsError::NotFound));
    let f = fs.create_file(disk, "f").unwrap();
    fs.remove_file(disk, "f").unwrap();
    assert_eq!(fs.metadata(f), Err(FsError::NotFound));
    fs.create_dir(disk, "dir").unwrap();
    fs.remove_dir(disk, "dir").unwrap();
    assert_eq!(fs.remove_dir(root, "/mnt/rosti"), Err(FsError::Busy));
    assert_eq!(fs.remove_dir(root, "/mnt"), Err(FsError::Busy));
}
#[test]
fn descriptors_preserve_rights_shared_offset_and_unmount_pins() {
    let mut fs = mounted();
    let root = NodeId::ROOT;
    let f = fs.create_file(root, "/mnt/rosti/f").unwrap();
    fs.replace(f, b"abc").unwrap();
    let mut fd = FdTable::new();
    let a = fd
        .open(
            &fs,
            root,
            "/mnt/rosti/f",
            Rights::new(Rights::READ | Rights::STAT),
        )
        .unwrap();
    let b = fd.dup(a, Rights::READ).unwrap();
    let mut buf = [0; 1];
    fd.read(&fs, a, &mut buf).unwrap();
    assert_eq!(&buf, b"a");
    fd.read(&fs, b, &mut buf).unwrap();
    assert_eq!(&buf, b"b");
    assert_eq!(fd.write(&mut fs, a, b"x"), Err(FdError::PermissionDenied));
    assert_eq!(fs.unmount(&mut fd, root), Err(FsError::Busy));
    fd.close(a).unwrap();
    assert_eq!(fs.unmount(&mut fd, root), Err(FsError::Busy));
    fd.close(b).unwrap();
    let cwd = fs.lookup(root, "/mnt/rosti").unwrap();
    assert_eq!(fs.unmount(&mut fd, cwd), Err(FsError::Busy));
    fs.unmount(&mut fd, root).unwrap();
    assert_eq!(fs.metadata(f), Err(FsError::NotFound));
}
#[test]
fn deleted_open_descriptors_pin_until_last_close_and_ids_stay_stale() {
    let mut fs = mounted();
    let root = NodeId::ROOT;
    let old = fs.create_file(root, "/mnt/rosti/old").unwrap();
    let mut fd = FdTable::new();
    let a = fd
        .open(&fs, root, "/mnt/rosti/old", Rights::new(Rights::READ))
        .unwrap();
    fs.remove_file(root, "/mnt/rosti/old").unwrap();
    let new = fs.create_file(root, "/mnt/rosti/new").unwrap();
    assert_ne!(old, new);
    assert_eq!(
        fd.read(&fs, a, &mut [0; 1]),
        Err(FdError::Fs(FsError::NotFound))
    );
    assert_eq!(fs.unmount(&mut fd, root), Err(FsError::Busy));
    fd.close(a).unwrap();
    fs.unmount(&mut fd, root).unwrap();
    fs.mount_backend(Box::leak(Box::new(RamFs::new()))).unwrap();
    let remount = fs.create_file(root, "/mnt/rosti/new").unwrap();
    assert_ne!(new, remount);
    assert_eq!(fs.metadata(new), Err(FsError::NotFound));
}
#[test]
fn directory_listing_returns_routed_ids_and_no_duplicates() {
    let fs = mounted();
    let root = NodeId::ROOT;
    let mut entries = alloc::vec::Vec::new();
    let mnt = fs.lookup(root, "/mnt").unwrap();
    fs.list(mnt, &mut |n, id, k| entries.push((n.to_owned(), id, k)))
        .unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].0, "rosti");
    assert_eq!(entries[0].2, NodeKind::Directory);
    assert_eq!(entries[0].1, fs.lookup(root, "/mnt/rosti").unwrap());
}
#[test]
fn refuse_to_hide_existing_files_or_replace_active_mount() {
    let mut fs = MountedFs::<RamFs>::new();
    let root = NodeId::ROOT;
    fs.create_dir(root, "/mnt").unwrap();
    fs.create_dir(root, "/mnt/rosti").unwrap();
    fs.create_file(root, "/mnt/rosti/keep").unwrap();
    assert_eq!(
        fs.mount_backend(Box::leak(Box::new(RamFs::new()))),
        Err(FsError::DirectoryNotEmpty)
    );
    assert!(!fs.is_mounted());
    assert!(fs.lookup(root, "/mnt/rosti/keep").is_ok());
    fs.remove_file(root, "/mnt/rosti/keep").unwrap();
    fs.mount_backend(Box::leak(Box::new(RamFs::new()))).unwrap();
    assert_eq!(
        fs.mount_backend(Box::leak(Box::new(RamFs::new()))),
        Err(FsError::Busy)
    );
}
#[test]
fn canonical_mount_prefix_counts_against_path_limit() {
    let mut fs = mounted();
    let mut cwd = fs.lookup(NodeId::ROOT, "/mnt/rosti").unwrap();
    let name = "a".repeat(60);
    for _ in 0..4 {
        cwd = fs.create_dir(cwd, &name).unwrap();
    }
    assert_eq!(fs.create_file(cwd, "xxx"), Err(FsError::InvalidPath));
    assert_eq!(
        fs.create_file(NodeId::ROOT, "/mnt/rosti/control\n"),
        Err(FsError::InvalidPath)
    );
}
