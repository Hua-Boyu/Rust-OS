#!/usr/bin/env python3
"""Host-only RostiFS harness safety and evidence regressions; never starts QEMU."""
import contextlib
import copy
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import Mock

import rostifs_test as target

CONSOLES = ("fd 0 console-in rights 0 offset 0 refs 0\n"
            "fd 1 console-out rights 0 offset 0 refs 0\n"
            "fd 2 console-out rights 0 offset 0 refs 0\n")


class FakeHarness:
    def __init__(self, args=None, run=None, image=None, deadline=None):
        self.report = {"overall": "FAIL", "checks": [], "commands": [], "qemu_pid": 1234}
        self.proc = Mock()
        self.proc.poll.return_value = None
        self.outputs = {}
        self.closed = False

    def start(self):
        pass

    def text(self):
        return "ROSTI: entered kernel_main\nROSTI: boot complete\nrosti>"

    def check(self, condition, label):
        self.report["checks"].append({"name": label, "pass": bool(condition)})
        if not condition:
            raise AssertionError(label)

    def command(self, command):
        self.report["commands"].append({"command": command})
        return self.outputs.get(command, "")

    def success(self, command):
        self.check(self.command(command).strip() in ("", "ok"), command)

    def exact(self, command, expected):
        self.check(self.command(command).rstrip("\n") == expected, command)

    def close(self):
        self.closed = True
        self.proc.poll.return_value = -9


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.media = target.OwnedImages(self.project)

    def test_exclusive_new_directory_is_under_dist(self):
        other = target.OwnedImages(self.project)
        self.assertEqual(self.media.directory.parent, self.project / "dist")
        self.assertNotEqual(self.media.directory, other.directory)

    def test_arbitrary_and_sibling_media_are_rejected(self):
        for image in (self.project / "disk.raw", self.media.directory / "other.raw",
                      self.media.directory / "../owned.raw"):
            with self.subTest(image=image), self.assertRaises(ValueError):
                self.media.require(image, new=True)

    def test_existing_media_cannot_be_reformatted(self):
        image = self.media.require(self.media.paths["owned"], new=True)
        image.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            self.media.require(image, new=True)
        self.assertEqual(image.read_bytes(), b"existing")

    def test_cli_does_not_accept_image_or_live_options(self):
        for option in ("--image", "--disk", "--live"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                target.parser().parse_args([option, "arbitrary.raw"])

    def test_fixture_corrupts_both_roots_preserving_ownership_and_source(self):
        source = self.media.paths["owned"]
        data = bytearray(target.BLOCKS * target.BLOCK_SIZE)
        data[:len(target.MAGIC)] = target.MAGIC
        for block in (1, 2):
            data[block * target.BLOCK_SIZE:block * target.BLOCK_SIZE + 8] = b"ROSTIFS\x01"
        source.write_bytes(data)
        baseline = target.digest(source)
        corrupt = self.media.copy_fixture(source, "corrupt")
        unowned = self.media.copy_fixture(source, "unowned")
        self.assertEqual(target.digest(source), baseline)
        self.assertEqual(corrupt.read_bytes()[:512], data[:512])
        for block in (1, 2):
            self.assertEqual(corrupt.read_bytes()[block * target.BLOCK_SIZE:block * target.BLOCK_SIZE + 8], bytes(8))
        self.assertEqual(unowned.read_bytes()[:512], bytes(512))
        self.assertEqual(unowned.read_bytes()[512:], data[512:])
        with self.assertRaises(FileExistsError):
            self.media.copy_fixture(source, "corrupt")

    def test_expired_deadline_refuses_formatter_before_subprocess(self):
        args = SimpleNamespace(mkrostifs=None)
        with self.assertRaises(TimeoutError):
            target.format_image(args, self.media, time.monotonic() - 1, self.project)
        self.assertFalse(self.media.paths["owned"].exists())

    def test_nonfinite_deadline_is_rejected_without_running(self):
        for timeout in ("nan", "inf", "0", "-1"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                target.main(["--timeout", timeout])

    def test_formatter_receives_explicit_image_geometry_and_identity(self):
        args = SimpleNamespace(mkrostifs=None)
        command = target.format_command(args, self.media.paths["owned"])
        self.assertEqual(command[0:4], ["cargo", "+nightly", "run", "--manifest-path"])
        self.assertTrue(Path(command[4]).is_absolute())
        self.assertEqual(command[-4:], ["--test-owned-image", str(self.media.paths["owned"]), "--blocks", "256"])
        self.assertIn("host-tools", command)


class StageTests(unittest.TestCase):
    def fixture(self):
        return [{"stage": name, "overall": "PASS", "qemu_pid": 100 + i,
                 "owned_qemu_exited": True, "checks": [{"name": "test", "pass": True}],
                 "commands": [{"command": "pwd"}], "check_count": 1, "command_count": 1}
                for i, name in enumerate(target.STAGES)]

    def test_complete_evidence_passes(self):
        self.assertTrue(target.validate_stages(self.fixture()))

    def test_missing_duplicate_reordered_failed_or_false_checks_fail(self):
        stages = self.fixture()
        variants = [stages[:-1], stages + [stages[-1]], list(reversed(stages))]
        for field, value in (("overall", "FAIL"), ("owned_qemu_exited", False),
                             ("checks", []), ("check_count", 2), ("command_count", 0),
                             ("qemu_pid", None)):
            variant = copy.deepcopy(stages)
            variant[0][field] = value
            variants.append(variant)
        variant = copy.deepcopy(stages)
        variant[0]["checks"][0]["pass"] = False
        variants.append(variant)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertFalse(target.validate_stages(variant))

    def test_boot2_reads_before_delete_and_never_rewrites(self):
        h = FakeHarness()
        h.outputs = {"pwd": target.MOUNT, "cat " + target.FILE: target.CONTENTS + "\n",
                     "ls " + target.NESTED: "message.txt\n", "fdlist": CONSOLES,
                     "stat " + target.FILE: "fs: not found\n"}
        target.boot2(h)
        commands = [c["command"] for c in h.report["commands"]]
        self.assertLess(commands.index("cat " + target.FILE), commands.index("rm " + target.FILE))
        self.assertFalse(any(c.split()[0] in ("write", "append", "touch", "mkdir") for c in commands))

    def test_boot3_is_read_only_and_does_not_recreate_paths(self):
        h = FakeHarness()
        h.outputs = {"pwd": target.MOUNT, "stat " + target.DIRECTORY: "fs: not found\n",
                     "stat " + target.FILE: "fs: not found\n", "fdlist": CONSOLES}
        target.boot3(h)
        self.assertTrue(all(c["command"].split()[0] in ("cd", "pwd", "stat", "ls", "fdlist")
                            for c in h.report["commands"]))

    def test_missing_requires_real_error_not_echo_or_empty(self):
        for output in ("", "stat " + target.FILE, "type: file\nsize: 0 bytes\n"):
            h = FakeHarness()
            h.outputs = {"stat " + target.FILE: output}
            with self.subTest(output=output), self.assertRaises(AssertionError):
                target.missing(h, target.FILE)

    def test_fdlist_rejects_leaked_descriptor_or_wrong_console(self):
        for output in (CONSOLES + "fd 3 file rights 1 offset 0 refs 1\n",
                       CONSOLES.replace("fd 2 console-out", "fd 2 file"),
                       CONSOLES.replace("rights 0", "rights 1"), ""):
            h = FakeHarness()
            h.outputs = {"fdlist": output}
            with self.subTest(output=output), self.assertRaises(AssertionError):
                target.console_only(h)
        h = FakeHarness()
        h.outputs = {"fdlist": CONSOLES}
        target.console_only(h)

    def test_failure_still_closes_and_writes_stage_report(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder).resolve()
            media = target.OwnedImages(project)
            image = media.paths["owned"]
            image.write_bytes(b"test")
            h = FakeHarness()
            def fail(_h):
                raise AssertionError("deliberate exercise failure")
            report = target.run_stage(None, project, "stage", image, media,
                                      time.monotonic() + 5, fail, factory=lambda *args: h)
            self.assertTrue(h.closed)
            self.assertTrue(report["owned_qemu_exited"])
            self.assertEqual(report["overall"], "FAIL")
            self.assertTrue((project / "stage/report.json").is_file())

    def test_socket_cleanup_failure_cannot_orphan_owned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder).resolve()
            media = target.OwnedImages(project)
            image = media.paths["owned"]
            image.write_bytes(b"test")
            h = FakeHarness()
            h.close = Mock(side_effect=OSError("socket close failed"))
            h.proc.kill.side_effect = lambda: setattr(h.proc.poll, "return_value", -9)
            report = target.run_stage(None, project, "stage", image, media,
                                      time.monotonic() + 5, lambda _h: None,
                                      factory=lambda *args: h)
            h.proc.kill.assert_called_once()
            h.proc.wait.assert_called_once_with(timeout=5)
            self.assertTrue(report["owned_qemu_exited"])
            self.assertEqual(report["overall"], "FAIL")


if __name__ == "__main__":
    unittest.main()
