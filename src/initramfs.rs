//! Bounded, non-executable CPIO newc (070701) index.
//!
//! All thirteen fields are ASCII hex, not octal text. Only regular files
//! (one link) and directories are supported. Paths are printable ASCII,
//! canonical relative paths with no dot/dotdot components.
//! Padding is required to be zero. After TRAILER!!!, optional zero block
//! padding is accepted (newc itself does not require a 512-byte block size).
//! This is structural validation, not authentication or a checksum format.
use alloc::vec::Vec;
use core::{
    fmt,
    sync::atomic::{AtomicU8, Ordering},
};

#[cfg(test)]
#[path = "../tests_kernel/src/initramfs_tests.rs"]
pub(crate) mod initramfs_tests;

pub const MAX_ENTRIES: usize = 32;
pub const MAX_NAME: usize = 63;
pub const MAX_PATH: usize = 256; // includes the leading slash in VFS paths
pub const MAX_FILE_SIZE: usize = 64 * 1024;
pub const MAX_ARCHIVE_BYTES: usize = 256 * 1024;
const HEADER: usize = 110;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum ArchiveError {
    Magic = 1,
    Truncated,
    Field,
    Alignment,
    Path,
    Duplicate,
    Type,
    Size,
    Limit,
    Trailer,
    OutOfMemory,
}
impl fmt::Display for ArchiveError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Magic => "bad magic",
            Self::Truncated => "truncated archive",
            Self::Field => "malformed header field",
            Self::Alignment => "invalid padding",
            Self::Path => "invalid path",
            Self::Duplicate => "duplicate path",
            Self::Type => "unsupported type or link",
            Self::Size => "invalid entry size",
            Self::Limit => "archive limit exceeded",
            Self::OutOfMemory => "archive index allocation failed",
            Self::Trailer => "invalid trailer",
        })
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Entry {
    pub name: [u8; MAX_PATH],
    pub name_len: u16,
    pub dir: bool,
    pub offset: u32,
    pub size: u32,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Archive {
    pub entries: Vec<Entry>,
    pub total_bytes: usize,
}
static OUTCOME: AtomicU8 = AtomicU8::new(0);
fn decode(code: u8) -> Option<ArchiveError> {
    Some(match code {
        1 => ArchiveError::Magic,
        2 => ArchiveError::Truncated,
        3 => ArchiveError::Field,
        4 => ArchiveError::Alignment,
        5 => ArchiveError::Path,
        6 => ArchiveError::Duplicate,
        7 => ArchiveError::Type,
        8 => ArchiveError::Size,
        9 => ArchiveError::Limit,
        10 => ArchiveError::Trailer,
        11 => ArchiveError::OutOfMemory,
        _ => return None,
    })
}
pub fn outcome() -> Option<ArchiveError> {
    decode(OUTCOME.load(Ordering::Acquire))
}
fn record_into(target: &AtomicU8, error: ArchiveError) -> ArchiveError {
    let _ = target.compare_exchange(0, error as u8, Ordering::AcqRel, Ordering::Acquire);
    error
}
pub(crate) fn record(error: ArchiveError) -> ArchiveError {
    record_into(&OUTCOME, error)
}
pub fn parse(bytes: &[u8]) -> Result<Archive, ArchiveError> {
    parse_inner(bytes, false).map_err(record)
}
fn hex8(bytes: &[u8]) -> Result<u32, ArchiveError> {
    let mut value = 0;
    for &c in bytes {
        let digit = match c {
            b'0'..=b'9' => c - b'0',
            b'a'..=b'f' => c - b'a' + 10,
            b'A'..=b'F' => c - b'A' + 10,
            _ => return Err(ArchiveError::Field),
        };
        value = (value << 4) | u32::from(digit);
    }
    Ok(value)
}
fn padded(bytes: &[u8], end: usize) -> Result<usize, ArchiveError> {
    let next = end.checked_add(3).ok_or(ArchiveError::Truncated)? & !3;
    let padding = bytes.get(end..next).ok_or(ArchiveError::Truncated)?;
    if padding.iter().any(|&b| b != 0) {
        return Err(ArchiveError::Alignment);
    }
    Ok(next)
}
fn valid_path(name: &[u8]) -> bool {
    !name.is_empty()
        && name.len() < MAX_PATH
        && name.iter().all(|&c| (0x20..=0x7e).contains(&c))
        && name
            .split(|&c| c == b'/')
            .all(|p| !p.is_empty() && p.len() <= MAX_NAME && p != b"." && p != b"..")
}
fn prefix(parent: &[u8], child: &[u8]) -> bool {
    child.starts_with(parent) && child.get(parent.len()) == Some(&b'/')
}
// The refusal switch exercises the exact reserve error path without a global
// allocator or shared test state. There is one bounded allocation in the parser.
fn parse_inner(bytes: &[u8], refuse_reserve: bool) -> Result<Archive, ArchiveError> {
    if bytes.len() > MAX_ARCHIVE_BYTES {
        return Err(ArchiveError::Limit);
    }
    let mut entries: Vec<Entry> = Vec::new();
    if refuse_reserve {
        return Err(ArchiveError::OutOfMemory);
    }
    entries
        .try_reserve_exact(MAX_ENTRIES)
        .map_err(|_| ArchiveError::OutOfMemory)?;
    if entries.capacity() > MAX_ENTRIES {
        return Err(ArchiveError::Limit);
    }
    let mut off: usize = 0;
    loop {
        let end = off.checked_add(HEADER).ok_or(ArchiveError::Truncated)?;
        let h = bytes.get(off..end).ok_or(ArchiveError::Truncated)?;
        if &h[..6] != b"070701" {
            return Err(ArchiveError::Magic);
        }
        let mut fields = [0u32; 13];
        for (i, field) in fields.iter_mut().enumerate() {
            *field = hex8(&h[6 + i * 8..14 + i * 8])?;
        }
        // ino, mode, uid, gid, nlink, mtime, filesize, devmajor,
        // devminor, rdevmajor, rdevminor, namesize, check.
        let (mode, links, size, namesize) = (fields[1], fields[4], fields[6], fields[11]);
        if fields[12] != 0 {
            return Err(ArchiveError::Field);
        }
        if namesize == 0 || namesize as usize > MAX_PATH + 1 {
            return Err(ArchiveError::Path);
        }
        let name_end = end
            .checked_add(namesize as usize)
            .ok_or(ArchiveError::Truncated)?;
        let terminated = bytes.get(end..name_end).ok_or(ArchiveError::Truncated)?;
        if terminated.last() != Some(&0) {
            return Err(ArchiveError::Path);
        }
        let name = &terminated[..terminated.len() - 1];
        let data_start = padded(bytes, name_end)?;
        if name == b"TRAILER!!!" {
            if size != 0 || mode != 0 || bytes[data_start..].iter().any(|&b| b != 0) {
                return Err(ArchiveError::Trailer);
            }
            return Ok(Archive {
                entries,
                total_bytes: bytes.len(),
            });
        }
        let dir = match mode & 0o170000 {
            0o100000 if links == 1 => false,
            0o040000 if links != 0 => true,
            _ => return Err(ArchiveError::Type),
        };
        if mode & !0o177777 != 0 {
            return Err(ArchiveError::Type);
        }
        if !valid_path(name) {
            return Err(ArchiveError::Path);
        }
        if size as usize > MAX_FILE_SIZE || (dir && size != 0) {
            return Err(ArchiveError::Size);
        }
        if entries.len() == MAX_ENTRIES {
            return Err(ArchiveError::Limit);
        }
        for e in &entries {
            let old = &e.name[..e.name_len as usize];
            if old == name {
                return Err(ArchiveError::Duplicate);
            }
            if (!e.dir && prefix(old, name)) || (!dir && prefix(name, old)) {
                return Err(ArchiveError::Path);
            }
        }
        let data_end = data_start
            .checked_add(size as usize)
            .ok_or(ArchiveError::Truncated)?;
        bytes
            .get(data_start..data_end)
            .ok_or(ArchiveError::Truncated)?;
        off = padded(bytes, data_end)?;
        let mut entry = Entry {
            name: [0; MAX_PATH],
            name_len: name.len() as u16,
            dir,
            offset: data_start as u32,
            size,
        };
        entry.name[..name.len()].copy_from_slice(name);
        entries.push(entry);
    }
}
