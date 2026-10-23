"""F4 disposable baseline Ring0 RED. No production mutation or CPL3."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from b13_entry_inject import QEMU, elf_symbols
from f1_retained_guest import port, connect
from f2_exception_guest import source_snapshot, sha, require, NAMES
from f3_gdt_guest import LoggedGdb, LoggedQmp
from f3_evidence import hardware

ROOT = Path(__file__).resolve().parents[1]
CALL = b"    // F4_BASELINE_CALL_BEGIN\n    unsafe { f4_baseline_probe(); }\n    // F4_BASELINE_CALL_END\n"
ASM = b'''
// F4_BASELINE_ASM_BEGIN
core::arch::global_asm!(r#"
.section .bss
.balign 8
.global f4_cpuid
f4_cpuid:
 .zero 80
.section .text
.global f4_baseline_probe
f4_baseline_probe:
 cli
 xor %eax,%eax
 cpuid
 mov %eax,f4_cpuid
 mov %ebx,f4_cpuid+4
 mov %ecx,f4_cpuid+8
 mov %edx,f4_cpuid+12
 mov %eax,%esi
 cmp $1,%esi
 jb 2f
 mov $1,%eax
 xor %ecx,%ecx
 cpuid
 mov %eax,f4_cpuid+16
 mov %ebx,f4_cpuid+20
 mov %ecx,f4_cpuid+24
 mov %edx,f4_cpuid+28
2:
 cmp $7,%esi
 jb 3f
 mov $7,%eax
 xor %ecx,%ecx
 cpuid
 mov %eax,f4_cpuid+32
 mov %ebx,f4_cpuid+36
 mov %ecx,f4_cpuid+40
 mov %edx,f4_cpuid+44
3:
 mov $0x80000000,%eax
 cpuid
 mov %eax,f4_cpuid+48
 mov %ebx,f4_cpuid+52
 mov %ecx,f4_cpuid+56
 mov %edx,f4_cpuid+60
 cmp $0x80000001,%eax
 jb 4f
 mov $0x80000001,%eax
 xor %ecx,%ecx
 cpuid
 mov %eax,f4_cpuid+64
 mov %ebx,f4_cpuid+68
 mov %ecx,f4_cpuid+72
 mov %edx,f4_cpuid+76
4:
.global f4_baseline_ready
f4_baseline_ready:
 hlt
 jmp f4_baseline_ready
"#, options(att_syntax));
unsafe extern "C" { fn f4_baseline_probe() -> !; }
// F4_BASELINE_ASM_END
'''


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2)
        f.write("\n")


def capture(kernel, out, ram):
    symbols = elf_symbols(kernel)
    gp, qp = port(), port()
    command = [str(QEMU), "-kernel", str(kernel), "-cpu", "qemu32", "-m", str(ram),
               "-smp", "1", "-machine", "pc", "-display", "none", "-nic", "none",
               "-monitor", "none", "-no-reboot", "-serial", "file:" + str(out / "serial.txt"),
               "-d", "int,guest_errors", "-D", str(out / "qemu.log"), "-S",
               "-gdb", f"tcp:127.0.0.1:{gp}", "-qmp", f"tcp:127.0.0.1:{qp},server=on,wait=off"]
    report = {"command": command, "ram_mib": ram, "capture_complete": False,
              "hardware_cpl3": False, "debugger_mutations": []}
    proc, sockets = None, []
    try:
        with (out / "stderr.txt").open("xb") as err, (out / "gdb.jsonl").open("x") as glog, (out / "qmp.jsonl").open("x") as qlog:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=err)
            report["owned_pid"] = proc.pid
            deadline = time.monotonic() + 90
            gs, qs = connect(gp, proc, deadline), connect(qp, proc, deadline)
            sockets = [gs, qs]
            gs.settimeout(25)
            qs.settimeout(10)
            gdb, qmp = LoggedGdb(gs, glog), LoggedQmp(qs, qlog)
            gdb.deadline = qmp.deadline = deadline
            qmp.deadline_socket = qs
            gdb.command("?")
            address = symbols["f4_baseline_ready"]["address"]
            require(gdb.command(f"Z1,{address:x},1") == "OK", "install checkpoint breakpoint")
            stopped = gdb.command("c")
            require(stopped.startswith(("T05", "S05")), "actual debugger stop")
            packet = gdb.command("g")
            (out / "register_packet.txt").write_text(packet)
            regs = dict(zip(NAMES, struct.unpack_from("<16I", bytes.fromhex(packet))))
            require(regs["eip"] == address and regs["cs"] & 3 == 0, "actual Ring0 checkpoint EIP")
            require(qmp.call("query-status")["running"] is False, "vCPU paused")
            _, text = qmp.hardware()
            (out / "hardware.txt").write_text(text, encoding="ascii")
            cpu = hardware(text.encode("ascii"))
            require(cpu["CR4"] & (1 << 21) == 0, "F4-local SMAP must be off")
            report["cpu"] = cpu
            target = out / "directory.bin"
            qmp.call("pmemsave", val=cpu["CR3"], size=4096, filename=target.as_posix())
            directory = target.read_bytes()
            repeat = out / "directory_repeat.bin"
            qmp.call("pmemsave", val=cpu["CR3"], size=4096, filename=repeat.as_posix())
            require(len(directory) == 4096 and directory == repeat.read_bytes(), "stable physical directory bytes")
            cpuid = gdb.read(symbols["f4_cpuid"]["address"], 80)
            (out / "cpuid.bin").write_bytes(cpuid)
            words = struct.unpack("<20I", cpuid)
            require(words[0] >= 1, "CPUID basic leaf availability")
            require(words[0] >= 7 or words[8:12] == (0, 0, 0, 0), "unsupported leaf7 not fabricated")
            require(words[12] >= 0x80000001 or words[16:20] == (0, 0, 0, 0), "unsupported extended leaf not fabricated")
            require(gdb.command("g") == packet, "CPU did not advance during capture")
            require(gdb.command(f"z1,{address:x},1") == "OK", "remove checkpoint breakpoint")
            pde = struct.unpack_from("<I", directory, 256 * 4)[0]
            report.update(capture_complete=True, checkpoint_eip=address,
                          pde256=pde, cpuid_words=list(words), physical_cr3=cpu["CR3"])
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        if proc is not None:
            report["qemu_exit_before_cleanup"] = proc.poll()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            report.update(qemu_exit=proc.returncode, owned_qemu_exited=proc.poll() is not None)
        for sock in sockets:
            sock.close()
        save(out / "guest_report.json", report)
    return report


def main():
    if sys.flags.optimize:
        raise SystemExit("optimized evidence execution refused")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ram", type=int, choices=(128, 512), default=128)
    args = parser.parse_args()
    require(args.output_dir.is_absolute(), "absolute output required")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "rosti.f4-runtime-red.v1", "overall": "HARNESS_FAIL",
              "driver_exit": 2, "build_exit": None, "hardware_cpl3": False}
    before = source_snapshot()
    save(out / "source_before.json", before)
    try:
        reviewpath = ROOT / "test_results/phase11f4_user_arena/reviews/design_review_02.json"
        review = json.loads(reviewpath.read_bytes())
        require(review["verdict"] == "APPROVE" and review["blocker_count"] == 0, "no design approval")
        require(all(sha((ROOT / p).read_bytes()) == h for p, h in review["raw_sha256"].items()), "design/source pin drift")
        report["design_review_sha256"] = sha(reviewpath.read_bytes())
        report["design_sha256"] = review["design_raw_sha256"]
        # Native Windows path-length precaution; no accepted output is touched.
        with tempfile.TemporaryDirectory(prefix="f4_", dir=ROOT / "dist") as tmp:
            stage = Path(tmp).resolve()
            source = stage / "s"
            source.mkdir()
            report["owned_stage"] = str(stage)
            for name, digest in before.items():
                if name.startswith(("src/", "crates/", "system/")) or name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "target.json", "linker.ld", ".cargo/config.toml"):
                    raw = (ROOT / name).read_bytes()
                    require(sha(raw) == digest, "source copy drift " + name)
                    dest = source / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(raw)
            path = source / "src/main.rs"
            original = path.read_bytes()
            anchor = b"    // stub: enable ps2 & interrupts"
            require(original.count(anchor) == 1, "unique postpaging anchor")
            changed = original.replace(anchor, CALL + anchor) + ASM
            require(changed.replace(CALL, b"", 1).replace(ASM, b"", 1) == original, "fixture stripping equality")
            path.write_bytes(changed)
            (out / "fixture_call.rs").write_bytes(CALL)
            (out / "fixture_assembly.rs").write_bytes(ASM)
            report.update(original_main_sha256=sha(original), injected_main_sha256=sha(changed), stripping_equality=True)
            command = ["cargo", "+nightly", "build", "--locked", "--manifest-path", str(source / "Cargo.toml"), "--target-dir", str(stage / "b")]
            report.update(build_command=command, build_cwd=str(source))
            with (out / "build.log").open("xb") as log:
                result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            report["build_exit"] = result.returncode
            require(result.returncode == 0, "build failure is NOT runtime RED")
            kernel = out / "kernel.elf"
            shutil.copyfile(stage / "b/target/debug/kernel", kernel)
            report["kernel_sha256"] = sha(kernel.read_bytes())
            guest = capture(kernel, out, args.ram)
            report["guest"] = guest
            require(guest["capture_complete"] and guest["owned_qemu_exited"], "incomplete actual CPU capture or cleanup")
            require(guest["pde256"] == 0, "baseline differs; characterize instead of manufacturing RED")
            report.update(overall="RUNTIME_RED", driver_exit=1,
                          assertion_failure={"name": "actual_owned_USER_arena_PDE_present_user", "expected_mask": 5,
                                             "actual_pde256": guest["pde256"], "actual_masked": guest["pde256"] & 5})
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        after = source_snapshot()
        save(out / "source_after.json", after)
        report.update(source_freeze_stable=before == after, source_input_count=len(before),
                      driver_source_sha256=sha(Path(__file__).read_bytes()))
        if before != after:
            report.update(overall="HARNESS_FAIL", driver_exit=2, error="source changed during baseline")
        report["frozen_bytes"] = {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()}
        save(out / "report.json", report)
        print(json.dumps({k: report.get(k) for k in ("overall", "driver_exit", "build_exit", "source_freeze_stable", "assertion_failure", "error")}, indent=2))
    return report["driver_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
