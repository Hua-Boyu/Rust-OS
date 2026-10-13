"""Host-only Phase 9.5 measurement contracts; no QEMU or disk writes."""
import contextlib
import io
import json
from contextlib import ExitStack
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import phase9_5_bench as bench


class BenchmarkContracts(unittest.TestCase):
    def test_metadata_failures_write_fail_evidence(self):
        for probe, error in (("elf", FileNotFoundError("missing kernel")),
                             ("elf", ValueError("malformed kernel")),
                             ("rustc", FileNotFoundError("missing rustc")),
                             ("iso", FileNotFoundError("missing ISO"))):
            with self.subTest(probe=probe, error=str(error)), \
                    tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                output = Path(directory) / "report.json"
                argv = ["bench", "--output", str(output)]
                if probe == "iso":
                    argv += ["--iso", str(Path(directory) / "missing.iso")]
                stack.enter_context(patch.object(sys, "argv", argv))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                stack.enter_context(patch.object(bench, "elf_metrics",
                    side_effect=error if probe == "elf" else None,
                    return_value={"sha256": "mock"}))
                stack.enter_context(patch.object(bench.subprocess, "check_output",
                    side_effect=error if probe == "rustc" else None, return_value="rustc mock"))
                media = stack.enter_context(patch.object(bench, "OwnedImages"))
                self.assertEqual(bench.main(), 1)
                report = json.loads(output.read_text())
                self.assertEqual(report["overall"], "FAIL")
                self.assertIn("missing.iso" if probe == "iso" else str(error), report["error"])
                self.assertEqual(report["runs"], [])
                media.assert_not_called()

    def scenario(self, close_error=None, workload_error=None, ownedexit=True,
                 mounted=True, kernel_changed=False, iso_changed=None, reap_error=None):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        output = Path(directory) / "report.json"
        argv = ["bench", "--output", str(output), "--repeats", "1"]
        iso = Path(directory) / "fixture.iso"
        if iso_changed is not None:
            iso.write_bytes(b"original ISO fixture")
            argv += ["--iso", str(iso)]
        harness = Mock()
        harness.report = {"overall": "FAIL", "commands": [], "checks": []}
        harness.proc = Mock()
        harness.proc.poll.return_value = None
        def kill():
            harness.proc.poll.return_value = -9
        harness.proc.kill.side_effect = kill
        harness.proc.wait.side_effect = RuntimeError(reap_error) if reap_error else None
        def close():
            self.assertNotEqual(harness.report["overall"], "PASS")
            if iso_changed:
                iso.write_bytes(b"changed ISO fixture")
            if close_error:
                raise RuntimeError(close_error)
            harness.report["owned_qemu_exited"] = ownedexit
            if ownedexit:
                harness.proc.kill()
                harness.proc.wait(timeout=5)
        harness.close.side_effect = close
        harness.start.side_effect = RuntimeError(workload_error) if workload_error else None
        harness.memory.return_value = {"used": 8232, "growth_pages": 0}
        harness.command.return_value = "reads 8 writes 24 bytes 16384"
        harness.text.return_value = "ROSTI: RostiFS mounted at /mnt/rosti" if mounted else "rosti>"
        def check(condition, label):
            if not condition:
                raise AssertionError(label)
        harness.check.side_effect = check
        def command(*args):
            harness.report["commands"].append({"timing": {
                "host_full_command_ns": 20, "host_enter_to_prompt_ns": 10}})
        harness.success.side_effect = command
        harness.exact.side_effect = command
        with patch.object(sys, "argv", argv), \
                patch.object(bench, "elf_metrics", side_effect=[{"sha256": "mock"},
                    {"sha256": "changed" if kernel_changed else "mock"}]), \
                patch.object(bench.subprocess, "check_output", return_value="rustc mock"), \
                patch.object(bench, "OwnedImages"), \
                patch.object(bench, "format_image", return_value=Path(directory) / "mock.img"), \
                patch.object(bench, "TimedHarness", return_value=harness), \
                contextlib.redirect_stdout(io.StringIO()):
            result = bench.main()
        evidence = list(Path(directory).glob("bench_*/report.json"))
        self.assertTrue(evidence, "scenario report must survive cleanup failure")
        return result, json.loads(output.read_text()), json.loads(evidence[0].read_text()), harness

    def test_close_failure_writes_fail_and_independently_reaps(self):
        result, aggregate, run, harness = self.scenario(close_error="close broke")
        self.assertEqual(result, 1)
        self.assertEqual(aggregate["overall"], "FAIL")
        self.assertEqual(run["overall"], "FAIL")
        self.assertIn("close broke", run["cleanup_error"])
        harness.proc.kill.assert_called_once()
        harness.proc.wait.assert_called_once_with(timeout=5)
        self.assertTrue(run["owned_qemu_exited"])

    def test_missing_owned_exit_never_writes_pass(self):
        result, aggregate, run, harness = self.scenario(ownedexit=False)
        self.assertEqual(result, 1)
        self.assertEqual(run["overall"], "FAIL")
        self.assertIn("owned QEMU did not exit", run["cleanup_error"])
        harness.proc.kill.assert_called_once()
        harness.proc.wait.assert_called_once_with(timeout=5)

    def test_workload_and_cleanup_errors_are_both_preserved(self):
        result, aggregate, run, harness = self.scenario(
            close_error="close broke", workload_error="workload broke")
        self.assertEqual(result, 1)
        self.assertEqual(run["overall"], "FAIL")
        self.assertIn("workload broke", run["error"])
        self.assertIn("close broke", run["cleanup_error"])
        self.assertIn("workload broke", aggregate["error"])
        self.assertIn("close broke", aggregate["error"])
        harness.proc.kill.assert_called_once()
        harness.proc.wait.assert_called_once_with(timeout=5)

    def test_mount_marker_required_before_startup_timing(self):
        result, aggregate, run, harness = self.scenario(mounted=False)
        self.assertEqual(result, 1)
        self.assertEqual(run["overall"], "FAIL")
        self.assertNotIn("host_start_to_mounted_prompt_ns", run)
        self.assertIn("mount marker", run["error"])

    def test_changed_kernel_fails_final_artifact_freeze(self):
        result, aggregate, run, harness = self.scenario(kernel_changed=True)
        self.assertEqual(result, 1)
        self.assertEqual(aggregate["overall"], "FAIL")
        self.assertIn("kernel changed", aggregate["error"])

    def test_changed_iso_fails_final_artifact_freeze(self):
        result, aggregate, run, harness = self.scenario(iso_changed=True)
        self.assertEqual(result, 1)
        self.assertEqual(aggregate["overall"], "FAIL")
        self.assertIn("ISO changed", aggregate["error"])

    def test_unchanged_iso_passes_final_artifact_freeze(self):
        result, aggregate, run, harness = self.scenario(iso_changed=False)
        self.assertEqual(result, 0)
        self.assertTrue(aggregate["artifact_freeze_verified"])

    def test_failed_fallback_reap_keeps_all_errors_and_fail_report(self):
        result, aggregate, run, harness = self.scenario(
            workload_error="workload broke", close_error="close broke", reap_error="reap broke")
        self.assertEqual(result, 1)
        self.assertEqual(run["overall"], "FAIL")
        self.assertFalse(run["owned_qemu_exited"])
        for error in ("workload broke", "close broke", "reap broke"):
            self.assertIn(error, aggregate["error"])
        self.assertIn("reap broke", run["cleanup_error"])

    def test_success_only_after_cleanup(self):
        result, aggregate, run, harness = self.scenario()
        self.assertEqual(result, 0)
        self.assertEqual(aggregate["overall"], "PASS")
        self.assertEqual(len(aggregate["runs"]), 2)
        self.assertTrue(all(row["overall"] == "PASS" for row in aggregate["runs"]))
        self.assertEqual(run["overall"], "PASS")
        self.assertTrue(run["owned_qemu_exited"])
        self.assertEqual([item["operation"] for item in aggregate["runs"][0]["operations"]],
                         ["traverse", "create", "write", "read", "append", "list", "delete"])

    def test_counters_require_real_diagnostics(self):
        self.assertEqual(bench.disk_counters("reads 8 writes 24 bytes 16384"),
                         {"reads": 8, "writes": 24, "bytes": 16384})
        with self.assertRaises(AssertionError):
            bench.disk_counters("disk\nrosti>")

    def test_elf_metrics_select_actual_backend_symbol(self):
        # Minimal ELF32 section/symbol fixture, never booted.
        data = bytearray(512)
        struct.pack_into("<16sHHIIIIIHHHHHH", data, 0,
                         b"\x7fELF\x01\x01\x01", 2, 3, 1, 0, 0, 52, 0,
                         52, 0, 0, 40, 4, 2)
        strings = b"\0.text\0.strtab\0.symtab\0BACKEND\0"
        data[240:240 + len(strings)] = strings
        # text (allocated), string table, symbol table linked to strings.
        struct.pack_into("<IIIIIIIIII", data, 92,
                         1, 1, 2, 4096, 232, 8, 0, 0, 4, 0)
        struct.pack_into("<IIIIIIIIII", data, 132,
                         7, 3, 0, 0, 240, len(strings), 0, 0, 1, 0)
        struct.pack_into("<IIIIIIIIII", data, 172,
                         15, 2, 0, 0, 300, 16, 2, 0, 4, 16)
        struct.pack_into("<IIIBBH", data, 300,
                         strings.index(b"BACKEND"), 4096, 8, 1, 0, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.elf"
            path.write_bytes(data)
            self.assertEqual(bench.elf_metrics(path)["selected_symbols"]["BACKEND"],
                             {"address": 4096, "bytes": 8})

    def test_elf_metrics_reject_non_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-elf"
            path.write_bytes(b"untrusted input")
            with self.assertRaises(ValueError):
                bench.elf_metrics(path)

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            original = b'{"prior_evidence":true}\n'
            path.write_bytes(original)
            with patch.object(sys, "argv", ["phase9_5_bench.py", "--output", str(path)]), \
                    patch.object(bench, "OwnedImages", side_effect=AssertionError("must not create media")), \
                    contextlib.redirect_stderr(io.StringIO()), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    bench.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
