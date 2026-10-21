//! Fixed F3 supervisor-only stacks and classic 32-bit task-state wire model.
//! Authority stays in the existing retained owner; this is not a mapper API.
use super::*;

pub(crate) const KERNEL_CODE: u64 = 0x00cf_9900_0000_ffff;
pub(crate) const KERNEL_DATA: u64 = 0x00cf_9300_0000_ffff;
pub(crate) const TRANSITION_GUARD: u32 = 0x07c0_0000;
pub(crate) const TRANSITION_BASE: u32 = 0x07c0_1000;
pub(crate) const TRANSITION_TOP: u32 = 0x07c0_5000;
pub(crate) const EMERGENCY_GUARD: u32 = 0x07c0_5000;
pub(crate) const EMERGENCY_BASE: u32 = 0x07c0_6000;
pub(crate) const EMERGENCY_TOP: u32 = 0x07c0_a000;

/// High half of selector slots is reserved and always initialized to zero.
/// Hardware may update dynamic slots on a task switch; no shared reference to
/// installed storage may survive CPU publication.
#[repr(C)]
pub(crate) struct Tss {
    pub backlink: u32,
    pub esp0: u32,
    pub ss0: u32,
    pub esp1: u32,
    pub ss1: u32,
    pub esp2: u32,
    pub ss2: u32,
    pub cr3: u32,
    pub eip: u32,
    pub eflags: u32,
    pub eax: u32,
    pub ecx: u32,
    pub edx: u32,
    pub ebx: u32,
    pub esp: u32,
    pub ebp: u32,
    pub esi: u32,
    pub edi: u32,
    pub es: u32,
    pub cs: u32,
    pub ss: u32,
    pub ds: u32,
    pub fs: u32,
    pub gs: u32,
    pub ldt: u32,
    pub trap: u16,
    pub iomap: u16,
}

impl Tss {
    pub const fn new() -> Self {
        Self {
            backlink: 0,
            esp0: 0,
            ss0: 0,
            esp1: 0,
            ss1: 0,
            esp2: 0,
            ss2: 0,
            cr3: 0,
            eip: 0,
            eflags: 0,
            eax: 0,
            ecx: 0,
            edx: 0,
            ebx: 0,
            esp: 0,
            ebp: 0,
            esi: 0,
            edi: 0,
            es: 0,
            cs: 0,
            ss: 0,
            ds: 0,
            fs: 0,
            gs: 0,
            ldt: 0,
            trap: 0,
            iomap: 104,
        }
    }
}

pub(crate) const fn descriptor(base: u32, access: u8) -> u64 {
    103 | ((base as u64 & 0xffff) << 16)
        | (((base as u64 >> 16) & 0xff) << 32)
        | ((access as u64) << 40)
        | ((base as u64 & 0xff00_0000) << 32)
}

const _: () = {
    assert!(core::mem::size_of::<Tss>() == 104);
    assert!(core::mem::align_of::<Tss>() == 4);
    assert!(core::mem::offset_of!(Tss, esp0) == 4);
    assert!(core::mem::offset_of!(Tss, ss0) == 8);
    assert!(core::mem::offset_of!(Tss, cr3) == 28);
    assert!(core::mem::offset_of!(Tss, eip) == 32);
    assert!(core::mem::offset_of!(Tss, eflags) == 36);
    assert!(core::mem::offset_of!(Tss, eax) == 40);
    assert!(core::mem::offset_of!(Tss, esp) == 56);
    assert!(core::mem::offset_of!(Tss, es) == 72);
    assert!(core::mem::offset_of!(Tss, cs) == 76);
    assert!(core::mem::offset_of!(Tss, ss) == 80);
    assert!(core::mem::offset_of!(Tss, ldt) == 96);
    assert!(core::mem::offset_of!(Tss, trap) == 100);
    assert!(core::mem::offset_of!(Tss, iomap) == 102);
    assert!(TRANSITION_TOP - TRANSITION_BASE == 16384);
    assert!(EMERGENCY_TOP - EMERGENCY_BASE == 16384);
};

impl PageMap {
    pub(super) fn privileged_slot(&self, linear: u64) -> bool {
        self.privileged_reserved
            && linear >= TRANSITION_GUARD as u64
            && linear < EMERGENCY_TOP as u64
    }

    /// One finite transaction, called only by retained-owner Preparing. The
    /// complete preflight dominates zeroing, pinning and every PTE write.
    pub(in crate::memory) fn install_privileged_stacks(
        &mut self,
        fa: &mut FrameAllocator,
        transition: &[Option<frame::FrameLease>; 4],
        emergency: &[Option<frame::FrameLease>; 4],
    ) -> bool {
        if !mutation_allowed()
            || self.privileged_reserved
            || !self.retained
            || !self.stats.enabled
            || fa.domain() != Some(self.domain)
            || self.window_end < EMERGENCY_TOP as u64
        {
            return false;
        }
        let table = self.tables[31];
        if table == 0
            || !fa.structure_pinned(table)
            || self.translate(table) != Some(table)
            || !self
                .permissions(table)
                .is_some_and(|p| p.present && p.writable && !p.user)
        {
            return false;
        }
        for i in 0..10 {
            let va = TRANSITION_GUARD as u64 + (i * PAGE_SIZE) as u64;
            if self.translate(va) != Some(va)
                || !self
                    .permissions(va)
                    .is_some_and(|p| p.present && p.writable && !p.user)
                || self
                    .entry(va)
                    .is_none_or(|e| e & ENTRY_RUNTIME_PAYLOAD != 0)
                || fa.is_live_allocation(va)
                || fa.runtime_pinned(va)
                || fa.structure_pinned(va)
                || is_boot_critical(va)
                || self.boot_pins.iter().any(|&(a, b)| a <= va && va < b)
            {
                return false;
            }
        }
        // The eight frame identities are private, nonduplicated leases in the
        // same owner. Still explicitly refuse duplicates before any pin write.
        let mut addresses = [0u64; 8];
        for (i, slot) in transition.iter().chain(emergency.iter()).enumerate() {
            let Some(lease) = slot.as_ref() else {
                return false;
            };
            let address = lease.frame_addr();
            if !fa.owns_live_lease(lease)
                || fa.runtime_pinned(address)
                || fa.structure_pinned(address)
                || payload_bit(&self.payload_bitmap, address)
                || self.translate(address) != Some(address)
                || !self
                    .permissions(address)
                    .is_some_and(|p| p.present && p.writable && !p.user)
                || (address >= TRANSITION_GUARD as u64 && address < EMERGENCY_TOP as u64)
                || addresses[..i].contains(&address)
            {
                return false;
            }
            addresses[i] = address;
        }
        #[cfg(not(test))]
        for &address in &addresses {
            // Physical write only after identity-access and lease preflight.
            unsafe {
                core::ptr::write_bytes(address as *mut u8, 0, PAGE_SIZE);
            }
        }
        // A terminal partial failure retains this reservation and every lease.
        // No returning mapper may replace even an as-yet-unwritten slot.
        self.privileged_reserved = true;
        for i in 0..10 {
            let va = TRANSITION_GUARD as u64 + (i * PAGE_SIZE) as u64;
            let entry = if i == 0 || i == 5 {
                self.stats.mapped_frames -= 1;
                self.stats.unmaps += 1;
                0
            } else {
                let address = addresses[if i < 5 { i - 1 } else { i - 2 }];
                if !fa.set_runtime_pin(address, true) {
                    return false;
                }
                payload_set_bit(&mut self.payload_bitmap, address, true);
                self.stats.maps += 1;
                address as u32 | ENTRY_PRESENT | ENTRY_WRITABLE | ENTRY_RUNTIME_PAYLOAD
            };
            write_entry(table, page_table_index(va), entry);
            invalidate_page(va);
            self.stats.tlb_invalidation += 1;
        }
        self.privileged_stacks_valid(fa, transition, emergency)
    }

    pub(in crate::memory) fn privileged_stacks_valid(
        &self,
        fa: &FrameAllocator,
        transition: &[Option<frame::FrameLease>; 4],
        emergency: &[Option<frame::FrameLease>; 4],
    ) -> bool {
        if !self.privileged_reserved || fa.domain() != Some(self.domain) {
            return false;
        }
        for guard in [TRANSITION_GUARD, EMERGENCY_GUARD] {
            if self.entry(guard as u64) != Some(0) || self.translate(guard as u64).is_some() {
                return false;
            }
        }
        for (i, slot) in transition.iter().chain(emergency.iter()).enumerate() {
            let Some(lease) = slot.as_ref() else {
                return false;
            };
            let address = lease.frame_addr();
            let va = if i < 4 {
                TRANSITION_BASE as u64 + (i * PAGE_SIZE) as u64
            } else {
                EMERGENCY_BASE as u64 + ((i - 4) * PAGE_SIZE) as u64
            };
            if !fa.owns_live_lease(lease)
                || !fa.runtime_pinned(address)
                || !payload_bit(&self.payload_bitmap, address)
                || self.translate(va) != Some(address)
                || !self
                    .permissions(va)
                    .is_some_and(|p| p.present && p.writable && !p.user)
            {
                return false;
            }
        }
        true
    }
}

#[cfg(test)]
#[path = "privileged_tests.rs"]
mod tests;
