//! Minimal 32-bit x86 paging: one page directory, 4 KiB page tables,
//! identity map over the managed frame window.
//!
//! Design:
//! - Page directory and page tables are built from frames handed out by the
//!   physical frame allocator, so they can never land on reserved memory.
//! - Identity mapping covers every frame in the managed window (kernel image,
//!   boot stack, VGA framebuffer, multiboot structures, usable RAM). Paging
//!   is enabled only after every required region is validated as present.
//! - Entry flags: present + writable. Ring 0 only, no NX, no user pages.
//! - CR3 is loaded, then CR0.PG is set. The page-fault handler decodes the
//!   error code, records CR2, and halts safely (faults are fatal here).

use crate::memory::frame::FrameAllocator;
use crate::utils::bits::CanManipulateBits;
extern crate alloc;
use alloc::vec;
use alloc::vec::Vec;

pub const PAGE_SIZE: usize = 4096;
pub const ENTRY_PRESENT: u32 = 1 << 0;
pub const ENTRY_WRITABLE: u32 = 1 << 1;

pub const PAGE_DIR_ENTRIES: usize = 1024;
pub const PAGE_TABLE_ENTRIES: usize = 1024;

pub fn page_dir_index(linear: u64) -> usize {
    ((linear >> 22) & 0x3FF) as usize
}

pub fn page_table_index(linear: u64) -> usize {
    ((linear >> 12) & 0x3FF) as usize
}

pub fn entry_value(frame: u64) -> u32 {
    (frame as u32) | ENTRY_PRESENT | ENTRY_WRITABLE
}

#[derive(Debug, Clone, Copy)]
pub struct PageFaultInfo {
    /// Decoded error-code bits: present, write, user.
    pub present: bool,
    pub write: bool,
    pub user: bool,
    /// Faulting linear address (CR2).
    pub cr2: u32,
}

pub fn decode_error_code(code: u32) -> PageFaultInfo {
    PageFaultInfo {
        present: code.get_bits(0, 1) == 1,
        write: code.get_bits(1, 1) == 1,
        user: code.get_bits(2, 1) == 1,
        cr2: 0,
    }
}

#[derive(Debug)]
pub struct PagingStats {
    pub page_tables: usize,
    pub mapped_frames: usize, // frames with a present entry
    pub enabled: bool,
}

pub struct PageMap {
    directory: u64,
    tables: Vec<u64>,
    stats: PagingStats,
}

impl PageMap {
    /// Entry for a linear address, if its page table exists.
    pub fn entry(&self, linear: u64) -> Option<u32> {
        if linear >= (1u64 << 32) {
            return None;
        }
        let base = self.tables[page_dir_index(linear)];
        if base == 0 {
            return None;
        }
        Some(read_entry(base, page_table_index(linear)))
    }

    pub fn is_mapped(&self, linear: u64) -> bool {
        match self.entry(linear) {
            Some(e) => e & ENTRY_PRESENT != 0,
            None => false,
        }
    }

    pub fn directory(&self) -> u64 {
        self.directory
    }

    pub fn stats(&self) -> &PagingStats {
        &self.stats
    }
}

/// Read one entry from a page table. In kernel builds this reads the physical
/// page directly; in host tests it reads the mirror contents recorded during
/// build_identity_map.
fn read_entry(table_base: u64, index: usize) -> u32 {
    #[cfg(test)]
    {
        return MIRROR.with(|m| {
            let m = m.borrow();
            m.get(&table_base).map(|t| t[index]).unwrap_or(0)
        });
    }
    #[allow(unreachable_code)]
    unsafe {
        core::ptr::read((table_base as *const u32).add(index))
    }
}

#[cfg(test)]
thread_local! {
    static MIRROR: core::cell::RefCell<std::collections::HashMap<u64, Vec<u32>>> =
        core::cell::RefCell::new(std::collections::HashMap::new());
}

/// Build an identity map over [0, window_end) using frames from `fa`.
/// Returns None if the allocator is exhausted mid-build.
pub fn build_identity_map(fa: &mut FrameAllocator, window_end: u64) -> Option<PageMap> {
    if window_end == 0 || window_end > (1u64 << 32) {
        return None;
    }
    let directory = fa.allocate()?;
    zero_table(directory);
    let mut tables = vec![0u64; PAGE_DIR_ENTRIES];
    let mut stats = PagingStats {
        page_tables: 0,
        mapped_frames: 0,
        enabled: false,
    };

    for dir in 0..PAGE_DIR_ENTRIES {
        let region_start = (dir as u64) << 22;
        if region_start >= window_end {
            break;
        }
        let table = match fa.allocate() {
            Some(table) => table,
            None => {
                for &frame in &tables {
                    if frame != 0 {
                        fa.free(frame);
                    }
                }
                fa.free(directory);
                return None;
            }
        };
        zero_table(table);
        tables[dir] = table;
        stats.page_tables += 1;

        for idx in 0..PAGE_TABLE_ENTRIES {
            let frame = region_start + (idx as u64) * PAGE_SIZE as u64;
            if frame >= window_end {
                break;
            }
            // A reserved physical null frame is not enough: leave its
            // virtual mapping absent too, so null accesses fault.
            if frame == 0 {
                continue;
            }
            let entry = entry_value(frame);
            #[cfg(not(test))]
            unsafe {
                core::ptr::write((table as *mut u32).add(idx), entry);
            }
            #[cfg(test)]
            MIRROR.with(|m| {
                m.borrow_mut()
                    .entry(table)
                    .or_insert_with(|| vec![0; PAGE_TABLE_ENTRIES])[idx] = entry;
            });
            stats.mapped_frames += 1;
        }

        let dir_entry = entry_value(table);
        #[cfg(not(test))]
        unsafe {
            core::ptr::write((directory as *mut u32).add(dir), dir_entry);
        }
        #[cfg(test)]
        MIRROR.with(|m| {
            m.borrow_mut()
                .entry(directory)
                .or_insert_with(|| vec![0; PAGE_DIR_ENTRIES])[dir] = dir_entry;
        });
    }

    Some(PageMap {
        directory,
        tables,
        stats,
    })
}

fn zero_table(frame: u64) {
    #[cfg(not(test))]
    unsafe {
        core::ptr::write_bytes(frame as *mut u8, 0, PAGE_SIZE);
    }
    #[cfg(test)]
    MIRROR.with(|m| {
        m.borrow_mut().insert(frame, vec![0; PAGE_TABLE_ENTRIES]);
    });
}

/// Validate that every required region has present entries before enabling
/// paging. Returns the names of missing regions (empty = safe to enable).
pub fn validate_mapping(
    page_map: &PageMap,
    required: &[(u64, u64, &'static str)],
) -> Vec<&'static str> {
    let mut missing = Vec::new();
    for &(start, end, name) in required {
        if start >= end {
            continue;
        }
        let mut addr = start & !(PAGE_SIZE as u64 - 1);
        while addr < end {
            if !page_map.is_mapped(addr) {
                missing.push(name);
                break;
            }
            addr += PAGE_SIZE as u64;
        }
    }
    missing
}

#[cfg(not(test))]
pub fn enable_paging(page_map: &PageMap) {
    unsafe {
        core::arch::asm!(
            "mov {cr3}, %cr3",
            cr3 = in(reg) page_map.directory() as u32,
            options(att_syntax)
        );
        // Set CR0.PG (bit 31): read CR0, OR in PG, write back.
        let mut cr0: u32;
        core::arch::asm!("mov %cr0, {out}", out = out(reg) cr0, options(att_syntax));
        cr0 |= 1 << 31;
        core::arch::asm!("mov {v}, %cr0", v = in(reg) cr0, options(att_syntax));
    }
}

#[cfg(test)]
pub fn enable_paging(_page_map: &PageMap) {}

pub fn paging_enabled() -> bool {
    #[cfg(test)]
    return false;
    #[allow(unreachable_code)]
    {
        let mut cr0: u32;
        unsafe {
            core::arch::asm!("mov %cr0, {out}", out = out(reg) cr0, options(att_syntax));
        }
        cr0 & (1 << 31) != 0
    }
}

pub fn read_cr2() -> u32 {
    #[cfg(test)]
    return 0;
    #[allow(unreachable_code)]
    {
        let mut cr2: u32;
        unsafe {
            core::arch::asm!("mov %cr2, {out}", out = out(reg) cr2, options(att_syntax));
        }
        cr2
    }
}
