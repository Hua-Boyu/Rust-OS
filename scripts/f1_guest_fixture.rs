//! COPIED-GUEST ONLY. Canonical owner bodies are not replaced.
use super::*;
use crate::memory::{FRAME_ALLOC, PAGE_MAP};

struct Fixture {
    alternate: Option<PageMap>,
    probe: Option<frame::FrameLease>,
}
static FIXTURE: SpinMutex<Fixture> = SpinMutex::new(Fixture {
    alternate: None,
    probe: None,
});
// signature, case, active dir, alt dir, fixture frames, baseline free/allocated,
// payload, sentinel, acquired, outcome, probe mask, mode-valid, alt-domain,
// original probe PTE, original probe PDE. Host reads physical bytes while stopped.
#[unsafe(no_mangle)]
static mut F1_GUEST_INVENTORY: [u32; 16] = [0; 16];
const CASE: u32 = F1_CASE_PLACEHOLDER;

macro_rules! checkpoint {
    ($name:literal) => {
        unsafe {
            core::arch::asm!(
                concat!(".global f1_", $name),
                concat!(".set f1_", $name, ", ."),
                "nop",
                options(nostack)
            );
        }
    };
}

#[inline(never)]
pub(super) fn pre_seal(owner: &RetainedOwner) {
    unsafe {
        F1_GUEST_INVENTORY[7] = owner.capture[8];
        F1_GUEST_INVENTORY[8] = owner.capture[9];
        F1_GUEST_INVENTORY[9] = owner.capture[1];
        F1_GUEST_INVENTORY[10] = owner.capture[0];
    }
    checkpoint!("pre_seal");
}

fn fail() -> ! {
    crate::io::serial::puts("F1OWNER FIXTURE FAIL\n");
    loop {
        unsafe {
            core::arch::asm!("cli", "hlt", options(nomem, nostack));
        }
    }
}

pub(crate) fn setup() {
    unsafe {
        core::arch::asm!("cli", options(nomem, nostack));
    }
    let mut tables = Vec::new();
    let mut bitmap = Vec::new();
    if tables.try_reserve_exact(PAGE_DIR_ENTRIES).is_err()
        || bitmap.try_reserve_exact(PAYLOAD_BITMAP_BYTES).is_err()
    {
        fail();
    }
    tables.resize(PAGE_DIR_ENTRIES, 0);
    bitmap.resize(PAYLOAD_BITMAP_BYTES, 0);
    let mut pins = Vec::new();
    let valid = {
        let mut fixture = FIXTURE.lock();
        let mut map = PAGE_MAP.lock();
        let mut frames = FRAME_ALLOC.lock();
        let mut okay = false;
        if let Some(pm) = map.as_mut() {
            let before = capacity(&frames);
            let accessible = identity(pm, &frames, hardware())
                && pm.window_end <= 512 * 1024 * 1024
                && (0..frame::MAX_FRAMES).all(|index| {
                    let address = index as u64 * PAGE_SIZE as u64;
                    !frames.is_free(address)
                        || (pm.translate(address) == Some(address)
                            && pm
                                .permissions(address)
                                .is_some_and(|p| p.present && p.writable && !p.user))
                });
            if accessible {
                fixture.alternate = build_identity_map_with_backing_in_place(
                    &mut frames,
                    pm.window_end,
                    &mut tables,
                    &mut pins,
                    &mut bitmap,
                );
                if let Some(alternate) = fixture.alternate.as_mut() {
                    okay = alternate.retain_for_publication()
                        && alternate.domain == pm.domain
                        && alternate.directory != pm.directory
                        && alternate.stats.page_tables <= 128
                        && frames.structure_pinned(alternate.directory)
                        && alternate
                            .tables
                            .iter()
                            .all(|&p| p == 0 || frames.structure_pinned(p));
                }
                if okay {
                    fixture.probe = frames.allocate_owned();
                    okay = fixture.probe.as_ref().is_some_and(|probe| {
                        pm.map_owned(&mut frames, GROWTH_START as u64, probe, &KERNEL_PERMS)
                    });
                }
                if okay {
                    let after = capacity(&frames);
                    let alternate = fixture.alternate.as_ref().unwrap();
                    okay = before[0] - after[0] == alternate.stats.page_tables + 2
                        && before[1] + alternate.stats.page_tables + 2 == after[1]
                        && pm.stats.page_tables
                            == (pm.window_end as usize).div_ceil(4 * 1024 * 1024)
                        && identity(pm, &frames, hardware());
                    unsafe {
                        F1_GUEST_INVENTORY = [
                            0xf101b3,
                            CASE,
                            pm.directory as u32,
                            alternate.directory as u32,
                            (before[0] - after[0]) as u32,
                            after[0] as u32,
                            after[1] as u32,
                            0,
                            0,
                            0,
                            0,
                            0,
                            okay as u32,
                            alternate.domain,
                            pm.entry(GROWTH_START as u64).unwrap_or(0),
                            read_entry(pm.directory, page_dir_index(GROWTH_START as u64)),
                        ];
                    }
                }
            }
        }
        okay
    };
    // Failed/unused backing drops only after ALL guards. Rooted backing stays.
    drop(tables);
    drop(bitmap);
    drop(pins);
    if !valid {
        fail();
    }
}

#[inline(never)]
pub(super) fn probes(success: bool) -> bool {
    let mut mask = 0u32;
    let expected = if CASE == 0 {
        2
    } else if CASE == 1 {
        0
    } else if CASE == 4 {
        2
    } else {
        1
    };
    {
        let mut fixture = FIXTURE.lock();
        let retained = OWNER.lock();
        let Fixture { alternate, probe } = &mut *fixture;
        let mut map = PAGE_MAP.lock();
        let mut frames = FRAME_ALLOC.lock();
        let pm = map.as_mut().unwrap();
        let payload = retained.payload.as_ref();
        let sentinel = retained.sentinel.as_ref();
        let acquired = payload.is_some() as u32 + sentinel.is_some() as u32;
        let before = capacity(&frames);
        let active_cpu = hardware();
        let probe = probe.as_ref().unwrap();
        let address = probe.frame_addr();
        let probe_entry = pm.entry(GROWTH_START as u64);
        let valid_slots = acquired == expected
            && retained.capture[1] == expected
            && payload.is_none_or(|p| {
                frames.owns_live_lease(p)
                    && !frames.runtime_pinned(p.frame_addr())
                    && !frames.structure_pinned(p.frame_addr())
            })
            && sentinel.is_none_or(|p| frames.owns_live_lease(p))
            && frames.owns_live_lease(probe)
            && frames.runtime_pinned(address)
            && hardware().cr3 as u64 == pm.directory;
        unsafe {
            F1_GUEST_INVENTORY[7] = payload.map_or(0, |p| p.frame_addr() as u32);
            F1_GUEST_INVENTORY[8] = sentinel.map_or(0, |p| p.frame_addr() as u32);
            F1_GUEST_INVENTORY[9] = acquired;
            F1_GUEST_INVENTORY[10] = retained.capture[0];
            F1_GUEST_INVENTORY[12] = valid_slots as u32;
        }
        checkpoint!("pre_probe");
        checkpoint!("before_admit");
        if !try_admit() {
            mask |= 1;
        }
        checkpoint!("after_admit");
        checkpoint!("before_release");
        let release = payload.unwrap_or(probe);
        if !frames.release_frame(release.duplicate_for_guest()) && frames.owns_live_lease(release) {
            mask |= 2;
        }
        checkpoint!("after_release");
        checkpoint!("before_unmap");
        if !pm.unmap_owned(&mut frames, GROWTH_START as u64, probe)
            && pm.entry(GROWTH_START as u64) == probe_entry
            && frames.runtime_pinned(address)
        {
            mask |= 4;
        }
        checkpoint!("after_unmap");
        checkpoint!("before_matrix");
        let mut matrix = frames.allocate_owned().is_none()
            && frames.allocate().is_none()
            && frames
                .claim_growth_frame((GROWTH_START + PAGE_SIZE) as u64)
                .is_none()
            && !frames.free(release.frame_addr())
            && !frames.init(&[], 0, 0, 0)
            && !frames.init_with_reservations(&[], 0, 0, 0, &[(2, 1)])
            && !pm.map_owned(
                &mut frames,
                (GROWTH_START + PAGE_SIZE) as u64,
                release,
                &KERNEL_PERMS,
            )
            && !pm.map_growth_claim(&mut frames, (GROWTH_START + PAGE_SIZE) as u64);
        for pinned in [false, true] {
            matrix &= !frames.set_runtime_pin(address, pinned)
                && !frames.set_structure_pin(pm.directory, pinned);
        }
        let alternate = alternate.as_mut().unwrap();
        matrix &= !alternate.retain_for_publication()
            && !alternate.release_unpublished_frames(&mut frames);
        if matrix && capacity(&frames) == before {
            mask |= 8;
        }
        checkpoint!("after_matrix");
        checkpoint!("before_enable");
        if !enable_paging(alternate)
            && hardware() == active_cpu
            && alternate.retained
            && alternate.domain == pm.domain
        {
            mask |= 16;
        }
        checkpoint!("after_enable");
        checkpoint!("before_reload");
        if !flush_tlb(alternate) && hardware() == active_cpu && alternate.directory != pm.directory
        {
            mask |= 32;
        }
        checkpoint!("after_reload");
        if valid_slots && capacity(&frames) == before {
            mask |= 64;
        }
        unsafe {
            F1_GUEST_INVENTORY[11] = mask;
        }
    }
    checkpoint!("post_probes");
    if mask == 127 {
        crate::io::serial::puts("F1OWNER PROBES PASS\n");
    } else {
        crate::io::serial::puts("F1OWNER PROBES FAIL\n");
    }
    if CASE != 0 && mask == 127 {
        crate::io::serial::puts("F1OWNER EXPECTED_REFUSAL\n");
    }
    success && mask == 127
}
