"""Read-only closeout; run AFTER exclusive canonical acceptance exits."""
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = Path(sys.argv[1]).resolve()
    report = {"overall": "FAIL", "scope": "Partial 11A map alias/GDT prerequisite, NOT CPL3 proof",
              "phase11_release_ready": False, "acceptance": str(path.relative_to(ROOT))}
    try:
        evidence = json.loads(path.read_text())
        assert evidence["overall"] == "PASS"
        assert evidence["phase"] == "11A-prerequisite"
        assert evidence["phase11_release_ready"] is False
        assert evidence["gates_total"] == evidence["gates_passed"] == len(evidence["gates"]) == 56
        assert all(g["status"] == "PASS" and g["exit_code"] == 0 for g in evidence["gates"])
        previous = json.loads((ROOT / "test_results/phase11/acceptance_20261016T154710Z_q3u90_53/acceptance.json").read_text())
        old_names = collections.Counter(g["gate"] for g in previous["gates"])
        new_names = collections.Counter(g["gate"] for g in evidence["gates"])
        assert not old_names - new_names
        assert new_names - old_names == collections.Counter({
            "Phase 11A phase11_snapshot prerequisite": 1, "Phase 11A phase11_gdt prerequisite": 1})
        assert evidence["counts"]["phase11_snapshot"] == {"pass": 1, "fail": 0}
        assert evidence["counts"]["phase11_gdt"] == {"pass": 3, "fail": 0}
        assert evidence["counts"]["host"] == {"pass": 273, "fail": 0}
        runner = load("acceptance_closeout", ROOT / "scripts/phase6_verify.py")
        live = runner.source_snapshot()
        assert live == evidence["source_sha256"]
        report.update(source_freeze_verified=True, source_input_count=len(live), source_sha256=live,
                      gates_passed=56, gates_total=56, counts=evidence["counts"])
        for ram in (128, 512):
            with (path.parent / f"boot_{ram}/boot_results.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == 10 and all(r["status"] == "PASS" for r in rows)
        matrix = list((path.parent / "phase10").glob("*/report.json"))
        assert len(matrix) == 1
        phase10 = json.loads(matrix[0].read_text())
        runner.phase10_evidence(phase10, matrix[0])
        report.update(phase10_scenarios=phase10["scenario_count"], phase10_checks=phase10["check_count"])
        cleanup = []

        def visit(value, target):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("cleanup", "owned_qemu_exited"):
                        assert item is True, (target, key, item)
                        cleanup.append((str(target), key))
                    visit(item, target)
            elif isinstance(value, list):
                for item in value:
                    visit(item, target)

        nested = list(path.parent.rglob("report.json"))
        for target in nested:
            child = json.loads(target.read_text())
            if "guests" in child and child.get("qemu_status") == "PASS":
                assert len(child["guests"]) == 4
            elif child.get("status") == "PASS" and child.get("entry") in ("_start", "b13_handoff"):
                assert child["cleanup"] is True
            else:
                runner.evidence_rows(child, target)
            visit(child, target)
        report.update(nested_reports=len(nested), cleanup_assertions=len(cleanup))
        helpers = load("prior_closeout_helpers", ROOT / "test_results/phase11/verify_checkpoint.py")
        iso = ROOT / evidence["iso"]["path"]
        assert sha(iso) == evidence["iso"]["sha256"]
        kernel = helpers.extract(iso, "/boot/rosti.bin")
        digest = hashlib.sha256(kernel).hexdigest()
        assert digest == evidence["iso"]["kernel_sha256"] == sha(ROOT / "target/target/debug/kernel")
        archive = helpers.extract(iso, "/boot/system.cpio")
        baseline = ROOT / "dist/rosti_phase10b_20261016T120546Z.iso"
        assert sha(baseline) == "117c7b2c0a1f21dc53442a7a1c558b45b8367cb163d405d4d6ef5956596993d8"
        assert helpers.extract(baseline, "/boot/system.cpio") == archive
        prior_iso = ROOT / previous["iso"]["path"]
        assert sha(prior_iso) == previous["iso"]["sha256"]
        old = helpers.sections(helpers.extract(prior_iso, "/boot/rosti.bin"))
        new = helpers.sections(kernel)
        fields = ("file_bytes", "allocated_bytes", "initialized_bytes", "static_span_bytes")
        resources = {"baseline": old, "candidate": new,
                     "delta_from_c347a9c_prerequisite": {k: new[k] - old[k] for k in fields},
                     "peak_heap_bytes": None, "peak_stack_bytes": None,
                     "cpl3_transition_latency": None,
                     "new_tss_bytes": 0, "new_user_or_transition_stack_bytes": 0,
                     "new_user_payload_bytes": 0, "new_page_tables": 0,
                     "new_runtime_heap_allocations_by_design": 0,
                     "gdt_wire_bytes": 24, "idt_wire_bytes": 2048}
        (OUT / "resource_sections.json").write_text(json.dumps(resources, indent=2) + "\n")
        report.update(iso=evidence["iso"], kernel_sha256=digest,
                      archive_sha256=hashlib.sha256(archive).hexdigest(), rollback_media_unchanged=True)
        review = json.loads((OUT / "independent_review.json").read_text())
        assert review["passed"] is True
        # The review schema's hash dictionary is deliberately required by closeout.
        hashes = review["source_sha256"]
        assert hashes
        assert all(sha(ROOT / name) == value for name, value in hashes.items())
        report["review_hashes_verified"] = len(hashes)
        proc = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
            "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^qemu-system' } | Select-Object ProcessId,ParentProcessId,Name) | ConvertTo-Json -Compress"],
            capture_output=True, text=True, check=True, timeout=30)
        remaining = json.loads(proc.stdout) if proc.stdout.strip() else []
        assert remaining == [], remaining
        report.update(qemu_remaining=remaining, overall="PASS")
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        (OUT / "final_verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k not in ("source_sha256", "counts")}, indent=2))


if __name__ == "__main__":
    main()
