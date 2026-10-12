#!/usr/bin/env python3
"""Deterministic, bounded QEMU boot-test runner for the Rosti kernel.

Design:
- Runs the compiled kernel ELF via QEMU's multiboot ELF loader, headless.
- Serial output is captured to a per-run file (`-serial file:`); QEMU flushes
  the file device per byte, so output survives process termination (verified
  empirically in the previous session).
- Strict end-to-end timeout: the harness kills ONLY the QEMU process it
  started. No orphan processes, no shared temp files.
- PASS requires both markers in order:
    ROSTI: entered kernel_main
    ROSTI: boot complete
- FAIL is classified as KERNEL_FAULT (triple fault / reboot / panic in the
  QEMU debug log, or kernel entered but init never completed) or
  HARNESS_FAIL (QEMU could not start, output capture failed, timeout without
  any marker).
- Logs for failed runs are preserved; each run gets its own directory.

Usage:
  python scripts/boot_test.py [--runs N] [--timeout SECONDS] [--kernel PATH]
Exit code: 0 if all runs pass, 1 otherwise. Results CSV printed and written
to test_results/boot_results.csv.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"
DEFAULT_KERNEL = str(PROJECT / "target" / "target" / "debug" / "kernel")
MARKER_ENTER = "ROSTI: entered kernel_main"
MARKER_DONE = "ROSTI: boot complete"
FAULT_PATTERNS = [
    ("triple fault", "triple fault"),
    ("rebooting", "reboot loop"),
    ("shutdown on triple", "triple fault"),
]

RESULTS_DIR = PROJECT / "test_results"


def run_once(kernel: Path, run_id: str, timeout: int, memory: int = 128) -> dict:
    run_dir = RESULTS_DIR / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    serial_path = run_dir / "serial.txt"
    log_path = run_dir / "qemu_log.txt"

    cmd = [
        QEMU,
        "-kernel", str(kernel),
        "-display", "none",
        "-no-reboot",
        "-no-shutdown",
        "-m", str(memory),
        "-serial", f"file:{serial_path}",
        "-monitor", "none",
        "-d", "int,guest_errors",
        "-D", str(log_path),
    ]

    result = {
        "run": run_id,
        "status": "",
        "class": "",
        "markers": "",
        "exit": "",
        "elapsed_s": "",
        "dir": str(run_dir),
    }

    t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL)
    except OSError as e:
        result["status"] = "FAIL"
        result["class"] = "HARNESS_FAIL"
        result["markers"] = "qemu launch failed: %s" % e
        return result

    killed = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        killed = True

    elapsed = time.time() - t0
    result["elapsed_s"] = f"{elapsed:.1f}"
    result["exit"] = "killed@timeout" if killed else str(proc.returncode)

    # QEMU's file: serial device flushes per byte; read after termination.
    serial = ""
    if serial_path.exists():
        serial = serial_path.read_text(errors="replace")
    qemu_log = ""
    if log_path.exists():
        qemu_log = log_path.read_text(errors="replace")

    fault = None
    for pat, name in FAULT_PATTERNS:
        if pat in qemu_log.lower():
            fault = name
            break

    enter_ok = MARKER_ENTER in serial
    done_ok = MARKER_DONE in serial
    order_ok = enter_ok and done_ok and serial.index(MARKER_ENTER) < serial.index(MARKER_DONE)
    result["markers"] = ("enter+done" if order_ok else
                         ("enter-only" if enter_ok else "none"))

    if order_ok and not fault:
        result["status"] = "PASS"
        result["class"] = ""
    elif fault:
        result["status"] = "FAIL"
        result["class"] = f"KERNEL_FAULT ({fault})"
    elif enter_ok:
        result["status"] = "FAIL"
        result["class"] = "KERNEL_FAULT (init incomplete)"
    else:
        # No markers at all: distinguish harness vs kernel.
        if not serial.strip() and not qemu_log.strip():
            result["status"] = "FAIL"
            result["class"] = "HARNESS_FAIL (no output captured)"
        else:
            result["status"] = "FAIL"
            result["class"] = "KERNEL_FAULT (never entered kernel_main)"

    if result["status"] == "FAIL":
        print(f"--- run {run_id} {result['class']} ---")
        print("serial:", serial.strip() or "(empty)")
        print("qemu log:", qemu_log.strip() or "(empty)")
    return result


def main():
    global RESULTS_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--kernel", default=DEFAULT_KERNEL)
    ap.add_argument("--memory", type=int, choices=(128, 512), default=128)
    ap.add_argument("--output-dir", type=Path, help="Preserve prior runs by using a separate evidence directory")
    args = ap.parse_args()
    if args.output_dir:
        RESULTS_DIR = args.output_dir.resolve()

    kernel = Path(args.kernel)
    if not kernel.exists():
        print(f"HARNESS_FAIL: kernel binary not found: {kernel}")
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(1, args.runs + 1):
        r = run_once(kernel, f"{i:02d}", args.timeout, args.memory)
        rows.append(r)
        print(f"run {r['run']}: {r['status']} {r['class']} "
              f"markers={r['markers']} exit={r['exit']} t={r['elapsed_s']}s")

    csv_path = RESULTS_DIR / "boot_results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["run", "status", "class", "markers",
                                          "exit", "elapsed_s", "dir"])
        w.writeheader()
        w.writerows(rows)

    passed = sum(1 for r in rows if r["status"] == "PASS")
    print(f"\n{passed}/{len(rows)} passed. Results: {csv_path}")

    # Orphan check: no qemu processes should remain from this harness.
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq qemu-system-i386.exe"],
            capture_output=True, text=True).stdout
        if "qemu-system-i386" in out:
            print("WARNING: orphaned QEMU process still running!")
            sys.exit(1)
    except OSError:
        pass

    sys.exit(0 if passed == len(rows) else 1)


if __name__ == "__main__":
    main()
