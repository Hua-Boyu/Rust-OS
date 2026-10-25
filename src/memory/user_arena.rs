//! Finite F4 USER arena; only the admitted retained owner can publish it.
//! Shared CR3, no NX, no CPL3, no teardown or returning production entry.
use super::retained_owner::{PREPARING, RetainedOwner, STATE};
use super::*;
use core::sync::atomic::{Ordering, compiler_fence};

pub(crate) const START: u64 = 0x4000_0000;
pub(crate) const END: u64 = 0x4040_0000;
pub(crate) const GUARD: u64 = 0x403f_e000;
pub(crate) const STACK: u64 = 0x403f_f000;
pub(crate) const PREFIX: [u8; 4] = [0x0f, 0x0b, 0xeb, 0xfc];
pub(crate) const DATA: &[u8] = b"F4-RO-DATA\0";

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Image {
    F4,
    F5,
}

#[cfg(test)]
#[path = "f5_page_observation.rs"]
pub(super) mod observation;

// Private exact-one-page transport, not an arbitrary payload loading API.
// The caller has validated the two distinct writable supervisor aliases.
unsafe fn initialize_pages(code: *mut u8, stack: *mut u8, image: Image) {
    unsafe {
        core::ptr::write_bytes(code, 0, PAGE_SIZE);
        core::ptr::copy_nonoverlapping(PREFIX.as_ptr(), code, PREFIX.len());
        core::ptr::copy_nonoverlapping(DATA.as_ptr(), code.add(2048), DATA.len());
        if image == Image::F5 {
            for (i, row) in f5_contract::F5_ROWS.iter().enumerate() {
                core::ptr::copy_nonoverlapping(
                    row.bytes.as_ptr(),
                    code.add(
                        f5_contract::F5_PAYLOAD_OFFSET as usize + i * f5_contract::F5_SLOT_BYTES,
                    ),
                    row.bytes.len(),
                );
            }
        }
        core::ptr::write_bytes(stack, 0, PAGE_SIZE);
    }
}

fn image_byte(offset: usize, image: Image) -> u8 {
    if offset < PREFIX.len() {
        return PREFIX[offset];
    }
    if (2048..2048 + DATA.len()).contains(&offset) {
        return DATA[offset - 2048];
    }
    if image == Image::F5 && (256..640).contains(&offset) {
        let slot = (offset - 256) / 64;
        let within = (offset - 256) % 64;
        if within < f5_contract::F5_ROWS[slot].bytes.len() {
            return f5_contract::F5_ROWS[slot].bytes[within];
        }
    }
    0
}

unsafe fn image_matches(code: *const u8, stack: *const u8, image: Image) -> bool {
    for offset in 0..PAGE_SIZE {
        unsafe {
            if core::ptr::read_volatile(code.add(offset)) != image_byte(offset, image)
                || core::ptr::read_volatile(stack.add(offset)) != 0
            {
                return false;
            }
        }
    }
    true
}

pub(super) fn valid_f5_image(owner: &RetainedOwner) -> bool {
    let (Some(code), Some(stack)) = (owner.payload.as_ref(), owner.user_stack.as_ref()) else {
        return false;
    };
    #[cfg(not(test))]
    unsafe {
        image_matches(
            code.frame_addr() as *const u8,
            stack.frame_addr() as *const u8,
            Image::F5,
        )
    }
    #[cfg(test)]
    observation::valid_image(code.frame_addr(), stack.frame_addr())
}

fn initialize_owned_pages(code: u64, stack: u64, image: Image) -> bool {
    #[cfg(not(test))]
    unsafe {
        initialize_pages(code as *mut u8, stack as *mut u8, image);
        true
    }
    #[cfg(test)]
    observation::initialize(code, stack, image)
}

#[derive(Clone, Copy)]
pub(super) struct Layout {
    pub(super) start: u64,
    pub(super) end: u64,
    pub(super) guard: u64,
    pub(super) stack: u64,
}

pub(super) const LAYOUT: Layout = Layout {
    start: START,
    end: END,
    guard: GUARD,
    stack: STACK,
};

impl Layout {
    pub(super) fn valid(self) -> bool {
        self.start == START && self.end == END && self.guard == GUARD && self.stack == STACK
    }
}

fn supervisor_alias(pm: &PageMap, address: u64) -> bool {
    pm.translate(address) == Some(address)
        && pm
            .permissions(address)
            .is_some_and(|p| p.present && p.writable && !p.user)
}

/// Audit raw directory entries against the private retained inventory before
/// reading each table. Only the installed F4 directory may be skipped at final
/// validation; it is checked separately in full below.
pub(super) fn supervisor_inventory(pm: &PageMap, fa: &FrameAllocator, installed: bool) -> bool {
    if !pm.retained
        || !pm.stats.enabled
        || fa.domain() != Some(pm.domain)
        || pm.directory == 0
        || !fa.structure_pinned(pm.directory)
        || pm.tables.len() != PAGE_DIR_ENTRIES
        || pm.window_end > START
        || !supervisor_alias(pm, pm.directory)
    {
        return false;
    }
    for dir in 0..PAGE_DIR_ENTRIES {
        if installed && dir == 256 {
            continue;
        }
        let raw = read_entry(pm.directory, dir);
        let table = pm.tables[dir];
        if table == 0 {
            if raw != 0 {
                return false;
            }
            continue;
        }
        if raw & (ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_USER | (1 << 7)) != 3
            || (raw as u64 & 0xffff_f000) != table
            || !fa.structure_pinned(table)
            || !supervisor_alias(pm, table)
        {
            return false;
        }
        for idx in 0..PAGE_TABLE_ENTRIES {
            if read_entry(table, idx) & ENTRY_USER != 0 {
                return false;
            }
        }
    }
    true
}

pub(super) fn preflight_map(pm: &PageMap, fa: &FrameAllocator, layout: Layout) -> bool {
    layout.valid()
        && supervisor_inventory(pm, fa, false)
        && !pm.user_arena_reserved
        && pm.tables[256] == 0
        && read_entry(pm.directory, 256) == 0
        && pm.tables[257] == 0
        && read_entry(pm.directory, 257) == 0
}

pub(super) fn new_frame(pm: &PageMap, fa: &FrameAllocator, lease: &frame::FrameLease) -> bool {
    let address = lease.frame_addr();
    let (kernel_start, kernel_end) = frame::kernel_bounds();
    fa.owns_live_lease(lease)
        && !fa.runtime_pinned(address)
        && !fa.structure_pinned(address)
        && !payload_bit(&pm.payload_bitmap, address)
        && supervisor_alias(pm, address)
        && !(address < kernel_end && address + PAGE_SIZE as u64 > kernel_start)
        && !pm
            .boot_pins
            .iter()
            .any(|&(a, b)| address < b && address + PAGE_SIZE as u64 > a)
        && !(address >= privileged::TRANSITION_GUARD as u64
            && address < privileged::EMERGENCY_TOP as u64)
}

fn distinct(owner: &RetainedOwner, fa: &FrameAllocator) -> bool {
    let mut addresses = [0u64; 12];
    for (i, slot) in core::iter::once(&owner.payload)
        .chain(core::iter::once(&owner.sentinel))
        .chain(owner.transition.iter())
        .chain(owner.emergency.iter())
        .chain(core::iter::once(&owner.user_stack))
        .chain(core::iter::once(&owner.arena_table))
        .enumerate()
    {
        let Some(lease) = slot.as_ref() else {
            return false;
        };
        if !fa.owns_live_lease(lease) || addresses[..i].contains(&lease.frame_addr()) {
            return false;
        }
        addresses[i] = lease.frame_addr();
    }
    true
}

/// Test mirrors are model backing, not guest allocations. B26 pre-seeds them
/// outside all owner guards and observes this existing-Vec zero-in-place path.
fn initialize_table(table: u64) {
    #[cfg(not(test))]
    zero_table(table);
    #[cfg(test)]
    {
        let exists = MIRROR.with(|m| {
            let mut mirror = m.borrow_mut();
            if let Some(words) = mirror.get_mut(&table) {
                words.fill(0);
                true
            } else {
                false
            }
        });
        if !exists {
            zero_table(table);
        }
    }
}

fn store(table: u64, index: usize, value: u32) {
    #[cfg(not(test))]
    unsafe {
        core::ptr::write_volatile((table as *mut u32).add(index), value);
    }
    #[cfg(test)]
    write_entry(table, index, value);
}

/// Whole preflight dominates all byte/pin writes. Static owning slots have
/// already received every lease. No ordinary map API gains USER authority.
pub(super) fn install(
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
    owner: &RetainedOwner,
    layout: Layout,
) -> bool {
    install_image(pm, fa, owner, layout, Image::F4)
}

pub(super) fn install_f5(
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
    owner: &RetainedOwner,
    layout: Layout,
) -> bool {
    install_image(pm, fa, owner, layout, Image::F5)
}

fn install_image(
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
    owner: &RetainedOwner,
    layout: Layout,
    image: Image,
) -> bool {
    if STATE.load(Ordering::Acquire) != PREPARING
        || !preflight_map(pm, fa, layout)
        || !pm.privileged_stacks_valid(fa, &owner.transition, &owner.emergency)
        || !distinct(owner, fa)
    {
        return false;
    }
    let (Some(code), Some(stack), Some(table)) = (
        owner.payload.as_ref(),
        owner.user_stack.as_ref(),
        owner.arena_table.as_ref(),
    ) else {
        return false;
    };
    if ![code, stack, table].iter().all(|l| new_frame(pm, fa, l)) {
        return false;
    }
    let code = code.frame_addr();
    let stack = stack.frame_addr();
    let table = table.frame_addr();
    let (Some(page_tables), Some(mapped_frames), Some(maps), Some(invalidations)) = (
        pm.stats.page_tables.checked_add(1),
        pm.stats.mapped_frames.checked_add(2),
        pm.stats.maps.checked_add(2),
        pm.stats.tlb_invalidation.checked_add(2),
    ) else {
        return false;
    };
    if !initialize_owned_pages(code, stack, image) {
        return false;
    }
    #[cfg(test)]
    observation::event(1, owner, pm, fa, code, stack, table);
    initialize_table(table);
    // F4_PREPUBLICATION: raw PDE256 is still zero here. Any unexpected pin
    // refusal closes the admitted wrapper terminally, retaining this prefix.
    #[cfg(all(not(test), target_os = "none"))]
    unsafe {
        core::arch::asm!(
            ".global f4_prepublication",
            ".set f4_prepublication, .",
            options(nostack)
        );
    }
    if !fa.set_runtime_pin(code, true) {
        return false;
    }
    #[cfg(test)]
    observation::event(2, owner, pm, fa, code, stack, table);
    if !fa.set_runtime_pin(stack, true) {
        return false;
    }
    #[cfg(test)]
    observation::event(3, owner, pm, fa, code, stack, table);
    if !fa.set_structure_pin(table, true) {
        return false;
    }
    #[cfg(test)]
    observation::event(4, owner, pm, fa, code, stack, table);
    payload_set_bit(&mut pm.payload_bitmap, code, true);
    payload_set_bit(&mut pm.payload_bitmap, stack, true);
    #[cfg(test)]
    observation::event(5, owner, pm, fa, code, stack, table);
    store(
        table,
        0,
        code as u32 | ENTRY_PRESENT | ENTRY_USER | ENTRY_RUNTIME_PAYLOAD,
    );
    #[cfg(test)]
    observation::event(6, owner, pm, fa, code, stack, table);
    store(
        table,
        1023,
        stack as u32 | ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_USER | ENTRY_RUNTIME_PAYLOAD,
    );
    #[cfg(test)]
    observation::event(7, owner, pm, fa, code, stack, table);
    pm.tables[256] = table;
    pm.user_arena_reserved = true;
    pm.stats.page_tables = page_tables;
    pm.stats.mapped_frames = mapped_frames;
    pm.stats.maps = maps;
    compiler_fence(Ordering::Release);
    // Last hardware publication; all owning authority and both leaves exist.
    #[cfg(test)]
    observation::event(8, owner, pm, fa, code, stack, table);
    store(
        pm.directory,
        256,
        table as u32 | ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_USER,
    );
    invalidate_page(START);
    invalidate_page(STACK);
    pm.stats.tlb_invalidation = invalidations;
    true
}

pub(super) fn valid(pm: &PageMap, fa: &FrameAllocator, owner: &RetainedOwner) -> bool {
    if !pm.user_arena_reserved
        || !distinct(owner, fa)
        || !pm.privileged_stacks_valid(fa, &owner.transition, &owner.emergency)
        || !supervisor_inventory(pm, fa, true)
    {
        return false;
    }
    let (Some(code), Some(stack), Some(table)) = (
        owner.payload.as_ref(),
        owner.user_stack.as_ref(),
        owner.arena_table.as_ref(),
    ) else {
        return false;
    };
    let code = code.frame_addr();
    let stack = stack.frame_addr();
    let table = table.frame_addr();
    if pm.tables[256] != table
        || !fa.structure_pinned(table)
        || fa.runtime_pinned(table)
        || !supervisor_alias(pm, table)
        || !supervisor_alias(pm, code)
        || !supervisor_alias(pm, stack)
        || !fa.runtime_pinned(code)
        || !fa.runtime_pinned(stack)
        || !payload_bit(&pm.payload_bitmap, code)
        || !payload_bit(&pm.payload_bitmap, stack)
        || read_entry(pm.directory, 256) & !0x20 != table as u32 | 7
    {
        return false;
    }
    for i in 0..1024 {
        let expected = match i {
            0 => code as u32 | ENTRY_PRESENT | ENTRY_USER | ENTRY_RUNTIME_PAYLOAD,
            1023 => {
                stack as u32 | ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_USER | ENTRY_RUNTIME_PAYLOAD
            }
            _ => 0,
        };
        let raw = read_entry(table, i);
        // Only hardware A/D may change mapped leaves; absent entries stay0.
        if (if expected == 0 { raw } else { raw & !0x60 }) != expected {
            return false;
        }
    }
    true
}

const _: () = {
    assert!(END - START == 1024 * PAGE_SIZE as u64);
    assert!(STACK + PAGE_SIZE as u64 == END);
    assert!(GUARD + PAGE_SIZE as u64 == STACK);
    assert!(1 + 1 + 4 + 4 + 1 + 1 == 12);
};
