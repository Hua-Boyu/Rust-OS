#!/usr/bin/env python3
"""Reader regressions using the actual captured Proxmox QMP response."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("fs_test", ROOT / "scripts/fs_test.py")
fs_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs_test)


class MediaParsingTests(unittest.TestCase):
    def setUp(self):
        report = json.loads((ROOT / "test_results/phase6/live_vm103/media_mismatch_report.json").read_text())
        self.blocks = report["live_block_checks"][0]
        block = next(b for b in self.blocks if b.get("qdev") == "ide2")
        self.expected = block["inserted"]["image"]["backing-image"]["filename"]

    def harness(self, blocks, expected):
        args = SimpleNamespace(timeout=10, ram=512, stress=False, expected_iso=expected)
        harness = fs_test.Harness(args, ROOT / "test_results/phase6")
        harness.qmp = lambda *_args, **_kwargs: blocks
        return harness

    def test_actual_throttle_raw_file_wrapper_matches_exact_leaf(self):
        self.harness(self.blocks, self.expected).verify_live_iso()

    def test_similar_filename_is_not_accepted(self):
        with self.assertRaises(AssertionError):
            self.harness(self.blocks, self.expected + ".wrong").verify_live_iso()

    def test_other_guest_drive_is_not_accepted(self):
        blocks = copy.deepcopy(self.blocks)
        for block in blocks:
            block["qdev"] = "ide0"
        with self.assertRaises(AssertionError):
            self.harness(blocks, self.expected).verify_live_iso()

    def test_partial_serial_command_has_no_completion_evidence(self):
        with self.assertRaises(AssertionError):
            fs_test.command_output("cat file\ndata\n", "cat file")
        self.assertEqual(fs_test.command_output("cat file\ndata\nrosti>", "cat file"), "data\n")


if __name__ == "__main__":
    unittest.main()
