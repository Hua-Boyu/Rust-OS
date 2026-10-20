//! Physical frame allocator: static bitmaps over 4 KiB frames.
//!
//! Design:
//! - `free` bitmap: set = frame currently free. `ever` bitmap: set = frame
//!   was handed out at least once (lets us classify double frees vs freeing a
//!   reserved frame). `covered` tracks complete usable frames; `ncov` is the
//!   authoritative competing-reservation denial bitmap, including overlapping
//!   firmware and boot spans. Growth's own reservation is not a denial.
//!   `growth_claimed` tracks live growth ownership separately from `ever`, so
//!   rollback restores growth-only capacity without losing double-free checks.
//! - All bitmaps are fixed-size static arrays: init must not allocate,
//!   because frame allocation is what the global allocator would run on.
//! - Only frames inside validated usable multiboot ranges (type 1) are ever
//!   marked free. Reserved regions (kernel image, boot stack, multiboot
//!   structures, bump-allocator segment, VGA framebuffer) can never be
//!   handed out.
//! - Exhaustion returns None; no wraparound, no panic.

use crate::memory::dbg;
use crate::memory::paging;
use crate::memory::paging::retained_owner::mutation_allowed;
use crate::multiboot::MmapEntry;
use core::sync::atomic::{AtomicU32, Ordering};

// Allocator addresses are movable, and reset must not reuse an old domain.
// Zero is never issued; exhaustion is permanent rather than wrapping to one.
static LAST_DOMAIN: AtomicU32 = AtomicU32::new(0);

fn issue_domain(last: &AtomicU32) -> Option<u32> {
    last.try_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
        value.checked_add(1)
    })
    .ok()
    .and_then(|previous| previous.checked_add(1))
}

#[cfg(test)]
#[path = "../../tests_kernel/src/b11_frame_tests.rs"]
mod b11_tests;

#[cfg(test)]
#[path = "generation_boundary_tests.rs"]
mod generation_boundary_tests;

pub const FRAME_SIZE: usize = 4096;

/// Managed address window. The kernel is 32-bit; frames above this are not
/// managed (documented limitation). 256 MiB = 65536 frames = 8 KiB per
/// bitmap, comfortably static.
pub const MAX_FRAME_ADDR: u64 = 256 * 1024 * 1024;
pub const MAX_FRAMES: usize = (MAX_FRAME_ADDR / FRAME_SIZE as u64) as usize;
const GROWTH_BITMAP_BYTES: usize =
    ((paging::GROWTH_END - paging::GROWTH_START) / FRAME_SIZE).div_ceil(8);
const BITMAP_FRAMES: usize = (MAX_FRAMES / 8 * 6 + GROWTH_BITMAP_BYTES).div_ceil(FRAME_SIZE);

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

/// A live ownership identity for one frame handed out by this allocator.
/// Move-only and non-copyable: fields are private and only the frame module
/// constructs it, so a copied numeric address cannot impersonate an owner.
/// `frame_addr()` is the accessor; the id/domain pair is the release proof.
pub struct FrameLease {
    addr: u64,
    id: u32,
    domain: u32,
}

impl FrameLease {
    pub fn frame_addr(&self) -> u64 {
        self.addr
    }

    /// Only negative host probes may duplicate authority; absent in production.
    #[cfg(test)]
    pub(super) fn duplicate_for_test(&self) -> Self {
        Self {
            addr: self.addr,
            id: self.id,
            domain: self.domain,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct FrameStats {
    pub total_frames: usize,     // frames inside usable mmap ranges (deduped)
    pub reserved_frames: usize,  // deduped mmap/policy spans, excluding live claims
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
    growth_claimed: [u8; GROWTH_BITMAP_BYTES],
    // Exclusive runtime payload references across all maps in this allocator.
    // Borrowed boot aliases are not pins; this is not generational authority.
    runtime_pins: [u8; MAX_FRAMES / 8],
    // Frames installed as paging structures (directory or tables entry) by a
    // PageMap of the current domain. Shadow metadata mirroring pm.tables;
    // set/clear discipline at install and release sites is the invariant.
    structure_pins: [u8; MAX_FRAMES / 8],
    // Current allocation identity per managed frame (0 = no live identity).
    // Stamped by allocate(), zeroed by every successful release path. This is
    // the generation-safe ownership ledger: a stale lease's id can never match
    // a reused frame's fresh identity.
    alloc_id: [u32; MAX_FRAMES],
    // Next identity to issue. Monotonic across domains (never reset by init),
    // so identities never wrap and never repeat; 0 is reserved for "no owner".
    next_id: u32,
    domain: u32,
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
            growth_claimed: [0; GROWTH_BITMAP_BYTES],
            runtime_pins: [0; MAX_FRAMES / 8],
            structure_pins: [0; MAX_FRAMES / 8],
            alloc_id: [0; MAX_FRAMES],
            next_id: 1,
            domain: 0,
            stats: FrameStats {
                total_frames: 0,
                reserved_frames: 0,
                free_frames: 0,
                allocated_frames: 0,
                double_frees: 0,
                invalid_frees: 0,
                bitmap_frames: BITMAP_FRAMES,
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
    /// A live allocator or exhausted domain issuer is refused without mutation.
    pub fn init(
        &mut self,
        entries: &[MmapEntry],
        bootinfo_addr: u64,
        bump_start: u64,
        bump_end: u64,
    ) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if self.stats.allocated_frames != 0 {
            return false;
        }
        let Some(domain) = issue_domain(&LAST_DOMAIN) else {
            return false;
        };
        dbg("DBG: init entered\n");
        self.free.fill(0);
        self.ever.fill(0);
        self.covered.fill(0);
        self.ncov.fill(0);
        self.growth_claimed.fill(0);
        self.runtime_pins.fill(0);
        self.structure_pins.fill(0);
        self.alloc_id.fill(0);
        self.stats = FrameStats {
            total_frames: 0,
            reserved_frames: 0,
            free_frames: 0,
            allocated_frames: 0,
            double_frees: 0,
            invalid_frees: 0,
            bitmap_frames: BITMAP_FRAMES,
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
            let bootinfo_overlap =
                fa < bootinfo_addr.saturating_add(FRAME_SIZE as u64) && fe > bootinfo_addr;
            let bump_overlap = bump_start < bump_end && fa < bump_end && fe > bump_start;
            // Growth-window frames are reserved for the heap: they are mapped
            // one page at a time on demand, and page tables must never live
            // there (entry writes assume identity mapping).
            let growth_window = fa >= paging::GROWTH_START as u64 && fa < paging::GROWTH_END as u64;
            let denied =
                null_page || kernel_overlap || vga_overlap || bootinfo_overlap || bump_overlap;
            set_bit(&mut self.ncov, f, denied);
            if denied || growth_window {
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
                    self.stats.reserved_frames += 1;
                }
                // Preserve the denial even for covered growth frames, which
                // were never in the general free pool in the first place.
                set_bit(&mut self.ncov, f, true);
            }
        }

        self.initialized = true;
        self.domain = domain;
        dbg("DBG: frame init passes done\n");
        true
    }

    /// Initialize with additional pinned boot/module/page-table byte spans.
    /// Spans are half-open; empty spans do nothing, any reversed span fails
    /// closed on an empty allocator. Live state is never erased, even for
    /// malformed reservations. No allocation occurs.
    pub fn init_with_reservations(
        &mut self,
        entries: &[MmapEntry],
        bootinfo_addr: u64,
        bump_start: u64,
        bump_end: u64,
        reservations: &[(u64, u64)],
    ) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if self.stats.allocated_frames != 0 {
            return false;
        }
        if reservations.iter().any(|&(start, end)| start > end) {
            self.initialized = false;
            self.domain = 0;
            return false;
        }
        if !self.init(entries, bootinfo_addr, bump_start, bump_end) {
            return false;
        }
        for &(start, end) in reservations {
            if start == end || start >= MAX_FRAME_ADDR {
                continue;
            }
            let first = (start / FRAME_SIZE as u64) as usize;
            let last = ((end - 1).min(MAX_FRAME_ADDR - 1) / FRAME_SIZE as u64) as usize;
            for f in first..=last {
                if bit(&self.free, f) {
                    set_bit(&mut self.free, f, false);
                    self.stats.free_frames -= 1;
                    self.stats.reserved_frames += 1;
                }
                if !bit(&self.covered, f) && !bit(&self.ncov, f) {
                    self.stats.reserved_frames += 1;
                }
                set_bit(&mut self.ncov, f, true);
            }
        }
        true
    }

    /// Issue the next allocation identity. Monotonic across domains and
    /// never reset by init; 0 is the permanent exhaustion sentinel, so
    /// identities never wrap and never silently repeat.
    fn issue_allocation_id(&mut self) -> Option<u32> {
        if !mutation_allowed() {
            return None;
        }
        let id = self.next_id;
        if id == 0 {
            return None;
        }
        self.next_id = id.checked_add(1).unwrap_or(0);
        Some(id)
    }

    /// Shared allocation core: find a free frame, clear availability, and
    /// stamp the ledger identity. Returns (addr, id). None on exhaustion or
    /// before init; a refused allocation mutates nothing.
    fn allocate_stamped(&mut self) -> Option<(u64, u32)> {
        if !mutation_allowed() {
            return None;
        }
        if !self.initialized {
            return None;
        }
        for frame in 0..MAX_FRAMES {
            if bit(&self.free, frame) {
                let Some(id) = self.issue_allocation_id() else {
                    return None;
                };
                set_bit(&mut self.free, frame, false);
                set_bit(&mut self.ever, frame, true);
                self.alloc_id[frame] = id;
                self.stats.free_frames -= 1;
                self.stats.allocated_frames += 1;
                return Some(((frame as u64) * FRAME_SIZE as u64, id));
            }
        }
        None
    }

    /// Raw numeric allocation (audited internal path): the returned address
    /// carries no ownership proof. Safe code allocates through
    /// `allocate_owned` and releases through `release_frame(lease)`.
    pub(crate) fn allocate(&mut self) -> Option<u64> {
        let Some((addr, _)) = self.allocate_stamped() else {
            return None;
        };
        Some(addr)
    }

    /// Safe public allocation: returns a move-only lease carrying the live
    /// ownership identity for the frame. None on exhaustion or before init.
    pub fn allocate_owned(&mut self) -> Option<FrameLease> {
        let Some((addr, id)) = self.allocate_stamped() else {
            return None;
        };
        Some(FrameLease {
            addr,
            id,
            domain: self.domain,
        })
    }

    /// Authenticate borrowed ordinary ownership against the live ledger.
    /// A retained Rust value alone is insufficient after audited raw release.
    /// Allocation-free and diagnostic-free; payload role/pins are checked by
    /// the mapping core under the same exclusive allocator borrow.
    pub(super) fn owns_live_lease(&self, lease: &FrameLease) -> bool {
        if !self.initialized
            || lease.domain != self.domain
            || lease.id == 0
            || paging::in_growth_window(lease.addr)
            || !self.is_live_allocation(lease.addr)
        {
            return false;
        }
        let Some(frame) = Self::frame_of(lease.addr) else {
            return false;
        };
        self.alloc_id[frame] == lease.id
    }

    /// Shared release core: validate availability, restore accounting, and
    /// clear the ledger identity. Growth claims return to the growth-only
    /// reservation, never the general free pool. Returns false (and counts
    /// the event) for double frees and frees of frames this allocator never
    /// handed out. A refused release mutates only diagnostics.
    fn release_by_address(&mut self, addr: u64) -> bool {
        if !mutation_allowed() {
            return false;
        }
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
        if bit(&self.runtime_pins, frame) {
            self.stats.invalid_frees += 1;
            return false;
        }
        if bit(&self.structure_pins, frame) {
            self.stats.invalid_frees += 1;
            return false;
        }
        if !bit(&self.covered, frame) || !bit(&self.ever, frame) {
            // A frame is releasable only if this allocator handed it out.
            // Usable-map coverage alone also includes our reserved frames.
            self.stats.invalid_frees += 1;
            return false;
        }
        if addr >= paging::GROWTH_START as u64 && addr < paging::GROWTH_END as u64 {
            let index = (addr as usize - paging::GROWTH_START) / FRAME_SIZE;
            if !bit(&self.growth_claimed, index) {
                self.stats.double_frees += 1;
                return false;
            }
            set_bit(&mut self.growth_claimed, index, false);
            self.alloc_id[frame] = 0;
            self.stats.reserved_frames += 1;
            self.stats.allocated_frames -= 1;
            return true;
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
        self.alloc_id[frame] = 0;
        self.stats.free_frames += 1;
        self.stats.allocated_frames -= 1;
        true
    }

    /// Raw numeric release (audited internal path): the address carries no
    /// ownership proof. Safe code releases through `release_frame(lease)`.
    pub(crate) fn free(&mut self, addr: u64) -> bool {
        self.release_by_address(addr)
    }

    /// Safe public release: consumes the lease by value, so a second release
    /// of the same lease is a compile error; the ledger identity is the
    /// runtime proof. A stale lease for a reused frame is refused, and the
    /// current owner stays live. Refusals mutate only diagnostics.
    pub fn release_frame(&mut self, lease: FrameLease) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if !self.initialized || lease.domain != self.domain {
            self.stats.invalid_frees += 1;
            return false;
        }
        let Some(frame) = Self::frame_of(lease.addr) else {
            self.stats.invalid_frees += 1;
            return false;
        };
        if lease.id == 0 || self.alloc_id[frame] != lease.id {
            if bit(&self.free, frame) {
                self.stats.double_frees += 1;
            } else {
                self.stats.invalid_frees += 1;
            }
            return false;
        }
        self.release_by_address(lease.addr)
    }

    /// Claim a reserved growth-window frame for heap growth. Only frames
    /// inside the growth window can be claimed; they are accounted as
    /// allocated so stats stay consistent. None if already claimed or the
    /// frame is not completely covered by a usable range, or any competing
    /// firmware/kernel/boot reservation overlaps it. This exact-address API
    /// never searches beyond a blocked slot: contiguous heap growth must stop.
    pub fn claim_growth_frame(&mut self, addr: u64) -> Option<u64> {
        if !mutation_allowed() {
            return None;
        }
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
        let index = (addr as usize - paging::GROWTH_START) / FRAME_SIZE;
        if !bit(&self.covered, frame) || bit(&self.ncov, frame) || bit(&self.growth_claimed, index)
        {
            return None;
        }
        set_bit(&mut self.growth_claimed, index, true);
        set_bit(&mut self.ever, frame, true);
        // The frame was reserved for the heap; claiming it converts reserved
        // to allocated so the accounting stays consistent.
        self.stats.reserved_frames -= 1;
        self.stats.allocated_frames += 1;
        Some(addr)
    }

    /// Current allocation eligibility, not a transferable ownership capability.
    /// In particular, not-free includes reserved and uncovered memory. Keep
    /// those states separate before admitting a runtime payload mapping.
    pub(super) fn is_live_allocation(&self, addr: u64) -> bool {
        if !self.initialized || addr == 0 || addr % FRAME_SIZE as u64 != 0 {
            return false;
        }
        let Some(frame) = Self::frame_of(addr) else {
            return false;
        };
        if !bit(&self.covered, frame)
            || bit(&self.ncov, frame)
            || !bit(&self.ever, frame)
            || bit(&self.free, frame)
        {
            return false;
        }
        if paging::in_growth_window(addr) {
            let index = (addr as usize - paging::GROWTH_START) / FRAME_SIZE;
            return bit(&self.growth_claimed, index);
        }
        true
    }

    pub fn is_free(&self, addr: u64) -> bool {
        match Self::frame_of(addr) {
            Some(f) => bit(&self.free, f),
            None => false,
        }
    }

    pub(super) fn domain(&self) -> Option<u32> {
        (self.initialized && self.domain != 0).then_some(self.domain)
    }

    pub(super) fn runtime_pinned(&self, addr: u64) -> bool {
        self.initialized
            && addr % FRAME_SIZE as u64 == 0
            && Self::frame_of(addr).is_some_and(|frame| bit(&self.runtime_pins, frame))
    }

    pub(super) fn structure_pinned(&self, addr: u64) -> bool {
        self.initialized
            && addr % FRAME_SIZE as u64 == 0
            && Self::frame_of(addr).is_some_and(|frame| bit(&self.structure_pins, frame))
    }

    /// Memory-internal commit after managed/live allocation preflight, under
    /// the same exclusive allocator borrow; never a public ownership API.
    pub(super) fn set_runtime_pin(&mut self, addr: u64, pinned: bool) -> bool {
        if !mutation_allowed() || addr % FRAME_SIZE as u64 != 0 {
            return false;
        }
        let Some(frame) = Self::frame_of(addr) else {
            return false;
        };
        set_bit(&mut self.runtime_pins, frame, pinned);
        true
    }

    /// Set/clear only at structure install and release sites; the bitmap
    /// mirrors pm.tables and must not be cleared wholesale.
    pub(super) fn set_structure_pin(&mut self, addr: u64, pinned: bool) -> bool {
        if !mutation_allowed() || addr % FRAME_SIZE as u64 != 0 {
            return false;
        }
        let Some(frame) = Self::frame_of(addr) else {
            return false;
        };
        set_bit(&mut self.structure_pins, frame, pinned);
        true
    }

    pub fn stats(&self) -> &FrameStats {
        &self.stats
    }

    /// Full host oracle only; never called under memory-owner guards.
    #[cfg(test)]
    pub(super) fn exact_state_for_retained_test(&self) -> alloc::vec::Vec<u64> {
        let mut result = alloc::vec![
            self.next_id as u64,
            self.domain as u64,
            self.initialized as u64,
            self.stats.total_frames as u64,
            self.stats.reserved_frames as u64,
            self.stats.free_frames as u64,
            self.stats.allocated_frames as u64,
            self.stats.double_frees as u64,
            self.stats.invalid_frees as u64,
            self.stats.bitmap_frames as u64,
        ];
        for bitmap in [
            &self.free[..],
            &self.ever[..],
            &self.covered[..],
            &self.ncov[..],
            &self.growth_claimed[..],
            &self.runtime_pins[..],
            &self.structure_pins[..],
        ] {
            result.extend(bitmap.iter().map(|&b| b as u64));
        }
        result.extend(self.alloc_id.iter().map(|&id| id as u64));
        result
    }

    pub fn is_initialized(&self) -> bool {
        self.initialized
    }
}

#[cfg(test)]
mod domain_tests {
    use super::*;

    #[test]
    fn runtime_pin_domain_issuer_retires_at_maximum_without_wrap() {
        let last = AtomicU32::new(u32::MAX - 1);
        assert_eq!(issue_domain(&last), Some(u32::MAX));
        assert_eq!(issue_domain(&last), None);
        assert_eq!(issue_domain(&last), None);
        assert_eq!(last.load(Ordering::Relaxed), u32::MAX);
        let fresh = AtomicU32::new(0);
        assert_eq!(issue_domain(&fresh), Some(1));
        assert_eq!(issue_domain(&fresh), Some(2));
    }

    #[test]
    fn runtime_pin_both_reset_entries_preserve_every_live_inventory_field() {
        let entries = [MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x1000000,
            type_: 1,
        }];
        for growth in [false, true] {
            let mut fa = FrameAllocator::new();
            assert!(fa.init(&entries, 0x90000, 0xa0000, 0xb0000));
            let payload = if growth {
                fa.claim_growth_frame(paging::GROWTH_START as u64).unwrap()
            } else {
                fa.allocate().unwrap()
            };
            let before_domain = fa.domain;
            let before_stats = format!("{:?}", fa.stats());
            let free = fa.free;
            let ever = fa.ever;
            let covered = fa.covered;
            let denied = fa.ncov;
            let claimed = fa.growth_claimed;
            let structures = fa.structure_pins;
            for malformed in [false, true] {
                let spans = if malformed {
                    [(2, 1)]
                } else {
                    [(0x20000, 0x21000)]
                };
                assert!(!fa.init_with_reservations(&entries, 0x90000, 0xa0000, 0xb0000, &spans));
                assert!(!fa.init(&entries, 0x90000, 0xa0000, 0xb0000));
                assert_eq!(fa.domain, before_domain);
                assert!(fa.initialized);
                assert_eq!(format!("{:?}", fa.stats()), before_stats);
                assert_eq!(fa.free, free);
                assert_eq!(fa.ever, ever);
                assert_eq!(fa.covered, covered);
                assert_eq!(fa.ncov, denied);
                assert_eq!(fa.growth_claimed, claimed);
                assert_eq!(fa.structure_pins, structures);
                assert!(fa.runtime_pins.iter().all(|&byte| byte == 0));
            }
            assert!(fa.free(payload));
            assert!(fa.init(&entries, 0x90000, 0xa0000, 0xb0000));
            assert_ne!(fa.domain, before_domain);
        }
    }
}

#[cfg(test)]
mod generation_ledger_tests {
    use super::*;

    fn ledger_fixture() -> FrameAllocator {
        let mut fa = FrameAllocator::new();
        assert!(fa.init(
            &[MmapEntry {
                size: 20,
                base_addr: 0x10000,
                length: 0x70000,
                type_: 1,
            }],
            0x90000,
            0xa0000,
            0xb0000,
        ));
        fa
    }

    #[test]
    fn generation_safe_stale_forged_lease_cannot_release_reused_frame() {
        // The ABA sequence with a forged stale lease (module-internal only):
        // allocate -> release -> reallocate the same frame -> the stale
        // identity is refused and the current owner stays live.
        let mut fa = ledger_fixture();
        let lease = fa.allocate_owned().unwrap();
        let addr = lease.frame_addr();
        let stale_id = lease.id;
        let stale_domain = lease.domain;
        assert!(fa.release_frame(lease));
        let current = fa.allocate_owned().unwrap();
        assert_eq!(current.frame_addr(), addr);
        let current_id = current.id;
        let stale = FrameLease {
            addr,
            id: stale_id,
            domain: stale_domain,
        };
        assert!(
            !fa.release_frame(stale),
            "BLOCKER: stale identity released a reused frame",
        );
        assert!(!fa.is_free(addr));
        assert_eq!(fa.stats().allocated_frames, 1);
        assert_eq!(
            fa.alloc_id[FrameAllocator::frame_of(addr).unwrap()],
            current_id
        );
        assert!(fa.release_frame(current));
        assert!(fa.is_free(addr));
    }

    #[test]
    fn generation_safe_double_release_by_forged_copy_is_refused() {
        // The consumed lease cannot be reused (type-level); a forged copy of
        // its identity proves the ledger also refuses at runtime.
        let mut fa = ledger_fixture();
        let lease = fa.allocate_owned().unwrap();
        let addr = lease.frame_addr();
        let forged = FrameLease {
            addr: lease.addr,
            id: lease.id,
            domain: lease.domain,
        };
        assert!(fa.release_frame(lease));
        let before_free = fa.stats().free_frames;
        assert!(
            !fa.release_frame(forged),
            "BLOCKER: ledger accepted a released identity",
        );
        assert_eq!(fa.stats().free_frames, before_free);
        assert_eq!(fa.stats().allocated_frames, 0);
        assert_eq!(fa.alloc_id[FrameAllocator::frame_of(addr).unwrap()], 0);
    }

    #[test]
    fn generation_safe_ledger_identity_never_repeats_across_cycles() {
        // Every allocation stamps a strictly increasing identity; the ledger
        // never reissues an id, so a stale lease can never match a reused
        // frame even after many cycles.
        let mut fa = ledger_fixture();
        let mut previous_id = 0;
        for _ in 0..16 {
            let lease = fa.allocate_owned().unwrap();
            assert!(lease.id > previous_id, "identities are strictly monotonic");
            previous_id = lease.id;
            let frame = FrameAllocator::frame_of(lease.addr).unwrap();
            assert_eq!(fa.alloc_id[frame], lease.id);
            assert!(fa.release_frame(lease));
            assert_eq!(fa.alloc_id[frame], 0);
        }
    }

    #[test]
    fn generation_safe_identity_exhaustion_is_permanent_not_wrapping() {
        // Documented policy: at identity exhaustion allocation returns None
        // permanently; the ledger never wraps to a reused id.
        let mut fa = ledger_fixture();
        fa.next_id = u32::MAX;
        let last = fa.allocate_owned().unwrap();
        assert_eq!(last.id, u32::MAX);
        assert_eq!(fa.next_id, 0);
        assert_eq!(
            fa.alloc_id[FrameAllocator::frame_of(last.addr).unwrap()],
            u32::MAX
        );
        assert!(fa.allocate_owned().is_none());
        assert_eq!(fa.allocate(), None);
        assert_eq!(fa.next_id, 0);
        // Exhaustion blocks issuing new identities, not releasing live ones.
        assert!(fa.release_frame(last));
        assert!(fa.allocate_owned().is_none());
    }

    #[test]
    fn generation_safe_raw_free_path_clears_ledger_identity() {
        // The audited raw path must not leave the ledger lying: a frame
        // freed through raw free() has its identity cleared, and a
        // re-allocation stamps a fresh one.
        let mut fa = ledger_fixture();
        let lease = fa.allocate_owned().unwrap();
        let addr = lease.frame_addr();
        let frame = FrameAllocator::frame_of(addr).unwrap();
        assert_eq!(fa.alloc_id[frame], lease.id);
        assert!(fa.free(addr));
        assert_eq!(fa.alloc_id[frame], 0);
        let reacquired = fa.allocate_owned().unwrap();
        assert_eq!(reacquired.frame_addr(), addr);
        assert_eq!(fa.alloc_id[frame], reacquired.id);
        assert_ne!(reacquired.id, lease.id);
        assert!(fa.release_frame(reacquired));
    }

    #[test]
    fn generation_safe_raw_allocated_frame_has_no_lease_release_path() {
        // A frame handed out through the raw path carries a ledger identity,
        // but no lease exists to release it; release requires the proof, so
        // the raw path stays audited-internal and the frame is only
        // releasable through raw free().
        let mut fa = ledger_fixture();
        let addr = fa.allocate().unwrap();
        let frame = FrameAllocator::frame_of(addr).unwrap();
        assert_ne!(fa.alloc_id[frame], 0);
        assert!(fa.free(addr));
        assert_eq!(fa.alloc_id[frame], 0);
    }
}
