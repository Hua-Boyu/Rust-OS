"""Refresh only the task evidence manifest, preserving its preceding bytes.
No build/test/hardware action and no independent-approval inference.
"""
import datetime
import hashlib
import json
from pathlib import Path
import sys

if sys.flags.optimize:
    raise RuntimeError("optimized verification refused")
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 3:
        raise RuntimeError("usage: refresh_manifest_04.py UNIQUE_NUMBER STATUS")
    number, status = sys.argv[1:]
    if not number.isdecimal():
        raise RuntimeError("number required")
    target = BASE / "evidence_manifest.json"
    old = target.read_bytes()
    archive = BASE / ("evidence_manifest_prior_" + number + ".json")
    with archive.open("xb") as stream:
        stream.write(old)
    active_reviews = []
    historical_reviews = []
    for path in sorted((BASE / "reviews").glob("*.json")):
        data = json.loads(path.read_bytes())
        if data.get("complete_scope") is True or path.name == "prerequisite_review_01.json":
            historical_reviews.append(path)
        else:
            active_reviews.append(path.relative_to(ROOT).as_posix())
    artifacts = []
    excluded = {target, *[ROOT / p for p in active_reviews]}
    for path in sorted(BASE.rglob("*")):
        if not path.is_file() or path in excluded or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        historical = path.name.startswith(("design_proposal_", "design_preflight_", "continuation_", "recovery_", "evidence_manifest_prior_")) or path in historical_reviews
        role = "independent review" if path in historical_reviews else (
            "design input manifest" if path.name.startswith("design_inputs_") else (
                "current design proposal" if path.name == "design.md" else (
                    "status/report" if path.name in ("STATE.md", "decisions.md", "FINAL_REPORT.md") else "task evidence or verifier")))
        artifacts.append({"path": rel, "sha256": sha(path), "role": role,
                          "phase": "F5 design recovery and review",
                          "immutable_historical": historical})
    manifest = {
        "schema": "rosti.f5.partial-manifest.v1", "status": status,
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "artifacts": artifacts, "artifact_count": len(artifacts),
        "in_progress_reviews_excluded": active_reviews,
        "previous_manifest": {"path": archive.relative_to(ROOT).as_posix(), "sha256": sha(archive)},
        "design_inputs": {"path": "test_results/phase11f5_cpl3_proof/design_inputs_03.json", "sha256": sha(BASE / "design_inputs_03.json")},
        "f5_tests_executed": False, "f5_implemented": False,
        "canonical_acceptance_executed": False,
        "note": "Artifact presence or complete review does not imply approval. No self-referential manifest hash.",
    }
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"manifest": str(target), "sha256": sha(target),
                      "artifact_count": len(artifacts), "status": status,
                      "in_progress_reviews_excluded": active_reviews}, indent=2))


if __name__ == "__main__":
    main()
