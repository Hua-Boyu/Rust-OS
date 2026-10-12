//! Physical frame allocator: static bitmaps over 4 KiB frames.
//!
//! Design:
//! - `free` bitmap: set = frame currently free. `ever` bitmap: set = frame
//!   was handed out at least once (lets us classify double frees vs freeing a
//!   reserved frame). `covered`/`ncov` track mmap coverage so overlapping
//!   ranges are counted once.
//! - All bitmaps are fixed-size static arrays: init must not allocate,
//!   because frame allocation is what the global allocator would run on.
//! - Only frames inside validated usable multiboot ranges (type 1) are ever
//!   marked free. Reserved regions (kernel image, boot stack, multiboot
//!   structures, bump-allocator segment, VGA framebuffer) can never be
//!   handed out.
//! - Exhaustion returns None; no wraparound, no panic.

use crate::memory::dbg;
use crate::memory::paging;
use crate::multiboot::MmapEntry;

pub const FRAME_SIZE: usize = 4096;

/// Managed address window. The kernel is 32-bit; frames above this are not
/// managed (documented limitation). 256 MiB = 65536 frames = 8 KiB per
/// bitmap, comfortably static.
pub const MAX_FRAME_ADDR: u64 = 256 * 1024 * 1024;
pub const MAX_FRAMES: usize = (MAX_FRAME_ADDR / FRAME_SIZE as u64) as usize;

// Always-reserved regardless of mmap type:
// - VGA framebuffer 0xB8000..0xBC000 (the kernel writes text directly here).
// - The kernel image (KERNEL_START..KERNEL_END from linker.ld), which also
//   covers the 16 KiB boot stack in .bss.
// - The multiboot info struct + memory map (bootloader-held).
// - The bump allocator's segment (passed to init).
const VGA_START: u64 = 0xB8000;
const VGA_END: u64 = 0xBC000;

#[cfg(not(test))]
unsafe extern "C" {
    static KERNEL_START: u32;
    static KERNEL_END: u32;
}

#[cfg(test)]
static KERNEL_START: u32 = 0;
#[cfg(test)]
static KERNEL_END: u32 = 0;

pub fn kernel_bounds() -> (u64, u64) {
    #[cfg(not(test))]
    unsafe {
        return (
            &KERNEL_START as *const u32 as u64,
            &KERNEL_END as *const u32 as u64,
        );
    }
    #[allow(unreachable_code)]
    (0, 4096)
}

#[derive(Debug, Clone, Copy)]
pub struct FrameStats {
    pub total_frames: usize,     // frames inside usable mmap ranges (deduped)
    pub reserved_frames: usize,  // frames reserved by mmap type or policy
    pub free_frames: usize,      // currently free
    pub allocated_frames: usize, // currently handed out
    pub double_frees: usize,     // rejected: freeing an already-free frame
    pub invalid_frees: usize,    // rejected: freeing a reserved frame
    pub bitmap_frames: usize,    // frames the bitmaps themselves occupy
}

pub struct FrameAllocator {
    free: [u8; MAX_FRAMES / 8],
    ever: [u8; MAX_FRAMES / 8],
    covered: [u8; MAX_FRAMES / 8],
    ncov: [u8; MAX_FRAMES / 8],
    stats: FrameStats,
    initialized: bool,
}

fn bit(bmap: &[u8], frame: usize) -> bool {
    bmap[frame / 8] & (1 << (frame % 8)) != 0
}

fn set_bit(bmap: &mut [u8], frame: usize, val: bool) {
    let byte = &mut bmap[frame / 8];
    let mask = 1 << (frame % 8);
    if val {
        *byte |= mask;
    } else {
        *byte &= !mask;
    }
}

impl FrameAllocator {
    pub const fn new() -> Self {
        Self {
            free: [0; MAX_FRAMES / 8],
            ever: [0; MAX_FRAMES / 8],
            covered: [0; MAX_FRAMES / 8],
            ncov: [0; MAX_FRAMES / 8],
            stats: FrameStats {
                total_frames: 0,
                reserved_frames: 0,
                free_frames: 0,
                allocated_frames: 0,
                double_frees: 0,
                invalid_frees: 0,
                bitmap_frames: MAX_FRAMES / 8 * 4 / FRAME_SIZE,
            },
            initialized: false,
        }
    }

    pub fn frame_of(addr: u64) -> Option<usize> {
        if addr >= MAX_FRAME_ADDR {
            return None;
        }
        Some((addr / FRAME_SIZE as u64) as usize)
    }

    /// Initialize from parsed mmap entries. Allocation-free.
    /// `bootinfo_addr` is the address of the multiboot info struct;
    /// `bump_start`/`bump_end` are the bump allocator's segment bounds.
    pub fn init(
        &mut self,
        entries: &[MmapEntry],
        bootinfo_addr: u64,
        bump_start: u64,
        bump_end: u64,
    ) {
        dbg("DBG: init entered\n");
        self.free.fill(0);
        self.ever.fill(0);
        self.covered.fill(0);
        self.ncov.fill(0);
        self.stats = FrameStats {
            total_frames: 0,
            reserved_frames: 0,
            free_frames: 0,
            allocated_frames: 0,
            double_frees: 0,
            invalid_frees: 0,
            bitmap_frames: MAX_FRAMES / 8 * 4 / FRAME_SIZE,
        };

        // Pass 1: mark frames covered by usable ranges (deduped).
        for &e in entries {
            if e.type_ != 1 || e.length == 0 {
                continue;
            }
            let Some(end) = e.base_addr.checked_add(e.length) else {
                continue;
            };
            // Only complete frames inside a usable range are allocatable.
            let first = e
                .base_addr
                .div_ceil(FRAME_SIZE as u64)
                .min(MAX_FRAMES as u64) as usize;
            let last = (end.min(MAX_FRAME_ADDR) / FRAME_SIZE as u64) as usize;
            for f in first..last {
                set_bit(&mut self.covered, f, true);
            }
        }

        // Pass 2: classify every covered frame.
        for f in 0..MAX_FRAMES {
            if !bit(&self.covered, f) {
                continue;
            }
            self.stats.total_frames += 1;
            let fa = (f as u64) * FRAME_SIZE as u64;
            let fe = fa + FRAME_SIZE as u64;
            let (kstart, kend) = kernel_bounds();
            // Frame 0 is reserved as the null page: page tables must never be
            // built there, and null dereferences must fault instead of
            // silently reading a page table.
            let null_page = f == 0;
            let kernel_overlap = fa < kend && fe > kstart;
            let vga_overlap = fa < VGA_END && fe > VGA_START;
            let bootinfo_overlap = fa < (bootinfo_addr + FRAME_SIZE as u64) && fe > bootinfo_addr;
            let bump_overlap = fa < bump_end && fe > bump_start;
            // Growth-window frames are reserved for the heap: they are mapped
            // one page at a time on demand, and page tables must never live
            // there (entry writes assume identity mapping).
            let growth_window = fa >= paging::GROWTH_START as u64 && fa < paging::GROWTH_END as u64;
            if null_page
                || kernel_overlap
                || vga_overlap
                || bootinfo_overlap
                || bump_overlap
                || growth_window
            {
                self.stats.reserved_frames += 1;
            } else {
                set_bit(&mut self.free, f, true);
                self.stats.free_frames += 1;
            }
        }

        // Pass 3: non-usable entries (ACPI/Reserved/MMIO) inside the window,
        // deduped against usable coverage.
        for &e in entries {
            if e.type_ == 1 || e.length == 0 {
                continue;
            }
            let Some(first) = Self::frame_of(e.base_addr) else {
                continue;
            };
            let last =
                Self::frame_of(e.base_addr.saturating_add(e.length - 1)).unwrap_or(MAX_FRAMES - 1);
            for f in first..=last {
                // Reserved/ACPI/MMIO ranges take precedence over usable
                // ranges, including when only one byte overlaps a frame.
                if bit(&self.free, f) {
                    set_bit(&mut self.free, f, false);
                    self.stats.free_frames -= 1;
                    self.stats.reserved_frames += 1;
                }
                if !bit(&self.covered, f) && !bit(&self.ncov, f) {
                    set_bit(&mut self.ncov, f, true);
                    self.stats.reserved_frames += 1;
                }
            }
        }

        self.initialized = true;
        dbg("DBG: frame init passes done\n");
    }

    /// Allocate one physical frame. None on exhaustion or before init.
    pub fn allocate(&mut self) -> Option<u64> {
        if !self.initialized {
            return None;
        }
        for frame in 0..MAX_FRAMES {
            if bit(&self.free, frame) {
                set_bit(&mut self.free, frame, false);
                set_bit(&mut self.ever, frame, true);
                self.stats.free_frames -= 1;
                self.stats.allocated_frames += 1;
                return Some((frame as u64) * FRAME_SIZE as u64);
            }
        }
        None
    }

    /// Free a previously allocated frame. Returns false (and counts the
    /// event) for double frees and frees of reserved frames.
    pub fn free(&mut self, addr: u64) -> bool {
        if !self.initialized {
            return false;
        }
        if addr % FRAME_SIZE as u64 != 0 {
            self.stats.invalid_frees += 1;
            return false;
        }
        let Some(frame) = Self::frame_of(addr) else {
            self.stats.invalid_frees += 1;
            return false;
        };
        if !bit(&self.covered, frame) || !bit(&self.ever, frame) {
            // A frame is releasable only if this allocator handed it out.
            // Usable-map coverage alone also includes our reserved frames.
            self.stats.invalid_frees += 1;
            return false;
        }
        if bit(&self.free, frame) {
            if bit(&self.ever, frame) {
                self.stats.double_frees += 1;
            } else {
                self.stats.invalid_frees += 1;
            }
            return false;
        }
        set_bit(&mut self.free, frame, true);
        self.stats.free_frames += 1;
        self.stats.allocated_frames -= 1;
        true
    }

    /// Claim a reserved growth-window frame for heap growth. Only frames
    /// inside the growth window can be claimed; they are accounted as
    /// allocated so stats stay consistent. None if already claimed or the
    /// frame is not covered by a usable range.
    pub fn claim_growth_frame(&mut self, addr: u64) -> Option<u64> {
        if !self.initialized {
            return None;
        }
        if addr % FRAME_SIZE as u64 != 0
            || addr < paging::GROWTH_START as u64
            || addr >= paging::GROWTH_END as u64
        {
            return None;
        }
        let frame = Self::frame_of(addr)?;
        if !bit(&self.covered, frame) || bit(&self.ever, frame) {
            return None;
        }
        set_bit(&mut self.ever, frame, true);
        // The frame was reserved for the heap; claiming it converts reserved
        // to allocated so the accounting stays consistent.
        self.stats.reserved_frames -= 1;
        self.stats.allocated_frames += 1;
        Some(addr)
    }

    pub fn is_free(&self, addr: u64) -> bool {
        match Self::frame_of(addr) {
            Some(f) => bit(&self.free, f),
            None => false,
        }
    }

    pub fn stats(&self) -> &FrameStats {
        &self.stats
    }

    pub fn is_initialized(&self) -> bool {
        self.initialized
    }
}
