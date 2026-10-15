"""Build/inspect B13's isolated ELF; run guests only with explicit --run-qemu."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from b13_entry_inject import elf_symbols, run_injected

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "target/b13_fixture"
KERNEL = TARGET / "target/debug/b13-boot-fixture"
BUILD = ["cargo", "+nightly", "rustc", "--manifest-path", "scripts/b13_fixture/Cargo.toml",
         "--target-dir", "target/b13_fixture", "--bin", "b13-boot-fixture", "--",
         "--emit=asm,llvm-ir,link", "-C", "link-arg=--entry=b13_handoff",
         "-C", "link-arg=--undefined=b13_abi_probe"]


def inspect():
    paths = list((TARGET / "target/debug/build/b13-boot-fixture").glob("*/out/b13_boot_fixture.s"))
    asm_path = max(paths, key=lambda p: p.stat().st_mtime_ns)
    asm = asm_path.read_text()
    ir_path = asm_path.with_suffix(".ll")
    ir = ir_path.read_text()
    probe = asm.split("b13_abi_probe:", 1)[1].split(".Lfunc_end", 1)[0]
    start = asm.split("_start:", 1)[1].split(".size\t_start", 1)[0]
    symbols = elf_symbols(KERNEL)
    data = KERNEL.read_bytes()
    phoff = struct.unpack_from("<I", data, 28)[0]
    phsize, phcount = struct.unpack_from("<HH", data, 42)
    addr = symbols["_start"]["address"]
    for i in range(phcount):
        typ, off, vaddr, paddr, filesz, memsz, flags, align = struct.unpack_from("<8I", data, phoff+i*phsize)
        if typ == 1 and vaddr <= addr < vaddr+filesz:
            code = data[off+addr-vaddr:off+addr-vaddr+symbols["_start"]["size"]]
            break
    else:
        raise AssertionError("_start not in file-backed LOAD")
    # Independent linked-machine-code inspection, not just source-string matching.
    assert code[:3] == bytes.fromhex("fafcbc"), code.hex()
    top = struct.unpack_from("<I", code, 3)[0]
    assert top == symbols["stack_top"]["address"] and top % 16 == 0
    assert code[7:13] == bytes.fromhex("83ec085350e8"), code.hex()
    call_target = addr + 17 + struct.unpack_from("<i", code, 13)[0]
    assert call_target == symbols["kernel_main"]["address"]
    assert code[17:19] == bytes.fromhex("faf4")
    assert "S128" in ir and 'target triple = "i686-unknown-none"' in ir
    assert "pushl\t%ebx" in probe and "subl\t$16, %esp" in probe and "calll\tb13_sink@PLT" in probe
    return {"status": "PASS", "kernel": str(KERNEL),
            "kernel_sha256": hashlib.sha256(data).hexdigest(),
            "assembly_path": str(asm_path), "assembly_sha256": hashlib.sha256(asm_path.read_bytes()).hexdigest(),
            "llvm_ir_path": str(ir_path), "start_assembly": start,
            "start_machine_hex": code.hex(), "stack_top": top,
            "stack_bytes": top-symbols["stack_bottom"]["address"],
            "abi_probe_assembly": probe,
            "abi_finding": "Current soft-float i686-unknown-none caller pushes EBX (4 bytes) and subtracts 16 before external CALL: only 4-byte stack alignment is enforced despite S128. Bootstrap now deliberately provides stronger 16-byte pre-CALL alignment; raw callee ESP=12 mod16.",
            "pre_call_esp_mod16": (top-8-4-4) % 16,
            "callee_esp_mod16": (top-8-4-4-4) % 16}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--run-qemu", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--production-kernel", type=Path)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "FAIL", "qemu_status": "NOT_RUN"}
    try:
        if args.build:
            result = subprocess.run(BUILD, cwd=ROOT, capture_output=True, text=True)
            (out / "build.log").write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"Isolated build exit {result.returncode}")
        report["inspection"] = inspect()
        rows = []
        if args.run_qemu:
            for ram in (128, 512):
                def fixture_mutation(gdb, before):
                    # Prove reusable physical-memory mutation and readback before entry.
                    case = elf_symbols(KERNEL)["b13_case"]["address"]
                    gdb.write(case, bytes(4))
                    gdb.set_registers(esi=0xB13)
                rows.append(run_injected(KERNEL, out / f"fixture_{ram}", fixture_mutation,
                                         entry="b13_handoff", memory=ram,
                                         debug_bytes=b"P"*16, expected_exit=33))
            if args.production_kernel:
                for ram in (128, 512):
                    def production_mutation(gdb, before):
                        # Multiboot specifies IF=0 but leaves DF unspecified.
                        gdb.set_registers(esp=0x90003,
                                          eflags=(before["eflags"] | 0x400) & ~0x200)
                    rows.append(run_injected(args.production_kernel, out / f"production_{ram}",
                                             production_mutation, memory=ram,
                                             serial_markers=("ROSTI: entered kernel_main",
                                                             "ROSTI: paging enabled (CR0.PG, identity map)",
                                                             "ROSTI: boot complete", "rosti>")))
            report["qemu_status"] = "PASS"
        report["guests"] = rows
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "qemu_status": report["qemu_status"],
                      "evidence": str(out / "report.json"), "error": report.get("error")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
