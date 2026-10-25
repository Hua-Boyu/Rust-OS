//! Finite, cooperative single-vCPU Ring-0 terminal authority.
//! No reset, shared ownership, teardown or CPL3 entry. F4 alone publishes its
//! finite owned USER arena during fresh Preparing, before the joint seal.
use super::*;
use crate::utils::mutex::SpinMutex;
use core::sync::atomic::{AtomicU8, Ordering};

const DORMANT: u8 = 0;
pub(super) const PREPARING: u8 = 1;
pub(super) const SEALED: u8 = 2;
pub(super) const TERMINAL: u8 = 3;
pub(super) static STATE: AtomicU8 = AtomicU8::new(DORMANT);
// (entire future policy maximum, maximum acquired in this F1 version).
const MANIFEST: [(u8, u8); 6] = [(1, 1), (1, 1), (1, 0), (4, 0), (4, 0), (1, 0)];

pub(super) struct RetainedOwner {
    pub(super) payload: Option<frame::FrameLease>,
    pub(super) sentinel: Option<frame::FrameLease>,
    pub(super) transition: [Option<frame::FrameLease>; 4],
    pub(super) emergency: [Option<frame::FrameLease>; 4],
    pub(super) user_stack: Option<frame::FrameLease>,
    pub(super) arena_table: Option<frame::FrameLease>,
    // outcome, acquired, code, stack, table, PDE, codePTE, stackPTE,
    // CR3, CR4, EFLAGS, free-before-F4, free-after, allocated-after, ready, seal.
    pub(super) arena_capture: [u32; 16],
    directory: u64,
    allocator_domain: u32,
    window_end: u64,
    table_count: usize,
    mapped_count: usize,
    capacity_before: [usize; 3],
    capacity_after: [usize; 3],
    pub(super) future_ranges: [[u32; 4]; 3],
    pub(super) capture: [u32; 16],
}

impl RetainedOwner {
    const fn new() -> Self {
        Self {
            payload: None,
            sentinel: None,
            transition: [const { None }; 4],
            emergency: [const { None }; 4],
            user_stack: None,
            arena_table: None,
            arena_capture: [0; 16],
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

pub(super) static OWNER: SpinMutex<RetainedOwner> = SpinMutex::new(RetainedOwner::new());
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

pub(super) fn try_admit() -> bool {
    STATE
        .compare_exchange(DORMANT, PREPARING, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) struct CpuState {
    pub(super) cr0: u32,
    pub(super) cr3: u32,
    pub(super) cr4: u32,
    pub(super) cs: u16,
}

#[cfg(test)]
pub(super) static MODEL_CPU: SpinMutex<CpuState> = SpinMutex::new(CpuState {
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

pub(super) fn capacity(fa: &FrameAllocator) -> [usize; 3] {
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
    prepare_stage(owner, pm, fa, true)
}

fn prepare_stage(
    owner: &mut RetainedOwner,
    pm: &PageMap,
    fa: &mut FrameAllocator,
    seal: bool,
) -> bool {
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
    if seal {
        STATE.store(SEALED, Ordering::Release);
    }
    true
}

pub(super) fn prepare_f3_locked(
    owner: &mut RetainedOwner,
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
) -> bool {
    if !prepare_stage(owner, pm, fa, false) {
        return false;
    }
    for i in 0..8 {
        let slot = if i < 4 {
            &mut owner.transition[i]
        } else {
            &mut owner.emergency[i - 4]
        };
        *slot = fa.allocate_owned();
        let Some(lease) = slot.as_ref() else {
            return close_failure(owner, fa, 7);
        };
        owner.capture[1] += 1;
        if !valid_lease(pm, fa, lease) {
            return close_failure(owner, fa, 8);
        }
    }
    if !pm.install_privileged_stacks(fa, &owner.transition, &owner.emergency) {
        return close_failure(owner, fa, 9);
    }
    use super::privileged::*;
    owner.future_ranges[1] = [TRANSITION_BASE, TRANSITION_TOP, TRANSITION_GUARD, 1];
    owner.future_ranges[2] = [EMERGENCY_BASE, EMERGENCY_TOP, EMERGENCY_GUARD, 1];
    owner.capacity_after = capacity(fa);
    owner.capture[12] = owner.capacity_after[0] as u32;
    owner.capture[13] = owner.capacity_after[1] as u32;
    owner.capture[15] = PREPARING as u32;
    true
}

fn f4_flags() -> u32 {
    #[cfg(test)]
    return 2;
    #[cfg(not(test))]
    unsafe {
        let flags: u32;
        core::arch::asm!("pushfd", "pop {0:e}", out(reg) flags, options(preserves_flags));
        flags
    }
}

fn f4_profile(pm: &PageMap, fa: &FrameAllocator) -> bool {
    let cpu = hardware();
    identity(pm, fa, cpu)
        && cpu.cr0 & 1 != 0
        && cpu.cr4 & ((1 << 23) | (1 << 21)) == 0
        && f4_flags() & ((1 << 17) | (1 << 14) | (3 << 12) | (1 << 9)) == 0
}

pub(super) fn prepare_f4_locked(
    owner: &mut RetainedOwner,
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
) -> bool {
    if STATE.load(Ordering::Acquire) != PREPARING
        || !f4_profile(pm, fa)
        || !user_arena::preflight_map(pm, fa, user_arena::LAYOUT)
    {
        return close_failure(owner, fa, 12);
    }
    if !prepare_f3_locked(owner, pm, fa) {
        return false;
    }
    prepare_arena_locked(owner, pm, fa)
}

pub(super) fn prepare_arena_locked(
    owner: &mut RetainedOwner,
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
) -> bool {
    prepare_arena_image_locked(owner, pm, fa, user_arena::Image::F4)
}

pub(super) fn admit_f5(scenario: u32) -> bool {
    f5_contract::f5_admissible(scenario) && try_admit()
}

pub(super) fn prepare_f5_locked(
    owner: &mut RetainedOwner,
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
    scenario: u32,
) -> bool {
    // Defense-in-depth refusal before the first owner/map/frame mutation.
    if !f5_contract::f5_admissible(scenario) {
        return false;
    }
    if STATE.load(Ordering::Acquire) != PREPARING
        || !f4_profile(pm, fa)
        || !user_arena::preflight_map(pm, fa, user_arena::LAYOUT)
    {
        return close_failure(owner, fa, 20);
    }
    if !prepare_f3_locked(owner, pm, fa) {
        return false;
    }
    prepare_arena_image_locked(owner, pm, fa, user_arena::Image::F5)
}

/// Memory/ownership half only: GDT/TSS CPU validation remains separate.
/// No host success here purports to execute LGDT, LTR or IRETD.
pub(super) fn seal_f5_locked(owner: &mut RetainedOwner, pm: &PageMap, fa: &FrameAllocator) -> bool {
    user_arena::valid_f5_image(owner) && seal_arena_locked(owner, pm, fa)
}

fn seal_arena_locked(owner: &mut RetainedOwner, pm: &PageMap, fa: &FrameAllocator) -> bool {
    if STATE.load(Ordering::Acquire) != PREPARING
        || !f4_profile(pm, fa)
        || !user_arena::valid(pm, fa, owner)
    {
        return false;
    }
    owner.arena_capture[15] = SEALED as u32;
    STATE.store(SEALED, Ordering::Release);
    true
}

fn prepare_arena_image_locked(
    owner: &mut RetainedOwner,
    pm: &mut PageMap,
    fa: &mut FrameAllocator,
    image: user_arena::Image,
) -> bool {
    if STATE.load(Ordering::Acquire) != PREPARING
        || owner.capture[1] != 10
        || owner.user_stack.is_some()
        || owner.arena_table.is_some()
        || !f4_profile(pm, fa)
        || !user_arena::preflight_map(pm, fa, user_arena::LAYOUT)
    {
        return close_failure(owner, fa, 18);
    }
    owner.arena_capture[11] = capacity(fa)[0] as u32;
    owner.user_stack = fa.allocate_owned();
    if owner.user_stack.is_none() {
        return close_failure(owner, fa, 13);
    }
    owner.capture[1] += 1;
    // F4_DENY_TABLE: no fallback or release of the retained stack lease.
    if owner
        .user_stack
        .as_ref()
        .is_none_or(|l| !user_arena::new_frame(pm, fa, l))
    {
        return close_failure(owner, fa, 19);
    }
    owner.arena_table = fa.allocate_owned();
    if owner.arena_table.is_none() {
        return close_failure(owner, fa, 14);
    }
    owner.capture[1] += 1;
    let (Some(code), Some(stack), Some(table)) = (
        owner.payload.as_ref().map(frame::FrameLease::frame_addr),
        owner.user_stack.as_ref().map(frame::FrameLease::frame_addr),
        owner
            .arena_table
            .as_ref()
            .map(frame::FrameLease::frame_addr),
    ) else {
        return close_failure(owner, fa, 15);
    };
    let installed = f4_profile(pm, fa)
        && match image {
            user_arena::Image::F4 => user_arena::install(pm, fa, owner, user_arena::LAYOUT),
            user_arena::Image::F5 => user_arena::install_f5(pm, fa, owner, user_arena::LAYOUT),
        };
    if !installed {
        return close_failure(owner, fa, 15);
    }
    owner.future_ranges[0] = [
        user_arena::START as u32,
        user_arena::END as u32,
        user_arena::GUARD as u32,
        1,
    ];
    let after = capacity(fa);
    owner.capacity_after = after;
    owner.arena_capture = [
        0,
        owner.capture[1],
        code as u32,
        stack as u32,
        table as u32,
        read_entry(pm.directory, 256),
        pm.entry(user_arena::START).unwrap_or(0),
        pm.entry(user_arena::STACK).unwrap_or(0),
        hardware().cr3,
        hardware().cr4,
        f4_flags(),
        owner.arena_capture[11],
        after[0] as u32,
        after[1] as u32,
        1,
        PREPARING as u32,
    ];
    true
}

#[cfg(all(not(test), target_os = "none"))]
pub(in crate::memory) fn run_user_arena() -> ! {
    unsafe {
        core::arch::asm!("cli", options(nomem, nostack));
    }
    if !try_admit() {
        f4_terminal(false);
    }
    let directory = {
        let mut retained = OWNER.lock();
        let mut map = crate::memory::PAGE_MAP.lock();
        let mut frames = crate::memory::FRAME_ALLOC.lock();
        match map.as_mut() {
            Some(pm) if crate::memory::PAGING_ENABLED.load(Ordering::Acquire) => {
                if prepare_f4_locked(&mut retained, pm, &mut frames) {
                    Some(pm.directory as u32)
                } else {
                    None
                }
            }
            _ => {
                close_failure(&mut retained, &frames, 16);
                None
            }
        }
    };
    let Some(directory) = directory else {
        f4_terminal(false);
    };
    if !crate::gdt_tss::install(directory) {
        f4_terminal(false);
    }
    let valid = {
        let mut retained = OWNER.lock();
        let map = crate::memory::PAGE_MAP.lock();
        let frames = crate::memory::FRAME_ALLOC.lock();
        let valid = map
            .as_ref()
            .is_some_and(|pm| seal_arena_locked(&mut retained, pm, &frames));
        if !valid {
            close_failure(&mut retained, &frames, 17);
        }
        valid
    };
    if !valid || !crate::gdt_tss::verify(directory) {
        f4_terminal(false);
    }
    f4_terminal(true)
}

#[cfg(all(not(test), target_os = "none"))]
#[inline(never)]
fn f4_terminal(success: bool) -> ! {
    // SAFETY: STATE.as_ptr() exposes the live AtomicU8's UnsafeCell without
    // creating a non-atomic reference. This x86 byte MOV is an atomic store,
    // not a Rust non-atomic access: byte stores cannot tear. x86 store ordering
    // plus asm's default read/write memory clobber supplies Release ordering
    // with the unchanged Acquire observers. Do not add nomem/readonly/pure:
    // prior retained-owner writes must precede this store and serial output
    // must follow it. No registers/flags/stack are changed except the memory
    // operand; no generic ordering dispatcher or panic helper is reachable.
    unsafe {
        core::arch::asm!(
            "mov byte ptr [{state}], {terminal}",
            state = in(reg) STATE.as_ptr(),
            terminal = const TERMINAL,
            options(nostack, preserves_flags)
        );
    }
    f4_terminal_serial(if success {
        b"F4 USER arena PASS Ring0 terminal\n"
    } else {
        b"F4 USER arena FAIL Ring0 terminal\n"
    });
    loop {
        unsafe {
            core::arch::asm!(
                ".global f4_arena_terminal",
                ".set f4_arena_terminal, .",
                "cli",
                "hlt",
                options(nostack)
            );
        }
    }
}

// F4-private equivalent of serial::puts/putc, without emitted iterator/panic
// dependencies. Keep both messages fixed-size; no general string/pointer API.
#[cfg(all(not(test), target_os = "none"))]
#[inline(never)]
fn f4_terminal_serial(message: &'static [u8; 34]) {
    // SAFETY: F4 runs at CPL0, IF0 on the admitted single vCPU; serial was
    // initialized by the existing driver. COM1 THR=0x3f8, LSR=0x3fd, THRE=0x20;
    // byte I/O and the 100000-poll/drop-on-timeout policy match serial::putc.
    // The static 34-byte allocation stays readable throughout. Each iteration
    // reads at most its current byte, then advances once; the final one-past
    // pointer is never dereferenced. No Rust unchecked arithmetic is used.
    // EAX/ECX/EDX and flags are clobbered; pointer/count are private scratch
    // registers. No stack access, calls, DF dependence or indirect branches.
    // Default asm memory effects preserve compiler ordering with publication
    // and the static bytes; do not add pure/nomem/readonly/preserves_flags.
    // IN/OUT execute in program order. At most 34*100000 LSR reads and 34 THR
    // writes; this is an iteration bound, not a wall-clock UART guarantee.
    unsafe {
        core::arch::asm!(
            "2:",
            "mov ecx, 100000",
            "mov dx, 0x3fd",
            "3:",
            "in al, dx",
            "test al, 0x20",
            "jnz 4f",
            "dec ecx",
            "jnz 3b",
            "jmp 5f",
            "4:",
            "mov al, byte ptr [{pointer}]",
            "mov dx, 0x3f8",
            "out dx, al",
            "5:",
            "inc {pointer}",
            "dec {remaining}",
            "jnz 2b",
            pointer = inout(reg) message.as_ptr() => _,
            remaining = inout(reg) 34usize => _,
            out("eax") _,
            out("ecx") _,
            out("edx") _,
            options(nostack)
        );
    }
}

/// F3 extends fresh Preparing only. No returning preparation or unseal API.
#[cfg(all(not(test), target_os = "none"))]
pub(in crate::memory) fn run_gdt_tss() -> ! {
    unsafe {
        core::arch::asm!("cli", options(nomem, nostack));
    }
    if !try_admit() {
        crate::gdt_tss::fail();
    }
    let directory = {
        let mut retained = OWNER.lock();
        let mut map = crate::memory::PAGE_MAP.lock();
        let mut frames = crate::memory::FRAME_ALLOC.lock();
        match map.as_mut() {
            Some(pm) if crate::memory::PAGING_ENABLED.load(Ordering::Acquire) => {
                if prepare_f3_locked(&mut retained, pm, &mut frames) {
                    Some(pm.directory as u32)
                } else {
                    None
                }
            }
            _ => {
                close_failure(&mut retained, &frames, 10);
                None
            }
        }
    };
    let Some(directory) = directory else {
        crate::gdt_tss::fail();
    };
    // Every owner guard is gone. CPU can now reach only retained storage.
    if !crate::gdt_tss::install(directory) {
        STATE.store(TERMINAL, Ordering::Release);
        crate::gdt_tss::fail();
    }
    let valid = {
        let mut retained = OWNER.lock();
        let map = crate::memory::PAGE_MAP.lock();
        let frames = crate::memory::FRAME_ALLOC.lock();
        let valid = map.as_ref().is_some_and(|pm| {
            identity(pm, &frames, hardware())
                && pm.privileged_stacks_valid(&frames, &retained.transition, &retained.emergency)
        });
        if valid {
            retained.capture[15] = SEALED as u32;
            STATE.store(SEALED, Ordering::Release);
        } else {
            close_failure(&mut retained, &frames, 11);
        }
        valid
    };
    if !valid || !crate::gdt_tss::verify(directory) {
        STATE.store(TERMINAL, Ordering::Release);
        crate::gdt_tss::fail();
    }
    STATE.store(TERMINAL, Ordering::Release);
    crate::gdt_tss::ready()
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
