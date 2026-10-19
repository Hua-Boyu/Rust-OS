//! Ordinary admission requires live borrowed authority, not a copied address.
use super::*;
use crate::multiboot::MmapEntry;

#[test]
fn numeric_map_production_api_rejects_numeric_and_private_core_calls() {
    use std::{fs, path::Path, process::Command, time::SystemTime};
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    let version = Command::new("rustc")
        .args(["+nightly", "-vV"])
        .output()
        .expect("rustc host discovery");
    assert!(version.status.success());
    let version = String::from_utf8(version.stdout).unwrap();
    let host = version
        .lines()
        .find_map(|s| s.strip_prefix("host: "))
        .unwrap();
    let nonce = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let output_dir = std::env::temp_dir().join(format!(
        "rosti_numeric_api_{}_{}",
        std::process::id(),
        nonce
    ));
    fs::create_dir(&output_dir).expect("exclusive task-owned compile output");
    for (mode, expected) in [
        ("base_control", None),
        ("owned_control", None),
        ("raw_numeric", Some("E0599")),
        ("private_core", Some("E0624")),
        ("numeric_owned", Some("E0308")),
    ] {
        let artifact = output_dir.join(format!("{mode}.rmeta"));
        let result = Command::new("rustc")
            .current_dir(root.parent().unwrap())
            .args([
                "+nightly",
                "--edition=2024",
                "--crate-type=lib",
                "--emit=metadata",
                "--error-format=json",
                "--target",
                host,
                "--cfg",
                mode,
            ])
            .arg(root.join("scripts/numeric_map_api_probe.rs"))
            .arg("-o")
            .arg(&artifact)
            .output()
            .expect("production-cfg rustc probe");
        let stderr = String::from_utf8(result.stderr).unwrap();
        if let Some(code) = expected {
            assert_eq!(result.status.code(), Some(1), "{mode}: {stderr}");
            let diagnostic = format!("\"code\":{{\"code\":\"{code}\"");
            assert_eq!(stderr.matches(&diagnostic).count(), 1, "{mode}: {stderr}");
            assert_eq!(
                stderr.matches("\"code\":{\"code\":").count(),
                1,
                "unexpected compiler error: {stderr}"
            );
            assert!(!artifact.exists(), "refused probe emitted metadata");
        } else {
            assert_eq!(result.status.code(), Some(0), "{mode}: {stderr}");
            assert!(artifact.is_file());
        }
    }
    fs::remove_dir_all(&output_dir).expect("owned probe output cleanup");
}

fn fixture() -> (FrameAllocator, PageMap) {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x1000000,
            type_: 1
        }],
        0x90000,
        0xa0000,
        0xb0000,
    ));
    let pm = build_identity_map(&mut fa, 0x1010000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    (fa, pm)
}

// Fully owned scalar/bitmap/entry snapshots, with diagnostic rejects excluded.
fn state(fa: &FrameAllocator, pm: &PageMap) -> (Vec<usize>, Vec<u64>, Vec<u32>, Vec<u8>) {
    let f = fa.stats();
    let p = pm.stats();
    let counters = alloc::vec![
        f.total_frames,
        f.free_frames,
        f.allocated_frames,
        f.reserved_frames,
        f.invalid_frees,
        f.double_frees,
        f.bitmap_frames,
        p.page_tables,
        p.mapped_frames,
        p.maps,
        p.unmaps,
        p.unmap_rejects,
        p.tlb_invalidation
    ];
    let mut pins = Vec::new();
    for index in 0..frame::MAX_FRAMES {
        let addr = (index * PAGE_SIZE) as u64;
        if fa.runtime_pinned(addr) {
            pins.push(addr);
        }
        if fa.structure_pinned(addr) {
            pins.push(addr | 1);
        }
    }
    let mut entries = Vec::new();
    for index in 0..PAGE_DIR_ENTRIES {
        entries.push(read_entry(pm.directory, index));
    }
    for &table in &pm.tables {
        if table != 0 {
            for index in 0..PAGE_TABLE_ENTRIES {
                entries.push(read_entry(table, index));
            }
        }
    }
    (counters, pins, entries, pm.payload_bitmap.clone())
}

#[test]
fn numeric_map_live_lease_borrow_pins_until_unmap() {
    let (mut fa, mut pm) = fixture();
    let lease = fa.allocate_owned().unwrap();
    let addr = lease.frame_addr();
    let slot = GROWTH_START as u64;
    assert!(fa.is_live_allocation(addr));
    assert!(!fa.runtime_pinned(addr));
    assert!(pm.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert_eq!(lease.frame_addr(), addr);
    assert_eq!(pm.translate(slot), Some(addr));
    assert_ne!(pm.entry(slot).unwrap() & ENTRY_RUNTIME_PAYLOAD, 0);
    assert!(fa.runtime_pinned(addr));
    assert!(payload_bit(&pm.payload_bitmap, addr));
    assert!(!fa.release_frame(lease.duplicate_for_test()));
    assert!(pm.unmap(&mut fa, slot));
    assert!(!fa.runtime_pinned(addr));
    assert!(!payload_bit(&pm.payload_bitmap, addr));
    assert!(fa.release_frame(lease));
    assert!(pm.release_unpublished_frames(&mut fa));
}

#[test]
fn numeric_map_stale_reused_identity_is_state_atomic() {
    let (mut fa, mut pm) = fixture();
    let old = fa.allocate_owned().unwrap();
    let stale = old.duplicate_for_test();
    assert!(fa.release_frame(old));
    let current = fa.allocate_owned().unwrap();
    assert_eq!(stale.frame_addr(), current.frame_addr());
    let before = state(&fa, &pm);
    let rejects = pm.stats().map_rejects;
    assert!(!pm.map_owned(&mut fa, GROWTH_START as u64, &stale, &KERNEL_PERMS));
    assert_eq!(state(&fa, &pm), before);
    assert_eq!(pm.stats().map_rejects, rejects + 1);
    assert!(pm.map_owned(&mut fa, GROWTH_START as u64, &current, &KERNEL_PERMS));
    assert!(pm.unmap(&mut fa, GROWTH_START as u64));
    assert!(fa.release_frame(current));
    // Audited raw release can invalidate an otherwise retained real lease.
    // Both raw and owned reuse must authenticate a new allocation identity.
    for raw_reuse in [true, false] {
        let retained = fa.allocate_owned().unwrap();
        let addr = retained.frame_addr();
        assert!(fa.free(addr));
        if raw_reuse {
            assert_eq!(fa.allocate(), Some(addr));
            let before = state(&fa, &pm);
            assert!(!pm.map_owned(&mut fa, GROWTH_START as u64, &retained, &KERNEL_PERMS));
            assert_eq!(state(&fa, &pm), before);
            assert!(fa.free(addr));
        } else {
            let owner = fa.allocate_owned().unwrap();
            assert_eq!(owner.frame_addr(), addr);
            let before = state(&fa, &pm);
            assert!(!pm.map_owned(&mut fa, GROWTH_START as u64, &retained, &KERNEL_PERMS));
            assert_eq!(state(&fa, &pm), before);
            assert!(pm.map_owned(&mut fa, GROWTH_START as u64, &owner, &KERNEL_PERMS));
            assert!(pm.unmap(&mut fa, GROWTH_START as u64));
            assert!(fa.release_frame(owner));
        }
    }
    assert!(pm.release_unpublished_frames(&mut fa));
}

#[test]
fn numeric_map_foreign_domain_is_state_atomic() {
    let (mut fa, mut pm) = fixture();
    // Avoid a second large by-value fixture return on Windows test stacks.
    let mut foreign = FrameAllocator::new();
    assert!(foreign.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 0x1000000,
            type_: 1,
        }],
        0x90000,
        0xa0000,
        0xb0000,
    ));
    // Match address and allocation ordinal in both allocators: refusal must
    // authenticate the domain, not accidentally hit a structure-role denial.
    let mut held = Vec::new();
    for _ in 0..fa.stats().allocated_frames {
        held.push(foreign.allocate().unwrap());
    }
    let owner = fa.allocate_owned().unwrap();
    let lease = foreign.allocate_owned().unwrap();
    assert_eq!(lease.frame_addr(), owner.frame_addr());
    let before = state(&fa, &pm);
    let foreign_before = state(&foreign, &pm);
    let rejects = pm.stats().map_rejects;
    assert!(!pm.map_owned(&mut fa, GROWTH_START as u64, &lease, &KERNEL_PERMS));
    assert_eq!(state(&fa, &pm), before);
    assert_eq!(state(&foreign, &pm), foreign_before);
    assert_eq!(pm.stats().map_rejects, rejects + 1);
    assert!(!pm.map_owned(&mut foreign, GROWTH_START as u64, &lease, &KERNEL_PERMS));
    assert_eq!(state(&fa, &pm), before);
    assert_eq!(state(&foreign, &pm), foreign_before);
    assert!(foreign.release_frame(lease));
    for addr in held {
        assert!(foreign.free(addr));
    }
    assert_eq!(foreign.stats().allocated_frames, 0);
    assert!(fa.release_frame(owner));
    assert!(pm.release_unpublished_frames(&mut fa));
}

#[test]
fn numeric_map_released_identity_is_state_atomic() {
    let (mut fa, mut pm) = fixture();
    let lease = fa.allocate_owned().unwrap();
    let stale = lease.duplicate_for_test();
    assert!(fa.release_frame(lease));
    let before = state(&fa, &pm);
    assert!(!pm.map_owned(&mut fa, GROWTH_START as u64, &stale, &KERNEL_PERMS));
    assert_eq!(state(&fa, &pm), before);
    assert!(pm.release_unpublished_frames(&mut fa));
}

#[test]
fn numeric_map_refusal_retains_lease_for_conflict_and_permissions() {
    let (mut fa, mut pm) = fixture();
    let first = fa.allocate_owned().unwrap();
    let second = fa.allocate_owned().unwrap();
    let slot = GROWTH_START as u64;
    assert!(pm.map_owned(&mut fa, slot, &first, &KERNEL_PERMS));
    for (dest, perms) in [
        (slot, KERNEL_PERMS),
        (
            slot + PAGE_SIZE as u64,
            PagePerms {
                user: true,
                ..KERNEL_PERMS
            },
        ),
        (
            slot + PAGE_SIZE as u64,
            PagePerms {
                present: false,
                ..KERNEL_PERMS
            },
        ),
        (0, KERNEL_PERMS),
    ] {
        let before = state(&fa, &pm);
        let rejects = pm.stats().map_rejects;
        assert!(!pm.map_owned(&mut fa, dest, &second, &perms));
        assert_eq!(state(&fa, &pm), before);
        assert_eq!(pm.stats().map_rejects, rejects + 1);
        assert!(fa.is_live_allocation(second.frame_addr()));
    }
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.release_frame(first));
    assert!(fa.release_frame(second));
    assert!(pm.release_unpublished_frames(&mut fa));
}

#[test]
fn numeric_map_exhaustion_retains_lease_and_allows_retry() {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
        &[MmapEntry {
            size: 20,
            base_addr: 0x10000,
            length: 4 * PAGE_SIZE as u64,
            type_: 1
        }],
        0x90000,
        0xa0000,
        0xb0000
    ));
    let mut pm = build_identity_map(&mut fa, 0x80000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let lease = fa.allocate_owned().unwrap();
    let held = fa.allocate_owned().unwrap();
    let before = state(&fa, &pm);
    let slot = GROWTH_START as u64;
    assert!(!pm.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert_eq!(state(&fa, &pm), before);
    assert!(fa.release_frame(held));
    assert!(pm.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.release_frame(lease));
    assert!(pm.release_unpublished_frames(&mut fa));
    assert_eq!(fa.stats().allocated_frames, 0);
    assert_eq!(fa.stats().free_frames, 4);
}

#[test]
fn numeric_map_existing_runtime_pin_refuses_second_map() {
    let (mut fa, mut a) = fixture();
    let mut b = build_identity_map(&mut fa, 0x1010000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    let lease = fa.allocate_owned().unwrap();
    let slot = GROWTH_START as u64;
    assert!(a.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    let before = state(&fa, &b);
    assert!(!b.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert_eq!(state(&fa, &b), before);
    assert!(a.unmap(&mut fa, slot));
    assert!(b.map_owned(&mut fa, slot, &lease, &KERNEL_PERMS));
    assert!(b.unmap(&mut fa, slot));
    assert!(fa.release_frame(lease));
    assert!(a.release_unpublished_frames(&mut fa));
    assert!(b.release_unpublished_frames(&mut fa));
}

#[test]
fn numeric_map_growth_specialization_cannot_admit_ordinary_backing() {
    let (mut fa, mut pm) = fixture();
    let lease = fa.allocate_owned().unwrap();
    let before = state(&fa, &pm);
    let slot = GROWTH_START as u64;
    for invalid in [
        lease.frame_addr(),
        slot,
        slot + 1,
        GROWTH_END as u64,
        u64::MAX,
    ] {
        assert!(!pm.map_growth_claim(&mut fa, invalid));
        assert_eq!(state(&fa, &pm), before);
    }
    assert_eq!(fa.claim_growth_frame(slot), Some(slot));
    assert!(pm.map_growth_claim(&mut fa, slot));
    assert_eq!(pm.translate(slot), Some(slot));
    let mapped = state(&fa, &pm);
    assert!(!pm.map_growth_claim(&mut fa, slot));
    assert_eq!(state(&fa, &pm), mapped);
    assert!(pm.unmap(&mut fa, slot));
    assert!(fa.free(slot));
    let released = state(&fa, &pm);
    assert!(!pm.map_growth_claim(&mut fa, slot));
    assert_eq!(state(&fa, &pm), released);
    assert!(fa.release_frame(lease));
    assert!(pm.release_unpublished_frames(&mut fa));
}
