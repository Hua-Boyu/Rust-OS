#!/usr/bin/env python3
"""Verify production-only Cargo resolution and absence of deliberate fault text."""
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent.parent


def main():
    result = subprocess.run(["cargo", "metadata", "--format-version", "1"],
                            cwd=PROJECT, capture_output=True, text=True, check=True)
    metadata = json.loads(result.stdout)
    names = {p["id"]: p["name"] for p in metadata["packages"]}
    features = {names[n["id"]]: n["features"] for n in metadata["resolve"]["nodes"]
                if names[n["id"]] in ("kernel", "rostifs")}
    forbidden = {"paging-fault-test", "paging-write-fault-test", "fault-injection", "host-tools"}
    checks = [
        (set(features) == {"kernel", "rostifs"}, "kernel and portable storage resolved"),
        (not any(forbidden.intersection(f) for f in features.values()), "no production fault or host-tool features"),
        (b"ROSTI: fault test trigger" not in (PROJECT / "target/target/debug/kernel").read_bytes(),
         "deliberate fatal-fault marker absent from ELF"),
    ]
    print(json.dumps({"features": features, "checks": [{"name": n, "pass": p} for p, n in checks]}, indent=2))
    return 0 if all(p for p, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
