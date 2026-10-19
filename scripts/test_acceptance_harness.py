"""Acceptance source-freeze regressions; subprocesses are fixtures, not live gates."""
import contextlib
import ast
import csv
import importlib.util
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("acceptance", Path(__file__).with_name("phase6_verify.py"))
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class AcceptanceLockTests(unittest.TestCase):
    def child(self, root, body):
        source = str(Path(__file__).with_name("phase6_verify.py").resolve())
        setup = ("import importlib.util,sys;from pathlib import Path;"
                 f"s=importlib.util.spec_from_file_location('acceptance',{source!r});"
                 "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                 f"m.PROJECT=Path({str(root)!r});")
        # Windows venv redirectors launch another interpreter process; killing
        # that wrapper is not killing the lock owner. Exercise the real host.
        return [getattr(sys, "_base_executable", sys.executable), "-B", "-u", "-c", setup + body]

    def test_contending_main_refuses_before_reports_or_builds(self):
        self.assertTrue(hasattr(acceptance, "acceptance_lock"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with acceptance.acceptance_lock(root):
                result = subprocess.run(self.child(root,
                    "m._run_acceptance=lambda:print('UNSAFE_WORK_STARTED') or 0;"
                    "sys.exit(m.main())"), capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("acceptance already running", result.stdout)
            self.assertNotIn("UNSAFE_WORK_STARTED", result.stdout)
            self.assertFalse((root / "test_results").exists())

    def test_os_lock_releases_after_normal_and_forced_owner_exit(self):
        self.assertTrue(hasattr(acceptance, "acceptance_lock"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for forced in (False, True):
                with self.subTest(forced=forced):
                    owner = subprocess.Popen(self.child(root,
                        "exec(\"with m.acceptance_lock(m.PROJECT):\\n print('LOCKED',flush=True)\\n sys.stdin.buffer.read(1)\")"),
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        self.assertEqual(owner.stdout.readline().strip(), b"LOCKED")
                        with self.assertRaises(acceptance.AcceptanceBusy):
                            with acceptance.acceptance_lock(root):
                                self.fail("a second owner acquired the lock")
                        if forced:
                            owner.terminate()
                        else:
                            owner.stdin.write(b"x")
                            owner.stdin.flush()
                        owner.wait(timeout=15)
                        with acceptance.acceptance_lock(root):
                            pass
                        self.assertTrue((root / "dist/.phase6_acceptance.lock").is_file())
                    finally:
                        if owner.poll() is None:
                            owner.kill()
                            owner.wait(timeout=15)
                        owner.stdin.close()
                        owner.stdout.close()
                        owner.stderr.close()


class Phase10EvidenceTests(unittest.TestCase):
    def fixture(self, root, cases=("absent", "trusted")):
        checks = [{"pass": True}]
        scenarios = []
        for boot in ("elf", "iso"):
            for ram in (128, 512):
                for case in cases:
                    child = root / f"{boot}_{ram}_{case}" / "report.json"
                    child.parent.mkdir(parents=True)
                    child.write_text(json.dumps({"overall": "PASS", "checks": checks,
                        "check_count": 1, "pass_count": 1, "cleanup": True}))
                    scenarios.append({"boot": boot, "ram_mib": ram, "case": case,
                        "overall": "PASS", "cleanup": True, "report": str(child)})
        return {"overall": "PASS", "checks": checks, "check_count": 1, "pass_count": 1,
                "scenarios": scenarios, "scenario_count": len(scenarios),
                "expected_scenarios": len(scenarios)}

    def test_explicit_complete_phase10_matrix_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = self.fixture(root)
            validate = lambda report: acceptance.phase10_evidence(
                report, root / "report.json", required_cases=("absent", "trusted"))
            self.assertEqual(len(validate(evidence)), 8)
            mutations = [lambda r: r.pop("overall"), lambda r: r.update(overall="RUNNING"),
                lambda r: r.update(overall="FAIL"), lambda r: r.update(checks=[]),
                lambda r: r.update(checks=[{"pass": 1}]),
                lambda r: r.update(checks=[{"pass": False}]),
                lambda r: r.pop("check_count"), lambda r: r.pop("pass_count"),
                lambda r: r.update(check_count=True), lambda r: r.update(pass_count=2),
                lambda r: r.pop("scenario_count"), lambda r: r.update(expected_scenarios=7),
                lambda r: r["scenarios"].pop(),
                lambda r: r["scenarios"].__setitem__(0, r["scenarios"][1]),
                lambda r: r["scenarios"][0].update(case="unknown"),
                lambda r: r["scenarios"][0].update(ram_mib="128"),
                lambda r: r["scenarios"][0].update(overall="RUNNING"),
                lambda r: r["scenarios"][0].pop("cleanup"),
                lambda r: r["scenarios"][0].update(cleanup=1),
                lambda r: r["scenarios"][0].update(report=str(root.parent / "report.json"))]
            for index, mutate in enumerate(mutations):
                bad = json.loads(json.dumps(evidence))
                mutate(bad)
                with self.subTest(mutation=index), self.assertRaises(RuntimeError):
                    validate(bad)
            child = Path(evidence["scenarios"][0]["report"])
            for bad in ({"overall": "PASS", "checks": []},
                        {"overall": "PASS", "checks": [{"pass": True}],
                         "check_count": 1, "pass_count": 1, "cleanup": False}):
                child.write_text(json.dumps(bad))
                with self.subTest(child=bad), self.assertRaises(RuntimeError):
                    validate(evidence)
            child.unlink()
            with self.assertRaises(RuntimeError):
                validate(evidence)


class SourceFreezeTests(unittest.TestCase):
    def declared_numeric_map_names(self):
        source = (Path(__file__).resolve().parents[1] / "src/memory/numeric_map_authority_tests.rs").read_text()
        names = re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
        self.assertEqual(len(names), 9)
        self.assertEqual(len(set(names)), 9)
        return ["memory::paging::numeric_map_authority_tests::" + name for name in names]

    def test_numeric_map_authority_prerequisite_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "numeric_map_authority_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--lib", commands[0])
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_numeric_map"], {"pass": 9, "fail": 0})

    def test_numeric_map_authority_bad_identities_cannot_publish(self):
        names = self.declared_numeric_map_names()
        def result(rows, passed=None, failed=0, ignored=0):
            return ("".join(f"test {name} ... ok\n" for name in rows)
                    + f"test result: ok. {len(rows) if passed is None else passed} passed; {failed} failed; {ignored} ignored\n")
        outputs = ["", result([]), result(names[:-1]), result(names + [names[0] + "_extra"]),
                   result(names[:-1] + [names[0]]), result(names[:-1] + [names[0] + "_substitute"]),
                   result(names, 8), result(names, 10), result(names[:-1], 9),
                   result(names, failed=1), result(names, ignored=1),
                   "".join(f"test {name} ... ok\n" for name in names), result(names) + result(names)]
        for text in outputs:
            with self.subTest(text=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"numeric_map_authority_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("phase11_numeric_map", self.last_report["counts"])

    def test_numeric_map_authority_identities_match_real_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        rows = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                and len(node.elts) == 3 and isinstance(node.elts[0], ast.Constant)
                and node.elts[0].value == "phase11_numeric_map"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(ast.literal_eval(rows[0].elts[1]), "numeric_map_authority_tests::")
        required = rows[0].elts[2]
        prefix = ast.literal_eval(required.elt.left)
        wired = [prefix + ast.literal_eval(n) for n in required.generators[0].iter.elts]
        self.assertEqual(len(wired), 9)
        self.assertEqual(set(wired), set(self.declared_numeric_map_names()))
        fixture = Path(__file__).with_name("numeric_map_api_probe.rs")
        self.assertIn(fixture.relative_to(acceptance.PROJECT).as_posix(), acceptance.source_snapshot())

    def declared_generation_families(self):
        root = Path(__file__).resolve().parents[1]
        families = {}
        for key, file, prefix, count in (
            ("phase11_generation_ownership", "generation_ownership_tests.rs", "memory::paging::generation_ownership_tests::", 8),
            ("phase11_generation_ledger", "frame.rs", "memory::frame::generation_ledger_tests::", 6),
            ("phase11_generation_boundaries", "generation_boundary_tests.rs", "memory::frame::generation_boundary_tests::", 6),
        ):
            source = (root / "src/memory" / file).read_text()
            if file == "frame.rs":
                source = source.split("mod generation_ledger_tests {", 1)[1]
            names = re.findall(r"(?m)^\s*#\[test\]\s*\n\s*fn (\w+)\(", source)
            self.assertEqual(len(names), count)
            self.assertEqual(len(set(names)), count)
            filter_name = prefix.split("::")[-2] + "::"
            families[key] = (filter_name, [prefix + name for name in names])
        return families

    def declared_b26_detector_names(self):
        source = (Path(__file__).resolve().parents[1] / "src/memory/ownership_observation_tests.rs").read_text()
        names = re.findall(r"(?m)^#\[test\]\s*\nfn (b26_\w+)\(", source)
        self.assertEqual(len(names), 5)
        self.assertEqual(len(set(names)), 5)
        return ["memory::ownership_observation_tests::" + name for name in names]

    def declared_structure_lifetime_names(self):
        source = (Path(__file__).resolve().parents[1] / "src/memory/structure_lifetime_tests.rs").read_text()
        names = re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
        self.assertEqual(len(names), 5)
        self.assertEqual(len(set(names)), 5)
        return ["memory::paging::structure_lifetime_tests::" + name for name in names]

    def declared_pin_names(self):
        source = (Path(__file__).resolve().parents[1] / "src/memory/mapping_pin_tests.rs").read_text()
        names = re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
        self.assertEqual(len(names), 11)
        self.assertEqual(len(set(names)), 11)
        return ["memory::paging::mapping_pin_tests::" + name for name in names]

    def isolated_host_names(self):
        return [
            "b18_outcome_tests::rejected_boot_outcome_is_recorded_once_and_visible_before_shell",
            "b18_outcome_tests::storage_gate_is_closed_when_boot_metadata_is_rejected",
            "memory::review_r1_tests::review_r1_production_prepare_pins_one_byte_module_and_metadata_partial_tails",
            "memory::frame::domain_tests::runtime_pin_domain_issuer_retires_at_maximum_without_wrap",
            "memory::frame::domain_tests::runtime_pin_both_reset_entries_preserve_every_live_inventory_field",
        ]

    def simulate(self, mutation, omit_reports=False, boot_rows=10, read_tests=4, write_tests=3,
                 safety_output=None, metadata_report="valid", b13_report="valid",
                 phase10_report="valid", failed_script=None, fs_checks=103):
        self.last_commands = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ("src/main.rs", "tests_kernel/src/lib.rs", "scripts/a.py", "Cargo.toml", "linker.ld", "target.json", ".cargo/config.toml"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("initial\n")
            kernel = root / "target/target/debug/kernel"
            kernel.parent.mkdir(parents=True)
            kernel.write_bytes(b"fixture kernel")

            def run(command, **kwargs):
                self.last_commands.append(command)
                # Simulate successful gates solely to reach the real final source-freeze check.
                output = kwargs["stdout"]
                prerequisite = next((c for c in command if c in (
                    "heap_growth_maps_one_page_on_demand", "phase11_gdt_tests::", "phase11a2_ownership_tests::", "phase11a2_abi_tests::", "mapping_pin_tests::", "structure_lifetime_tests::", "numeric_map_authority_tests::", "generation_ownership_tests::", "generation_ledger_tests::", "generation_boundary_tests::")), None)
                if prerequisite:
                    names = (["heap_growth_maps_one_page_on_demand"]
                             if prerequisite == "heap_growth_maps_one_page_on_demand" else [
                                 "gdt::phase11_gdt_tests::phase11_gdt_nonzero_base_does_not_contaminate_access",
                                 "gdt::phase11_gdt_tests::phase11_gdt_wire_fields_and_limit_boundaries",
                                 "gdt::phase11_gdt_tests::phase11_gdt_privilege_presence_and_tss_type"])
                    if prerequisite == "phase11a2_ownership_tests::":
                        names = ["memory::paging::phase11a2_ownership_tests::" + name for name in (
                            "phase11a2_null_frame_mapping_is_rejected_without_side_effects",
                            "phase11a2_free_pool_frame_alias_is_rejected",
                            "phase11a2_live_page_structure_alias_is_rejected_as_payload",
                            "phase11a2_growth_claimed_frame_maps_exactly_once_and_rolls_back",
                            "phase11a2_payload_frame_cannot_alias_two_active_slots",
                            "phase11a2_unmapping_boot_alias_preserves_live_runtime_payload_reference",
                            "phase11a2_unmap_then_release_restores_allocator_ownership",
                            "phase11a2_reserved_and_uncovered_frames_cannot_enter_runtime_mapping",
                        )]
                    if prerequisite == "phase11a2_abi_tests::":
                        names = ["memory::paging::phase11a2_abi_tests::" + name for name in (
                            "phase11a2_error_code_vectors_are_classified",
                            "phase11a2_gp_error_code_is_selector_format",
                            "phase11a2_pf_error_code_keeps_page_semantics",
                            "phase11a2_fault_origin_reads_saved_cs_ring",
                        )]
                    if prerequisite == "mapping_pin_tests::":
                        names = self.declared_pin_names()
                    if prerequisite == "structure_lifetime_tests::":
                        names = self.declared_structure_lifetime_names()
                    if prerequisite == "numeric_map_authority_tests::":
                        names = self.declared_numeric_map_names()
                    if prerequisite.startswith("generation_"):
                        names = next(names for filter_name, names in self.declared_generation_families().values()
                                     if filter_name == prerequisite)
                    text = (safety_output or {}).get(prerequisite,
                        "".join(f"test {name} ... ok\n" for name in names)
                        + f"test result: ok. {len(names)} passed; 0 failed; 0 ignored\n")
                    output.write(text.encode())
                    return type("Result", (), {"returncode": 0})()
                safety_filter = next((c for c in command if c in ("b11_", "b18_inventory_tests::", "b26_", "phase11_permission_tests::")), None)
                if safety_filter:
                    if safety_filter == "phase11_permission_tests::":
                        names = (
                            "phase11_permissions_intersect_both_paging_levels",
                            "phase11_unowned_user_map_is_rejected_before_table_allocation",
                            "phase11_nonpresent_map_is_rejected_without_side_effects",
                            "phase11_identity_maps_remain_supervisor_at_128_and_512_mib",
                            "phase11_rejected_requests_preserve_existing_table_and_mapping",
                        )
                        text = (safety_output or {}).get(safety_filter,
                            "".join(f"test memory::paging::{safety_filter}{name} ... ok\n" for name in names)
                            + "test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 265 filtered out\n")
                        output.write(text.encode())
                        return type("Result", (), {"returncode": 0})()
                    names = (["growth_tests::b26_growth_failure_does_not_consume_reserved_frame"]
                             + self.declared_b26_detector_names() if safety_filter == "b26_"
                             else [f"safety::{safety_filter}fixture"])
                    text = (safety_output or {}).get(safety_filter,
                        "".join(f"test {name} ... ok\n" for name in names)
                        + f"test result: ok. {len(names)} passed; 0 failed; 0 ignored; 0 measured; 4 filtered out\n")
                    output.write(text.encode())
                    return type("Result", (), {"returncode": 0})()
                if "test" in command and any(Path(str(c)).name == "Cargo.toml" and Path(str(c)).parent.name == "tests_kernel" for c in command):
                    names = self.isolated_host_names()
                    text = (safety_output or {}).get("mandatory_host",
                        "".join(f"test {name} ... ok\n" for name in names)
                        + f"test result: ok. {len(names)} passed; 0 failed; 0 ignored\n")
                    output.write(text.encode())
                elif "test" in command:
                    passed = read_tests if "read_performance" in command else 1
                    if "write_preservation" in command:
                        passed = write_tests
                    output.write(f"test result: ok. {passed} passed; 0 failed\n".encode())
                if command == ["cargo", "build"]:
                    # A real production build replaces the feature-fixture kernel.
                    kernel = root / "target/target/debug/kernel"
                    if kernel.exists():
                        kernel.write_bytes(b"fixture kernel production")
                if any(str(c).endswith("boot_test.py") for c in command):
                    folder = Path(command[command.index("--output-dir") + 1])
                    folder.mkdir(parents=True, exist_ok=True)
                    with (folder / "boot_results.csv").open("w", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=["status"])
                        writer.writeheader()
                        writer.writerows([{"status": "PASS"}] * boot_rows)
                script_name = next((Path(str(c)).name for c in command if str(c).endswith(".py")), "")
                if script_name == failed_script:
                    return type("Result", (), {"returncode": 1})()
                if script_name == "phase10_initramfs_test.py" and phase10_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1]) / "fixture"
                    folder.mkdir(parents=True, exist_ok=True)
                    evidence = Phase10EvidenceTests().fixture(folder, acceptance.PHASE10_CASES)
                    if phase10_report != "valid":
                        evidence = phase10_report
                    (folder / "report.json").write_text(json.dumps(evidence))
                if script_name == "test_b13_boot.py":
                    path = Path(command[command.index("--report") + 1])
                    path.write_text(json.dumps({"status": "PASS", "tests_run": 3, "failures": []}))
                if script_name == "b13_boot_fixture.py" and b13_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1])
                    folder.mkdir(parents=True, exist_ok=True)
                    guests = []
                    for kind, entry in (("fixture", "b13_handoff"), ("production", "_start")):
                        for ram in (128, 512):
                            guest = {"status": "PASS", "cleanup": True, "memory_mib": ram, "entry": entry}
                            child = folder / f"{kind}_{ram}"
                            child.mkdir()
                            (child / "report.json").write_text(json.dumps(guest))
                            guests.append(guest)
                    evidence = {"status": "PASS", "qemu_status": "PASS", "inspection": {"status": "PASS"}, "guests": guests}
                    if b13_report != "valid":
                        evidence.update(b13_report)
                    (folder / "report.json").write_text(json.dumps(evidence))
                if script_name == "boot_metadata_test.py" and metadata_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1]) / "fixture"
                    folder.mkdir(parents=True, exist_ok=True)
                    scenarios = []
                    for boot in ("elf", "iso"):
                        for ram in (128, 512):
                            for name in ("nomodule", "invalidmagic", "null", "headerbad", "mmaptruncated",
                                         "modulein-growth", "module-overlap", "countedoverflow", "validmodule",
                                         "reservedgrowth", "frameexhaustion"):
                                child = folder / f"{boot}_{ram}_{name}"
                                child.mkdir()
                                path = child / "report.json"
                                path.write_text(json.dumps({"overall": "PASS", "checks": [{"pass": True}]}))
                                scenarios.append({"boot": boot, "ram_mib": ram, "name": name,
                                                  "overall": "PASS", "report": str(path)})
                    evidence = {"overall": "PASS", "checks": [{"pass": True}],
                                "scenarios": scenarios, "scenario_count": 44, "expected_scenarios": 44}
                    if metadata_report != "valid":
                        evidence = metadata_report
                    (folder / "report.json").write_text(json.dumps(evidence))
                if not omit_reports and script_name in ("paging_test.py", "fs_test.py", "block_test.py", "rostifs_test.py"):
                    folder = Path(command[command.index("--output-dir") + 1]) / "fixture"
                    folder.mkdir(parents=True, exist_ok=True)
                    count = {"fs_test.py": fs_checks, "block_test.py": 98, "rostifs_test.py": 168}.get(script_name, 2)
                    if script_name == "paging_test.py" and "--runs" in command:
                        count = 20
                    field = "results" if script_name == "paging_test.py" else "checks"
                    (folder / "report.json").write_text(json.dumps({"overall": "PASS", field: [{"pass": True}] * count}))
                if any(str(c).endswith("build-proxmox-iso.py") for c in command):
                    (root / "dist").mkdir(exist_ok=True)
                    (root / "dist/rosti.iso").write_bytes(b"fixture ISO")
                if any(str(c).endswith("block_test.py") for c in command) and "--iso" in command and "512" in command:
                    mutation(root)
                return type("Result", (), {"returncode": 0})()

            with patch.object(acceptance, "PROJECT", root), patch.object(sys, "argv", ["phase6_verify.py"]), patch.object(acceptance.subprocess, "run", side_effect=run), patch.object(acceptance.subprocess, "check_output", return_value="fixture-head\n"), contextlib.redirect_stdout(io.StringIO()):
                code = acceptance.main()
            self.last_versioned_count = len(list((root / "dist").glob("rosti_phase*.iso")))
            reports = list((root / "test_results").glob("phase*/acceptance_*/acceptance.json"))
            self.last_report = json.loads(reports[0].read_text())
            return code

    def test_ramfs_baseline_listing_requires_exact_103_checks(self):
        # Capturing the existing root listing adds one VGA-prompt check to
        # each complete RAMFS workload. Reject both missing and extra rows.
        self.assertEqual(self.simulate(lambda root: None, fs_checks=103), 0)
        for count in (102, 104):
            with self.subTest(count=count):
                self.assertEqual(self.simulate(lambda root: None, fs_checks=count), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_checkout_attributes_are_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "crates").mkdir()
            attributes = root / ".gitattributes"
            attributes.write_text("system/** -text\n")
            with patch.object(acceptance, "PROJECT", root):
                before = acceptance.source_snapshot()
                self.assertIn(".gitattributes", before)
                attributes.write_text("system/** text\n")
                self.assertNotEqual(before, acceptance.source_snapshot())

    def test_current_milestone_is_only_phase11_prerequisite(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertEqual(self.last_report["phase"], "11A-prerequisite")
        self.assertEqual(self.last_report["phase11_release_ready"], False)
        self.assertRegex(self.last_report["iso"]["name"], r"^rosti_phase11a_prerequisite_\d{8}T\d{6}Z\.iso$")

    def test_phase11_permission_prerequisite_gate_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "phase11_permission_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_permissions"], {"pass": 5, "fail": 0})

    def test_phase11_missing_or_wrong_permission_tests_cannot_publish(self):
        for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                     "test memory::paging::phase11_permission_tests::unknown ... ok\n"
                     "test result: ok. 1 passed; 0 failed; 0 ignored\n"):
            with self.subTest(output=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"phase11_permission_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_production_fixture_policy_gate_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any(any(str(a).endswith("test_production_fixture_policy.py") for a in command)
                            for command in self.last_commands))
        self.assertEqual(self.simulate(lambda root: None, failed_script="test_production_fixture_policy.py"), 1)

    def test_phase10_builder_contract_and_complete_guest_gates_are_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        scripts = ("test_build_initramfs.py", "test_phase10_initramfs_harness.py",
                   "phase10_initramfs_test.py")
        for name in scripts:
            commands = [c for c in self.last_commands if any(str(a).endswith(name) for a in c)]
            self.assertEqual(len(commands), 1, name)
        guest = next(c for c in self.last_commands if any(str(a).endswith(scripts[-1]) for a in c))
        self.assertEqual(Path(guest[guest.index("--output-dir") + 1]).name, "phase10")
        self.assertEqual(self.last_report["counts"]["phase10_scenarios"],
                         {"pass": 4 * len(acceptance.PHASE10_CASES), "fail": 0})
        # Preserve all 63 predecessor gates plus exact numeric-map authority.
        self.assertEqual(self.last_report["gates_total"], 64)
        for name in scripts:
            with self.subTest(failed=name):
                self.assertEqual(self.simulate(lambda root: None, failed_script=name), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_missing_or_partial_phase10_report_cannot_publish(self):
        for evidence in (None, {}, {"overall": "RUNNING", "checks": [{"pass": True}]},
                         {"overall": "PASS", "checks": [{"pass": True}],
                          "check_count": 1, "pass_count": 1, "scenarios": [],
                          "scenario_count": 0, "expected_scenarios": 0}):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.simulate(lambda root: None, phase10_report=evidence), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_phase10_evidence_is_frozen_through_publication(self):
        def corrupt(root):
            path = next((root / "test_results").glob("phase*/acceptance_*/phase10/*/elf_128_absent/report.json"))
            evidence = json.loads(path.read_text())
            evidence["cleanup"] = False
            path.write_text(json.dumps(evidence))
        self.assertEqual(self.simulate(corrupt), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_read_boundary_and_transfer_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any("read_performance" in command and "host-tools" in command
                            and "--ignored" not in command for command in self.last_commands))

    def test_b13_injection_transport_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any(any(str(arg).endswith("test_b13_entry_inject.py") for arg in command)
                            for command in self.last_commands))

    def test_phase9_6_host_safety_suites_cannot_disappear(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        for key, filter_name, manifest in (("b11", "b11_", "tests_kernel/Cargo.toml"),
                                           ("b18", "b18_inventory_tests::", "tests_kernel/Cargo.toml"),
                                           ("b26", "b26_", "tests_b26/Cargo.toml")):
            with self.subTest(suite=key):
                commands = [c for c in self.last_commands if filter_name in c]
                self.assertEqual(len(commands), 1)
                self.assertIn("--lib", commands[0])
                self.assertTrue(any(str(c).replace("\\", "/").endswith(manifest) for c in commands[0]))
                self.assertEqual(self.last_report["counts"][key], {"pass": 6 if key == "b26" else 1, "fail": 0})

    def test_empty_or_unobserved_host_safety_suites_cannot_publish(self):
        for filter_name in ("b11_", "b18_inventory_tests::", "b26_"):
            for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                         "test result: ok. 1 passed; 0 failed; 0 ignored\n",
                         f"test safety::{filter_name}fixture ... ok\n"
                         "test result: ok. 2 passed; 0 failed; 0 ignored\n",
                         f"test safety::{filter_name}fixture ... ok\n"
                         "test result: ok. 1 passed; 1 failed; 0 ignored\n",
                         f"test safety::{filter_name}fixture ... ok\n"
                         "test result: ok. 1 passed; 0 failed; 1 ignored\n"):
                with self.subTest(suite=filter_name, output=text):
                    self.assertEqual(self.simulate(lambda root: None,
                        safety_output={filter_name: text}), 1)
                    self.assertEqual(self.last_versioned_count, 0)

    def test_integrated_boot_metadata_guests_are_mandatory_and_sequential(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = self.last_commands
        guests = [i for i, c in enumerate(commands) if any(str(a).endswith("boot_metadata_test.py") for a in c)]
        contracts = [c for c in commands if any(str(a).endswith("test_boot_metadata_harness.py") for a in c)]
        self.assertEqual(len(guests), 1)
        self.assertEqual(len(contracts), 1)
        production = next(i for i, c in enumerate(commands) if c == ["cargo", "build"])
        first_boot = next(i for i, c in enumerate(commands) if any(str(a).endswith("boot_test.py") for a in c))
        self.assertLess(production, guests[0])
        self.assertLess(guests[0], first_boot)
        command = commands[guests[0]]
        self.assertTrue(Path(command[command.index("--output-dir") + 1]).is_absolute())
        self.assertIn("both", command)
        self.assertEqual(self.last_report["counts"]["boot_metadata_scenarios"], {"pass": 44, "fail": 0})

    def test_missing_or_empty_boot_metadata_evidence_cannot_publish(self):
        for evidence in (None, {}, {"overall": "PASS", "checks": []},
                         {"overall": "PASS", "checks": [{"pass": False}]},
                         {"overall": "PASS", "checks": [{"pass": True}], "check_count": 2},
                         {"overall": "PASS", "checks": [{"pass": True}], "scenarios": [],
                          "expected_scenarios": 0, "scenario_count": 0}):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.simulate(lambda root: None, metadata_report=evidence), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_b13_host_and_privileged_handoff_gates_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        for name in ("test_b13_boot.py", "b13_boot_fixture.py"):
            commands = [c for c in self.last_commands if any(str(a).endswith(name) for a in c)]
            self.assertEqual(len(commands), 1)
            if name == "b13_boot_fixture.py":
                for option in ("--build", "--run-qemu", "--production-kernel", "--output-dir"):
                    self.assertIn(option, commands[0])
        self.assertEqual(self.last_report["counts"]["b13_host"], {"pass": 3, "fail": 0})
        self.assertEqual(self.last_report["counts"]["b13_qemu"], {"pass": 4, "fail": 0})

    def test_b13_missing_or_incomplete_privileged_proof_cannot_publish(self):
        for evidence in (None, {"qemu_status": "NOT_RUN"}, {"guests": []},
                         {"inspection": {"status": "FAIL"}},
                         {"guests": [{"status": "PASS", "cleanup": False}] * 4}):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.simulate(lambda root: None, b13_report=evidence), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_late_b13_evidence_corruption_cannot_publish(self):
        def corrupt(root):
            child = next((root / "test_results").glob("phase*/acceptance_*/b13_qemu/fixture_128/report.json"))
            child.write_text(json.dumps({"status": "FAIL"}))
        self.assertEqual(self.simulate(corrupt), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_boot_metadata_matrix_cannot_shrink_after_validation(self):
        def corrupt(root):
            path = next((root / "test_results").glob("phase*/acceptance_*/boot_metadata/*/report.json"))
            evidence = json.loads(path.read_text())
            evidence["scenario_count"] = 43
            path.write_text(json.dumps(evidence))
        self.assertEqual(self.simulate(corrupt), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_missing_read_regression_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, read_tests=1), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_write_preservation_regressions_are_required(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        self.assertTrue(any("write_preservation" in command and "host-tools" in command
                            and "--ignored" not in command for command in self.last_commands))

    def test_missing_write_regression_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, write_tests=2), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_missing_mandatory_reports_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, omit_reports=True), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_nine_boot_rows_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, boot_rows=9), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_invalid_report_schemas_and_declared_totals_cannot_pass(self):
        for report in (None, {}, {"checks": [{"pass": True}]},
                       {"overall": "PASS"}, {"overall": "PASS", "checks": []},
                       {"overall": "PASS", "checks": [{"pass": False}]},
                       {"overall": "PASS", "results": [{"pass": 1}]},
                       {"overall": "PASS", "checks": [{"pass": True}], "check_count": 2}):
            with self.subTest(report=report), self.assertRaises(RuntimeError):
                acceptance.evidence_rows(report, "fixture")

    def test_bad_mandatory_report_cannot_publish(self):
        for bad in ({}, {"checks": [{"pass": True}]}, {"overall": "PASS", "checks": []}):
            def corrupt(root):
                path = next((root / "test_results").glob("phase*/acceptance_*/fs_elf_128/*/report.json"))
                path.write_text(json.dumps(bad))
            with self.subTest(report=bad):
                self.assertEqual(self.simulate(corrupt), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_failed_source_freeze_does_not_publish_versioned_iso(self):
        self.assertEqual(self.simulate(lambda root: (root / "src/late.rs").write_text("late\n")), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_failed_harness_report_cannot_pass_or_publish(self):
        def failed_report(root):
            run = next((root / "test_results").glob("phase*/acceptance_*"))
            folder = run / "fixture"
            folder.mkdir()
            (folder / "report.json").write_text('{"overall":"FAIL","checks":[{"pass":false}]}')
        self.assertEqual(self.simulate(failed_report), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_source_added_during_acceptance_is_rejected(self):
        self.assertEqual(self.simulate(lambda root: (root / "src/late.rs").write_text("late\n")), 1)

    def test_target_configuration_changed_during_acceptance_is_rejected(self):
        self.assertEqual(self.simulate(lambda root: (root / "target.json").write_text("changed\n")), 1)

    def test_system_assets_with_any_extension_are_frozen(self):
        for relative in ("system/etc/banner", "system/bin/tool.bin", "system/config.yaml",
                         "src/initramfs/new_trust.rs"):
            def add(root):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"late trusted input")
            with self.subTest(input=relative):
                self.assertEqual(self.simulate(add), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_stable_source_can_finish(self):
        self.assertEqual(self.simulate(lambda root: None), 0)

    def test_phase11_owned_snapshot_and_gdt_tests_are_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        for filter_name in ("heap_growth_maps_one_page_on_demand", "phase11_gdt_tests::"):
            commands = [c for c in self.last_commands if filter_name in c]
            self.assertEqual(len(commands), 1)
            self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_snapshot"], {"pass": 1, "fail": 0})
        self.assertEqual(self.last_report["counts"]["phase11_gdt"], {"pass": 3, "fail": 0})

    def test_phase11_registry_reservation_prerequisite_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "phase11a2_ownership_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_registry_reservation"], {"pass": 8, "fail": 0})

    def test_phase11_registry_reservation_bad_identities_cannot_publish(self):
        for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                     "test impostor ... ok\ntest result: ok. 8 passed; 0 failed; 0 ignored\n"):
            with self.subTest(text=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"phase11a2_ownership_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_phase11_exception_abi_prerequisite_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "phase11a2_abi_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_exception_abi"], {"pass": 4, "fail": 0})

    def test_phase11_exception_abi_bad_identities_cannot_publish(self):
        for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                     "test impostor ... ok\ntest result: ok. 4 passed; 0 failed; 0 ignored\n"):
            with self.subTest(text=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"phase11a2_abi_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_phase11_runtime_pin_prerequisite_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "mapping_pin_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_runtime_pins"], {"pass": 11, "fail": 0})

    def test_phase11_runtime_pin_bad_identities_cannot_publish(self):
        names = self.declared_pin_names()
        first = names[0]
        def result(cases):
            return "".join(f"test {name} ... ok\n" for name in cases) + f"test result: ok. {len(cases)} passed; 0 failed; 0 ignored\n"
        for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                     "test impostor ... ok\ntest result: ok. 11 passed; 0 failed; 0 ignored\n",
                     result([first] * len(names)), result(names[:-1]),
                     result(names + ["memory::paging::mapping_pin_tests::extra"]),
                     result(names[:-1] + ["memory::paging::mapping_pin_tests::substituted"])):
            with self.subTest(text=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"mapping_pin_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_phase11_runtime_pin_identities_match_real_rust_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        rows = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                and len(node.elts) == 3 and isinstance(node.elts[0], ast.Constant)
                and node.elts[0].value == "phase11_runtime_pins"]
        self.assertEqual(len(rows), 1)
        required = rows[0].elts[2]
        prefix = ast.literal_eval(required.elt.left)
        wired = {prefix + ast.literal_eval(name) for name in required.generators[0].iter.elts}
        self.assertEqual(wired, set(self.declared_pin_names()))
        self.assertEqual(len(wired), 11)
        self.assertTrue({prefix + name for name in (
            "shared_mapping_same_and_cross_map_refusal_is_state_atomic",
            "shared_mapping_table_failure_then_retry_preserves_lease_and_capacity",
            "shared_mapping_retained_lease_remap_refuses_old_and_foreign_unmap",
        )}.issubset(wired))

    def test_phase11_structure_lifetime_prerequisite_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "structure_lifetime_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--lib", commands[0])
        self.assertIn("--test-threads=1", commands[0])
        self.assertTrue(any(str(c).replace("\\", "/").endswith("tests_kernel/Cargo.toml")
                            for c in commands[0]))
        self.assertEqual(self.last_report["counts"]["phase11_structure_lifetime"], {"pass": 5, "fail": 0})
        self.assertEqual(self.last_report["gates_total"], 64)

    def test_phase11_structure_lifetime_bad_identities_cannot_publish(self):
        names = self.declared_structure_lifetime_names()
        def result(cases, passed=None, failed=0, ignored=0):
            return ("".join(f"test {name} ... ok\n" for name in cases)
                    + f"test result: ok. {len(cases) if passed is None else passed} passed; {failed} failed; {ignored} ignored\n")
        outputs = {
            "empty": "", "zero": result([]),
            "one_short": result(names[:-1]),
            "extra": result(names + ["memory::paging::structure_lifetime_tests::extra"]),
            "duplicate": result(names[:-1] + [names[0]]),
            "substituted": result(names[:-1] + ["memory::paging::structure_lifetime_tests::substituted"]),
            "declared_short": result(names, passed=4),
            "declared_extra": result(names, passed=6),
            "missing_row": result(names[:-1], passed=5),
            "failed": result(names, failed=1),
            "ignored": result(names, ignored=1),
            "missing_summary": "".join(f"test {name} ... ok\n" for name in names),
            "duplicate_summary": result(names) + "test result: ok. 5 passed; 0 failed; 0 ignored\n",
        }
        for label, text in outputs.items():
            with self.subTest(mutation=label):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"structure_lifetime_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("phase11_structure_lifetime", self.last_report["counts"])

    def test_phase11_structure_lifetime_identities_match_real_rust_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        rows = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                and len(node.elts) == 3 and isinstance(node.elts[0], ast.Constant)
                and node.elts[0].value == "phase11_structure_lifetime"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(ast.literal_eval(rows[0].elts[1]), "structure_lifetime_tests::")
        required = rows[0].elts[2]
        prefix = ast.literal_eval(required.elt.left)
        wired = [prefix + ast.literal_eval(name) for name in required.generators[0].iter.elts]
        self.assertEqual(len(wired), 5)
        self.assertEqual(set(wired), set(self.declared_structure_lifetime_names()))
        paging = (Path(__file__).resolve().parents[1] / "src/memory/paging.rs").read_text()
        self.assertRegex(paging, r'#\[cfg\(test\)\]\s*#\[path = "structure_lifetime_tests.rs"\]\s*mod structure_lifetime_tests;')

    def test_phase11_generation_prerequisites_are_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        for key, (filter_name, names) in self.declared_generation_families().items():
            commands = [c for c in self.last_commands if filter_name in c]
            self.assertEqual(len(commands), 1, key)
            self.assertIn("--lib", commands[0])
            self.assertIn("--test-threads=1", commands[0])
            self.assertEqual(self.last_report["counts"][key], {"pass": len(names), "fail": 0})
        self.assertEqual(self.last_report["gates_total"], 64)

    def test_phase11_generation_bad_identities_cannot_publish(self):
        for key, (filter_name, names) in self.declared_generation_families().items():
            def result(rows, passed=None, failed=0, ignored=0):
                return ("".join(f"test {name} ... ok\n" for name in rows)
                        + f"test result: ok. {len(rows) if passed is None else passed} passed; {failed} failed; {ignored} ignored\n")
            outputs = ["", result([]), result(names[:-1]), result(names + [names[0] + "_extra"]),
                       result(names[:-1] + [names[0]]), result(names[:-1] + [names[0] + "_substitute"]),
                       result(names, len(names) - 1), result(names, len(names) + 1),
                       result(names[:-1], len(names)), result(names, failed=1), result(names, ignored=1),
                       "".join(f"test {name} ... ok\n" for name in names), result(names) + result(names)]
            for text in outputs:
                with self.subTest(key=key, text=text):
                    self.assertEqual(self.simulate(lambda root: None, safety_output={filter_name: text}), 1)
                    self.assertEqual(self.last_versioned_count, 0)
                    self.assertNotIn(key, self.last_report["counts"])

    def test_phase11_generation_identities_match_real_rust_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        for key, (filter_name, names) in self.declared_generation_families().items():
            rows = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                    and len(node.elts) == 3 and isinstance(node.elts[0], ast.Constant)
                    and node.elts[0].value == key]
            self.assertEqual(len(rows), 1)
            self.assertEqual(ast.literal_eval(rows[0].elts[1]), filter_name)
            required = rows[0].elts[2]
            prefix = ast.literal_eval(required.elt.left)
            wired = [prefix + ast.literal_eval(n) for n in required.generators[0].iter.elts]
            self.assertEqual(len(wired), len(names))
            self.assertEqual(set(wired), set(names))

    def test_domain_and_isolation_host_coverage_cannot_shrink(self):
        names = self.isolated_host_names()
        for removed in names:
            with self.subTest(removed=removed):
                kept = [name for name in names if name != removed]
                text = "".join(f"test {name} ... ok\n" for name in kept) + f"test result: ok. {len(kept)} passed; 0 failed; 0 ignored\n"
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"mandatory_host": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_b26_detector_controls_cannot_disappear_or_be_substituted(self):
        names = self.declared_b26_detector_names()
        growth = "growth_tests::b26_growth_failure_does_not_consume_reserved_frame"
        cases = [[growth] + names[:-1], [growth] + names[:-1] + [names[0]],
                 [growth] + names[:-1] + ["memory::ownership_observation_tests::b26_substituted"]]
        cases += [[growth] + [n for n in names if n != missing] for missing in names]
        for kept in cases:
            text = ("".join(f"test {name} ... ok\n" for name in kept)
                    + f"test result: ok. {len(kept)} passed; 0 failed; 0 ignored\n")
            with self.subTest(kept=kept):
                self.assertEqual(self.simulate(lambda root: None, safety_output={"b26_": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_b26_detector_identities_match_real_rust_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "mandatory_b26_detectors"
                               for t in node.targets)]
        self.assertEqual(len(assignments), 1)
        required = assignments[0].value
        prefix = ast.literal_eval(required.elt.left)
        names = [prefix + ast.literal_eval(n) for n in required.generators[0].iter.elts]
        self.assertEqual(len(names), 5)
        self.assertEqual(set(names), set(self.declared_b26_detector_names()))

    def test_b26_growth_isolation_coverage_cannot_shrink(self):
        text = "test safety::b26_fixture ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored\n"
        self.assertEqual(self.simulate(lambda root: None, safety_output={"b26_": text}), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_phase11_prerequisite_identities_cannot_be_substituted(self):
        for filter_name in ("heap_growth_maps_one_page_on_demand", "phase11_gdt_tests::"):
            for text in ("", "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                         "test impostor ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored\n"):
                with self.subTest(filter=filter_name, text=text):
                    self.assertEqual(self.simulate(lambda root: None,
                        safety_output={filter_name: text}), 1)
                    self.assertEqual(self.last_versioned_count, 0)

    def test_safety_fixture_build_inputs_are_frozen(self):
        for relative in ("tests_b26/src/lib.rs", "tests_b26/Cargo.toml",
                         "tests_b26/Cargo.lock", "tests_b26/.cargo/config.toml",
                         "scripts/b13_fixture/main.rs", "scripts/b13_fixture/entry.s",
                         "scripts/b13_fixture/linker.ld", "scripts/b13_fixture/target.json",
                         "scripts/b13_fixture/.cargo/config.toml", "scripts/b13_fixture/Cargo.toml"):
            def add(root):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("late input\n")
            with self.subTest(input=relative):
                self.assertEqual(self.simulate(add), 1)
                self.assertEqual(self.last_versioned_count, 0)

    def test_portable_source_added_during_acceptance_is_rejected(self):
        def add(root):
            directory = root / "crates/rostifs/src"
            directory.mkdir(parents=True)
            (directory / "late.rs").write_text("late\n")
        self.assertEqual(self.simulate(add), 1)
        self.assertEqual(self.last_versioned_count, 0)


if __name__ == "__main__":
    unittest.main()
