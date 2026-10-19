//! Same-slot unmap authority: a live lease is required to remove a runtime
//! mapping. A stale lease for a replaced same-slot mapping cannot disturb the
//! current owner's PTE, pins, or registry.
use super::*;
use crate::multiboot::MmapEntry;

#[test]
fn unmap_authority_production_api_rejects_numeric_and_private_core_calls() {
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
    let output_dir =
        std::env::temp_dir().join(format!("rosti_unmap_api_{}_{}", std::process::id(), nonce));
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
            .arg(root.join("scripts/unmap_api_probe.rs"))
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

#[test]
fn unmap_authority_stale_lease_cannot_unmap_replacement_mapping() {
    // Case A: A maps F1@V, unmaps, releases; B maps F2@V. Stale Owner A
    // (retained lease_a) must not remove B's current mapping.
    let (mut fa, mut pm) = fixture();
    let slot = GROWTH_START as u64;
    let lease_a = fa.allocate_owned().unwrap();
    assert!(pm.map_owned(&mut fa, slot, &lease_a, &KERNEL_PERMS));
    assert!(pm.unmap_owned(&mut fa, slot, &lease_a));
    let stale_a = lease_a.duplicate_for_test();
    assert!(fa.release_frame(lease_a));
    let lease_b = fa.allocate_owned().unwrap();
    assert!(pm.map_owned(&mut fa, slot, &lease_b, &KERNEL_PERMS));
    let before = state(&fa, &pm);
    let rejects = pm.stats().unmap_rejects;
    // Stale Owner A's lease-authorized unmap must be refused without mutation.
    assert!(!pm.unmap_owned(&mut fa, slot, &stale_a));
    assert_eq!(state(&fa, &pm), before);
    assert_eq!(pm.stats().unmap_rejects, rejects + 1);
    // B's current mapping is intact and B's legitimate unmap still succeeds.
    assert_eq!(pm.translate(slot), Some(lease_b.frame_addr()));
    assert!(fa.runtime_pinned(lease_b.frame_addr()));
    assert!(payload_bit(&pm.payload_bitmap, lease_b.frame_addr()));
    assert!(pm.unmap_owned(&mut fa, slot, &lease_b));
    assert!(fa.release_frame(lease_b));
    assert!(pm.release_unpublished_frames(&mut fa));
}

#[test]
fn unmap_authority_stale_generation_and_foreign_domain_refuse_without_mutation() {
    // Case D: release and reallocate through the legitimate lifecycle; the
    // stale lease cannot unmap the newer generation. Case B: a foreign-domain
    // lease is refused before any structure dereference.
    let (mut fa, mut pm) = fixture();
    let slot = GROWTH_START as u64;
    let old = fa.allocate_owned().unwrap();
    let stale = old.duplicate_for_test();
    assert!(pm.map_owned(&mut fa, slot, &old, &KERNEL_PERMS));
    assert!(pm.unmap_owned(&mut fa, slot, &old));
    assert!(fa.release_frame(old));
    let current = fa.allocate_owned().unwrap();
    assert_eq!(stale.frame_addr(), current.frame_addr());
    assert!(pm.map_owned(&mut fa, slot, &current, &KERNEL_PERMS));
    let before = state(&fa, &pm);
    let rejects = pm.stats().unmap_rejects;
    assert!(!pm.unmap_owned(&mut fa, slot, &stale));
    assert_eq!(state(&fa, &pm), before);
    assert_eq!(pm.stats().unmap_rejects, rejects + 1);
    // Foreign domain: same address, different allocator.
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
    // Match address and allocation ordinal in both allocators: the refusal
    // must authenticate the domain, not accidentally hit another denial.
    while foreign.stats().allocated_frames + 1 < fa.stats().allocated_frames {
        assert!(foreign.allocate().is_some());
    }
    let foreign_lease = foreign.allocate_owned().unwrap();
    assert_eq!(foreign_lease.frame_addr(), current.frame_addr());
    let foreign_before = state(&foreign, &pm);
    let rejects = pm.stats().unmap_rejects;
    assert!(!pm.unmap_owned(&mut foreign, slot, &foreign_lease));
    assert_eq!(state(&fa, &pm), before);
    assert_eq!(state(&foreign, &pm), foreign_before);
    assert_eq!(pm.stats().unmap_rejects, rejects + 1);
    // Legitimate lifecycle remains completable after the refusals.
    assert!(pm.unmap_owned(&mut fa, slot, &current));
    assert!(fa.release_frame(current));
    assert!(foreign.release_frame(foreign_lease));
    assert!(pm.release_unpublished_frames(&mut fa));
}

fn fixture() -> (FrameAllocator, PageMap) {
    let mut fa = FrameAllocator::new();
    assert!(fa.init(
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
    let pm = build_identity_map(&mut fa, 0x1010000, alloc::vec![0; PAGE_DIR_ENTRIES]).unwrap();
    (fa, pm)
}

// Fully owned scalar/bitmap/entry snapshots (diagnostic reject counters excluded
// from equality; asserted separately).
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
        p.tlb_invalidation,
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
