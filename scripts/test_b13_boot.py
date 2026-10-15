"""B13 source-level handoff regressions; privileged proof is a separate fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
BOOT = ROOT / "src/boot.s"


def handoff(source, incoming_esp=0x90003, flags=0x602):
    """Small fail-closed model, deliberately limited to the bootstrap instruction set."""
    body = source.split("_start:", 1)[1].split("call kernel_main", 1)[0]
    instructions = [line.split("//", 1)[0].strip() for line in body.splitlines()]
    instructions = [line for line in instructions if line]
    regs = {"%eax": 0x2BADB002, "%ebx": 0x12345678, "%esp": incoming_esp}
    stack = {}
    for ins in instructions:
        if ins == "cli":
            flags &= ~0x200
        elif ins == "cld":
            flags &= ~0x400
        elif ins == "mov $stack_top, %esp":
            regs["%esp"] = 0x204000
        elif ins.startswith("sub $") and ins.endswith(", %esp"):
            regs["%esp"] -= int(ins.split("$", 1)[1].split(",", 1)[0], 0)
        elif ins.startswith("push "):
            regs["%esp"] -= 4
            stack[regs["%esp"]] = regs[ins.split()[1]]
        else:
            raise AssertionError(f"Unmodeled boot instruction: {ins}")
    return instructions, regs, flags, stack


class BootHandoff(unittest.TestCase):
    def test_interrupts_disabled_before_stack_setup(self):
        source = BOOT.read_text()
        instructions, _, flags, _ = handoff(source)
        self.assertEqual(instructions[0], "cli", "CLI must precede stack/ABI work")
        self.assertEqual(flags & 0x200, 0)

    def test_direction_flag_cleared_before_rust(self):
        _, _, flags, _ = handoff(BOOT.read_text())
        self.assertEqual(flags & 0x400, 0, "Rust/C ABI requires DF clear")

    def test_pre_call_stack_is_16_byte_aligned(self):
        for residue in range(16):
            with self.subTest(incoming_esp_residue=residue):
                _, regs, _, stack = handoff(BOOT.read_text(), 0x90000 + residue)
                self.assertEqual(regs["%esp"] % 16, 0,
                                 "bootstrap aligns ESP before CALL, not at callee entry")
                self.assertEqual((regs["%esp"] - 4) % 16, 12)
                self.assertEqual(stack[regs["%esp"]], 0x2BADB002)
                self.assertEqual(stack[regs["%esp"] + 4], 0x12345678)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args, extra = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BootHandoff)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"status": "PASS" if result.wasSuccessful() else "FAIL",
              "scope": "source-level bounded model, not privileged execution",
              "source_sha256": hashlib.sha256(BOOT.read_bytes()).hexdigest(),
              "tests_run": result.testsRun,
              "failures": [{"test": str(test), "trace": trace}
                           for test, trace in result.failures + result.errors]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
