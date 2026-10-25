"""Read-only input reconciliation; writes only a new numbered task record.
Not independent review, test execution, CPL3 proof, or implementation permission.
"""
import collections
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if sys.flags.optimize:
    raise RuntimeError("optimized verification refused")
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from phase6_verify import F3_PREDECESSOR_GATES, F4_GATES, source_snapshot


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def git(*args):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return {"argv": list(args), "exit": proc.returncode, "stdout": proc.stdout,
            "stderr": proc.stderr}


def reconcile(expected):
    return {p: {"expected": h, "actual": sha(ROOT / p),
                "match": sha(ROOT / p) == h} for p, h in expected.items()}


def main():
    if len(sys.argv) != 2:
        raise RuntimeError("usage: verify_continuation_04.py NEW_RECORD.json")
    output = Path(sys.argv[1]).resolve()
    if output.parent != BASE or output.exists():
        raise RuntimeError("output must be new file directly in task root")
    prior = load(BASE / "continuation_verification_03.json")
    old = load(BASE / "continuation_snapshot_02.json")
    recovery = load(BASE / "recovery_snapshot_01.json")
    review = load(BASE / "reviews/design_review_01.json")
    manifest = {p: v["expected"] for p, v in prior["unchanged_review01_inputs"].items()}
    review_inputs = {p: h for p, h in review["source_hashes"].items()
                     if p != "test_results/phase11f5_cpl3_proof/design.md"}
    current = source_snapshot()
    before = old["source_sha256"]
    delta = {p: {"old": before.get(p), "current": current.get(p)}
             for p in sorted(before.keys() | current.keys())
             if before.get(p) != current.get(p)}
    pins = reconcile(manifest)
    recovery_pins = reconcile(recovery["pins"])
    expected_authority = {
        "design.md": "44325607eb36e0a16a3692c212509acdfe3c8303999a2297a60ed82d772597a9",
        "design_proposal_01.md": "6d4eabbbe45349804a994d24016e81fe31ba4e3d6d0a20956ddca5cc9d6346bf",
        "reviews/design_review_01.json": "d9d8c719492656d41a73867e0f24806288d76124b051db1408bb4fa638f52161",
    }
    authority = {p: {"expected": h, "actual": sha(BASE / p), "match": sha(BASE / p) == h}
                 for p, h in expected_authority.items()}
    predecessor_path = review["gate_multiset"]["predecessor_path"]
    predecessor = load(ROOT / predecessor_path)
    expected_gates = collections.Counter(F3_PREDECESSOR_GATES) + collections.Counter(F4_GATES)
    actual_gates = collections.Counter(row["gate"] for row in predecessor["gates"])
    ancestry = git("merge-base", "--is-ancestor", "c1b28b2", "HEAD")
    conditions = {
        "exact_23_manifest": len(manifest) == 23 and manifest == review_inputs,
        "pinned_23_raw_bytes": all(v["match"] for v in pins.values()),
        "authority_bytes": all(v["match"] for v in authority.values()),
        "recovery_bytes": all(v["match"] for v in recovery_pins.values()),
        "source_membership_and_bytes": not delta,
        "f4_raw_hash": sha(ROOT / predecessor_path) == "3f9661a9446829288616ea32b1b7b3b0ff41207431edd3d22923b8a25b6452e4",
        "f4_pass_and_exact_gates": predecessor["overall"] == "PASS"
            and predecessor["gates_total"] == predecessor["gates_passed"] == 72
            and sum(actual_gates.values()) == 72 and actual_gates == expected_gates
            and all(r["status"] == "PASS" and r["exit_code"] == 0 for r in predecessor["gates"]),
        "accepted_f4_source_ancestry": ancestry["exit"] == 0,
    }
    report = {
        "schema": "rosti.f5.continuation-readonly-pin-check.v1",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall": "PASS" if all(conditions.values()) else "FAIL",
        "scope": "Input identity/provenance reconciliation only; not independent approval or fresh tests",
        "conditions": conditions, "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"), "worktree": git("status", "--short"),
        "ancestry": ancestry, "pinned_inputs": pins, "authority": authority,
        "recovery_pins": recovery_pins, "source_count": len(current),
        "source_sha256": current, "source_delta": delta,
        "f4_acceptance": {"path": predecessor_path, "sha256": sha(ROOT / predecessor_path),
                          "gates": dict(actual_gates)},
        "review02_present_at_check": (BASE / "reviews/design_review_02.json").exists(),
        "implementation_authorized_by_this_record": False,
        "independent_review_dispatch": "deleg_67ad2e7d / sa-0-fb13e3b6",
        "verifier_sha256": sha(Path(__file__)),
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"overall": report["overall"], "conditions": conditions,
                      "source_count": len(current), "record": str(output),
                      "record_sha256": sha(output)}, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
