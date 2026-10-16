//! Main-context mount namespace. NodeId stays eight bytes (descriptor budget):
//! RAM slots are 0..64, disk bindings are 0x100..0x140; system bindings are 0x200..0x240. Bindings retire
//! instead of wrapping and are invalidated across every unmount/remount.
use super::*;
#[cfg(test)]
#[path = "../../tests_kernel/src/mount_tests.rs"]
mod tests;
use crate::fd::{FdTable, MAX_DESCRIPTORS};
use core::cell::Cell;
const MOUNT: u16 = 0x100;
const BINDINGS: usize = 64;
const SYSTEM: u16 = 0x200;
#[derive(Clone, Copy)]
struct Binding {
    node: Option<NodeId>,
    generation: u32,
}

/// Keep this in static storage; never access from interrupts. The root RAMFS
/// retains its original quotas/accounting and is untouched until mount succeeds.
pub struct MountedFs<B: Vfs + 'static = RostiBackend<'static>> {
    ram: RamFs,
    backend: Option<&'static mut B>,
    system: Option<&'static mut ArchiveFs>,
    system_point: Option<NodeId>,
    system_bindings: [Cell<Binding>; BINDINGS],
    point: Option<NodeId>,
    parent: Option<NodeId>,
    bindings: [Cell<Binding>; BINDINGS],
}
impl<B: Vfs + 'static> MountedFs<B> {
    pub const fn new() -> Self {
        Self {
            ram: RamFs::new(),
            backend: None,
            system: None,
            system_point: None,
            system_bindings: [const {
                Cell::new(Binding {
                    node: None,
                    generation: 0,
                })
            }; BINDINGS],
            point: None,
            parent: None,
            bindings: [const {
                Cell::new(Binding {
                    node: None,
                    generation: 0,
                })
            }; BINDINGS],
        }
    }
    pub fn is_mounted(&self) -> bool {
        self.backend.is_some()
    }
    /// Mounted archive node count, logical payload and allocated payload capacity.
    /// Metadata includes ArchiveFs, its node capacity and system routing bindings;
    /// RAMFS quotas/stats and transient import allocations remain separate.
    pub fn system_info(&self) -> Option<FsStats> {
        let mut info = self.system.as_deref()?.stats();
        info.metadata_bytes += core::mem::size_of_val(&self.system_bindings);
        Some(info)
    }
    fn disk(id: NodeId) -> bool {
        (MOUNT..MOUNT + BINDINGS as u16).contains(&id.slot)
    }
    fn system_id(id: NodeId) -> bool {
        (SYSTEM..SYSTEM + BINDINGS as u16).contains(&id.slot)
    }
    fn archive(&self) -> Result<&ArchiveFs, FsError> {
        self.system.as_deref().ok_or(FsError::NotFound)
    }
    fn system_local(&self, id: NodeId) -> Result<NodeId, FsError> {
        self.archive()?;
        let i = id.slot.checked_sub(SYSTEM).ok_or(FsError::NotFound)? as usize;
        let b = self.system_bindings.get(i).ok_or(FsError::NotFound)?.get();
        if b.generation != id.generation {
            return Err(FsError::NotFound);
        }
        b.node.ok_or(FsError::NotFound)
    }
    fn system_bind(&self, node: NodeId) -> Result<NodeId, FsError> {
        self.archive()?;
        self.system_bindings
            .iter()
            .enumerate()
            .find_map(|(i, cell)| {
                let b = cell.get();
                (b.node == Some(node)).then_some(NodeId {
                    slot: SYSTEM + i as u16,
                    generation: b.generation,
                })
            })
            .ok_or(FsError::NotFound)
    }
    /// Attach a structurally valid owned ArchiveFs snapshot, VERIFIED by the
    /// caller's trust policy. This API does not authenticate archive bytes.
    /// Success pins exclusive static ownership until reboot; no detach exists.
    /// Failure resets the unpublished archive, releasing its node/payload capacity.
    /// Stage every bounded binding and canonical path before touching RAMFS.
    /// No allocations or fallible work follow mountpoint creation/publication.
    pub fn mount_system(&mut self, archive: &'static mut ArchiveFs) -> Result<(), FsError> {
        self.mount_system_inner(
            archive,
            #[cfg(any(test, feature = "initramfs-failure-test"))]
            false,
        )
    }
    /// Deterministic guest/host rollback probe; absent from production builds.
    #[cfg(any(test, feature = "initramfs-failure-test"))]
    pub fn mount_system_failure_fixture(
        &mut self,
        archive: &'static mut ArchiveFs,
    ) -> Result<(), FsError> {
        self.mount_system_inner(archive, true)
    }
    fn mount_system_inner(
        &mut self,
        archive: &'static mut ArchiveFs,
        #[cfg(any(test, feature = "initramfs-failure-test"))] fail_after_point: bool,
    ) -> Result<(), FsError> {
        let (staged, point) = self.prepare_system(
            archive,
            #[cfg(any(test, feature = "initramfs-failure-test"))]
            fail_after_point,
        )?;
        for (cell, binding) in self.system_bindings.iter().zip(staged) {
            cell.set(binding);
        }
        self.system_point = Some(point);
        self.system = Some(archive);
        Ok(())
    }
    // Own the staging result, never a borrow of the archive. The static wrapper
    // can publish its exclusive borrow only after all fallible work is done.
    fn prepare_system(
        &mut self,
        archive: &mut ArchiveFs,
        #[cfg(any(test, feature = "initramfs-failure-test"))] fail_after_point: bool,
    ) -> Result<([Binding; BINDINGS], NodeId), FsError> {
        let result = self.preflight_system(
            archive,
            #[cfg(any(test, feature = "initramfs-failure-test"))]
            fail_after_point,
        );
        if result.is_err() {
            // The unpublished exclusive borrow is still ours. Drop both owned
            // Vec backings before the static wrapper returns an error.
            *archive = ArchiveFs::empty();
        }
        result
    }
    fn preflight_system(
        &mut self,
        archive: &ArchiveFs,
        #[cfg(any(test, feature = "initramfs-failure-test"))] fail_after_point: bool,
    ) -> Result<([Binding; BINDINGS], NodeId), FsError> {
        if self.system.is_some() {
            return Err(FsError::Busy);
        }
        let mut staged = [Binding {
            node: None,
            generation: 0,
        }; BINDINGS];
        staged[0].node = Some(archive.root());
        let mut count = 1;
        let mut cursor = 0;
        while cursor < count {
            let node = staged[cursor].node.ok_or(FsError::CorruptVolume)?;
            let mut path = [0; MAX_PATH];
            let len = archive.path(node, &mut path)?;
            if node != archive.root() && len + b"/system".len() > MAX_PATH {
                return Err(FsError::InvalidPath);
            }
            if archive.metadata(node)?.kind == NodeKind::Directory {
                let mut error = None;
                archive.list(node, &mut |_, child, _| {
                    if staged[..count].iter().any(|b| b.node == Some(child)) {
                        error = Some(FsError::CorruptVolume);
                    } else if count == BINDINGS {
                        error = Some(FsError::FilesystemFull);
                    } else {
                        staged[count].node = Some(child);
                        count += 1;
                    }
                })?;
                if let Some(e) = error {
                    return Err(e);
                }
            }
            cursor += 1;
        }
        let (point, owned) = match self.ram.lookup(NodeId::ROOT, "/system") {
            Ok(id) => {
                self.ram.directory(id)?;
                let mut nonempty = false;
                self.ram.list(id, &mut |_, _, _| nonempty = true)?;
                if nonempty {
                    return Err(FsError::DirectoryNotEmpty);
                }
                (id, false)
            }
            Err(FsError::NotFound) => (self.ram.create_dir(NodeId::ROOT, "/system")?, true),
            Err(e) => return Err(e),
        };
        // Deterministic probe: fail after mountpoint resolution, before any
        // publication. Undo only the directory this transaction created.
        #[cfg(any(test, feature = "initramfs-failure-test"))]
        if fail_after_point {
            if owned {
                let _ = self.ram.remove_dir(NodeId::ROOT, "/system");
            }
            return Err(FsError::OutOfMemory);
        }
        Ok((staged, point))
    }
    fn backend(&self) -> Result<&B, FsError> {
        self.backend.as_deref().ok_or(FsError::NotFound)
    }
    fn local(&self, id: NodeId) -> Result<NodeId, FsError> {
        self.backend()?;
        let i = id.slot.checked_sub(MOUNT).ok_or(FsError::NotFound)? as usize;
        let b = self.bindings.get(i).ok_or(FsError::NotFound)?.get();
        if b.generation != id.generation {
            return Err(FsError::NotFound);
        }
        b.node.ok_or(FsError::NotFound)
    }
    fn bind(&self, node: NodeId) -> Result<NodeId, FsError> {
        let backend = self.backend()?;
        for (i, cell) in self.bindings.iter().enumerate() {
            let b = cell.get();
            if b.node == Some(node) {
                return Ok(NodeId {
                    slot: MOUNT + i as u16,
                    generation: b.generation,
                });
            }
        }
        for (i, cell) in self.bindings.iter().enumerate() {
            let mut b = cell.get();
            if b.node
                .is_some_and(|n| backend.metadata(n) == Err(FsError::NotFound))
            {
                b.node = None;
                b.generation = b.generation.saturating_add(1);
                cell.set(b);
            }
            if b.node.is_none() && b.generation != u32::MAX {
                b.node = Some(node);
                cell.set(b);
                return Ok(NodeId {
                    slot: MOUNT + i as u16,
                    generation: b.generation,
                });
            }
        }
        Err(FsError::FilesystemFull)
    }
    /// Attach an already validated backend. No formatting and no hidden RAMFS
    /// directory contents: reject nonempty /mnt/rosti. Failed attach rolls back
    /// only directories created by this call. Backend storage belongs to caller.
    pub fn mount_backend(&mut self, backend: &'static mut B) -> Result<(), FsError> {
        if self.is_mounted() {
            return Err(FsError::Busy);
        }
        if backend.metadata(backend.root())?.kind != NodeKind::Directory {
            return Err(FsError::NotADirectory);
        }
        let mut made_parent = false;
        let parent = match self.ram.lookup(NodeId::ROOT, "/mnt") {
            Ok(id) => {
                self.ram.directory(id)?;
                id
            }
            Err(FsError::NotFound) => {
                made_parent = true;
                self.ram.create_dir(NodeId::ROOT, "/mnt")?
            }
            Err(e) => return Err(e),
        };
        let point = match self.ram.lookup(parent, "rosti") {
            Ok(id) => {
                let result = self.ram.directory(id).and_then(|()| {
                    let mut nonempty = false;
                    self.ram.list(id, &mut |_, _, _| nonempty = true)?;
                    if nonempty {
                        Err(FsError::DirectoryNotEmpty)
                    } else {
                        Ok(id)
                    }
                });
                result
            }
            Err(FsError::NotFound) => self.ram.create_dir(parent, "rosti"),
            Err(e) => Err(e),
        };
        let point = match point {
            Ok(id) => id,
            Err(e) => {
                if made_parent {
                    let _ = self.ram.remove_dir(NodeId::ROOT, "/mnt");
                }
                return Err(e);
            }
        };
        self.backend = Some(backend);
        self.point = Some(point);
        self.parent = Some(parent);
        Ok(())
    }
    /// Check actual descriptors, not a caller-supplied count. Duplicates and
    /// deleted-but-still-open nodes block detach. A mounted cwd also pins it.
    pub fn unmount(&mut self, descriptors: &mut FdTable, cwd: NodeId) -> Result<(), FsError> {
        self.backend()?;
        if Self::disk(cwd) {
            return Err(FsError::Busy);
        }
        for fd in 0..MAX_DESCRIPTORS as u8 {
            if descriptors.node(fd).is_ok_and(Self::disk) {
                return Err(FsError::Busy);
            }
        }
        self.backend = None;
        self.point = None;
        self.parent = None;
        for cell in &self.bindings {
            let mut b = cell.get();
            b.node = None;
            b.generation = b.generation.saturating_add(1);
            cell.set(b);
        }
        Ok(())
    }
    fn enter(&self, id: NodeId) -> Result<NodeId, FsError> {
        if self.system_point == Some(id) {
            self.system_bind(self.archive()?.root())
        } else if self.point == Some(id) {
            self.bind(self.backend()?.root())
        } else {
            Ok(id)
        }
    }
    fn directory(&self, id: NodeId) -> Result<(), FsError> {
        if self.metadata(id)?.kind == NodeKind::Directory {
            Ok(())
        } else {
            Err(FsError::NotADirectory)
        }
    }
    fn parent_leaf<'p>(&self, cwd: NodeId, path: &'p str) -> Result<(NodeId, &'p str), FsError> {
        RamFs::validate(path)?;
        self.metadata(cwd)?;
        let trimmed = path.trim_end_matches('/');
        let (p, leaf) = match trimmed.rsplit_once('/') {
            Some((p, n)) => (if p.is_empty() { "/" } else { p }, n),
            None => (".", trimmed),
        };
        if leaf.is_empty() || leaf == "." || leaf == ".." {
            return Err(FsError::InvalidPath);
        }
        let parent = self.lookup(cwd, p)?;
        self.directory(parent)?;
        let mut buf = [0; MAX_PATH];
        let len = self.path(parent, &mut buf)?;
        if len + usize::from(parent != NodeId::ROOT) + leaf.len() > MAX_PATH {
            return Err(FsError::InvalidPath);
        }
        // Preserve trailing slash type checks by passing the original leaf tail.
        Ok((
            parent,
            &path[path.len() - (leaf.len() + path.len() - trimmed.len())..],
        ))
    }
    fn create(&mut self, cwd: NodeId, path: &str, dir: bool) -> Result<NodeId, FsError> {
        let (p, leaf) = self.parent_leaf(cwd, path)?;
        if Self::system_id(p) {
            self.system_local(p)?;
            return Err(FsError::ReadOnly);
        }
        if Self::disk(p) {
            let local = self.local(p)?;
            let b = self.backend.as_deref_mut().ok_or(FsError::NotFound)?;
            let node = if dir {
                b.create_dir(local, leaf)?
            } else {
                b.create_file(local, leaf)?
            };
            self.bind(node)
        } else {
            let id = if dir {
                self.ram.create_dir(p, leaf)?
            } else {
                self.ram.create_file(p, leaf)?
            };
            self.enter(id)
        }
    }
}
impl MountedFs<RostiBackend<'static>> {
    /// Mount an explicitly supplied static device backend in place, then expose
    /// /mnt/rosti. A corrupt/unknown disk never creates mount directories and is
    /// never formatted. RostiBackend::new(device) must be a static initializer.
    pub fn mount_rosti(
        &mut self,
        backend: &'static mut RostiBackend<'static>,
    ) -> Result<(), FsError> {
        if self.is_mounted() {
            return Err(FsError::Busy);
        }
        backend.mount_in_place()?;
        self.mount_backend(backend)
    }
    pub fn disk_info(&self) -> Option<rostifs::engine::MountInfo> {
        self.backend.as_deref().map(|backend| {
            let mut info = backend.mount_info();
            info.metadata_bytes =
                core::mem::size_of_val(backend) + core::mem::size_of_val(&self.bindings);
            info
        })
    }
    pub fn mount_info(&self) -> Option<rostifs::engine::MountInfo> {
        self.disk_info()
    }
}
impl<B: Vfs + 'static> Default for MountedFs<B> {
    fn default() -> Self {
        Self::new()
    }
}
impl<B: Vfs + 'static> Vfs for MountedFs<B> {
    fn system_info(&self) -> Option<FsStats> {
        MountedFs::system_info(self)
    }
    fn persistent_info(&self) -> Option<rostifs::engine::MountInfo> {
        let mut info = self.backend.as_deref()?.persistent_info()?;
        info.metadata_bytes += core::mem::size_of_val(&self.bindings);
        Some(info)
    }
    fn root(&self) -> NodeId {
        NodeId::ROOT
    }
    fn lookup(&self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        RamFs::validate(path)?;
        self.metadata(cwd)?;
        let mut current = if path.starts_with('/') {
            self.root()
        } else {
            self.enter(cwd)?
        };
        for part in path.split('/').filter(|s| !s.is_empty()) {
            self.directory(current)?;
            if Self::system_id(current) {
                let local = self.system_local(current)?;
                let b = self.archive()?;
                current = if part == ".." && local == b.root() {
                    NodeId::ROOT
                } else {
                    self.system_bind(b.lookup(local, part)?)?
                };
            } else if Self::disk(current) {
                let local = self.local(current)?;
                let b = self.backend()?;
                current = if part == ".." && local == b.root() {
                    self.parent.ok_or(FsError::NotFound)?
                } else {
                    self.bind(b.lookup(local, part)?)?
                };
            } else {
                current = self.enter(self.ram.lookup(current, part)?)?;
            }
        }
        if path.ends_with('/') {
            self.directory(current)?;
        }
        Ok(current)
    }
    fn create_file(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.create(cwd, path, false)
    }
    fn create_dir(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.create(cwd, path, true)
    }
    fn metadata(&self, id: NodeId) -> Result<Metadata, FsError> {
        if Self::system_id(id) {
            self.archive()?.metadata(self.system_local(id)?)
        } else if Self::disk(id) {
            self.backend()?.metadata(self.local(id)?)
        } else {
            self.ram.metadata(id)
        }
    }
    fn read(&self, id: NodeId, offset: usize, buf: &mut [u8]) -> Result<usize, FsError> {
        if Self::system_id(id) {
            self.archive()?.read(self.system_local(id)?, offset, buf)
        } else if Self::disk(id) {
            self.backend()?.read(self.local(id)?, offset, buf)
        } else {
            self.ram.read(id, offset, buf)
        }
    }
    fn write(&mut self, id: NodeId, offset: usize, data: &[u8]) -> Result<usize, FsError> {
        let id = self.enter(id)?;
        if Self::system_id(id) {
            self.system_local(id)?;
            return Err(FsError::ReadOnly);
        }
        if Self::disk(id) {
            let n = self.local(id)?;
            self.backend
                .as_deref_mut()
                .ok_or(FsError::NotFound)?
                .write(n, offset, data)
        } else {
            self.ram.write(id, offset, data)
        }
    }
    fn replace(&mut self, id: NodeId, data: &[u8]) -> Result<(), FsError> {
        let id = self.enter(id)?;
        if Self::system_id(id) {
            self.system_local(id)?;
            return Err(FsError::ReadOnly);
        }
        if Self::disk(id) {
            let n = self.local(id)?;
            self.backend
                .as_deref_mut()
                .ok_or(FsError::NotFound)?
                .replace(n, data)
        } else {
            self.ram.replace(id, data)
        }
    }
    fn truncate(&mut self, id: NodeId, len: usize) -> Result<(), FsError> {
        let id = self.enter(id)?;
        if Self::system_id(id) {
            self.system_local(id)?;
            return Err(FsError::ReadOnly);
        }
        if Self::disk(id) {
            let n = self.local(id)?;
            self.backend
                .as_deref_mut()
                .ok_or(FsError::NotFound)?
                .truncate(n, len)
        } else {
            self.ram.truncate(id, len)
        }
    }
    fn remove_file(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        let id = self.lookup(cwd, path)?;
        let id = self.enter(id)?;
        if Self::system_id(id) {
            self.system_local(id)?;
            return Err(FsError::ReadOnly);
        }
        if Self::disk(id) {
            let n = self.local(id)?;
            let b = self.backend.as_deref_mut().ok_or(FsError::NotFound)?;
            if n == b.root() {
                return Err(FsError::IsADirectory);
            }
            let mut buf = [0; MAX_PATH];
            let len = b.path(n, &mut buf)?;
            let path = core::str::from_utf8(&buf[..len]).map_err(|_| FsError::InvalidPath)?;
            b.remove_file(b.root(), path)
        } else {
            let mut buf = [0; MAX_PATH];
            let len = self.ram.path(id, &mut buf)?;
            let path = core::str::from_utf8(&buf[..len]).map_err(|_| FsError::InvalidPath)?;
            self.ram.remove_file(NodeId::ROOT, path)
        }
    }
    fn remove_dir(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        let id = self.lookup(cwd, path)?;
        if self.point == Some(id) || self.parent == Some(id) {
            return Err(FsError::Busy);
        }
        let id = self.enter(id)?;
        if Self::system_id(id) {
            self.system_local(id)?;
            return Err(FsError::ReadOnly);
        }
        if Self::disk(id) {
            let n = self.local(id)?;
            let b = self.backend.as_deref_mut().ok_or(FsError::NotFound)?;
            if n == b.root() {
                return Err(FsError::Busy);
            }
            let mut buf = [0; MAX_PATH];
            let len = b.path(n, &mut buf)?;
            let path = core::str::from_utf8(&buf[..len]).map_err(|_| FsError::InvalidPath)?;
            b.remove_dir(b.root(), path)
        } else {
            let mut buf = [0; MAX_PATH];
            let len = self.ram.path(id, &mut buf)?;
            let path = core::str::from_utf8(&buf[..len]).map_err(|_| FsError::InvalidPath)?;
            self.ram.remove_dir(NodeId::ROOT, path)
        }
    }
    fn list(
        &self,
        id: NodeId,
        visitor: &mut dyn FnMut(&str, NodeId, NodeKind),
    ) -> Result<(), FsError> {
        let mut error = None;
        if Self::system_id(id) {
            self.archive()?.list(
                self.system_local(id)?,
                &mut |s, n, k| match self.system_bind(n) {
                    Ok(n) => visitor(s, n, k),
                    Err(e) => error = Some(e),
                },
            )?;
        } else if Self::disk(id) {
            self.backend()?
                .list(self.local(id)?, &mut |s, n, k| match self.bind(n) {
                    Ok(n) => visitor(s, n, k),
                    Err(e) => error = Some(e),
                })?;
        } else {
            self.ram.list(id, &mut |s, n, k| match self.enter(n) {
                Ok(n) => visitor(s, n, k),
                Err(e) => error = Some(e),
            })?;
        }
        error.map_or(Ok(()), Err)
    }
    fn path(&self, id: NodeId, buf: &mut [u8]) -> Result<usize, FsError> {
        let (n, b, prefix): (NodeId, &dyn Vfs, &[u8]) = if Self::system_id(id) {
            (self.system_local(id)?, self.archive()?, b"/system")
        } else if Self::disk(id) {
            (self.local(id)?, self.backend()?, b"/mnt/rosti")
        } else {
            return self.ram.path(id, buf);
        };
        let mut tail = [0; MAX_PATH];
        let len = b.path(n, &mut tail)?;
        let suffix = if n == b.root() {
            &tail[..0]
        } else {
            &tail[..len]
        };
        let total = prefix.len() + suffix.len();
        if total > MAX_PATH || total > buf.len() {
            return Err(FsError::InvalidPath);
        }
        buf[..prefix.len()].copy_from_slice(prefix);
        buf[prefix.len()..total].copy_from_slice(suffix);
        Ok(total)
    }
    fn stats(&self) -> FsStats {
        let mut s = self.ram.stats();
        if let Some(b) = self.backend.as_deref() {
            let d = b.stats();
            s.nodes += d.nodes - 1;
            s.logical_bytes += d.logical_bytes;
            s.allocated_bytes += d.allocated_bytes;
            s.metadata_bytes += d.metadata_bytes + core::mem::size_of_val(&self.bindings);
        }
        s
    }
}
