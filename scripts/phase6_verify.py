#!/usr/bin/env python3
"""Fail-closed local acceptance. Never deploys or changes authentication.

Run from the canonical repository with the existing Rust/QEMU/WSL tools.
Evidence lives beneath test_results/phase11; logs and counts are real subprocess
results. Preserve the currently built ISO before packaging the replacement.
"""
import argparse
from contextlib import contextmanager
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


class AcceptanceBusy(RuntimeError):
    """Another process owns this checkout's complete acceptance pipeline."""


@contextmanager
def acceptance_lock(project):
    # Never unlink this file: replacing the inode could create two owners.
    # OS handle lifetime releases the lock even after a crashed/terminated owner.
    path = Path(project) / "dist/.phase6_acceptance.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AcceptanceBusy(f"acceptance already running for {project}") from error
        # Owner metadata is diagnostic only, never a PID-based stale-lock oracle.
        handle.truncate(1)
        handle.write(json.dumps({"pid": os.getpid()}).encode("ascii"))
        handle.flush()
        yield
    finally:
        handle.close()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot():
    paths = set()
    for directory, suffixes in (("src", {".rs", ".s"}),
                                ("tests_kernel/src", {".rs"}),
                                ("tests_b26", {".rs", ".s", ".S", ".ld", ".json", ".toml", ".lock"}),
                                ("scripts", {".py", ".sh", ".rs", ".s", ".S", ".ld", ".json", ".toml", ".lock"})):
        paths.update(p for p in (PROJECT / directory).rglob("*")
                     if p.is_file() and p.suffix in suffixes
                     and not {"target", "__pycache__"}.intersection(p.relative_to(PROJECT / directory).parts))
    # Trusted system image bytes are build inputs, including extensionless and
    # binary assets. Do not filter these by suffix.
    paths.update(p for p in (PROJECT / "system").rglob("*") if p.is_file())
    for name in (".gitattributes", "Cargo.toml", "Cargo.lock", "linker.ld", "target.json",
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


# This explicit required set is the guest contract, not inferred from evidence.
# Coordinate any host-only fault-injection split with the Phase 10 harness owner;
# never silently shrink this list to match an incomplete report.
PHASE10_CASES = (
    "absent", "trusted", "bad-digest", "truncated", "malformed", "oversize",
    "duplicate", "invalid-descriptor", "missing-storage", "corrupt-rostifs",
    "mount-collision", "mount-failure", "resource-exhaustion", "reboot-after-failure",
)


def phase10_evidence(evidence, path, *, required_cases=PHASE10_CASES):
    """Validate the exact matrix and invocation-owned, fully completed children."""
    path = Path(path)

    def completed(report, target):
        rows = evidence_rows(report, target)
        if "checks" not in report or any(
                type(report.get(name)) is not int or report[name] != len(rows)
                for name in ("check_count", "pass_count")):
            raise RuntimeError(f"missing or inconsistent Phase 10 check totals: {target}")
        return rows

    completed(evidence, path)
    if not required_cases or len(set(required_cases)) != len(required_cases):
        raise RuntimeError("invalid Phase 10 required case contract")
    expected = {(boot, ram, case) for boot in ("elf", "iso")
                for ram in (128, 512) for case in required_cases}
    scenarios = evidence.get("scenarios")
    if (not isinstance(scenarios, list) or len(scenarios) != len(expected)
            or any(type(evidence.get(name)) is not int or evidence[name] != len(expected)
                   for name in ("expected_scenarios", "scenario_count"))):
        raise RuntimeError("incomplete mandatory Phase 10 scenario totals")
    observed = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise RuntimeError("invalid Phase 10 scenario row")
        identity = (scenario.get("boot"), scenario.get("ram_mib"), scenario.get("case"))
        if (any(not isinstance(value, (str, int)) for value in identity)
                or type(identity[1]) is not int or identity not in expected
                or identity in observed or scenario.get("overall") != "PASS"
                or scenario.get("cleanup") is not True):
            raise RuntimeError("missing, duplicate, failed or unclean Phase 10 configuration")
        observed.add(identity)
        boot, ram, case = identity
        child = path.parent / f"{boot}_{ram}_{case}" / "report.json"
        declared = scenario.get("report")
        if (not isinstance(declared, str) or not declared
                or Path(declared).resolve() != child.resolve()
                or not child.resolve().is_relative_to(path.parent.resolve())):
            raise RuntimeError("Phase 10 guest report is not invocation-owned")
        try:
            guest = json.loads(child.read_text())
        except (OSError, ValueError) as error:
            raise RuntimeError(f"missing or unreadable Phase 10 guest report: {child}") from error
        completed(guest, child)
        if guest.get("cleanup") is not True:
            raise RuntimeError(f"unverified Phase 10 guest cleanup: {child}")
    if observed != expected:
        raise RuntimeError("incomplete mandatory Phase 10 matrix")
    return scenarios


def _run_acceptance():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parent = (args.output_dir or PROJECT / "test_results" / "phase11").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f"acceptance_{stamp}_", dir=parent))
    report = {"phase": "11A-prerequisite", "phase11_release_ready": False,
              "timestamp_utc": stamp, "overall": "RUNNING", "gates": [], "counts": {}}
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
        # Separate filtered invocations prove every Phase 9.6 safety family ran;
        # a successful broad suite (or a renamed-away filter) cannot substitute.
        for key, filter_name, host_manifest in (
                ("b11", "b11_", "tests_kernel/Cargo.toml"),
                ("b18", "b18_inventory_tests::", "tests_kernel/Cargo.toml"),
                ("b26", "b26_", "tests_b26/Cargo.toml")):
            text = gate(f"Phase 9.6 {key.upper()} host safety regressions",
                        ["cargo", "+nightly", "test", "--manifest-path", str(PROJECT / host_manifest),
                         "--lib", filter_name, "--", "--test-threads=1"], cwd=Path.home())
            totals = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored", text)
            observed = re.findall(r"^test (\S+) \.\.\. ok\s*$", text, re.M)
            if (len(totals) != 1 or int(totals[0][0]) == 0
                    or int(totals[0][1]) != 0 or int(totals[0][2]) != 0
                    or len(observed) != int(totals[0][0])
                    or len(set(observed)) != len(observed)
                    or any(filter_name not in name for name in observed)):
                raise RuntimeError(f"{key.upper()} safety test totals missing, empty or inconsistent")
            report["counts"][key] = {"pass": len(observed), "fail": 0}
        # This is only the first memory-permission prerequisite, NOT CPL3
        # acceptance. Keep the exact test identities mandatory and fail closed.
        text = gate("Phase 11A effective permission prerequisite",
                    ["cargo", "+nightly", "test", "--manifest-path",
                     str(PROJECT / "tests_kernel/Cargo.toml"), "--lib",
                     "phase11_permission_tests::", "--", "--test-threads=1"], cwd=Path.home())
        prefix = "memory::paging::phase11_permission_tests::"
        required_permissions = {prefix + name for name in (
            "phase11_permissions_intersect_both_paging_levels",
            "phase11_unowned_user_map_is_rejected_before_table_allocation",
            "phase11_nonpresent_map_is_rejected_without_side_effects",
            "phase11_identity_maps_remain_supervisor_at_128_and_512_mib",
            "phase11_rejected_requests_preserve_existing_table_and_mapping",
        )}
        observed = re.findall(r"^test (\S+) \.\.\. ok\s*$", text, re.M)
        totals = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored", text)
        if (totals != [("5", "0", "0")] or len(observed) != 5
                or set(observed) != required_permissions):
            raise RuntimeError("Phase 11 permission prerequisite tests missing or inconsistent")
        report["counts"]["phase11_permissions"] = {"pass": len(observed), "fail": 0}
        # B19 alias closure and descriptor encoding only: no CPL3 readiness claim.
        for key, filter_name, required in (
                ("phase11_snapshot", "heap_growth_maps_one_page_on_demand",
                 {"heap_growth_maps_one_page_on_demand"}),
                ("phase11_gdt", "phase11_gdt_tests::", {
                    "gdt::phase11_gdt_tests::phase11_gdt_nonzero_base_does_not_contaminate_access",
                    "gdt::phase11_gdt_tests::phase11_gdt_wire_fields_and_limit_boundaries",
                    "gdt::phase11_gdt_tests::phase11_gdt_privilege_presence_and_tss_type",
                })):
            command = ["cargo", "+nightly", "test", "--manifest-path",
                       str(PROJECT / "tests_kernel/Cargo.toml"), "--lib", filter_name,
                       "--", "--test-threads=1"]
            if key == "phase11_snapshot":
                command.append("--exact")
            text = gate(f"Phase 11A {key} prerequisite", command, cwd=Path.home())
            observed = re.findall(r"^test (\S+) \.\.\. ok\s*$", text, re.M)
            totals = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored", text)
            if (totals != [(str(len(required)), "0", "0")]
                    or len(observed) != len(required) or set(observed) != required):
                raise RuntimeError(f"{key} prerequisite tests missing or inconsistent")
            report["counts"][key] = {"pass": len(observed), "fail": 0}
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
        gate("Phase 9.6 boot metadata harness contracts", script("test_boot_metadata_harness.py"))
        gate("system image policy contracts", script("test_system_image_policy.py"))
        gate("Phase 10B initramfs builder contracts", script("test_build_initramfs.py"))
        gate("Phase 10B initramfs harness contracts", script("test_phase10_initramfs_harness.py"))
        b13_host_path = run / "b13_host.json"
        gate("Phase 9.6 B13 boot entry host contracts",
             script("test_b13_boot.py", "--report", b13_host_path))
        b13_host = json.loads(b13_host_path.read_text())
        if (b13_host.get("status") != "PASS" or type(b13_host.get("tests_run")) is not int
                or b13_host["tests_run"] < 3 or b13_host.get("failures") != []):
            raise RuntimeError("B13 host entry contracts missing, empty or failed")
        report["counts"]["b13_host"] = {"pass": b13_host["tests_run"], "fail": 0}
        features_active = True
        gate("build read fault fixture", ["cargo", "build", "--features", "paging-fault-test"])
        gate("CPU read faults 128 and 512", script("paging_test.py", "--fault", "--output-dir", run / "read_fault"))
        gate("build write fault fixture", ["cargo", "build", "--features", "paging-write-fault-test"])
        gate("CPU write faults 128 and 512", script("paging_test.py", "--write-fault", "--output-dir", run / "write_fault"))
        gate("build initramfs failure fixture", ["cargo", "build", "--features", "initramfs-failure-test"])
        fixture_kernel = PROJECT / "dist" / "phase10b_fixture_kernel"
        fixture_kernel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / "target/target/debug/kernel", fixture_kernel)
        report["phase10_fixture_kernel"] = {"path": str(fixture_kernel.relative_to(PROJECT)),
                                            "sha256": sha256(fixture_kernel)}
        gate("production build", ["cargo", "build"])
        features_active = False
        gate("production fixture policy contracts", script("test_production_fixture_policy.py"))
        gate("production feature and fault exclusion", script("verify_production.py"))
        if sha256(fixture_kernel) == sha256(PROJECT / "target/target/debug/kernel"):
            raise RuntimeError("Phase 10B fixture kernel is not feature-distinct from production")
        b13_output = run / "b13_qemu"
        gate("Phase 9.6 B13 privileged boot entry and production handoff",
             script("b13_boot_fixture.py", "--build", "--run-qemu", "--production-kernel",
                    PROJECT / "target/target/debug/kernel", "--output-dir", b13_output), timeout=600)
        b13_path = b13_output / "report.json"
        b13 = json.loads(b13_path.read_text())
        guests = b13.get("guests")
        if (b13.get("status") != "PASS" or b13.get("qemu_status") != "PASS"
                or b13.get("inspection", {}).get("status") != "PASS"
                or not isinstance(guests, list) or len(guests) != 4):
            raise RuntimeError("B13 privileged entry proof missing or incomplete")
        b13_reports = {b13_path}
        expected_guests = {(entry, ram) for entry in ("b13_handoff", "_start") for ram in (128, 512)}
        observed_guests = set()
        for guest in guests:
            if guest.get("status") != "PASS" or guest.get("cleanup") is not True:
                raise RuntimeError("B13 failed guest or unverified cleanup")
            identity = (guest.get("entry"), guest.get("memory_mib"))
            if identity not in expected_guests or identity in observed_guests:
                raise RuntimeError("B13 missing or duplicate guest configuration")
            observed_guests.add(identity)
            kind = "fixture" if identity[0] == "b13_handoff" else "production"
            child = b13_output / f"{kind}_{identity[1]}" / "report.json"
            if json.loads(child.read_text()) != guest:
                raise RuntimeError("B13 aggregate/guest evidence mismatch")
            b13_reports.add(child)
        report["counts"]["b13_qemu"] = {"pass": len(observed_guests), "fail": 0}
        gate("Phase 9.6 B13 injection transport contracts", script("test_b13_entry_inject.py"))
        b13_report_hashes = {path: sha256(path) for path in b13_reports | {b13_host_path}}
        metadata_output = run / "boot_metadata"
        gate("Phase 9.6 integrated boot metadata ELF and GRUB safety",
             script("boot_metadata_test.py", "--boot", "both", "--ram", 128, 512,
                    "--output-dir", metadata_output), timeout=1800)
        metadata_paths = list(metadata_output.glob("*/report.json"))
        if len(metadata_paths) != 1:
            raise RuntimeError("missing or ambiguous mandatory boot metadata report")
        metadata_path = metadata_paths[0]
        metadata = json.loads(metadata_path.read_text())
        metadata_rows = evidence_rows(metadata, metadata_path)
        fixtures = ("nomodule", "invalidmagic", "null", "headerbad", "mmaptruncated",
                    "modulein-growth", "module-overlap", "countedoverflow", "validmodule",
                    "reservedgrowth", "frameexhaustion")
        expected_metadata = {(boot, ram, fixture) for boot in ("elf", "iso")
                             for ram in (128, 512) for fixture in fixtures}
        scenarios = metadata.get("scenarios")
        if (not isinstance(scenarios, list) or len(scenarios) != len(expected_metadata)
                or metadata.get("expected_scenarios") != len(expected_metadata)
                or metadata.get("scenario_count") != len(expected_metadata)):
            raise RuntimeError("incomplete mandatory boot metadata scenario totals")
        observed_metadata = set()
        for scenario in scenarios:
            identity = (scenario.get("boot"), scenario.get("ram_mib"), scenario.get("name"))
            if (identity not in expected_metadata or identity in observed_metadata
                    or scenario.get("overall") != "PASS"):
                raise RuntimeError("missing, duplicate or failed boot metadata configuration")
            observed_metadata.add(identity)
            boot, ram, fixture = identity
            child = metadata_path.parent / f"{boot}_{ram}_{fixture}" / "report.json"
            if Path(scenario.get("report", "")).resolve() != child.resolve():
                raise RuntimeError("boot metadata guest report is not invocation-owned")
            evidence_rows(json.loads(child.read_text()), child)
        report["counts"]["boot_metadata"] = {"pass": len(metadata_rows), "fail": 0}
        report["counts"]["boot_metadata_scenarios"] = {"pass": len(observed_metadata), "fail": 0}
        metadata_digest = sha256(metadata_path)
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
        phase10_output = run / "phase10"
        gate("Phase 10B trusted initramfs guest matrix",
             script("phase10_initramfs_test.py", "--output-dir", phase10_output), timeout=5400)
        phase10_paths = list(phase10_output.glob("*/report.json"))
        if len(phase10_paths) != 1:
            raise RuntimeError("missing or ambiguous mandatory Phase 10B report")
        phase10_path = phase10_paths[0]
        phase10_scenarios = phase10_evidence(json.loads(phase10_path.read_text()), phase10_path)
        report["counts"]["phase10_scenarios"] = {"pass": len(phase10_scenarios), "fail": 0}
        phase10_digest = sha256(phase10_path)
        final_hashes = source_snapshot()
        if final_hashes != report["source_sha256"]:
            raise RuntimeError("source changed during acceptance; rerun against stable source")
        if any(sha256(path) != digest for path, digest in b13_report_hashes.items()):
            raise RuntimeError("B13 validated evidence changed during acceptance")
        if sha256(metadata_path) != metadata_digest:
            raise RuntimeError("boot metadata validated matrix changed during acceptance")
        phase10_scenarios = phase10_evidence(json.loads(phase10_path.read_text()), phase10_path)
        if sha256(phase10_path) != phase10_digest:
            raise RuntimeError("Phase 10B validated matrix changed during acceptance")
        required = {"read_fault": 2, "write_fault": 2, "paging": 20, "iso_paging": 2}
        for boot in ("elf", "iso"):
            for memory in (128, 512):
                # Capturing the pre-existing root adds one VGA-prompt check;
                # every former assertion remains, with exact baseline cleanup.
                required[f"fs_{boot}_{memory}"] = 103
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
            # These exact reports use B13's status/guests schema and were fully
            # validated above; never exempt any other discovered report.
            if p in b13_reports:
                continue
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
        versioned = PROJECT / "dist" / f"rosti_phase11a_prerequisite_{stamp}.iso"
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


def main():
    try:
        with acceptance_lock(PROJECT):
            # Includes failure-fixture production restoration and final evidence.
            return _run_acceptance()
    except AcceptanceBusy as error:
        print(f"HARNESS_BUSY: {error}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
