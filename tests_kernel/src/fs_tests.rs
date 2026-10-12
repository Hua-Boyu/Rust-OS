use crate::fs::{FsError, NodeId, NodeKind, RamFs, Vfs};
#[test]
fn fs_nested_paths() {
    let mut fs = RamFs::new();
    let r = fs.root();
    let a = fs.create_dir(r, "/a/").unwrap();
    let b = fs.create_dir(a, "b").unwrap();
    let f = fs.create_file(r, "/a/b/猫").unwrap();
    assert_eq!(fs.metadata(f).unwrap().kind, NodeKind::File);
    assert_eq!(fs.lookup(b, "../b/./猫"), Ok(f));
    assert_eq!(fs.lookup(r, "/../../a//b/"), Ok(b));
    assert_eq!(fs.lookup(r, "/a/b/猫/.."), Err(FsError::NotADirectory));
    assert_eq!(fs.lookup(r, "/a/b/猫/"), Err(FsError::NotADirectory));
    assert_eq!(fs.create_file(b, "猫"), Err(FsError::AlreadyExists));
    for p in ["", ".", "..", "/"] {
        assert_eq!(fs.create_dir(r, p), Err(FsError::InvalidPath));
    }
    assert_eq!(fs.create_file(r, "x/"), Err(FsError::NotADirectory));
    let mut out = [0; 256];
    let n = fs.path(f, &mut out).unwrap();
    assert_eq!(&out[..n], "/a/b/猫".as_bytes());
    let mut seen = Vec::new();
    fs.list(b, &mut |s, id, k| seen.push((s.to_string(), id, k)))
        .unwrap();
    assert_eq!(seen, vec![("猫".to_string(), f, NodeKind::File)]);
    assert_eq!(fs.list(f, &mut |_, _, _| {}), Err(FsError::NotADirectory));
    assert_eq!(fs.path(f, &mut [0; 2]), Err(FsError::InvalidPath));
    assert_eq!(fs.lookup(r, &"x".repeat(257)), Err(FsError::InvalidPath));
    assert_eq!(
        fs.create_file(r, &"x".repeat(64)),
        Err(FsError::InvalidPath)
    );
    assert_eq!(fs.create_file(r, "bad\0name"), Err(FsError::InvalidPath));
}

#[test]
fn fs_binary_offsets_truncate() {
    let mut fs = RamFs::new();
    let id = fs.create_file(fs.root(), "data").unwrap();
    assert_eq!(fs.write(id, 3, &[0xff, 0, 0x80]), Ok(3));
    let mut buf = [9; 8];
    assert_eq!(fs.read(id, 0, &mut buf), Ok(6));
    assert_eq!(&buf[..6], &[0, 0, 0, 0xff, 0, 0x80]);
    assert_eq!(fs.read(id, usize::MAX, &mut buf), Ok(0));
    assert_eq!(fs.read(id, 4, &mut buf[..1]), Ok(1));
    assert_eq!(buf[0], 0);
    fs.write(id, 1, b"ab").unwrap();
    fs.truncate(id, 2).unwrap();
    fs.truncate(id, 5).unwrap();
    assert_eq!(fs.read(id, 0, &mut buf), Ok(5));
    assert_eq!(&buf[..5], &[0, b'a', 0, 0, 0]);
    fs.replace(id, "猫".as_bytes()).unwrap();
    assert_eq!(fs.metadata(id).unwrap().size, 3);
    assert_eq!(fs.read(id, 0, &mut buf), Ok(3));
    assert_eq!(&buf[..3], "猫".as_bytes());
    fs.truncate(id, 0).unwrap();
    assert_eq!(fs.metadata(id).unwrap().size, 0);
    assert_eq!(fs.read(fs.root(), 0, &mut buf), Err(FsError::IsADirectory));
    assert_eq!(fs.write(fs.root(), 0, b""), Err(FsError::IsADirectory));
    assert_eq!(fs.replace(fs.root(), b""), Err(FsError::IsADirectory));
    assert_eq!(fs.truncate(fs.root(), 0), Err(FsError::IsADirectory));
    assert_eq!(fs.write(id, usize::MAX, b"x"), Err(FsError::FileTooLarge));
}

#[test]
fn fs_removal_stale_ids_and_bounded_cycles() {
    let mut fs = RamFs::new();
    let r = fs.root();
    let dir = fs.create_dir(r, "dir").unwrap();
    let old = fs.create_file(dir, "child").unwrap();
    assert_eq!(fs.remove_dir(r, "dir"), Err(FsError::DirectoryNotEmpty));
    assert_eq!(fs.remove_file(r, "dir"), Err(FsError::IsADirectory));
    assert_eq!(fs.remove_dir(dir, "child"), Err(FsError::NotADirectory));
    assert_eq!(fs.remove_dir(r, "/"), Err(FsError::InvalidPath));
    fs.remove_file(dir, "child").unwrap();
    let new = fs.create_file(dir, "child").unwrap();
    assert_ne!(old, new);
    assert_eq!(fs.metadata(old), Err(FsError::NotFound));
    assert_eq!(fs.write(old, 0, b"x"), Err(FsError::NotFound));
    assert_eq!(fs.lookup(old, "/"), Err(FsError::NotFound));
    fs.remove_file(dir, "child").unwrap();
    fs.remove_dir(r, "dir").unwrap();
    assert_eq!(fs.lookup(dir, "."), Err(FsError::NotFound));
    for _ in 0..512 {
        let f = fs.create_file(r, "cycle").unwrap();
        fs.replace(f, b"payload").unwrap();
        fs.remove_file(r, "cycle").unwrap();
    }
    for i in 0..63 {
        fs.create_file(r, &format!("f{i}")).unwrap();
    }
    assert_eq!(fs.create_dir(r, "overflow"), Err(FsError::FilesystemFull));
    fs.remove_file(r, "f0").unwrap();
    fs.create_dir(r, "freed").unwrap();
}

#[test]
fn fs_capacity_quota_accounting() {
    use crate::fs::{MAX_FILE_SIZE, MAX_PAYLOAD};
    let mut fs = RamFs::new();
    assert_eq!(fs.stats().nodes, 1);
    assert_eq!(fs.stats().metadata_bytes, core::mem::size_of::<RamFs>());
    assert_eq!(fs.stats().allocated_bytes, 0);
    let r = fs.root();
    let f = fs.create_file(r, "first").unwrap();
    fs.truncate(f, MAX_FILE_SIZE).unwrap();
    assert_eq!(fs.stats().logical_bytes, MAX_FILE_SIZE);
    assert_eq!(fs.stats().allocated_bytes, MAX_FILE_SIZE);
    fs.truncate(f, 1).unwrap();
    assert_eq!(fs.stats().logical_bytes, 1);
    assert_eq!(fs.stats().allocated_bytes, MAX_FILE_SIZE);
    assert_eq!(
        fs.truncate(f, MAX_FILE_SIZE + 1),
        Err(FsError::FileTooLarge)
    );
    assert_eq!(
        fs.replace(f, &vec![0; MAX_FILE_SIZE + 1]),
        Err(FsError::FileTooLarge)
    );
    for i in 1..8 {
        let id = fs.create_file(r, &format!("f{i}")).unwrap();
        fs.truncate(id, MAX_FILE_SIZE).unwrap();
    }
    assert_eq!(fs.stats().allocated_bytes, MAX_PAYLOAD);
    let extra = fs.create_file(r, "extra").unwrap();
    let before = fs.stats();
    assert_eq!(fs.write(extra, 0, b"x"), Err(FsError::FilesystemFull));
    assert_eq!(fs.stats(), before);
    fs.truncate(f, 0).unwrap();
    assert_eq!(fs.stats().allocated_bytes, MAX_PAYLOAD - MAX_FILE_SIZE);
    fs.replace(extra, b"x").unwrap();
    fs.remove_file(r, "extra").unwrap();
    assert_eq!(fs.stats().allocated_bytes, MAX_PAYLOAD - MAX_FILE_SIZE);
    for i in 1..8 {
        fs.remove_file(r, &format!("f{i}")).unwrap();
    }
    fs.remove_file(r, "first").unwrap();
    assert_eq!(fs.stats().nodes, 1);
    assert_eq!(fs.stats().logical_bytes, 0);
    assert_eq!(fs.stats().allocated_bytes, 0);
}

#[test]
fn fs_reserve_failure_is_transactional() {
    let mut fs = RamFs::new();
    let r = fs.root();
    let f = fs.create_file(r, "safe").unwrap();
    fs.replace(f, b"safe").unwrap();
    for operation in 0..3 {
        let before = fs.stats();
        fs.fail_next_allocation();
        let result = match operation {
            0 => fs.write(f, 100, b"x").map(|_| ()),
            1 => fs.replace(f, &[9; 100]),
            _ => fs.truncate(f, 100),
        };
        assert_eq!(result, Err(FsError::OutOfMemory));
        assert_eq!(fs.stats(), before);
        let mut buf = [0; 4];
        assert_eq!(fs.read(f, 0, &mut buf), Ok(4));
        assert_eq!(&buf, b"safe");
    }
    fs.fail_next_allocation();
    let empty = fs.create_file(r, "empty").unwrap(); // Fixed metadata needs no allocation.
    let before = fs.stats();
    assert_eq!(fs.write(empty, 0, b"x"), Err(FsError::OutOfMemory));
    assert_eq!(fs.stats(), before);
    fs.write(empty, 0, b"x").unwrap();
}

#[test]
fn fs_canonical_path_bound_and_deep_iteration() {
    let mut fs = RamFs::new();
    let r = fs.root();
    let mut cwd = r;
    for _ in 0..4 {
        cwd = fs.create_dir(cwd, &"a".repeat(63)).unwrap();
    }
    let mut buf = [0; 256];
    assert_eq!(fs.path(cwd, &mut buf), Ok(256));
    let before = fs.stats();
    assert_eq!(fs.create_file(cwd, "x"), Err(FsError::InvalidPath));
    assert_eq!(fs.stats(), before);
    assert_eq!(fs.lookup(r, core::str::from_utf8(&buf).unwrap()), Ok(cwd));
    let mut fs = RamFs::new();
    let mut cwd = fs.root();
    for _ in 0..63 {
        cwd = fs.create_dir(cwd, "d").unwrap();
    }
    let n = fs.path(cwd, &mut buf).unwrap();
    assert_eq!(n, 126);
    assert_eq!(fs.lookup(cwd, &"../".repeat(63)), Ok(fs.root()));
}

#[test]
fn fs_stale_handles_reject_every_id_operation() {
    let mut fs = RamFs::new();
    let r = fs.root();
    let id = fs.create_file(r, "gone").unwrap();
    fs.remove_file(r, "gone").unwrap();
    let mut bytes = [7; 8];
    assert_eq!(fs.read(id, 0, &mut bytes), Err(FsError::NotFound));
    assert_eq!(fs.replace(id, b"x"), Err(FsError::NotFound));
    assert_eq!(fs.truncate(id, 0), Err(FsError::NotFound));
    assert_eq!(
        fs.list(id, &mut |_, _, _| panic!("stale callback")),
        Err(FsError::NotFound)
    );
    assert_eq!(fs.path(id, &mut bytes), Err(FsError::NotFound));
    assert_eq!(bytes, [7; 8]);
    assert_eq!(fs.create_file(id, "new"), Err(FsError::NotFound));
    assert_eq!(fs.create_dir(id, "/new"), Err(FsError::NotFound));
    assert_eq!(fs.remove_file(id, "/missing"), Err(FsError::NotFound));
    assert_eq!(fs.remove_dir(id, "/missing"), Err(FsError::NotFound));
}

#[test]
fn fs_error_display_is_human_readable() {
    for (error, text) in [
        (FsError::NotFound, "not found"),
        (FsError::AlreadyExists, "already exists"),
        (FsError::NotADirectory, "not a directory"),
        (FsError::IsADirectory, "is a directory"),
        (FsError::DirectoryNotEmpty, "directory not empty"),
        (FsError::OutOfMemory, "out of memory"),
        (FsError::FilesystemFull, "filesystem full"),
        (FsError::FileTooLarge, "file too large"),
        (FsError::InvalidPath, "invalid path"),
    ] {
        assert_eq!(error.to_string(), text);
    }
}

#[test]
fn fs_reference_bytes_across_repeated_edits() {
    let mut fs = RamFs::new();
    let id = fs.create_file(fs.root(), "model").unwrap();
    let mut model = Vec::new();
    for step in 0..256usize {
        match step % 3 {
            0 => {
                let offset = step % 91;
                let data = [step as u8, 0, 0xff];
                if model.len() < offset + data.len() {
                    model.resize(offset + data.len(), 0);
                }
                model[offset..offset + data.len()].copy_from_slice(&data);
                assert_eq!(fs.write(id, offset, &data), Ok(data.len()));
            }
            1 => {
                let len = step % 101;
                model.resize(len, 0);
                fs.truncate(id, len).unwrap();
            }
            _ => {
                model = vec![step as u8; step % 67];
                fs.replace(id, &model).unwrap();
            }
        }
        let mut bytes = [0; 128];
        assert_eq!(fs.read(id, 0, &mut bytes), Ok(model.len()));
        assert_eq!(&bytes[..model.len()], &model);
        assert_eq!(fs.stats().logical_bytes, model.len());
        assert!(fs.stats().allocated_bytes >= model.len());
        assert_eq!(fs.stats().nodes, 2);
    }
}

#[test]
fn fs_rejects_terminal_control_characters_in_paths() {
    let mut fs = RamFs::new();
    let root = fs.root();
    let before = fs.stats();
    for path in ["bad\nname", "bad\tname", "bad\u{1b}name", "bad\u{7f}name"] {
        assert_eq!(fs.create_file(root, path), Err(FsError::InvalidPath));
        assert_eq!(fs.create_dir(root, path), Err(FsError::InvalidPath));
        assert_eq!(fs.lookup(root, path), Err(FsError::InvalidPath));
        assert_eq!(fs.stats(), before);
    }
}

#[test]
fn keyboard_queue_overflow_discards_all_partial_commands_and_recovers() {
    let ring = crate::kbd::RingBuffer::<8>::new();
    // An earlier Enter must not clear the loss before a later damaged command.
    for byte in b"bad\nrm " {
        assert!(ring.push(*byte));
    }
    assert!(!ring.push(b'x'));
    assert!(ring.recover_overflow());
    assert!(ring.is_empty());
    assert_eq!(ring.pop(), None);
    assert!(!ring.recover_overflow());
    for byte in b"pwd\n" {
        assert!(ring.push(*byte));
    }
    for byte in b"pwd\n" {
        assert_eq!(ring.pop(), Some(*byte));
    }
    assert_eq!(ring.pop(), None);
}

#[test]
fn fs_create_read() {
    let mut fs = RamFs::new();
    let id = fs.create_file(NodeId::ROOT, "hello").unwrap();
    assert_eq!(fs.lookup(fs.root(), "/hello").unwrap(), id);
    let mut buf = [0; 8];
    assert_eq!(fs.read(id, 0, &mut buf).unwrap(), 0);
}
