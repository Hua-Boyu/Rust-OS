#!/usr/bin/env python3
"""Verify hardware paging and a deliberate page fault in local QEMU.

Use --fault only with `cargo build --features paging-fault-test`.
Rebuild WITHOUT features before ISO creation/deployment.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
QEMU = r"C:\Program Files\qemu\qemu-system-i386.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault", action="store_true")
    parser.add_argument("--write-fault", action="store_true", help="With paging-write-fault-test build")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--iso", type=Path)
    args = parser.parse_args()
    args.fault = args.fault or args.write_fault
    root = PROJECT / "test_results" / "phase4" / (time.strftime("%Y%m%d_%H%M%S") + ("_fault" if args.fault else "_paging"))
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for memory in (128, 512):
        for iteration in range(args.runs):
            run = root / f"ram_{memory}_run_{iteration + 1}"
            run.mkdir()
            serial = run / "serial.txt"
            log = run / "qemu_log.txt"
            boot = ["-cdrom", str(args.iso.resolve()), "-boot", "d"] if args.iso else [
                "-kernel", str(PROJECT / "target" / "target" / "debug" / "kernel")]
            q = subprocess.Popen([QEMU, *boot, "-display", "none", "-no-reboot", "-m", str(memory),
                                  "-serial", f"file:{serial}", "-monitor", "none",
                                  "-d", "int,guest_errors", "-D", str(log)])
            try:
                end = time.monotonic() + 12
                marker = "page fault:" if args.fault else "rosti>"
                while time.monotonic() < end and q.poll() is None:
                    if serial.exists() and marker in serial.read_text(errors="replace"):
                        break
                    time.sleep(0.1)
                time.sleep(0.5)
                text = serial.read_text(errors="replace") if serial.exists() else ""
                trace = log.read_text(errors="replace") if log.exists() else ""
                checks = {
                    "ordered_boot": 0 <= text.find("ROSTI: entered kernel_main") < text.find("ROSTI: boot complete"),
                    "paging_enabled": "ROSTI: paging enabled (CR0.PG, identity map)" in text,
                    "no_validation_failure": "paging validation FAILED" not in text,
                    "no_panic": "PANIC:" not in text,
                    "no_triple_fault": "triple fault" not in trace.lower(),
                    "guest_alive": q.poll() is None,
                }
                if args.fault:
                    checks["fault_triggered"] = "fault test trigger" in text
                    expected = (r"page fault: code 0x0002 present=false write=true user=false cr2=0x00000000 rip=0x[0-9a-f]+"
                                if args.write_fault else r"page fault: code 0x0000 present=false write=false user=false cr2=0xfffff000 rip=0x[0-9a-f]+")
                    checks["correct_cpu_error_and_cr2"] = bool(re.search(expected, text))
                    checks["fault_exactly_once"] = text.count("page fault:") == 1
                    checks["no_other_exception"] = "CPU exception" not in text
                else:
                    checks["shell_ready"] = "rosti>" in text
                    checks["production_build"] = "fault test trigger" not in text
                results.append({"ram_mib": memory, "iteration": iteration + 1, "checks": checks, "pass": all(checks.values()), "serial": serial.relative_to(PROJECT).as_posix()})
                print(f"{'PASS' if all(checks.values()) else 'FAIL'}: {memory} MiB run {iteration + 1}; failed={[k for k, v in checks.items() if not v]}")
                if not all(checks.values()):
                    print(text)
            finally:
                if q.poll() is None:
                    q.kill()
                q.wait(timeout=5)
    (root / "report.json").write_text(json.dumps({"fault_build": args.fault, "results": results, "overall": "PASS" if all(r["pass"] for r in results) else "FAIL"}, indent=2) + "\n")
    print(f"Evidence: {root}")
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
