use super::*;
use crate::initramfs::{
    initramfs_tests::{append, fixture, gnu_fixture},
    parse,
};
use alloc::{format, vec, vec::Vec};

fn sample() -> Vec<u8> {
    // Child-before-parent, implicit multi-level parents and explicit directory.
    fixture(&[
        (0o100644, b"sub/deep/note.txt", b"note"),
        (0o40755, b"sub", b""),
        (0o100755, b"hello.txt", b"hello rosti"),
        (0o100644, b"empty.txt", b""),
        (0o40700, b"other", b""),
    ])
}
fn built(bytes: &[u8]) -> ArchiveFs {
    let mut fs = ArchiveFs::empty();
    assert!(fs.build(&parse(bytes).unwrap(), bytes));
    fs
}
fn contents(fs: &ArchiveFs, id: NodeId) -> Vec<u8> {
    let mut buf = vec![0; fs.metadata(id).unwrap().size];
    assert_eq!(fs.read(id, 0, &mut buf).unwrap(), buf.len());
    buf
}
#[test]
fn independent_gnu_archive_is_readable_after_source_drop() {
    let mut bytes = gnu_fixture();
    let fs = built(&bytes);
    bytes.fill(0);
    drop(bytes);
    let id = fs.lookup(fs.root(), "hello.txt").unwrap();
    assert_eq!(contents(&fs, id), b"hello rosti");
    assert_eq!(
        fs.metadata(id),
        Ok(Metadata {
            kind: NodeKind::File,
            size: 11
        })
    );
}
#[test]
fn root_empty_unbuilt_and_trailer_only_are_real_directories() {
    for fs in [ArchiveFs::empty(), built(&fixture(&[]))] {
        assert_eq!(fs.stats().nodes, 1);
        assert_eq!(
            fs.metadata(fs.root()),
            Ok(Metadata {
                kind: NodeKind::Directory,
                size: 0
            })
        );
        assert_eq!(fs.lookup(fs.root(), "/../../."), Ok(fs.root()));
        let mut count = 0;
        fs.list(fs.root(), &mut |_, _, _| count += 1).unwrap();
        assert_eq!(count, 0);
        assert_eq!(fs.path(fs.root(), &mut []), Err(FsError::InvalidPath));
        let mut buf = [42; 2];
        assert_eq!(fs.path(fs.root(), &mut buf), Ok(1));
        assert_eq!(&buf, b"/*");
        assert_eq!(fs.read(fs.root(), 0, &mut []), Err(FsError::IsADirectory));
    }
}
#[test]
fn root_listing_skips_root_and_nested_children() {
    let fs = built(&sample());
    let mut names = Vec::new();
    fs.list(fs.root(), &mut |name, id, kind| {
        assert_eq!(fs.lookup(fs.root(), name), Ok(id));
        assert_eq!(fs.metadata(id).unwrap().kind, kind);
        names.push(name.to_owned());
    })
    .unwrap();
    assert_eq!(names, ["sub", "hello.txt", "empty.txt", "other"]);
    let sub = fs.lookup(fs.root(), "sub").unwrap();
    let mut names = Vec::new();
    fs.list(sub, &mut |name, _, _| names.push(name.to_owned()))
        .unwrap();
    assert_eq!(names, ["deep"]);
    assert_eq!(fs.stats().nodes, 7);
}
#[test]
fn relative_semantic_traversal_matches_ramfs_conventions() {
    let fs = built(&sample());
    let root = fs.root();
    let sub = fs.lookup(root, "sub").unwrap();
    let deep = fs.lookup(sub, "deep").unwrap();
    let note = fs.lookup(deep, "note.txt").unwrap();
    assert_eq!(fs.lookup(sub, "./deep//note.txt"), Ok(note));
    assert_eq!(fs.lookup(deep, "../deep/note.txt"), Ok(note));
    assert_eq!(fs.lookup(deep, "/hello.txt"), fs.lookup(root, "hello.txt"));
    assert_eq!(fs.lookup(root, "//sub//deep//"), Ok(deep));
    for path in [
        "sub/deep/note.txt/..",
        "sub/deep/note.txt/.",
        "hello.txt/",
        "hello.txt/missing",
    ] {
        assert_eq!(fs.lookup(root, path), Err(FsError::NotADirectory));
    }
    assert_eq!(fs.lookup(note, "."), Err(FsError::NotADirectory));
    assert_eq!(fs.lookup(note, "/"), Ok(root));
    assert_eq!(fs.lookup(root, "missing"), Err(FsError::NotFound));
    for path in ["", "a\x1b", "a\x7f"] {
        assert_eq!(fs.lookup(root, path), Err(FsError::InvalidPath));
    }
    assert_eq!(
        fs.lookup(root, &"a".repeat(MAX_PATH + 1)),
        Err(FsError::InvalidPath)
    );
    assert_eq!(
        fs.lookup(root, &"a".repeat(MAX_NAME + 1)),
        Err(FsError::InvalidPath)
    );
}
#[test]
fn reads_are_bounded_partial_eof_and_do_not_touch_sentinels() {
    let fs = built(&sample());
    let id = fs.lookup(fs.root(), "hello.txt").unwrap();
    let mut buf = [0xa5; 16];
    assert_eq!(fs.read(id, 3, &mut buf), Ok(8));
    assert_eq!(&buf[..8], b"lo rosti");
    assert_eq!(&buf[8..], &[0xa5; 8]);
    for off in [11, 12, usize::MAX] {
        let mut buf = [0xa5; 2];
        assert_eq!(fs.read(id, off, &mut buf), Ok(0));
        assert_eq!(buf, [0xa5; 2]);
    }
    assert_eq!(fs.read(id, 0, &mut []), Ok(0));
    let empty = fs.lookup(fs.root(), "empty.txt").unwrap();
    assert_eq!(fs.read(empty, usize::MAX, &mut buf), Ok(0));
    assert_eq!(
        fs.list(id, &mut |_, _, _| panic!("file visitor")),
        Err(FsError::NotADirectory)
    );
}
#[test]
fn path_roundtrips_and_short_buffers_are_unchanged() {
    let fs = built(&sample());
    for name in ["/", "/sub", "/sub/deep", "/sub/deep/note.txt", "/hello.txt"] {
        let id = fs.lookup(fs.root(), name).unwrap();
        let mut short = vec![0xa5; name.len() - 1];
        assert_eq!(fs.path(id, &mut short), Err(FsError::InvalidPath));
        assert!(short.iter().all(|&b| b == 0xa5));
        let mut buf = [0xa5; MAX_PATH];
        let len = fs.path(id, &mut buf).unwrap();
        assert_eq!(&buf[..len], name.as_bytes());
        assert!(buf[len..].iter().all(|&b| b == 0xa5));
        assert_eq!(
            fs.lookup(fs.root(), core::str::from_utf8(&buf[..len]).unwrap()),
            Ok(id)
        );
    }
}
#[test]
fn every_mutation_is_read_only_and_preserves_data_and_accounting() {
    let mut fs = built(&sample());
    let id = fs.lookup(fs.root(), "hello.txt").unwrap();
    let stats = fs.stats();
    assert_eq!(fs.write(id, usize::MAX, b"x"), Err(FsError::ReadOnly));
    assert_eq!(fs.write(id, 0, b""), Err(FsError::ReadOnly));
    assert_eq!(fs.replace(id, b"x"), Err(FsError::ReadOnly));
    assert_eq!(fs.truncate(id, 0), Err(FsError::ReadOnly));
    assert_eq!(fs.create_file(fs.root(), "new"), Err(FsError::ReadOnly));
    assert_eq!(fs.create_dir(fs.root(), "new"), Err(FsError::ReadOnly));
    assert_eq!(
        fs.remove_file(fs.root(), "hello.txt"),
        Err(FsError::ReadOnly)
    );
    assert_eq!(fs.remove_dir(fs.root(), "sub"), Err(FsError::ReadOnly));
    assert_eq!(contents(&fs, id), b"hello rosti");
    assert_eq!(fs.stats(), stats);
    assert_eq!(format!("{}", FsError::ReadOnly), "read-only filesystem");
}
fn assert_invalid(fs: &mut ArchiveFs, id: NodeId) {
    assert_eq!(fs.metadata(id), Err(FsError::NotFound));
    assert_eq!(fs.read(id, usize::MAX, &mut []), Err(FsError::NotFound));
    assert_eq!(
        fs.list(id, &mut |_, _, _| panic!("invalid visitor")),
        Err(FsError::NotFound)
    );
    assert_eq!(fs.path(id, &mut [0; MAX_PATH]), Err(FsError::NotFound));
    assert_eq!(fs.lookup(id, "/"), Err(FsError::NotFound));
    assert_eq!(fs.write(id, 0, b""), Err(FsError::NotFound));
    assert_eq!(fs.replace(id, b""), Err(FsError::NotFound));
    assert_eq!(fs.truncate(id, 0), Err(FsError::NotFound));
    assert_eq!(fs.create_file(id, "x"), Err(FsError::NotFound));
    assert_eq!(fs.create_dir(id, "x"), Err(FsError::NotFound));
    assert_eq!(fs.remove_file(id, "x"), Err(FsError::NotFound));
    assert_eq!(fs.remove_dir(id, "x"), Err(FsError::NotFound));
}
#[test]
fn forged_handles_cannot_panic_or_alias_root() {
    let mut fs = built(&sample());
    for id in [
        NodeId {
            slot: 0,
            generation: 1,
        },
        NodeId {
            slot: 0,
            generation: u32::MAX,
        },
        NodeId {
            slot: 1,
            generation: 0,
        },
        NodeId {
            slot: 7,
            generation: 1,
        },
        NodeId {
            slot: 64,
            generation: 1,
        },
        NodeId {
            slot: u16::MAX,
            generation: 1,
        },
    ] {
        assert_invalid(&mut fs, id);
    }
    for slot in 7..=u16::MAX {
        assert_eq!(
            fs.metadata(NodeId {
                slot,
                generation: 1
            }),
            Err(FsError::NotFound)
        );
    }
    let mut empty = ArchiveFs::empty();
    assert_invalid(
        &mut empty,
        NodeId {
            slot: 1,
            generation: 0,
        },
    );
}
#[test]
fn successful_rebuild_revokes_old_ids_and_replaces_not_appends() {
    let mut fs = built(&sample());
    let old = fs.lookup(fs.root(), "sub").unwrap();
    let bytes = gnu_fixture();
    assert!(fs.build(&parse(&bytes).unwrap(), &bytes));
    assert_invalid(&mut fs, old);
    assert_eq!(fs.stats().nodes, 2);
    assert_eq!(fs.total_payload(), 11);
    let new = fs.lookup(fs.root(), "hello.txt").unwrap();
    assert_ne!(old, new);
    let bytes = fixture(&[]);
    assert!(fs.build(&parse(&bytes).unwrap(), &bytes));
    assert_invalid(&mut fs, new);
    assert_eq!(fs.stats().nodes, 1);
}
#[test]
fn every_reservation_refusal_preserves_existing_snapshot() {
    let mut fs = built(&sample());
    let id = fs.lookup(fs.root(), "hello.txt").unwrap();
    let old_stats = fs.stats();
    let bytes = gnu_fixture();
    let index = parse(&bytes).unwrap();
    for allocation in 0..3 {
        fs.fail_reserve_at = Some(allocation);
        assert_eq!(fs.try_build(&index, &bytes), Err(FsError::OutOfMemory));
        assert_eq!(fs.stats(), old_stats);
        assert_eq!(contents(&fs, id), b"hello rosti");
    }
    assert!(fs.build(&index, &bytes));
    assert_invalid(&mut fs, id);
}
#[test]
fn forged_indexes_and_mismatched_buffers_fail_atomically() {
    let mut fs = built(&sample());
    let stats = fs.stats();
    let bytes = gnu_fixture();
    let index = parse(&bytes).unwrap();
    for which in 0..5 {
        let mut forged = index.clone();
        match which {
            0 => forged.entries[0].name_len = u16::MAX,
            1 => forged.entries[0].offset = u32::MAX,
            2 => forged.entries[0].size = u32::MAX,
            3 => forged.entries[0].dir = true,
            _ => forged.total_bytes = usize::MAX,
        }
        assert_eq!(fs.try_build(&forged, &bytes), Err(FsError::CorruptVolume));
        assert_eq!(fs.stats(), stats);
    }
    assert_eq!(
        fs.try_build(&index, &bytes[..100]),
        Err(FsError::CorruptVolume)
    );
    let mut bad = bytes.clone();
    bad[0] = b'x';
    assert_eq!(fs.try_build(&index, &bad), Err(FsError::CorruptVolume));
    assert_eq!(fs.stats(), stats);
}
#[test]
fn implicit_node_limit_exact_boundary_and_late_failure_are_atomic() {
    let path = vec!["a"; MAX_ARCHIVE_NODES - 1].join("/");
    let mut bytes = Vec::new();
    append(&mut bytes, 0o100644, path.as_bytes(), b"x");
    let mut full = bytes.clone();
    append(&mut full, 0, b"TRAILER!!!", b"");
    let mut fs = built(&full);
    assert_eq!(fs.stats().nodes, MAX_ARCHIVE_NODES);
    let id = fs.lookup(fs.root(), &path).unwrap();
    let mut buf = [0; MAX_PATH];
    let len = fs.path(id, &mut buf).unwrap();
    assert_eq!(&buf[..len], format!("/{path}").as_bytes());
    let old_stats = fs.stats();
    append(&mut bytes, 0o100644, b"extra", b"y");
    append(&mut bytes, 0, b"TRAILER!!!", b"");
    assert_eq!(
        fs.try_build(&parse(&bytes).unwrap(), &bytes),
        Err(FsError::FilesystemFull)
    );
    assert_eq!(fs.stats(), old_stats);
    assert_eq!(contents(&fs, id), b"x");
}
#[test]
fn generation_exhaustion_never_wraps_or_revokes_on_failure() {
    let mut fs = built(&sample());
    fs.generation = u32::MAX - 1;
    let bytes = gnu_fixture();
    let index = parse(&bytes).unwrap();
    assert!(fs.build(&index, &bytes));
    let id = fs.lookup(fs.root(), "hello.txt").unwrap();
    assert_eq!(id.generation, u32::MAX);
    let stats = fs.stats();
    assert_eq!(fs.try_build(&index, &bytes), Err(FsError::FilesystemFull));
    assert_eq!(fs.stats(), stats);
    assert_eq!(contents(&fs, id), b"hello rosti");
}
#[test]
fn maximum_canonical_path_roundtrips_at_vfs_boundary() {
    let path = [
        "a".repeat(63),
        "b".repeat(63),
        "c".repeat(63),
        "d".repeat(63),
    ]
    .join("/");
    let bytes = fixture(&[(0o100644, path.as_bytes(), b"x")]);
    let fs = built(&bytes);
    let absolute = format!("/{path}");
    assert_eq!(absolute.len(), MAX_PATH);
    let id = fs.lookup(fs.root(), &absolute).unwrap();
    let mut buf = [0; MAX_PATH];
    assert_eq!(fs.path(id, &mut buf), Ok(MAX_PATH));
    assert_eq!(&buf, absolute.as_bytes());
}
#[test]
fn stats_separate_capacity_metadata_and_payload_bounds() {
    let fs = built(&sample());
    let stats = fs.stats();
    assert_eq!(stats.logical_bytes, 15);
    assert_eq!(stats.allocated_bytes, fs.payload.capacity());
    assert!(stats.allocated_bytes <= MAX_ARCHIVE_BYTES);
    assert_eq!(
        stats.metadata_bytes,
        core::mem::size_of::<ArchiveFs>() + fs.nodes.capacity() * core::mem::size_of::<Node>()
    );
    assert!(fs.nodes.capacity() <= MAX_ARCHIVE_NODES - 1);
    assert_eq!(fs.persistent_info(), None);
}
