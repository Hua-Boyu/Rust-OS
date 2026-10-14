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
    def simulate(self, mutation, omit_reports=False, boot_rows=10, read_tests=4, write_tests=3):
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

    def test_current_milestone_is_phase9_5(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertEqual(self.last_report["phase"], "9.5")

    def test_read_boundary_and_transfer_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any("read_performance" in command and "host-tools" in command
                            and "--ignored" not in command for command in self.last_commands))

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

    def test_portable_source_added_during_acceptance_is_rejected(self):
        def add(root):
            directory = root / "crates/rostifs/src"
            directory.mkdir(parents=True)
            (directory / "late.rs").write_text("late\n")
        self.assertEqual(self.simulate(add), 1)
        self.assertEqual(self.last_versioned_count, 0)


if __name__ == "__main__":
    unittest.main()
