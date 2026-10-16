#!/usr/bin/env python3
"""Host-only production fixture policy regressions; no build or guest needed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_production as policy


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "production_iso_builder", Path(__file__).with_name("build-proxmox-iso.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata(kernel_features=(), storage_features=()):
    return {
        "packages": [{"id": "k", "name": "kernel"}, {"id": "r", "name": "rostifs"}],
        "resolve": {"nodes": [
            {"id": "k", "features": list(kernel_features)},
            {"id": "r", "features": list(storage_features)},
        ]},
    }


class ProductionFixturePolicyTests(unittest.TestCase):
    def run_verifier(self, resolved, artifact=b"\x7fELF production"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / "target/target/debug/kernel"
            kernel.parent.mkdir(parents=True)
            kernel.write_bytes(artifact)
            with patch.object(policy, "PROJECT", root), patch.object(
                    policy.subprocess, "run") as cargo, contextlib.redirect_stdout(io.StringIO()):
                cargo.return_value.stdout = json.dumps(resolved)
                return policy.main()

    def test_fixture_symbol_is_rejected_even_with_production_metadata(self):
        self.assertEqual(1, self.run_verifier(
            metadata(), b"\x7fELF\0_ZN6kernel19INITRAMFS_TEST_MODE17h1234E\0"))

    def test_iso_entrypoint_rejects_fixture_before_validation_or_build(self):
        builder = load_builder()
        with tempfile.TemporaryDirectory() as directory:
            kernel = Path(directory) / "kernel"
            kernel.write_bytes(b"\x7fELF\0INITRAMFS_TEST_MODE\0")
            with patch.object(builder, "KERNEL", kernel), patch.object(
                    builder, "validate_elf", return_value=True) as validate, patch.object(
                    builder, "build_iso", return_value=True) as build, patch.object(
                    builder.sys, "argv", ["builder", "--skip-boot-test"]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    builder.main()
                self.assertEqual(1, stopped.exception.code)
                validate.assert_not_called()
                build.assert_not_called()

    def test_direct_iso_build_refuses_fixture_before_staging(self):
        builder = load_builder()
        for marker in (b"INITRAMFS_TEST_MODE", b"ROSTI: fault test trigger"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                kernel = root / "kernel"
                kernel.write_bytes(b"\x7fELF\0" + marker + b"\0")
                with patch.object(builder, "PROJECT", root), patch.object(
                        builder, "KERNEL", kernel), patch.object(builder, "DIST", root / "dist"), patch(
                        "system_image_policy.trusted_archive", return_value=b"archive") as archive, patch.object(
                        builder.subprocess, "run") as rescue, contextlib.redirect_stdout(io.StringIO()):
                    self.assertFalse(builder.build_iso())
                    self.assertFalse((root / "dist").exists())
                    archive.assert_not_called()
                    rescue.assert_not_called()

    def test_production_features_and_bytes_are_allowed(self):
        self.assertEqual(0, self.run_verifier(metadata()))

    def test_all_inherited_fault_and_host_features_remain_rejected(self):
        for feature in ("paging-fault-test", "paging-write-fault-test", "fault-injection", "host-tools"):
            for package in ("kernel", "rostifs"):
                with self.subTest(feature=feature, package=package):
                    resolved = metadata([feature]) if package == "kernel" else metadata((), [feature])
                    self.assertEqual(1, self.run_verifier(resolved))

    def test_missing_required_resolved_package_is_rejected(self):
        resolved = metadata()
        resolved["resolve"]["nodes"].pop()
        self.assertEqual(1, self.run_verifier(resolved))

    def test_inherited_fatal_marker_remains_rejected(self):
        self.assertEqual(1, self.run_verifier(metadata(), b"\x7fELF ROSTI: fault test trigger"))

    def test_shared_byte_policy_scans_entire_payload(self):
        for marker in (b"INITRAMFS_TEST_MODE", b"ROSTI: fault test trigger"):
            with self.subTest(marker=marker):
                checks = policy.artifact_policy_checks(b"\x7fELF" + b"\0" * 16384 + marker + b"\0")
                self.assertTrue(checks)
                self.assertFalse(all(passed for passed, _ in checks))
        self.assertTrue(all(passed for passed, _ in policy.artifact_policy_checks(b"\x7fELF production")))

    def test_clean_iso_stages_the_same_bytes_that_were_checked(self):
        builder = load_builder()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / "kernel"
            clean = b"\x7fELF production snapshot"
            kernel.write_bytes(clean)
            iso = root / "dist/rosti.iso"

            def archive_after_kernel_changes(_project):
                kernel.write_bytes(b"\x7fELF INITRAMFS_TEST_MODE")
                return b"trusted archive"

            def fake_rescue(*args, **kwargs):
                iso.write_bytes(b"mock ISO")
                return type("Result", (), {"stdout": "mock rescue", "returncode": 0})()

            with patch.object(builder, "PROJECT", root), patch.object(
                    builder, "KERNEL", kernel), patch.object(builder, "DIST", root / "dist"), patch.object(
                    builder, "ISO", iso), patch("system_image_policy.trusted_archive",
                    side_effect=archive_after_kernel_changes), patch.object(
                    builder.subprocess, "run", side_effect=fake_rescue), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(builder.build_iso())
                self.assertEqual(clean, (root / "dist/stage/boot/rosti.bin").read_bytes())
                self.assertEqual(b"trusted archive", (root / "dist/stage/boot/system.cpio").read_bytes())

    def test_initramfs_failure_feature_is_not_production(self):
        self.assertEqual(1, self.run_verifier(metadata(["initramfs-failure-test"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
