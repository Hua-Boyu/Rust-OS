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
// Reads go through the descriptor layer; UTF-8 scalars are read with at most
// four bytes; unsafe terminal controls escape. The descriptor offset is realigned
// to the scalar boundary after each peek so shared offsets stay correct.
fn cat(
    fs: &impl crate::fs::Vfs,
    table: &mut FdTable,
    fd: u8,
    out: &mut dyn FnMut(core::fmt::Arguments<'_>),
) -> Result<(), FdError> {
    if table.stat(fs, fd)?.kind != crate::fs::NodeKind::File {
        return Err(FdError::Fs(crate::fs::FsError::IsADirectory));
    }
    let mut bytes = [0; 4];
    loop {
        let start = table.info(fd)?.offset;
        let n = table.read(fs, fd, &mut bytes)?;
        if n == 0 {
            break;
        }
        let first = bytes[0];
        let width = match first {
            0..=0x7f => 1,
            0xc2..=0xdf => 2,
            0xe0..=0xef => 3,
            0xf0..=0xf4 => 4,
            _ => 0,
        };
        if width != 0
            && width <= n
            && (first >= 32 || first == b'\n' || first == b'\t')
            && first != 127
        {
            if let Ok(text) = core::str::from_utf8(&bytes[..width]) {
                out(format_args!("{}", text));
                table.seek(fd, start + width)?;
                continue;
            }
        }
        out(format_args!("\\x{:02x}", first));
        table.seek(fd, start + 1)?;
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
