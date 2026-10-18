//! Physical memory subsystem: frame allocator + paging.
//!
//! Init order in kernel_main: bump allocator (so Vec works) -> frame
//! allocator init from the multiboot mmap -> page tables built from managed
//! frames -> mapping validated -> paging enabled (after the IDT is loaded, so
//! any fault is handled by the vector-14 handler).

pub(crate) mod boot_copy;
pub mod frame;
pub mod paging;

#[cfg(test)]
mod module_access_tests;
#[cfg(test)]
mod review_r1_tests;

pub use paging::{GROWTH_END, GROWTH_START};

extern crate alloc;
use alloc::vec::Vec;
use core::sync::atomic::{AtomicBool, Ordering};

use crate::multiboot::MmapEntry;
use crate::utils::mutex::SpinMutex;

/// Serial diagnostics are hardware-dependent: active in kernel builds,
/// no-op in the host-test harness (which has no COM1).
fn dbg(s: &str) {
    #[cfg(not(test))]
    crate::io::serial::puts(s);
    #[cfg(test)]
    let _ = s;
}

pub static FRAME_ALLOC: SpinMutex<frame::FrameAllocator> =
    SpinMutex::new(frame::FrameAllocator::new());

// Private owner: no reference or guard is exported. Queries return owned scalars.
// Production critical sections never allocate/drop backing or invoke callbacks.
// Lock order is heap -> PAGE_MAP -> FRAME_ALLOC; IRQs must not acquire either.
static PAGE_MAP: SpinMutex<Option<paging::PageMap>> = SpinMutex::new(None);
static PAGING_ENABLED: AtomicBool = AtomicBool::new(false);

/// Highest address the identity map must cover: the end of the highest usable
/// mmap range, OR the end of the kernel image if the kernel is loaded above
/// it (the kernel executes from .text/.bss, so its frames must be mapped).
pub fn managed_window_end(entries: &[MmapEntry]) -> u64 {
    let mmap_end = entries
        .iter()
        .filter(|e| e.type_ == 1)
        .filter(|e| e.base_addr < (1u64 << 32))
        .filter_map(|e| e.base_addr.checked_add(e.length))
        .map(|end| end.min(1u64 << 32))
        .max()
        .unwrap_or(0);
    let (_, kend) = frame::kernel_bounds();
    mmap_end.max(kend)
}

/// Regions that MUST be mapped before paging is enabled. Validation is
/// explicit so a bug shows up as a named missing region instead of a fault.
pub fn required_region_iter(
    entries: &[MmapEntry],
    bootinfo_addr: u64,
) -> impl Iterator<Item = (u64, u64, &'static str)> + '_ {
    #[cfg(not(test))]
    let kernel = {
        let (start, end) = frame::kernel_bounds();
        (start, end, "kernel image (incl. boot stack)")
    };
    #[cfg(test)]
    let kernel = (4096, 8192, "kernel image (test dummy)");
    [
        kernel,
        (0xB8000, 0xBC000, "VGA framebuffer"),
        (bootinfo_addr, bootinfo_addr + 4096, "multiboot info struct"),
    ]
    .into_iter()
    .chain(entries.iter().filter_map(|e| {
        if e.type_ != 1 || e.base_addr >= (1u64 << 32) {
            return None;
        }
        let end = e.base_addr.checked_add(e.length)?.min(1u64 << 32);
        let start = e.base_addr.max(paging::PAGE_SIZE as u64);
        // Validation skips individual growth pages. Do not discard an entire
        // usable record merely because its first page lies in that window.
        Some((start, end, "usable mmap range"))
    }))
}

/// Allocating compatibility helper for unlocked host tests only.
#[cfg(test)]
pub fn required_regions(
    entries: &[MmapEntry],
    bootinfo_addr: u64,
) -> Vec<(u64, u64, &'static str)> {
    required_region_iter(entries, bootinfo_addr).collect()
}

/// Retain all nonusable inventory entries conservatively: production carries
/// module and metadata reservations as synthetic type-2 records. Only identity
/// pages in the managed window need pins; firmware ranges above it are unmapped.
/// The header's existing 4 KiB physical reservation is retained in full.
fn permanent_boot_pins(
    entries: &[MmapEntry],
    bootinfo_addr: u64,
    window: u64,
) -> Result<Vec<(u64, u64)>, &'static str> {
    let limit = 1u64 << 32;
    let header_end = bootinfo_addr
        .checked_add(4096)
        .filter(|&end| bootinfo_addr != 0 && end <= limit)
        .ok_or("invalid multiboot info address")?;
    let mut pins = Vec::new();
    let capacity = entries
        .len()
        .checked_add(1)
        .ok_or("boot pin capacity overflow")?;
    pins.try_reserve_exact(capacity)
        .map_err(|_| "boot pin backing allocation failed")?;
    let mask = paging::PAGE_SIZE as u64 - 1;
    pins.push((bootinfo_addr & !mask, (header_end + mask) & !mask));
    for entry in entries.iter().filter(|e| e.type_ != 1 && e.length != 0) {
        let end = entry
            .base_addr
            .checked_add(entry.length)
            .ok_or("invalid nonusable mmap span")?;
        let end = end.min(window).min(limit);
        let start = entry.base_addr.max(paging::PAGE_SIZE as u64);
        if start < end {
            pins.push((start & !mask, (end + mask) & !mask));
        }
    }
    Ok(pins)
}

/// Initialize the frame allocator and build + validate the identity map.
/// Does NOT enable paging — call enable_paging() after the IDT is loaded.
/// Returns Ok(window_end) or the first static failure diagnostic.
/// Boot-only, serialized by the kernel's single-owner initialization path.
/// Once a map is published, reject reinitialization before touching the frame
/// allocator or replacing published backing.
/// Table/pin/payload backing reservations are fallible and happen outside the frame
/// guard. Failure diagnostics never allocate, including reserve failures.
pub fn prepare(
    entries: &[MmapEntry],
    bootinfo_addr: u64,
    bump_start: u64,
    bump_end: u64,
) -> Result<u64, &'static str> {
    if page_directory().is_some() {
        return Err("paging already prepared");
    }
    dbg("DBG: frame init start\n");
    // Pre-allocate the table vector BEFORE taking the frame lock: heap
    // allocation must never happen while the frame lock is held (the heap
    // growth path takes heap -> frame; this would invert the order).
    let window = managed_window_end(entries);
    let mut boot_pins = permanent_boot_pins(entries, bootinfo_addr, window)?;
    let mut tables = Vec::new();
    tables
        .try_reserve_exact(paging::PAGE_DIR_ENTRIES)
        .map_err(|_| "page table backing allocation failed")?;
    tables.resize(paging::PAGE_DIR_ENTRIES, 0u64);
    let mut payload_bitmap = Vec::new();
    payload_bitmap
        .try_reserve_exact(paging::PAYLOAD_BITMAP_BYTES)
        .map_err(|_| "payload registry backing allocation failed")?;
    payload_bitmap.resize(paging::PAYLOAD_BITMAP_BYTES, 0);

    // Recheck under exclusive ownership after unlocked resource reservation.
    // This also serializes concurrent preparation before allocator mutation.
    let mut owner = PAGE_MAP.lock();
    if owner.is_some() {
        return Err("paging already prepared");
    }
    let (window, built) = {
        let fa = &mut FRAME_ALLOC.lock();
        dbg("DBG: frame lock acquired\n");
        let built = if fa.init(entries, bootinfo_addr, bump_start, bump_end) {
            dbg("DBG: frame init done\n");
            paging::build_identity_map_with_backing_in_place(
                fa,
                window,
                &mut tables,
                &mut boot_pins,
                &mut payload_bitmap,
            )
            .ok_or("frame exhaustion during page table build")
        } else {
            Err("frame allocator initialization refused")
        };
        (window, built)
    }; // frame lock released before table backing destruction
    let pm = match built {
        Ok(pm) => pm,
        Err(error) => {
            drop(owner);
            return Err(error);
        }
    };
    dbg("DBG: page tables built\n");

    // Validation streams required regions and reports only the first failure.
    let missing = paging::first_missing_mapping(&pm, required_region_iter(entries, bootinfo_addr));
    if missing.is_none() {
        *owner = Some(pm);
        Ok(window)
    } else {
        {
            let fa = &mut FRAME_ALLOC.lock();
            pm.release_unpublished_frames(fa);
        } // unlock before PageMap's Vec backing or diagnostics are dropped
        drop(owner);
        Err(missing.unwrap())
    }
}

/// Enable paging (CR3 + CR0.PG). Only called after validation and IDT load.
pub fn enable_paging() {
    let owner = PAGE_MAP.lock();
    if let Some(pm) = owner.as_ref() {
        unsafe {
            paging::enable_paging(pm);
        }
        PAGING_ENABLED.store(true, Ordering::Release);
    }
}

pub fn paging_enabled() -> bool {
    PAGING_ENABLED.load(Ordering::Acquire)
}

pub fn page_directory() -> Option<u64> {
    PAGE_MAP.lock().as_ref().map(|pm| pm.directory())
}

/// Owned diagnostic value, safe to retain across allocation and mapping growth.
/// This is an observation, not a lifetime pin or physical-frame authority.
#[derive(Debug, Clone, Copy)]
pub struct PageSnapshot {
    pub physical_frame: Option<u64>,
    pub permissions: Option<paging::PagePerms>,
    pub mapped_pages: usize,
}

pub fn page_snapshot(linear: u64) -> Option<PageSnapshot> {
    let owner = PAGE_MAP.lock();
    let pm = owner.as_ref()?;
    Some(PageSnapshot {
        physical_frame: pm.translate(linear),
        permissions: pm.permissions(linear),
        mapped_pages: pm.stats().mapped_frames,
    })
}

pub(crate) fn pinned_identity_span(start: u64, end: u64) -> bool {
    PAGE_MAP
        .lock()
        .as_ref()
        .is_some_and(|pm| pm.pinned_identity_span(start, end))
}

/// Present-entry count for the shell's `mem` command (copied, no lock held
/// while printing).
pub fn mapped_pages() -> usize {
    match PAGE_MAP.lock().as_ref() {
        Some(pm) => pm.stats().mapped_frames,
        None => 0,
    }
}

/// Map one heap growth page: claim the identity frame at the growth slot and
/// map it. Called from the heap growth path (heap -> map -> frame lock
/// — the frame allocator never re-enters the heap, so the lock order is
/// safe). Growth pages are identity-mapped (virtual == physical), which keeps
/// heap free-list pointers valid and page-table entry writes safe.
pub fn heap_grow_frame(slot: usize) -> Option<u64> {
    let mut owner = PAGE_MAP.lock();
    let pm = owner.as_mut()?;
    let fa = &mut FRAME_ALLOC.lock();
    let frame = fa.claim_growth_frame(slot as u64)?;
    if pm.map(fa, slot as u64, frame, &paging::KERNEL_PERMS) {
        Some(frame)
    } else {
        // Growth-aware free restores reserved ownership, never ordinary free
        // capacity. Keep the pre-existing PTE untouched on a map rejection.
        fa.free(frame);
        None
    }
}

/// Host-only fixture: safely replace a mapped growth page with a distinct
/// acquired payload, so a later exact growth claim meets a real PTE conflict.
/// No production mapping/unmapping API is exposed by this test setup.
#[cfg(test)]
pub(crate) fn replace_growth_with_test_conflict(slot: usize) -> Option<u64> {
    let mut owner = PAGE_MAP.lock();
    let pm = owner.as_mut()?;
    let fa = &mut FRAME_ALLOC.lock();
    if !pm.unmap(fa, slot as u64) || !fa.free(slot as u64) {
        return None;
    }
    let payload = fa.allocate()?;
    if pm.map(fa, slot as u64, payload, &paging::KERNEL_PERMS) {
        Some(payload)
    } else {
        fa.free(payload);
        None
    }
}
