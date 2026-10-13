//! Main-context shell argument parsing. File data keeps trailing whitespace.
//! Phase 7: file operations route through the capability-aware descriptor
//! layer (Shell -> Descriptor API -> Open Resource -> VFS -> RAMFS). FsError
//! variants keep the existing "fs:" prefix; descriptor-layer errors use "fd:".

use crate::fd::{FdError, FdTable, Rights};

pub fn split_word(input: &str) -> (&str, &str) {
    let input = input.trim_start();
    match input.find(char::is_whitespace) {
        Some(end) => (&input[..end], input[end..].trim_start()),
        None => (input, ""),
    }
}

/// Returns false for commands owned by the existing hardware shell.
pub fn run(
    fs: &mut impl crate::fs::Vfs,
    table: &mut FdTable,
    cwd: &mut crate::fs::NodeId,
    name: &str,
    rest: &str,
    out: &mut dyn FnMut(core::fmt::Arguments<'_>),
) -> bool {
    use crate::fs::{FsError, NodeKind};
    if !matches!(
        name,
        "pwd"
            | "mkdir"
            | "cd"
            | "rmdir"
            | "ls"
            | "touch"
            | "cat"
            | "write"
            | "append"
            | "rm"
            | "stat"
            | "fdlist"
    ) {
        return false;
    }
    // Synchronous commands own only the descriptors they open. Cleanup must
    // also run after disk I/O errors, without closing preexisting handles.
    let mut existing = 0u64;
    table.list(&mut |info| existing |= 1u64 << info.fd);
    let result = (|| -> Result<(), FdError> {
        match name {
            "pwd" => {
                if !rest.trim().is_empty() {
                    return Err(FdError::Fs(FsError::InvalidPath));
                }
                if *cwd == fs.root() {
                    out(format_args!("/\n"));
                } else {
                    let mut path = [0; crate::fs::MAX_PATH];
                    let len = fs.path(*cwd, &mut path)?;
                    let text =
                        core::str::from_utf8(&path[..len]).map_err(|_| FsError::InvalidPath)?;
                    out(format_args!("{}\n", text));
                }
            }
            "mkdir" => {
                fs.create_dir(*cwd, required_path(rest)?)?;
                out(format_args!("ok\n"));
            }
            "cd" => {
                let id = fs.lookup(*cwd, required_path(rest)?)?;
                if fs.metadata(id)?.kind != NodeKind::Directory {
                    return Err(FdError::Fs(FsError::NotADirectory));
                }
                *cwd = id;
                out(format_args!("ok\n"));
            }
            "rmdir" => {
                let path = required_path(rest)?;
                if fs.lookup(*cwd, path)? == *cwd {
                    let mut nonempty = false;
                    fs.list(*cwd, &mut |_, _, _| nonempty = true)?;
                    return Err(FdError::Fs(if nonempty {
                        FsError::DirectoryNotEmpty
                    } else {
                        FsError::InvalidPath
                    }));
                }
                fs.remove_dir(*cwd, path)?;
                out(format_args!("ok\n"));
            }
            "touch" => {
                let path = required_path(rest)?;
                let rights = Rights::new(Rights::STAT | Rights::CREATE);
                match table.open(fs, *cwd, path, rights) {
                    Ok(fd) => {
                        let kind = table.stat(fs, fd)?.kind;
                        table.close(fd)?;
                        if kind != NodeKind::File {
                            return Err(FdError::Fs(FsError::IsADirectory));
                        }
                        out(format_args!("ok\n"));
                    }
                    Err(FdError::Fs(FsError::NotFound)) => {
                        fs.create_file(*cwd, path)?;
                        out(format_args!("ok\n"));
                    }
                    Err(error) => return Err(error),
                }
            }
            "write" | "append" => {
                let (path, data) = split_word(rest);
                let path = required_path(path)?;
                let rights =
                    Rights::new(Rights::WRITE | Rights::STAT | Rights::SEEK | Rights::CREATE);
                let (fd, created) = match table.open(fs, *cwd, path, rights) {
                    Ok(fd) => (fd, false),
                    Err(FdError::Fs(FsError::NotFound)) if name == "write" => {
                        fs.create_file(*cwd, path)?;
                        (table.open(fs, *cwd, path, rights)?, true)
                    }
                    Err(error) => return Err(error),
                };
                let result = if name == "write" {
                    table.replace(fs, fd, data.as_bytes())
                } else {
                    let size = table.stat(fs, fd)?.size; // STAT required for append sizing
                    table.seek(fd, size)?;
                    table.write(fs, fd, data.as_bytes()).map(|_| ())
                };
                if let Err(error) = result {
                    if created {
                        fs.remove_file(*cwd, path)?;
                    }
                    return Err(error);
                }
                table.close(fd)?;
                out(format_args!("ok\n"));
            }
            "cat" => {
                let fd = table.open(
                    fs,
                    *cwd,
                    required_path(rest)?,
                    Rights::new(Rights::READ | Rights::STAT | Rights::SEEK),
                )?;
                cat(fs, table, fd, out)?;
                table.close(fd)?;
            }
            "ls" => {
                let path = if rest.trim().is_empty() {
                    "."
                } else {
                    required_path(rest)?
                };
                let fd = table.open(
                    fs,
                    *cwd,
                    path,
                    Rights::new(Rights::DIRECTORY_READ | Rights::STAT),
                )?;
                let id = table.node(fd)?;
                fs.list(id, &mut |name, _, kind| {
                    out(format_args!(
                        "{}{}\n",
                        name,
                        if kind == NodeKind::Directory { "/" } else { "" }
                    ));
                })?;
                table.close(fd)?;
            }
            "stat" => {
                let fd = table.open(fs, *cwd, required_path(rest)?, Rights::new(Rights::STAT))?;
                let meta = table.stat(fs, fd)?;
                table.close(fd)?;
                out(format_args!(
                    "type: {}\nsize: {} bytes\n",
                    if meta.kind == NodeKind::File {
                        "file"
                    } else {
                        "directory"
                    },
                    meta.size
                ));
            }
            "rm" => {
                let path = required_path(rest)?;
                let fd = table.open(fs, *cwd, path, Rights::new(Rights::DELETE))?;
                fs.remove_file(*cwd, path)?;
                table.close(fd)?;
                out(format_args!("ok\n"));
            }
            "fdlist" => {
                if !rest.trim().is_empty() {
                    return Err(FdError::Fs(FsError::InvalidPath));
                }
                table.list(&mut |info| {
                    out(format_args!(
                        "fd {} {} rights {} offset {} refs {}\n",
                        info.fd,
                        info.kind.label(),
                        rights_mask(info.rights),
                        info.offset,
                        info.refs
                    ));
                });
            }
            _ => unreachable!(),
        }
        Ok(())
    })();
    let mut opened = 0u64;
    table.list(&mut |info| opened |= 1u64 << info.fd);
    let new = opened & !existing;
    for fd in 0..64u8 {
        if new & (1u64 << fd) != 0 {
            let _ = table.close(fd);
        }
    }
    if let Err(error) = result {
        match error {
            FdError::Fs(e) => out(format_args!("fs: {}\n", e)),
            e => out(format_args!("fd: {}\n", e)),
        }
    }
    true
}

fn rights_mask(rights: Rights) -> u8 {
    rights.mask()
}

// No infallible temporary allocation, including binary/invalid UTF-8 files.
// Reads go through the descriptor layer in bounded 128-byte batches. Refill
// from the current scalar when fewer than four peek bytes remain in a full
// batch, so UTF-8 and invalid-byte escaping are unchanged at buffer boundaries.
// Realign after every scalar to preserve final/shared offsets and SEEK checks.
fn cat(
    fs: &impl crate::fs::Vfs,
    table: &mut FdTable,
    fd: u8,
    out: &mut dyn FnMut(core::fmt::Arguments<'_>),
) -> Result<(), FdError> {
    if table.stat(fs, fd)?.kind != crate::fs::NodeKind::File {
        return Err(FdError::Fs(crate::fs::FsError::IsADirectory));
    }
    let mut bytes = [0; 128];
    // A descriptor without SEEK must retain the old four-byte read advance
    // before its first scalar is printed and the realignment is denied.
    let capacity = if table.info(fd)?.rights.allows(Rights::SEEK) {
        bytes.len()
    } else {
        4
    };
    let mut n = 0;
    let mut cursor = 0;
    loop {
        let start = table.info(fd)?.offset;
        if cursor == n || (n == capacity && n - cursor < 4) {
            n = table.read(fs, fd, &mut bytes[..capacity])?;
            cursor = 0;
            if n == 0 {
                break;
            }
        }
        let first = bytes[cursor];
        let width = match first {
            0..=0x7f => 1,
            0xc2..=0xdf => 2,
            0xe0..=0xef => 3,
            0xf0..=0xf4 => 4,
            _ => 0,
        };
        if width != 0
            && width <= n - cursor
            && (first >= 32 || first == b'\n' || first == b'\t')
            && first != 127
        {
            if let Ok(text) = core::str::from_utf8(&bytes[cursor..cursor + width]) {
                out(format_args!("{}", text));
                table.seek(fd, start + width)?;
                cursor += width;
                continue;
            }
        }
        out(format_args!("\\x{:02x}", first));
        table.seek(fd, start + 1)?;
        cursor += 1;
    }
    out(format_args!("\n"));
    Ok(())
}

fn required_path(rest: &str) -> Result<&str, FdError> {
    let path = rest.trim();
    if path.is_empty() || path.chars().any(char::is_whitespace) {
        Err(FdError::Fs(crate::fs::FsError::InvalidPath))
    } else {
        Ok(path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fd::FdTable;
    use crate::fs::{NodeId, RamFs, Vfs};

    // Real portable-core fixture: count sectors only after format/mount/write.
    struct CatDevice {
        bytes: std::vec::Vec<u8>,
        reads: std::rc::Rc<core::cell::Cell<usize>>,
        fail_at: std::rc::Rc<core::cell::Cell<Option<usize>>>,
    }

    impl rostifs::block::BlockDevice for CatDevice {
        fn sector_size(&self) -> usize {
            512
        }
        fn capacity_sectors(&self) -> usize {
            self.bytes.len() / 512
        }
        fn test_owned(&self) -> bool {
            true
        }
        fn flush(&mut self) -> Result<(), rostifs::block::BlockError> {
            Ok(())
        }
        fn read_sector(
            &mut self,
            lba: usize,
            buf: &mut [u8],
        ) -> Result<(), rostifs::block::BlockError> {
            let count = self.reads.get();
            self.reads.set(count + 1);
            if self.fail_at.get() == Some(count) {
                return Err(rostifs::block::BlockError::Rejected);
            }
            buf.copy_from_slice(&self.bytes[lba * 512..(lba + 1) * 512]);
            Ok(())
        }
        fn write_sector(
            &mut self,
            lba: usize,
            data: &[u8],
        ) -> Result<(), rostifs::block::BlockError> {
            assert_ne!(lba, 0);
            self.bytes[lba * 512..(lba + 1) * 512].copy_from_slice(data);
            Ok(())
        }
    }

    fn portable_cat_fixture(
        data: &[u8],
    ) -> (
        crate::fs::RostiBackend<'static>,
        std::rc::Rc<core::cell::Cell<usize>>,
        std::rc::Rc<core::cell::Cell<Option<usize>>>,
    ) {
        let reads = std::rc::Rc::new(core::cell::Cell::new(0));
        let fail_at = std::rc::Rc::new(core::cell::Cell::new(None));
        let mut device = CatDevice {
            bytes: std::vec![0; 32 * 4096],
            reads: reads.clone(),
            fail_at: fail_at.clone(),
        };
        rostifs::engine::RostiFs::format(&mut device, 0x9500).unwrap();
        let mut fs =
            crate::fs::RostiBackend::new(std::boxed::Box::leak(std::boxed::Box::new(device)));
        fs.mount_in_place().unwrap();
        let file = fs.create_file(NodeId::ROOT, "data").unwrap();
        fs.replace(file, data).unwrap();
        reads.set(0);
        (fs, reads, fail_at)
    }

    #[test]
    fn cat_portable_ascii_uses_one_block_read() {
        let (mut fs, reads, _) = portable_cat_fixture(&[b'a'; 64]);
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        let mut output = std::string::String::new();
        run(&mut fs, &mut table, &mut cwd, "cat", "data", &mut |args| {
            use core::fmt::Write;
            output.write_fmt(args).unwrap();
        });
        assert_eq!(output, format!("{}\n", "a".repeat(64)));
        assert_eq!(table.stats().open_slots, 0);
        assert_eq!(table.stats().open_records, 0);
        assert_eq!(
            reads.get(),
            8,
            "one 4 KiB block, not 64 scalar peeks (512 sectors)"
        );
    }

    #[test]
    fn cat_buffer_boundaries_preserve_utf8_invalid_and_truncated_bytes() {
        // Start each sequence one, two, or three bytes before the 128-byte edge.
        let cases: &[(&[u8], &str)] = &[
            ("é".as_bytes(), "é"),
            ("猫".as_bytes(), "猫"),
            ("🦀".as_bytes(), "🦀"),
            (&[0xe2, b'(', 0xa1], "\\xe2(\\xa1"),
            (&[0xf0, 0x80, 0x80, 0x80], "\\xf0\\x80\\x80\\x80"),
            (&[0xed, 0xa0, 0x80], "\\xed\\xa0\\x80"),
            (&[0xf4, 0x90, 0x80, 0x80], "\\xf4\\x90\\x80\\x80"),
            (&[0xc0, 0xaf, 0xff], "\\xc0\\xaf\\xff"),
            (&[0xe2], "\\xe2"),
            (&[0xe2, 0x82], "\\xe2\\x82"),
            (&[0xf0, 0x9f, 0xa6], "\\xf0\\x9f\\xa6"),
            (
                &[0, 0x1b, 0x7f, b'\r', b'\n', b'\t'],
                "\\x00\\x1b\\x7f\\x0d\n\t",
            ),
            ("\u{0085}".as_bytes(), "\u{0085}"), // Existing multibyte control policy.
        ];
        let mut fs = RamFs::new();
        let file = fs.create_file(NodeId::ROOT, "data").unwrap();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        for prefix in [125, 126, 127, 128, 253, 254, 255] {
            for &(bytes, escaped) in cases {
                for suffix in ["", "猫\n\tend"] {
                    let mut data = std::vec![b'a'; prefix];
                    data.extend_from_slice(bytes);
                    data.extend_from_slice(suffix.as_bytes());
                    fs.replace(file, &data).unwrap();
                    assert_eq!(
                        command(&mut fs, &mut table, &mut cwd, "cat data"),
                        format!("{}{}{}\n", "a".repeat(prefix), escaped, suffix),
                        "prefix={prefix}, bytes={bytes:?}, suffix={suffix:?}"
                    );
                    assert_eq!(table.stats().open_slots, 0);
                }
            }
        }
    }

    #[test]
    fn cat_preserves_rights_denials_and_final_shared_offsets() {
        let mut fs = RamFs::new();
        let file = fs.create_file(NodeId::ROOT, "data").unwrap();
        fs.replace(file, &[b'a'; 260]).unwrap();
        for (mask, expected, offset) in [
            (
                Rights::READ | Rights::STAT | Rights::SEEK,
                "a".repeat(257) + "\n",
                260,
            ),
            (Rights::STAT | Rights::SEEK, std::string::String::new(), 3),
            (Rights::READ | Rights::SEEK, std::string::String::new(), 3),
            (Rights::READ | Rights::STAT, "a".into(), 7),
        ] {
            let mut table = FdTable::new();
            let fd = table
                .open(
                    &fs,
                    NodeId::ROOT,
                    "data",
                    Rights::new(Rights::READ | Rights::STAT | Rights::SEEK),
                )
                .unwrap();
            table.seek(fd, 3).unwrap();
            let shared = table.dup(fd, mask).unwrap();
            let mut output = std::string::String::new();
            let result = cat(&fs, &mut table, shared, &mut |args| {
                use core::fmt::Write;
                output.write_fmt(args).unwrap();
            });
            if mask == Rights::READ | Rights::STAT | Rights::SEEK {
                assert_eq!(result, Ok(()));
            } else {
                assert_eq!(result, Err(FdError::PermissionDenied));
            }
            assert_eq!(output, expected);
            assert_eq!(table.info(fd).unwrap().offset, offset);
            assert_eq!(table.info(shared).unwrap().offset, offset);
        }
    }

    #[test]
    fn cat_portable_read_failure_closes_only_owned_descriptor() {
        for (failure, prefix) in [(0, 0), (8, 125)] {
            let (mut fs, reads, fail_at) = portable_cat_fixture(&[b'a'; 260]);
            let mut table = FdTable::new();
            table.init_console();
            let keep = table
                .open(
                    &fs,
                    NodeId::ROOT,
                    "data",
                    Rights::new(Rights::READ | Rights::SEEK),
                )
                .unwrap();
            table.seek(keep, 9).unwrap();
            let duplicate = table.dup(keep, Rights::READ).unwrap();
            let before = table.stats();
            fail_at.set(Some(failure));
            let mut cwd = NodeId::ROOT;
            let mut output = std::string::String::new();
            run(&mut fs, &mut table, &mut cwd, "cat", "data", &mut |args| {
                use core::fmt::Write;
                output.write_fmt(args).unwrap();
            });
            assert_eq!(output, "a".repeat(prefix) + "fs: device I/O error\n");
            assert_eq!(reads.get(), failure + 1);
            assert_eq!(table.stats().open_slots, before.open_slots);
            assert_eq!(table.stats().open_records, before.open_records);
            assert_eq!(table.stats().opens, before.opens + 1);
            assert_eq!(table.stats().closes, before.closes + 1);
            assert_eq!(table.info(keep).unwrap().offset, 9);
            assert_eq!(table.info(duplicate).unwrap().offset, 9);
        }
    }

    #[test]
    fn failing_shell_operations_close_only_command_owned_descriptors() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        table.init_console();
        let mut cwd = NodeId::ROOT;
        fs.create_dir(cwd, "dir").unwrap();
        fs.create_file(cwd, "keep").unwrap();
        let keep = table
            .open(&mut fs, cwd, "keep", Rights::new(Rights::READ))
            .unwrap();
        for (command, path) in [
            ("cat", "dir"),
            ("write", "dir data"),
            ("ls", "keep"),
            ("rm", "dir"),
        ] {
            run(&mut fs, &mut table, &mut cwd, command, path, &mut |_| {});
            assert!(table.info(keep).is_ok());
            let mut count = 0;
            table.list(&mut |_| count += 1);
            assert_eq!(count, 4);
        }
        table.close(keep).unwrap();
    }

    #[test]
    fn pwd_outputs_root_without_allocating_filesystem_storage() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        let mut output = std::string::String::new();
        assert!(run(&mut fs, &mut table, &mut cwd, "pwd", "", &mut |args| {
            use core::fmt::Write;
            output.write_fmt(args).unwrap();
        }));
        assert_eq!(output, "/\n");
    }

    fn command(
        fs: &mut RamFs,
        table: &mut FdTable,
        cwd: &mut NodeId,
        input: &str,
    ) -> std::string::String {
        let (name, rest) = split_word(input);
        let mut output = std::string::String::new();
        assert!(run(fs, table, cwd, name, rest, &mut |args| {
            use core::fmt::Write;
            output.write_fmt(args).unwrap();
        }));
        output
    }

    #[test]
    fn directory_commands_track_cwd_and_reject_duplicates() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "mkdir docs"), "ok\n");
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "mkdir docs"),
            "fs: already exists\n"
        );
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "cd docs"), "ok\n");
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "pwd"), "/docs\n");
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "cd .."), "ok\n");
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "rmdir docs"), "ok\n");
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "pwd"), "/\n");
    }

    #[test]
    fn file_commands_write_append_list_stat_and_remove() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "touch hello.txt"),
            "ok\n"
        );
        assert_eq!(
            command(
                &mut fs,
                &mut table,
                &mut cwd,
                "write hello.txt Hello from Rosti OS"
            ),
            "ok\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "append hello.txt !"),
            "ok\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "cat hello.txt"),
            "Hello from Rosti OS!\n"
        );
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "ls"), "hello.txt\n");
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "stat hello.txt"),
            "type: file\nsize: 20 bytes\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "rm hello.txt"),
            "ok\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "cat hello.txt"),
            "fs: not found\n"
        );
    }

    #[test]
    fn shell_file_commands_route_through_the_descriptor_layer() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        command(&mut fs, &mut table, &mut cwd, "touch f");
        command(&mut fs, &mut table, &mut cwd, "write f abc");
        command(&mut fs, &mut table, &mut cwd, "cat f");
        // Every file command opens and closes exactly one descriptor.
        // (touch on a missing path creates through the VFS directly, so only
        // the write and cat dispatches count as descriptor opens here.)
        let stats = table.stats();
        assert_eq!(stats.opens, 2); // write, cat
        assert_eq!(stats.closes, 2);
        assert_eq!(stats.open_slots, 0); // nothing left open after dispatch
        assert_eq!(stats.open_records, 0);
    }

    #[test]
    fn fdlist_reports_open_descriptors_and_denied_rights() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        table.init_console();
        fs.create_file(cwd, "f").unwrap();
        let fd = table
            .open(&fs, cwd, "f", Rights::new(Rights::READ | Rights::STAT))
            .unwrap();
        table.write(&mut fs, fd, b"x").unwrap_err(); // denied, counted
        let out = command(&mut fs, &mut table, &mut cwd, "fdlist");
        assert!(out.contains("fd 0 console-in"));
        assert!(out.contains(&format!("fd {} file", fd)));
        assert!(out.contains("rights 9")); // READ|STAT
        assert!(out.contains("offset 0")); // denied write must not advance the offset
        assert_eq!(table.stats().denials, 1);
    }

    #[test]
    fn removing_current_nonempty_directory_reports_not_empty() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        command(&mut fs, &mut table, &mut cwd, "mkdir docs");
        command(&mut fs, &mut table, &mut cwd, "cd docs");
        command(&mut fs, &mut table, &mut cwd, "touch a");
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "rmdir /docs"),
            "fs: directory not empty\n"
        );
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "pwd"), "/docs\n");
    }

    #[test]
    fn failed_shell_write_rolls_back_creation_and_preserves_existing_contents() {
        use crate::fs::Vfs;
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        let before = fs.stats();
        fs.fail_next_allocation();
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "write new data"),
            "fs: out of memory\n"
        );
        assert_eq!(fs.stats(), before);
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "stat new"),
            "fs: not found\n"
        );
        command(&mut fs, &mut table, &mut cwd, "write saved old");
        let before = fs.stats();
        fs.fail_next_allocation();
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "write saved longer"),
            "fs: out of memory\n"
        );
        assert_eq!(fs.stats(), before);
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "cat saved"), "old\n");
        command(&mut fs, &mut table, &mut cwd, "touch saved");
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "cat saved"), "old\n");
    }

    #[test]
    fn shell_handles_utf8_binary_empty_data_types_and_invalid_arguments() {
        use crate::fs::Vfs;
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        let mut cwd = NodeId::ROOT;
        let id = fs.create_file(cwd, "data").unwrap();
        fs.replace(id, "猫\n".as_bytes()).unwrap();
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "cat data"), "猫\n\n");
        fs.replace(id, &[0, 0xff, 0x1b]).unwrap();
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "cat data"),
            "\\x00\\xff\\x1b\n"
        );
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "write data"), "ok\n");
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "cat data"), "\n");
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "write data spaces  "),
            "ok\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "cat data"),
            "spaces  \n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "append missing x"),
            "fs: not found\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "cd data"),
            "fs: not a directory\n"
        );
        command(&mut fs, &mut table, &mut cwd, "mkdir dir");
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "touch dir"),
            "fs: is a directory\n"
        );
        assert_eq!(
            command(&mut fs, &mut table, &mut cwd, "ls data"),
            "fs: not a directory\n"
        );
        assert_eq!(command(&mut fs, &mut table, &mut cwd, "ls"), "data\ndir/\n");
        for input in ["mkdir", "pwd extra", "rm two paths", "cat", "write"] {
            assert_eq!(
                command(&mut fs, &mut table, &mut cwd, input),
                "fs: invalid path\n"
            );
        }
        assert!(!run(
            &mut fs,
            &mut table,
            &mut cwd,
            "help",
            "",
            &mut |_| panic!("unexpected filesystem output")
        ));
    }

    #[test]
    fn command_words_accept_whitespace_and_preserve_file_data() {
        assert_eq!(
            split_word(" \twrite\tfile hello  "),
            ("write", "file hello  ")
        );
        assert_eq!(split_word("file hello  "), ("file", "hello  "));
        assert_eq!(split_word("pwd"), ("pwd", ""));
        assert_eq!(split_word(" \t "), ("", ""));
    }
}
