"""B13-owned separate GRUB staging + production paging smoke, no canonical ISO writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import uuid

from b13_entry_inject import run_injected

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path):
    path = path.resolve()
    return "/mnt/" + path.drive[0].lower() + path.as_posix().split(":", 1)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    kernel = ROOT / "target/target/debug/kernel"
    canonical = ROOT / "dist/rosti.iso"
    stage = ROOT / "dist" / ("b13_grub_stage_" + uuid.uuid4().hex[:10])
    iso = stage.with_suffix(".iso")
    report = {"status": "FAIL", "kernel": str(kernel), "iso": str(iso),
              "canonical_iso_before": sha(canonical) if canonical.exists() else None}
    try:
        report["kernel_sha256"] = sha(kernel)
        (stage / "boot/grub").mkdir(parents=True, exist_ok=False)
        (stage / "boot/rosti.bin").write_bytes(kernel.read_bytes())
        (stage / "boot/grub/grub.cfg").write_text(
            'set timeout=0\nset default=0\nmenuentry "B13 production smoke" {\n    multiboot /boot/rosti.bin\n}\n')
        cmd = ["wsl", "bash", "-c", "grub-mkrescue -o " + shlex.quote(wsl_path(iso)) + " " + shlex.quote(wsl_path(stage))]
        build = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        (output / "iso_build.log").write_text(build.stdout + build.stderr)
        if build.returncode or not iso.exists():
            raise RuntimeError(f"grub-mkrescue exit {build.returncode}")
        report["iso_sha256"] = sha(iso)
        rows = []
        for ram in (128, 512):
            def observe(gdb, before):
                header = gdb.read(before["ebx"], 116)
                flags = struct.unpack_from("<I", header)[0]
                length, address = struct.unpack_from("<II", header, 44)
                gdb.mutations.append({"observed_bootinfo": {"address": before["ebx"],
                    "flags": flags, "flags_hex": hex(flags), "mmap_address": address,
                    "mmap_length": length, "header_hex": header.hex()}})
            rows.append(run_injected(kernel, output / f"grub_entry_{ram}", observe,
                memory=ram, boot_iso=iso, timeout=30,
                serial_markers=("ROSTI: entered kernel_main", "ROSTI: paging enabled (CR0.PG, identity map)",
                                "ROSTI: boot complete", "rosti>")))
        report["entry_observations"] = rows
        paging = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/paging_test.py"),
                                 "--iso", str(iso), "--output-dir", str(output / "paging")],
                                cwd=ROOT, capture_output=True, text=True, timeout=90)
        (output / "paging.log").write_text(paging.stdout + paging.stderr)
        paths = list((output / "paging").glob("*/report.json"))
        if paging.returncode or len(paths) != 1:
            raise AssertionError(f"Paging exit {paging.returncode}, reports {len(paths)}")
        actual = json.loads(paths[0].read_text())
        if actual.get("overall") != "PASS" or len(actual.get("results", [])) != 2:
            raise AssertionError("Incomplete paging matrix")
        for row in actual["results"]:
            if not row.get("checks") or not all(row["checks"].values()):
                raise AssertionError("Failed paging checks")
        report["paging_report"] = str(paths[0])
        report["kernel_unchanged"] = sha(kernel) == report["kernel_sha256"]
        report["canonical_iso_after"] = sha(canonical) if canonical.exists() else None
        if not report["kernel_unchanged"] or report["canonical_iso_before"] != report["canonical_iso_after"]:
            raise AssertionError("Production ELF/canonical ISO changed during smoke")
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "evidence": str(output / "report.json"),
                      "error": report.get("error")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
