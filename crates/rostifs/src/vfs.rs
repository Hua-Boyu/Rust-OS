//! Shared VFS contract used by the kernel and RostiFS. Kept in the portable
//! crate so host tools and the kernel use the same definitions.

use core::fmt;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NodeId {
    pub(crate) slot: u8,
    pub(crate) generation: u32,
}
impl NodeId {
    pub const ROOT: Self = Self {
        slot: 0,
        generation: 0,
    };
    pub const fn new(slot: u8, generation: u32) -> Self {
        Self { slot, generation }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NodeKind {
    File,
    Directory,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Metadata {
    pub kind: NodeKind,
    pub size: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FsStats {
    pub nodes: usize,
    pub logical_bytes: usize,
    pub allocated_bytes: usize,
    pub metadata_bytes: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FsError {
    NotFound,
    AlreadyExists,
    NotADirectory,
    IsADirectory,
    DirectoryNotEmpty,
    OutOfMemory,
    FilesystemFull,
    FileTooLarge,
    InvalidPath,
    /// RostiFS additions (Phase 9).
    CorruptVolume,
    UnsupportedVersion,
    DeviceIo,
}

impl fmt::Display for FsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::NotFound => "not found",
            Self::AlreadyExists => "already exists",
            Self::NotADirectory => "not a directory",
            Self::IsADirectory => "is a directory",
            Self::DirectoryNotEmpty => "directory not empty",
            Self::OutOfMemory => "out of memory",
            Self::FilesystemFull => "filesystem full",
            Self::FileTooLarge => "file too large",
            Self::InvalidPath => "invalid path",
            Self::CorruptVolume => "corrupt volume",
            Self::UnsupportedVersion => "unsupported format version",
            Self::DeviceIo => "device I/O error",
        })
    }
}

pub trait Vfs {
    fn root(&self) -> NodeId;
    fn lookup(&self, cwd: NodeId, path: &str) -> Result<NodeId, FsError>;
    fn create_file(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError>;
    fn create_dir(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError>;
    fn metadata(&self, id: NodeId) -> Result<Metadata, FsError>;
    fn read(&self, id: NodeId, offset: usize, buf: &mut [u8]) -> Result<usize, FsError>;
    fn write(&mut self, id: NodeId, offset: usize, data: &[u8]) -> Result<usize, FsError>;
    fn replace(&mut self, id: NodeId, data: &[u8]) -> Result<(), FsError>;
    fn truncate(&mut self, id: NodeId, len: usize) -> Result<(), FsError>;
    fn remove_file(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError>;
    fn remove_dir(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError>;
    fn list(
        &self,
        id: NodeId,
        visitor: &mut dyn FnMut(&str, NodeId, NodeKind),
    ) -> Result<(), FsError>;
    fn path(&self, id: NodeId, buf: &mut [u8]) -> Result<usize, FsError>;
    fn stats(&self) -> FsStats;
}
