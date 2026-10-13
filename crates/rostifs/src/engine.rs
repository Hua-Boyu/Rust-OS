//! Two metadata banks, data COW, and CRC-protected alternating root publication.
//! Data -> flush -> inactive metadata -> flush -> inactive root -> flush.
//! Both valid roots' data remain protected until the next root is committed.
//! I/O failure poisons mutations until remount (commit outcome is ambiguous).
//! RefCell gives checked exclusive device access, including &self VFS reads;
//! no unsafe code, no allocation. Keep the instance in static/heap storage and
//! use mount_in_place in the kernel. By-value mount/format are host conveniences.
use crate::{
    block::BlockDevice,
    checksum::{crc32c, update},
    format::*,
    vfs::*,
};
use core::cell::RefCell;
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct MountInfo {
    pub fs_id: u64,
    pub generation: u64,
    pub total_blocks: u32,
    pub free_blocks: u32,
    pub used_blocks: u32,
    pub leaked_blocks: u32,
    pub metadata_bytes: usize,
    /// Number of independently validated roots (1 means degraded recovery).
    pub valid_roots: u8,
}
pub struct RostiFs<'a> {
    device: RefCell<&'a mut dyn BlockDevice>,
    scratch: RefCell<[u8; FS_BLOCK_SIZE]>,
    sb: Superblock,
    nodes: [Inode; MAX_INODES],
    previous: [Inode; MAX_INODES],
    staged: [Inode; MAX_INODES],
    mounted: bool,
    poisoned: bool,
    valid_roots: u8,
}
impl<'a> RostiFs<'a> {
    pub const fn new(device: &'a mut dyn BlockDevice) -> Self {
        Self {
            device: RefCell::new(device),
            scratch: RefCell::new([0; FS_BLOCK_SIZE]),
            sb: Superblock {
                fs_id: 0,
                generation: 0,
                total_blocks: 0,
                bank: 0,
                metadata_crc: [0; 2],
            },
            nodes: [Inode::EMPTY; MAX_INODES],
            previous: [Inode::EMPTY; MAX_INODES],
            staged: [Inode::EMPTY; MAX_INODES],
            mounted: false,
            poisoned: false,
            valid_roots: 0,
        }
    }
    fn read_block(&self, b: usize, out: &mut [u8]) -> Result<(), FsError> {
        self.device
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?
            .read_block(b, out)
            .map_err(|_| FsError::DeviceIo)
    }
    fn write_block(&self, b: usize, data: &[u8]) -> Result<(), FsError> {
        self.device
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?
            .write_block(b, data)
            .map_err(|_| FsError::DeviceIo)
    }
    fn flush(&self) -> Result<(), FsError> {
        self.device
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?
            .flush()
            .map_err(|_| FsError::DeviceIo)
    }
    pub fn metadata_bytes(&self) -> usize {
        core::mem::size_of::<Self>()
    }
    pub fn mount_info(&self) -> MountInfo {
        let used = (DATA_START..self.sb.total_blocks as usize)
            .filter(|&b| Self::occupied(&self.nodes, b) || Self::occupied(&self.previous, b))
            .count()
            + DATA_START;
        MountInfo {
            fs_id: self.sb.fs_id,
            generation: self.sb.generation,
            total_blocks: self.sb.total_blocks,
            free_blocks: self.sb.total_blocks.saturating_sub(used as u32),
            used_blocks: used as u32,
            leaked_blocks: 0,
            metadata_bytes: self.metadata_bytes(),
            valid_roots: self.valid_roots,
        }
    }
    pub fn mount(device: &'a mut dyn BlockDevice) -> Result<Self, FsError> {
        let mut fs = Self::new(device);
        fs.mount_in_place()?;
        Ok(fs)
    }
    pub fn mount_in_place(&mut self) -> Result<(), FsError> {
        self.mounted = false;
        self.poisoned = true;
        let cap = {
            let d = self.device.try_borrow().map_err(|_| FsError::DeviceIo)?;
            if d.sector_size() != 512 {
                return Err(FsError::CorruptVolume);
            }
            d.capacity_sectors()
        };
        let mut roots = [None, None];
        let mut last = FsError::CorruptVolume;
        for (bank, root) in roots.iter_mut().enumerate() {
            match self.load_candidate(bank, cap) {
                Ok(sb) => {
                    if bank == 0 {
                        self.nodes.copy_from_slice(&self.staged);
                    } else {
                        self.previous.copy_from_slice(&self.staged);
                    }
                    *root = Some(sb);
                }
                Err(e) => {
                    // Do not overwrite an unreadable or future-format root using
                    // an older snapshot: its protected data set is unknown.
                    if e == FsError::DeviceIo || e == FsError::UnsupportedVersion {
                        return Err(e);
                    }
                    last = e;
                }
            }
        }
        self.valid_roots = roots.iter().filter(|r| r.is_some()).count() as u8;
        match (roots[0], roots[1]) {
            (None, None) => return Err(last),
            (Some(a), Some(b)) => {
                if a.fs_id != b.fs_id
                    || a.total_blocks != b.total_blocks
                    || a.generation.abs_diff(b.generation) != 1
                {
                    return Err(FsError::CorruptVolume);
                }
                if b.generation > a.generation {
                    core::mem::swap(&mut self.nodes, &mut self.previous);
                    self.sb = b;
                } else {
                    self.sb = a;
                }
            }
            (Some(a), None) => {
                self.sb = a;
                self.previous.fill(Inode::EMPTY);
            }
            (None, Some(b)) => {
                self.sb = b;
                self.nodes.copy_from_slice(&self.previous);
                self.previous.fill(Inode::EMPTY);
            }
        }
        self.mounted = true;
        self.poisoned = false;
        Ok(())
    }
    fn load_candidate(&mut self, bank: usize, cap: usize) -> Result<Superblock, FsError> {
        let mut page = self
            .scratch
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?;
        self.read_block(1 + bank, &mut *page)?;
        let sb = Superblock::decode(&page, bank, cap)?;
        for p in 0..METADATA_BLOCKS {
            self.read_block(3 + bank * METADATA_BLOCKS + p, &mut *page)?;
            if crc32c(&*page) != sb.metadata_crc[p] {
                return Err(FsError::CorruptVolume);
            }
            for j in 0..32 {
                self.staged[p * 32 + j] = Inode::decode(&page[j * 128..(j + 1) * 128])?;
            }
        }
        drop(page);
        self.validate(&self.staged, sb.total_blocks)?;
        Ok(sb)
    }
    fn validate(&self, ns: &[Inode; MAX_INODES], total: u32) -> Result<(), FsError> {
        let bad = FsError::CorruptVolume;
        if ns[0].kind != TYPE_DIR
            || ns[0].generation != 0
            || ns[0].parent != 0
            || ns[0].name_len != 0
        {
            return Err(bad);
        }
        for (i, n) in ns.iter().enumerate() {
            if n.kind == 0 {
                let mut empty = Inode::EMPTY;
                empty.generation = n.generation;
                if *n != empty {
                    return Err(bad);
                }
                continue;
            }
            if n.kind != TYPE_DIR && n.kind != TYPE_FILE {
                return Err(bad);
            }
            if n.name_len as usize > MAX_NAME_LEN
                || n.name[n.name_len as usize..].iter().any(|&b| b != 0)
            {
                return Err(bad);
            }
            if i != 0 {
                if !valid_name(
                    core::str::from_utf8(&n.name[..n.name_len as usize]).map_err(|_| bad)?,
                ) || n.parent as usize >= MAX_INODES
                    || ns[n.parent as usize].kind != TYPE_DIR
                {
                    return Err(bad);
                }
                let mut parent = i;
                let mut path_bytes = 0usize;
                for step in 0..MAX_INODES {
                    if parent == 0 {
                        break;
                    }
                    path_bytes += ns[parent].name_len as usize + 1;
                    if path_bytes > MAX_PATH_LEN {
                        return Err(bad);
                    }
                    parent = ns[parent].parent as usize;
                    if parent >= MAX_INODES || step == MAX_INODES - 1 {
                        return Err(bad);
                    }
                }
                if ns[..i].iter().any(|x| {
                    x.kind != 0
                        && x.parent == n.parent
                        && x.name_len == n.name_len
                        && x.name == n.name
                }) {
                    return Err(bad);
                }
            }
            if n.kind == TYPE_DIR {
                if n.size != 0 || n.start != 0 || n.blocks != 0 || n.data_crc != 0 {
                    return Err(bad);
                }
                continue;
            }
            if n.size as usize > MAX_FILE_BYTES
                || n.blocks != (n.size as usize).div_ceil(FS_BLOCK_SIZE) as u32
            {
                return Err(bad);
            }
            if n.blocks == 0 {
                if n.start != 0 || n.data_crc != 0 {
                    return Err(bad);
                }
                continue;
            }
            let end = n.start.checked_add(n.blocks).ok_or(bad)?;
            if n.start < DATA_START as u32 || end > total {
                return Err(bad);
            }
            for x in &ns[..i] {
                if x.blocks != 0 && n.start < x.start + x.blocks && x.start < end {
                    return Err(bad);
                }
            }
            let mut page = self
                .scratch
                .try_borrow_mut()
                .map_err(|_| FsError::DeviceIo)?;
            let mut crc = !0;
            for b in n.start..end {
                self.read_block(b as usize, &mut *page)?;
                crc = update(crc, &*page);
            }
            if !crc != n.data_crc {
                return Err(bad);
            }
        }
        Ok(())
    }
    /// Host-only explicit formatting; never a mount fallback. Device must be test-owned.
    #[cfg(any(test, feature = "host-tools"))]
    pub fn format(device: &mut dyn BlockDevice, fs_id: u64) -> Result<Superblock, FsError> {
        if !device.test_owned() {
            return Err(FsError::InvalidPath);
        }
        let cap = device.capacity_sectors();
        if device.sector_size() != 512
            || cap % 8 != 0
            || !(DATA_START..=MAX_VOLUME_BLOCKS).contains(&(cap / 8))
        {
            return Err(FsError::FilesystemFull);
        }
        let mut fs = RostiFs::new(device);
        fs.sb.total_blocks = (cap / 8) as u32;
        fs.sb.fs_id = fs_id;
        fs.staged[0].kind = TYPE_DIR;
        // Invalidate roots first: formatting has no transactional preservation promise.
        let mut page = [0u8; FS_BLOCK_SIZE];
        fs.write_block(1, &page)?;
        fs.write_block(2, &page)?;
        fs.flush()?;
        for bank in 0..2 {
            let mut sb = fs.sb;
            sb.bank = bank;
            sb.generation = bank as u64;
            fs.write_metadata(&mut sb)?;
            fs.flush()?;
            sb.encode(&mut page);
            fs.write_block(1 + bank as usize, &page)?;
            fs.flush()?;
            fs.sb = sb;
        }
        Ok(fs.sb)
    }
    fn write_metadata(&self, sb: &mut Superblock) -> Result<(), FsError> {
        let mut page = self
            .scratch
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?;
        for p in 0..2 {
            for j in 0..32 {
                self.staged[p * 32 + j].encode(&mut page[j * 128..(j + 1) * 128]);
            }
            sb.metadata_crc[p] = crc32c(&*page);
            self.write_block(3 + sb.bank as usize * 2 + p, &*page)?;
        }
        Ok(())
    }
    fn begin(&mut self) -> Result<(), FsError> {
        if !self.mounted {
            return Err(FsError::CorruptVolume);
        }
        if self.poisoned {
            return Err(FsError::DeviceIo);
        }
        if self.sb.generation == u64::MAX {
            return Err(FsError::FilesystemFull);
        }
        self.staged.copy_from_slice(&self.nodes);
        Ok(())
    }
    fn commit(&mut self) -> Result<(), FsError> {
        self.poisoned = true;
        let mut sb = self.sb;
        sb.generation += 1;
        sb.bank ^= 1;
        self.flush()?;
        self.write_metadata(&mut sb)?;
        self.flush()?;
        let mut page = self
            .scratch
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?;
        sb.encode(&mut *page);
        self.write_block(1 + sb.bank as usize, &*page)?;
        self.flush()?;
        self.previous.copy_from_slice(&self.nodes);
        self.nodes.copy_from_slice(&self.staged);
        self.sb = sb;
        self.valid_roots = 2;
        self.poisoned = false;
        Ok(())
    }
    fn occupied(ns: &[Inode; MAX_INODES], b: usize) -> bool {
        ns.iter().any(|n| {
            n.blocks != 0 && b >= n.start as usize && b < n.start as usize + n.blocks as usize
        })
    }
    fn allocate(&self, count: usize) -> Result<usize, FsError> {
        if count == 0 {
            return Ok(0);
        }
        for b in DATA_START..=self.sb.total_blocks as usize {
            let Some(end) = b.checked_add(count) else {
                break;
            };
            if end > self.sb.total_blocks as usize {
                break;
            }
            if (b..end)
                .all(|x| !Self::occupied(&self.nodes, x) && !Self::occupied(&self.previous, x))
            {
                return Ok(b);
            }
        }
        Err(FsError::FilesystemFull)
    }
    fn id(&self, i: usize) -> NodeId {
        NodeId::new(i as u8, self.nodes[i].generation)
    }
    fn index(&self, id: NodeId) -> Result<usize, FsError> {
        let i = id.slot as usize;
        if !self.mounted {
            return Err(FsError::CorruptVolume);
        }
        if i >= MAX_INODES || self.nodes[i].kind == 0 || self.nodes[i].generation != id.generation {
            return Err(FsError::NotFound);
        }
        Ok(i)
    }
    fn name(n: &Inode) -> &str {
        core::str::from_utf8(&n.name[..n.name_len as usize]).unwrap_or("")
    }
    fn directory(&self, i: usize) -> Result<(), FsError> {
        if self.nodes[i].kind != TYPE_DIR {
            Err(FsError::NotADirectory)
        } else {
            Ok(())
        }
    }
    fn child(&self, parent: usize, name: &str) -> Option<usize> {
        (1..MAX_INODES).find(|&i| {
            self.nodes[i].kind != 0
                && self.nodes[i].parent as usize == parent
                && Self::name(&self.nodes[i]) == name
        })
    }
    fn check_path(path: &str) -> Result<(), FsError> {
        if path.is_empty()
            || path.len() > MAX_PATH_LEN
            || path.chars().any(|c| c.is_control() || c == '\\')
            || path.split('/').any(|s| s.len() > MAX_NAME_LEN)
        {
            Err(FsError::InvalidPath)
        } else {
            Ok(())
        }
    }
    fn parent<'p>(&self, cwd: NodeId, path: &'p str) -> Result<(usize, &'p str), FsError> {
        Self::check_path(path)?;
        let (prefix, name) = match path.rsplit_once('/') {
            Some((p, n)) => (if p.is_empty() { "/" } else { p }, n),
            None => (".", path),
        };
        if !valid_name(name) {
            return Err(FsError::InvalidPath);
        }
        let p = self.index(self.lookup(cwd, prefix)?)?;
        self.directory(p)?;
        Ok((p, name))
    }
    fn create(&mut self, cwd: NodeId, path: &str, kind: u8) -> Result<NodeId, FsError> {
        let (p, name) = self.parent(cwd, path)?;
        if self.child(p, name).is_some() {
            return Err(FsError::AlreadyExists);
        }
        let i = (1..MAX_INODES)
            .find(|&i| self.nodes[i].kind == 0 && self.nodes[i].generation != u32::MAX)
            .ok_or(FsError::FilesystemFull)?;
        // Canonical path bound is independent of a relative input's length.
        let mut buf = [0u8; MAX_PATH_LEN];
        let len = self.path(self.id(p), &mut buf)?;
        if len + usize::from(p != 0) + name.len() > MAX_PATH_LEN {
            return Err(FsError::InvalidPath);
        }
        self.begin()?;
        let n = &mut self.staged[i];
        n.kind = kind;
        n.parent = p as u8;
        n.name_len = name.len() as u8;
        n.name[..name.len()].copy_from_slice(name.as_bytes());
        self.commit()?;
        Ok(self.id(i))
    }
    fn remove(&mut self, cwd: NodeId, path: &str, kind: u8) -> Result<(), FsError> {
        let (p, name) = self.parent(cwd, path)?;
        let i = self.child(p, name).ok_or(FsError::NotFound)?;
        if self.nodes[i].kind != kind {
            return Err(if kind == TYPE_FILE {
                FsError::IsADirectory
            } else {
                FsError::NotADirectory
            });
        }
        if kind == TYPE_DIR
            && self
                .nodes
                .iter()
                .any(|n| n.kind != 0 && n.parent as usize == i)
        {
            return Err(FsError::DirectoryNotEmpty);
        }
        self.begin()?;
        let generation = self.staged[i].generation.saturating_add(1);
        self.staged[i] = Inode::EMPTY;
        self.staged[i].generation = generation;
        self.commit()
    }
    fn change(
        &mut self,
        id: NodeId,
        len: usize,
        offset: usize,
        data: &[u8],
        preserve: bool,
    ) -> Result<(), FsError> {
        let i = self.index(id)?;
        let old = self.nodes[i];
        if old.kind != TYPE_FILE {
            return Err(FsError::IsADirectory);
        }
        if len > MAX_FILE_BYTES {
            return Err(FsError::FileTooLarge);
        }
        self.begin()?;
        let blocks = len.div_ceil(FS_BLOCK_SIZE);
        let start = self.allocate(blocks)?;
        let mut page = self
            .scratch
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?;
        let mut crc = !0;
        // Only COW destinations are written, so a read/write failure cannot harm roots.
        for b in 0..blocks {
            page.fill(0);
            let base = b * FS_BLOCK_SIZE;
            if preserve && base < old.size as usize {
                self.read_block(old.start as usize + b, &mut *page)?;
                let keep = (old.size as usize - base)
                    .min(FS_BLOCK_SIZE)
                    .min(len - base);
                page[keep..].fill(0);
            }
            let low = base.max(offset);
            let high = (base + FS_BLOCK_SIZE).min(offset + data.len()).min(len);
            if low < high {
                page[low - base..high - base].copy_from_slice(&data[low - offset..high - offset]);
            }
            if len < base + FS_BLOCK_SIZE {
                page[len - base..].fill(0);
            }
            crc = update(crc, &*page);
            self.poisoned = true;
            self.write_block(start + b, &*page)?;
        }
        drop(page);
        self.staged[i].size = len as u32;
        self.staged[i].start = start as u32;
        self.staged[i].blocks = blocks as u32;
        self.staged[i].data_crc = if blocks == 0 { 0 } else { !crc };
        self.commit()
    }
    pub fn append(&mut self, id: NodeId, data: &[u8]) -> Result<usize, FsError> {
        let size = self.metadata(id)?.size;
        self.write(id, size, data)
    }
}
impl Vfs for RostiFs<'_> {
    fn root(&self) -> NodeId {
        NodeId::ROOT
    }
    fn lookup(&self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        Self::check_path(path)?;
        let mut i = if path.starts_with('/') {
            self.index(NodeId::ROOT)?
        } else {
            self.index(cwd)?
        };
        for c in path.split('/').filter(|s| !s.is_empty()) {
            self.directory(i)?;
            if c == "." {
                continue;
            }
            if c == ".." {
                i = self.nodes[i].parent as usize;
            } else {
                i = self.child(i, c).ok_or(FsError::NotFound)?;
            }
        }
        if path.ends_with('/') {
            self.directory(i)?;
        }
        Ok(self.id(i))
    }
    fn create_file(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.create(cwd, path, TYPE_FILE)
    }
    fn create_dir(&mut self, cwd: NodeId, path: &str) -> Result<NodeId, FsError> {
        self.create(cwd, path, TYPE_DIR)
    }
    fn metadata(&self, id: NodeId) -> Result<Metadata, FsError> {
        let n = self.nodes[self.index(id)?];
        Ok(Metadata {
            kind: if n.kind == TYPE_FILE {
                NodeKind::File
            } else {
                NodeKind::Directory
            },
            size: n.size as usize,
        })
    }
    fn read(&self, id: NodeId, offset: usize, out: &mut [u8]) -> Result<usize, FsError> {
        let n = self.nodes[self.index(id)?];
        if n.kind != TYPE_FILE {
            return Err(FsError::IsADirectory);
        }
        let count = out.len().min((n.size as usize).saturating_sub(offset));
        let mut done = 0;
        let mut page = self
            .scratch
            .try_borrow_mut()
            .map_err(|_| FsError::DeviceIo)?;
        while done < count {
            let pos = offset + done;
            self.read_block(n.start as usize + pos / FS_BLOCK_SIZE, &mut *page)?;
            let take = (FS_BLOCK_SIZE - pos % FS_BLOCK_SIZE).min(count - done);
            out[done..done + take]
                .copy_from_slice(&page[pos % FS_BLOCK_SIZE..pos % FS_BLOCK_SIZE + take]);
            done += take;
        }
        Ok(count)
    }
    fn write(&mut self, id: NodeId, offset: usize, data: &[u8]) -> Result<usize, FsError> {
        let old = self.metadata(id)?;
        if old.kind != NodeKind::File {
            return Err(FsError::IsADirectory);
        }
        let end = offset
            .checked_add(data.len())
            .ok_or(FsError::FileTooLarge)?;
        if data.is_empty() {
            return Ok(0);
        }
        self.change(id, old.size.max(end), offset, data, true)?;
        Ok(data.len())
    }
    fn replace(&mut self, id: NodeId, data: &[u8]) -> Result<(), FsError> {
        self.change(id, data.len(), 0, data, false)
    }
    fn truncate(&mut self, id: NodeId, len: usize) -> Result<(), FsError> {
        self.change(id, len, 0, &[], true)
    }
    fn remove_file(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        self.remove(cwd, path, TYPE_FILE)
    }
    fn remove_dir(&mut self, cwd: NodeId, path: &str) -> Result<(), FsError> {
        self.remove(cwd, path, TYPE_DIR)
    }
    fn list(
        &self,
        id: NodeId,
        visitor: &mut dyn FnMut(&str, NodeId, NodeKind),
    ) -> Result<(), FsError> {
        let i = self.index(id)?;
        self.directory(i)?;
        for j in 1..MAX_INODES {
            let n = &self.nodes[j];
            if n.kind != 0 && n.parent as usize == i {
                visitor(
                    Self::name(n),
                    self.id(j),
                    if n.kind == TYPE_FILE {
                        NodeKind::File
                    } else {
                        NodeKind::Directory
                    },
                );
            }
        }
        Ok(())
    }
    fn path(&self, id: NodeId, out: &mut [u8]) -> Result<usize, FsError> {
        let mut i = self.index(id)?;
        let mut chain = [0usize; MAX_INODES];
        let mut depth = 0;
        let mut size = 1;
        while i != 0 {
            chain[depth] = i;
            depth += 1;
            size += self.nodes[i].name_len as usize + usize::from(depth > 1);
            i = self.nodes[i].parent as usize;
        }
        if size > out.len() {
            return Err(FsError::InvalidPath);
        }
        out[0] = b'/';
        let mut pos = 1;
        for &j in chain[..depth].iter().rev() {
            if pos > 1 {
                out[pos] = b'/';
                pos += 1;
            }
            let n = &self.nodes[j];
            out[pos..pos + n.name_len as usize].copy_from_slice(&n.name[..n.name_len as usize]);
            pos += n.name_len as usize;
        }
        Ok(pos)
    }
    fn stats(&self) -> FsStats {
        FsStats {
            nodes: self.nodes.iter().filter(|n| n.kind != 0).count(),
            logical_bytes: self.nodes.iter().map(|n| n.size as usize).sum(),
            allocated_bytes: self
                .nodes
                .iter()
                .map(|n| n.blocks as usize * FS_BLOCK_SIZE)
                .sum(),
            metadata_bytes: self.metadata_bytes(),
        }
    }
}
