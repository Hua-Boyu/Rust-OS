"""F4 minimal ready oracle, Ring0 only; NOT the full acceptance matrix."""
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
from f4_user_guest import ASM as BASELINE_ASM, save

ROOT = Path(__file__).resolve().parents[1]
CALL = b"    // F4_READY_CALL_BEGIN\n    unsafe { f4_baseline_probe(); }\n    // F4_READY_CALL_END\n"
END = b"4:\n.global f4_baseline_ready\nf4_baseline_ready:\n hlt\n jmp f4_baseline_ready\n"
require(BASELINE_ASM.count(END) == 1, "baseline CPUID probe tail")
ASM = BASELINE_ASM.replace(END, b"4:\n jmp f4_run_user_arena\n")


def guest(kernel, out, ram):
    out.mkdir()
    symbols = elf_symbols(kernel)
    gp, qp = port(), port()
    command = [str(QEMU), "-kernel", str(kernel), "-cpu", "qemu32", "-m", str(ram),
               "-smp", "1", "-machine", "pc", "-display", "none", "-nic", "none",
               "-monitor", "none", "-no-reboot", "-serial", "file:" + str(out / "serial.txt"),
               "-d", "int,guest_errors", "-D", str(out / "qemu.log"), "-S",
               "-gdb", f"tcp:127.0.0.1:{gp}", "-qmp", f"tcp:127.0.0.1:{qp},server=on,wait=off"]
    row = {"scenario": "ready", "ram_mib": ram, "command": command, "overall": "FAIL",
           "capture_complete": False, "hardware_cpl3": False, "debugger_mutations": [], "checks": []}
    proc, sockets = None, []
    try:
        with (out / "stderr.txt").open("xb") as err, (out / "gdb.jsonl").open("x") as glog, (out / "qmp.jsonl").open("x") as qlog:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=err)
            row["owned_pid"] = proc.pid
            deadline = time.monotonic() + 120
            gs, qs = connect(gp, proc, deadline), connect(qp, proc, deadline)
            sockets = [gs, qs]
            gs.settimeout(25)
            qs.settimeout(10)
            gdb, qmp = LoggedGdb(gs, glog), LoggedQmp(qs, qlog)
            gdb.deadline = qmp.deadline = deadline
            qmp.deadline_socket = qs
            gdb.command("?")

            def stop(symbol, label):
                address = symbols[symbol]["address"]
                require(gdb.command(f"Z1,{address:x},1") == "OK", "install " + symbol)
                reply = gdb.command("c")
                require(reply.startswith(("T05", "S05")), "actual debugger stop")
                packet = gdb.command("g")
                (out / (label + "_register_packet.txt")).write_text(packet)
                regs = dict(zip(NAMES, struct.unpack_from("<16I", bytes.fromhex(packet))))
                require(regs["eip"] == address and regs["cs"] & 3 == 0, "Ring0 stopped EIP")
                require(qmp.call("query-status")["running"] is False, "paused")
                require(gdb.command(f"z1,{address:x},1") == "OK", "remove breakpoint")
                return packet

            def physical(name, address, length):
                require(address >= 4096 and address + length <= ram * 1024 * 1024, "RAM bound")
                path = out / name
                qmp.call("pmemsave", val=address, size=length, filename=path.as_posix())
                raw = path.read_bytes()
                require(len(raw) == length, "physical capture length")
                return raw

            def memory(name, address, length):
                raw = b"".join(gdb.read(address + i, min(512, length - i)) for i in range(0, length, 512))
                (out / name).write_bytes(raw)
                return raw

            def snapshot(label):
                _, text = qmp.hardware()
                (out / (label + "_hardware.txt")).write_text(text, encoding="ascii")
                cpu = hardware(text.encode("ascii"))
                require(cpu["CR4"] & (1 << 21) == 0, "F4-local SMAP0")
                directory = physical(label + "_directory.bin", cpu["CR3"], 4096)
                repeat = physical(label + "_directory_repeat.bin", cpu["CR3"], 4096)
                require(directory == repeat, "stable directory capture")
                tables = {}
                for i, pde in enumerate(struct.unpack("<1024I", directory)):
                    if pde & 1:
                        require(pde & 0x80 == 0, "no large pages")
                        pa = pde & 0xfffff000
                        require(pa not in tables, "no duplicate table structure")
                        tables[pa] = physical(f"{label}_table_{i:03d}.bin", pa, 4096)
                owners = []
                for ordinal, (name, sym) in enumerate(sorted(symbols.items())):
                    if "retained_owner" in name and ("OWNER" in name or "STATE" in name):
                        require(0 < sym["size"] <= 4096, "owner bound")
                        filename = f"{label}_owner_{ordinal}.bin"
                        memory(filename, sym["address"], sym["size"])
                        owners.append({"symbol": name, **sym, "file": filename})
                require(len(owners) == 2, "exact owner/latch capture")
                save(out / (label + "_owner_symbols.json"), owners)
                return cpu, directory, tables

            pre_packet = stop("f4_prepublication", "pre")
            pre_cpu, pre_directory, pre_tables = snapshot("pre")
            require(struct.unpack_from("<I", pre_directory, 1024)[0] == 0, "PDE absent before commit")
            require(gdb.command("g") == pre_packet, "stable pre CPU")
            ready_packet = stop("f4_arena_terminal", "ready")
            cpu, directory, tables = snapshot("ready")
            require(cpu["CR3"] == pre_cpu["CR3"] and cpu["TR"] == 24, "same CR3/F3 TR")
            require(cpu["GDT"][1] == 39, "unchanged F3 GDT layout")
            entries = struct.unpack("<1024I", directory)
            pde = entries[256]
            require(pde & 0x87 == 7 and entries[257] == 0, "actual USER PDE and upper boundary")
            table = tables[pde & 0xfffff000]
            leaves = struct.unpack("<1024I", table)
            require(leaves[0] & 0x207 == 0x205 and leaves[1023] & 0x207 == 0x207, "codeRO/stackRW USER leaves")
            require(all(v == 0 for v in leaves[1:1023]), "guard and holes absent")
            code, stack = leaves[0] & 0xfffff000, leaves[1023] & 0xfffff000
            require(code != stack and code not in tables and stack not in tables, "distinct nonstructure backing")
            user_leaves = []
            for i, dp in enumerate(entries):
                if not dp & 1:
                    require(dp == 0, "absent directory exact zero")
                    continue
                if i != 256:
                    require(dp & 4 == 0, "supervisor PDE not promoted")
                    require(all(v & 4 == 0 for v in struct.unpack("<1024I", tables[dp & 0xfffff000])), "no kernel USER leaves")
                else:
                    user_leaves = [j for j, p in enumerate(leaves) if p & 5 == 5]
            require(user_leaves == [0, 1023], "exact effective USER inventory")
            for frame in (code, stack, pde & 0xfffff000):
                dp = entries[frame >> 22]
                lp = struct.unpack_from("<I", tables[dp & 0xfffff000], ((frame >> 12) & 1023) * 4)[0]
                require(dp & 7 == 3 and lp & 7 == 3 and lp & 0xfffff000 == frame, "supervisor RW identity alias")
            payload = physical("payload.bin", code, 4096)
            stack_raw = physical("stack.bin", stack, 4096)
            require(payload[:4] == bytes([15, 11, 235, 252]) and payload[2048:2059] == b"F4-RO-DATA\0", "actual owned payload pattern")
            require(stack_raw == bytes(4096), "owned stack initialized")
            for i, old in enumerate(struct.unpack("<1024I", pre_directory)):
                if i != 256:
                    require((entries[i] & ~0x20) == (old & ~0x20), "supervisor PDE preservation")
            for pa, old in pre_tables.items():
                require(pa in tables, "predecessor table retained")
                require(all((x & ~0x60) == (y & ~0x60) for x, y in zip(struct.unpack("<1024I", old), struct.unpack("<1024I", tables[pa]))), "supervisor PTE bytes preserved modulo AD")
            cpuid = memory("cpuid.bin", symbols["f4_cpuid"]["address"], 80)
            words = struct.unpack("<20I", cpuid)
            require(words[0] >= 1 and (words[0] >= 7 or words[8:12] == (0, 0, 0, 0)), "bounded CPUID leaves")
            require(words[12] >= 0x80000001 or words[16:] == (0, 0, 0, 0), "bounded extended CPUID")
            require(gdb.command("g") == ready_packet, "stable ready CPU")
            serial = (out / "serial.txt").read_bytes()
            require(b"F4 USER arena PASS Ring0 terminal\n" in serial and b"F4 USER arena FAIL" not in serial, "production terminal outcome")
            row.update(overall="PASS", capture_complete=True, cpu=cpu, pde256=pde, code_frame=code,
                       stack_frame=stack, table_frame=pde & 0xfffff000, cpuid_words=list(words),
                       checks=[{"name": n, "pass": True} for n in ("owned_USER_PDE_present_user", "unpublished_before_commit", "effective_leaf_permissions", "guards_absent", "supervisor_preservation", "physical_backing", "initialized_payload", "SMAP0_CPL0_CR3", "F3_descriptors", "production_terminal")])
    except Exception as exc:
        row["error"] = repr(exc)
    finally:
        if proc is not None:
            row["qemu_exit_before_cleanup"] = proc.poll()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            row.update(qemu_exit=proc.returncode, owned_qemu_exited=proc.poll() is not None)
        for sock in sockets:
            sock.close()
        row["frozen_bytes"] = {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()}
        save(out / "guest_report.json", row)
    return row


def main():
    if sys.flags.optimize:
        raise SystemExit("optimized evidence execution refused")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    require(args.output_dir.is_absolute(), "absolute output required")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"overall": "HARNESS_FAIL", "driver_exit": 2, "full_f4_acceptance": False,
              "hardware_cpl3": False, "guests": []}
    before = source_snapshot()
    save(out / "source_before.json", before)
    try:
        rp = ROOT / "test_results/phase11f4_user_arena/reviews/design_review_02.json"
        review = json.loads(rp.read_bytes())
        require(review["verdict"] == "APPROVE" and review["blocker_count"] == 0, "design approval")
        require(sha((ROOT / review["design_path"]).read_bytes()) == review["design_raw_sha256"], "approved design drift")
        report.update(design_review_sha256=sha(rp.read_bytes()), design_sha256=review["design_raw_sha256"])
        with tempfile.TemporaryDirectory(prefix="f4_", dir=ROOT / "dist") as tmp:
            stage = Path(tmp).resolve()
            source = stage / "s"
            source.mkdir()
            report["owned_stage"] = str(stage)
            for name, digest in before.items():
                if name.startswith(("src/", "crates/", "system/")) or name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "target.json", "linker.ld", ".cargo/config.toml"):
                    raw = (ROOT / name).read_bytes()
                    require(sha(raw) == digest, "copy drift " + name)
                    target = source / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
            path = source / "src/main.rs"
            original = path.read_bytes()
            anchor = b"    // stub: enable ps2 & interrupts"
            require(original.count(anchor) == 1, "unique anchor")
            changed = original.replace(anchor, CALL + anchor) + ASM
            require(changed.replace(CALL, b"", 1).replace(ASM, b"", 1) == original, "stripping equality")
            path.write_bytes(changed)
            (out / "fixture_call.rs").write_bytes(CALL)
            (out / "fixture_assembly.rs").write_bytes(ASM)
            report.update(stripping_equality=True, original_main_sha256=sha(original), injected_main_sha256=sha(changed))
            command = ["cargo", "+nightly", "build", "--locked", "--manifest-path", str(source / "Cargo.toml"), "--target-dir", str(stage / "b")]
            report.update(build_command=command, build_cwd=str(source))
            with (out / "build.log").open("xb") as log:
                result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            report["build_exit"] = result.returncode
            require(result.returncode == 0, "build failed")
            kernel = out / "kernel.elf"
            shutil.copyfile(stage / "b/target/debug/kernel", kernel)
            report["kernel_sha256"] = sha(kernel.read_bytes())
            for ram in (128, 512):
                row = guest(kernel, out / f"ready_{ram}", ram)
                report["guests"].append(row)
                require(row["overall"] == "PASS" and row["owned_qemu_exited"], "ready guest failed")
        report.update(overall="MINIMAL_RING0_GREEN", driver_exit=0)
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        after = source_snapshot()
        save(out / "source_after.json", after)
        report.update(source_freeze_stable=before == after, driver_source_sha256=sha(Path(__file__).read_bytes()))
        if before != after:
            report.update(overall="HARNESS_FAIL", driver_exit=2, error="source drift")
        report["frozen_bytes"] = {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()}
        save(out / "report.json", report)
        print(json.dumps({"overall": report["overall"], "build_exit": report.get("build_exit"), "driver_exit": report["driver_exit"], "guests": [{k: r.get(k) for k in ("ram_mib", "overall", "pde256", "error")} for r in report["guests"]], "error": report.get("error")}))
    return report["driver_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
