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

#[path = "retained_owner.rs"]
pub(crate) mod retained_owner;
use retained_owner::mutation_allowed;

#[cfg(test)]
#[path = "phase11_permission_tests.rs"]
mod phase11_permission_tests;

#[cfg(test)]
#[path = "phase11a2_ownership_tests.rs"]
mod phase11a2_ownership_tests;

#[cfg(test)]
#[path = "phase11a2_abi_tests.rs"]
mod phase11a2_abi_tests;

#[cfg(test)]
#[path = "runtime_table_access_tests.rs"]
mod runtime_table_access_tests;

#[cfg(test)]
#[path = "mapping_pin_tests.rs"]
mod mapping_pin_tests;

#[cfg(test)]
#[path = "structure_lifetime_tests.rs"]
mod structure_lifetime_tests;

#[cfg(test)]
#[path = "generation_ownership_tests.rs"]
mod generation_ownership_tests;

#[cfg(test)]
#[path = "virtual_page_zero_tests.rs"]
mod virtual_page_zero_tests;

#[cfg(test)]
#[path = "numeric_map_authority_tests.rs"]
mod numeric_map_authority_tests;

#[cfg(test)]
#[path = "unmap_authority_tests.rs"]
mod unmap_authority_tests;

#[cfg(test)]
#[path = "retained_owner_tests.rs"]
mod retained_owner_tests;

pub const PAGE_SIZE: usize = 4096;
pub const ENTRY_PRESENT: u32 = 1 << 0;
pub const ENTRY_WRITABLE: u32 = 1 << 1;
pub const ENTRY_USER: u32 = 1 << 2;
// Software-available PTE bit: only runtime entries own a payload registry bit.
// Boot supervisor identity aliases must not release those references.
const ENTRY_RUNTIME_PAYLOAD: u32 = 1 << 9;

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
        present: code & 1 != 0,
        write: code & 2 != 0,
        user: code & 4 != 0,
        // Bit 4 (instruction fetch) is only reported by CPUs supporting the
        // NX feature; on this 32-bit mode it is always 0 and reported as such.
        fetch: code & 16 != 0,
        cr2: 0,
    }
}

// Baseline mandatory-error predicate only, NOT a universal no-error classifier.
// F2 dispatch uses exception_abi::FrameKind: optional 21/29/30 are unsupported
// and terminate without decoding any CPU frame. Keep this inherited API narrow.
pub fn exception_pushes_error_code(vector: u8) -> bool {
    matches!(vector, 8 | 10 | 11 | 12 | 13 | 14 | 17)
}

// Fault-origin detection: the saved CS from the CPU frame carries the
// privilege level of the faulting code in the selector's RPL bits (0-1);
// the descriptor's DPL is not encoded in the selector value. Kernel-origin
// faults (ring 0) fail closed; only ring-3 faults may transfer to a
// kernel-owned continuation.
pub fn fault_ring_from_saved_cs(cs: u32) -> u32 {
    cs & 3
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
    domain: u32,
    // Published or CPU-loaded boot backing is retained until reboot.
    retained: bool,
    tables: Vec<u64>,
    // Page-rounded permanent boot identity spans; backing is prepared unlocked.
    boot_pins: Vec<(u64, u64)>,
    // Physical payload frames currently referenced by runtime mappings.
    // The registry is the alias authority: a frame already mapped at any
    // slot cannot be mapped at a second slot while the first mapping is
    // active, and unmap releases the reference. One bit per managed frame
    // (8 KiB, sized like the frame allocator's own bitmaps) so checks
    // stay O(1) in the guest. Boot identity frames are established by
    // build_identity_map and are never registered, so identity mappings
    // are unaffected.
    payload_bitmap: Vec<u8>,
    stats: PagingStats,
    window_end: u64,
}

impl PageMap {
    /// Return only paging-structure frames from an unpublished map. Borrowing
    /// keeps Vec backing alive until the caller has released its frame guard.
    /// Success revokes the map before any backing can be reused. Repeated
    /// cleanup is refused without touching the allocator. Vec storage remains
    /// alive for the caller to drop after unlocking.
    pub(super) fn release_unpublished_frames(&mut self, fa: &mut FrameAllocator) -> bool {
        if !mutation_allowed() {
            return false;
        }
        // This remains a prepare-failure-only helper, not general teardown.
        // Never release another domain or orphan live runtime payload pins.
        if self.retained
            || fa.domain() != Some(self.domain)
            || self.payload_bitmap.iter().any(|&byte| byte != 0)
        {
            return false;
        }
        // Check the entire release set before changing any role or capacity.
        // With exclusive allocator access, these checks make every free below
        // infallible; a damaged mirror must not leave a half-reclaimed map.
        let releasable = |frame| {
            fa.is_live_allocation(frame) && fa.structure_pinned(frame) && !fa.runtime_pinned(frame)
        };
        if !releasable(self.directory)
            || self
                .tables
                .iter()
                .any(|&table| table != 0 && !releasable(table))
        {
            return false;
        }
        for &table in &self.tables {
            if table != 0 {
                if !fa.set_structure_pin(table, false) {
                    return false;
                }
                fa.free(table);
            }
        }
        if !fa.set_structure_pin(self.directory, false) {
            return false;
        }
        fa.free(self.directory);
        self.tables.fill(0);
        self.directory = 0;
        self.domain = 0;
        self.window_end = 0;
        self.stats.page_tables = 0;
        self.stats.mapped_frames = 0;
        true
    }

    /// Seal before publication or any CR3 load. There is no inverse transition
    /// until a separately reviewed CPU teardown contract exists.
    pub(super) fn retain_for_publication(&mut self) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if self.domain == 0 {
            return false;
        }
        self.retained = true;
        true
    }

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
        self.permissions(linear).is_some_and(|p| p.present)
    }

    /// Check a nonempty byte span against permanent boot pins and current
    /// identity translations. This allocates nothing and grants no raw access.
    /// The caller must not retain this PageMap borrow across heap growth.
    pub(crate) fn pinned_identity_span(&self, start: u64, end: u64) -> bool {
        if start < PAGE_SIZE as u64 || start >= end || end > (1u64 << 32) {
            return false;
        }
        let mut page = start & !(PAGE_SIZE as u64 - 1);
        while page < end {
            if !self.boot_pins.iter().any(|&(a, b)| a <= page && page < b)
                || self.translate(page) != Some(page)
            {
                return false;
            }
            page += PAGE_SIZE as u64;
        }
        true
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
        if !self.permissions(linear)?.present {
            return None;
        }
        Some(e as u64 & 0xFFFFF000)
    }

    /// Effective permissions for the page containing a virtual address.
    /// The CPU intersects PRESENT, R/W and U/S at both levels. Absent pages
    /// grant no access, even when stale flag bits remain in either entry.
    /// This is not a user-buffer ownership check or an execute-disable claim.
    pub fn permissions(&self, linear: u64) -> Option<PagePerms> {
        let e = self.entry(linear)?;
        let directory_entry = read_entry(self.directory, page_dir_index(linear));
        let effective = e & directory_entry;
        let present = effective & ENTRY_PRESENT != 0;
        Some(PagePerms {
            present,
            writable: present && effective & ENTRY_WRITABLE != 0,
            user: present && effective & ENTRY_USER != 0,
            // NX requires PAE/long mode; this kernel uses 32-bit paging, so
            // execution cannot be restricted per page. Reported honestly.
            nx_supported: false,
        })
    }

    /// Publish an ordinary payload using borrowed current ownership authority.
    /// The lease stays caller-owned; runtime pins protect backing after this
    /// temporary borrow ends. No lease reference is stored in the PageMap.
    pub fn map_owned(
        &mut self,
        fa: &mut FrameAllocator,
        linear: u64,
        lease: &frame::FrameLease,
        perms: &PagePerms,
    ) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if fa.domain() != Some(self.domain) || !fa.owns_live_lease(lease) {
            self.stats.map_rejects += 1;
            return false;
        }
        self.map_authorized(fa, linear, lease.frame_addr(), perms)
    }

    /// Audited heap-only category: a live exact growth claim, identity mapped
    /// with fixed supervisor permissions. Cannot select ordinary backing.
    pub(super) fn map_growth_claim(&mut self, fa: &mut FrameAllocator, slot: u64) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if fa.domain() != Some(self.domain)
            || !in_growth_window(slot)
            || !fa.is_live_allocation(slot)
        {
            self.stats.map_rejects += 1;
            return false;
        }
        self.map_authorized(fa, slot, slot, &KERNEL_PERMS)
    }

    /// Explicit legacy numeric fault-injection authority, absent in production.
    /// These fixtures exercise the common checks, not lease authentication.
    #[cfg(test)]
    pub(crate) fn map(
        &mut self,
        fa: &mut FrameAllocator,
        linear: u64,
        phys_frame: u64,
        perms: &PagePerms,
    ) -> bool {
        self.map_authorized(fa, linear, phys_frame, perms)
    }

    /// Private publication core for the checked authority entry points above.
    /// Paging descendants can reach private items; all fixture descendants
    /// remain cfg(test). Bootstrap borrowed identity construction is separate.
    /// Map `frame` (must be page-aligned and inside the managed window) to
    /// `linear`. Rejects: unaligned addresses, addresses outside the paging
    /// window, conflicting present entries, and exhaustion (allocates a page
    /// table on demand only when one is missing). Invalidates the TLB entry
    /// on success.
    /// User mappings are unsupported by this raw kernel mapping API: they
    /// require a separately reviewed owned-address-space contract. Never
    /// promote an identity-map PDE to USER to approximate that contract.
    /// Nonpresent requests are rejected; use unmap to remove a mapping.
    fn map_authorized(
        &mut self,
        fa: &mut FrameAllocator,
        linear: u64,
        phys_frame: u64,
        perms: &PagePerms,
    ) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if fa.domain() != Some(self.domain) {
            self.stats.map_rejects += 1;
            return false;
        }
        if perms.user || !perms.present {
            self.stats.map_rejects += 1;
            return false;
        }
        if linear % PAGE_SIZE as u64 != 0 || phys_frame % PAGE_SIZE as u64 != 0 {
            self.stats.map_rejects += 1;
            return false;
        }
        if linear >= (1u64 << 32) || phys_frame >= frame::MAX_FRAME_ADDR {
            self.stats.map_rejects += 1;
            return false;
        }
        // Virtual page zero stays unmapped: the boot identity map deliberately
        // leaves it absent so null accesses fault, and an ordinary runtime
        // publication there would replace that faulting sentinel with an
        // unauthorized null-virtual mapping. No accepted boot requirement maps
        // virtual zero; supervisor identity construction is unaffected.
        if linear == 0 {
            self.stats.map_rejects += 1;
            return false;
        }
        // Boot identity mappings cover [0, window_end); the growth window is
        // mapped on demand. Anything else is outside the managed space.
        if linear >= self.window_end && !in_growth_window(linear) {
            self.stats.map_rejects += 1;
            return false;
        }
        // Authority was authenticated by the selected checked entry point;
        // preserve allocation eligibility and exclusive payload-role checks.
        // Boot supervisor identity mappings are constructed separately and
        // intentionally do not transfer payload ownership.
        if !fa.is_live_allocation(phys_frame)
            || fa.runtime_pinned(phys_frame)
            || fa.structure_pinned(phys_frame)
        {
            self.stats.map_rejects += 1;
            return false;
        }
        if phys_frame == self.directory || self.tables.contains(&phys_frame) {
            self.stats.map_rejects += 1;
            return false;
        }
        // Alias authority: a payload frame already referenced by an active
        // runtime mapping cannot be referenced by a second mapping. Boot
        // identity frames are established by build_identity_map and never
        // enter this registry, so identity mappings are unaffected.
        if payload_bit(&self.payload_bitmap, phys_frame) {
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
            // Runtime table writes use physical addresses as virtual pointers.
            // The current kernel map must still provide a writable supervisor
            // identity alias before zero_table can touch the candidate. A host
            // mirror alone cannot establish that accessibility. Fail closed on
            // the first candidate; do not retain inaccessible allocations while
            // searching or consume caller payload on this refusal.
            if self.translate(table) != Some(table)
                || !self
                    .permissions(table)
                    .is_some_and(|p| p.present && p.writable && !p.user)
            {
                fa.free(table);
                self.stats.map_rejects += 1;
                return false;
            }
            zero_table(table);
            // Install authority: pin only after installation, never at the
            // raw allocate site, so the accessibility rollback free above
            // (before any pin) still succeeds.
            if !fa.set_structure_pin(table, true) {
                return false;
            }
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
        let mut entry = phys_frame as u32 | ENTRY_PRESENT | ENTRY_RUNTIME_PAYLOAD;
        if perms.writable {
            entry |= ENTRY_WRITABLE;
        }
        // All refusals are complete. Commit the allocator-wide reference and
        // its local mirror before publishing the PTE; no fallible work follows.
        if !fa.set_runtime_pin(phys_frame, true) {
            return false;
        }
        payload_set_bit(&mut self.payload_bitmap, phys_frame, true);
        write_entry(self.tables[dir], idx, entry);
        self.stats.mapped_frames += 1;
        self.stats.maps += 1;
        invalidate_page(linear);
        self.stats.tlb_invalidation += 1;
        true
    }

    /// Unmap a runtime payload mapping using borrowed current ownership
    /// authority. The lease must be live in this allocator domain and its
    /// frame must be exactly the payload the slot's PTE references; a stale
    /// lease for a replaced same-slot mapping is refused without mutation.
    pub fn unmap_owned(
        &mut self,
        fa: &mut FrameAllocator,
        linear: u64,
        lease: &frame::FrameLease,
    ) -> bool {
        if !mutation_allowed() {
            return false;
        }
        if fa.domain() != Some(self.domain) || !fa.owns_live_lease(lease) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        self.unmap_authorized(fa, linear, Some(lease.frame_addr()))
    }

    /// Audited legacy numeric unmap for host fixtures only, absent in
    /// production. Exercises the shared structural checks without lease
    /// authentication; same precedent as the accepted legacy map adapter.
    #[cfg(test)]
    pub(crate) fn unmap(&mut self, fa: &mut FrameAllocator, linear: u64) -> bool {
        self.unmap_authorized(fa, linear, None)
    }

    /// Private unmap core for the checked authority entry points above.
    /// `expected_payload` (when present) must equal the PTE payload frame,
    /// binding the operation to the current slot mapping. Unmap a page-aligned
    /// virtual address. Rejects absent pages and boot-critical regions (kernel
    /// image, VGA, multiboot structures), which must stay mapped for the
    /// kernel to run. Retains every pre-existing check: domain, alignment,
    /// window, boot-critical and structure/boot-pin refusals, present,
    /// payload-consistency.
    fn unmap_authorized(
        &mut self,
        fa: &mut FrameAllocator,
        linear: u64,
        expected_payload: Option<u64>,
    ) -> bool {
        if !mutation_allowed() {
            return false;
        }
        // Domain mismatch must fail before any paging-structure dereference.
        if fa.domain() != Some(self.domain) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        if linear % PAGE_SIZE as u64 != 0 || linear >= (1u64 << 32) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        if linear >= self.window_end && !in_growth_window(linear) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        if is_boot_critical(linear)
            || linear == self.directory
            || self.tables.contains(&linear)
            || self
                .boot_pins
                .iter()
                .any(|&(start, end)| linear >= start && linear < end)
        {
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
        let payload = entry as u64 & 0xFFFFF000;
        if entry & ENTRY_RUNTIME_PAYLOAD != 0
            && (!fa.is_live_allocation(payload)
                || !fa.runtime_pinned(payload)
                || !payload_bit(&self.payload_bitmap, payload))
        {
            self.stats.unmap_rejects += 1;
            return false;
        }
        // Same-slot authority: the lease-authorized entry point requires the
        // current PTE payload to be exactly the frame the caller possesses.
        // A stale lease for a replaced mapping never matches the fresh
        // allocation identity and is refused before any mutation.
        if expected_payload.is_some() && expected_payload != Some(payload) {
            self.stats.unmap_rejects += 1;
            return false;
        }
        write_entry(base, idx, 0);
        // End CPU translation before returning release eligibility. Boot
        // aliases have no runtime ownership and never clear either pin mirror.
        invalidate_page(linear);
        self.stats.tlb_invalidation += 1;
        if entry & ENTRY_RUNTIME_PAYLOAD != 0 {
            payload_set_bit(&mut self.payload_bitmap, payload, false);
            if !fa.set_runtime_pin(payload, false) {
                return false;
            }
        }
        self.stats.mapped_frames -= 1;
        self.stats.unmaps += 1;
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

/// Bit helpers for the payload alias registry (same layout as the frame
/// allocator's bitmaps: one bit per managed frame).
fn payload_bit(bitmap: &[u8], frame_addr: u64) -> bool {
    let idx = frame_addr / PAGE_SIZE as u64;
    if idx >= bitmap.len() as u64 * 8 {
        return false;
    }
    (bitmap[(idx / 8) as usize] >> (idx % 8)) & 1 != 0
}

fn payload_set_bit(bitmap: &mut [u8], frame_addr: u64, value: bool) {
    let idx = frame_addr / PAGE_SIZE as u64;
    if idx >= bitmap.len() as u64 * 8 {
        return;
    }
    let byte = &mut bitmap[(idx / 8) as usize];
    let mask = 1u8 << (idx % 8);
    if value {
        *byte |= mask;
    } else {
        *byte &= !mask;
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
pub(super) fn flush_tlb(page_map: &mut PageMap) -> bool {
    if !mutation_allowed() {
        return false;
    }
    if !page_map.retain_for_publication() {
        return false;
    }
    #[cfg(not(test))]
    unsafe {
        core::arch::asm!(
            "mov {cr3}, %cr3",
            cr3 = in(reg) page_map.directory() as u32,
            options(att_syntax)
        );
    }
    #[cfg(test)]
    retained_owner::model_write(page_map.directory);
    true
}

/// Unlocked host-test convenience builder. Production must reserve all backing
/// before locking and call `build_identity_map_with_backing_in_place` instead.
#[cfg(test)]
pub fn build_identity_map(
    fa: &mut FrameAllocator,
    window_end: u64,
    mut tables: Vec<u64>,
) -> Option<PageMap> {
    build_identity_map_in_place(fa, window_end, &mut tables)
}

/// Unlocked host-test adapter retaining caller-owned table backing on failure.
#[cfg(test)]
pub(crate) fn build_identity_map_in_place(
    fa: &mut FrameAllocator,
    window_end: u64,
    tables: &mut Vec<u64>,
) -> Option<PageMap> {
    build_identity_map_with_pins_in_place(fa, window_end, tables, &mut Vec::new())
}

/// Unlocked host-test adapter for callers that supply permanent boot pins.
#[cfg(test)]
pub(crate) fn build_identity_map_with_pins_in_place(
    fa: &mut FrameAllocator,
    window_end: u64,
    tables: &mut Vec<u64>,
    boot_pins: &mut Vec<(u64, u64)>,
) -> Option<PageMap> {
    if !mutation_allowed() {
        return None;
    }
    let mut payload_bitmap = alloc::vec![0; PAYLOAD_BITMAP_BYTES];
    build_identity_map_with_backing_in_place(fa, window_end, tables, boot_pins, &mut payload_bitmap)
}

pub(crate) const PAYLOAD_BITMAP_BYTES: usize = frame::MAX_FRAMES / 8;

/// All backing remains caller-owned on failure and moves without allocation
/// on success. Reserve before map/frame locks; unlock before dropping backing.
pub(crate) fn build_identity_map_with_backing_in_place(
    fa: &mut FrameAllocator,
    window_end: u64,
    tables: &mut Vec<u64>,
    boot_pins: &mut Vec<(u64, u64)>,
    payload_bitmap: &mut Vec<u8>,
) -> Option<PageMap> {
    if !mutation_allowed() {
        return None;
    }
    if window_end == 0
        || window_end > (1u64 << 32)
        || tables.len() != PAGE_DIR_ENTRIES
        || tables.iter().any(|&frame| frame != 0)
        || payload_bitmap.len() != PAYLOAD_BITMAP_BYTES
        || payload_bitmap.iter().any(|&byte| byte != 0)
    {
        return None;
    }
    let domain = fa.domain()?;
    let directory = fa.allocate()?;
    zero_table(directory);
    // The directory is installed before any table candidate exists; the
    // exhaustion rollback below must clear this pin before freeing.
    if !fa.set_structure_pin(directory, true) {
        return None;
    }
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
                // Clear structure authority before each rollback free; a
                // pinned frame is refused by free() by design.
                for frame in tables.iter_mut() {
                    if *frame != 0 {
                        if !fa.set_structure_pin(*frame, false) {
                            return None;
                        }
                        fa.free(*frame);
                        *frame = 0;
                    }
                }
                if !fa.set_structure_pin(directory, false) {
                    return None;
                }
                fa.free(directory);
                return None;
            }
        };
        zero_table(table);
        if !fa.set_structure_pin(table, true) {
            return None;
        }
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
        domain,
        retained: false,
        tables: core::mem::take(tables),
        boot_pins: core::mem::take(boot_pins),
        payload_bitmap: core::mem::take(payload_bitmap),
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

/// Stream validation without heap allocation, including permanent boot pins.
fn missing_mapping_regions<'a>(
    page_map: &'a PageMap,
    required: impl IntoIterator<Item = (u64, u64, &'static str)> + 'a,
) -> impl Iterator<Item = &'static str> + 'a {
    required
        .into_iter()
        .chain(
            page_map
                .boot_pins
                .iter()
                .map(|&(start, end)| (start, end, "permanent boot span")),
        )
        .filter_map(move |(start, end, name)| {
            if start >= end {
                return None;
            }
            let mut addr = start & !(PAGE_SIZE as u64 - 1);
            while addr < end {
                // Growth holes are intentionally absent until mapped on demand.
                if !in_growth_window(addr) && !page_map.is_mapped(addr) {
                    return Some(name);
                }
                addr += PAGE_SIZE as u64;
            }
            None
        })
}

/// Return the first missing region with no allocation on success or failure.
pub fn first_missing_mapping(
    page_map: &PageMap,
    required: impl IntoIterator<Item = (u64, u64, &'static str)>,
) -> Option<&'static str> {
    missing_mapping_regions(page_map, required).next()
}

/// Allocating compatibility helper for unlocked host tests only.
#[cfg(test)]
pub fn validate_mapping(
    page_map: &PageMap,
    required: &[(u64, u64, &'static str)],
) -> Vec<&'static str> {
    missing_mapping_regions(page_map, required.iter().copied()).collect()
}

pub(super) fn enable_paging(page_map: &mut PageMap) -> bool {
    if !mutation_allowed() {
        return false;
    }
    if !page_map.retain_for_publication() {
        return false;
    }
    #[cfg(not(test))]
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
    #[cfg(test)]
    retained_owner::model_write(page_map.directory);
    page_map.stats.enabled = true;
    true
}

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
