//! Physical memory subsystem: frame allocator + paging.
//!
//! Init order in kernel_main: bump allocator (so Vec works) -> frame
//! allocator init from the multiboot mmap -> page tables built from managed
//! frames -> mapping validated -> paging enabled (after the IDT is loaded, so
//! any fault is handled by the vector-14 handler).

pub mod frame;
pub mod paging;

extern crate alloc;
use alloc::vec::Vec;

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

static mut PAGE_MAP: Option<paging::PageMap> = None;
static mut PAGING_ENABLED: bool = false;

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
pub fn required_regions(
    entries: &[MmapEntry],
    bootinfo_addr: u64,
) -> Vec<(u64, u64, &'static str)> {
    let mut regions = Vec::new();

    #[cfg(not(test))]
    unsafe extern "C" {
        static KERNEL_START: u32;
        static KERNEL_END: u32;
    }
    #[cfg(not(test))]
    unsafe {
        regions.push((
            &KERNEL_START as *const u32 as u64,
            &KERNEL_END as *const u32 as u64,
            "kernel image (incl. boot stack)",
        ));
    }
    #[cfg(test)]
    regions.push((4096, 8192, "kernel image (test dummy)"));

    regions.push((0xB8000, 0xBC000, "VGA framebuffer"));
    regions.push((bootinfo_addr, bootinfo_addr + 4096, "multiboot info struct"));

    // Every usable mmap range inside the window must be mapped (the bump
    // allocator and the page tables live there).
    for e in entries {
        if e.type_ == 1 && e.base_addr < (1u64 << 32) {
            if let Some(end) = e.base_addr.checked_add(e.length) {
                regions.push((
                    e.base_addr.max(paging::PAGE_SIZE as u64),
                    end.min(1u64 << 32),
                    "usable mmap range",
                ));
            }
        }
    }

    regions
}

/// Initialize the frame allocator and build + validate the identity map.
/// Does NOT enable paging — call enable_paging() after the IDT is loaded.
/// Returns Ok(window_end) or the names of missing regions.
pub fn prepare(
    entries: &[MmapEntry],
    bootinfo_addr: u64,
    bump_start: u64,
    bump_end: u64,
) -> Result<u64, Vec<&'static str>> {
    dbg("DBG: frame init start\n");
    let fa = &mut FRAME_ALLOC.lock();
    dbg("DBG: frame lock acquired\n");
    fa.init(entries, bootinfo_addr, bump_start, bump_end);
    dbg("DBG: frame init done\n");

    let window = managed_window_end(entries);
    let pm = match paging::build_identity_map(fa, window) {
        Some(pm) => pm,
        None => return Err(alloc::vec!["frame exhaustion during page table build"]),
    };
    dbg("DBG: page tables built\n");

    let missing = paging::validate_mapping(&pm, &required_regions(entries, bootinfo_addr));
    if missing.is_empty() {
        unsafe {
            PAGE_MAP = Some(pm);
        }
        Ok(window)
    } else {
        Err(missing)
    }
}

/// Enable paging (CR3 + CR0.PG). Only called after validation and IDT load.
pub fn enable_paging() {
    unsafe {
        if let Some(pm) = (&raw const PAGE_MAP).as_ref().and_then(|o| o.as_ref()) {
            paging::enable_paging(pm);
            PAGING_ENABLED = true;
        }
    }
}

pub fn paging_enabled() -> bool {
    unsafe { PAGING_ENABLED }
}

pub fn page_directory() -> Option<u64> {
    unsafe {
        (&raw const PAGE_MAP)
            .as_ref()
            .and_then(|o| o.as_ref())
            .map(|pm| pm.directory())
    }
}
