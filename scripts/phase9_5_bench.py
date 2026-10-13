#!/usr/bin/env python3
"""Phase 9.5 host-observed QEMU baseline; exclusive dist images, no live mode.

Timings include emulation, serial polling and QMP overhead, NOT guest cycles.
Enter-to-prompt includes the existing 65 ms key pacing and 20 ms polling.
This is a repeatable small-file workload, not device bandwidth measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import subprocess
import tempfile
import time

from block_test import BlockHarness, PROJECT
from rostifs_test import OwnedImages, format_image


def elf_metrics(path):
    data = path.read_bytes()
    if data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("expected little-endian ELF32")
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    offset, stride, count, names_index = header[6], header[11], header[12], header[13]
    sections = [struct.unpack_from("<IIIIIIIIII", data, offset + i * stride)
                for i in range(count)]
    names_row = sections[names_index]
    names = data[names_row[4]:names_row[4] + names_row[5]]
    named = {names[row[0]:].split(b"\0", 1)[0].decode(): row for row in sections}
    allocated = [row for row in sections if row[2] & 2]
    symbols = {}
    for row in sections:
        if row[1] != 2:
            continue
        strings_row = sections[row[6]]
        strings = data[strings_row[4]:strings_row[4] + strings_row[5]]
        for pos in range(row[4], row[4] + row[5], row[9]):
            name, value, size, _, _, _ = struct.unpack_from("<IIIBBH", data, pos)
            symbol = strings[name:].split(b"\0", 1)[0].decode(errors="replace")
            if size and any(part in symbol for part in
                            ("FRAME_ALLOC", "FILESYSTEM", "BACKEND", "DESCRIPTORS", "BOOT_STACK")):
                symbols[symbol] = {"address": value, "bytes": size}
    return {"file_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "section_bytes": {name: row[5] for name, row in named.items()},
            "allocated_section_bytes": sum(row[5] for row in allocated),
            "static_address_span_bytes": max(row[3] + row[5] for row in allocated)
                                         - min(row[3] for row in allocated),
            "initialized_allocated_bytes": sum(row[5] for row in allocated if row[1] != 8),
            "selected_symbols": symbols}


def disk_counters(output):
    match = re.search(r"reads (\d+) writes (\d+).*?bytes (\d+)", output)
    if not match:
        raise AssertionError("ATA transfer counters missing")
    return dict(zip(("reads", "writes", "bytes"), map(int, match.groups())))


class TimedHarness(BlockHarness):
    def key(self, name):
        if name == "ret":
            self.enter_started = time.perf_counter_ns()
        return super().key(name)

    def wait(self, predicate, label, seconds=12):
        result = super().wait(predicate, label, seconds)
        if label.startswith("next prompt after"):
            self.prompt_observed = time.perf_counter_ns()
        return result

    def command(self, typed, edit=False):
        started = time.perf_counter_ns()
        result = super().command(typed, edit)
        self.report["commands"][-1]["timing"] = {
            "host_full_command_ns": time.perf_counter_ns() - started,
            "host_enter_to_prompt_ns": self.prompt_observed - self.enter_started}
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--iso", type=Path)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 10:
        parser.error("repeats must be 1..10")
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error("refusing to overwrite benchmark evidence; choose a new output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"overall": "RUNNING", "clock": "host time.perf_counter_ns",
              "timing_scope": "host-observed QEMU; key pacing and serial polling included",
              "startup_timing_scope": "start to validated mounted prompt; includes QMP query-block",
              "kernel_metrics_scope": "local ELF; ISO payload identity not established" if args.iso else "booted local ELF",
              "guest_operation_timing_ns": None,
              "mount_latency_ns": None, "peak_stack_bytes": None,
              "peak_transient_allocations_bytes": None,
              "shell_parser_isolated_ns": None, "flush_command_count": None,
              "runs": []}
    try:
        report["kernel"] = elf_metrics(PROJECT / "target/target/debug/kernel")
        report["rustc"] = subprocess.check_output(["rustc", "+nightly", "-Vv"], text=True)
        if args.iso:
            image = args.iso.resolve()
            report["iso"] = {"path": str(image), "bytes": image.stat().st_size,
                             "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
        for ram in (128, 512):
            for repeat in range(args.repeats):
                run = Path(tempfile.mkdtemp(prefix=f"bench_{ram}_{repeat}_", dir=args.output.parent))
                options = argparse.Namespace(ram=ram, timeout=180, iso=args.iso,
                                             live=None, stress=False, mkrostifs=None)
                media = OwnedImages()
                deadline = time.monotonic() + options.timeout
                image = format_image(options, media, deadline, run)
                h = TimedHarness(options, run, image, deadline)
                row = {"ram_mib": ram, "repeat": repeat,
                       "overall": "FAIL", "evidence": str(run / "report.json")}
                report["runs"].append(row)
                h.report["overall"] = "FAIL"
                workload_error = None
                cleanup_errors = []
                try:
                    started = time.perf_counter_ns()
                    h.start()
                    h.check("ROSTI: RostiFS mounted at /mnt/rosti" in h.text(),
                            "startup mount marker")
                    h.report["host_start_to_mounted_prompt_ns"] = time.perf_counter_ns() - started
                    before = h.memory("before")
                    c0 = disk_counters(h.command("disk"))
                    operations = []
                    for label, command, expected in (
                        ("traverse", "cd /mnt/rosti", ""),
                        ("create", "touch sample", ""),
                        ("write", "write sample " + "x" * 64, ""),
                        ("read", "cat sample", "x" * 64),
                        ("append", "append sample tail", ""),
                        ("list", "ls", "sample"),
                        ("delete", "rm sample", "")):
                        if expected:
                            h.exact(command, expected)
                        else:
                            h.success(command)
                        operations.append({"operation": label, **h.report["commands"][-1]["timing"]})
                    c1 = disk_counters(h.command("disk"))
                    after = h.memory("after")
                    h.check(before["used"] == after["used"], "no retained heap growth")
                    h.check(before["growth_pages"] == after["growth_pages"], "no growth pages")
                    row.update({
                        "host_start_to_mounted_prompt_ns": h.report["host_start_to_mounted_prompt_ns"],
                        "memory_before": before, "memory_after": after,
                        "ata_delta": {key: c1[key] - c0[key] for key in c0},
                        "operations": operations})
                except Exception as error:
                    workload_error = f"{type(error).__name__}: {error}"
                    h.report["error"] = workload_error
                finally:
                    # Keep our own handle: reused close may fail before process cleanup.
                    proc = h.proc
                    try:
                        try:
                            h.close()
                        except Exception as error:
                            cleanup_errors.append(f"{type(error).__name__}: {error}")
                        try:
                            if not h.report.get("owned_qemu_exited") or (proc is not None and proc.poll() is None):
                                cleanup_errors.append("owned QEMU did not exit")
                            if proc is not None and cleanup_errors:
                                if proc.poll() is None:
                                    proc.kill()
                                proc.wait(timeout=5)
                            h.report["owned_qemu_exited"] = proc is None or proc.poll() is not None
                        except Exception as error:
                            h.report["owned_qemu_exited"] = False
                            cleanup_errors.append(f"{type(error).__name__}: {error}")
                    finally:
                        if cleanup_errors:
                            h.report["cleanup_error"] = "; ".join(cleanup_errors)
                        if workload_error is None and not cleanup_errors:
                            h.report["overall"] = "PASS"
                        row["overall"] = h.report["overall"]
                        (run / "report.json").write_text(json.dumps(h.report, indent=2) + "\n")
                if workload_error or cleanup_errors:
                    raise RuntimeError("; ".join(filter(None, [workload_error, *cleanup_errors])))
        if elf_metrics(PROJECT / "target/target/debug/kernel")["sha256"] != report["kernel"]["sha256"]:
            raise AssertionError("kernel changed during benchmark")
        if args.iso and hashlib.sha256(args.iso.resolve().read_bytes()).hexdigest() != report["iso"]["sha256"]:
            raise AssertionError("ISO changed during benchmark")
        report["artifact_freeze_verified"] = True
        report["summary"] = {}
        for ram in (128, 512):
            rows = [row for row in report["runs"] if row["ram_mib"] == ram]
            report["summary"][str(ram)] = {
                "host_boot_median_ns": statistics.median(row["host_start_to_mounted_prompt_ns"] for row in rows),
                "operation_enter_to_prompt_median_ns": {
                    op: statistics.median(item["host_enter_to_prompt_ns"] for row in rows
                                          for item in row["operations"] if item["operation"] == op)
                    for op in ("traverse", "create", "write", "read", "append", "list", "delete")}}
        report["overall"] = "PASS"
    except Exception as error:
        report["overall"] = "FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['overall']}: {args.output}")
    if "error" in report:
        print(report["error"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
