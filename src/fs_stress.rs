//! Explicit, bounded main-context growth/OOM fixture; never runs at boot.
//! Uses only fallible allocations and cleans up its own reserved directory.
//! Expanded heap pages remain mapped for reuse (the heap does not shrink).

use crate::fs::{FsError, MAX_FILE_SIZE, NodeId, Vfs};
use alloc::vec::Vec;

const DIRECTORY: &str = "/__fsstress";
const NAMES: [&str; 10] = ["a", "b", "c", "d", "e", "f", "g", "h", "quota", "probe"];

struct Fixture<'a, F: Vfs> {
    fs: &'a mut F,
    directory: NodeId,
    files: [Option<NodeId>; 10],
}

impl<'a, F: Vfs> Fixture<'a, F> {
    fn new(fs: &'a mut F) -> Result<Self, FsError> {
        // Never overwrite user data or clean up a pre-existing directory.
        let directory = fs.create_dir(fs.root(), DIRECTORY)?;
        Ok(Self {
            fs,
            directory,
            files: [None; 10],
        })
    }

    fn create(&mut self, index: usize) -> Result<NodeId, FsError> {
        let id = self.fs.create_file(self.directory, NAMES[index])?;
        self.files[index] = Some(id);
        Ok(id)
    }

    fn remove(&mut self, index: usize) -> Result<(), FsError> {
        self.fs.remove_file(self.directory, NAMES[index])?;
        self.files[index] = None;
        Ok(())
    }

    fn verify(&self, count: usize) -> Result<(), FsError> {
        let mut bytes = [0; 1024];
        for index in 0..count {
            let id = self.files[index].ok_or(FsError::NotFound)?;
            if self.fs.metadata(id)?.size != MAX_FILE_SIZE {
                return Err(FsError::InvalidPath);
            }
            for offset in (0..MAX_FILE_SIZE).step_by(bytes.len()) {
                let n = self.fs.read(id, offset, &mut bytes)?;
                if n != bytes.len()
                    || bytes
                        .iter()
                        .enumerate()
                        .any(|(i, b)| *b != ((offset + i) % 251) as u8)
                {
                    return Err(FsError::InvalidPath);
                }
            }
        }
        Ok(())
    }
}

impl<F: Vfs> Drop for Fixture<'_, F> {
    fn drop(&mut self) {
        for (index, id) in self.files.iter().enumerate() {
            if id.is_some() {
                let _ = self.fs.remove_file(self.directory, NAMES[index]);
            }
        }
        let _ = self.fs.remove_dir(self.fs.root(), DIRECTORY);
    }
}

pub fn run(fs: &mut impl Vfs, out: &mut dyn FnMut(core::fmt::Arguments<'_>)) {
    let before_fs = fs.stats();
    let before_heap = crate::allocator::heap_stats();
    let before_maps = crate::memory::mapped_pages();
    let result = exercise(fs, out);
    let after_heap = crate::allocator::heap_stats();
    let after_fs = fs.stats();
    let clean = before_fs == after_fs
        && after_heap.used == before_heap.used
        && after_heap.live_allocs == before_heap.live_allocs
        && after_heap.invalid_deallocs == before_heap.invalid_deallocs
        && after_heap.growth_pages > before_heap.growth_pages
        && after_heap.failed_allocs > before_heap.failed_allocs;
    // Drop all buffers and filesystem data before these diagnostics.
    out(format_args!(
        "fsstress: heap used {} -> {}, growth {} -> {}, failed {} -> {}\n",
        before_heap.used,
        after_heap.used,
        before_heap.growth_pages,
        after_heap.growth_pages,
        before_heap.failed_allocs,
        after_heap.failed_allocs
    ));
    out(format_args!(
        "fsstress: mapped pages {} -> {}, FS storage {} -> {}, nodes {} -> {}\n",
        before_maps,
        crate::memory::mapped_pages(),
        before_fs.allocated_bytes,
        after_fs.allocated_bytes,
        before_fs.nodes,
        after_fs.nodes
    ));
    match result {
        Ok(()) if clean => out(format_args!("fsstress: PASS\n")),
        Ok(()) => out(format_args!(
            "fsstress: FAIL (accounting or growth invariant)\n"
        )),
        Err(error) => out(format_args!("fsstress: FAIL ({})\n", error)),
    }
}

fn exercise(
    fs: &mut impl Vfs,
    out: &mut dyn FnMut(core::fmt::Arguments<'_>),
) -> Result<(), FsError> {
    let mut fixture = Fixture::new(fs)?;
    let mut data = Vec::new();
    data.try_reserve_exact(MAX_FILE_SIZE)
        .map_err(|_| FsError::OutOfMemory)?;
    data.resize(MAX_FILE_SIZE, 0);
    for (i, b) in data.iter_mut().enumerate() {
        *b = (i % 251) as u8;
    }
    for i in 0..8 {
        let id = fixture.create(i)?;
        fixture.fs.replace(id, &data)?;
    }
    fixture.verify(8)?;
    out(format_args!("fsstress: 4194304 data bytes verified\n"));
    let quota = fixture.create(8)?;
    let stats = fixture.fs.stats();
    if fixture.fs.replace(quota, b"x") != Err(FsError::FilesystemFull)
        || fixture.fs.stats() != stats
        || fixture.fs.metadata(quota)?.size != 0
    {
        return Err(FsError::InvalidPath);
    }
    fixture.remove(8)?;
    for i in 3..8 {
        fixture.remove(i)?;
    }
    let probe = fixture.create(9)?;
    fixture.fs.replace(probe, b"old")?;
    drop(data);

    // Request more than the entire 7 MiB managed heap: the allocator maps all
    // remaining growth pages, then returns null through try_reserve, not panic.
    let mut impossible = Vec::<u8>::new();
    if impossible.try_reserve_exact(8 * 1024 * 1024).is_ok() {
        return Err(FsError::InvalidPath);
    }
    drop(impossible);

    // Claim every usable free-list block without allocating our bookkeeping.
    // The 64-buffer bound matches the node bound. Refuse to test if fragment
    // count exceeds it; cleanup still runs and no unrelated file is changed.
    let mut held: [Vec<u8>; 64] = [const { Vec::new() }; 64];
    for buffer in &mut held {
        let largest = crate::allocator::heap_stats().largest_free;
        if largest <= crate::allocator::HEADER_SIZE {
            break;
        }
        buffer
            .try_reserve_exact(largest - crate::allocator::HEADER_SIZE)
            .map_err(|_| FsError::OutOfMemory)?;
    }
    if crate::allocator::heap_stats().largest_free > crate::allocator::HEADER_SIZE {
        return Err(FsError::InvalidPath);
    }
    let stats = fixture.fs.stats();
    let bytes = [0xa5; 1024];
    // These are REAL KernelHeap allocation failures; existing data and metadata
    // must remain unchanged on replace, offset write and extending truncate.
    let oom_safe = fixture.fs.replace(probe, &bytes) == Err(FsError::OutOfMemory)
        && fixture.fs.write(probe, 3, &bytes) == Err(FsError::OutOfMemory)
        && fixture.fs.truncate(probe, 1024) == Err(FsError::OutOfMemory)
        && fixture.fs.stats() == stats;
    let mut original = [0; 4];
    let original_safe = fixture.fs.read(probe, 0, &mut original)? == 3 && &original[..3] == b"old";
    drop(held);
    if !oom_safe || !original_safe {
        return Err(FsError::InvalidPath);
    }
    out(format_args!(
        "fsstress: quota and real heap OOM preserve metadata/data\n"
    ));
    fixture.verify(3)?;

    // Only owned scalar snapshots escape paging ownership.
    let growth = crate::allocator::heap_stats().growth_pages;
    let mapped = (0..growth).all(|i| {
        let page = (crate::memory::GROWTH_START + i * 4096) as u64;
        crate::memory::page_snapshot(page).is_some_and(|snapshot| {
            snapshot.physical_frame == Some(page)
                && snapshot
                    .permissions
                    .is_some_and(|p| p.present && p.writable && !p.user)
        })
    });
    if !mapped {
        return Err(FsError::InvalidPath);
    }
    out(format_args!(
        "fsstress: {} growth pages present writable supervisor identity-mapped\n",
        growth
    ));
    // Fixture's Drop deletes all owned files/directories even on early error.
    Ok(())
}
