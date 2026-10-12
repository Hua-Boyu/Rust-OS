//! Phase 7: capability-aware file descriptors and generational kernel handles.
//!
//! Contract (documented in ARCHITECTURE.md):
//! - `Handle` is an internal generational reference (slot + generation), never
//!   a kernel pointer exposed to callers. Stale handles fail after slot reuse;
//!   exhausted generations are retired, never wrapped (no ABA aliasing).
//! - `OpenFile` is an open-file description: the shared offset lives here, so
//!   duplicated descriptors share it through the same handle.
//! - `Descriptor` is a per-context slot holding a handle plus an explicit
//!   capability mask. Rights are default-deny; duplication can only attenuate.
//! - Open resources are reference-counted; the last close releases the record
//!   and bumps its generation, invalidating every handle to it.
//! - Node bindings are generation-checked through the VFS, so a deleted file
//!   makes open descriptors fail cleanly instead of dangling.
//! - Static tables, zero allocation on any fd path: 64 descriptor slots
//!   (asserted <= 16 bytes each) + 64 open records (asserted <= 24 bytes each)
//!   = <= 2,560 bytes fixed overhead plus counters; on i686 the actual sizes
//!   are smaller. Exhaustion returns an error; it cannot fragment the heap
//!   or corrupt filesystem metadata. Lock order: descriptor table -> VFS.
//!   No fd operation allocates, so the heap -> frame order is never crossed.
//!   ISRs must not touch this subsystem (SpinMutex is not interrupt-safe).

use crate::fs::{FsError, Metadata, NodeId, NodeKind, Vfs};
use core::fmt;

pub const MAX_DESCRIPTORS: usize = 64;
pub const MAX_HANDLES: usize = 64;

// Conventional context descriptors, wired to the console at boot.
pub const STDIN: u8 = 0;
pub const STDOUT: u8 = 1;
pub const STDERR: u8 = 2;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rights(u8);

impl Rights {
    pub const READ: u8 = 1 << 0;
    pub const WRITE: u8 = 1 << 1;
    pub const SEEK: u8 = 1 << 2;
    pub const STAT: u8 = 1 << 3;
    pub const DIRECTORY_READ: u8 = 1 << 4;
    pub const CREATE: u8 = 1 << 5;
    pub const DELETE: u8 = 1 << 6;
    pub const MAP: u8 = 1 << 7; // reserved for future file-backed mappings

    pub const fn new(mask: u8) -> Self {
        Self(mask)
    }
    pub const fn allows(&self, bit: u8) -> bool {
        self.0 & bit != 0
    }
    /// Attenuation only: `other` must be a subset of the current mask, so
    /// duplication can never escalate rights.
    pub const fn attenuate(&self, other: u8) -> Option<Self> {
        if other & !self.0 != 0 {
            None
        } else {
            Some(Self(other))
        }
    }
    pub const fn mask(&self) -> u8 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Handle {
    pub slot: u8,
    pub generation: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResourceKind {
    File,
    Directory,
    ConsoleInput,
    ConsoleOutput,
    // Reserved for later phases: Pipe, Socket, Device.
}

impl ResourceKind {
    pub const fn label(&self) -> &'static str {
        match self {
            Self::File => "file",
            Self::Directory => "dir",
            Self::ConsoleInput => "console-in",
            Self::ConsoleOutput => "console-out",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DescriptorInfo {
    pub fd: u8,
    pub handle: Handle,
    pub kind: ResourceKind,
    pub rights: Rights,
    pub offset: usize,
    pub refs: u8,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FdError {
    InvalidHandle,
    StaleHandle,
    InvalidDescriptor,
    PermissionDenied,
    TableFull,
    NotOpen,
    ResourceMismatch,
    OffsetOverflow,
    Fs(FsError),
}

impl fmt::Display for FdError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidHandle => f.write_str("invalid handle"),
            Self::StaleHandle => f.write_str("stale handle"),
            Self::InvalidDescriptor => f.write_str("invalid descriptor"),
            Self::PermissionDenied => f.write_str("permission denied"),
            Self::TableFull => f.write_str("descriptor table full"),
            Self::NotOpen => f.write_str("resource not open"),
            Self::ResourceMismatch => f.write_str("resource type mismatch"),
            Self::OffsetOverflow => f.write_str("offset overflow"),
            Self::Fs(e) => e.fmt(f),
        }
    }
}

impl From<FsError> for FdError {
    fn from(e: FsError) -> Self {
        Self::Fs(e)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct OpenFile {
    /// Node binding captured at open time. Generation-checked through the VFS,
    /// so deletion invalidates the binding instead of dangling.
    node: NodeId,
    offset: usize,
    refs: u8,
    generation: u32,
    in_use: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Slot {
    handle: Handle,
    kind: ResourceKind,
    rights: Rights,
    /// Index into the open-file table for filesystem resources.
    open: Option<u8>,
    in_use: bool,
}

/// Operation counters: deterministic proof that dispatch went through the
/// descriptor layer, and a resource-budget diagnostic for the shell.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct FdStats {
    pub opens: usize,
    pub closes: usize,
    pub denials: usize,
    pub stale_rejections: usize,
    pub open_slots: usize,
    pub open_records: usize,
}

const fn handle(slot: usize, generation: u32) -> Handle {
    Handle {
        slot: slot as u8,
        generation,
    }
}

pub struct FdTable {
    descriptors: [Slot; MAX_DESCRIPTORS],
    opens: [OpenFile; MAX_HANDLES],
    stats: FdStats,
}

impl FdTable {
    pub const fn new() -> Self {
        Self {
            descriptors: [const {
                Slot {
                    handle: handle(0, 0),
                    kind: ResourceKind::ConsoleInput,
                    rights: Rights::new(0),
                    open: None,
                    in_use: false,
                }
            }; MAX_DESCRIPTORS],
            opens: [const {
                OpenFile {
                    node: NodeId::ROOT,
                    offset: 0,
                    refs: 0,
                    generation: 0,
                    in_use: false,
                }
            }; MAX_HANDLES],
            stats: FdStats {
                opens: 0,
                closes: 0,
                denials: 0,
                stale_rejections: 0,
                open_slots: 0,
                open_records: 0,
            },
        }
    }

    /// Wire conventional descriptors to the console. Filesystem rights are
    /// default-deny; only the shell's console writer uses these slots.
    pub fn init_console(&mut self) {
        // Conventional descriptors: 0 stdin, 1 stdout, 2 stderr.
        for (fd, kind) in [
            (STDIN, ResourceKind::ConsoleInput),
            (STDOUT, ResourceKind::ConsoleOutput),
            (STDERR, ResourceKind::ConsoleOutput),
        ] {
            let _ = self.install(fd, kind, Rights::new(0));
        }
    }

    fn install(&mut self, fd: u8, kind: ResourceKind, rights: Rights) -> Result<u8, FdError> {
        let i = fd as usize;
        if i >= MAX_DESCRIPTORS {
            return Err(FdError::InvalidDescriptor);
        }
        let slot = &mut self.descriptors[i];
        if slot.in_use {
            return Err(FdError::InvalidDescriptor);
        }
        slot.handle = handle(i, slot.handle.generation + 1);
        slot.kind = kind;
        slot.rights = rights;
        slot.open = None;
        slot.in_use = true;
        self.stats.open_slots += 1;
        Ok(fd)
    }

    /// Open a resource. `rights` is the caller's intended mask; the table
    /// never grants rights it was not given.
    pub fn open(
        &mut self,
        fs: &impl Vfs,
        cwd: NodeId,
        path: &str,
        rights: Rights,
    ) -> Result<u8, FdError> {
        let node = fs.lookup(cwd, path)?;
        let kind = match fs.metadata(node)?.kind {
            NodeKind::File => ResourceKind::File,
            NodeKind::Directory => ResourceKind::Directory,
        };
        let fd = self.allocate_descriptor(kind, rights)?;
        let open_index = self.allocate_open(node)?;
        let slot = &mut self.descriptors[fd as usize];
        slot.open = Some(open_index);
        // The descriptor handle points at the open record, so a stale handle
        // can never alias a reused record.
        slot.handle = handle(
            open_index as usize,
            self.opens[open_index as usize].generation,
        );
        self.stats.opens += 1;
        Ok(fd)
    }

    fn allocate_descriptor(&mut self, kind: ResourceKind, rights: Rights) -> Result<u8, FdError> {
        let i = (0..MAX_DESCRIPTORS)
            .find(|&i| {
                !self.descriptors[i].in_use && self.descriptors[i].handle.generation != u32::MAX
            })
            .ok_or(FdError::TableFull)?;
        let slot = &mut self.descriptors[i];
        slot.handle = handle(i, slot.handle.generation + 1);
        slot.kind = kind;
        slot.rights = rights;
        slot.open = None;
        slot.in_use = true;
        self.stats.open_slots += 1;
        Ok(i as u8)
    }

    fn allocate_open(&mut self, node: NodeId) -> Result<u8, FdError> {
        // Generation rollover safety: a slot whose generation is exhausted is
        // retired forever, so a stale handle can never alias a new resource.
        let i = (0..MAX_HANDLES)
            .find(|&i| !self.opens[i].in_use && self.opens[i].generation != u32::MAX)
            .ok_or(FdError::TableFull)?;
        let open = &mut self.opens[i];
        open.node = node;
        open.offset = 0;
        open.refs = 1;
        open.generation += 1;
        open.in_use = true;
        self.stats.open_records += 1;
        Ok(i as u8)
    }

    pub(crate) fn resolve(&mut self, h: Handle) -> Result<&OpenFile, FdError> {
        let i = h.slot as usize;
        if i >= MAX_HANDLES {
            return Err(FdError::InvalidHandle);
        }
        let open = &self.opens[i];
        if !open.in_use {
            return Err(FdError::InvalidHandle);
        }
        if open.generation != h.generation {
            self.stats.stale_rejections += 1;
            return Err(FdError::StaleHandle);
        }
        Ok(open)
    }

    fn descriptor(&self, fd: u8) -> Result<&Slot, FdError> {
        let slot = self
            .descriptors
            .get(fd as usize)
            .ok_or(FdError::InvalidDescriptor)?;
        if !slot.in_use {
            return Err(FdError::InvalidDescriptor);
        }
        Ok(slot)
    }

    /// Snapshot the descriptor + open record so the VFS call and the offset
    /// mutation never hold overlapping borrows of the table.
    fn bound(
        &mut self,
        fd: u8,
        required: u8,
    ) -> Result<(u8, NodeId, usize, ResourceKind), FdError> {
        let slot = *self.descriptor(fd)?;
        if !slot.rights.allows(required) {
            self.stats.denials += 1;
            return Err(FdError::PermissionDenied);
        }
        let open_index = slot.open.ok_or(FdError::NotOpen)?;
        let open = *self.resolve(slot.handle)?;
        Ok((open_index, open.node, open.offset, slot.kind))
    }

    pub fn read(&mut self, fs: &impl Vfs, fd: u8, buf: &mut [u8]) -> Result<usize, FdError> {
        let (open_index, node, offset, kind) = self.bound(fd, Rights::READ)?;
        if kind != ResourceKind::File {
            return Err(FdError::ResourceMismatch);
        }
        let n = fs.read(node, offset, buf)?;
        // Offset advances only by bytes actually delivered (EOF stops).
        self.opens[open_index as usize].offset = offset + n;
        Ok(n)
    }

    pub fn write(&mut self, fs: &mut impl Vfs, fd: u8, data: &[u8]) -> Result<usize, FdError> {
        let (open_index, node, offset, kind) = self.bound(fd, Rights::WRITE)?;
        if kind != ResourceKind::File {
            return Err(FdError::ResourceMismatch);
        }
        let end = offset
            .checked_add(data.len())
            .ok_or(FdError::OffsetOverflow)?;
        let n = fs.write(node, offset, data)?;
        if n == data.len() {
            let _ = end; // checked arithmetic gate; bytes delivered advance the offset
        }
        self.opens[open_index as usize].offset = offset + n;
        Ok(n)
    }

    pub fn truncate(&mut self, fs: &mut impl Vfs, fd: u8, len: usize) -> Result<(), FdError> {
        let (open_index, node, _, kind) = self.bound(fd, Rights::WRITE)?;
        if kind != ResourceKind::File {
            return Err(FdError::ResourceMismatch);
        }
        fs.truncate(node, len)?;
        self.opens[open_index as usize].offset = len;
        Ok(())
    }

    /// Atomic content replacement through the capability check. Kept as a
    /// single VFS transaction so shell rollback semantics stay intact.
    pub fn replace(&mut self, fs: &mut impl Vfs, fd: u8, data: &[u8]) -> Result<(), FdError> {
        let (_, node, _, kind) = self.bound(fd, Rights::WRITE)?;
        if kind != ResourceKind::File {
            return Err(FdError::ResourceMismatch);
        }
        fs.replace(node, data).map_err(FdError::Fs)
    }

    pub fn seek(&mut self, fd: u8, offset: usize) -> Result<(), FdError> {
        let (open_index, _, _, kind) = self.bound(fd, Rights::SEEK)?;
        if kind != ResourceKind::File {
            return Err(FdError::ResourceMismatch);
        }
        self.opens[open_index as usize].offset = offset;
        Ok(())
    }

    pub fn stat(&mut self, fs: &impl Vfs, fd: u8) -> Result<Metadata, FdError> {
        let (_, node, _, _) = self.bound(fd, Rights::STAT)?;
        fs.metadata(node).map_err(FdError::Fs)
    }

    /// Duplicate a descriptor. `request` must be a subset of the source mask
    /// (attenuation only — a read-only descriptor cannot become writable).
    /// The duplicate shares the open-file description, including its offset.
    pub fn dup(&mut self, fd: u8, request: u8) -> Result<u8, FdError> {
        let source = self.descriptor(fd)?;
        let rights = source
            .rights
            .attenuate(request)
            .ok_or(FdError::PermissionDenied)?;
        let open_index = source.open.ok_or(FdError::NotOpen)?;
        let source_handle = source.handle;
        let kind = source.kind;
        let new_fd = self.allocate_descriptor(kind, rights)?;
        let open = &mut self.opens[open_index as usize];
        open.refs = open.refs.checked_add(1).ok_or(FdError::TableFull)?;
        let slot = &mut self.descriptors[new_fd as usize];
        slot.open = Some(open_index);
        slot.handle = source_handle; // shared open-file description
        Ok(new_fd)
    }

    /// Close a descriptor. The open-file description survives until the last
    /// descriptor referencing it closes; double close is rejected explicitly.
    pub fn close(&mut self, fd: u8) -> Result<(), FdError> {
        let slot = self.descriptor(fd)?;
        let open_index = slot.open;
        let slot = &mut self.descriptors[fd as usize];
        slot.in_use = false;
        slot.open = None;
        if open_index.is_none() {
            slot.handle = handle(fd as usize, slot.handle.generation + 1);
        }
        self.stats.open_slots -= 1;
        self.stats.closes += 1;
        if let Some(i) = open_index {
            let open = &mut self.opens[i as usize];
            open.refs -= 1;
            if open.refs == 0 {
                open.in_use = false;
                open.generation += 1; // stale handles to this record now fail
                self.stats.open_records -= 1;
            }
        }
        Ok(())
    }

    pub fn info(&self, fd: u8) -> Result<DescriptorInfo, FdError> {
        let slot = self.descriptor(fd)?;
        let (offset, refs) = match slot.open {
            Some(i) => (self.opens[i as usize].offset, self.opens[i as usize].refs),
            None => (0, 0),
        };
        Ok(DescriptorInfo {
            fd,
            handle: slot.handle,
            kind: slot.kind,
            rights: slot.rights,
            offset,
            refs,
        })
    }

    pub(crate) fn node(&mut self, fd: u8) -> Result<NodeId, FdError> {
        let slot = self.descriptor(fd)?;
        let _open_index = slot.open.ok_or(FdError::NotOpen)?;
        Ok(self.resolve(slot.handle)?.node)
    }

    pub fn stats(&self) -> FdStats {
        self.stats
    }

    /// Visit every open descriptor in slot order (fdlist diagnostics).
    pub fn list(&self, visitor: &mut dyn FnMut(&DescriptorInfo)) {
        for fd in 0..MAX_DESCRIPTORS as u8 {
            if let Ok(info) = self.info(fd) {
                visitor(&info);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fs::{NodeId, RamFs, Vfs};

    fn file_rights() -> Rights {
        Rights::new(Rights::READ | Rights::WRITE | Rights::SEEK | Rights::STAT)
    }

    fn opened(fs: &mut RamFs, table: &mut FdTable, path: &str, rights: Rights) -> u8 {
        table.open(fs, NodeId::ROOT, path, rights).unwrap()
    }

    #[test]
    fn descriptor_allocation_and_slot_reuse() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        assert_eq!(fd, 0);
        assert_eq!(table.stats().open_slots, 1);
        table.close(fd).unwrap();
        assert_eq!(table.stats().open_slots, 0);
        assert_eq!(opened(&mut fs, &mut table, "f", file_rights()), 0);
    }

    #[test]
    fn generation_rejects_stale_handles_and_invalid_indexes() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        let handle_at_open = table.info(fd).unwrap().handle;
        table.close(fd).unwrap();
        // Released record: the handle no longer resolves.
        assert_eq!(table.resolve(handle_at_open), Err(FdError::InvalidHandle));
        // Reusing the slot bumps the generation: the old handle is stale.
        let fd2 = opened(&mut fs, &mut table, "f", file_rights());
        assert_eq!(table.resolve(handle_at_open), Err(FdError::StaleHandle));
        assert_eq!(table.stats().stale_rejections, 1);
        assert_ne!(table.info(fd2).unwrap().handle, handle_at_open);
        assert_eq!(
            table.resolve(Handle {
                slot: MAX_HANDLES as u8,
                generation: 0
            }),
            Err(FdError::InvalidHandle)
        );
    }

    #[test]
    fn generation_rollover_retires_exhausted_slots() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        // A slot whose generation is exhausted is retired, never wrapped:
        // allocation must skip it, and its stale handle must fail.
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        let handle_at_open = table.info(fd).unwrap().handle;
        table.opens[handle_at_open.slot as usize].generation = u32::MAX - 1;
        table.close(fd).unwrap(); // last close bumps to MAX: retired
        let mut fresh = FdTable::new();
        fresh.opens[0].generation = u32::MAX;
        assert_eq!(fresh.allocate_open(NodeId::ROOT), Ok(1));
        assert_eq!(table.resolve(handle_at_open), Err(FdError::InvalidHandle));
    }

    #[test]
    fn double_close_and_invalid_descriptor_rejected() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        table.close(fd).unwrap();
        assert_eq!(table.close(fd), Err(FdError::InvalidDescriptor));
        assert_eq!(table.info(200), Err(FdError::InvalidDescriptor));
    }

    #[test]
    fn table_exhaustion_is_clean_and_recoverable() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        for _ in 0..MAX_DESCRIPTORS {
            let fd = opened(&mut fs, &mut table, "f", file_rights());
            assert!(fd < MAX_DESCRIPTORS as u8);
        }
        assert_eq!(
            table.open(&fs, NodeId::ROOT, "f", file_rights()),
            Err(FdError::TableFull)
        );
        table.close(0).unwrap();
        assert_eq!(opened(&mut fs, &mut table, "f", file_rights()), 0);
    }

    #[test]
    fn read_write_seek_eof_track_shared_offset() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        assert_eq!(table.write(&mut fs, fd, b"hello").unwrap(), 5);
        table.seek(fd, 0).unwrap();
        let mut buf = [0; 8];
        assert_eq!(table.read(&fs, fd, &mut buf).unwrap(), 5);
        assert_eq!(&buf[..5], b"hello");
        assert_eq!(table.read(&fs, fd, &mut buf).unwrap(), 0); // EOF
        table.seek(fd, 2).unwrap();
        assert_eq!(table.read(&fs, fd, &mut buf[..1]).unwrap(), 1);
        assert_eq!(buf[0], b'l');
        assert_eq!(table.info(fd).unwrap().offset, 3);
    }

    #[test]
    fn duplication_shares_offset_and_can_only_attenuate() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        assert_eq!(table.dup(fd, Rights::MAP), Err(FdError::PermissionDenied)); // escalation
        let ro = table.dup(fd, Rights::READ | Rights::STAT).unwrap();
        table.write(&mut fs, fd, b"abc").unwrap();
        assert_eq!(table.info(ro).unwrap().offset, 3); // shared open description
        assert_eq!(table.info(fd).unwrap().offset, 3);
        assert_eq!(table.seek(ro, 0), Err(FdError::PermissionDenied)); // no SEEK on ro
        assert_eq!(
            table.write(&mut fs, ro, b"x"),
            Err(FdError::PermissionDenied)
        );
        table.seek(fd, 0).unwrap(); // shared offset moves for both descriptors
        table.close(fd).unwrap(); // refcount keeps the read-only view alive
        let mut buf = [0; 4];
        assert_eq!(table.read(&fs, ro, &mut buf).unwrap(), 3);
        assert_eq!(table.info(ro).unwrap().refs, 1);
        table.close(ro).unwrap(); // last close releases the record
        assert_eq!(table.info(ro), Err(FdError::InvalidDescriptor));
    }

    #[test]
    fn default_deny_and_type_mismatch_rules() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        fs.create_dir(NodeId::ROOT, "d").unwrap();
        let ro = opened(&mut fs, &mut table, "f", Rights::new(Rights::READ));
        assert_eq!(
            table.write(&mut fs, ro, b"x"),
            Err(FdError::PermissionDenied)
        );
        assert_eq!(table.seek(ro, 0), Err(FdError::PermissionDenied));
        assert_eq!(table.stat(&fs, ro), Err(FdError::PermissionDenied));
        let dir = opened(
            &mut fs,
            &mut table,
            "d",
            Rights::new(Rights::DIRECTORY_READ | Rights::STAT | Rights::READ | Rights::WRITE),
        );
        assert_eq!(
            table.read(&fs, dir, &mut [0; 1]),
            Err(FdError::ResourceMismatch)
        );
        assert_eq!(
            table.write(&mut fs, dir, b"x"),
            Err(FdError::ResourceMismatch)
        );
        assert_eq!(table.stat(&fs, dir).unwrap().kind, NodeKind::Directory);
    }

    #[test]
    fn deletion_while_open_fails_cleanly_and_releases_on_close() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        table.write(&mut fs, fd, b"data").unwrap();
        fs.remove_file(NodeId::ROOT, "f").unwrap();
        // Unlink semantics: the node binding is generation-checked, so reads
        // on the open descriptor report not-found instead of dangling.
        assert_eq!(
            table.read(&fs, fd, &mut [0; 4]),
            Err(FdError::Fs(FsError::NotFound))
        );
        table.close(fd).unwrap();
        assert_eq!(table.stats().open_slots, 0);
        assert_eq!(table.stats().open_records, 0);
    }

    #[test]
    fn console_descriptors_are_reserved_and_default_deny() {
        let mut table = FdTable::new();
        table.init_console();
        assert_eq!(table.info(0).unwrap().kind, ResourceKind::ConsoleInput);
        assert_eq!(table.info(1).unwrap().kind, ResourceKind::ConsoleOutput);
        assert_eq!(table.info(2).unwrap().kind, ResourceKind::ConsoleOutput);
        assert_eq!(table.info(0).unwrap().rights, Rights::new(0));
        table.close(1).unwrap();
        assert_eq!(table.info(1), Err(FdError::InvalidDescriptor));
    }

    #[test]
    fn repeated_open_close_cycles_leak_nothing() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        for _ in 0..256 {
            let fd = opened(&mut fs, &mut table, "f", file_rights());
            table.write(&mut fs, fd, b"x").unwrap();
            table.close(fd).unwrap();
        }
        assert_eq!(table.stats().open_slots, 0);
        assert_eq!(table.stats().open_records, 0);
        assert_eq!(fs.stats().allocated_bytes, 1); // only the file's own data
    }

    #[test]
    fn offset_overflow_is_checked() {
        let mut fs = RamFs::new();
        let mut table = FdTable::new();
        fs.create_file(NodeId::ROOT, "f").unwrap();
        let fd = opened(&mut fs, &mut table, "f", file_rights());
        table.seek(fd, usize::MAX).unwrap();
        assert_eq!(table.write(&mut fs, fd, b"x"), Err(FdError::OffsetOverflow));
    }

    #[test]
    fn static_table_resource_budget() {
        // Documented i686 budget: 64 slots x 10 bytes + 64 records x 12 bytes
        // = 704 bytes fixed, plus counters. Host (x86_64) sizes are upper
        // bounds; no fd path allocates from the kernel heap.
        assert!(core::mem::size_of::<Slot>() <= 16);
        assert!(core::mem::size_of::<OpenFile>() <= 24);
        assert!(
            core::mem::size_of::<FdTable>() <= 64 * 16 + 64 * 24 + core::mem::size_of::<FdStats>()
        );
    }
}
