"""Read-only proposal03 review admission, preserving a fresh parent readback.
Structural/hash checks complement (never replace) independent substantive review.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

if sys.flags.optimize:
    raise RuntimeError("optimized review validation refused")
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from phase6_verify import source_snapshot


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise RuntimeError("duplicate JSON key: " + key)
            data[key] = value
        return data
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def main():
    if len(sys.argv) != 3:
        raise RuntimeError("usage: validate_design_review_03.py REVIEW.json NEW_READBACK.json")
    review_path, output = (Path(p).resolve() for p in sys.argv[1:])
    need(review_path.parent == BASE / "reviews", "task-local review required")
    need(output.parent == BASE and not output.exists(), "new task-local readback required")
    manifest_path = BASE / "design_inputs_03.json"
    need(sha(manifest_path) == "adea88bcf78b78ebe182c79c82563d88707de3075435c24a675e1ab22f69d42f", "manifest drift")
    manifest = load(manifest_path)
    review = load(review_path)
    raw_review_hash = sha(review_path)
    need(review.get("schema") == "rosti.f5-complete-design-review.v1", "review schema")
    need(review.get("verdict") in {"APPROVE", "REJECT"} and review.get("complete_scope") is True, "review not a complete final verdict")
    provenance = review.get("reviewer", {})
    need(provenance.get("execution_context") == "sa-0-f6844592" and provenance.get("delegation_id") == "deleg_cc26d882", "reviewer execution provenance")
    need(provenance.get("independence") and provenance.get("authority"), "review independence/authority missing")
    need(review.get("design_raw_sha256") == manifest["design_raw_sha256"], "wrong design pin")
    need(sha(ROOT / manifest["design_path"]) == manifest["design_raw_sha256"], "current design drift")
    findings = review.get("findings", [])
    need(len(findings) == 26 and {f.get("checklist_point") for f in findings} == set(range(1, 27)), "26 exact findings missing/duplicated")
    for finding in findings:
        need(finding.get("assessment") and finding.get("source_refs") and finding.get("status"), "incomplete grounded finding")
        for ref in finding["source_refs"]:
            if ref.startswith("https://"):
                continue
            path_text, separator, suffix = ref.partition(":")
            local = ROOT / path_text
            need(local.is_file(), "missing referenced artifact: " + ref)
            if separator and suffix and not suffix[0].isdigit():
                need(local.suffix == ".json" and suffix in load(local),
                     "missing referenced JSON field: " + ref)
    required = {**manifest["source_authority_sha256"], **manifest["canonical_source_sha256"],
                **manifest["additional_review_inputs_sha256"],
                manifest["design_path"]: manifest["design_raw_sha256"]}
    reviewed = review.get("source_hashes", {})
    need(all(reviewed.get(p) == h for p, h in manifest["source_authority_sha256"].items()), "required23 reviewer pins missing/wrong")
    mismatches = {p: {"expected": h, "actual": sha(ROOT / p)} for p, h in required.items() if sha(ROOT / p) != h}
    need(not mismatches, "frozen design/source/authority changed")
    reviewed_mismatches = {p: h for p, h in reviewed.items() if sha(ROOT / p) != h}
    need(not reviewed_mismatches, "reviewed raw source changed")
    current = source_snapshot()
    need(current == manifest["canonical_source_sha256"], "canonical source membership/byte drift")
    blockers = review.get("blockers")
    need(isinstance(blockers, list) and review.get("blocker_count") == len(blockers), "explicit blocker count/list mismatch")
    approve = review["verdict"] == "APPROVE"
    need(not approve or (not blockers and review.get("design_complete") is True
                        and review.get("approved_design_raw_sha256") == manifest["design_raw_sha256"]), "APPROVE inconsistent with blockers/design pin/completeness")
    need(sha(review_path) == raw_review_hash, "review changed during readback")
    record = {
        "schema": "rosti.f5.design-review-readback.v1", "overall": "PASS",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Parent structural/provenance/hash readback; not a substitute for independent findings",
        "review_path": review_path.relative_to(ROOT).as_posix(), "review_sha256": raw_review_hash,
        "verdict": review["verdict"], "blocker_count": len(blockers), "blockers": blockers,
        "reviewer": provenance, "checklist_count": len(findings),
        "design_raw_sha256": manifest["design_raw_sha256"], "manifest_sha256": sha(manifest_path),
        "canonical_input_count": len(current), "reviewed_hash_count": len(reviewed),
        "required_input_count_after_deduplication": len(required),
        "all_required_hashes_and_membership_stable": True,
        "implementation_gate_eligible": approve,
        "remaining_design_revisions": 0,
        "reviewer_findings_require_parent_substantive_inspection": True,
        "reader_sha256": sha(Path(__file__)),
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"readback": "PASS", "verdict": record["verdict"],
                      "blocker_count": len(blockers), "review_sha256": raw_review_hash,
                      "readback_sha256": sha(output), "canonical_input_count": len(current),
                      "implementation_gate_eligible": approve}, indent=2))


if __name__ == "__main__":
    main()
