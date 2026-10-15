use super::*;

#[test]
fn b26_growth_failure_does_not_consume_reserved_frame() {
    // This lifecycle publishes PAGE_MAP permanently; keep it out of the shared
    // process so allocation-refusal and validation tests can run in any order.
    const CHILD: &str = "RUST_OS_B26_GROWTH_CHILD";
    if std::env::var_os(CHILD).is_none() {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                concat!(
                    module_path!(),
                    "::b26_growth_failure_does_not_consume_reserved_frame"
                ),
            ])
            .env(CHILD, "1")
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        return;
    }
    let _serial = TEST_LOCK.lock().unwrap();
    let g = memory::GROWTH_START;
    let entries = [entry(0x10000, 0x10000), entry(g as u64, 4096)];
    memory::FRAME_ALLOC
        .lock()
        .init(&entries, 0x200000, 0x300000, 0x310000);
    // This isolated binary has not installed a PAGE_MAP.
    assert!(memory::page_map_ref().is_none());
    let before = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(memory::heap_grow_frame(g), None);
    let after = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(after.allocated_frames, before.allocated_frames);
    assert_eq!(after.reserved_frames, before.reserved_frames);
    assert_eq!(after.free_frames, before.free_frames);
    assert_eq!(after.invalid_frees, before.invalid_frees);
    assert_eq!(after.double_frees, before.double_frees);
    assert_eq!(
        memory::FRAME_ALLOC.lock().claim_growth_frame(g as u64),
        Some(g as u64)
    );
    assert!(memory::FRAME_ALLOC.lock().free(g as u64));

    assert!(memory::prepare(&entries, 0x200000, 0x300000, 0x310000).is_ok());
    let directory = memory::page_directory();
    let before = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(
        memory::prepare(&entries, 0x200000, 0x300000, 0x310000),
        Err("paging already prepared")
    );
    assert_eq!(memory::page_directory(), directory);
    let after = *memory::FRAME_ALLOC.lock().stats();
    assert_eq!(after.allocated_frames, before.allocated_frames);
    assert_eq!(after.reserved_frames, before.reserved_frames);
    assert_eq!(after.free_frames, before.free_frames);
    assert_eq!(memory::heap_grow_frame(g), Some(g as u64));
    // Inject an existing-PTE conflict while the physical growth slot is
    // unclaimed. Never remove/overwrite that unrelated mapping on rejection.
    assert!(memory::FRAME_ALLOC.lock().free(g as u64));
    let before = *memory::FRAME_ALLOC.lock().stats();
    for _ in 0..2 {
        assert_eq!(memory::heap_grow_frame(g), None);
        let after = *memory::FRAME_ALLOC.lock().stats();
        assert_eq!(after.allocated_frames, before.allocated_frames);
        assert_eq!(after.reserved_frames, before.reserved_frames);
        assert_eq!(after.free_frames, before.free_frames);
        assert_eq!(after.invalid_frees, before.invalid_frees);
        assert_eq!(after.double_frees, before.double_frees);
        assert!(!memory::FRAME_ALLOC.lock().is_free(g as u64));
        assert_eq!(
            memory::page_map_ref().unwrap().translate(g as u64),
            Some(g as u64)
        );
    }
    assert_eq!(
        memory::FRAME_ALLOC.lock().claim_growth_frame(g as u64),
        Some(g as u64)
    );
    assert!(memory::FRAME_ALLOC.lock().free(g as u64));
}
