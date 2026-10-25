"""Lightweight integrity controls. All mutations are isolated temp-root fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import integrity_02 as integrity


class IntegrityControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="integrity02_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(integrity, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.put("src/a.rs", b"source\r\n")
        self.put("extra/wrapper.py", b"wrapper\n")
        self.put("extra/review.json", b"{}\n")
        self.canonical_patch = patch.object(integrity, "canonical_snapshot", side_effect=self.canonical)
        self.canonical_patch.start()
        self.addCleanup(self.canonical_patch.stop)
        self.extras_patch = patch.object(integrity, "extra_inputs", return_value=["extra/wrapper.py", "extra/review.json"])
        self.extras_patch.start()
        self.addCleanup(self.extras_patch.stop)
        self.put("manifest.json", b"{}")

    def put(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value).encode() if isinstance(value, dict) else value
        target.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def canonical(self):
        return {"src/a.rs": integrity.sha256("src/a.rs")}

    def freeze(self):
        canonical = self.canonical()
        pins = integrity.enumerate_inputs()
        return {"schema": integrity.FREEZE_SCHEMA, "canonical_inputs": canonical,
                "inputs": [{"path": p, "sha256": h} for p, h in pins.items()], "input_count": len(pins)}

    def manifest(self):
        entry = {"path": "extra/review.json", "sha256": integrity.sha256("extra/review.json")}
        return {"schema": "rosti.p12a-evidence.v1", "status": "VERIFIED_HOST_ONLY",
                "artifacts": [entry], "required_artifacts": [copy.deepcopy(entry)]}

    def verify_manifest(self, doc):
        pin = self.put("manifest.json", doc)
        return integrity.verify_manifest("manifest.json", pin)

    def test_valid_freeze_and_exclusive_create(self):
        expected = self.freeze()
        self.assertEqual(integrity.create_freeze("freeze.json"), expected)
        self.assertEqual(integrity.verify_freeze("freeze.json"), {"input_count": 3, "canonical_count": 1})
        with self.assertRaises(FileExistsError):
            integrity.create_freeze("freeze.json")

    def test_public_path_objects(self):
        integrity.create_freeze(self.root / "freeze.json")
        self.assertEqual(integrity.verify_freeze(self.root / "freeze.json")["input_count"], 3)
        pin = self.put("manifest.json", self.manifest())
        self.assertEqual(integrity.verify_manifest(self.root / "manifest.json", pin)["required_count"], 1)

    def test_removed_required_canonical_input(self):
        doc = self.freeze()
        doc["inputs"] = [e for e in doc["inputs"] if e["path"] != "src/a.rs"]
        doc["input_count"] -= 1
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_removed_extra_even_with_adjusted_count(self):
        doc = self.freeze()
        doc["inputs"].pop()
        doc["input_count"] -= 1
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_duplicate_input(self):
        doc = self.freeze()
        doc["inputs"].append(copy.deepcopy(doc["inputs"][0]))
        doc["input_count"] += 1
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_bad_hash(self):
        doc = self.freeze()
        doc["inputs"][0]["sha256"] = "0" * 64
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_missing_file(self):
        doc = self.freeze()
        (self.root / "extra/review.json").unlink()
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_malformed_pin(self):
        for bad in (None, "", "a" * 63, "A" * 64, 1, "g" * 64):
            with self.subTest(pin=bad):
                doc = self.freeze()
                doc["inputs"][0]["sha256"] = bad
                with self.assertRaises(integrity.IntegrityError):
                    integrity.verify_freeze(doc)

    def test_same_basename_wrong_path(self):
        doc = self.freeze()
        self.put("elsewhere/review.json", b"{}\n")
        next(e for e in doc["inputs"] if e["path"] == "extra/review.json")["path"] = "elsewhere/review.json"
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_unreflected_changed_input(self):
        doc = self.freeze()
        self.put("extra/wrapper.py", b"changed\n")
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_new_input_membership(self):
        doc = self.freeze()
        self.put("extra/new.rs", b"new")
        self.extras_patch.stop()
        with patch.object(integrity, "extra_inputs", return_value=["extra/wrapper.py", "extra/review.json", "extra/new.rs"]):
            with self.assertRaises(integrity.IntegrityError):
                integrity.verify_freeze(doc)

    def test_canonical_map_changed(self):
        doc = self.freeze()
        self.put("src/a.rs", b"new source")
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_freeze(doc)

    def test_nonnormal_paths(self):
        for bad in ("./extra/review.json", "extra/../extra/review.json", "extra//review.json",
                    "/extra/review.json", "extra\\review.json", "EXTRA/review.json",
                    "C:/extra/review.json", "extra/review.json."):
            with self.subTest(path=bad), self.assertRaises(integrity.IntegrityError):
                integrity._path(bad)

    def test_wrong_input_count(self):
        for count in (True, 0, "3", 4):
            doc = self.freeze()
            doc["input_count"] = count
            with self.subTest(count=count), self.assertRaises(integrity.IntegrityError):
                integrity.verify_freeze(doc)

    def test_valid_manifest(self):
        self.assertEqual(self.verify_manifest(self.manifest())["required_count"], 1)

    def test_manifest_missing_evidence(self):
        doc = self.manifest()
        doc["artifacts"] = []
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_external_wrong_hash(self):
        self.put("manifest.json", self.manifest())
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_manifest("manifest.json", "0" * 64)

    def test_manifest_missing_required_pin(self):
        for mode in ("field", "empty", "hash"):
            doc = self.manifest()
            if mode == "field":
                del doc["required_artifacts"]
            elif mode == "empty":
                doc["required_artifacts"] = []
            else:
                del doc["required_artifacts"][0]["sha256"]
            with self.subTest(mode=mode), self.assertRaises(integrity.IntegrityError):
                self.verify_manifest(doc)

    def test_manifest_required_removed(self):
        doc = self.manifest()
        self.put("extra/other.log", b"other")
        doc["artifacts"] = [{"path": "extra/other.log", "sha256": integrity.sha256("extra/other.log")}]
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_manifest_wrong_path_same_basename(self):
        doc = self.manifest()
        self.put("elsewhere/review.json", b"{}\n")
        doc["artifacts"][0]["path"] = "elsewhere/review.json"
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_manifest_changed_artifact(self):
        doc = self.manifest()
        self.put("extra/review.json", b"changed review\n")
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_manifest_invalid_canonicalization(self):
        doc = self.manifest()
        doc["artifacts"][0]["path"] = "extra/./review.json"
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_malformed_manifest(self):
        for raw in (b"{", b"[]", b'{"schema":1,"schema":2}', b'{"n":NaN}', b'\xff'):
            pin = self.put("manifest.json", raw)
            with self.subTest(raw=raw), self.assertRaises(integrity.IntegrityError):
                integrity.verify_manifest("manifest.json", pin)

    def test_manifest_circular_self_claim(self):
        for field in ("self_sha256", "self_digest", "self_hash", "digest", "manifest_sha256"):
            doc = self.manifest()
            doc[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(integrity.IntegrityError):
                self.verify_manifest(doc)

    def test_manifest_lists_itself(self):
        doc = self.manifest()
        doc["artifacts"].append({"path": "manifest.json", "sha256": "0" * 64})
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_manifest_duplicate_artifacts(self):
        doc = self.manifest()
        doc["artifacts"].append(copy.deepcopy(doc["artifacts"][0]))
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def review_fixture(self):
        source_pin = integrity.sha256("src/a.rs")
        inputs_pin = self.put("review_inputs.json", {"source": "src/a.rs", "source_sha256": source_pin})
        doc = {"schema": "rosti.p12a-independent-contract-review.v1",
               "reviewed_input_manifest": {"path": "review_inputs.json", "raw_sha256": inputs_pin,
                  "pin_count": 1, "pin_verification": [{"name": "source", "path": "src/a.rs", "expected": source_pin}]}}
        pin = self.put("reviews/design.json", doc)
        return doc, pin

    def test_review_external_pin_and_changed_input(self):
        doc, pin = self.review_fixture()
        self.assertEqual(integrity.verify_review("reviews/design.json", pin)["input_count"], 1)
        self.put("src/a.rs", b"changed")
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_review("reviews/design.json", pin)

    def test_review_manifest_changed(self):
        doc, pin = self.review_fixture()
        self.put("review_inputs.json", {})
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_review("reviews/design.json", pin)

    def test_review_wrong_path_even_with_correct_bytes(self):
        doc, _ = self.review_fixture()
        self.put("elsewhere/a.rs", b"source\r\n")
        doc["reviewed_input_manifest"]["pin_verification"][0]["path"] = "elsewhere/a.rs"
        pin = self.put("reviews/design.json", doc)
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_review("reviews/design.json", pin)

    def test_review_no_invented_self_hash(self):
        doc, _ = self.review_fixture()
        doc["self_sha256"] = "0" * 64
        pin = self.put("reviews/design.json", doc)
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_review("reviews/design.json", pin)

    def test_nested_review_changed_input_via_manifest(self):
        _, review_pin = self.review_fixture()
        entry = {"path": "reviews/design.json", "sha256": review_pin}
        doc = {"schema": "rosti.p12a-evidence.v1", "status": "HOST_ONLY",
               "artifacts": [entry], "required_artifacts": [entry]}
        self.verify_manifest(doc)
        self.put("src/a.rs", b"changed")
        with self.assertRaises(integrity.IntegrityError):
            self.verify_manifest(doc)

    def test_native_heavy_process_refused(self):
        for name in ("cargo.exe", "rustc.exe", "link.exe", "qemu-system-i386.exe"):
            process = types.SimpleNamespace(pid=123, name=lambda n=name: n)
            with self.subTest(name=name), patch("psutil.process_iter", return_value=[process]):
                with self.assertRaises(integrity.IntegrityError):
                    integrity.verify_processes()

    def test_native_empty_observation(self):
        with patch("psutil.process_iter", return_value=[]):
            self.assertEqual(integrity.verify_processes()["active_heavy_processes"], [])

    def predecessor_fixture(self):
        """Synthetic F5 shape in temp root only; not evidence for real PASS76."""
        report = "f5/FINAL_REPORT.md"
        manifest = "f5/evidence_manifest.json"
        acceptance = "f5/acceptance.json"
        report_pin = self.put(report, b"historical report")
        artifact_pin = self.put("f5/other.log", b"artifact")
        live_lib = Path(integrity.__file__).resolve().parents[2] / "tests_kernel/src/lib.rs"
        self.put("tests_kernel/src/lib.rs", live_lib.read_bytes())
        self.put(manifest, {"schema": "rosti.f5-final-evidence-manifest.v1", "artifact_count": 3,
             "artifacts": [{"path": report, "sha256": report_pin,
                "source_binding": "historical_self_bound; not transferred to current candidate",
                "status": "historical_immutable_evidence"},
                {"path": "f5/other.log", "sha256": artifact_pin},
                {"path": "tests_kernel/src/lib.rs", "sha256": integrity.LIB_HISTORICAL_SHA256}]})
        gates = ["fixture gate " + str(i) for i in range(76)]
        self.put(acceptance, {"overall": "PASS", "gates_total": 76, "gates_passed": 76,
              "gates": [{"gate": g, "status": "PASS", "exit_code": 0} for g in gates]})
        review = {"f5_final_report": report, "f5_evidence_manifest": manifest, "f5_acceptance": acceptance}
        for key in list(review):
            review[key + "_sha256"] = integrity.sha256(review[key])
        review_pin = self.put(integrity.REVIEW_INPUTS, review)
        pre = {"f5_predecessor": {"path": acceptance, "sha256": integrity.sha256(acceptance),
               "gates": gates, "actual_exit": 0, "files": {review[key]: review[key + "_sha256"]
                for key in ("f5_final_report", "f5_evidence_manifest", "f5_acceptance")}}}
        pre_pin = self.put(integrity.PREFLIGHT, pre)
        for name, pin in (("REVIEW_INPUTS_SHA256", review_pin), ("PREFLIGHT_SHA256", pre_pin)):
            p = patch.object(integrity, name, pin)
            p.start()
            self.addCleanup(p.stop)
        return review, pre

    def test_predecessor_exact_dispositions(self):
        self.predecessor_fixture()
        self.assertEqual(len(integrity.verify_predecessor()["dispositions"]), 2)

    def test_predecessor_changed_nonlib_artifact_refused(self):
        self.predecessor_fixture()
        self.put("f5/other.log", b"changed")
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_predecessor()

    def test_predecessor_unrelated_lib_delta_refused(self):
        self.predecessor_fixture()
        path = self.root / "tests_kernel/src/lib.rs"
        self.put("tests_kernel/src/lib.rs", path.read_bytes() + b"// unrelated delta\n")
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_predecessor()

    def test_predecessor_changed_top_level_raw_binding(self):
        self.predecessor_fixture()
        self.put("f5/FINAL_REPORT.md", b"changed")
        with self.assertRaises(integrity.IntegrityError):
            integrity.verify_predecessor()

    def test_predecessor_wrong_gate_multiset_despite_pass76(self):
        review, pre = self.predecessor_fixture()
        path = review["f5_acceptance"]
        doc = json.loads((self.root / path).read_bytes())
        doc["gates"][0]["gate"] = doc["gates"][1]["gate"]
        pin = self.put(path, doc)
        review["f5_acceptance_sha256"] = pin
        pre["f5_predecessor"]["sha256"] = pin
        pre["f5_predecessor"]["files"][path] = pin
        with patch.object(integrity, "REVIEW_INPUTS_SHA256", self.put(integrity.REVIEW_INPUTS, review)), \
             patch.object(integrity, "PREFLIGHT_SHA256", self.put(integrity.PREFLIGHT, pre)):
            with self.assertRaises(integrity.IntegrityError):
                integrity.verify_predecessor()

    def test_original_protected_changed_pin_or_path_refused(self):
        entries = []
        for index in range(8):
            path = "protected/" + str(index)
            entries.append({"path": path, "sha256": self.put(path, b"original")})
        backup = {"schema": "rosti.p12a-git-backup-manifest.v1",
                  "protected": [{"path": e["path"], "raw_sha256": e["sha256"]} for e in entries]}
        self.put(integrity.BACKUP, backup)
        pin = self.put(integrity.PREFLIGHT, {"protected": entries})
        with patch.object(integrity, "PREFLIGHT_SHA256", pin):
            self.assertEqual(len(integrity.verify_protected()), 8)
            self.put("protected/0", b"changed")
            with self.assertRaises(integrity.IntegrityError):
                integrity.verify_protected()

    def test_unauthenticated_phase6_never_executes(self):
        self.canonical_patch.stop()
        self.put("scripts/phase6_verify.py", b"raise RuntimeError('must not execute')\n")
        with self.assertRaisesRegex(integrity.IntegrityError, "identity changed"):
            integrity.canonical_snapshot()

    def test_actual_optimized_subprocess_refuses(self):
        result = subprocess.run([sys.executable, "-B", "-O", str(Path(integrity.__file__).resolve()), "enumerate"],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("optimized integrity execution refused", result.stderr)


class RealReadOnlyChecks(unittest.TestCase):
    def test_actual_canonical_snapshot(self):
        snapshot = integrity.canonical_snapshot()
        self.assertIn("src/p12a_policy.rs", snapshot)
        self.assertIn("tests_kernel/src/p12a_policy_tests.rs", snapshot)
        self.assertIn("tests_kernel/src/lib.rs", snapshot)
        self.assertEqual(snapshot["scripts/phase6_verify.py"], integrity.PHASE6_SHA256)

    def test_actual_enumeration_and_in_memory_freeze(self):
        canonical = integrity.canonical_snapshot()
        inputs = integrity.enumerate_inputs()
        for path, pin in canonical.items():
            self.assertEqual(inputs[path], pin)
        self.assertIn("test_results/phase12_p12a/integrity_02.py", inputs)
        self.assertIn("test_results/phase12_p12a/test_integrity_02.py", inputs)
        self.assertNotIn("test_results/phase12_p12a/STATE.md", inputs)
        self.assertNotIn("test_results/phase12_p12a/evidence_manifest.json", inputs)
        freeze = {"schema": integrity.FREEZE_SCHEMA, "canonical_inputs": canonical,
                  "inputs": [{"path": p, "sha256": h} for p, h in inputs.items()], "input_count": len(inputs)}
        self.assertEqual(integrity.verify_freeze(freeze)["input_count"], len(inputs))

    def test_actual_original_eight_protected(self):
        self.assertEqual(len(integrity.verify_protected()), 8)

    def test_actual_predecessor(self):
        result = integrity.verify_predecessor()
        self.assertEqual(result["gates"], 76)
        self.assertTrue(any(d["disposition"] == "exact_six_line_authorized_host_wiring"
                            for d in result["dispositions"]))

    def test_actual_review_without_self_hash(self):
        result = integrity.verify_review("test_results/phase12_p12a/reviews/design_review_01.json",
                                        "5cbdc5401e80d0c883f12a69398f0a69ac9d9a7bb2f0dfbae6975d45686156f8")
        self.assertEqual(result["input_count"], 9)


if __name__ == "__main__":
    if sys.flags.optimize:
        raise SystemExit("optimized test execution refused")
    unittest.main(verbosity=2)
