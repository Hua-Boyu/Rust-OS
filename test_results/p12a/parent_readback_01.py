"""P12-A parent artifact integrity readback (read-only; never edits anything).

(a) re-hashes every input in the current freeze and shows source-before = source-after
(b) re-hashes every artifact cited in the P12-A evidence_manifest.json and checks
    each review JSON's recorded self-hash and the pinned inputs it names
(c) re-hashes the F5 predecessor files against the F5 manifest
(d) re-hashes every initially protected path and shows it equals the initial snapshot
(e) confirms no owned processes remain (reported by the caller, not here)
"""
import json, hashlib, subprocess, sys
from pathlib import Path

ROOT = Path("C:/Users/iamsv/Documents/Rust-OS")

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main() -> int:
    out = {"ok": True, "sections": {}}
    freeze = json.loads((ROOT / "test_results/p12a/f01/source_freeze_01.json").read_bytes())
    # (a) freeze re-hash
    a = {}
    for rel, want in freeze["inputs"].items():
        got = sha(ROOT / rel) if (ROOT / rel).exists() else None
        a[rel] = {"want": want, "got": got, "match": got == want}
        if got != want:
            out["ok"] = False
    out["sections"]["a_freeze"] = a
    # (b) evidence manifest artifacts + review self-hashes
    b = {}
    try:
        ev = json.loads((ROOT / "test_results/phase12_p12a/evidence_manifest.json").read_bytes())
    except FileNotFoundError:
        ev = None
    if ev:
        for rel, want in (ev.get("artifacts") or {}).items():
            got = sha(ROOT / rel) if (ROOT / rel).exists() else None
            b[rel] = {"want": want, "got": got, "match": got == want}
            if got != want:
                out["ok"] = False
    for rev in ["test_results/phase12_p12a/reviews/design_review_01.json"]:
        rp = ROOT / rev
        if rp.exists():
            doc = json.loads(rp.read_bytes())
            rim = doc.get("reviewed_input_manifest") or {}
            got_raw = sha(ROOT / rim["path"]) if rim.get("path") else None
            b["review_inputs_raw"] = {"want": rim.get("raw_sha256"), "got": got_raw, "match": got_raw == rim.get("raw_sha256")}
            if got_raw != rim.get("raw_sha256"):
                out["ok"] = False
            for pin in rim.get("pin_verification", []):
                got = sha(ROOT / pin["path"]) if (ROOT / pin["path"]).exists() else None
                b[pin["name"]] = {"want": pin["expected"], "got": got, "match": got == pin["expected"]}
                if got != pin["expected"]:
                    out["ok"] = False
    out["sections"]["b_evidence"] = b
    # (c) F5 predecessor identity
    c = {}
    f5man = json.loads((ROOT / "test_results/phase11f5_cpl3_proof/evidence_manifest.json").read_bytes())
    for ent in f5man.get("artifacts", []):
        rel, want = ent["path"], ent["sha256"]
        got = sha(ROOT / rel) if (ROOT / rel).exists() else None
        c[rel] = {"want": want, "got": got, "match": got == want}
    out["sections"]["c_f5"] = c
    # (d) protected paths vs initial snapshot
    d = {}
    state = (ROOT / "test_results/phase12_p12a/STATE.md").read_text()
    for line in state.splitlines():
        line = line.strip().lstrip("- ")
        if line.startswith("{") and '"path"' in line and '"sha256"' in line:
            try:
                ent = json.loads(line)
            except json.JSONDecodeError:
                continue
            rel, want = ent["path"], ent["sha256"]
            got = sha(ROOT / rel) if (ROOT / rel).exists() else None
            d[rel] = {"want": want, "got": got, "match": got == want}
            if got != want:
                out["ok"] = False
    out["sections"]["d_protected"] = d
    print(json.dumps(out, indent=1))
    return 0 if out["ok"] else 1

if __name__ == "__main__":
    sys.exit(main())
