"""Task-local P12-A raw-byte integrity; no build/guest/acceptance execution.

Only create_freeze writes (exclusive creation, never historical replacement).
All verifiers raise IntegrityError; success returns useful readback data, not approval.
Manifest required_artifacts is a nonempty list of {path, sha256}, externally bound
with the entire manifest. Review v1 has no declared canonical self-digest scheme;
verify_review therefore authenticates external raw bytes and actual reviewed pins.
"""
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
TASK = "test_results/phase12_p12a"
REVIEW_INPUTS = TASK + "/review_inputs_01.json"
PREFLIGHT = TASK + "/preflight_01.json"
BACKUP = TASK + "/git_backup_manifest_01.json"
# Explicit, genuinely required authorities only. Parent may extend before freeze.
SUPPLEMENTAL_FIXED_DEPENDENCIES = ()
PHASE6_SHA256 = "394dfcfa9e5d40ebb56c614ac2356a4c930fbbd80b418c408f46b30daf388b20"
REVIEW_INPUTS_SHA256 = "7f0c86f924b01025a15f0fcbfb16111acf2e922b05746b137af80614d933113e"
PREFLIGHT_SHA256 = "bf29c886c3761943bdd1ccedf124cd6c5a83996d0ef6bd78e1c0b5f499e193d1"
BACKUP_SHA256 = ""  # Backup authority is bound by freeze; original protected set cross-checks preflight.
FREEZE_SCHEMA = "rosti.p12a-source-freeze.v2"
LIB_HISTORICAL_SHA256 = "d975e34b3e9ae7201c82d177e7ca5c153c6eb32c8a0e05596e06a1aa94979189"
LIB_ADDITION = (b'#[path = "../../src/p12a_policy.rs"]\n'
                b'pub mod p12a_policy;\n\n'
                b'#[path = "p12a_policy_tests.rs"]\n'
                b'pub mod p12a_policy_tests;\n\n')


class IntegrityError(RuntimeError):
    """Authentication, membership, schema or observation failed closed."""


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _runtime():
    _require(sys.flags.optimize == 0, "optimized integrity execution refused")


def _pin(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "malformed raw SHA256 pin")
    return value


def _relative_argument(value):
    # Public callers may pass absolute Path objects; manifest members stay strict strings.
    if isinstance(value, Path):
        try:
            return value.relative_to(ROOT).as_posix() if value.is_absolute() else value.as_posix()
        except ValueError as error:
            raise IntegrityError("path outside repository") from error
    return value


def _path(value, must_exist=True):
    value = _relative_argument(value)
    _require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
             "path must be canonical repository-relative POSIX spelling")
    parts = value.split("/")
    _require(not any(x in ("", ".", "..") or x.endswith((" ", ".")) for x in parts)
             and not any(ord(c) < 32 for c in value), "nonnormal path")
    _require(PurePosixPath(value).as_posix() == value, "noncanonical path")
    current = ROOT
    for index, part in enumerate(parts):
        _require(current.is_dir(), "missing parent: " + value)
        names = {p.name for p in current.iterdir()}
        if part not in names:
            _require(not must_exist and index == len(parts) - 1, "missing/wrong-case path: " + value)
        current = current / part
        _require(not current.is_symlink() and not getattr(current, "is_junction", lambda: False)(),
                 "path substitution via symlink/junction: " + value)
    _require(not must_exist or current.is_file(), "missing/nonfile input: " + value)
    _require(current.resolve().is_relative_to(ROOT.resolve()), "path escapes repository")
    return current


def sha256(path):
    """Hash canonical repo-relative file, raw bytes only."""
    return hashlib.sha256(_path(path).read_bytes()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _json_bytes(raw):
    try:
        doc = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda x: (_ for _ in ()).throw(IntegrityError("nonfinite JSON")))
    except (ValueError, UnicodeError) as error:
        raise IntegrityError("malformed JSON") from error
    _require(isinstance(doc, dict), "JSON object required")
    return doc


def _read(path, expected=None):
    path = _relative_argument(path)
    raw = _path(path).read_bytes()
    if expected is not None:
        _require(hashlib.sha256(raw).hexdigest() == _pin(expected), "raw hash mismatch: " + path)
    return _json_bytes(raw)


def _entries(entries, hash_key="sha256"):
    _require(isinstance(entries, list) and entries, "nonempty explicit artifact/input list required")
    result = {}
    folded = set()
    for entry in entries:
        _require(isinstance(entry, dict), "artifact/input object required")
        path = entry.get("path")
        _path(path)
        _require(path.casefold() not in folded, "duplicate artifact/input path")
        folded.add(path.casefold())
        result[path] = _pin(entry.get(hash_key))
    return result


def _map(value):
    _require(isinstance(value, dict) and value, "nonempty input map required")
    return _entries([{"path": p, "sha256": h} for p, h in value.items()])


def _check_pins(pins):
    for path, expected in pins.items():
        _require(sha256(path) == _pin(expected), "raw hash mismatch: " + path)


def canonical_snapshot():
    """Call actual inspected phase6 function, without running its guarded main.

    Exact inspected module raw pin prevents executing modified top-level/import code.
    Imports are stdlib only; top level defines constants/functions, guarded main.
    source_snapshot reads/enumerates files and sha256; it performs no writes/jobs.
    """
    _runtime()
    path = "scripts/phase6_verify.py"
    _require(sha256(path) == PHASE6_SHA256, "phase6 inspected module identity changed")
    spec = importlib.util.spec_from_file_location("_p12a_readonly_phase6", _path(path))
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        _require(module.PROJECT.resolve() == ROOT.resolve(), "canonical root substitution")
        snapshot = _map(module.source_snapshot())
    finally:
        sys.dont_write_bytecode = old
    _check_pins(snapshot)
    return dict(sorted(snapshot.items()))


def extra_inputs():
    """Dynamic direct task wrappers plus immutable authority/provenance closure.

    Does not glob generated reports/evidence/reviews, live STATE or decisions.
    Named historical baseline/RED artifacts are dependencies, not current outputs.
    """
    _runtime()
    paths = {REVIEW_INPUTS, PREFLIGHT, BACKUP,
             TASK + "/p12a_contract.md", TASK + "/p12a_allowlist.json",
             TASK + "/reviews/design_review_01.json",
             TASK + "/reviews/readiness_audit_01.json",
             TASK + "/reviews/budget_reconstruction_01.json",
             TASK + "/STATE_budget_review_snapshot_01.md",
             TASK + "/filter_audit_01.json", TASK + "/mock_gate_decision_01.json",
             TASK + "/hashing_method_01.json", TASK + "/reviewer_disclosure_preflight_01.json",
             TASK + "/remediation_compliance_01.md"}
    for directory in (TASK, "test_results/p12a"):
        for p in (ROOT / directory).iterdir():
            if p.suffix in (".py", ".rs") and p.is_file():
                paths.add(p.relative_to(ROOT).as_posix())
    review = _read(REVIEW_INPUTS, REVIEW_INPUTS_SHA256)
    for key in ("contract", "phase12_design", "review_inputs_01", "source_inventory",
                "f5_final_report", "f5_evidence_manifest", "f5_acceptance",
                "baseline_report", "baseline_elf_A", "baseline_elf_B", "filter_audit"):
        paths.add(review[key])
    # Transitive approved design-review and inventory pins are immutable
    # authority inputs too, including historical docs and design decisions.
    design_manifest = _read(review["review_inputs_01"], review["review_inputs_01_sha256"])
    paths.update(design_manifest["pins"])
    inventory = _read(review["source_inventory"], review["source_inventory_sha256"])
    paths.update(row["path"] for row in inventory["source_files"].values())
    # Immutable dependencies of approved phase12 design, excluding mutable context.
    backup = _read(BACKUP)
    for entry in backup["included"]:
        if (entry.get("classification") == "APPROVED_DESIGN_AUTHORITY"
                and Path(entry["path"]).name not in ("STATE.md", "decisions.md", "KICKOFF_REPORT.md")
                and not Path(entry["path"]).name.startswith("parent_review_readback")):
            paths.add(entry["path"])
    # Complete immutable baseline input provenance, including logs/binaries.
    for p in (ROOT / "test_results/p12a/b01").iterdir():
        if p.is_file():
            paths.add(p.relative_to(ROOT).as_posix())
    # These authorities appear during bounded remediation; freeze captures membership.
    for pattern in ("remediation_plan_*.json", "red_provenance_*.json",
                    "red_disclosure_*.md", "red_disclosure_*.json", "original_red_*.log",
                    "STATE_remediation_snapshot_*.md"):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / TASK).glob(pattern) if p.is_file())
    paths.update(SUPPLEMENTAL_FIXED_DEPENDENCIES)
    for p in paths:
        _require(p not in (TASK + "/STATE.md", TASK + "/decisions.md", "test_results/phase12_design/STATE.md"), "mutable live context cannot be frozen")
        _path(p)
    return sorted(paths)


def enumerate_inputs():
    """Return current canonical+extras {exact relative path: raw SHA256}."""
    _runtime()
    result = canonical_snapshot()
    result.update({p: sha256(p) for p in extra_inputs()})
    return dict(sorted(_map(result).items()))


def create_freeze(path):
    """Exclusive-create numbered freeze and return its manifest; path is repo relative."""
    _runtime()
    path = _relative_argument(path)
    canonical = canonical_snapshot()
    inputs = enumerate_inputs()
    _require(all(inputs.get(p) == h for p, h in canonical.items()), "unstable canonical snapshot")
    doc = {"schema": FREEZE_SCHEMA, "canonical_inputs": canonical,
           "inputs": [{"path": p, "sha256": h} for p, h in inputs.items()],
           "input_count": len(inputs)}
    verify_freeze(doc)
    target = _path(path, must_exist=False)
    _require(path not in inputs, "freeze cannot bind itself")
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(doc, indent=2) + "\n")
    return doc


def verify_freeze(freeze):
    """Exact fresh membership/bytes and canonical map readback; dict or relative path."""
    _runtime()
    doc = _read(freeze) if isinstance(freeze, (str, Path)) else freeze
    _require(isinstance(doc, dict) and doc.get("schema") == FREEZE_SCHEMA, "wrong freeze schema")
    pins = _entries(doc.get("inputs"))
    _require(type(doc.get("input_count")) is int and doc["input_count"] == len(pins), "wrong input_count")
    canonical = _map(doc.get("canonical_inputs"))
    _require(canonical == canonical_snapshot(), "canonical membership/bytes changed")
    _require(all(pins.get(p) == h for p, h in canonical.items()), "freeze omits canonical input")
    _require(pins == enumerate_inputs(), "freeze membership/raw bytes changed")
    return {"input_count": len(pins), "canonical_count": len(canonical)}


def _no_self_claims(value):
    if isinstance(value, dict):
        for key, item in value.items():
            _require(key.lower() not in {"self_sha256", "self_digest", "self_hash", "digest", "manifest_sha256"},
                     "circular/undeclared manifest digest claim")
            _no_self_claims(item)
    elif isinstance(value, list):
        for item in value:
            _no_self_claims(item)


def verify_review(path, expected_external_sha256):
    """Authenticate existing no-self-digest review schema and every declared input."""
    _runtime()
    doc = _read(path, expected_external_sha256)
    _require("self_sha256" not in doc and "self_digest" not in doc,
             "no reviewed self-digest schema declared; use external raw pin")
    rim = doc.get("reviewed_input_manifest")
    _require(isinstance(rim, dict), "review input manifest missing")
    inputs = _read(rim.get("path"), rim.get("raw_sha256"))
    _pin(rim.get("raw_sha256"))
    pins = _entries(rim.get("pin_verification"), "expected")
    _require(type(rim.get("pin_count")) is int and rim["pin_count"] == len(pins), "review pin_count mismatch")
    # Verify names resolve to exactly their approved manifest paths AND raw pins.
    for entry in rim["pin_verification"]:
        name = entry.get("name")
        _require(isinstance(name, str) and inputs.get(name) == entry["path"]
                 and inputs.get(name + "_sha256") == entry["expected"], "review pin/path substitution")
    _check_pins(pins)
    return {"path": path, "input_count": len(pins), "identity": "externally_pinned_raw_no_self_digest"}


def verify_manifest(manifest, expected_external_sha256):
    """Authenticate v1 evidence via external raw pin and explicit required pins."""
    _runtime()
    manifest = _relative_argument(manifest)
    doc = _read(manifest, _pin(expected_external_sha256))
    _require(doc.get("schema") == "rosti.p12a-evidence.v1", "wrong evidence schema")
    _require(isinstance(doc.get("status"), str) and doc["status"]
             and doc["status"] != "PREIMPLEMENTATION", "absent/preimplementation evidence")
    _no_self_claims(doc)
    pins = _entries(doc.get("artifacts"))
    required = _entries(doc.get("required_artifacts"))
    _require(manifest not in pins and manifest not in required, "manifest cannot hash itself")
    _require(all(pins.get(p) == h for p, h in required.items()), "required evidence pin missing/wrong path/hash")
    _check_pins(pins)
    for path, pin in pins.items():
        if path.endswith(".json"):
            review = _read(path, pin)
            if "reviewed_input_manifest" in review:
                verify_review(path, pin)
    return {"artifact_count": len(pins), "required_count": len(required), "status": doc["status"]}


def verify_predecessor():
    """Authenticate F5 raw bindings/PASS76 and every historical manifest artifact."""
    _runtime()
    review = _read(REVIEW_INPUTS, REVIEW_INPUTS_SHA256)
    pre = _read(PREFLIGHT, PREFLIGHT_SHA256)["f5_predecessor"]
    for key in ("f5_final_report", "f5_evidence_manifest", "f5_acceptance"):
        path, pin = review[key], _pin(review[key + "_sha256"])
        _require(pre["files"].get(path) == pin, "F5 authority disagreement")
        _check_pins({path: pin})
    _require(pre["path"] == review["f5_acceptance"] and pre["sha256"] == review["f5_acceptance_sha256"]
             and pre["actual_exit"] == 0, "F5 preflight identity/exit mismatch")
    acceptance = _read(review["f5_acceptance"], review["f5_acceptance_sha256"])
    gates = acceptance.get("gates")
    _require(isinstance(gates, list) and len(gates) == 76 and len(pre["gates"]) == 76,
             "F5 exact 76 gates required")
    _require(acceptance.get("overall") == "PASS" and acceptance.get("gates_passed") == 76
             and acceptance.get("gates_total") == 76, "F5 not PASS76")
    _require(all(isinstance(g, dict) and isinstance(g.get("gate"), str)
                 and g.get("status") == "PASS" and type(g.get("exit_code")) is int
                 and g["exit_code"] == 0 for g in gates), "F5 failed/skipped gate")
    _require(Counter(g["gate"] for g in gates) == Counter(pre["gates"]), "F5 gate multiset mismatch")
    manifest = _read(review["f5_evidence_manifest"], review["f5_evidence_manifest_sha256"])
    _require(manifest.get("schema") == "rosti.f5-final-evidence-manifest.v1", "wrong F5 manifest schema")
    pins = _entries(manifest.get("artifacts"))
    _require(manifest.get("artifact_count") == len(pins), "F5 artifact count mismatch")
    dispositions = []
    for entry in manifest["artifacts"]:
        path, expected = entry["path"], entry["sha256"]
        got = sha256(path)
        if path == review["f5_final_report"]:
            _require(entry.get("source_binding") == "historical_self_bound; not transferred to current candidate"
                     and entry.get("status") == "historical_immutable_evidence"
                     and expected == review["f5_final_report_sha256"] and got == expected,
                     "invalid historical_self_bound report disposition")
            dispositions.append({"path": path, "disposition": "historical_self_bound_not_current_candidate"})
        elif got != expected and path == "tests_kernel/src/lib.rs":
            raw = _path(path).read_bytes()
            _require(expected == LIB_HISTORICAL_SHA256 and raw.count(LIB_ADDITION) == 1,
                     "lib delta is not exact six authorized wiring lines")
            historical = raw.replace(LIB_ADDITION, b"", 1)
            _require(hashlib.sha256(historical).hexdigest() == expected, "unrelated lib delta")
            dispositions.append({"path": path, "disposition": "exact_six_line_authorized_host_wiring",
                                 "historical_sha256": expected, "current_sha256": got})
        else:
            _require(got == expected, "F5 artifact mismatch: " + path)
    return {"gates": 76, "artifact_count": len(pins), "dispositions": dispositions}


def verify_protected():
    """Hash original eight from backup, cross-authenticated by pinned preflight."""
    _runtime()
    backup = _read(BACKUP)
    _require(backup.get("schema") == "rosti.p12a-git-backup-manifest.v1", "wrong backup schema")
    pins = _entries(backup.get("protected"), "raw_sha256")
    original = _entries(_read(PREFLIGHT, PREFLIGHT_SHA256).get("protected"))
    _require(len(pins) == 8 and pins == original, "original eight protected paths/pins changed")
    _check_pins(pins)
    return pins


def verify_processes():
    """Observe native processes with psutil; refuse active heavy tools or uncertainty."""
    _runtime()
    try:
        import psutil
        observed = []
        for process in psutil.process_iter():
            try:
                name = process.name().lower()
                stem = name.removesuffix(".exe")
                if stem in {"cargo", "rustc", "rust-lld", "lld", "ld", "link"} or stem.startswith("qemu"):
                    observed.append({"pid": process.pid, "name": name})
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied as error:
                raise IntegrityError("native process observation denied") from error
    except ImportError as error:
        raise IntegrityError("psutil required for real native process observation") from error
    _require(not observed, "active heavy native processes: " + json.dumps(observed))
    return {"observer": "psutil", "active_heavy_processes": observed}


def observe_processes():
    """Parent-facing read-only process API; refuses heavy native jobs."""
    return verify_processes()


def main(argv=None):
    try:
        _runtime()
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("action", choices=("enumerate", "predecessor", "protected", "processes", "verify-freeze", "verify-manifest"))
        parser.add_argument("path", nargs="?")
        parser.add_argument("external_sha256", nargs="?")
        args = parser.parse_args(argv)
        if args.action == "verify-freeze":
            result = verify_freeze(args.path)
        elif args.action == "verify-manifest":
            result = verify_manifest(args.path, args.external_sha256)
        else:
            result = {"enumerate": enumerate_inputs, "predecessor": verify_predecessor,
                      "protected": verify_protected, "processes": verify_processes}[args.action]()
        print(json.dumps(result, indent=2))
        return 0
    except (IntegrityError, OSError, KeyError, TypeError, ValueError) as error:
        print("INTEGRITY_REFUSED: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
