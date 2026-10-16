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

#[test]
fn trusted_and_portable_mounts_coexist_in_both_attachment_orders() {
    for system_first in [false, true] {
        let mut device = MemoryDevice::blank();
        rostifs::engine::RostiFs::format(&mut device, 0x10203040).unwrap();
        let backend = Box::leak(Box::new(crate::fs::RostiBackend::new(Box::leak(Box::new(
            device,
        )))));
        backend.mount_in_place().unwrap();
        let mut fs = MountedFs::new();
        if system_first {
            fs.mount_system(archive_backend()).unwrap();
            fs.mount_backend(backend).unwrap();
        } else {
            fs.mount_backend(backend).unwrap();
            fs.mount_system(archive_backend()).unwrap();
        }
        let root = NodeId::ROOT;
        let trusted = fs.lookup(root, "/system/hello").unwrap();
        let disk = fs.create_file(root, "/mnt/rosti/hello").unwrap();
        let ram = fs.create_file(root, "/hello").unwrap();
        assert_ne!(trusted, disk);
        assert_ne!(trusted, ram);
        fs.replace(disk, b"persistent").unwrap();
        fs.replace(ram, b"recovery").unwrap();
        assert_eq!(fs.replace(trusted, b"changed"), Err(FsError::ReadOnly));
        for (id, expected) in [
            (trusted, &b"hello rosti"[..]),
            (disk, &b"persistent"[..]),
            (ram, &b"recovery"[..]),
        ] {
            let mut bytes = [0; 32];
            let len = fs.read(id, 0, &mut bytes).unwrap();
            assert_eq!(&bytes[..len], expected);
        }
        assert_eq!(fs.lookup(root, "/system/../mnt/rosti/hello"), Ok(disk));
        assert_eq!(
            fs.lookup(root, "/mnt/rosti/../../system/hello"),
            Ok(trusted)
        );
        assert!(fs.persistent_info().is_some());
    }
}

#[test]
fn system_every_mutator_is_read_only_even_through_old_mountpoint() {
    let mut fs = MountedFs::<RamFs>::new();
    let root = NodeId::ROOT;
    let old_point = fs.create_dir(root, "/system").unwrap();
    fs.mount_system(archive_backend()).unwrap();
    let file = fs.lookup(root, "/system/hello").unwrap();
    let before = fs.stats();
    assert_eq!(fs.create_file(root, "/system/new"), Err(FsError::ReadOnly));
    assert_eq!(fs.create_dir(old_point, "new"), Err(FsError::ReadOnly));
    for id in [file, old_point, fs.lookup(root, "/system").unwrap()] {
        assert_eq!(fs.write(id, 0, b""), Err(FsError::ReadOnly));
        assert_eq!(fs.replace(id, b"x"), Err(FsError::ReadOnly));
        assert_eq!(fs.truncate(id, usize::MAX), Err(FsError::ReadOnly));
    }
    assert_eq!(
        fs.remove_file(root, "/system/hello"),
        Err(FsError::ReadOnly)
    );
    assert_eq!(fs.remove_dir(root, "/system/sub"), Err(FsError::ReadOnly));
    assert_eq!(fs.remove_dir(root, "/system"), Err(FsError::ReadOnly));
    assert_eq!(fs.stats(), before);
    let mut b = [0; 11];
    assert_eq!(fs.read(file, 0, &mut b), Ok(11));
    assert_eq!(&b, b"hello rosti");
    assert_eq!(fs.lookup(root, "/system/new"), Err(FsError::NotFound));
}

#[test]
fn system_after_point_failure_rolls_back_only_owned_directory() {
    for existing in [false, true] {
        let mut fs = MountedFs::<RamFs>::new();
        let root = NodeId::ROOT;
        let old = existing.then(|| fs.create_dir(root, "/system").unwrap());
        let before = fs.stats();
        assert_eq!(
            fs.mount_system_failure_fixture(archive_backend()),
            Err(FsError::OutOfMemory)
        );
        assert_eq!(fs.stats(), before);
        assert!(fs.system.is_none());
        assert!(fs.system_point.is_none());
        assert!(fs.system_bindings.iter().all(|c| c.get().node.is_none()));
        assert_eq!(fs.lookup(root, "/system/hello"), Err(FsError::NotFound));
        assert_eq!(fs.lookup(root, "/system"), old.ok_or(FsError::NotFound));
        fs.mount_system(archive_backend()).unwrap();
        assert!(fs.lookup(root, "/system/hello").is_ok());
    }
}

#[test]
fn system_failed_preflight_releases_owned_snapshot_capacities() {
    let mut fs = MountedFs::<RamFs>::new();
    let keep = fs.create_file(NodeId::ROOT, "/system").unwrap();
    fs.replace(keep, b"keep").unwrap();
    let mut archive = archive_owned();
    assert!(archive.stats().allocated_bytes > 0);
    assert!(archive.stats().metadata_bytes > crate::fs::ArchiveFs::empty().stats().metadata_bytes);
    assert_eq!(
        fs.prepare_system(&mut archive, false).err(),
        Some(FsError::NotADirectory)
    );
    assert_eq!(archive.stats(), crate::fs::ArchiveFs::empty().stats());
}

#[test]
fn system_info_accounts_archive_and_routing_separately_from_ram() {
    let mut fs = MountedFs::<RamFs>::new();
    assert_eq!(fs.system_info(), None);
    let archive = archive_backend();
    let mut expected = archive.stats();
    expected.metadata_bytes += core::mem::size_of_val(&fs.system_bindings);
    let point = fs.create_dir(NodeId::ROOT, "/system").unwrap();
    let ram = fs.stats();
    fs.mount_system(archive).unwrap();
    assert_eq!(fs.system_info(), Some(expected));
    fn generic_info(fs: &impl Vfs) -> Option<crate::fs::FsStats> {
        fs.system_info()
    }
    assert_eq!(generic_info(&fs), Some(expected));
    assert_eq!(generic_info(&RamFs::new()), None);
    assert_eq!(fs.stats(), ram);
    assert_eq!(fs.ram.lookup(NodeId::ROOT, "/system"), Ok(point));
}

#[test]
fn system_refusal_matrix_preserves_namespace_descriptors_and_releases_capacity() {
    for case in 0..7 {
        let mut fs = MountedFs::<RamFs>::new();
        let root = NodeId::ROOT;
        let cwd = fs.create_dir(root, "cwd").unwrap();
        let keep = fs.create_file(cwd, "keep").unwrap();
        fs.replace(keep, b"keep").unwrap();
        let mut fd = FdTable::new();
        let a = fd
            .open(&fs, cwd, "keep", Rights::new(Rights::READ))
            .unwrap();
        let b = fd.dup(a, Rights::READ).unwrap();
        let mut byte = [0; 1];
        fd.read(&fs, a, &mut byte).unwrap();
        let expected = match case {
            0 => {
                let id = fs.create_file(root, "/system").unwrap();
                fs.replace(id, b"collision").unwrap();
                FsError::NotADirectory
            }
            1 => {
                fs.create_dir(root, "/system").unwrap();
                fs.create_file(root, "/system/child").unwrap();
                FsError::DirectoryNotEmpty
            }
            2 => {
                while fs
                    .create_file(root, &alloc::format!("f{}", fs.stats().nodes))
                    .is_ok()
                {}
                FsError::FilesystemFull
            }
            3 => FsError::InvalidPath,
            4 => {
                fs.mount_system(archive_backend()).unwrap();
                FsError::Busy
            }
            5 => FsError::OutOfMemory,
            6 => {
                fs.create_dir(root, "/system").unwrap();
                FsError::OutOfMemory
            }
            _ => unreachable!(),
        };
        let mut archive = if case == 3 {
            archive_with_path(250)
        } else {
            archive_owned()
        };
        let ram_before = fs.stats();
        let info_before = fs.system_info();
        let bindings_before: alloc::vec::Vec<_> = fs
            .system_bindings
            .iter()
            .map(|c| (c.get().node, c.get().generation))
            .collect();
        let point_before = fs.system_point;
        let mut names_before = alloc::vec::Vec::new();
        fs.list(root, &mut |name, id, kind| {
            names_before.push((name.to_owned(), id, kind))
        })
        .unwrap();
        let descriptors = [fd.info(a).unwrap(), fd.info(b).unwrap()];
        let counts = fd.stats();
        assert!(archive.stats().allocated_bytes > 0);
        assert_eq!(
            fs.prepare_system(&mut archive, case >= 5).err(),
            Some(expected),
            "case {case}"
        );
        assert_eq!(
            archive.stats(),
            crate::fs::ArchiveFs::empty().stats(),
            "case {case}"
        );
        assert_eq!(fs.stats(), ram_before);
        assert_eq!(fs.system_info(), info_before);
        assert_eq!(fs.system_point, point_before);
        assert_eq!(
            fs.system_bindings
                .iter()
                .map(|c| (c.get().node, c.get().generation))
                .collect::<alloc::vec::Vec<_>>(),
            bindings_before
        );
        let mut names_after = alloc::vec::Vec::new();
        fs.list(root, &mut |name, id, kind| {
            names_after.push((name.to_owned(), id, kind))
        })
        .unwrap();
        assert_eq!(names_after, names_before);
        assert_eq!([fd.info(a).unwrap(), fd.info(b).unwrap()], descriptors);
        assert_eq!(fd.stats(), counts);
        assert_eq!(fs.lookup(cwd, "keep"), Ok(keep));
        fd.read(&fs, b, &mut byte).unwrap();
        assert_eq!(&byte, b"e");
        if case == 0 {
            let id = fs.lookup(root, "/system").unwrap();
            let mut bytes = [0; 9];
            assert_eq!(fs.read(id, 0, &mut bytes), Ok(9));
            assert_eq!(&bytes, b"collision");
        }
        if case == 1 {
            assert!(fs.lookup(root, "/system/child").is_ok());
        }
        if case == 4 {
            assert!(fs.lookup(root, "/system/hello").is_ok());
        }
    }
}

fn archive_with_path(len: usize) -> crate::fs::ArchiveFs {
    // Three full components and one tail: archive absolute length is len + 1.
    let path = alloc::format!("{0}/{0}/{0}/{1}", "a".repeat(63), "z".repeat(len - 192));
    let bytes =
        crate::initramfs::initramfs_tests::fixture(&[(0o100644, path.as_bytes(), b"payload")]);
    let mut archive = crate::fs::ArchiveFs::empty();
    archive
        .try_build(&crate::initramfs::parse(&bytes).unwrap(), &bytes)
        .unwrap();
    archive
}

#[test]
fn system_canonical_prefix_exact_boundary_and_empty_point_succeed() {
    for existing in [false, true] {
        let mut fs = MountedFs::<RamFs>::new();
        if existing {
            fs.create_dir(NodeId::ROOT, "/system").unwrap();
        }
        // 248 relative bytes + archive leading slash + seven-byte prefix = 256.
        fs.mount_system(Box::leak(Box::new(archive_with_path(248))))
            .unwrap();
        let system = fs.lookup(NodeId::ROOT, "/system").unwrap();
        let path = alloc::format!("{0}/{0}/{0}/{1}", "a".repeat(63), "z".repeat(56));
        let file = fs.lookup(system, &path).unwrap();
        let mut buf = [0; 256];
        assert_eq!(fs.path(file, &mut buf), Ok(256));
    }
    let mut fs = MountedFs::<RamFs>::new();
    let mut archive = archive_with_path(249);
    assert_eq!(
        fs.prepare_system(&mut archive, false).err(),
        Some(FsError::InvalidPath)
    );
    assert_eq!(archive.stats(), crate::fs::ArchiveFs::empty().stats());
    assert_eq!(fs.lookup(NodeId::ROOT, "/system"), Err(FsError::NotFound));
}

#[test]
fn system_descriptors_enforce_capabilities_and_share_offsets_across_disk_remount() {
    let mut fs = mounted();
    fs.mount_system(archive_backend()).unwrap();
    let root = NodeId::ROOT;
    let mut fd = FdTable::new();
    let a = fd
        .open(
            &fs,
            root,
            "/system/hello",
            Rights::new(Rights::READ | Rights::STAT | Rights::SEEK),
        )
        .unwrap();
    let b = fd.dup(a, Rights::READ).unwrap();
    assert_eq!(fd.stat(&fs, a).unwrap().size, 11);
    let mut bytes = [0; 2];
    assert_eq!(fd.read(&fs, a, &mut bytes), Ok(2));
    assert_eq!(&bytes, b"he");
    assert_eq!(fd.read(&fs, b, &mut bytes), Ok(2));
    assert_eq!(&bytes, b"ll");
    let slots = fd.stats().open_slots;
    let records = fd.stats().open_records;
    assert_eq!(fd.dup(b, Rights::WRITE), Err(FdError::PermissionDenied));
    assert_eq!(fd.seek(b, 0), Err(FdError::PermissionDenied));
    assert_eq!(fd.stat(&fs, b), Err(FdError::PermissionDenied));
    assert_eq!(fd.write(&mut fs, a, b"x"), Err(FdError::PermissionDenied));
    assert_eq!(fd.truncate(&mut fs, a, 0), Err(FdError::PermissionDenied));
    assert_eq!(fd.replace(&mut fs, a, b"x"), Err(FdError::PermissionDenied));
    assert_eq!(fd.info(a).unwrap().offset, 4);
    assert_eq!(fd.info(b).unwrap().offset, 4);
    assert_eq!(
        (fd.stats().open_slots, fd.stats().open_records),
        (slots, records)
    );
    fd.seek(a, 6).unwrap();
    assert_eq!(fd.info(b).unwrap().offset, 6);
    fs.unmount(&mut fd, root).unwrap();
    fs.mount_backend(Box::leak(Box::new(RamFs::new()))).unwrap();
    assert_eq!(fd.read(&fs, b, &mut bytes), Ok(2));
    assert_eq!(&bytes, b"ro");
    let w = fd
        .open(
            &fs,
            root,
            "/system/hello",
            Rights::new(Rights::WRITE | Rights::SEEK),
        )
        .unwrap();
    fd.seek(w, 3).unwrap();
    let before = fd.info(w).unwrap();
    let live = (fd.stats().open_slots, fd.stats().open_records);
    assert_eq!(
        fd.write(&mut fs, w, b"x"),
        Err(FdError::Fs(FsError::ReadOnly))
    );
    assert_eq!(
        fd.replace(&mut fs, w, b"x"),
        Err(FdError::Fs(FsError::ReadOnly))
    );
    assert_eq!(
        fd.truncate(&mut fs, w, 0),
        Err(FdError::Fs(FsError::ReadOnly))
    );
    assert_eq!(fd.info(w).unwrap(), before);
    assert_eq!((fd.stats().open_slots, fd.stats().open_records), live);
    assert_eq!(fd.read(&fs, w, &mut bytes), Err(FdError::PermissionDenied));
    for handle in [a, b, w] {
        fd.close(handle).unwrap();
    }
    assert_eq!((fd.stats().open_slots, fd.stats().open_records), (0, 0));
}

#[test]
fn system_forged_binding_boundaries_never_alias_live_nodes() {
    let mut fs = MountedFs::<RamFs>::new();
    fs.mount_system(archive_backend()).unwrap();
    let file = fs.lookup(NodeId::ROOT, "/system/hello").unwrap();
    for id in [
        NodeId {
            generation: file.generation + 1,
            ..file
        },
        NodeId {
            slot: 0x23f,
            generation: 0,
        },
        NodeId {
            slot: 0x240,
            generation: 0,
        },
        NodeId {
            slot: u16::MAX,
            generation: 0,
        },
    ] {
        assert_eq!(fs.metadata(id), Err(FsError::NotFound));
        assert_eq!(fs.read(id, 0, &mut [0; 1]), Err(FsError::NotFound));
    }
}

fn archive_backend() -> &'static mut crate::fs::ArchiveFs {
    Box::leak(Box::new(archive_owned()))
}
fn archive_owned() -> crate::fs::ArchiveFs {
    let bytes = crate::initramfs::initramfs_tests::fixture(&[
        (0o100644, b"sub/note", b"note"),
        (0o100644, b"hello", b"hello rosti"),
    ]);
    let mut archive = crate::fs::ArchiveFs::empty();
    archive
        .try_build(&crate::initramfs::parse(&bytes).unwrap(), &bytes)
        .unwrap();
    archive
}
#[test]
fn system_publication_reads_lists_and_traverses_independently() {
    let mut fs = MountedFs::<RamFs>::new();
    fs.mount_system(archive_backend()).unwrap();
    let root = NodeId::ROOT;
    let system = fs.lookup(root, "/system").unwrap();
    let note = fs.lookup(system, "sub/note").unwrap();
    assert!(system.slot >= 0x200 && note.slot >= 0x200);
    let mut buf = [0; 256];
    assert_eq!(fs.read(note, 1, &mut buf), Ok(3));
    assert_eq!(&buf[..3], b"ote");
    let n = fs.path(note, &mut buf).unwrap();
    assert_eq!(&buf[..n], b"/system/sub/note");
    assert_eq!(fs.lookup(system, ".."), Ok(root));
    assert_eq!(fs.lookup(system, "sub/../../system/sub/note"), Ok(note));
    assert_eq!(fs.lookup(system, "hello/.."), Err(FsError::NotADirectory));
    let mut names = alloc::vec::Vec::new();
    fs.list(system, &mut |name, id, kind| {
        assert_eq!(fs.lookup(system, name), Ok(id));
        assert_eq!(fs.metadata(id).unwrap().kind, kind);
        names.push(name.to_owned());
    })
    .unwrap();
    assert_eq!(names, ["sub", "hello"]);
    assert_eq!(fs.lookup(root, "/mnt"), Err(FsError::NotFound));
    assert!(!fs.is_mounted());
    assert!(fs.persistent_info().is_none());
    fs.create_file(root, "ram").unwrap();
}
