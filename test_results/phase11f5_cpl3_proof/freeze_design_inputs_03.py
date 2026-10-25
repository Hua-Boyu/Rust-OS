"""Freeze proposal03 inputs and validate historical proposal02 review pins.
Creates new evidence only; does not authorize implementation or run tests.
"""
import collections
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

if sys.flags.optimize:
    raise RuntimeError("optimized verification refused")
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from phase6_verify import source_snapshot


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    review_path = BASE / "reviews/design_review_02.json"
    review = load(review_path)
    proposal = BASE / "design.md"
    historical = BASE / "design_proposal_02.md"
    need(sha(review_path) == "43cf36aeced0f76d91055b3cd2f18de3810b7b804b67b0d8890adf0605d000bc", "review02 changed")
    need(sha(historical) == review["design_raw_sha256"] == "44325607eb36e0a16a3692c212509acdfe3c8303999a2297a60ed82d772597a9", "historical proposal02 mismatch")
    need(sha(proposal) == "6b0b3a9324576b0fa148fa415fcaea23fe33a8e5f655da608e8ea56794a1791c", "proposal03 drift")
    need(review["schema"] == "rosti.f5-complete-design-review.v1", "review schema")
    need(review["verdict"] == "REJECT" and review["complete_scope"] is True, "review final disposition")
    need(review["blocker_count"] == len(review["blockers"]) == 2, "blocker count")
    need(review["reviewer"]["execution_context"] == "sa-0-fb13e3b6" and review["reviewer"]["delegation_id"] == "deleg_67ad2e7d", "independence provenance")
    need(len(review["findings"]) == 26 and {f["checklist_point"] for f in review["findings"]} == set(range(1, 27)), "complete checklist")
    need(set(review["checklist_coverage_mapping"]) == {str(i) for i in range(1, 27)}, "coverage mapping")
    checked = {}
    for path, expected in review["source_hashes"].items():
        actual_path = historical if path == "test_results/phase11f5_cpl3_proof/design.md" else ROOT / path
        actual = sha(actual_path)
        need(actual == expected, "reviewed input changed: " + path)
        checked[path] = {"expected": expected, "actual": actual,
                         "current_read_path": actual_path.relative_to(ROOT).as_posix()}
    authority = {p: v["expected"] for p, v in load(BASE / "continuation_verification_03.json")["unchanged_review01_inputs"].items()}
    need(len(authority) == 23 and all(review["source_hashes"].get(p) == h for p, h in authority.items()), "23 pin membership")
    for finding in review["findings"]:
        need(finding.get("assessment") and finding.get("source_refs"), "ungrounded finding")
        for reference in finding["source_refs"]:
            if reference.startswith("https://"):
                continue
            local = ROOT / re.sub(r":[0-9].*$", "", reference)
            need(local.is_file(), "missing reference: " + reference)
    names = re.findall(r"^\d+\. `((?:memory::paging::)?f5_cpl3(?:_owner)?_tests::[^`]+)`$", proposal.read_text(encoding="utf-8"), re.M)
    need(len(names) == len(set(names)) == 14, "closed14 identity manifest")
    need(sum(n.startswith("f5_cpl3_tests::") for n in names) == 10, "pure10")
    need(sum(n.startswith("memory::paging::f5_cpl3_owner_tests::") for n in names) == 4, "owner4")
    current = source_snapshot()
    frozen = load(BASE / "continuation_snapshot_02.json")["source_sha256"]
    need(current == frozen, "canonical187 source membership/byte drift")
    readback = {
        "schema": "rosti.f5.design-review-readback.v1", "overall": "PASS",
        "scope": "Parent validation of complete independent REJECT, not independent approval",
        "review_path": review_path.relative_to(ROOT).as_posix(), "review_sha256": sha(review_path),
        "review_verdict": review["verdict"], "blockers": review["blockers"],
        "checklist_count": 26, "source_hashes_checked": checked,
        "historical_design_relocation": {"reviewed_original_path": "test_results/phase11f5_cpl3_proof/design.md",
                                         "preserved_byte_identical_path": historical.relative_to(ROOT).as_posix()},
        "all23_input_membership_verified": True, "all30_reviewed_hashes_match": True,
        "implementation_authorized": False,
    }
    readback_path = BASE / "design_review_02_readback_01.json"
    save(readback_path, readback)
    manifest = {
        "schema": "rosti.f5.design-input-manifest.v1", "proposal": 3,
        "status": "PROPOSED / LAST AUTHORIZED DESIGN REVISION / INDEPENDENT REVIEW REQUIRED",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "design_path": proposal.relative_to(ROOT).as_posix(), "design_raw_sha256": sha(proposal),
        "source_authority_sha256": authority, "source_authority_count": len(authority),
        "canonical_source_sha256": current, "canonical_source_count": len(current),
        "additional_review_inputs_sha256": {
            p: sha(ROOT / p) for p in [
                "test_results/phase11f5_cpl3_proof/design_proposal_01.md",
                "test_results/phase11f5_cpl3_proof/design_proposal_02.md",
                "test_results/phase11f5_cpl3_proof/reviews/design_review_01.json",
                "test_results/phase11f5_cpl3_proof/reviews/design_review_02.json",
                "test_results/phase11f5_cpl3_proof/design_review_02_readback_01.json",
                "test_results/phase11f5_cpl3_proof/continuation_verification_03.json",
                "test_results/phase11f5_cpl3_proof/continuation_verification_04.json",
                "test_results/f4acc/c03/acceptance_20261023T032857Z_we8akw8p/acceptance.json",
                "test_results/phase11f4_user_arena/correction_green_02/closure.json",
            ]},
        "expected_f5_rust_identities": names, "expected_ignored_f5": [],
        "expected_hardware_matrix": [{"scenario": s, "ram_mib": ram} for s in "ABCDEF" for ram in (128, 512)],
        "expected_new_gate_multiset": dict(collections.Counter([
            "Phase 11 F5 CPL3 host and fixture contracts",
            "Phase 11 F5 CPL3 exact ELF terminal closure",
            "Phase 11 F5 CPL3 one-shot hardware matrix",
            "Phase 11 F5 retained prerequisite hardware preservation",
        ])),
        "revision_budget_remaining_after_this_proposal": 0,
        "implementation_authorized": False, "generator_sha256": sha(Path(__file__)),
    }
    output = BASE / "design_inputs_03.json"
    save(output, manifest)
    print(json.dumps({"readback": "PASS", "reviewed_pins": len(checked),
                      "manifest": str(output), "manifest_sha256": sha(output),
                      "design_sha256": sha(proposal), "rust_identities": len(names),
                      "source_count": len(current)}, indent=2))


if __name__ == "__main__":
    main()
