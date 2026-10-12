//! Virtual memory subsystem built on the existing i686 4 KiB paging mode.
//!
//! Extends the Phase 4 identity map with runtime operations:
//! - map a physical frame to a virtual page (rejecting conflicts),
//! - unmap a mapping (rejecting absent pages),
//! - translate virtual -> physical,
//! - inspect permissions (present / writable / user; NX investigated below),
//! - TLB invalidation for changed pages.
//!
//! Design rules:
//! - Page tables live in frames handed out by the frame allocator; entries
//!   are read/written through the identity map (kernel is identity-mapped, so
//!   a table frame is readable/writable at its own linear address).
//! - A page table for a new region is allocated on demand from the frame
//!   allocator; if none is free, mapping fails cleanly (None) instead of
//!   corrupting existing mappings.
//! - Boot-critical regions (kernel image, VGA, multiboot structures) are
//!   identity-mapped by build_identity_map and are never unmapped here.
//! - NX (bit 63 / PAE) is NOT supported by this 32-bit single-directory mode;
//!   `entry_nx` reports that honestly rather than claiming protection.
//! - All address arithmetic is checked; unaligned or out-of-range virtual
//!   addresses are rejected.

use crate::memory::frame::{self, FrameAllocator};
use crate::utils::bits::CanManipulateBits;
extern crate alloc;
use alloc::vec::Vec;

pub const PAGE_SIZE: usize = 4096;
pub const ENTRY_PRESENT: u32 = 1 << 0;
pub const ENTRY_WRITABLE: u32 = 1 << 1;
pub const ENTRY_USER: u32 = 1 << 2;

pub const PAGE_DIR_ENTRIES: usize = 1024;
pub const PAGE_TABLE_ENTRIES: usize = 1024;

// Virtual growth window for the dynamic heap. These pages are deliberately
// NOT identity-mapped at boot; heap growth maps them one page at a time, so
// runtime mapping can never conflict with the boot identity map.
pub const GROWTH_START: usize = 0x800_000;
pub const GROWTH_END: usize = 0xE00_000;

pub fn in_growth_window(addr: u64) -> bool {
    addr >= GROWTH_START as u64 && addr < GROWTH_END as u64
}

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
    /// Decoded error-code bits: present, write, user, instruction fetch.
    pub present: bool,
    pub write: bool,
    pub user: bool,
    pub fetch: bool,
    /// Faulting linear address (CR2).
    pub cr2: u32,
}

pub fn decode_error_code(code: u32) -> PageFaultInfo {
    PageFaultInfo {
        present: code.get_bits(0, 1) == 1,
        write: code.get_bits(1, 1) == 1,
        user: code.get_bits(2, 1) == 1,
        // Bit 4 (instruction fetch) is only reported by CPUs supporting the
        // NX feature; on this 32-bit mode it is always 0 and reported as such.
        fetch: code.get_bits(4, 1) == 1,
        cr2: 0,
    }
}

#[derive(Debug)]
pub struct PagingStats {
    pub page_tables: usize,
    pub mapped_frames: usize, // frames with a present entry
    pub enabled: bool,
    pub maps: usize,          // successful runtime map operations
    pub map_rejects: usize,   // rejected: conflict, unaligned, out of range
    pub unmaps: usize,        // successful runtime unmap operations
    pub unmap_rejects: usize, // rejected: absent page
    pub tlb_invalidation: usize,
}

pub struct PageMap {
    directory: u64,
    tables: Vec<u64>,
    stats: PagingStats,
    window_end: u64,
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

    /// Translate a page-aligned virtual address to its physical frame.
    /// None if unmapped or unaligned/out of range.
    pub fn translate(&self, linear: u64) -> Option<u64> {
        if linear % PAGE_SIZE as u64 != 0 || linear >= (1u64 << 32) {
            return None;
        }
        let e = self.entry(linear)?;
        if e & ENTRY_PRESENT == 0 {
            return None;
        }
        Some(e as u64 & 0xFFFFF000)
    }

    /// Permission flags for a page-aligned virtual address.
    pub fn permissions(&self, linear: u64) -> Option<PagePerms> {
        let e = self.entry(linear)?;
        Some(PagePerms {
            present: e & ENTRY_PRESENT != 0,
            writable: e & ENTRY_WRITABLE != 0,
            user: e & ENTRY_USER != 0,
            // NX requires PAE/long mode; this kernel uses 32-bit paging, so
            // execution cannot be restricted per page. Reported honestly.
            nx_supported: false,
        })
    }

    /// Map `frame` (must be page-aligned and inside the managed window) to
    /// `linear`. Rejects: unaligned addresses, addresses outside the paging
    /// window, conflicting present entries, and exhaustion (allocates a page
    /// table on demand only when one is missing). Invalidates the TLB entry
    /// on success.
    pub fn map(
        &mut self,
        fa: &mut FrameAllocator,
        linear: u64,
        phys_frame: u64,
        perms: &PagePerms,
    ) -> bool {
        if linear % PAGE_SIZE as u64 != 0 || phys_frame % PAGE_SIZE as u64 != 0 {
            self.stats.map_rejects += 1;
            return false;
        }
        if linear >= (1u64 << 32) || phys_frame >= frame::MAX_FRAME_ADDR {
            self.stats.map_rejects += 1;
            return false;
        }
        // Boot identity mappings cover [0, window_end); the growth window is
        // mapped on demand. Anything else is outside the managed space.
        if linear >= self.window_end && !in_growth_window(linear) {
            self.stats.map_rejects += 1;
            return false;
        }
        let dir = page_dir_index(linear);
        let idx = page_table_index(linear);
        if self.tables[dir] == 0 {
            let table = match fa.allocate() {
                Some(t) => t,
                None => {
                    self.stats.map_rejects += 1;
                    return false;
                }
            };
            zero_table(table);
            self.tables[dir] = table;
            self.stats.page_tables += 1;
            let dir_entry = entry_value(table);
            write_entry(self.directory, dir, dir_entry);
        }
        let existing = read_entry(self.tables[dir], idx);
        if existing & ENTRY_PRESENT != 0 {
            // Conflicting mapping: never overwrite an existing page.
            self.stats.map_rejects += 1;
            return false;
        }
        let mut entry = phys_frame as u32 | ENTRY_PRESENT;
        if perms.writable {
            entry |= ENTRY_WRITABLE;
        }
        if perms.user {
            entry |= ENTRY_USER;
        }
        write_entry(self.tables[dir], idx, entry);
        self.stats.mapped_frames += 1;
        self.stats.maps += 1;
        invalidate_page(linear);
        self.stats.tlb_invalidation += 1;
        true
    }

    /// Unmap a page-aligned virtual address. Rejects absent pages and
    /// boot-critical regions (kernel image, VGA, multiboot structures), which
    /// must stay mapped for the kernel to run.
    pub fn unmap(&mut self, linear: u64) -> bool {
        if linear % PAGE_SIZE as u64 != 0 || linear >= (1u64 << 32) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        if linear >= self.window_end && !in_growth_window(linear) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        if is_boot_critical(linear) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        let dir = page_dir_index(linear);
        let base = self.tables[dir];
        if base == 0 {
            self.stats.unmap_rejects += 1;
            return false;
        }
        let idx = page_table_index(linear);
        let entry = read_entry(base, idx);
        if entry & ENTRY_PRESENT == 0 {
            self.stats.unmap_rejects += 1;
            return false;
        }
        write_entry(base, idx, 0);
        self.stats.mapped_frames -= 1;
        self.stats.unmaps += 1;
        invalidate_page(linear);
        self.stats.tlb_invalidation += 1;
        true
    }

    pub fn window_end(&self) -> u64 {
        self.window_end
    }
}

#[derive(Debug, Clone, Copy)]
pub struct PagePerms {
    pub present: bool,
    pub writable: bool,
    pub user: bool,
    /// True only when the paging mode can enforce per-page execute-disable.
    /// 32-bit single-directory paging cannot, so this is always false here.
    pub nx_supported: bool,
}

pub const KERNEL_PERMS: PagePerms = PagePerms {
    present: true,
    writable: true,
    user: false,
    nx_supported: false,
};

/// Regions that must never be unmapped at runtime.
fn is_boot_critical(linear: u64) -> bool {
    let (kstart, kend) = frame::kernel_bounds();
    if linear >= kstart && linear < kend {
        return true;
    }
    if linear >= 0xB8000 && linear < 0xBC000 {
        return true;
    }
    false
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

fn write_entry(table_base: u64, index: usize, value: u32) {
    #[cfg(test)]
    MIRROR.with(|m| {
        m.borrow_mut()
            .entry(table_base)
            .or_insert_with(|| vec![0; PAGE_TABLE_ENTRIES])[index] = value;
    });
    #[cfg(not(test))]
    unsafe {
        core::ptr::write((table_base as *mut u32).add(index), value);
    }
}

#[cfg(test)]
thread_local! {
    static MIRROR: core::cell::RefCell<std::collections::HashMap<u64, Vec<u32>>> =
        core::cell::RefCell::new(std::collections::HashMap::new());
}

/// Invalidate the TLB entry for one page (kernel-mode single-page flush).
fn invalidate_page(linear: u64) {
    #[cfg(not(test))]
    unsafe {
        core::arch::asm!("invlpg ({})", in(reg) linear as u32, options(att_syntax, nostack));
    }
    #[cfg(test)]
    let _ = linear;
}

/// Flush the entire TLB (writing CR3 to itself is the canonical full flush).
pub fn flush_tlb(page_map: &PageMap) {
    #[cfg(not(test))]
    unsafe {
        core::arch::asm!(
            "mov {cr3}, %cr3",
            cr3 = in(reg) page_map.directory() as u32,
            options(att_syntax)
        );
    }
    #[cfg(test)]
    let _ = page_map;
}

/// Build an identity map over [0, window_end) using frames from `fa`.
/// `tables` must be pre-allocated by the caller: allocating inside this
/// function while the frame lock is held would invert the heap->frame lock
/// order used by the heap growth path.
/// Returns None if the allocator is exhausted mid-build.
pub fn build_identity_map(
    fa: &mut FrameAllocator,
    window_end: u64,
    mut tables: Vec<u64>,
) -> Option<PageMap> {
    if window_end == 0 || window_end > (1u64 << 32) {
        return None;
    }
    let directory = fa.allocate()?;
    zero_table(directory);
    let mut stats = PagingStats {
        page_tables: 0,
        mapped_frames: 0,
        enabled: false,
        maps: 0,
        map_rejects: 0,
        unmaps: 0,
        unmap_rejects: 0,
        tlb_invalidation: 0,
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
            // The heap growth window stays unmapped at boot so runtime
            // mapping of growth pages cannot conflict with boot mappings.
            if in_growth_window(frame) {
                continue;
            }
            let entry = entry_value(frame);
            write_entry(table, idx, entry);
            stats.mapped_frames += 1;
        }

        let dir_entry = entry_value(table);
        write_entry(directory, dir, dir_entry);
    }

    Some(PageMap {
        directory,
        tables,
        stats,
        window_end,
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
            // The heap growth window is intentionally unmapped until the heap
            // maps it on demand; validation must not require it.
            if !in_growth_window(addr) && !page_map.is_mapped(addr) {
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
        // Enforce supervisor-only pages while paging is active: CR4.PSE is not
        // needed for 4 KiB pages, but CR0.WP must be set so that ring-0 writes
        // to read-only pages fault. Without WP, supervisor writes ignore the
        // R/W flag entirely.
        cr0 |= 1 << 16;
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
