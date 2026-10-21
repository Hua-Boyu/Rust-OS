"""Acceptance source-freeze regressions; subprocesses are fixtures, not live gates."""
import contextlib
import ast
from collections import Counter
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

import f2_evidence
import f3_evidence
import test_f3_evidence as f3_models
import f3_full_evidence
import test_f3_full_evidence as f3_full_models

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

    def declared_unmap_authority_names(self):
        source = (Path(__file__).resolve().parents[1] / "src/memory/unmap_authority_tests.rs").read_text()
        names = re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3)
        return ["memory::paging::unmap_authority_tests::" + name for name in names]

    def test_unmap_authority_prerequisite_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "unmap_authority_tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--lib", commands[0])
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["phase11_unmap_authority"], {"pass": 3, "fail": 0})

    def test_unmap_authority_bad_identities_cannot_publish(self):
        names = self.declared_unmap_authority_names()
        def result(rows, passed=None, failed=0, ignored=0):
            return ("".join(f"test {name} ... ok\n" for name in rows)
                    + f"test result: ok. {len(rows) if passed is None else passed} passed; {failed} failed; {ignored} ignored\n")
        outputs = ["", result([]), result(names[:-1]), result(names + [names[0] + "_extra"]),
                   result(names[:-1] + [names[0]]), result(names[:-1] + [names[0] + "_substitute"]),
                   result(names, 2), result(names, 4), result(names[:-1], 3),
                   result(names, failed=1), result(names, ignored=1),
                   "".join(f"test {name} ... ok\n" for name in names), result(names) + result(names)]
        for text in outputs:
            with self.subTest(text=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"unmap_authority_tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("phase11_unmap_authority", self.last_report["counts"])

    def test_unmap_authority_identities_match_real_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        rows = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                and len(node.elts) == 3 and isinstance(node.elts[0], ast.Constant)
                and node.elts[0].value == "phase11_unmap_authority"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(ast.literal_eval(rows[0].elts[1]), "unmap_authority_tests::")
        required = rows[0].elts[2]
        prefix = ast.literal_eval(required.elt.left)
        wired = [prefix + ast.literal_eval(n) for n in required.generators[0].iter.elts]
        self.assertEqual(len(wired), 3)
        self.assertEqual(set(wired), set(self.declared_unmap_authority_names()))

    def declared_f2_exception_abi_names(self):
        source = (Path(__file__).resolve().parents[1] / "src/exception_abi_tests.rs").read_text()
        names = re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
        self.assertEqual(len(names), 7)
        self.assertEqual(len(set(names)), 7)
        return ["exception_abi::tests::" + name for name in names]

    def test_f2_exception_abi_exact_family_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "exception_abi::tests::" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--lib", commands[0])
        self.assertIn("--test-threads=1", commands[0])
        self.assertTrue(any(str(c).replace("\\", "/").endswith("tests_kernel/Cargo.toml")
                            for c in commands[0]))
        self.assertEqual(self.last_report["counts"]["f2_exception_abi"], {"pass": 7, "fail": 0})
        self.assertEqual(self.last_report["gates_total"], 70)
        gates = [g["gate"] for g in self.last_report["gates"]]
        self.assertEqual(gates.count("Phase 11F2 exception ABI exact identity family"), 1)

    def test_f2_exception_abi_bad_identities_cannot_publish(self):
        names = self.declared_f2_exception_abi_names()
        def result(rows, passed=None, failed=0, ignored=0):
            return ("".join(f"test {name} ... ok\n" for name in rows)
                    + f"test result: ok. {len(rows) if passed is None else passed} passed; {failed} failed; {ignored} ignored\n")
        outputs = {
            "missing-output": "",
            "zero": result([]),
            "missing": result(names[:-1]),
            "duplicate": result(names[:-1] + [names[0]]),
            "extra": result(names + [names[0] + "_extra"]),
            "substituted": result(names[:-1] + [names[-1] + "_renamed"]),
            "impostor": result([name.replace("exception_abi::tests::", "impostor::tests::") for name in names]),
            "short-total": result(names, 6),
            "extra-total": result(names, 8),
            "missing-row": result(names[:-1], 7),
            "failed": result(names, failed=1),
            "ignored": result(names, ignored=1),
            "no-summary": "".join(f"test {name} ... ok\n" for name in names),
            "duplicate-summary": result(names) + result(names),
        }
        for control, text in outputs.items():
            with self.subTest(control=control):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"exception_abi::tests::": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("f2_exception_abi", self.last_report["counts"])
                self.assertEqual(self.last_report["error"], "F2 exception ABI tests missing or inconsistent")

    def test_f2_exception_abi_identities_match_real_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        rows = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "f2_required"
                        for target in node.targets)]
        self.assertEqual(len(rows), 1)
        required = rows[0]
        prefix = ast.literal_eval(required.elt.left)
        wired = [prefix + ast.literal_eval(n) for n in required.generators[0].iter.elts]
        self.assertEqual(len(wired), 7)
        self.assertEqual(set(wired), set(self.declared_f2_exception_abi_names()))
        root = Path(__file__).resolve().parents[1]
        self.assertIn('mod exception_abi;', (root / "tests_kernel/src/lib.rs").read_text())
        abi_source = (root / "src/exception_abi.rs").read_text()
        self.assertIn('#[path = "exception_abi_tests.rs"]', abi_source)
        self.assertIn('mod tests;', abi_source)

    def test_f2_hardware_matrix_is_one_mandatory_gate(self):
        with patch.object(f2_evidence, "validate", wraps=f2_evidence.validate) as validate:
            self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [(i, c) for i, c in enumerate(self.last_commands)
                    if any(str(arg).endswith("f2_exception_guest.py") for arg in c)]
        self.assertEqual(len(commands), 1)
        index, command = commands[0]
        self.assertEqual(self.last_timeouts[index], 300)
        self.assertEqual(len(command), 4)
        output = Path(command[command.index("--output-dir") + 1])
        self.assertTrue(output.is_absolute())
        self.assertEqual(output.name, "f2_exception")
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(validate.call_args.args[0].parent.parent, output)
        self.assertEqual(validate.call_args.args[1], self.last_report["source_sha256"])
        self.assertEqual(self.last_report["counts"]["f2_exception_scenarios"], {"pass": 8, "fail": 0})
        self.assertEqual(len(self.last_report["f2_evidence_sha256"]), 10)
        self.assertEqual(self.last_report["gates_total"], 70)
        self.assertEqual(self.last_report["gates_passed"], 70)
        self.assertEqual(sum(g["gate"] == "Phase 11F2 exception ABI hardware matrix"
                             for g in self.last_report["gates"]), 1)

    def test_f2_missing_or_failed_driver_cannot_publish(self):
        for option in ("missing_script", "failed_script"):
            with self.subTest(option=option):
                self.assertEqual(self.simulate(lambda root: None,
                    **{option: "f2_exception_guest.py"}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("f2_exception_scenarios", self.last_report["counts"])
                self.assertEqual(self.last_report["gates"][-1]["status"], "FAIL")

    def test_f2_missing_report_or_validator_failure_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, f2_report=None), 1)
        self.assertEqual(self.last_versioned_count, 0)
        self.assertEqual(self.last_report["error"], "missing or ambiguous mandatory F2 hardware report")
        with patch.object(f2_evidence, "validate", side_effect=RuntimeError("F2 validator refused")):
            self.assertEqual(self.simulate(lambda root: None), 1)
        self.assertEqual(self.last_versioned_count, 0)
        self.assertEqual(self.last_report["error"], "F2 validator refused")
        self.assertNotIn("f2_exception_scenarios", self.last_report["counts"])
        self.assertEqual(self.simulate(lambda root: None, f2_report={"overall": "FAIL"}), 1)
        self.assertEqual(self.last_versioned_count, 0)

    def test_f2_ambiguous_owned_aggregate_cannot_publish(self):
        with patch.object(f2_evidence, "validate", wraps=f2_evidence.validate) as validate:
            self.assertEqual(self.simulate(lambda root: None, f2_report="ambiguous"), 1)
        self.assertEqual(validate.call_count, 0)
        self.assertEqual(self.last_versioned_count, 0)
        self.assertEqual(self.last_report["error"], "missing or ambiguous mandatory F2 hardware report")

    def test_f2_every_returned_pin_is_frozen_through_publication(self):
        targets = ["report.json", "kernel.elf"] + [
            f"{case}_{ram}/report.json" for case in ("ud", "de", "gp", "pf") for ram in (128, 512)]
        for relative in targets:
            def corrupt(root):
                folder = next((root / "test_results").glob("phase*/acceptance_*/f2_exception/*"))
                target = folder / relative
                target.write_bytes(target.read_bytes() + b" ")
            with self.subTest(pin=relative):
                self.assertEqual(self.simulate(corrupt), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertEqual(self.last_report["error"],
                                 "F2 validated hardware evidence changed during acceptance")

    def declared_f3_names(self):
        root = Path(__file__).resolve().parents[1]
        names = []
        for file, prefix, count in (
            ("privileged_tests.rs", "memory::paging::privileged::tests::", 5),
            ("privileged_owner_tests.rs", "memory::paging::privileged_owner_tests::", 2),
        ):
            source = (root / "src/memory" / file).read_text()
            found = re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
            self.assertEqual(len(found), count)
            names.extend(prefix + name for name in found)
        self.assertEqual(len(names), 7)
        self.assertEqual(len(set(names)), 7)
        return names

    def test_f3_exact_family_matches_source_declarations(self):
        tree = ast.parse(Path(acceptance.__file__).read_text())
        required = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "f3_required" for t in node.targets)]
        self.assertEqual(len(required), 1)
        self.assertEqual(ast.literal_eval(required[0]), set(self.declared_f3_names()))
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "::f3_" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--lib", commands[0])
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["f3_minimal_ring0"], {"pass": 7, "fail": 0})

    def test_f3_bad_host_identities_cannot_publish(self):
        names = self.declared_f3_names()
        def result(rows, passed=None, failed=0, ignored=0):
            return ("".join(f"test {name} ... ok\n" for name in rows)
                    + f"test result: ok. {len(rows) if passed is None else passed} passed; {failed} failed; {ignored} ignored\n")
        controls = {"missing-output": "", "zero": result([]), "missing": result(names[:-1]),
                    "duplicate": result(names[:-1] + [names[0]]),
                    "substitute": result(names[:-1] + [names[-1] + "_substitute"]),
                    "impostor": result([n.replace("memory::", "impostor::") for n in names]),
                    "extra": result(names + [names[0] + "_extra"]),
                    "short-total": result(names, 6), "extra-total": result(names, 8),
                    "missing-row": result(names[:-1], 7), "failed": result(names, failed=1),
                    "ignored": result(names, ignored=1), "duplicate-summary": result(names)*2,
                    "no-summary": "".join(f"test {name} ... ok\n" for name in names)}
        for control, output in controls.items():
            with self.subTest(control=control):
                self.assertEqual(self.simulate(lambda root: None, safety_output={"::f3_": output}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("f3_minimal_ring0", self.last_report["counts"])
                self.assertEqual(self.last_report["error"], "F3 minimal Ring0 tests missing or inconsistent")

    def test_f3_hardware_matrix_is_one_owned_validated_gate(self):
        with patch.object(f3_full_evidence, "validate", wraps=f3_full_evidence.validate) as validate:
            self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [(i, c) for i, c in enumerate(self.last_commands)
                    if any(str(arg).endswith("f3_full_guest.py") for arg in c)]
        self.assertEqual(len(commands), 1)
        index, command = commands[0]
        self.assertEqual(self.last_timeouts[index], 2100)
        self.assertEqual(len(command), 4)
        self.assertEqual(command[2], "--output-dir")
        output = Path(command[3])
        self.assertTrue(output.is_absolute())
        self.assertEqual(output.name, "f3_gdt_tss")
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(validate.call_args.args[0].parent.parent, output)
        self.assertEqual(validate.call_args.args[1], self.last_report["source_sha256"])
        self.assertEqual(self.last_report["counts"]["f3_minimal_ring0_scenarios"],
                         {"pass": len(f3_full_evidence.REQUIRED), "fail": 0})
        self.assertGreater(len(self.last_report["f3_evidence_sha256"]), len(f3_full_evidence.REQUIRED))
        self.assertEqual(self.last_report["gates_passed"], 70)
        self.assertEqual(Counter(g["gate"] for g in self.last_report["gates"])[
            "Phase 11F3 minimal Ring0 hardware matrix"], 1)

    def test_f3_missing_failed_driver_report_and_validator_refuse(self):
        for option in ("missing_script", "failed_script"):
            with self.subTest(option=option):
                self.assertEqual(self.simulate(lambda root: None, **{option: "f3_full_guest.py"}), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("f3_minimal_ring0_scenarios", self.last_report["counts"])
        for mode in (None, "ambiguous"):
            with self.subTest(report=mode):
                with patch.object(f3_full_evidence, "validate", wraps=f3_full_evidence.validate) as validate:
                    self.assertEqual(self.simulate(lambda root: None, f3_report=mode), 1)
                self.assertEqual(validate.call_count, 0)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertEqual(self.last_report["error"], "missing or ambiguous mandatory F3 hardware report")
        with patch.object(f3_full_evidence, "validate", side_effect=ValueError("F3 validator refused")):
            self.assertEqual(self.simulate(lambda root: None), 1)
        self.assertEqual(self.last_report["error"], "F3 validator refused")
        self.assertEqual(self.last_versioned_count, 0)

    def test_f3_contradictory_matrix_driver_and_cleanup_refuse(self):
        def missing(r): r["scenarios"].pop()
        def duplicate(r): r["scenarios"][-1] = r["scenarios"][0]
        def substitute(r): r["scenarios"][0]["name"] = "impostor_128"
        def extra(r): r["scenarios"].append(r["scenarios"][0])
        controls = [missing, duplicate, substitute, extra,
                    lambda r: r.update(scenarios=[]), lambda r: r.update(driver_exit=1),
                    lambda r: r["drivers"][0].update(exit=1), lambda r: r.update(overall="PASS"),
                    lambda r: r.update(UNIT_MODEL_cleanup_override={"owned_qemu_exited":False}),
                    lambda r: r["scenarios"][0].update(qemu_exit_before_cleanup=0),
                    lambda r: r.update(UNIT_MODEL_cleanup_override={"cleanup_action":"none"}),
                    lambda r: r.update(UNIT_MODEL_cleanup_override={"qemu_exit":0})]
        for index, mutate in enumerate(controls):
            with self.subTest(control=index):
                self.assertEqual(self.simulate(lambda root: None, f3_report=mutate), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertNotIn("f3_minimal_ring0_scenarios", self.last_report["counts"])

    def test_f3_actual_minimal_only_validator_cannot_publish(self):
        self.assertEqual(self.simulate(lambda root: None, f3_complete=False), 1)
        self.assertEqual(self.last_versioned_count, 0)
        self.assertNotIn("f3_minimal_ring0_scenarios", self.last_report["counts"])
        self.assertEqual(self.last_report["error"],
                         "F3 hardware evidence is partial; full mandatory oracles remain unverified")

    def test_f3_every_returned_pin_is_frozen_until_publication(self):
        # Derive the complete pin list from a real validator call on unit models.
        final_reads = set()
        original_sha = acceptance.sha256
        def record(path):
            if rechecks[0]:
                final_reads.add(str(Path(path).resolve()))
            return original_sha(path)
        rechecks = [False]
        with patch.object(acceptance, "sha256", side_effect=record):
            self.assertEqual(self.simulate(lambda root: rechecks.__setitem__(0, True)), 0)
        self.assertTrue(set(self.last_report["f3_evidence_sha256"]) <= final_reads)
        prefix = "/f3_gdt_tss/f3_full_UNIT_MODEL/"
        relatives = [p.replace("\\", "/").split(prefix, 1)[1]
                     for p in self.last_report["f3_evidence_sha256"]]
        self.assertTrue(relatives)
        # Mutate ALL pins together in one mock run, and separately exercise each
        # artifact class so a report-only recheck cannot satisfy this contract.
        representatives = ["report.json", "driver.py", "validator.py", "minimal.log",
                           "source_freeze_before.json", "minimal/f3_minimal_UNIT_MODEL/kernel.elf",
                           "minimal/f3_minimal_UNIT_MODEL/frozen_inputs/src/main.rs",
                           "minimal/f3_minimal_UNIT_MODEL/ready_128/guest_report.json",
                           "minimal/f3_minimal_UNIT_MODEL/ready_128/cpu_gdt.bin",
                           "supplemental/f3_supplemental_UNIT_MODEL/ss_nonpresent_128/mandatory_prefix.bin"]
        for targets in [relatives] + [[p] for p in representatives]:
            def corrupt(root):
                folder = next((root / "test_results").glob("phase*/acceptance_*/f3_gdt_tss/*"))
                for relative in targets:
                    target = folder / relative
                    target.write_bytes(target.read_bytes() + b" ")
            with self.subTest(targets=targets):
                self.assertEqual(self.simulate(corrupt), 1)
                self.assertEqual(self.last_versioned_count, 0)
                self.assertEqual(self.last_report["error"], "F3 validated hardware evidence changed during acceptance")

    def test_f3_unvalidated_extra_report_cannot_bypass_generic_schema(self):
        def impostor(root):
            folder = next((root / "test_results").glob("phase*/acceptance_*/f3_gdt_tss/*"))
            other = folder / "impostor"
            other.mkdir()
            (other / "report.json").write_text(json.dumps({"overall": "MINIMAL_RING0_GREEN"}))
        self.assertEqual(self.simulate(impostor), 1)
        self.assertEqual(self.last_versioned_count, 0)
        self.assertIn("failed or invalid harness report", self.last_report["error"])

    def declared_f1_retained_owner_names(self):
        root = Path(__file__).resolve().parents[1]
        names = []
        for file, prefix, count in (
            ("retained_owner_policy_tests.rs", "memory::paging::retained_owner::tests::", 8),
            ("retained_owner_tests.rs", "memory::paging::retained_owner_tests::", 1),
        ):
            source = (root / "src/memory" / file).read_text()
            found = [name for name in re.findall(r"(?m)^#\[test\]\s*\nfn (\w+)\(", source)
                     if not name.startswith("b26_detector_")]
            self.assertEqual(len(found), count)
            self.assertEqual(len(set(found)), count)
            names.extend(prefix + name for name in found)
        self.assertEqual(len(names), 9)
        self.assertEqual(len(set(names)), 9)
        return names

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
                 phase10_report="valid", failed_script=None, fs_checks=103,
                 f2_report="valid", missing_script=None, f3_report="valid", f3_complete=True):
        self.last_commands = []
        self.last_timeouts = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ("src/main.rs", "tests_kernel/src/lib.rs", "scripts/a.py", "Cargo.toml", "linker.ld", "target.json", ".cargo/config.toml"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("initial\n")
            (root / "src/main.rs").write_bytes(b"UNIT MODEL ONLY\n    // stub: enable ps2 & interrupts\n")
            # Canonical source-freeze prerequisites for the pure F3 unit model.
            for name in ("src/gdt.rs", "src/gdt_tss.rs", "src/f3_entry.s", "src/interrupt.rs",
                         "src/memory/mod.rs", "src/memory/paging.rs", "src/memory/retained_owner.rs",
                         "scripts/f3_gdt_guest.py", "scripts/f3_evidence.py", "scripts/test_f3_evidence.py",
                         "Cargo.lock", "rust-toolchain.toml"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("UNIT MODEL ONLY " + name + "\n")
            for name,raw in f3_full_models.default_sources().items():
                if not (root/name).exists() or name in ("src/exception_entry.s","src/f3_entry.s"):
                    f3_models.write(root/name,raw)
            kernel = root / "target/target/debug/kernel"
            kernel.parent.mkdir(parents=True)
            kernel.write_bytes(b"fixture kernel")

            def run(command, **kwargs):
                self.last_commands.append(command)
                self.last_timeouts.append(kwargs.get("timeout"))
                script_name = next((Path(str(c)).name for c in command if str(c).endswith(".py")), "")
                if script_name == missing_script:
                    raise FileNotFoundError(script_name)
                # Simulate successful gates solely to reach the real final source-freeze check.
                output = kwargs["stdout"]
                prerequisite = next((c for c in command if c in (
                    "heap_growth_maps_one_page_on_demand", "phase11_gdt_tests::", "phase11a2_ownership_tests::", "phase11a2_abi_tests::", "mapping_pin_tests::", "structure_lifetime_tests::", "numeric_map_authority_tests::", "unmap_authority_tests::", "generation_ownership_tests::", "generation_ledger_tests::", "generation_boundary_tests::", "retained_owner", "exception_abi::tests::", "::f3_")), None)
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
                    if prerequisite == "unmap_authority_tests::":
                        names = self.declared_unmap_authority_names()
                    if prerequisite.startswith("generation_"):
                        names = next(names for filter_name, names in self.declared_generation_families().values()
                                     if filter_name == prerequisite)
                    if prerequisite == "retained_owner":
                        names = self.declared_f1_retained_owner_names()
                    if prerequisite == "exception_abi::tests::":
                        names = self.declared_f2_exception_abi_names()
                    if prerequisite == "::f3_":
                        names = self.declared_f3_names()
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
                if script_name == "f2_exception_guest.py" and f2_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1]) / "f2_guest_fixture"
                    folder.mkdir(parents=True)
                    fixture_kernel = folder / "kernel.elf"
                    fixture_kernel.write_bytes(b"mock F2 fixture ELF, not hardware evidence")
                    source = acceptance.source_snapshot()
                    digest = acceptance.sha256(fixture_kernel)
                    cases = []
                    for case in ("ud", "de", "gp", "pf"):
                        for ram in (128, 512):
                            child = folder / f"{case}_{ram}" / "report.json"
                            child.parent.mkdir()
                            (child.parent / "serial.txt").write_text("F2 FIXTURE TRIGGER\nF2 fatal terminal\n")
                            (child.parent / "mandatory_prefix.bin").write_bytes(bytes(68))
                            names = sorted(f2_evidence.COMMON_CHECKS
                                           | ({"page_fault_CR2_zero"} if case == "pf" else set()))
                            guest = {"overall": "PASS", "case": case, "ram_mib": ram,
                                     "owned_qemu_exited": True, "qemu_exit": -1,
                                     "hardware_cpl3": False, "kernel_sha256": digest,
                                     "checks": [{"name": name, "pass": True} for name in names],
                                     "command": ["mock-qemu", "-kernel", str(fixture_kernel),
                                                 "-m", str(ram), "-smp", "1", "-cpu", "qemu32",
                                                 "-serial", "file:" + str(child.parent / "serial.txt")]}
                            child.write_text(json.dumps(guest))
                            cases.append({"case": case, "ram_mib": ram,
                                          "overall": "PASS", "report": str(child)})
                    evidence = {"overall": "PASS", "build_exit": 0,
                                "source_sha256": source, "stripping_equality": True,
                                "original_main_sha256": source["src/main.rs"],
                                "kernel_sha256": digest, "cases": cases,
                                "checks": [{"name": "all_requested_cpu_scenarios_PASS", "pass": True},
                                           {"name": "source_freeze_stable", "pass": True}]}
                    if f2_report == "ambiguous":
                        other = folder.with_name("f2_guest_extra")
                        other.mkdir()
                        (other / "report.json").write_text(json.dumps(evidence))
                    elif f2_report != "valid":
                        evidence = f2_report
                    (folder / "report.json").write_text(json.dumps(evidence))
                if script_name == "f3_full_guest.py" and f3_report is not None:
                    folder = Path(command[command.index("--output-dir") + 1]) / "f3_full_UNIT_MODEL"
                    source_bytes = {name:(root/name).read_bytes() for name in acceptance.source_snapshot()}
                    evidence = f3_full_models.matrix_model(folder,source_bytes)
                    if callable(f3_report):
                        f3_report(evidence)
                        cleanup = evidence.pop("UNIT_MODEL_cleanup_override",None)
                        if cleanup:
                            child = folder/evidence["supplemental_report"]
                            report = f3_evidence.strict_json(child)
                            row = report["scenarios"][0]; row.update(cleanup)
                            raw = child.parent/row["name"]/"guest_report.json"
                            f3_models.dump(raw,row)
                            report["frozen_bytes"][raw.relative_to(child.parent).as_posix()] = f3_evidence.sha(raw.read_bytes())
                            f3_models.dump(child,report)
                            for p in (raw,child): evidence["frozen_bytes"][p.relative_to(folder).as_posix()] = f3_evidence.sha(p.read_bytes())
                    elif f3_report not in ("valid","ambiguous"):
                        evidence = f3_report
                    f3_models.dump(folder/"report.json",evidence)
                    if f3_report == "ambiguous":
                        f3_models.dump(folder.with_name("f3_full_ambiguous_UNIT_MODEL")/"report.json",evidence)
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

            real_full_validator = f3_full_evidence.validate
            def unit_full_validator(*args, **kwargs):
                result = real_full_validator(*args, **kwargs)
                if not f3_complete:
                    # Scope refusal control only; never promote minimal evidence.
                    result = {**result,"full_f3_acceptance":False,"planned_only":f3_evidence.PLANNED}
                return result
            with patch.object(acceptance, "PROJECT", root), patch.object(sys, "argv", ["phase6_verify.py"]), patch.object(acceptance.subprocess, "run", side_effect=run), patch.object(acceptance.subprocess, "check_output", return_value="fixture-head\n"), f3_full_models.model_environment(root), patch.object(f3_full_evidence,"validate",side_effect=unit_full_validator), contextlib.redirect_stdout(io.StringIO()):
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

    def test_phase11_f1_retained_owner_gate_is_mandatory(self):
        self.assertEqual(self.simulate(lambda root: None), 0)
        commands = [c for c in self.last_commands if "retained_owner" in c]
        self.assertEqual(len(commands), 1)
        self.assertIn("--test-threads=1", commands[0])
        self.assertEqual(self.last_report["counts"]["f1_retained_owner"], {"pass": 9, "fail": 0})
        self.assertEqual(self.last_report["gates_total"], 70)

    def test_phase11_missing_or_wrong_f1_identities_cannot_publish(self):
        declared = self.declared_f1_retained_owner_names()
        impostor = "memory::paging::retained_owner::tests::impostor_frame_is_not_declared"
        substituted = next(n for n in declared if "alias_failure" in n).replace("alias_failure", "alias_renamed")
        for text in ("",
                     "test result: ok. 0 passed; 0 failed; 0 ignored\n",
                     "\n".join(f"test {name} ... ok" for name in declared[:8]) + "\n"
                     "test result: ok. 8 passed; 0 failed; 0 ignored\n",
                     "\n".join(f"test {name} ... ok" for name in declared) + "\n"
                     f"test {impostor} ... ok\n"
                     "test result: ok. 10 passed; 0 failed; 0 ignored\n",
                     "\n".join(f"test {name} ... ok" for name in [substituted] + [n for n in declared if n != substituted.replace("alias_renamed", "alias_failure")]) + "\n"
                     "test result: ok. 9 passed; 0 failed; 0 ignored\n"):
            with self.subTest(output=text):
                self.assertEqual(self.simulate(lambda root: None,
                    safety_output={"retained_owner": text}), 1)
                self.assertEqual(self.last_versioned_count, 0)

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
        # Preserve all 68 predecessor gates; add only F3 host and hardware gates.
        self.assertEqual(self.last_report["gates_total"], 70)
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
        self.assertEqual(self.last_report["gates_total"], 70)

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
        self.assertEqual(self.last_report["gates_total"], 70)

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
