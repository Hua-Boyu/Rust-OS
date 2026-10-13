//! Portable VFS adapter. Opaque portable node identities are interned rather
//! than layout-cast, preserving both type independence and stale bindings.
use super::*;
use core::cell::Cell;
use portable::Vfs as PortableVfs;
use rostifs::vfs as portable;

pub struct RostiBackend<'a> {
    core: rostifs::engine::RostiFs<'a>,
    bindings: [Cell<Option<portable::NodeId>>; 64],
    generations: [Cell<u32>; 64],
}
pub(crate) fn error(e: portable::FsError) -> FsError {
    match e {
        portable::FsError::NotFound => FsError::NotFound,
        portable::FsError::AlreadyExists => FsError::AlreadyExists,
        portable::FsError::NotADirectory => FsError::NotADirectory,
        portable::FsError::IsADirectory => FsError::IsADirectory,
        portable::FsError::DirectoryNotEmpty => FsError::DirectoryNotEmpty,
        portable::FsError::OutOfMemory => FsError::OutOfMemory,
        portable::FsError::FilesystemFull => FsError::FilesystemFull,
        portable::FsError::FileTooLarge => FsError::FileTooLarge,
        portable::FsError::InvalidPath => FsError::InvalidPath,
        portable::FsError::CorruptVolume => FsError::CorruptVolume,
        portable::FsError::UnsupportedVersion => FsError::UnsupportedVersion,
        portable::FsError::DeviceIo => FsError::DeviceIo,
    }
}
fn kind(k: portable::NodeKind) -> NodeKind {
    match k {
        portable::NodeKind::File => NodeKind::File,
        portable::NodeKind::Directory => NodeKind::Directory,
    }
}
impl<'a> RostiBackend<'a> {
    /// Declare this with a const initializer in static storage. Do not construct
    /// it at runtime on the 16 KiB kernel stack: the core owns large arrays.
    pub const fn new(device: &'a mut dyn rostifs::block::BlockDevice) -> Self {
        Self {
            core: rostifs::engine::RostiFs::new(device),
            bindings: [const { Cell::new(None) }; 64],
            generations: [const { Cell::new(0) }; 64],
        }
    }
    pub fn mount_in_place(&mut self) -> Result<(), FsError> {
        self.core.mount_in_place().map_err(error)
    }
    pub fn mount_info(&self) -> rostifs::engine::MountInfo {
        self.core.mount_info()
    }
    fn local(&self, id: NodeId) -> Result<portable::NodeId, FsError> {
        let i = id.slot as usize;
        if self.generations.get(i).ok_or(FsError::NotFound)?.get() != id.generation {
            return Err(FsError::NotFound);
        }
        if i == 0 {
            return Ok(self.core.root());
        }
        self.bindings[i].get().ok_or(FsError::NotFound)
    }
    fn bind(&self, node: portable::NodeId) -> Result<NodeId, FsError> {
        if node == self.core.root() {
            return Ok(NodeId::ROOT);
        }
        for i in 1..64 {
            if self.bindings[i].get() == Some(node) {
                return Ok(NodeId {
                    slot: i as u16,
                    generation: self.generations[i].get(),
                });
            }
        }
        for i in 1..64 {
            if let Some(n) = self.bindings[i].get() {
                // Only NotFound proves deletion; transient I/O must never revoke
                // an otherwise valid node binding.
                if self.core.metadata(n) == Err(portable::FsError::NotFound) {
                    self.bindings[i].set(None);
                    self.generations[i].set(self.generations[i].get().saturating_add(1));
                }
            }
            if self.bindings[i].get().is_none() && self.generations[i].get() != u32::MAX {
                self.bindings[i].set(Some(node));
                return Ok(NodeId {
                    slot: i as u16,
                    generation: self.generations[i].get(),
                });
            }
        }
        Err(FsError::FilesystemFull)
    }
}
impl Vfs for RostiBackend<'_> {
    fn persistent_info(&self) -> Option<rostifs::engine::MountInfo> {
        let mut info = self.core.mount_info();
        info.metadata_bytes = core::mem::size_of::<Self>();
        Some(info)
    }
    fn root(&self) -> NodeId {
        NodeId::ROOT
    }
    fn lookup(&self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.bind(self.core.lookup(self.local(cwd)?, path).map_err(error)?)
    }
    fn create_file(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        let n = self
            .core
            .create_file(self.local(cwd)?, path)
            .map_err(error)?;
        self.bind(n)
    }
    fn create_dir(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        let n = self
            .core
            .create_dir(self.local(cwd)?, path)
            .map_err(error)?;
        self.bind(n)
    }
    fn metadata(&self, id: NodeId) -> Result<Metadata, FsError> {
        let m = self.core.metadata(self.local(id)?).map_err(error)?;
        Ok(Metadata {
            kind: kind(m.kind),
            size: m.size,
        })
    }
    fn read(&self, id: NodeId, offset: usize, buf: &mut [u8]) -> Result<usize, FsError> {
        self.core.read(self.local(id)?, offset, buf).map_err(error)
    }
    fn write(&mut self, id: NodeId, offset: usize, data: &[u8]) -> Result<usize, FsError> {
        self.core
            .write(self.local(id)?, offset, data)
            .map_err(error)
    }
    fn replace(&mut self, id: NodeId, data: &[u8]) -> Result<(), FsError> {
        self.core.replace(self.local(id)?, data).map_err(error)
    }
    fn truncate(&mut self, id: NodeId, len: usize) -> Result<(), FsError> {
        self.core.truncate(self.local(id)?, len).map_err(error)
    }
    fn remove_file(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        self.core.remove_file(self.local(cwd)?, path).map_err(error)
    }
    fn remove_dir(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        self.core.remove_dir(self.local(cwd)?, path).map_err(error)
    }
    fn list(
        &self,
        id: NodeId,
        visitor: &mut dyn FnMut(&str, NodeId, NodeKind),
    ) -> Result<(), FsError> {
        let mut err = None;
        self.core
            .list(self.local(id)?, &mut |s, n, k| match self.bind(n) {
                Ok(n) => visitor(s, n, kind(k)),
                Err(e) => err = Some(e),
            })
            .map_err(error)?;
        err.map_or(Ok(()), Err)
    }
    fn path(&self, id: NodeId, buf: &mut [u8]) -> Result<usize, FsError> {
        self.core.path(self.local(id)?, buf).map_err(error)
    }
    fn stats(&self) -> FsStats {
        let s = self.core.stats();
        FsStats {
            nodes: s.nodes,
            logical_bytes: s.logical_bytes,
            allocated_bytes: s.allocated_bytes,
            metadata_bytes: core::mem::size_of::<Self>(),
        }
    }
}
