"""Reproduce one Phase 10 guest scenario standalone for investigation.

Usage: python -B scripts/phase10_repro_one.py CASE BOOT RAM OUTDIR
Runs exactly one matrix row through the same PhaseHarness/exercise path as the
full matrix, with a short timeout so a hang is bounded and observable.
"""
import argparse
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "phase10", Path(__file__).with_name("phase10_initramfs_test.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("boot", choices=("elf", "iso"))
    ap.add_argument("ram", type=int, choices=(128, 512))
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--timeout", type=float, default=180)
    a = ap.parse_args()

    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    kernel = Path(mod.PROJECT) / "target/target/debug/kernel"
    fixture_kernel = Path(mod.PROJECT) / "dist/phase10b_fixture_kernel"
    archive = mod.system_assets()

    args = argparse.Namespace(
        kernel=kernel, fixture_kernel=fixture_kernel,
        iso=None, ram=a.ram, timeout=a.timeout,
        live=None, stress=False)
    row = {"case": a.case, "boot": a.boot, "ram": a.ram}
    import time
    deadline = time.monotonic() + a.timeout
    ok = mod.run_one(args, out, row, archive, None, deadline)
    print("scenario completed:", ok)
    rep = out / row["case"] / "report.json"
    if rep.exists():
        import json
        r = json.load(open(rep))
        print("overall:", r.get("overall"), "error:", r.get("error"))
        print("checks:", sum(c["pass"] for c in r["checks"]), "/", len(r["checks"]))


if __name__ == "__main__":
    main()
