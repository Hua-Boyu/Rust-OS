"""Sequential B13 stress replay: N identical strict fixture runs per RAM size.

Detects intermittent interrupt-window faults; not a proof of absence.
Reuses the strict run_injected oracle (exact P*16 debug bytes, exit 33,
ordered markers, owned cleanup) — no weakened assertions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from b13_entry_inject import elf_symbols, run_injected

ROOT = Path(__file__).resolve().parent.parent
KERNEL = ROOT / "target/b13_fixture/target/debug/b13-boot-fixture"


def fixture_mutation(gdb, before):
    case = elf_symbols(KERNEL)["b13_case"]["address"]
    gdb.write(case, bytes(4))
    gdb.set_registers(esi=0xB13)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    kernel_sha = hashlib.sha256(KERNEL.read_bytes()).hexdigest()
    rows = []
    overall = "PASS"
    for ram in (128, 512):
        for run in range(1, args.runs + 1):
            status = "FAIL"
            error = None
            try:
                report = run_injected(
                    KERNEL, out / f"r{ram}_{run:02d}", fixture_mutation,
                    entry="b13_handoff", memory=ram,
                    debug_bytes=b"P" * 16, expected_exit=33)
                status = report["status"]
            except Exception as error_:
                error = f"{type(error_).__name__}: {error_}"
            row = {"ram_mib": ram, "run": run, "fixture_sha256": kernel_sha,
                   "status": status, "error": error,
                   "marker_bytes": 16 if status == "PASS" else None,
                   "exit_code": 33 if status == "PASS" else None,
                   "cleanup": True if status == "PASS" else None,
                   "evidence": str(out / f"r{ram}_{run:02d}" / "report.json")}
            rows.append(row)
            if status != "PASS":
                overall = "FAIL"
            print(json.dumps(row), flush=True)
            time.sleep(0.05)
    summary = {"fixture_sha256": kernel_sha, "runs_per_size": args.runs,
               "sizes_mib": [128, 512], "total": len(rows),
               "passed": sum(r["status"] == "PASS" for r in rows),
               "status": overall, "rows": rows}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": overall, "evidence": str(out / "summary.json")}))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
