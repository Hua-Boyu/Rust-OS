"""Host checks for deterministic image generation (not kernel acceptance)."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from build_initramfs import build, MAX_FILE_BYTES


class BuilderTests(unittest.TestCase):
    def test_standard_wire_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "hello.txt").write_bytes(b"hello rosti")
            first = build(root)
            (root / "hello.txt").touch()
            self.assertEqual(first, build(root))
            self.assertEqual(len(first) % 512, 0)
            self.assertEqual(first[:6], b"070701")
            self.assertEqual(int(first[14:22], 16), 0o100644)
            self.assertEqual(int(first[54:62], 16), 11)
            self.assertEqual(int(first[94:102], 16), 10)
            self.assertEqual(int(first[102:110], 16), 0)
            self.assertEqual(first[110:120], b"hello.txt\0")
            self.assertEqual(first[120:131], b"hello rosti")
            self.assertEqual(first[242:253], b"TRAILER!!!\0")
            self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(build(root)).digest())

    def test_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = build(Path(temp))
            self.assertEqual(len(archive), 512)
            self.assertEqual(archive[110:121], b"TRAILER!!!\0")

    def test_limits_and_control_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "large"
            path.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
            with self.assertRaises(ValueError):
                build(root)
            path.unlink()
            (root / ("a" * 64)).write_bytes(b"")
            with self.assertRaises(ValueError):
                build(root)

    def test_reserved_trailer_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "TRAILER!!!"
            path.write_bytes(b"not a trailer")
            with self.assertRaisesRegex(ValueError, "reserved CPIO trailer"):
                build(root)
            path.unlink()
            path.mkdir()
            with self.assertRaisesRegex(ValueError, "reserved CPIO trailer"):
                build(root)

    def test_entry_and_archive_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(32):
                (root / f"f{index:02}").write_bytes(b"")
            build(root)
            (root / "extra").write_bytes(b"")
            with self.assertRaises(ValueError):
                build(root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(3):
                (root / f"f{index}").write_bytes(b"x" * MAX_FILE_BYTES)
            build(root)
            (root / "f3").write_bytes(b"x" * MAX_FILE_BYTES)
            with self.assertRaises(ValueError):
                build(root)

    def test_vfs_path_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root
            for segment in ("a" * 63, "b" * 63, "c" * 63):
                parent = parent / segment
                parent.mkdir()
            leaf = parent / ("d" * 63)
            leaf.write_bytes(b"x")
            self.assertEqual(len(leaf.relative_to(root).as_posix()), 255)
            build(root)
            leaf.unlink()
            parent = parent / ("d" * 62)
            parent.mkdir()
            leaf = parent / "e"
            leaf.write_bytes(b"x")
            self.assertEqual(len(leaf.relative_to(root).as_posix()), 256)
            with self.assertRaises(ValueError):
                build(root)

    def test_directory_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sub").mkdir()
            (root / "sub" / "note").write_bytes(b"note")
            archive = build(root)
            self.assertLess(archive.index(b"sub\0"), archive.index(b"sub/note\0"))


if __name__ == "__main__":
    unittest.main()
