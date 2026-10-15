"""Host contracts for the B13-owned reusable GDB entry helper."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from b13_entry_inject import Gdb, REGISTERS, elf_symbols, patch_registers, run_injected

ROOT = Path(__file__).resolve().parent.parent


class RegisterPacket(unittest.TestCase):
    def test_patch_preserves_every_unrequested_byte(self):
        raw = bytes(range(128))
        patched = bytes.fromhex(patch_registers(raw.hex(), {"eax": 0x2BADB002, "eflags": 0x602}))
        expected = bytearray(raw)
        struct.pack_into("<I", expected, 0, 0x2BADB002)
        struct.pack_into("<I", expected, 36, 0x602)
        self.assertEqual(patched, expected)

    def test_unknown_register_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported register"):
            patch_registers(bytes(64).hex(), {"cr3": 0})

    def test_short_register_packet_rejected(self):
        with self.assertRaisesRegex(ValueError, "Short"):
            patch_registers(bytes(20).hex(), {"eax": 0})

    def test_register_overflow_is_not_truncated(self):
        with self.assertRaises(struct.error):
            patch_registers(bytes(64).hex(), {"ebx": 0x100000000})


class MemoryReadback(unittest.TestCase):
    def test_connection_close_failure_still_reaps_owned_guest_and_writes_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            kernel = root / 'kernel'
            kernel.write_bytes(b'host mock only')
            proc = mock.Mock(returncode=-9)
            proc.poll.side_effect = [None, None, 0]
            connection = mock.Mock()
            connection.close.side_effect = OSError('close failed')
            with mock.patch('b13_entry_inject.elf_symbols', return_value={'_start': {'address': 0x100000}}), \
                 mock.patch('b13_entry_inject.subprocess.Popen', return_value=proc), \
                 mock.patch('b13_entry_inject.socket.create_connection', return_value=connection), \
                 mock.patch('b13_entry_inject.Gdb') as transport:
                transport.return_value.command.side_effect = RuntimeError('handshake failed')
                with self.assertRaisesRegex(RuntimeError, 'Entry fixture failed'):
                    run_injected(kernel, root / 'guest', lambda *_: None)
            proc.kill.assert_called_once()
            proc.wait.assert_called_once()
            report = json.loads((root / 'guest/report.json').read_text())
            self.assertEqual(report['status'], 'FAIL')
            self.assertTrue(report['cleanup'])
            self.assertIn('close failed', report['connection_cleanup_error'])

    def test_checksum_eof_is_rejected_without_retrying_closed_socket(self):
        sock = mock.Mock()
        sock.recv.side_effect = [b'$', b'#', b'', AssertionError('retried EOF')]
        with self.assertRaisesRegex(EOFError, 'checksum'):
            Gdb(sock).receive()
        self.assertEqual(sock.recv.call_count, 3)

    def test_write_requires_exact_readback(self):
        gdb = Gdb(None)
        responses = iter(["OK", "ffff"])
        gdb.command = lambda _: next(responses)
        with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
            gdb.write(0x10000, b"\x12\x34")
        self.assertEqual(gdb.mutations, [])

    def test_readback_confirmed_mutation_is_recorded(self):
        gdb = Gdb(None)
        commands = []
        responses = iter(["OK", "1234"])
        def command(text):
            commands.append(text)
            return next(responses)
        gdb.command = command
        gdb.write(0x10000, b"\x12\x34")
        self.assertEqual(commands, ["M10000,2:1234", "m10000,2"])
        self.assertEqual(gdb.mutations, [{"address": 0x10000, "bytes": "1234"}])

    def test_short_memory_read_rejected(self):
        gdb = Gdb(None)
        gdb.command = lambda _: "12"
        with self.assertRaisesRegex(RuntimeError, "Short memory"):
            gdb.read(0x10000, 2)


class FixtureSymbols(unittest.TestCase):
    def test_actual_isolated_fixture_symbols(self):
        symbols = elf_symbols(ROOT / "target/b13_fixture/target/debug/b13-boot-fixture")
        for name in ("_start", "b13_handoff", "kernel_main", "b13_case", "b13_abi_probe"):
            self.assertGreaterEqual(symbols[name]["address"], 0x200000)
        self.assertEqual(symbols["stack_top"]["address"] % 16, 0)
        self.assertEqual(symbols["stack_top"]["address"] - symbols["stack_bottom"]["address"], 16384)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
    report = {"status": "PASS" if result.wasSuccessful() else "FAIL", "tests_run": result.testsRun,
              "failures": [{"test": str(test), "trace": trace} for test, trace in result.failures + result.errors]}
    (ROOT / "test_results/phase9_6/b13_inject_host.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
