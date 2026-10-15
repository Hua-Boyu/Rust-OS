//! Read-only, owned archive snapshot. No module references escape construction.
//!
//! Publication replaces the whole snapshot only after validation and allocation
//! succeed. Non-root handles are revoked on every successful replacement; failed
//! builds preserve both handles and contents. Root is the stable VFS root token.
//! Heap bounds: 63 node records and MAX_ARCHIVE_BYTES payload capacity per live
//! snapshot. A replacement temporarily coexists with the old snapshot and a
//! MAX_ENTRIES parser index. Allocator headers/fragmentation are not included.
//! All mutating Vfs operations return ReadOnly for valid handles.
use super::{FsError, FsStats, Metadata, NodeId, NodeKind, Vfs};
use crate::initramfs::{self, Archive, MAX_ARCHIVE_BYTES, MAX_NAME, MAX_PATH};
use alloc::vec::Vec;

#[cfg(test)]
#[path = "../../tests_kernel/src/archive_vfs_tests.rs"]
mod tests;

pub const MAX_ARCHIVE_NODES: usize = 64; // includes virtual root and implicit parents
#[derive(Clone, Copy)]
struct Node {
    name: [u8; MAX_NAME],
    name_len: u8,
    parent: u16,
    payload: usize,
    size: usize,
    dir: bool,
}
pub struct ArchiveFs {
    nodes: Vec<Node>, // slot n is nodes[n-1]; slot zero is never in this Vec
    payload: Vec<u8>,
    generation: u32,
    #[cfg(test)]
    fail_reserve_at: Option<usize>,
}
impl ArchiveFs {
    pub const fn empty() -> Self {
        Self {
            nodes: Vec::new(),
            payload: Vec::new(),
            generation: 0,
            #[cfg(test)]
            fail_reserve_at: None,
        }
    }
    fn node(&self, slot: usize) -> &Node {
        &self.nodes[slot - 1]
    }
    fn index(&self, id: NodeId) -> Result<usize, FsError> {
        if id == NodeId::ROOT {
            return Ok(0);
        }
        let slot = id.slot as usize;
        if slot == 0 || slot > self.nodes.len() || id.generation != self.generation {
            return Err(FsError::NotFound);
        }
        Ok(slot)
    }
    fn bind(&self, slot: usize) -> NodeId {
        if slot == 0 {
            NodeId::ROOT
        } else {
            NodeId {
                slot: slot as u16,
                generation: self.generation,
            }
        }
    }
    fn directory(&self, slot: usize) -> Result<(), FsError> {
        if slot != 0 && !self.node(slot).dir {
            Err(FsError::NotADirectory)
        } else {
            Ok(())
        }
    }
    fn child(&self, parent: usize, name: &[u8]) -> Option<usize> {
        self.nodes
            .iter()
            .position(|n| n.parent as usize == parent && &n.name[..n.name_len as usize] == name)
            .map(|i| i + 1)
    }
    fn intern(&mut self, path: &[u8], dir: bool) -> Result<usize, FsError> {
        let mut parent = 0;
        let mut parts = path.split(|&c| c == b'/').peekable();
        while let Some(part) = parts.next() {
            let is_dir = parts.peek().is_some() || dir;
            parent = if let Some(slot) = self.child(parent, part) {
                if self.node(slot).dir != is_dir {
                    return Err(FsError::InvalidPath);
                }
                slot
            } else {
                if self.nodes.len() == MAX_ARCHIVE_NODES - 1 {
                    return Err(FsError::FilesystemFull);
                }
                let mut node = Node {
                    name: [0; MAX_NAME],
                    name_len: part.len() as u8,
                    parent: parent as u16,
                    payload: 0,
                    size: 0,
                    dir: is_dir,
                };
                node.name[..part.len()].copy_from_slice(part);
                self.nodes.push(node); // capacity was reserved before any insertion
                self.nodes.len()
            };
        }
        Ok(parent)
    }
    /// Compatibility boolean API; try_build provides the exact failure.
    pub fn build(&mut self, archive: &Archive, bytes: &[u8]) -> bool {
        self.try_build(archive, bytes).is_ok()
    }
    pub fn try_build(&mut self, archive: &Archive, bytes: &[u8]) -> Result<(), FsError> {
        #[cfg(test)]
        let refuse = self.fail_reserve_at.take();
        // Archive's fields are public. Reparse before indexing any caller-supplied
        // name length/offset, and require the supplied index to match these bytes.
        #[cfg(test)]
        if refuse == Some(0) {
            return Err(FsError::OutOfMemory);
        }
        let validated = initramfs::parse(bytes).map_err(|error| match error {
            initramfs::ArchiveError::OutOfMemory => FsError::OutOfMemory,
            _ => FsError::CorruptVolume,
        })?;
        if &validated != archive {
            return Err(FsError::CorruptVolume);
        }
        let generation = self
            .generation
            .checked_add(1)
            .ok_or(FsError::FilesystemFull)?;
        let mut staged = Self::empty();
        staged.generation = generation;
        let total = validated
            .entries
            .iter()
            .try_fold(0usize, |sum, e| sum.checked_add(e.size as usize))
            .ok_or(FsError::FileTooLarge)?;
        if total > MAX_ARCHIVE_BYTES {
            return Err(FsError::FilesystemFull);
        }
        #[cfg(test)]
        if refuse == Some(1) {
            return Err(FsError::OutOfMemory);
        }
        staged
            .nodes
            .try_reserve_exact(MAX_ARCHIVE_NODES - 1)
            .map_err(|_| FsError::OutOfMemory)?;
        if staged.nodes.capacity() > MAX_ARCHIVE_NODES - 1 {
            return Err(FsError::FilesystemFull);
        }
        #[cfg(test)]
        if refuse == Some(2) {
            return Err(FsError::OutOfMemory);
        }
        staged
            .payload
            .try_reserve_exact(total)
            .map_err(|_| FsError::OutOfMemory)?;
        if staged.payload.capacity() > MAX_ARCHIVE_BYTES {
            return Err(FsError::FilesystemFull);
        }
        for e in &validated.entries {
            let slot = staged.intern(&e.name[..e.name_len as usize], e.dir)?;
            if !e.dir {
                let start = e.offset as usize;
                let end = start
                    .checked_add(e.size as usize)
                    .ok_or(FsError::CorruptVolume)?;
                let data = bytes.get(start..end).ok_or(FsError::CorruptVolume)?;
                let payload = staged.payload.len();
                staged.payload.extend_from_slice(data);
                let n = &mut staged.nodes[slot - 1];
                n.payload = payload;
                n.size = data.len();
            }
        }
        *self = staged;
        Ok(())
    }
    pub fn total_payload(&self) -> usize {
        self.payload.len()
    }
}
impl Vfs for ArchiveFs {
    fn root(&self) -> NodeId {
        NodeId::ROOT
    }
    fn lookup(&self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        if path.is_empty()
            || path.len() > MAX_PATH
            || path.chars().any(char::is_control)
            || path.split('/').any(|p| p.len() > MAX_NAME)
        {
            return Err(FsError::InvalidPath);
        }
        let cwd = self.index(cwd)?;
        let mut current = if path.starts_with('/') { 0 } else { cwd };
        for part in path.split('/').filter(|p| !p.is_empty()) {
            self.directory(current)?; // do not lexically cancel file/..
            current = match part {
                "." => current,
                ".." => {
                    if current == 0 {
                        0
                    } else {
                        self.node(current).parent as usize
                    }
                }
                _ => self
                    .child(current, part.as_bytes())
                    .ok_or(FsError::NotFound)?,
            };
        }
        if path.ends_with('/') {
            self.directory(current)?;
        }
        Ok(self.bind(current))
    }
    fn metadata(&self, id: NodeId) -> Result<Metadata, FsError> {
        let slot = self.index(id)?;
        if slot == 0 {
            return Ok(Metadata {
                kind: NodeKind::Directory,
                size: 0,
            });
        }
        let n = self.node(slot);
        Ok(Metadata {
            kind: if n.dir {
                NodeKind::Directory
            } else {
                NodeKind::File
            },
            size: n.size,
        })
    }
    fn read(&self, id: NodeId, offset: usize, buf: &mut [u8]) -> Result<usize, FsError> {
        let slot = self.index(id)?;
        if slot == 0 || self.node(slot).dir {
            return Err(FsError::IsADirectory);
        }
        let n = self.node(slot);
        let offset = offset.min(n.size);
        let count = buf.len().min(n.size - offset);
        let start = n.payload + offset; // bounded by validated payload length
        let data = self
            .payload
            .get(start..start + count)
            .ok_or(FsError::CorruptVolume)?;
        buf[..count].copy_from_slice(data);
        Ok(count)
    }
    fn list(
        &self,
        id: NodeId,
        visitor: &mut dyn FnMut(&str, NodeId, NodeKind),
    ) -> Result<(), FsError> {
        let slot = self.index(id)?;
        self.directory(slot)?;
        for (i, n) in self.nodes.iter().enumerate() {
            if n.parent as usize == slot {
                let name = core::str::from_utf8(&n.name[..n.name_len as usize])
                    .map_err(|_| FsError::CorruptVolume)?;
                visitor(
                    name,
                    self.bind(i + 1),
                    if n.dir {
                        NodeKind::Directory
                    } else {
                        NodeKind::File
                    },
                );
            }
        }
        Ok(())
    }
    fn path(&self, id: NodeId, buf: &mut [u8]) -> Result<usize, FsError> {
        let mut slot = self.index(id)?;
        let mut chain = [0usize; MAX_ARCHIVE_NODES];
        let (mut depth, mut len) = (0, 0);
        while slot != 0 {
            if depth == chain.len() {
                return Err(FsError::InvalidPath);
            }
            chain[depth] = slot;
            depth += 1;
            len += 1 + self.node(slot).name_len as usize;
            slot = self.node(slot).parent as usize;
        }
        len = len.max(1);
        if len > buf.len() {
            return Err(FsError::InvalidPath);
        }
        let mut pos = 0;
        for &slot in chain[..depth].iter().rev() {
            let n = self.node(slot);
            let name = &n.name[..n.name_len as usize];
            buf[pos] = b'/';
            pos += 1;
            buf[pos..pos + name.len()].copy_from_slice(name);
            pos += name.len();
        }
        if depth == 0 {
            buf[0] = b'/';
        }
        Ok(len)
    }
    fn stats(&self) -> FsStats {
        FsStats {
            nodes: self.nodes.len() + 1,
            logical_bytes: self.payload.len(),
            allocated_bytes: self.payload.capacity(),
            metadata_bytes: core::mem::size_of::<Self>()
                + self.nodes.capacity() * core::mem::size_of::<Node>(),
        }
    }
    fn create_file(&mut self, cwd: NodeId, _: &str) -> Result<NodeId, FsError> {
        self.index(cwd)?;
        Err(FsError::ReadOnly)
    }
    fn create_dir(&mut self, cwd: NodeId, _: &str) -> Result<NodeId, FsError> {
        self.index(cwd)?;
        Err(FsError::ReadOnly)
    }
    fn write(&mut self, id: NodeId, _: usize, _: &[u8]) -> Result<usize, FsError> {
        self.index(id)?;
        Err(FsError::ReadOnly)
    }
    fn replace(&mut self, id: NodeId, _: &[u8]) -> Result<(), FsError> {
        self.index(id)?;
        Err(FsError::ReadOnly)
    }
    fn truncate(&mut self, id: NodeId, _: usize) -> Result<(), FsError> {
        self.index(id)?;
        Err(FsError::ReadOnly)
    }
    fn remove_file(&mut self, cwd: NodeId, _: &str) -> Result<(), FsError> {
        self.index(cwd)?;
        Err(FsError::ReadOnly)
    }
    fn remove_dir(&mut self, cwd: NodeId, _: &str) -> Result<(), FsError> {
        self.index(cwd)?;
        Err(FsError::ReadOnly)
    }
}
