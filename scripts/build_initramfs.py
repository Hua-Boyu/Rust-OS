"""Deterministic bounded CPIO newc builder; never overwrites an output.

The printed SHA256 identifies the complete archive; it is NOT authentication
unless a trusted kernel build separately pins and checks that expected digest.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat

MAX_ARCHIVE_BYTES = 256 * 1024
MAX_FILE_BYTES = 64 * 1024
MAX_ENTRIES = 32
MAX_PATH = 256
MAX_COMPONENT = 63


def record(name: bytes, mode: int, payload: bytes, inode: int) -> bytes:
    fields = (inode, mode, 0, 0, 1, 0, len(payload), 0, 0, 0, 0, len(name) + 1, 0)
    result = bytearray(b"070701" + b"".join(f"{n:08x}".encode("ascii") for n in fields))
    result.extend(name + b"\0")
    result.extend(b"\0" * (-len(result) % 4))
    result.extend(payload)
    result.extend(b"\0" * (-len(result) % 4))
    return bytes(result)


def build(source: Path) -> bytes:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be a real directory")
    entries: list[tuple[bytes, int, bytes]] = []
    total_payload = 0

    def visit(directory: Path) -> None:
        nonlocal total_payload
        children: list[Path] = []
        # Stream enumeration and enforce the count before sorting or reading data.
        with os.scandir(directory) as iterator:
            for child in iterator:
                if len(entries) + len(children) >= MAX_ENTRIES:
                    raise ValueError("entry limit exceeded")
                children.append(Path(child.path))
        for path in sorted(children, key=lambda p: p.name):
            metadata = path.lstat()
            name = path.relative_to(source).as_posix().encode("ascii")
            if name == b"TRAILER!!!":
                raise ValueError("reserved CPIO trailer name")
            # Reserve one byte for the leading slash in the VFS absolute path.
            if len(name) >= MAX_PATH or any(
                not part or len(part) > MAX_COMPONENT or part in (b".", b"..")
                or any(c < 32 or c >= 127 for c in part)
                for part in name.split(b"/")
            ):
                raise ValueError("unsupported archive path")
            if len(entries) == MAX_ENTRIES:
                raise ValueError("entry limit exceeded")
            if stat.S_ISDIR(metadata.st_mode):
                entries.append((name, 0o40755, b""))
                visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_nlink != 1 or metadata.st_size > MAX_FILE_BYTES:
                    raise ValueError("hardlinked or oversized file")
                with path.open("rb") as stream:
                    payload = stream.read(MAX_FILE_BYTES + 1)
                if len(payload) > MAX_FILE_BYTES:
                    raise ValueError("file grew beyond limit")
                total_payload += len(payload)
                if total_payload > MAX_ARCHIVE_BYTES:
                    raise ValueError("aggregate payload limit exceeded")
                entries.append((name, 0o100644, payload))
            else:
                raise ValueError("symlinks and special files are unsupported")

    visit(source)
    output = bytearray()
    for inode, (name, mode, payload) in enumerate(entries, 1):
        output.extend(record(name, mode, payload, inode))
        if len(output) > MAX_ARCHIVE_BYTES:
            raise ValueError("archive limit exceeded")
    output.extend(record(b"TRAILER!!!", 0, b"", 0))
    output.extend(b"\0" * (-len(output) % 512))
    if len(output) > MAX_ARCHIVE_BYTES:
        raise ValueError("archive limit exceeded")
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # Generated archives belong under canonical dist, not arbitrary/device paths.
    dist = Path(__file__).resolve().parents[1] / "dist"
    output = args.output.absolute()
    if output.suffix != ".cpio" or output.parent.resolve() != dist.resolve():
        parser.error("output must be a new .cpio file directly under repository dist")
    archive = build(args.source)
    dist.mkdir(exist_ok=True)
    with output.open("xb") as stream:
        stream.write(archive)
    print(f"{hashlib.sha256(archive).hexdigest()}  {output} ({len(archive)} bytes)")


if __name__ == "__main__":
    main()
