"""Acceptance source-freeze regressions; subprocesses are fixtures, not live gates."""
import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("acceptance", Path(__file__).with_name("phase6_verify.py"))
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class SourceFreezeTests(unittest.TestCase):
    def simulate(self, mutation):
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
                # Simulate successful gates solely to reach the real final source-freeze check.
                output = kwargs["stdout"]
                if "test" in command:
                    output.write(b"test result: ok. 1 passed; 0 failed\n")
                if any(str(c).endswith("boot_test.py") for c in command):
                    folder = Path(command[command.index("--output-dir") + 1])
                    folder.mkdir(parents=True, exist_ok=True)
                    with (folder / "boot_results.csv").open("w", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=["status"])
                        writer.writeheader()
                        writer.writerows([{"status": "PASS"}] * 10)
                if any(str(c).endswith("build-proxmox-iso.py") for c in command):
                    (root / "dist").mkdir(exist_ok=True)
                    (root / "dist/rosti.iso").write_bytes(b"fixture ISO")
                if any(str(c).endswith("block_test.py") for c in command) and "--iso" in command and "512" in command:
                    mutation(root)
                return type("Result", (), {"returncode": 0})()

            with patch.object(acceptance, "PROJECT", root), patch.object(sys, "argv", ["phase6_verify.py"]), patch.object(acceptance.subprocess, "run", side_effect=run), patch.object(acceptance.subprocess, "check_output", return_value="fixture-head\n"), contextlib.redirect_stdout(io.StringIO()):
                code = acceptance.main()
            self.last_versioned_count = len(list((root / "dist").glob("rosti_phase9_*.iso")))
            return code

    def test_failed_source_freeze_does_not_publish_versioned_iso(self):
        self.assertEqual(self.simulate(lambda root: (root / "src/late.rs").write_text("late\n")), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_failed_harness_report_cannot_pass_or_publish(self):
        def failed_report(root):
            run = next((root / "test_results/phase9").glob("acceptance_*"))
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
