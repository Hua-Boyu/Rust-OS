mod vfs;
use alloc::vec::Vec;
pub use vfs::{FsError, FsStats, Metadata, NodeId, NodeKind, Vfs};
const MAX_NODES: usize = 64;
pub const MAX_PATH: usize = 256;
pub const MAX_NAME: usize = 63;
pub const MAX_FILE_SIZE: usize = 512 * 1024;
pub const MAX_PAYLOAD: usize = 4 * 1024 * 1024;
struct Node {
    parent: NodeId,
    name: [u8; MAX_NAME],
    name_len: u8,
    kind: NodeKind,
    data: Vec<u8>,
}
impl Node {
    const fn root() -> Self {
        Self {
            parent: NodeId::ROOT,
            name: [0; MAX_NAME],
            name_len: 0,
            kind: NodeKind::Directory,
            data: Vec::new(),
        }
    }
    fn name(&self) -> &str {
        core::str::from_utf8(&self.name[..self.name_len as usize]).unwrap()
    }
}
/// Fixed metadata slots never allocate. Payload growth uses fallible allocation.
pub struct RamFs {
    nodes: [Option<Node>; MAX_NODES],
    generations: [u32; MAX_NODES],
    #[cfg(test)]
    fail_reserve: bool,
}
impl RamFs {
    #[cfg(test)]
    pub fn fail_next_allocation(&mut self) {
        self.fail_reserve = true;
    }
    pub const fn new() -> Self {
        let mut nodes = [const { None }; MAX_NODES];
        // SAFETY: slot zero is empty; write avoids const Vec destructor evaluation.
        unsafe {
            nodes.as_mut_ptr().write(Some(Node::root()));
        }
        Self {
            nodes,
            generations: [0; MAX_NODES],
            #[cfg(test)]
            fail_reserve: false,
        }
    }
    fn node(&self, id: NodeId) -> Result<&Node, FsError> {
        let i = id.slot as usize;
        if i >= MAX_NODES || self.generations[i] != id.generation {
            return Err(FsError::NotFound);
        }
        self.nodes[i].as_ref().ok_or(FsError::NotFound)
    }
    fn file(&self, id: NodeId) -> Result<&Node, FsError> {
        let n = self.node(id)?;
        if n.kind == NodeKind::Directory {
            return Err(FsError::IsADirectory);
        }
        Ok(n)
    }
    fn grow(&mut self, id: NodeId, len: usize) -> Result<(), FsError> {
        let n = self.file(id)?;
        if len > MAX_FILE_SIZE {
            return Err(FsError::FileTooLarge);
        }
        if len <= n.data.capacity() {
            return Ok(());
        }
        let other_capacities = self.stats().allocated_bytes - n.data.capacity();
        if len > MAX_PAYLOAD - other_capacities {
            return Err(FsError::FilesystemFull);
        }
        // Stage growth so both reserve failures and unexpectedly oversized
        // capacities preserve the original bytes and accounting.
        #[cfg(test)]
        if core::mem::replace(&mut self.fail_reserve, false) {
            return Err(FsError::OutOfMemory);
        }
        let mut replacement = Vec::new();
        replacement
            .try_reserve_exact(len)
            .map_err(|_| FsError::OutOfMemory)?;
        if replacement.capacity() > MAX_PAYLOAD - other_capacities {
            return Err(FsError::FilesystemFull);
        }
        replacement.extend_from_slice(&self.file(id)?.data);
        self.nodes[id.slot as usize].as_mut().unwrap().data = replacement;
        Ok(())
    }
    fn id(&self, slot: usize) -> NodeId {
        NodeId {
            slot: slot as u8,
            generation: self.generations[slot],
        }
    }
    fn directory(&self, id: NodeId) -> Result<(), FsError> {
        if self.node(id)?.kind != NodeKind::Directory {
            return Err(FsError::NotADirectory);
        }
        Ok(())
    }
    fn validate(path: &str) -> Result<(), FsError> {
        if path.is_empty() || path.len() > MAX_PATH || path.chars().any(char::is_control) {
            return Err(FsError::InvalidPath);
        }
        if path.split('/').any(|s| s.len() > MAX_NAME) {
            return Err(FsError::InvalidPath);
        }
        Ok(())
    }
    fn child(&self, parent: NodeId, name: &str) -> Option<NodeId> {
        self.nodes
            .iter()
            .enumerate()
            .skip(1)
            .find(|(_, n)| {
                n.as_ref()
                    .is_some_and(|n| n.parent == parent && n.name() == name)
            })
            .map(|(i, _)| self.id(i))
    }
    fn create(&mut self, cwd: NodeId, path: &str, kind: NodeKind) -> Result<NodeId, FsError> {
        Self::validate(path)?;
        self.node(cwd)?;
        let trimmed = path.trim_end_matches('/');
        let (parent_path, leaf) = match trimmed.rsplit_once('/') {
            Some((p, n)) => (if p.is_empty() { "/" } else { p }, n),
            None => (".", trimmed),
        };
        if leaf.is_empty() || leaf == "." || leaf == ".." {
            return Err(FsError::InvalidPath);
        }
        let parent = self.lookup(cwd, parent_path)?;
        self.directory(parent)?;
        if let Some(existing) = self.child(parent, leaf) {
            if path.ends_with('/') {
                self.directory(existing)?;
            }
            return Err(FsError::AlreadyExists);
        }
        if path.ends_with('/') && kind == NodeKind::File {
            return Err(FsError::NotADirectory);
        }
        let mut canonical = [0; MAX_PATH];
        let parent_len = self.path(parent, &mut canonical)?;
        let separator = usize::from(parent != self.root());
        if parent_len + separator + leaf.len() > MAX_PATH {
            return Err(FsError::InvalidPath);
        }
        // Never wrap a generation: exhausted slots are retired, preventing ABA.
        let i = (1..MAX_NODES)
            .find(|&i| self.nodes[i].is_none() && self.generations[i] != u32::MAX)
            .ok_or(FsError::FilesystemFull)?;
        let mut name = [0; MAX_NAME];
        name[..leaf.len()].copy_from_slice(leaf.as_bytes());
        self.nodes[i] = Some(Node {
            parent,
            name,
            name_len: leaf.len() as u8,
            kind,
            data: Vec::new(),
        });
        Ok(self.id(i))
    }
}
impl Default for RamFs {
    fn default() -> Self {
        Self::new()
    }
}
impl Vfs for RamFs {
    fn root(&self) -> NodeId {
        NodeId::ROOT
    }
    fn lookup(&self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        Self::validate(path)?;
        self.node(cwd)?;
        let mut current = if path.starts_with('/') {
            self.root()
        } else {
            cwd
        };
        for part in path.split('/').filter(|s| !s.is_empty()) {
            // Check before dot processing: file/.. must not silently normalize.
            self.directory(current)?;
            current = match part {
                "." => current,
                ".." => self.node(current)?.parent,
                name => self.child(current, name).ok_or(FsError::NotFound)?,
            };
        }
        if path.ends_with('/') {
            self.directory(current)?;
        }
        Ok(current)
    }
    fn create_file(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.create(cwd, path, NodeKind::File)
    }
    fn create_dir(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.create(cwd, path, NodeKind::Directory)
    }
    fn metadata(&self, id: NodeId) -> Result<Metadata, FsError> {
        let n = self.node(id)?;
        Ok(Metadata {
            kind: n.kind,
            size: n.data.len(),
        })
    }
    fn read(&self, id: NodeId, offset: usize, buf: &mut [u8]) -> Result<usize, FsError> {
        let n = self.node(id)?;
        if n.kind == NodeKind::Directory {
            return Err(FsError::IsADirectory);
        }
        let start = offset.min(n.data.len());
        let len = buf.len().min(n.data.len() - start);
        buf[..len].copy_from_slice(&n.data[start..start + len]);
        Ok(len)
    }
    fn write(&mut self, id: NodeId, offset: usize, data: &[u8]) -> Result<usize, FsError> {
        self.file(id)?;
        if data.is_empty() {
            return Ok(0);
        }
        let end = offset
            .checked_add(data.len())
            .ok_or(FsError::FileTooLarge)?;
        self.grow(id, end)?;
        let n = self.nodes[id.slot as usize].as_mut().unwrap();
        if end > n.data.len() {
            n.data.resize(end, 0);
        }
        n.data[offset..end].copy_from_slice(data);
        Ok(data.len())
    }
    fn replace(&mut self, id: NodeId, data: &[u8]) -> Result<(), FsError> {
        self.grow(id, data.len())?;
        let n = self.nodes[id.slot as usize].as_mut().unwrap();
        n.data.resize(data.len(), 0);
        n.data.copy_from_slice(data);
        if data.is_empty() {
            n.data = Vec::new();
        }
        Ok(())
    }
    fn truncate(&mut self, id: NodeId, len: usize) -> Result<(), FsError> {
        self.grow(id, len)?;
        let n = self.nodes[id.slot as usize].as_mut().unwrap();
        n.data.resize(len, 0);
        if len == 0 {
            n.data = Vec::new();
        }
        Ok(())
    }
    fn remove_file(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        let id = self.lookup(cwd, path)?;
        if id == self.root() {
            return Err(FsError::InvalidPath);
        }
        self.file(id)?;
        self.nodes[id.slot as usize] = None;
        self.generations[id.slot as usize] += 1;
        Ok(())
    }
    fn remove_dir(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        let id = self.lookup(cwd, path)?;
        if id == self.root() {
            return Err(FsError::InvalidPath);
        }
        self.directory(id)?;
        if self.nodes.iter().flatten().any(|n| n.parent == id) {
            return Err(FsError::DirectoryNotEmpty);
        }
        self.nodes[id.slot as usize] = None;
        self.generations[id.slot as usize] += 1;
        Ok(())
    }
    fn list(
        &self,
        id: NodeId,
        visitor: &mut dyn FnMut(&str, NodeId, NodeKind),
    ) -> Result<(), FsError> {
        self.directory(id)?;
        for (i, node) in self.nodes.iter().enumerate().skip(1) {
            if let Some(n) = node {
                if n.parent == id {
                    visitor(n.name(), self.id(i), n.kind);
                }
            }
        }
        Ok(())
    }
    fn path(&self, id: NodeId, buf: &mut [u8]) -> Result<usize, FsError> {
        self.node(id)?;
        let mut chain = [NodeId::ROOT; MAX_NODES];
        let mut depth = 0;
        let mut current = id;
        let mut len = 0;
        while current != self.root() {
            if depth == MAX_NODES {
                return Err(FsError::InvalidPath);
            }
            let n = self.node(current)?;
            chain[depth] = current;
            depth += 1;
            len += 1 + n.name_len as usize;
            current = n.parent;
        }
        let len = len.max(1);
        if len > buf.len() {
            return Err(FsError::InvalidPath);
        }
        let mut pos = 0;
        for id in chain[..depth].iter().rev() {
            let name = self.node(*id)?.name().as_bytes();
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
        let mut stats = FsStats {
            nodes: 0,
            logical_bytes: 0,
            allocated_bytes: 0,
            metadata_bytes: core::mem::size_of::<Self>(),
        };
        for n in self.nodes.iter().flatten() {
            stats.nodes += 1;
            stats.logical_bytes += n.data.len();
            stats.allocated_bytes += n.data.capacity();
        }
        stats
    }
}
