//! Finite, cooperative single-vCPU Ring-0 terminal authority.
//! No reset, shared ownership, USER publication, teardown or CPL3 entry.
use super::*;
use crate::utils::mutex::SpinMutex;
use core::sync::atomic::{AtomicU8, Ordering};

const DORMANT: u8 = 0;
const PREPARING: u8 = 1;
const SEALED: u8 = 2;
const TERMINAL: u8 = 3;
static STATE: AtomicU8 = AtomicU8::new(DORMANT);
// (entire future policy maximum, maximum acquired in this F1 version).
const MANIFEST: [(u8, u8); 6] = [(1, 1), (1, 1), (1, 0), (4, 0), (4, 0), (1, 0)];

struct RetainedOwner {
    payload: Option<frame::FrameLease>,
    sentinel: Option<frame::FrameLease>,
    directory: u64,
    allocator_domain: u32,
    window_end: u64,
    table_count: usize,
    mapped_count: usize,
    capacity_before: [usize; 3],
    capacity_after: [usize; 3],
    future_ranges: [[u32; 4]; 3],
    capture: [u32; 16],
}

impl RetainedOwner {
    const fn new() -> Self {
        Self {
            payload: None,
            sentinel: None,
            directory: 0,
            allocator_domain: 0,
            window_end: 0,
            table_count: 0,
            mapped_count: 0,
            capacity_before: [0; 3],
            capacity_after: [0; 3],
            future_ranges: [[0; 4]; 3],
            capture: [0; 16],
        }
    }
}

static OWNER: SpinMutex<RetainedOwner> = SpinMutex::new(RetainedOwner::new());
const _: () = assert!(
    core::mem::size_of::<SpinMutex<RetainedOwner>>()
        + core::mem::size_of::<AtomicU8>()
        + core::mem::size_of_val(&MANIFEST)
        <= 4096
);
const _: () = assert!(1 + 1 + 1 + 4 + 4 + 1 == 12);

pub(in crate::memory) fn mutation_allowed() -> bool {
    STATE.load(Ordering::Acquire) < SEALED
}

pub(in crate::memory) fn owner_locked() -> bool {
    OWNER.is_locked()
}

fn try_admit() -> bool {
    STATE
        .compare_exchange(DORMANT, PREPARING, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[derive(Clone, Copy, PartialEq, Eq)]
struct CpuState {
    cr0: u32,
    cr3: u32,
    cr4: u32,
    cs: u16,
}

#[cfg(test)]
static MODEL_CPU: SpinMutex<CpuState> = SpinMutex::new(CpuState {
    cr0: 0,
    cr3: 0,
    cr4: 0,
    cs: 0,
});
#[cfg(test)]
static MODEL_WRITES: core::sync::atomic::AtomicUsize = core::sync::atomic::AtomicUsize::new(0);
#[cfg(test)]
static MODEL_FAIL_FINAL: core::sync::atomic::AtomicBool =
    core::sync::atomic::AtomicBool::new(false);

fn hardware() -> CpuState {
    #[cfg(test)]
    return *MODEL_CPU.lock();
    #[cfg(not(test))]
    unsafe {
        let cr0: usize;
        let cr3: usize;
        let cr4: usize;
        let cs: u16;
        core::arch::asm!("mov {}, cr0", out(reg) cr0, options(nostack));
        core::arch::asm!("mov {}, cr3", out(reg) cr3, options(nostack));
        core::arch::asm!("mov {}, cr4", out(reg) cr4, options(nostack));
        core::arch::asm!("mov {0:x}, cs", out(reg) cs, options(nostack));
        CpuState {
            cr0: cr0 as u32,
            cr3: cr3 as u32,
            cr4: cr4 as u32,
            cs,
        }
    }
}

#[cfg(test)]
pub(in crate::memory) fn model_write(directory: u64) {
    MODEL_CPU.lock().cr3 = directory as u32;
    MODEL_WRITES.fetch_add(1, Ordering::Relaxed);
}

fn capacity(fa: &FrameAllocator) -> [usize; 3] {
    let stats = fa.stats();
    [
        stats.free_frames,
        stats.allocated_frames,
        stats.reserved_frames,
    ]
}

fn identity(pm: &PageMap, fa: &FrameAllocator, cpu: CpuState) -> bool {
    cpu.cr0 & 0x80010000 == 0x80010000
        && cpu.cr4 & 0x30 == 0
        && cpu.cr3 & 4095 == 0
        && cpu.cr3 as u64 == pm.directory
        && cpu.cs & 3 == 0
        && pm.retained
        && pm.stats.enabled
        && fa.domain() == Some(pm.domain)
        && fa.structure_pinned(pm.directory)
        && pm.tables.iter().all(|&p| p == 0 || fa.structure_pinned(p))
}

fn valid_lease(pm: &PageMap, fa: &FrameAllocator, lease: &frame::FrameLease) -> bool {
    let address = lease.frame_addr();
    fa.owns_live_lease(lease)
        && !fa.runtime_pinned(address)
        && !fa.structure_pinned(address)
        && pm.translate(address) == Some(address)
        && pm
            .permissions(address)
            .is_some_and(|p| p.present && p.writable && !p.user)
}

fn close_failure(owner: &mut RetainedOwner, fa: &FrameAllocator, code: u32) -> bool {
    owner.capture[0] = code;
    owner.capacity_after = capacity(fa);
    owner.capture[12] = owner.capacity_after[0] as u32;
    owner.capture[13] = owner.capacity_after[1] as u32;
    owner.capture[15] = TERMINAL as u32;
    STATE.store(TERMINAL, Ordering::Release);
    false
}

// Caller continuously owns smoke -> PAGE_MAP -> FRAME_ALLOC, with CLI and no
// IRQ/NMI/fatal owner reentry. Only a scalar returns to the divergent wrapper.
#[inline(never)]
fn prepare_locked(owner: &mut RetainedOwner, pm: &PageMap, fa: &mut FrameAllocator) -> bool {
    owner.directory = pm.directory;
    owner.allocator_domain = pm.domain;
    owner.window_end = pm.window_end;
    owner.table_count = pm.stats.page_tables;
    owner.mapped_count = pm.stats.mapped_frames;
    owner.capacity_before = capacity(fa);
    let cpu = hardware();
    owner.capture[2] = pm.directory as u32;
    owner.capture[3] = pm.domain;
    owner.capture[4] = cpu.cr0;
    owner.capture[5] = cpu.cr3;
    owner.capture[6] = cpu.cr4;
    owner.capture[7] = cpu.cs as u32;
    owner.capture[10] = owner.capacity_before[0] as u32;
    owner.capture[11] = owner.capacity_before[1] as u32;
    owner.capture[14] = MANIFEST.iter().map(|entry| entry.0 as u32).sum();
    if !identity(pm, fa, cpu) {
        return close_failure(owner, fa, 1);
    }
    // F1_GUEST_DENY_FIRST
    owner.payload = fa.allocate_owned();
    let Some(payload) = owner.payload.as_ref() else {
        return close_failure(owner, fa, 2);
    };
    owner.capture[1] = 1;
    owner.capture[8] = payload.frame_addr() as u32;
    // F1_GUEST_DENY_ALIAS
    if !valid_lease(pm, fa, payload) {
        return close_failure(owner, fa, 3);
    }
    // F1_GUEST_DENY_SECOND
    owner.sentinel = fa.allocate_owned();
    let Some(sentinel) = owner.sentinel.as_ref() else {
        return close_failure(owner, fa, 4);
    };
    owner.capture[1] = 2;
    owner.capture[9] = sentinel.frame_addr() as u32;
    if !valid_lease(pm, fa, sentinel) || owner.capture[8] == owner.capture[9] {
        return close_failure(owner, fa, 5);
    }
    owner.capacity_after = capacity(fa);
    owner.capture[12] = owner.capacity_after[0] as u32;
    owner.capture[13] = owner.capacity_after[1] as u32;
    // F1_GUEST_DENY_IDENTITY
    #[cfg(test)]
    if MODEL_FAIL_FINAL.load(Ordering::Relaxed) {
        MODEL_CPU.lock().cr3 ^= PAGE_SIZE as u32;
    }
    if hardware() != cpu || !identity(pm, fa, hardware()) {
        return close_failure(owner, fa, 6);
    }
    owner.capture[0] = 0;
    owner.capture[15] = SEALED as u32;
    // F1_GUEST_PRE_SEAL
    STATE.store(SEALED, Ordering::Release);
    true
}

#[cfg(not(test))]
fn terminal(success: bool, capture: [u32; 16]) -> ! {
    use crate::io::serial::puts;
    const HEX: [&str; 16] = [
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f",
    ];
    puts(if success {
        "F1OWNER PASS cpl=0 terminal=halt "
    } else {
        "F1OWNER FAIL terminal=halt "
    });
    for value in capture {
        for digit in (0..8).rev() {
            puts(HEX[((value >> (digit * 4)) & 15) as usize]);
        }
        puts(" ");
    }
    puts("\nF1OWNER TERMINAL\n");
    loop {
        unsafe {
            core::arch::asm!("cli", "hlt", options(nomem, nostack));
        }
    }
}

/// Only dedicated main-context opt-in invocation. Ordinary boot never calls it.
/// CLI remains effective permanently; no allocation, formatting or destruction
/// survives into terminal. Production exports no returning preparation API.
#[cfg(not(test))]
pub(in crate::memory) fn run() -> ! {
    unsafe {
        core::arch::asm!("cli", options(nomem, nostack));
    }
    if !try_admit() {
        terminal(false, [0; 16]);
    }
    let (success, capture) = {
        let mut retained = OWNER.lock();
        let map = crate::memory::PAGE_MAP.lock();
        let mut frames = crate::memory::FRAME_ALLOC.lock();
        let success = match map.as_ref() {
            Some(pm) if crate::memory::PAGING_ENABLED.load(Ordering::Acquire) => {
                prepare_locked(&mut retained, pm, &mut frames)
            }
            _ => close_failure(&mut retained, &frames, 1),
        };
        (success, retained.capture)
    };
    STATE.store(TERMINAL, Ordering::Release);
    // F1_GUEST_POST_UNLOCK_PROBES
    terminal(success, capture)
}

#[cfg(test)]
#[path = "retained_owner_policy_tests.rs"]
pub(super) mod tests;

#[cfg(test)]
pub(super) fn seal_for_test(pm: &mut PageMap, fa: &mut FrameAllocator) -> bool {
    if !try_admit() {
        return false;
    }
    if !enable_paging(pm) {
        return close_failure(&mut OWNER.lock(), fa, 1);
    }
    *MODEL_CPU.lock() = CpuState {
        cr0: 0x80010000,
        cr3: pm.directory as u32,
        cr4: 0,
        cs: 8,
    };
    prepare_locked(&mut OWNER.lock(), pm, fa)
}
