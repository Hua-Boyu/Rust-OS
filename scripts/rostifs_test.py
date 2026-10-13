#!/usr/bin/env python3
"""Bounded local RostiFS persistence tests; NEW dist/ media only, never live VMs.

ELF is the default; --iso selects GRUB. Run RAM 128/512 and ELF/ISO sequentially,
not alongside the global boot acceptance runner. Each stage owns a fresh QEMU
process. Formatting runs from the user home, outside the kernel Cargo config.
No existing disk path is accepted. Images and per-stage evidence are retained.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import time

from block_test import BlockHarness, MAGIC, PROJECT

BLOCK_SIZE = 4096
BLOCKS = 256

MOUNT = "/mnt/rosti"
DIRECTORY = MOUNT + "/persist"
NESTED = DIRECTORY + "/nested"
FILE = NESTED + "/message.txt"
INITIAL = "old payload must disappear"
OVERWRITE = "Persistent Rosti data"
APPEND = "-append!"
CONTENTS = OVERWRITE + APPEND
STAGES = ("boot1_write", "boot2_read_delete", "boot3_deleted", "corrupt", "unowned")


def digest(image):
    with image.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--ram", type=int, choices=(128, 512), default=128)
    result.add_argument("--iso", type=Path)
    result.add_argument("--timeout", type=float, default=300)
    result.add_argument("--mkrostifs", type=Path,
                        help="Optional host formatter executable (not a disk path)")
    return result


class OwnedImages:
    """Only exact files registered inside this invocation's exclusive dist child."""
    def __init__(self, project=PROJECT):
        project = project.resolve()
        dist = project / "dist"
        dist.mkdir(exist_ok=True)
        if dist.resolve() != dist or dist.is_symlink():
            raise ValueError("dist must be a real directory inside the project")
        self.directory = Path(tempfile.mkdtemp(prefix="phase9_rostifs_", dir=dist)).resolve()
        self.paths = {name: self.directory / (name + ".img")
                      for name in ("owned", "corrupt", "unowned")}

    def require(self, image, *, new=False):
        image = Path(image)
        if image not in self.paths.values() or image.is_symlink() or image.resolve() != image:
            raise ValueError("refusing media outside this invocation's owned scope")
        if self.directory.is_symlink() or self.directory.resolve() != self.directory:
            raise ValueError("owned directory was redirected")
        if new and image.exists():
            raise FileExistsError("refusing to overwrite existing media")
        if not new and not image.is_file():
            raise ValueError("owned media is missing")
        return image

    def copy_fixture(self, source, kind):
        source = self.require(source)
        if kind not in ("corrupt", "unowned"):
            raise ValueError("invalid fixture kind")
        target = self.require(self.paths[kind], new=True)
        # Exclusive target creation; source never modified.
        with source.open("rb") as inp, target.open("xb") as out:
            while chunk := inp.read(65536):
                out.write(chunk)
        with target.open("r+b") as stream:
            if kind == "unowned":
                stream.write(bytes(512))
            else:
                # Invalidate BOTH independently checksummed root slots. A single
                # damaged root is recoverable by design and is not rejection.
                for block in (1, 2):
                    stream.seek(block * BLOCK_SIZE)
                    stream.write(bytes(8))
        return target


def format_command(args, image):
    tail = ["--test-owned-image", str(image), "--blocks", str(BLOCKS)]
    if args.mkrostifs:
        return [str(args.mkrostifs.resolve()), *tail]
    return ["cargo", "+nightly", "run", "--manifest-path",
            str((PROJECT / "crates/rostifs/Cargo.toml").resolve()),
            "--features", "host-tools", "--bin", "mkrostifs", "--", *tail]


def format_image(args, media, deadline, run):
    image = media.require(media.paths["owned"], new=True)
    command = format_command(args, image)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("HARNESS_FAIL: deadline expired before formatting")
    with (run / "mkrostifs_stdout.txt").open("wb") as stdout, \
            (run / "mkrostifs_stderr.txt").open("wb") as stderr:
        completed = subprocess.run(command, cwd=Path.home(), stdout=stdout, stderr=stderr,
                                   timeout=remaining, check=False)
    (run / "mkrostifs.json").write_text(json.dumps({"argv": command,
        "cwd": str(Path.home()), "exit_code": completed.returncode}, indent=2) + "\n")
    if completed.returncode:
        raise RuntimeError(f"HARNESS_FAIL: mkrostifs exited {completed.returncode}; see formatter logs")
    media.require(image)
    with image.open("rb") as stream:
        marker = stream.read(512)
    if image.stat().st_size != BLOCKS * BLOCK_SIZE or marker != MAGIC + bytes(512 - len(MAGIC)):
        raise AssertionError("formatter must create exact geometry and protected ownership sector")
    return image


def missing(h, path):
    output = h.command("stat " + path)
    h.check(bool(re.fullmatch(r"fs: [^\n]*(?:not found|no such|does not exist|missing)[^\n]*\n?",
                              output, re.IGNORECASE)), path + ": missing, not echo-only evidence")


def validate_host_tools(image, run, deadline):
    """Exercise the shared read-only checker/inspector on guest-written media."""
    before = digest(image)
    results = {}
    for tool in ("rostifsck", "rostifs-inspect"):
        command = ["cargo", "+nightly", "run", "--manifest-path",
                   str(PROJECT / "crates/rostifs/Cargo.toml"), "--features", "host-tools",
                   "--bin", tool, "--", "--test-owned-image", str(image)]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("host tool deadline expired")
        result = subprocess.run(command, cwd=Path.home(), capture_output=True,
                                timeout=remaining, check=False)
        (run / (tool + "_stdout.txt")).write_bytes(result.stdout)
        (run / (tool + "_stderr.txt")).write_bytes(result.stderr)
        if result.returncode != 0 or not result.stdout.startswith(b"OK version=1 "):
            raise AssertionError(tool + " must validate guest-written media")
        results[tool] = {"exit_code": result.returncode, "stdout": result.stdout.decode(errors="replace")}
    if digest(image) != before:
        raise AssertionError("checker/inspector modified media")
    if "/persist/nested/message.txt" not in results["rostifs-inspect"]["stdout"]:
        raise AssertionError("host inspector must expose guest-written nested file")
    return results


def console_only(h):
    output = h.command("fdlist")
    rows = [line for line in output.splitlines() if line.strip()]
    h.check(len(rows) == 3 and
            all(re.fullmatch(rf"fd {index} {kind} rights 0 offset 0 refs 0", row)
                for index, kind, row in zip(range(3),
                    ("console-in", "console-out", "console-out"), rows)),
            "fdlist contains only reserved console descriptors 0/1/2")


def mounted(h):
    h.success("cd " + MOUNT)
    h.exact("pwd", MOUNT)
    h.success("cd /")


def boot1(h):
    mounted(h)
    before = h.memory("before persistent writes")
    info = h.command("rostifs")
    match = re.search(r"filesystem metadata: (\d+) bytes; mount allocations: 0; cache: 0", info)
    h.check(match is not None and "format 1 mounted /mnt/rosti" in info,
            "mounted format and bounded allocation diagnostics")
    h.report["rostifs_metadata_bytes"] = int(match[1])
    h.exact("diskwrite 8", "block: raw writes refused while RostiFS is mounted")
    h.exact("ls " + MOUNT, "")
    h.success("mkdir " + DIRECTORY)
    h.success("mkdir " + NESTED)
    h.success("write " + FILE + " " + INITIAL)
    h.exact("cat " + FILE, INITIAL)
    h.success("write " + FILE + " " + OVERWRITE)
    h.exact("cat " + FILE, OVERWRITE)
    h.success("append " + FILE + " " + APPEND)
    h.exact("cat " + FILE, CONTENTS)
    output = h.command("stat " + FILE)
    h.check(re.search(r"(?m)^type: file$", output) is not None and
            re.search(rf"(?m)^size: {len(CONTENTS.encode())} bytes$", output) is not None,
            "persistent file type and byte length are exact")
    console_only(h)
    after = h.memory("after persistent writes")
    h.check(before["used"] == after["used"] and before["growth_pages"] == after["growth_pages"],
            "persistent traversal and writes allocate no heap or growth pages")
    # Guest-requested reboot, followed by the separate process stages. Reopen
    # and read only: no replacement write can manufacture persistence evidence.
    h.reboot()
    mounted(h)
    h.exact("cat " + FILE, CONTENTS)
    console_only(h)


def boot2(h):
    # No mkdir/touch/write/append before read. Data must come from prior media.
    mounted(h)
    h.exact("cat " + FILE, CONTENTS)
    h.exact("ls " + NESTED, "message.txt")
    console_only(h)
    h.success("rm " + FILE)
    missing(h, FILE)
    h.success("rmdir " + NESTED)
    h.success("rmdir " + DIRECTORY)
    h.exact("ls " + MOUNT, "")
    console_only(h)


def boot3(h):
    # Verification only: never repair/recreate the deleted paths.
    mounted(h)
    missing(h, DIRECTORY)
    missing(h, FILE)
    h.exact("ls " + MOUNT, "")
    console_only(h)


def rejected(h):
    missing(h, MOUNT)
    h.exact("pwd", "/")
    h.success("write /recovery.txt Recovery RAMFS")
    h.exact("cat /recovery.txt", "Recovery RAMFS")
    h.success("rm /recovery.txt")
    missing(h, "/recovery.txt")
    console_only(h)
    h.check(not re.search(r"PANIC:|PAGE FAULT|page fault:|CPU exception", h.text()),
            "mount rejection retains a fault-free recovery shell")


def run_stage(args, run, name, image, media, deadline, exercise, factory=BlockHarness):
    media.require(image)
    folder = run / name
    folder.mkdir()
    h = factory(args, folder, image, deadline)
    try:
        h.start()
        exercise(h)
        h.check(h.proc is not None and h.proc.poll() is None, "owned guest alive after stage")
        h.check(not re.search(r"PANIC:|PAGE FAULT|page fault:|CPU exception", h.text()),
                "no serial kernel fault")
        h.report["overall"] = "PASS"
    except (Exception, KeyboardInterrupt) as error:
        h.report["error"] = f"{type(error).__name__}: {error}"
        if h.proc is not None and h.proc.poll() is None and getattr(h, "sock", None) is not None:
            try:
                h.report["failure_disk_status"] = h.command("disk")
            except Exception as diagnostic:
                h.report["diagnostic_error"] = str(diagnostic)
    finally:
        # Harness.close can throw on socket shutdown before killing the guest.
        # Always reap exactly our Popen, including that failure path.
        try:
            h.close()
        except Exception as error:
            h.report["cleanup_error"] = str(error)
            h.report["overall"] = "FAIL"
        finally:
            if h.proc is not None:
                try:
                    if h.proc.poll() is None:
                        h.proc.kill()
                    h.proc.wait(timeout=5)
                except Exception as error:
                    h.report["cleanup_error"] = str(error)
                    h.report["overall"] = "FAIL"
            exited = h.proc is not None and h.proc.poll() is not None
            h.report["owned_qemu_exited"] = exited
            h.report["checks"].append({"name": "owned QEMU process terminated", "pass": exited})
            if not exited or not all(c.get("pass") is True for c in h.report["checks"]):
                h.report["overall"] = "FAIL"
            h.report["stage"] = name
            h.report["image"] = str(image)
            h.report["check_count"] = len(h.report["checks"])
            h.report["command_count"] = len(h.report["commands"])
            (folder / "report.json").write_text(json.dumps(h.report, indent=2) + "\n")
    return h.report


def validate_stages(stages):
    """Fail closed on missing, duplicate, reordered or incomplete stage evidence."""
    if [stage.get("stage") for stage in stages] != list(STAGES):
        return False
    pids = [stage.get("qemu_pid") for stage in stages]
    # PID reuse is possible after reap; independent Popen lifecycle is the
    # proof, not a universal uniqueness guarantee on operating-system PIDs.
    return all(isinstance(pid, int) and pid > 0 for pid in pids) and all(
        stage.get("overall") == "PASS" and stage.get("owned_qemu_exited") is True and
        bool(stage.get("checks")) and
        stage.get("check_count") == len(stage["checks"]) and
        stage.get("command_count") == len(stage.get("commands", [])) and
        all(check.get("pass") is True for check in stage["checks"])
        for stage in stages)


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        cli.error("timeout must be finite and positive")
    args.live, args.stress = None, False
    root = (args.output_dir or PROJECT / "test_results/phase9").resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f"rostifs_ram{args.ram}_", dir=root))
    started = time.monotonic()
    deadline = started + args.timeout
    report = {"overall": "FAIL", "ram_mib": args.ram,
              "boot_path": "ISO" if args.iso else "ELF",
              "iso": str(args.iso.resolve()) if args.iso else None,
              "checks": [], "scenarios": [], "binary_fixture": "not required; not exercised"}

    def check(value, name, **details):
        report["checks"].append({"name": name, "pass": bool(value), **details})
        if not value:
            raise AssertionError(name)

    try:
        media = OwnedImages()
        report["disk_dir"] = str(media.directory)
        owned = format_image(args, media, deadline, run)
        corrupt = media.copy_fixture(owned, "corrupt")
        unowned = media.copy_fixture(owned, "unowned")
        baselines = {kind: digest(path) for kind, path in
                     (("corrupt", corrupt), ("unowned", unowned))}
        for name, image, exercise in zip(STAGES,
                (owned, owned, owned, corrupt, unowned), (boot1, boot2, boot3, rejected, rejected)):
            stage = run_stage(args, run, name, image, media, deadline, exercise)
            report["scenarios"].append(stage)
            report["checks"].extend({**c, "name": name + ": " + c["name"]} for c in stage["checks"])
            check(stage["overall"] == "PASS", name + ": complete independent process stage",
                  error=stage.get("error", stage.get("cleanup_error")))
            if name == "boot1_write":
                report["after_write_sha256"] = digest(owned)
                report["host_tools"] = validate_host_tools(owned, run, deadline)
                check(True, "host checker and inspector validate guest-written media without modification")
            elif name == "boot2_read_delete":
                report["after_delete_sha256"] = digest(owned)
            elif name == "boot3_deleted":
                check(digest(owned) == report["after_delete_sha256"], "boot3 verification makes no disk writes")
        for kind in ("corrupt", "unowned"):
            check(digest(media.require(media.paths[kind])) == baselines[kind],
                  "entire " + kind + " image unchanged", sha256=baselines[kind])
        with owned.open("rb") as stream:
            check(stream.read(512) == MAGIC + bytes(512 - len(MAGIC)), "ownership sector preserved exactly")
        check(validate_stages(report["scenarios"]), "all five independent stages complete and cleaned up")
        check(all(c["pass"] for c in report["checks"]), "all checks pass")
        report["overall"] = "PASS"
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["elapsed_s"] = round(time.monotonic() - started, 3)
        report["check_count"] = len(report["checks"])
        report["pass_count"] = sum(c["pass"] for c in report["checks"])
        (run / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['overall']}: RostiFS {report['pass_count']}/{report['check_count']} checks; evidence: {run}")
    if "error" in report:
        print(report["error"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
