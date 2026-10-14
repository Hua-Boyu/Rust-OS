#!/usr/bin/env python3
"""Fail-closed local acceptance. Never deploys or changes authentication.

Run from the canonical repository with the existing Rust/QEMU/WSL tools.
Evidence lives beneath test_results/phase9_5; logs and counts are real subprocess
results. Preserve the currently built ISO before packaging the replacement.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parent.parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot():
    paths = set()
    for directory, suffixes in (("src", {".rs", ".s"}),
                                ("tests_kernel/src", {".rs"}),
                                ("scripts", {".py", ".sh"})):
        paths.update(p for p in (PROJECT / directory).rglob("*")
                     if p.is_file() and p.suffix in suffixes)
    for name in ("Cargo.toml", "Cargo.lock", "linker.ld", "target.json",
                 "rust-toolchain.toml", ".cargo/config.toml",
                 "tests_kernel/Cargo.toml", "tests_kernel/Cargo.lock",
                 "tests_kernel/.cargo/config.toml"):
        path = PROJECT / name
        if path.is_file():
            paths.add(path)
    # Portable storage code and tool inputs are release inputs too. Never hash
    # generated target/ trees or include them as source-freeze dependencies.
    for crate in (PROJECT / "crates").glob("*"):
        if not crate.is_dir():
            continue
        paths.update(p for p in (crate / "src").rglob("*.rs") if p.is_file())
        paths.update(p for p in (crate / "tests").rglob("*.rs") if p.is_file())
        for name in ("Cargo.toml", "Cargo.lock", ".cargo/config.toml"):
            path = crate / name
            if path.is_file():
                paths.add(path)
    return {p.relative_to(PROJECT).as_posix(): sha256(p) for p in sorted(paths)}


def evidence_rows(evidence, path):
    """An explicit PASS plus nonempty all-true rows, never a default status."""
    if not isinstance(evidence, dict) or evidence.get("overall") != "PASS":
        raise RuntimeError(f"failed or invalid harness report: {path}")
    field = "checks" if "checks" in evidence else "results"
    rows = evidence.get(field)
    if not isinstance(rows, list) or not rows or any(
            not isinstance(row, dict) or row.get("pass") is not True for row in rows):
        raise RuntimeError(f"failed, missing or empty harness rows: {path}")
    for name in ("check_count", "pass_count"):
        if name in evidence and evidence[name] != len(rows):
            raise RuntimeError(f"inconsistent declared harness count: {path}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parent = (args.output_dir or PROJECT / "test_results" / "phase9_5").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f"acceptance_{stamp}_", dir=parent))
    report = {"phase": "9.5", "timestamp_utc": stamp, "overall": "RUNNING", "gates": [], "counts": {}}
    features_active = False

    def gate(name, command, timeout=180, cwd=PROJECT):
        log = run / (f"{len(report['gates']) + 1:02d}_" + re.sub(r"[^a-z0-9]+", "_", name.lower()) + ".log")
        with log.open("wb") as output:
            try:
                result = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                        timeout=timeout, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                output.write((f"\nHARNESS_FAIL: {error}\n").encode())
                code = -1
        text = log.read_text(errors="replace")
        report["gates"].append({"gate": name, "command": command, "exit_code": code,
                                "status": "PASS" if code == 0 else "FAIL", "log": str(log.relative_to(PROJECT))})
        (run / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{'PASS' if code == 0 else 'FAIL'}: {name}", flush=True)
        if code != 0:
            print(text[-6000:], flush=True)
            raise RuntimeError(name)
        return text

    py = sys.executable
    def script(name, *args):
        return [py, str(PROJECT / "scripts" / name), *map(str, args)]

    try:
        report["source_base"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
        report["source_sha256"] = source_snapshot()
        gate("kernel formatting", ["cargo", "fmt", "--check"])
        gate("host formatting", ["cargo", "+nightly", "fmt", "--manifest-path", str(PROJECT / "tests_kernel/Cargo.toml"), "--check"])
        text = gate("host tests", ["cargo", "+nightly", "test", "--manifest-path", str(PROJECT / "tests_kernel/Cargo.toml")], cwd=Path.home())
        match = re.search(r"test result: ok\. (\d+) passed; (\d+) failed", text)
        if not match:
            raise RuntimeError("host test totals not found")
        report["counts"]["host"] = {"pass": int(match[1]), "fail": int(match[2])}
        manifest = str(PROJECT / "crates/rostifs/Cargo.toml")
        gate("RostiFS formatting", ["cargo", "+nightly", "fmt", "--manifest-path", manifest, "--check"])
        text = gate("RostiFS host and crash recovery tests", ["cargo", "+nightly", "test", "--manifest-path", manifest, "--", "--nocapture"], timeout=300, cwd=Path.home())
        totals = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed", text)
        if not totals:
            raise RuntimeError("RostiFS test totals not found")
        report["counts"]["rostifs_host"] = {"pass": sum(int(p) for p, _ in totals), "fail": sum(int(f) for _, f in totals)}
        text = gate("RostiFS host tool safety and integration", ["cargo", "+nightly", "test", "--manifest-path", manifest, "--features", "host-tools", "--test", "host_tools"], timeout=180, cwd=Path.home())
        match = re.search(r"test result: ok\. (\d+) passed; (\d+) failed", text)
        if not match:
            raise RuntimeError("host tool test totals not found")
        report["counts"]["rostifs_tools"] = {"pass": int(match[1]), "fail": int(match[2])}
        text = gate("RostiFS read boundary and transfer regressions", ["cargo", "+nightly", "test", "--manifest-path", manifest, "--features", "host-tools", "--test", "read_performance"], timeout=180, cwd=Path.home())
        match = re.search(r"test result: ok\. (\d+) passed; (\d+) failed", text)
        if not match or int(match[1]) != 4 or int(match[2]) != 0:
            raise RuntimeError("RostiFS read regression totals missing or incomplete")
        report["counts"]["rostifs_read"] = {"pass": int(match[1]), "fail": int(match[2])}
        text = gate("RostiFS write preservation regressions", ["cargo", "+nightly", "test", "--manifest-path", manifest, "--features", "host-tools", "--test", "write_preservation"], timeout=180, cwd=Path.home())
        match = re.search(r"test result: ok\. (\d+) passed; (\d+) failed", text)
        if not match or int(match[1]) != 3 or int(match[2]) != 0:
            raise RuntimeError("RostiFS write regression totals missing or incomplete")
        report["counts"]["rostifs_write"] = {"pass": int(match[1]), "fail": int(match[2])}
        gate("Python media reader regressions", script("test_fs_harness.py"))
        gate("acceptance runner regressions", script("test_acceptance_harness.py"))
        gate("RostiFS harness regressions", script("test_rostifs_harness.py"))
        gate("Phase 9.5 benchmark contracts", script("test_phase9_5_bench.py"))
        features_active = True
        gate("build read fault fixture", ["cargo", "build", "--features", "paging-fault-test"])
        gate("CPU read faults 128 and 512", script("paging_test.py", "--fault", "--output-dir", run / "read_fault"))
        gate("build write fault fixture", ["cargo", "build", "--features", "paging-write-fault-test"])
        gate("CPU write faults 128 and 512", script("paging_test.py", "--write-fault", "--output-dir", run / "write_fault"))
        gate("production build", ["cargo", "build"])
        features_active = False
        gate("production feature and fault exclusion", script("verify_production.py"))
        text = gate("ELF validation", script("validate_elf.py", PROJECT / "target/target/debug/kernel"))
        report["counts"]["elf"] = {"pass": len(re.findall(r"^PASS:", text, re.M)), "fail": len(re.findall(r"^FAIL:", text, re.M))}
        for memory in (128, 512):
            output = run / f"boot_{memory}"
            gate(f"ten ELF boots {memory} MiB", script("boot_test.py", "--runs", 10, "--timeout", 3, "--memory", memory, "--output-dir", output), timeout=90)
            with (output / "boot_results.csv").open(newline="") as capture:
                rows = list(csv.DictReader(capture))
            if len(rows) != 10 or any(r.get("status") != "PASS" for r in rows):
                raise RuntimeError(f"incomplete or failed ten-boot matrix: {memory}")
            report["counts"][f"boot_{memory}"] = {"pass": sum(r["status"] == "PASS" for r in rows), "fail": sum(r["status"] != "PASS" for r in rows)}
        gate("paging stability twenty ELF boots", script("paging_test.py", "--runs", 10, "--output-dir", run / "paging"), timeout=180)
        gate("keyboard integration", script("keyboard_test.py"), timeout=150)
        gate("VGA backspace ELF", script("backspace_test.py"), timeout=150)
        for memory in (128, 512):
            gate(f"filesystem growth OOM ELF {memory} MiB", script("fs_test.py", "--ram", memory, "--stress", "--output-dir", run / f"fs_elf_{memory}"), timeout=210)
            gate(f"block persistence ELF {memory} MiB", script("block_test.py", "--ram", memory, "--output-dir", run / f"block_elf_{memory}"), timeout=240)
            gate(f"RostiFS persistence ELF {memory} MiB", script("rostifs_test.py", "--ram", memory, "--output-dir", run / f"rostifs_elf_{memory}"), timeout=300)
        current_iso = PROJECT / "dist/rosti.iso"
        if current_iso.exists():
            digest = sha256(current_iso)
            backup = PROJECT / "dist" / f"rosti_preserved_{digest[:16]}.iso"
            if backup.exists() and sha256(backup) != digest:
                raise RuntimeError("rollback ISO name collision")
            if not backup.exists():
                shutil.copy2(current_iso, backup)
            report["rollback_iso"] = {"path": str(backup.relative_to(PROJECT)), "sha256": sha256(backup)}
        gate("GRUB ISO build and boot", script("build-proxmox-iso.py"), timeout=240)
        gate("ISO paging 128 and 512", script("paging_test.py", "--iso", current_iso, "--output-dir", run / "iso_paging"), timeout=90)
        gate("VGA backspace ISO", script("backspace_test.py", "--iso", current_iso), timeout=150)
        for memory in (128, 512):
            gate(f"filesystem growth OOM ISO {memory} MiB", script("fs_test.py", "--iso", current_iso, "--ram", memory, "--stress", "--output-dir", run / f"fs_iso_{memory}"), timeout=210)
            gate(f"block persistence ISO {memory} MiB", script("block_test.py", "--iso", current_iso, "--ram", memory, "--output-dir", run / f"block_iso_{memory}"), timeout=240)
            gate(f"RostiFS persistence ISO {memory} MiB", script("rostifs_test.py", "--iso", current_iso, "--ram", memory, "--output-dir", run / f"rostifs_iso_{memory}"), timeout=300)
        final_hashes = source_snapshot()
        if final_hashes != report["source_sha256"]:
            raise RuntimeError("source changed during acceptance; rerun against stable source")
        required = {"read_fault": 2, "write_fault": 2, "paging": 20, "iso_paging": 2}
        for boot in ("elf", "iso"):
            for memory in (128, 512):
                required[f"fs_{boot}_{memory}"] = 102
                required[f"block_{boot}_{memory}"] = 98
                required[f"rostifs_{boot}_{memory}"] = 168
        for directory, expected in required.items():
            # Each harness creates one invocation-owned child. Stage reports are
            # deeper and must not substitute for its complete aggregate report.
            paths = list((run / directory).glob("*/report.json"))
            if len(paths) != 1:
                raise RuntimeError(f"missing or ambiguous mandatory report: {directory}")
            rows = evidence_rows(json.loads(paths[0].read_text()), paths[0])
            if len(rows) != expected:
                raise RuntimeError(f"incomplete mandatory checks: {directory}: {len(rows)}/{expected}")
        for p in run.rglob("report.json"):
            evidence = json.loads(p.read_text())
            key = str(p.relative_to(run))
            evidence_rows(evidence, key)
            if "checks" in evidence:
                checks = evidence["checks"]
                if not checks or any(c.get("pass") is not True for c in checks):
                    raise RuntimeError(f"failed or empty harness checks: {key}")
                report["counts"][key] = {"pass": sum(c["pass"] for c in checks), "fail": sum(not c["pass"] for c in checks), "commands": evidence.get("command_count")}
            elif "results" in evidence:
                rows = evidence["results"]
                if not rows or any(r.get("pass") is not True for r in rows):
                    raise RuntimeError(f"failed or empty harness results: {key}")
                report["counts"][key] = {"pass": sum(r["pass"] for r in rows), "fail": sum(not r["pass"] for r in rows)}
        versioned = PROJECT / "dist" / f"rosti_phase9_5_{stamp}.iso"
        if versioned.exists():
            raise RuntimeError("refusing to overwrite versioned ISO")
        shutil.copy2(current_iso, versioned)
        report["iso"] = {"name": versioned.name, "path": str(versioned.relative_to(PROJECT)), "sha256": sha256(versioned), "bytes": versioned.stat().st_size,
                          "kernel_sha256": sha256(PROJECT / "target/target/debug/kernel")}
        report["overall"] = "PASS"
    except Exception as error:
        report["overall"] = "FAIL"
        report["error"] = str(error)
    finally:
        if features_active:
            with (run / "restore_production.log").open("wb") as output:
                restored = subprocess.run(["cargo", "build"], cwd=PROJECT, stdout=output, stderr=subprocess.STDOUT, timeout=180)
            report["production_restored"] = restored.returncode == 0
        report["gates_passed"] = sum(g["status"] == "PASS" for g in report["gates"])
        report["gates_total"] = len(report["gates"])
        (run / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['overall']}: {report['gates_passed']}/{report['gates_total']} gates; {run / 'acceptance.json'}", flush=True)
    if "error" in report:
        print(report["error"], flush=True)
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
