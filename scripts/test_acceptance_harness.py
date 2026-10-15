"""Acceptance source-freeze regressions; subprocesses are fixtures, not live gates."""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("acceptance", Path(__file__).with_name("phase6_verify.py"))
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class SourceFreezeTests(unittest.TestCase):
    def simulate(self, mutation, omit_reports=False, boot_rows=10, read_tests=4, write_tests=3,
                 safety_output=None, metadata_report="valid", b13_report="valid"):
        self.last_commands = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ("src/main.rs", "tests_kernel/src/lib.rs", "scripts/a.py", "Cargo.toml", "linker.ld", "target.json", ".cargo/config.toml"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("initial\n")
            kernel = root / "target/target/debug/kernel"
            kernel.parent.mkdir(parents=True)
            kernel.write_bytes(b"fixture kernel")

            def run(command, **kwargs):
                self.last_commands.append(command)
                # Simulate successful gates solely to reach the real final source-freeze check.
                output = kwargs["stdout"]
                safety_filter = next((c for c in command if c in ("b11_", "b18_inventory_tests::", "b26_")), None)
                if safety_filter:
                    text = (safety_output or {}).get(safety_filter,
                        f"test safety::{safety_filter}fixture ... ok\n"
                        "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 4 filtered out\n")
                    output.write(text.encode())
                    return type("Result", (), {"returncode": 0})()
                if "test" in command:
                    passed = read_tests if "read_performance" in command else 1
                    if "write_preservation" in command:
                        passed = write_tests
                    output.write(f"test result: ok. {passed} passed; 0 failed\n".encode())
                if any(str(c).endswith("boot_test.py") for c in command):
                    folder = Path(command[command.index("--output-dir") + 1])
                    folder.mkdir(parents=True, exist_ok=True)
                    with (folder / "boot_results.csv").open("w", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=["status"])
                        writer.writeheader()
                        writer.writerows([{"status": "PASS"}] * boot_rows)
                script_name = next((Path(str(c)).name for c in command if str(c).endswith(".py")), "")
                if script_name == "test_b13_boot.py":
                    path = Path(command[command.index("--report") + 1])
                    path.write_text(json.dumps({"status": "PASS", "tests_run": 3, "failures": []}))
                if script_name == "b13_boot_fixture.py" and b13_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1])
                    folder.mkdir(parents=True, exist_ok=True)
                    guests = []
                    for kind, entry in (("fixture", "b13_handoff"), ("production", "_start")):
                        for ram in (128, 512):
                            guest = {"status": "PASS", "cleanup": True, "memory_mib": ram, "entry": entry}
                            child = folder / f"{kind}_{ram}"
                            child.mkdir()
                            (child / "report.json").write_text(json.dumps(guest))
                            guests.append(guest)
                    evidence = {"status": "PASS", "qemu_status": "PASS", "inspection": {"status": "PASS"}, "guests": guests}
                    if b13_report != "valid":
                        evidence.update(b13_report)
                    (folder / "report.json").write_text(json.dumps(evidence))
                if script_name == "boot_metadata_test.py" and metadata_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1]) / "fixture"
                    folder.mkdir(parents=True, exist_ok=True)
                    scenarios = []
                    for boot in ("elf", "iso"):
                        for ram in (128, 512):
                            for name in ("nomodule", "invalidmagic", "null", "headerbad", "mmaptruncated",
                                         "modulein-growth", "module-overlap", "countedoverflow", "validmodule",
                                         "reservedgrowth", "frameexhaustion"):
                                child = folder / f"{boot}_{ram}_{name}"
                                child.mkdir()
                                path = child / "report.json"
                                path.write_text(json.dumps({"overall": "PASS", "checks": [{"pass": True}]}))
                                scenarios.append({"boot": boot, "ram_mib": ram, "name": name,
                                                  "overall": "PASS", "report": str(path)})
                    evidence = {"overall": "PASS", "checks": [{"pass": True}],
                                "scenarios": scenarios, "scenario_count": 44, "expected_scenarios": 44}
                    if metadata_report != "valid":
                        evidence = metadata_report
                    (folder / "report.json").write_text(json.dumps(evidence))
                if not omit_reports and script_name in ("paging_test.py", "fs_test.py", "block_test.py", "rostifs_test.py"):
                    folder = Path(command[command.index("--output-dir") + 1]) / "fixture"
                    folder.mkdir(parents=True, exist_ok=True)
                    count = {"fs_test.py": 102, "block_test.py": 98, "rostifs_test.py": 168}.get(script_name, 2)
                    if script_name == "paging_test.py" and "--runs" in command:
                        count = 20
                    field = "results" if script_name == "paging_test.py" else "checks"
                    (folder / "report.json").write_text(json.dumps({"overall": "PASS", field: [{"pass": True}] * count}))
                if any(str(c).endswith("build-proxmox-iso.py") for c in command):
                    (root / "dist").mkdir(exist_ok=True)
                    (root / "dist/rosti.iso").write_bytes(b"fixture ISO")
                if any(str(c).endswith("block_test.py") for c in command) and "--iso" in command and "512" in command:
                    mutation(root)
                return type("Result", (), {"returncode": 0})()

            with patch.object(acceptance, "PROJECT", root), patch.object(sys, "argv", ["phase6_verify.py"]), patch.object(acceptance.subprocess, "run", side_effect=run), patch.object(acceptance.subprocess, "check_output", return_value="fixture-head\n"), contextlib.redirect_stdout(io.StringIO()):
                code = acceptance.main()
            self.last_versioned_count = len(list((root / "dist").glob("rosti_phase*.iso")))
            reports = list((root / "test_results").glob("phase*/acceptance_*/acceptance.json"))
            self.last_report = json.loads(reports[0].read_text())
            return code

    def test_current_milestone_is_phase9_6(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertEqual(self.last_report["phase"], "9.6")
        self.assertRegex(self.last_report["iso"]["name"], r"^rosti_phase9_6_\d{8}T\d{6}Z\.iso$")

    def test_read_boundary_and_transfer_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any("read_performance" in command and "host-tools" in command
                            and "--ignored" not in command for command in self.last_commands))

    def test_b13_injection_transport_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any(any(str(arg).endswith("test_b13_entry_inject.py") for arg in command)
                            for command in self.last_commands))

    def test_phase9_6_host_safety_suites_cannot_disappear(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        for key, filter_name, manifest in (("b11", "b11_", "tests_kernel/Cargo.toml"),
                                           ("b18", "b18_inventory_tests::", "tests_kernel/Cargo.toml"),
                                           ("b26", "b26_", "tests_b26/Cargo.toml")):
            with self.subTest(suite=key):
                commands = [c for c in self.last_commands if filter_name in c]
                self.assertEqual(len(commands), 1)
                self.assertIn("--lib", commands[0])
                self.assertTrue(any(str(c).replace("\\", "/").endswith(manifest) for c in commands[0]))
                self.assertEqual(self.last_report["counts"][key], {"pass": 1, "fail": 0})

    def test_empty_or_unobserved_host_safety_suites_cannot_publish(self):
        for filter_name in ("b11_", "b18_inventory_tests::", "b26_"):
            for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                         "test result: ok. 1 passed; 0 failed; 0 ignored\n",
                         f"test safety::{filter_name}fixture ... ok\n"
                         "test result: ok. 2 passed; 0 failed; 0 ignored\n",
                         f"test safety::{filter_name}fixture ... ok\n"
                         "test result: ok. 1 passed; 1 failed; 0 ignored\n",
                         f"test safety::{filter_name}fixture ... ok\n"
                         "test result: ok. 1 passed; 0 failed; 1 ignored\n"):
                with self.subTest(suite=filter_name, output=text):
                    self.assertEqual(self.simulate(lambda root: None,
                        safety_output={filter_name: text}), 1)
                    self.assertEqual(self.last_versioned_count, 0)

    def test_integrated_boot_metadata_guests_are_mandatory_and_sequential(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = self.last_commands
        guests = [i for i, c in enumerate(commands) if any(str(a).endswith("boot_metadata_test.py") for a in c)]
        contracts = [c for c in commands if any(str(a).endswith("test_boot_metadata_harness.py") for a in c)]
        self.assertEqual(len(guests), 1)
        self.assertEqual(len(contracts), 1)
        production = next(i for i, c in enumerate(commands) if c == ["cargo", "build"])
        first_boot = next(i for i, c in enumerate(commands) if any(str(a).endswith("boot_test.py") for a in c))
        self.assertLess(production, guests[0])
        self.assertLess(guests[0], first_boot)
        command = commands[guests[0]]
        self.assertTrue(Path(command[command.index("--output-dir") + 1]).is_absolute())
        self.assertIn("both", command)
        self.assertEqual(self.last_report["counts"]["boot_metadata_scenarios"], {"pass": 44, "fail": 0})

    def test_missing_or_empty_boot_metadata_evidence_cannot_publish(self):
        for evidence in (None, {}, {"overall": "PASS", "checks": []},
                         {"overall": "PASS", "checks": [{"pass": False}]},
                         {"overall": "PASS", "checks": [{"pass": True}], "check_count": 2},
                         {"overall": "PASS", "checks": [{"pass": True}], "scenarios": [],
                          "expected_scenarios": 0, "scenario_count": 0}):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.simulate(lambda root: None, metadata_report=evidence), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_b13_host_and_privileged_handoff_gates_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        for name in ("test_b13_boot.py", "b13_boot_fixture.py"):
            commands = [c for c in self.last_commands if any(str(a).endswith(name) for a in c)]
            self.assertEqual(len(commands), 1)
            if name == "b13_boot_fixture.py":
                for option in ("--build", "--run-qemu", "--production-kernel", "--output-dir"):
                    self.assertIn(option, commands[0])
        self.assertEqual(self.last_report["counts"]["b13_host"], {"pass": 3, "fail": 0})
        self.assertEqual(self.last_report["counts"]["b13_qemu"], {"pass": 4, "fail": 0})

    def test_b13_missing_or_incomplete_privileged_proof_cannot_publish(self):
        for evidence in (None, {"qemu_status": "NOT_RUN"}, {"guests": []},
                         {"inspection": {"status": "FAIL"}},
                         {"guests": [{"status": "PASS", "cleanup": False}] * 4}):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.simulate(lambda root: None, b13_report=evidence), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_late_b13_evidence_corruption_cannot_publish(self):
        def corrupt(root):
            child = next((root / "test_results").glob("phase*/acceptance_*/b13_qemu/fixture_128/report.json"))
            child.write_text(json.dumps({"status": "FAIL"}))
        self.assertEqual(self.simulate(corrupt), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_boot_metadata_matrix_cannot_shrink_after_validation(self):
        def corrupt(root):
            path = next((root / "test_results").glob("phase*/acceptance_*/boot_metadata/*/report.json"))
            evidence = json.loads(path.read_text())
            evidence["scenario_count"] = 43
            path.write_text(json.dumps(evidence))
        self.assertEqual(self.simulate(corrupt), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_missing_read_regression_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, read_tests=1), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_write_preservation_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any("write_preservation" in command and "host-tools" in command
                            and "--ignored" not in command for command in self.last_commands))

    def test_missing_write_regression_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, write_tests=2), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_missing_mandatory_reports_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, omit_reports=True), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_nine_boot_rows_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, boot_rows=9), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_invalid_report_schemas_and_declared_totals_cannot_pass(self):
        for report in (None, {}, {"checks": [{"pass": True}]},
                       {"overall": "PASS"}, {"overall": "PASS", "checks": []},
                       {"overall": "PASS", "checks": [{"pass": False}]},
                       {"overall": "PASS", "results": [{"pass": 1}]},
                       {"overall": "PASS", "checks": [{"pass": True}], "check_count": 2}):
            with self.subTest(report=report), self.assertRaises(RuntimeError):
                acceptance.evidence_rows(report, "fixture")

    def test_bad_mandatory_report_cannot_publish(self):
        for bad in ({}, {"checks": [{"pass": True}]}, {"overall": "PASS", "checks": []}):
            def corrupt(root):
                path = next((root / "test_results").glob("phase*/acceptance_*/fs_elf_128/*/report.json"))
                path.write_text(json.dumps(bad))
            with self.subTest(report=bad):
                self.assertEqual(self.simulate(corrupt), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_failed_source_freeze_does_not_publish_versioned_iso(self):
        self.assertEqual(self.simulate(lambda root: (root / "src/late.rs").write_text("late\n")), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_failed_harness_report_cannot_pass_or_publish(self):
        def failed_report(root):
            run = next((root / "test_results").glob("phase*/acceptance_*"))
            folder = run / "fixture"
            folder.mkdir()
            (folder / "report.json").write_text('{"overall":"FAIL","checks":[{"pass":false}]}')
        self.assertEqual(self.simulate(failed_report), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_source_added_during_acceptance_is_rejected(self):
        self.assertEqual(self.simulate(lambda root: (root / "src/late.rs").write_text("late\n")), 1)

    def test_target_configuration_changed_during_acceptance_is_rejected(self):
        self.assertEqual(self.simulate(lambda root: (root / "target.json").write_text("changed\n")), 1)

    def test_stable_source_can_finish(self):
        self.assertEqual(self.simulate(lambda root: None), 0)

    def test_safety_fixture_build_inputs_are_frozen(self):
        for relative in ("tests_b26/src/lib.rs", "tests_b26/Cargo.toml",
                         "tests_b26/Cargo.lock", "tests_b26/.cargo/config.toml",
                         "scripts/b13_fixture/main.rs", "scripts/b13_fixture/entry.s",
                         "scripts/b13_fixture/linker.ld", "scripts/b13_fixture/target.json",
                         "scripts/b13_fixture/.cargo/config.toml", "scripts/b13_fixture/Cargo.toml"):
            def add(root):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("late input\n")
            with self.subTest(input=relative):
                self.assertEqual(self.simulate(add), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_portable_source_added_during_acceptance_is_rejected(self):
        def add(root):
            directory = root / "crates/rostifs/src"
            directory.mkdir(parents=True)
            (directory / "late.rs").write_text("late\n")
        self.assertEqual(self.simulate(add), 1)
        self.assertEqual(self.last_versioned_count, 0)


if __name__ == "__main__":
    unittest.main()
