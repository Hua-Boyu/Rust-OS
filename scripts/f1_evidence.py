"""Fail-closed readback of invocation-owned F1 physical-image evidence."""
import json
from pathlib import Path
import re
import struct
import sys

from b13_entry_inject import elf_symbols
from f1_capture import require, sha
from f1_retained_guest import CASES, OPERATIONS


def schedule_for(case):
    return (['pre_seal'] if case == 0 else []) + ['pre_probe'] + [edge + operation for operation in OPERATIONS for edge in ('before_', 'after_')] + ['post_probes']


def scenario_identities(rows):
    expected = {(case, ram) for case in range(5) for ram in (128, 512)}
    require(isinstance(rows, list) and len(rows) == len(expected), 'missing/zero/extra F1 scenarios')
    actual = []
    for row in rows:
        identity = (row.get('case'), row.get('ram_mib'))
        require(identity in expected and row.get('name') == CASES[identity[0]] and row.get('overall') == 'PASS', 'impostor/substituted F1 scenario')
        actual.append(identity)
    require(len(set(actual)) == len(expected), 'duplicate F1 scenario')
    return expected


def f1_evidence(path, expected_source):
    require(not sys.flags.optimize, 'optimized F1 readback refused')
    path = Path(path).resolve()
    root = path.parent
    pins = {}
    def read(p):
        p = Path(p).resolve()
        require(p.is_relative_to(root), 'evidence outside invocation')
        data = p.read_bytes()
        pins[p] = sha(data)
        return data
    report = json.loads(read(path))
    require(report.get('overall') == 'PASS' and report.get('source_unchanged') is True and report.get('default_elf_unchanged') is True and report.get('stage_removed') is True, 'F1 aggregate state/preservation/cleanup')
    require(report.get('source_snapshot') == expected_source, 'F1 source snapshot substitution')
    require(report.get('checks') and all(row.get('pass') is True for row in report['checks']), 'F1 empty/failed aggregate checks')
    scenario_identities(report.get('scenarios'))
    require({p.parent.name for p in root.glob('*_*/report.json')} == {f'{c}_{r}' for c in range(5) for r in (128, 512)}, 'extra/missing invocation child reports')
    snapshots = 0
    for row in report['scenarios']:
        case, ram = row['case'], row['ram_mib']
        child_path = root / f'{case}_{ram}' / 'report.json'
        require(Path(row['report']).resolve() == child_path, 'child report path substitution')
        child = json.loads(read(child_path))
        require(child['overall'] == 'PASS' and child['owned_qemu_exited'] is True and child['actual_qemu_exit'] == 1, 'F1 guest/cleanup/actual exit')
        require((child['case'], child['ram_mib'], child['name']) == (case, ram, CASES[case]), 'child scenario identity')
        wanted = schedule_for(case)
        require(child['schedule'] == wanted and [r['checkpoint'] for r in child['checkpoints']] == wanted, 'missing/duplicate/substituted F1 checkpoint')
        require([r['ordinal'] for r in child['checkpoints']] == list(range(len(wanted))), 'checkpoint ordinals')
        require({p.name for p in child_path.parent.iterdir() if p.is_dir()} == {f'{i:02d}_{name}' for i, name in enumerate(wanted)}, 'extra/missing snapshot directory')
        build_path = root / f'build_{case}' / 'build.json'
        build = json.loads(read(build_path))
        require(build['exit'] == 0 and build['case'] == case and build['source_snapshot'] == expected_source, 'build/input identity')
        retained_kernel = root / f'build_{case}' / 'kernel.elf'
        require(sha(read(retained_kernel)) == build['kernel_sha256'], 'retained emitted kernel')
        symbols = elf_symbols(retained_kernel)
        identity = child['identities']
        require(identity['source_snapshot_sha256'] == sha(json.dumps(expected_source, sort_keys=True).encode()) and identity['build_manifest_sha256'] == pins[build_path] and identity['kernel_sha256'] == build['kernel_sha256'] and identity['iso_sha256'] is None and identity['boot'] == 'elf', 'source/build/ELF/ISO identity')
        boot_path = root / f'build_{case}' / f'fixture_{ram}.elf'
        require(sha(read(boot_path)) == identity['boot_fixture_sha256'], 'boot fixture bytes')
        argv = child['argv']
        require(argv.count('-m') == 1 and argv[argv.index('-m') + 1] == str(ram) and argv[argv.index('-smp') + 1] == '1' and '-drive' not in argv and '-cdrom' not in argv, 'actual QEMU configuration')
        require(Path(argv[argv.index('-kernel') + 1]).resolve() == Path(report['owned_stage']) / str(case) / f'ram{ram}' / 'fixture.elf', 'QEMU boot operand identity')
        prior = None
        cr3 = None
        final_inventory = None
        for ordinal, checkpoint in enumerate(wanted):
            item = child['checkpoints'][ordinal]
            here = child_path.parent / f'{ordinal:02d}_{checkpoint}'
            snapshot_path = here / 'snapshot.json'
            require(Path(item['snapshot']).resolve() == snapshot_path, 'snapshot path identity')
            snapshot = json.loads(read(snapshot_path))
            require((snapshot['run'], snapshot['case'], snapshot['ram_mib'], snapshot['checkpoint'], snapshot['ordinal']) == (child_path.parent.name, case, ram, checkpoint, ordinal), 'snapshot identity')
            require(snapshot['identities'] == identity and snapshot['capture_complete'] is True and snapshot['failure_outcome'] is None and snapshot['query_status']['running'] is False and snapshot['stop_reply'].startswith(('T05', 'S05')), 'capture/stop identity')
            cpu = snapshot['hardware']
            require(cpu == snapshot['hardware_after'] and cpu['EIP'] == symbols['f1_' + checkpoint]['address'] and cpu['CR0'] & 0x80010000 == 0x80010000 and not cpu['CR4'] & 0x30 and not cpu['EFL'] & 0x200, 'actual CPU identity/mode')
            require('CPL=0' in snapshot['registers'] and 'CPL=0' in snapshot['registers_after'], 'actual CPL')
            if cr3 is None:
                cr3 = cpu['CR3']
            require(cpu['CR3'] == snapshot['actual_cr3'] == cr3 and cr3 % 4096 == 0, 'CR3 stability')
            inventory_raw = read(here / 'inventory.bin')
            require(inventory_raw == read(here / 'inventory_after.bin'), 'inventory advanced during capture')
            inventory = list(struct.unpack('<16I', inventory_raw))
            require(inventory == snapshot['inventory'] and inventory[0:3] == [0xf101b3, case, cr3] and inventory[3] != cr3 and inventory[12] == 1 and inventory[13] != 0, 'physical scalar inventory')
            final_inventory = inventory
            pages = {}
            roles = {}
            require(len(snapshot['images']) == 2 * (1 + ram // 4), 'complete active/alternate table inventory')
            for image in snapshot['images']:
                physical = image['physical']
                require(physical not in pages and physical >= 4096 and physical % 4096 == 0 and physical + 4096 <= ram * 1024 * 1024, 'frame uniqueness/bounds')
                require(Path(image['file']).name == image['file'] and image['length'] == 4096, 'image filename/length')
                raw = read(here / image['file'])
                require(len(raw) == 4096 and sha(raw) == image['sha256'] and raw == read(here / ('repeat_' + image['file'])), 'full-page bytes/hash/repeat')
                require(image['kind'] in ('PDE', 'PTE') and image['role'] in ('active', 'alternate'), 'table role')
                pages[physical] = raw
                roles[physical] = (image['kind'], image['role'])
            for role, directory in [('active', cr3), ('alternate', inventory[3])]:
                require(roles[directory] == ('PDE', role), 'directory role identity')
                pdes = struct.unpack('<1024I', pages[directory])
                tables = {p & 0xfffff000 for p in pdes if p & 1}
                require(len(tables) == ram // 4 and tables == {p for p, tags in roles.items() if tags == ('PTE', role)}, 'actual directory/table linkage')
                require(all(not p & 0x84 for p in pdes if p & 1), 'USER/large PDE')
                require(all(not pte & 4 for table in tables for pte in struct.unpack('<1024I', pages[table]) if pte & 1), 'USER PTE')
            differences = []
            equal = None
            if prior is not None:
                require(prior.keys() == pages.keys(), 'cross-checkpoint frame identity')
                equal = True
                for physical, raw in pages.items():
                    if prior[physical] != raw:
                        equal = False
                        allowed = 0x20 if roles[physical][0] == 'PDE' else 0x60
                        for index, (a, b) in enumerate(zip(struct.unpack('<1024I', prior[physical]), struct.unpack('<1024I', raw))):
                            if a != b:
                                require(not ((a ^ b) & ~allowed), 'software-controlled table difference')
                                differences.append({'physical': physical, 'offset': index * 4, 'old': a, 'new': b, 'allowed_ad': allowed, 'kind': roles[physical][0]})
            require(snapshot['raw_equal_previous'] == equal and snapshot['differences'] == differences, 'raw/A-D difference report mismatch')
            prior = pages
            ack = json.loads(read(here / 'ack.json'))
            require(ack == {'run': child_path.parent.name, 'case': case, 'checkpoint': checkpoint, 'ordinal': ordinal, 'manifest_sha256': pins[snapshot_path], 'capture_complete': True}, 'persisted capture acknowledgement')
            snapshots += 1
        require(child['inventory'] == final_inventory and final_inventory[9:12] == [(2, 0, 1, 1, 2)[case], (0, 2, 4, 3, 6)[case], 127], 'postprobe retained identity/outcome')
        s = child['resource_scalars']
        acquired = (2, 0, 1, 1, 2)[case]
        require(len(s) == 16 and s[1] == acquired and s[10:12] == final_inventory[5:7] and s[12] == s[10] - acquired and s[13] == s[11] + acquired and s[14] == 12 and final_inventory[4] <= 130, 'measured resources')
        terminal = child['terminal_hardware']
        require(len(terminal) == 2 and all('HLT=1' in text and 'CPL=0' in text and re.search(r'CR3=0*' + f'{cr3:x}' + r'\b', text) for text in terminal), 'actual nonreturning terminal')
        serial = read(child_path.parent / 'serial.txt').decode(errors='replace')
        require(serial.count('F1OWNER TERMINAL\n') == 1 and serial.count('F1OWNER PROBES PASS\n') == 1 and 'rosti>' not in serial and 'PANIC:' not in serial and 'page fault:' not in serial and 'CPU exception' not in serial, 'terminal serial identity')
    return {'scenarios': 10, 'snapshots': snapshots, 'pins': pins}
