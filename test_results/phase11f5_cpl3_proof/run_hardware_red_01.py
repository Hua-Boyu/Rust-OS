"""Meaningful missing-CPL3 RED using unchanged, successfully built F4-ready.
Not attempted CPL3 entry, not new payload execution, and not RED for B-F.
Only disposable local QEMU owned by the inherited driver is launched.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

if sys.flags.optimize:
    raise RuntimeError("optimized RED verification refused")
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from phase6_verify import source_snapshot


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    out = ROOT / "test_results/f5red/r01"
    out.mkdir(parents=True, exist_ok=False)
    before = source_snapshot()
    report = {"overall": "INFRASTRUCTURE_FAIL", "rows": [],
              "scope": "A missing-CPL3 property only; unchanged F4-ready baseline, not attempted USER entry",
              "payload_executed": False, "source_before": before,
              "driver_sha256": sha(Path(__file__)), "red_for_scenarios": ["A_missing_CPL3_only"]}
    started = time.monotonic()
    try:
        review_path = BASE / "reviews/design_review_03.json"
        review = json.loads(review_path.read_bytes())
        admission = json.loads((BASE / "design_review_03_readback_01.json").read_bytes())
        manifest = json.loads((BASE / "design_inputs_03.json").read_bytes())
        need(sha(review_path) == admission["review_sha256"] == "3c73bf80b6c504e6f6c982a90d928f3e66ba8fac18f1174ce000c528289cfd83", "review identity")
        need(review["verdict"] == "APPROVE" and review["complete_scope"] is True and review["blocker_count"] == 0, "no design approval")
        need(sha(BASE / "design.md") == review["approved_design_raw_sha256"], "design drift")
        need(before == manifest["canonical_source_sha256"], "not preimplementation source")
        report["design_review_sha256"] = sha(review_path)
        report["design_raw_sha256"] = sha(BASE / "design.md")
        command = [sys.executable, "-B", str(ROOT / "scripts/f4_ready_guest.py"),
                   "--output-dir", str(out / "baseline")]
        report["command"] = command
        report["watchdog_contract"] = {"inherited_guest_seconds": 120,
                                       "inherited_build_seconds": 600,
                                       "source": "scripts/f4_ready_guest.py:42,216"}
        # Inherited driver owns bounded build/guest lifecycles and finally cleanup;
        # do not introduce a wrapper timeout that kills it ahead of guest cleanup.
        with (out / "driver.log").open("xb") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        report["actual_driver_exit"] = result.returncode
        need(result.returncode == 0, "baseline driver failed, not valid RED")
        baseline_path = out / "baseline/report.json"
        baseline = json.loads(baseline_path.read_bytes())
        need(baseline["overall"] == "MINIMAL_RING0_GREEN" and baseline["build_exit"] == 0
             and baseline["driver_exit"] == 0 and baseline["source_freeze_stable"] is True,
             "baseline not successful built/booted source-stable")
        guests = baseline["guests"]
        need(len(guests) == 2 and {g["ram_mib"] for g in guests} == {128, 512}, "baseline RAM membership")
        for guest in guests:
            ram = guest["ram_mib"]
            need(guest["overall"] == "PASS" and guest["capture_complete"] is True
                 and guest["owned_qemu_exited"] is True, "baseline capture/cleanup")
            argv = guest["command"]
            need(argv[0] == r"C:\Program Files\qemu\qemu-system-i386.exe", "wrong QEMU")
            need(not any(a in argv for a in ("-drive", "-hda", "-hdb", "-blockdev", "-device", "-cdrom")), "unexpected persistent/passthrough media")
            need(argv.count("-m") == 1 and argv[argv.index("-m") + 1] == str(ram), "QEMU RAM")
            need(argv[argv.index("-smp") + 1] == "1", "single vCPU")
            need(argv[argv.index("-kernel") + 1] == str(out / "baseline/kernel.elf"), "owned local kernel identity")
            packet_path = out / f"baseline/ready_{ram}/ready_register_packet.txt"
            packet = bytes.fromhex(packet_path.read_text(encoding="ascii").strip())
            need(len(packet) >= 64, "short actual hardware packet")
            cs = struct.unpack_from("<16I", packet)[10]
            gdtr_limit = guest["cpu"]["GDT"][1]
            need(cs & 0xffff == 8 and gdtr_limit == 39, "did not reach expected unchanged Ring0 baseline")
            cpl3_assertion = cs & 3 == 3
            need(cpl3_assertion is False, "missing-CPL3 RED did not fail the intended assertion")
            report["rows"].append({"identity": "A_missing_CPL3_property", "ram_mib": ram,
                                   "baseline_reached": True, "actual_cs_raw": cs,
                                   "actual_gdtr_limit": gdtr_limit,
                                   "required_property": "actual_saved_or_live_CS_RPL_equals_3",
                                   "property_assertion_passed": cpl3_assertion,
                                   "expected_assertion_failure": True,
                                   "classification": "MISSING_PROPERTY_ASSERTION_FAILURE_NOT_INFRASTRUCTURE",
                                   "register_packet_sha256": sha(packet_path),
                                   "owned_qemu_exited": True, "qemu_command": argv})
        report.update(overall="RED_CONFIRMED", baseline_report_sha256=sha(baseline_path),
                      kernel_sha256=baseline["kernel_sha256"],
                      explicit_missing_property_failures=len(report["rows"]))
    except Exception as error:
        report["error"] = repr(error)
    finally:
        after = source_snapshot()
        report.update(source_after=after, source_freeze_stable=before == after,
                      elapsed_seconds=time.monotonic() - started)
        if before != after:
            report.update(overall="INVALID_SOURCE_DRIFT", error="source changed during baseline RED")
        report["artifact_sha256"] = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
        save(out / "report.json", report)
        print(json.dumps({k: report.get(k) for k in ("overall", "actual_driver_exit", "explicit_missing_property_failures", "source_freeze_stable", "elapsed_seconds", "error")}, indent=2))
    return 0 if report["overall"] == "RED_CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
