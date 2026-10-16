use super::*;

#[test]
fn review_r1_usable_range_starting_in_growth_still_validates_its_tail() {
    let mut fa = frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 0x10000, 1)], 0x200000, 0x300000, 0x310000);
    let pm = paging::build_identity_map(
        &mut fa,
        paging::GROWTH_END as u64,
        vec![0; paging::PAGE_DIR_ENTRIES],
    )
    .unwrap();
    let entries = [entry(paging::GROWTH_START as u64, 0x800000, 1)];
    assert_eq!(
        paging::first_missing_mapping(&pm, required_region_iter(&entries, 0x200000)),
        Some("usable mmap range"),
        "only growth pages may be omitted, not the later usable tail"
    );
}

fn entry(base_addr: u64, length: u64, type_: u32) -> MmapEntry {
    MmapEntry {
        size: 20,
        base_addr,
        length,
        type_,
    }
}

#[test]
fn review_r1_production_prepare_pins_one_byte_module_and_metadata_partial_tails() {
    // prepare publishes process-global state. Isolate it from other host tests
    // (including B26's boot lifecycle test), even under parallel test execution.
    const CHILD: &str = "RUST_OS_MAPPING_PINS_REVIEW_CHILD";
    if std::env::var_os(CHILD).is_none() {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                concat!(
                    module_path!(),
                    "::review_r1_production_prepare_pins_one_byte_module_and_metadata_partial_tails"
                ),
            ])
            .env(CHILD, "1")
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        return;
    }
    let entries = vec![
        entry(0x10000, 0x600000, 1),
        entry(0x210fff, 1, 2), // one-byte module in the final byte of a page
        entry(0x230fff, 2, 2), // metadata straddles a page boundary
    ];
    assert!(prepare(&entries, 0x250fff, 0x300000, 0x310000).is_ok());
    drop(entries); // PageMap must own its pins, not borrow the boot inventory
    let mut pm = PAGE_MAP.lock().take().unwrap();
    for page in [0x210000, 0x230000, 0x231000, 0x250000, 0x251000] {
        assert_eq!(pm.translate(page), Some(page));
        assert!(!pm.unmap(page), "permanent boot pin {page:#x} was unmapped");
    }
    assert!(
        pm.unmap(0x240000),
        "non-pinned identity page remains mutable"
    );
}

#[test]
fn review_r1_live_page_structure_identity_aliases_stay_mapped() {
    let mut fa = frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 0x40000, 1)], 0x200000, 0x300000, 0x310000);
    let mut pm =
        paging::build_identity_map(&mut fa, 0x400000, vec![0; paging::PAGE_DIR_ENTRIES]).unwrap();
    let directory = pm.directory();
    assert_eq!(pm.translate(directory), Some(directory));
    assert!(
        !pm.unmap(directory),
        "live directory identity alias must be permanent"
    );
    let table = directory + 4096; // first-fit allocator's immediately following frame
    assert_eq!(pm.translate(table), Some(table));
    assert!(
        !pm.unmap(table),
        "live table identity alias must be permanent"
    );
    assert!(
        pm.unmap(0x40000),
        "ordinary identity pages remain unmap-capable"
    );
    let next_table = fa.allocate().unwrap();
    assert!(fa.free(next_table));
    assert!(pm.map(
        &mut fa,
        paging::GROWTH_START as u64,
        0x50000,
        &paging::KERNEL_PERMS
    ));
    assert_eq!(pm.translate(next_table), Some(next_table));
    assert!(
        !pm.unmap(next_table),
        "runtime-created live tables are protected too"
    );
}

#[test]
fn review_r1_pin_backing_retained_on_failure_and_moved_on_success() {
    let mut fa = frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 8192, 1)], 0x200000, 0x300000, 0x310000);
    let mut tables = vec![0; paging::PAGE_DIR_ENTRIES];
    let mut pins = permanent_boot_pins(&[entry(0x20fff, 2, 2)], 0x30000, 0x400000).unwrap();
    let ptr = pins.as_ptr();
    let cap = pins.capacity();
    assert!(
        paging::build_identity_map_with_pins_in_place(&mut fa, 0x400001, &mut tables, &mut pins)
            .is_none()
    );
    assert_eq!(pins.as_ptr(), ptr);
    assert_eq!(pins.capacity(), cap);
    assert_eq!(pins.len(), 2);
    assert_eq!(fa.stats().allocated_frames, 0);
    tables.fill(0);
    let mut pm =
        paging::build_identity_map_with_pins_in_place(&mut fa, 0x400000, &mut tables, &mut pins)
            .unwrap();
    assert_eq!(pins.capacity(), 0);
    assert_eq!(tables.capacity(), 0);
    assert!(!pm.unmap(0x20000));
    assert!(!pm.unmap(0x21000));
    assert!(paging::validate_mapping(&pm, &[]).is_empty());
}

#[test]
fn review_r1_pin_span_address_checks_and_clipping() {
    let pins = permanent_boot_pins(
        &[
            entry(0x3fffff, 0x200000, 2),
            entry(1u64 << 32, 4096, 2),
            entry(0x22000, 0, 2),
            entry(0, 4096, 2), // the intentionally absent null page is not a live alias
        ],
        0x20000,
        0x400000,
    )
    .unwrap();
    assert_eq!(pins, vec![(0x20000, 0x21000), (0x3ff000, 0x400000)]);
    assert!(permanent_boot_pins(&[entry(u64::MAX, 2, 2)], 0x20000, 0x400000).is_err());
    for header in [0, (1u64 << 32) - 4095, u64::MAX] {
        assert!(permanent_boot_pins(&[], header, 0x400000).is_err());
    }
}

#[test]
fn review_r1_validation_checks_pinned_non_growth_pages_not_growth_holes() {
    let mut fa = frame::FrameAllocator::new();
    fa.init(&[entry(0x10000, 0x10000, 1)], 0x200000, 0x300000, 0x310000);
    let mut tables = vec![0; paging::PAGE_DIR_ENTRIES];
    let mut pins = vec![
        (0x20000, 0x21000),
        (paging::GROWTH_START as u64, paging::GROWTH_END as u64),
    ];
    let pm =
        paging::build_identity_map_with_pins_in_place(&mut fa, 0x20000, &mut tables, &mut pins)
            .unwrap();
    assert_eq!(
        paging::validate_mapping(&pm, &[]),
        vec!["permanent boot span"]
    );
}
