//! Main-context shell argument parsing. File data keeps trailing whitespace.

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
    ) {
        return false;
    }
    let result = (|| -> Result<(), FsError> {
        match name {
            "pwd" => {
                if !rest.trim().is_empty() {
                    return Err(FsError::InvalidPath);
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
                    return Err(FsError::NotADirectory);
                }
                *cwd = id;
                out(format_args!("ok\n"));
            }
            "rmdir" => {
                let path = required_path(rest)?;
                if fs.lookup(*cwd, path)? == *cwd {
                    let mut nonempty = false;
                    fs.list(*cwd, &mut |_, _, _| nonempty = true)?;
                    return Err(if nonempty {
                        FsError::DirectoryNotEmpty
                    } else {
                        FsError::InvalidPath
                    });
                }
                fs.remove_dir(*cwd, path)?;
                out(format_args!("ok\n"));
            }
            "touch" => {
                let path = required_path(rest)?;
                match fs.lookup(*cwd, path) {
                    Ok(id) if fs.metadata(id)?.kind == NodeKind::File => {}
                    Ok(_) => return Err(FsError::IsADirectory),
                    Err(FsError::NotFound) => {
                        fs.create_file(*cwd, path)?;
                    }
                    Err(error) => return Err(error),
                }
                out(format_args!("ok\n"));
            }
            "write" | "append" => {
                let (path, data) = split_word(rest);
                let path = required_path(path)?;
                let (id, created) = match fs.lookup(*cwd, path) {
                    Ok(id) => (id, false),
                    Err(FsError::NotFound) if name == "write" => {
                        (fs.create_file(*cwd, path)?, true)
                    }
                    Err(error) => return Err(error),
                };
                let result = if name == "write" {
                    fs.replace(id, data.as_bytes())
                } else {
                    fs.write(id, fs.metadata(id)?.size, data.as_bytes())
                        .map(|_| ())
                };
                if let Err(error) = result {
                    if created {
                        fs.remove_file(*cwd, path)?;
                    }
                    return Err(error);
                }
                out(format_args!("ok\n"));
            }
            "cat" => {
                let id = fs.lookup(*cwd, required_path(rest)?)?;
                cat(fs, id, out)?;
            }
            "ls" => {
                let path = if rest.trim().is_empty() {
                    "."
                } else {
                    required_path(rest)?
                };
                let id = fs.lookup(*cwd, path)?;
                fs.list(id, &mut |name, _, kind| {
                    out(format_args!(
                        "{}{}\n",
                        name,
                        if kind == NodeKind::Directory { "/" } else { "" }
                    ));
                })?;
            }
            "stat" => {
                let id = fs.lookup(*cwd, required_path(rest)?)?;
                let meta = fs.metadata(id)?;
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
                fs.remove_file(*cwd, required_path(rest)?)?;
                out(format_args!("ok\n"));
            }
            _ => unreachable!(),
        }
        Ok(())
    })();
    if let Err(error) = result {
        out(format_args!("fs: {}\n", error));
    }
    true
}

// No infallible temporary allocation, including binary/invalid UTF-8 files.
// UTF-8 scalars are read with at most four bytes; unsafe terminal controls escape.
fn cat(
    fs: &impl crate::fs::Vfs,
    id: crate::fs::NodeId,
    out: &mut dyn FnMut(core::fmt::Arguments<'_>),
) -> Result<(), crate::fs::FsError> {
    if fs.metadata(id)?.kind != crate::fs::NodeKind::File {
        return Err(crate::fs::FsError::IsADirectory);
    }
    let mut offset = 0;
    let mut bytes = [0; 4];
    loop {
        let n = fs.read(id, offset, &mut bytes)?;
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
                offset += width;
                continue;
            }
        }
        out(format_args!("\\x{:02x}", first));
        offset += 1;
    }
    out(format_args!("\n"));
    Ok(())
}

fn required_path(rest: &str) -> Result<&str, crate::fs::FsError> {
    let path = rest.trim();
    if path.is_empty() || path.chars().any(char::is_whitespace) {
        Err(crate::fs::FsError::InvalidPath)
    } else {
        Ok(path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fs::{NodeId, RamFs};

    #[test]
    fn pwd_outputs_root_without_allocating_filesystem_storage() {
        let mut fs = RamFs::new();
        let mut cwd = NodeId::ROOT;
        let mut output = std::string::String::new();
        assert!(run(&mut fs, &mut cwd, "pwd", "", &mut |args| {
            use core::fmt::Write;
            output.write_fmt(args).unwrap();
        }));
        assert_eq!(output, "/\n");
    }

    fn command(fs: &mut RamFs, cwd: &mut NodeId, input: &str) -> std::string::String {
        let (name, rest) = split_word(input);
        let mut output = std::string::String::new();
        assert!(run(fs, cwd, name, rest, &mut |args| {
            use core::fmt::Write;
            output.write_fmt(args).unwrap();
        }));
        output
    }

    #[test]
    fn directory_commands_track_cwd_and_reject_duplicates() {
        let mut fs = RamFs::new();
        let mut cwd = NodeId::ROOT;
        assert_eq!(command(&mut fs, &mut cwd, "mkdir docs"), "ok\n");
        assert_eq!(
            command(&mut fs, &mut cwd, "mkdir docs"),
            "fs: already exists\n"
        );
        assert_eq!(command(&mut fs, &mut cwd, "cd docs"), "ok\n");
        assert_eq!(command(&mut fs, &mut cwd, "pwd"), "/docs\n");
        assert_eq!(command(&mut fs, &mut cwd, "cd .."), "ok\n");
        assert_eq!(command(&mut fs, &mut cwd, "rmdir docs"), "ok\n");
        assert_eq!(command(&mut fs, &mut cwd, "pwd"), "/\n");
    }

    #[test]
    fn file_commands_write_append_list_stat_and_remove() {
        let mut fs = RamFs::new();
        let mut cwd = NodeId::ROOT;
        assert_eq!(command(&mut fs, &mut cwd, "touch hello.txt"), "ok\n");
        assert_eq!(
            command(&mut fs, &mut cwd, "write hello.txt Hello from Rosti OS"),
            "ok\n"
        );
        assert_eq!(command(&mut fs, &mut cwd, "append hello.txt !"), "ok\n");
        assert_eq!(
            command(&mut fs, &mut cwd, "cat hello.txt"),
            "Hello from Rosti OS!\n"
        );
        assert_eq!(command(&mut fs, &mut cwd, "ls"), "hello.txt\n");
        assert_eq!(
            command(&mut fs, &mut cwd, "stat hello.txt"),
            "type: file\nsize: 20 bytes\n"
        );
        assert_eq!(command(&mut fs, &mut cwd, "rm hello.txt"), "ok\n");
        assert_eq!(
            command(&mut fs, &mut cwd, "cat hello.txt"),
            "fs: not found\n"
        );
    }

    #[test]
    fn removing_current_nonempty_directory_reports_not_empty() {
        let mut fs = RamFs::new();
        let mut cwd = NodeId::ROOT;
        command(&mut fs, &mut cwd, "mkdir docs");
        command(&mut fs, &mut cwd, "cd docs");
        command(&mut fs, &mut cwd, "touch a");
        assert_eq!(
            command(&mut fs, &mut cwd, "rmdir /docs"),
            "fs: directory not empty\n"
        );
        assert_eq!(command(&mut fs, &mut cwd, "pwd"), "/docs\n");
    }

    #[test]
    fn failed_shell_write_rolls_back_creation_and_preserves_existing_contents() {
        use crate::fs::Vfs;
        let mut fs = RamFs::new();
        let mut cwd = NodeId::ROOT;
        let before = fs.stats();
        fs.fail_next_allocation();
        assert_eq!(
            command(&mut fs, &mut cwd, "write new data"),
            "fs: out of memory\n"
        );
        assert_eq!(fs.stats(), before);
        assert_eq!(command(&mut fs, &mut cwd, "stat new"), "fs: not found\n");
        command(&mut fs, &mut cwd, "write saved old");
        let before = fs.stats();
        fs.fail_next_allocation();
        assert_eq!(
            command(&mut fs, &mut cwd, "write saved longer"),
            "fs: out of memory\n"
        );
        assert_eq!(fs.stats(), before);
        assert_eq!(command(&mut fs, &mut cwd, "cat saved"), "old\n");
        command(&mut fs, &mut cwd, "touch saved");
        assert_eq!(command(&mut fs, &mut cwd, "cat saved"), "old\n");
    }

    #[test]
    fn shell_handles_utf8_binary_empty_data_types_and_invalid_arguments() {
        use crate::fs::Vfs;
        let mut fs = RamFs::new();
        let mut cwd = NodeId::ROOT;
        let id = fs.create_file(cwd, "data").unwrap();
        fs.replace(id, "猫\n".as_bytes()).unwrap();
        assert_eq!(command(&mut fs, &mut cwd, "cat data"), "猫\n\n");
        fs.replace(id, &[0, 0xff, 0x1b]).unwrap();
        assert_eq!(command(&mut fs, &mut cwd, "cat data"), "\\x00\\xff\\x1b\n");
        assert_eq!(command(&mut fs, &mut cwd, "write data"), "ok\n");
        assert_eq!(command(&mut fs, &mut cwd, "cat data"), "\n");
        assert_eq!(command(&mut fs, &mut cwd, "write data spaces  "), "ok\n");
        assert_eq!(command(&mut fs, &mut cwd, "cat data"), "spaces  \n");
        assert_eq!(
            command(&mut fs, &mut cwd, "append missing x"),
            "fs: not found\n"
        );
        assert_eq!(
            command(&mut fs, &mut cwd, "cd data"),
            "fs: not a directory\n"
        );
        command(&mut fs, &mut cwd, "mkdir dir");
        assert_eq!(
            command(&mut fs, &mut cwd, "touch dir"),
            "fs: is a directory\n"
        );
        assert_eq!(
            command(&mut fs, &mut cwd, "ls data"),
            "fs: not a directory\n"
        );
        assert_eq!(command(&mut fs, &mut cwd, "ls"), "data\ndir/\n");
        for input in ["mkdir", "pwd extra", "rm two paths", "cat", "write"] {
            assert_eq!(command(&mut fs, &mut cwd, input), "fs: invalid path\n");
        }
        assert!(!run(&mut fs, &mut cwd, "help", "", &mut |_| panic!(
            "unexpected filesystem output"
        )));
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
