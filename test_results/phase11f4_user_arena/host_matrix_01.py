"""Run/validate exact F4 host+B26 membership outside bare-metal Cargo config.

Unique output required. Raw source snapshot before/after; no acceptance claim.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

if sys.flags.optimize:
    raise SystemExit("optimized verification refused")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from f2_exception_guest import source_snapshot

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(exist_ok=False)
CWD = Path("C:/Users/iamsv")

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def declarations(path, module):
    names = re.findall(r"#\[test\]\s*fn\s+([a-zA-Z0-9_]+)\s*\(", path.read_text())
    need(len(names) == len(set(names)), "duplicate test declarations")
    return [module + "::" + name for name in names]

host_extra = declarations(ROOT / "src/memory/f4_user_arena_tests.rs", "memory::paging::f4_user_arena_tests")
b26_extra = declarations(ROOT / "src/memory/f4_b26_tests.rs", "memory::paging::f4_b26_tests")
section = (ROOT / "test_results/phase11f4_user_arena/design.md").read_text().split("Twelve planned exact test names", 1)[1].split("Tests must", 1)[0]
reviewed = ["memory::paging::f4_user_arena_tests::" + n for n in re.findall(r"^- ([a-z0-9_]+)$", section, re.M)]
need(len(reviewed) == 12 and Counter(host_extra) == Counter(reviewed), "reviewed twelve identities mismatch")
need(len(b26_extra) == 3, "three B26 declarations required")
report = {"scope": "F4 component regressions; NOT canonical acceptance", "overall": "RUNNING", "records": [],
          "recorder_sha256": sha(Path(__file__)), "source_before": source_snapshot(), "checks": []}
try:
    for family, extras in [("host", host_extra), ("b26", host_extra + b26_extra)]:
        baseline_path = ROOT / "test_results/phase11f4_user_arena" / ("baseline_" + family + "_01/report.json")
        baseline = json.loads(baseline_path.read_bytes())
        baseline_list = next(r for r in baseline["records"] if r["name"] == "list")["listed"]
        baseline_ignored = next(r for r in baseline["records"] if r["name"] == "serial")["ignored"]
        expected = Counter(baseline_list + extras)
        need(all(n == 1 for n in expected.values()), family + " duplicate baseline/new identity")
        manifest = ROOT / ("tests_kernel" if family == "host" else "tests_b26") / "Cargo.toml"
        rows = []
        for mode, tail in [("list", ["--list"]), ("serial", ["--test-threads=1"]), ("parallel", [])]:
            argv = ["cargo", "+nightly", "test", "--manifest-path", str(manifest), "--target", "x86_64-pc-windows-msvc", "--lib", "--"] + tail
            log = OUT / (family + "_" + mode + ".log")
            with log.open("xb") as f:
                process = subprocess.run(argv, cwd=CWD, stdout=f, stderr=subprocess.STDOUT)
            text = log.read_text(encoding="utf-8", errors="replace")
            row = {"family": family, "mode": mode, "argv": argv, "cwd": str(CWD), "exit_code": process.returncode,
                   "log": str(log), "log_sha256": sha(log), "baseline": str(baseline_path), "baseline_sha256": sha(baseline_path),
                   "listed": re.findall(r"^([^\r\n]+): test$", text, re.M),
                   "passed": re.findall(r"^test (\S+) \.\.\. ok$", text, re.M),
                   "ignored": re.findall(r"^test (\S+) \.\.\. ignored(?:,.*)?$", text, re.M),
                   "summaries": re.findall(r"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", text)}
            report["records"].append(row)
            rows.append(row)
            need(process.returncode == 0, family + " " + mode + " process exit")
            if mode == "list":
                need(Counter(row["listed"]) == expected, family + " exact baseline+F4 listing")
            else:
                need(len(row["summaries"]) == 1, family + " one libtest summary")
                passed, failed, ignored = map(int, row["summaries"][0])
                need(passed > 0 and failed == 0 and passed == len(row["passed"]) and ignored == len(row["ignored"]), family + " nonzero matching summary")
                need(Counter(row["passed"] + row["ignored"]) == expected, family + " exact executed identities")
                need(Counter(row["ignored"]) == Counter(baseline_ignored), family + " inherited ignored membership")
            print(json.dumps({"family": family, "mode": mode, "exit": process.returncode, "listed": len(row["listed"]), "summary": row["summaries"]}), flush=True)
        report["checks"].append({"name": family + " baseline preserved and additions exact; serial/parallel/list", "pass": True})
    report["source_after"] = source_snapshot()
    report["source_drift"] = {p: [report["source_before"].get(p), report["source_after"].get(p)] for p in sorted(report["source_before"].keys() | report["source_after"].keys()) if report["source_before"].get(p) != report["source_after"].get(p)}
    need(not report["source_drift"], "source changed during regressions")
    report["overall"] = "PASS"
except Exception as exc:
    report.update(overall="FAIL", error=repr(exc))
finally:
    with (OUT / "report.json").open("x", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps({"overall": report["overall"], "error": report.get("error"), "report": str(OUT / "report.json")}), flush=True)
raise SystemExit(0 if report["overall"] == "PASS" else 1)
