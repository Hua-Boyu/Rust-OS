// RED: boot metadata rejection must be recorded as an explicit outcome that the
// storage/shell paths can gate on. Before the fix there is no outcome API, so
// this fixture fails to compile; after GREEN it proves the recorded contract.
use crate::multiboot::inventory::{self, BootError};

#[test]
fn rejected_boot_outcome_is_recorded_once_and_visible_before_shell() {
    // Process-global outcome: isolate through the established child pattern.
    const CHILD: &str = "ROSTI_B18_OUTCOME_CHILD";
    if std::env::var_os(CHILD).is_none() {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                &format!(
                    "{}::rejected_boot_outcome_is_recorded_once_and_visible_before_shell",
                    module_path!().split_once("::").unwrap().1
                ),
            ])
            .env(CHILD, "1")
            .output()
            .unwrap();
        assert!(
            output.status.success()
                && String::from_utf8_lossy(&output.stdout)
                    .contains("test result: ok. 1 passed; 0 failed; 0 ignored;"),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        return;
    }
    assert_eq!(inventory::outcome(), None, "fresh boot records no outcome");
    // A malformed inventory must fail closed AND record the rejection.
    let result = inventory::parse(0, 0x5000, (0x100000, 0x180000), |_, _| {
        panic!("bad magic read")
    });
    assert_eq!(result.err(), Some(BootError::Magic));
    assert_eq!(
        inventory::outcome(),
        Some(BootError::Magic),
        "rejection is recorded before any shell dispatch"
    );
    // The outcome is first-rejection-wins: a later error cannot rewrite it.
    inventory::record(BootError::Allocation);
    assert_eq!(inventory::outcome(), Some(BootError::Magic));
}

#[test]
fn storage_gate_is_closed_when_boot_metadata_is_rejected() {
    const CHILD: &str = "ROSTI_B18_GATE_CHILD";
    if std::env::var_os(CHILD).is_none() {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                &format!(
                    "{}::storage_gate_is_closed_when_boot_metadata_is_rejected",
                    module_path!().split_once("::").unwrap().1
                ),
            ])
            .env(CHILD, "1")
            .output()
            .unwrap();
        assert!(
            output.status.success()
                && String::from_utf8_lossy(&output.stdout)
                    .contains("test result: ok. 1 passed; 0 failed; 0 ignored;"),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        return;
    }
    assert!(
        inventory::storage_allowed(),
        "accepted boot keeps storage paths"
    );
    let result = inventory::parse(0, 0x5000, (0x100000, 0x180000), |_, _| {
        panic!("bad magic read")
    });
    assert_eq!(result.err(), Some(BootError::Magic));
    assert!(
        !inventory::storage_allowed(),
        "rejected metadata must close ATA probe, mount and raw shell writes"
    );
}
