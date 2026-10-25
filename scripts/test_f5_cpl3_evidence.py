"""Host-only refusal controls for the F5 raw-evidence reader. Synthetic fixtures
below are NOT guest evidence and never establish hardware execution."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import f5_cpl3_evidence as reader

ROOT = Path(__file__).resolve().parents[1]
BEFORE_ELF = ROOT / 'test_results/phase11f5_cpl3_proof/f2_before_macro_01.elf'


class StableWaitControls(unittest.TestCase):
    def test_early_wake_waits_remaining_monotonic_interval(self):
        import f5_cpl3_guest as guest
        with patch.object(guest.time, 'monotonic_ns', side_effect=[0, 188000000, 200000000]), \
             patch.object(guest.time, 'sleep') as sleeper:
            guest.wait_stable_interval(0)
        self.assertEqual([args.args for args in sleeper.call_args_list], [(0.2,), (0.012,)])

    def test_elapsed_interval_does_not_sleep(self):
        import f5_cpl3_guest as guest
        with patch.object(guest.time, 'monotonic_ns', return_value=200000000), \
             patch.object(guest.time, 'sleep') as sleeper:
            guest.wait_stable_interval(0)
        sleeper.assert_not_called()


class AuthorityControls(unittest.TestCase):
    def test_missing_or_mutated_authority_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = root / reader.AUTHORITY
            authority.mkdir(parents=True)
            (authority / 'design.md').write_text('design fixture')
            (authority / 'harness_contract_01.json').write_text('{}')
            (root / 'src').mkdir()
            (root / 'src/exception_entry.s').write_text('f2 fixture')
            with self.assertRaisesRegex(ValueError, 'raw pin'):
                reader.check_authority(root)

    def test_closed_contract_fields_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = root / reader.AUTHORITY
            authority.mkdir(parents=True)
            (root / 'src').mkdir()
            design = (authority / 'design.md')
            contract = (authority / 'harness_contract_01.json')
            f2 = (root / 'src/exception_entry.s')
            amendment = (authority / 'entry_design_amendment_01.md')
            with patch.object(reader, 'DESIGN_SHA', hashlib.sha256(b'design fixture').hexdigest()), \
                 patch.object(reader, 'F2_SHA', hashlib.sha256(b'f2 fixture').hexdigest()):
                for payload in ({'design_sha256': reader.DESIGN_SHA, 'rams': [128],
                                 'scenario_identities': list(reader.IDENTITIES)},
                                {'design_sha256': reader.DESIGN_SHA, 'rams': [128, 512],
                                 'scenario_identities': ['wrong']},
                                {'design_sha256': reader.DESIGN_SHA, 'rams': [128, 512],
                                 'scenario_identities': list(reader.IDENTITIES) * 2}):
                    design.write_text('design fixture')
                    contract.write_text(json.dumps(payload))
                    f2.write_text('f2 fixture')
                    amendment.write_text('amendment fixture')
                    with patch.object(reader, 'CONTRACT_SHA',
                                      hashlib.sha256(contract.read_bytes()).hexdigest()):
                        with self.subTest(contract=payload), self.assertRaisesRegex(
                                ValueError, 'closed authority contract'):
                            reader.check_authority(root)


class HardwareControls(unittest.TestCase):
    base = ('CR0=80010001 CR2=0 CR3=00100000 CR4=00000000 '
            'EIP=100 EFL=2 GDT=00007000 00000037 IDT=00008000 00000fff '
            'TR=0018 07c05000 00000067 00008900 CPL=0 HLT=0 '
            'EFER=0000000000000000')

    def test_missing_or_duplicate_cpu_register_refuses(self):
        with self.assertRaisesRegex(ValueError, 'unique CPU'):
            reader.hardware(self.base.replace('CR2=', '', 1).encode())
        with self.assertRaisesRegex(ValueError, 'unique CPU'):
            reader.hardware((self.base + ' EIP=200').encode())

    def test_unsupported_protection_or_extended_controls_refuses(self):
        mutations = [lambda text: text.replace('CR0=80010001', 'CR0=60010001', 1),
                     lambda text: text.replace('CR4=00000000', 'CR4=00000010'),
                     lambda text: text.replace('CR4=00000000', 'CR4=00000020'),
                     lambda text: text.replace('CR4=00000000', 'CR4=00200000'),
                     lambda text: text.replace('EFER=0000000000000000', 'EFER=0000000080000000'),
                     lambda text: text.replace('CR3=00100000', 'CR3=00100001')]
        for mutation in mutations:
            with self.subTest(text=mutation(self.base)), self.assertRaises(ValueError):
                reader.hardware(mutation(self.base).encode())

    def test_descriptor_register_shape_refuses(self):
        with self.assertRaisesRegex(ValueError, 'unique GDT'):
            reader.hardware(self.base.replace('GDT=00007000 00000037', 'GDT=00007000').encode())
        with self.assertRaisesRegex(ValueError, 'unique IDT'):
            reader.hardware(self.base.replace('IDT=00008000 00000fff', 'IDT=00008000').encode())


class GdtStorageControls(unittest.TestCase):
    """SYNTHETIC HOST fixtures: exercise reader seams, never CPU evidence."""
    def fixture(self, initial=False):
        import struct
        symbols = {'f3_context': {'address': 0x9000, 'size': 272},
                   'f5_gdt': {'address': 0xa000, 'size': 64}}
        old = (bytes(8) + bytes.fromhex('ffff00000099cf00ffff00000093cf00')
               + reader.descriptor(0x9028, 0x8b) + reader.descriptor(0x9090, 0x89))
        gdt = old + struct.pack('<QQ', 0x00cffb000000ffff, 0x00cff3000000ffff)
        storage = bytes(64) if initial else gdt + struct.pack('<I', 1) + bytes(4)
        data = {'f5_gdt': storage, 'gdt': old if initial else gdt,
                'f3_context': old + bytes(232)}
        hw = {'GDT': [0x9000, 39] if initial else [0xa000, 55], 'TR': 24}
        return data, hw, symbols

    def test_exact_extension_lifecycle_and_seven_descriptors(self):
        for initial in (True, False):
            with self.subTest(initial=initial):
                reader.validate_gdt_storage(*self.fixture(initial), initial=initial)

    def test_extent_attempted_padding_and_each_descriptor_tamper_refuse(self):
        for initial in (True, False):
            for offset in (*range(56), 56, 57, 58, 59, 60, 61, 62, 63):
                data, hw, symbols = self.fixture(initial)
                raw = bytearray(data['f5_gdt']); raw[offset] ^= 1
                data['f5_gdt'] = bytes(raw)
                with self.subTest(initial=initial, offset=offset), self.assertRaises(ValueError):
                    reader.validate_gdt_storage(data, hw, symbols, initial=initial)
            for size in (56, 60, 63, 65):
                data, hw, symbols = self.fixture(initial)
                data['f5_gdt'] = (data['f5_gdt'] + bytes(64))[:size]
                symbols['f5_gdt']['size'] = size
                with self.subTest(initial=initial, size=size), self.assertRaises(ValueError):
                    reader.validate_gdt_storage(data, hw, symbols, initial=initial)

    def test_live_table_old_table_and_gdtr_tamper_refuse(self):
        for target in ('gdt', 'f3_context'):
            for offset in range(40 if target == 'f3_context' else 56):
                data, hw, symbols = self.fixture()
                raw = bytearray(data[target]); raw[offset] ^= 1; data[target] = bytes(raw)
                with self.subTest(target=target, offset=offset), self.assertRaises(ValueError):
                    reader.validate_gdt_storage(data, hw, symbols)
        for key, value in (('GDT', [0xa008, 55]), ('GDT', [0xa000, 63]),
                           ('GDT', [0xa000, 54]), ('TR', 32)):
            data, hw, symbols = self.fixture(); hw[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                reader.validate_gdt_storage(data, hw, symbols)

    def test_initial_snapshot_accepts_real_extension_extent(self):
        import struct
        data, hw, symbols = self.fixture(True)
        symbols.update({'f5_record': {'address': 0xb000, 'size': 256},
                        'f5_expect': {'address': 0xc000, 'size': 28},
                        'f5_latch': {'address': 0xd000, 'size': 4}})
        stores = {'owner': {'address': 0xe000, 'size': 8},
                  'allocator': {'address': 0xf000, 'size': 40},
                  'state': {'address': 0x10000, 'size': 1}}
        hw.update({'CR3': 0x1000, 'IDT': [0x11000, 2047]})
        layout = {'OwnerMutex': {'size': 8, 'fields': {'lock': 0}},
                  'AllocatorMutex': {'size': 40, 'fields': {'lock': 0}},
                  'FrameAllocator': {'fields': {'structure_pins': 0, 'runtime_pins': 8,
                                               'free': 16, 'alloc_id': 24}}}
        directory = [0] * 1024; directory[0] = 0x2003
        blobs = {'directory': struct.pack('<1024I', *directory),
                 'table_000': struct.pack('<1024I', *(i * 4096 | 3 for i in range(1024))),
                 **data, **{n: bytes(s['size']) for n, s in stores.items()},
                 **{n: bytes(symbols[n]['size']) for n in ('f5_record', 'f5_expect', 'f5_latch')},
                 'idt': bytes(2048)}
        fa = bytearray(40); fa[0] = 6
        struct.pack_into('<II', fa, 28, 1, 2)
        class SyntheticTransport:
            def origin(self, name, address, size):
                raw = blobs[name.removeprefix('initial_').removesuffix('.bin').removesuffix('_repeat')]
                if len(raw) != size:
                    raise ValueError('synthetic host capture extent')
                return raw
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'initial_capture.json').write_text(json.dumps({
                'controls': hw, 'capture_stable': True, 'table_indices': [0],
                'symbols': {**stores, **symbols}, 'decoded_owner': {}}))
            with patch.object(reader, 'storage_symbols', return_value=stores), \
                 patch.object(reader, 'decode_owner', return_value={}), \
                 patch.object(reader, 'authority', return_value={}), \
                 patch.object(reader, 'decode_allocator', return_value=fa), \
                 patch.object(reader, 'allocator_stats', return_value={}):
                result = reader.snapshot(root, 'initial', hw, layout, symbols,
                                         SyntheticTransport(), initial=True)
            self.assertEqual(result['data']['f5_gdt'], bytes(64))


class AggregateControls(unittest.TestCase):
    def guests(self):
        return [{'scenario': name, 'scenario_integer': n, 'ram_mib': ram}
                for n, name in enumerate(reader.IDENTITIES, 1) for ram in (128, 512)]

    def test_model_only_or_wrong_schema_aggregate_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'report.json').write_text('{"schema":"MODEL_ONLY","overall":"PASS"}')
            with self.assertRaisesRegex(ValueError, 'aggregate outcome'):
                reader.validate(root)

    def test_nonzero_driver_or_partial_matrix_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'artifact.bin').write_bytes(b'x')
            digest = hashlib.sha256(b'x').hexdigest()
            for payload in ({'schema': 'rosti.f5-cpl3-matrix.v1', 'overall': 'PASS',
                             'driver_exit': 1, 'not_canonical_acceptance': True,
                             'selected_scenario': None, 'full_f5_matrix': True,
                             'guests': self.guests(), 'frozen_bytes': {'artifact.bin': digest},
                             'checks': [{'pass': True}]},
                            {'schema': 'rosti.f5-cpl3-matrix.v1', 'overall': 'PASS',
                             'driver_exit': 0, 'not_canonical_acceptance': True,
                             'selected_scenario': 2, 'full_f5_matrix': True,
                             'guests': self.guests(), 'frozen_bytes': {'artifact.bin': digest},
                             'checks': [{'pass': True}]}):
                (root / 'report.json').write_text(json.dumps(payload))
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    reader.validate(root, require_full=True)

    def test_unstable_source_freeze_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'artifact.bin').write_bytes(b'x')
            digest = hashlib.sha256(b'x').hexdigest()
            (root / 'report.json').write_text(json.dumps({
                'schema': 'rosti.f5-cpl3-matrix.v1', 'overall': 'PASS', 'driver_exit': 0,
                'not_canonical_acceptance': True, 'selected_scenario': None,
                'full_f5_matrix': True, 'guests': self.guests(),
                'source_freeze_stable': False,
                'frozen_bytes': {'artifact.bin': digest,
                                 'source_before.json': hashlib.sha256(
                                     json.dumps({'artifact.bin': digest}).encode()).hexdigest(),
                                 'source_after.json': hashlib.sha256(
                                     json.dumps({'artifact.bin': digest}).encode()).hexdigest()},
                'checks': [{'pass': True}]}))
            (root / 'source_before.json').write_text(json.dumps({'artifact.bin': digest}))
            (root / 'source_after.json').write_text(json.dumps({'artifact.bin': digest}))
            with self.assertRaisesRegex(ValueError, 'source freeze'):
                reader.validate(root)


class RecordControls(unittest.TestCase):
    def record(self):
        import struct
        words = [0] * 64
        words[:16] = [0x46354350, 2, 1, 0x07c04fb4, 0x07c04f9c, 0x80010001,
                      0x40000800, 0x1000, 0, 0, 8, 16, 16, 16, 16, 16]
        frame = [0x33] * 4 + [0, 0, 0, 0x07c04fe4, 0x5a17c0de, 0, 0, 0x2b,
                              14, 7, 0x4000010c, 0x2b, 0x10446, 0x40400000, 0x33]
        words[16:35] = frame
        words[35] = 55
        words[37:41] = [24, 0x07c05000, 16, 104]
        return bytearray(struct.pack('<64I', *words))

    def test_wrong_vector_error_oracle_refuses(self):
        import struct
        for word, value in ((16 + 12, 13), (16 + 13, 4), (16 + 14, 0x40000110)):
            raw = self.record()
            struct.pack_into('<I', raw, word * 4, value)
            with self.subTest(word=word), self.assertRaises(ValueError):
                reader.records(raw, 2, 0x1000, 0x446)

    def test_rf_and_af_only_flags_enforced(self):
        import struct
        for word, value in ((16 + 16, 0x10447), (16 + 16, 0x446), (16 + 16, 0x10456 | 0x40)):
            raw = self.record()
            struct.pack_into('<I', raw, word * 4, value)
            with self.subTest(word=word), self.assertRaises(ValueError):
                reader.records(raw, 2, 0x1000, 0x446)

    def test_latch_sentinel_and_frame_geometry_refuse(self):
        import struct
        for word, value in ((2, 0), (16 + 8, 0), (16 + 4, 0x07c04fe0), (3, 0x07c04fb0)):
            raw = self.record()
            struct.pack_into('<I', raw, word * 4, value)
            with self.subTest(word=word), self.assertRaises(ValueError):
                reader.records(raw, 2, 0x1000, 0x446)


class TransportControls(unittest.TestCase):
    def fixture(self, gdb_rows, qmp_rows):
        root = Path(tempfile.mkdtemp())
        (root / 'gdb.jsonl').write_text('\n'.join(gdb_rows))
        (root / 'qmp.jsonl').write_text('\n'.join(qmp_rows))
        return root

    def ok_gdb(self, seq):
        return '{"seq":%d,"command":"g","reply":"4142","started_ns":%d,"ended_ns":%d}' % (seq, seq, seq + 1)

    def ok_qmp(self, seq):
        return '{"seq":%d,"command":"query-status","reply":{"running":true},"started_ns":%d,"ended_ns":%d}' % (seq, seq, seq + 1)

    def test_forbidden_transport_commands_refuse(self):
        bad_gdb = '{"seq":1,"command":"M0,1,aa","reply":"OK","started_ns":1,"ended_ns":2}'
        bad_qmp = '{"seq":2,"command":"system_reset","reply":{},"started_ns":2,"ended_ns":3}'
        with self.assertRaisesRegex(ValueError, 'forbidden GDB'):
            reader.Transport(self.fixture([bad_gdb], [self.ok_qmp(2)]), {})
        with self.assertRaisesRegex(ValueError, 'forbidden QMP'):
            reader.Transport(self.fixture([self.ok_gdb(1)], [bad_qmp]), {})

    def test_sequence_and_causality_refuse(self):
        dup = [self.ok_qmp(2), '{"seq":2,"command":"query-version","reply":{},"started_ns":3,"ended_ns":4}']
        back = [self.ok_qmp(2), '{"seq":3,"command":"query-version","reply":{},"started_ns":0,"ended_ns":1}']
        with self.assertRaisesRegex(ValueError, 'sequence'):
            reader.Transport(self.fixture([self.ok_gdb(1)], dup), {})
        with self.assertRaisesRegex(ValueError, 'causal order|timestamps'):
            reader.Transport(self.fixture([self.ok_gdb(1)], back), {})

    def test_duplicate_pmemsave_refuses(self):
        rows = ['{"seq":%d,"command":"pmemsave","arguments":{"filename":"initial_x.bin",'
                '"val":4096,"size":16},"reply":{},"started_ns":%d,"ended_ns":%d}'
                % (i, i, i + 1) for i in (2, 3)]
        with self.assertRaisesRegex(ValueError, 'duplicate/failed pmemsave'):
            reader.Transport(self.fixture([self.ok_gdb(1)], rows), {})

    def test_stable_interval_exact_boundary_and_short_capture_refusal(self):
        # SYNTHETIC HOST protocol schedule; a requested sleep is not elapsed proof.
        for elapsed in (188000000, 199999999, 200000000, 203000000):
            transport = object.__new__(reader.Transport)
            transport.g = [{'seq': 1, 'command': 'Z1,1000,1', 'reply': 'OK'},
                           {'seq': 2, 'command': 'c', 'reply': 'T05'},
                           {'seq': 3, 'command': 'z1,1000,1', 'reply': 'OK'}]
            transport.q = [{'seq': 4, 'command': 'cont', 'ended_ns': 0},
                           {'seq': 5, 'command': 'stop', 'started_ns': elapsed},
                           {'seq': 6, 'command': 'query-status', 'reply': {'running': False}}]
            transport.physical = {}; transport.used = set()
            with self.subTest(elapsed_ns=elapsed):
                if elapsed < 200000000:
                    with self.assertRaisesRegex(ValueError, 'actual timed stable interval'):
                        transport.finish([0x1000])
                else:
                    transport.finish([0x1000])

    def test_failed_rsp_refuses(self):
        rows = ['{"seq":1,"command":"m1000,4","reply":"E02","started_ns":1,"ended_ns":2}']
        with self.assertRaisesRegex(ValueError, 'failed RSP'):
            reader.Transport(self.fixture(rows, [self.ok_qmp(2)]), {})


class AuditReadbackControls(unittest.TestCase):
    def test_blocked_or_self_declared_audit_refuses_before_io(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'report.json').write_text(
                '{"overall":"BLOCKED","blockers":["open obligation"],"checks":{},"before":"x"}')
            with self.assertRaisesRegex(ValueError, 'incomplete/blocked audit'):
                reader.validate_audit(root, Path('kernel.elf'), BEFORE_ELF)

    def test_wrong_baseline_bytes_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'report.json').write_text('{"overall":"PASS","blockers":[],"checks":{"x":true}}')
            (root / 'not-the-baseline.elf').write_bytes(b'MZ-not-baseline')
            with self.assertRaisesRegex(ValueError, 'baseline bytes'):
                reader.validate_audit(root, Path('kernel.elf'), root / 'not-the-baseline.elf')


class PinControls(unittest.TestCase):
    def test_malformed_digest_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'raw.bin').write_bytes(b'x')
            with self.assertRaisesRegex(ValueError, 'malformed digest'):
                reader.verify_pins(root, {'raw.bin': 'ZZ'})

    def test_noncanonical_or_escaping_artifact_name_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'raw.bin').write_bytes(b'x')
            for name in ('../escape.bin', 'raw.bin\\x', 'raw.bin:', ''):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    reader.local(root, name)

    def test_symlink_artifact_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'real.bin').write_bytes(b'x')
            (root / 'link.bin').symlink_to(root / 'real.bin')
            with self.assertRaises(ValueError):
                reader.tree_pins(root)


class MatrixControls(unittest.TestCase):
    def matrix(self):
        return [{'scenario': name, 'scenario_integer': n, 'ram_mib': ram}
                for n, name in enumerate(reader.IDENTITIES, 1) for ram in (128, 512)]

    def test_component_selection_requires_component_rows(self):
        rows = self.matrix()
        reader.validate_matrix_rows(rows)
        with self.assertRaisesRegex(ValueError, 'exact ordered matrix'):
            reader.validate_matrix_rows(rows, selected=2)
        component = [r for r in rows if r['scenario_integer'] == 2]
        reader.validate_matrix_rows(component, selected=2)
        with self.assertRaisesRegex(ValueError, 'exact ordered matrix'):
            reader.validate_matrix_rows(self.matrix(), selected=2)

    def test_noninteger_or_wrong_identity_rows_refuse(self):
        for bad in ([{**r, 'ram_mib': str(r['ram_mib'])} for r in self.matrix()],
                    [{**r, 'scenario': 'model_only'} for r in self.matrix()],
                    list(reversed(self.matrix()))):
            with self.subTest(rows=bad), self.assertRaises(ValueError):
                reader.validate_matrix_rows(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
