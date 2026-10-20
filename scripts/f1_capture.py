"""F1-only stopped-vCPU capture; no detach, register or guest-memory writes."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


class Qmp:
    def __init__(self, sock):
        self.stream = sock.makefile('rwb')
        self.ident = 0
        require('QMP' in json.loads(self.stream.readline()), 'QMP greeting')
        self.call('qmp_capabilities')

    def call(self, command, **arguments):
        self.ident += 1
        self.stream.write((json.dumps({'execute': command, 'arguments': arguments, 'id': self.ident}) + '\n').encode())
        self.stream.flush()
        while True:
            reply = json.loads(self.stream.readline())
            if reply.get('id') != self.ident:
                continue
            require('error' not in reply, f'QMP {reply}')
            return reply['return']

    def hardware(self):
        text = self.call('human-monitor-command', **{'command-line': 'info registers'})
        fields = {name: int(value, 16) for name, value in re.findall(r'\b(CR0|CR3|CR4|EIP|EFL)=([0-9a-fA-F]+)', text)}
        require(set(fields) == {'CR0', 'CR3', 'CR4', 'EIP', 'EFL'}, 'missing hardware fields')
        require('CPL=0' in text and not fields['EFL'] & 0x200, 'CPL/IF')
        require(fields['CR0'] & 0x80010000 == 0x80010000 and fields['CR4'] & 0x30 == 0, 'paging mode')
        require(fields['CR3'] and not fields['CR3'] & 4095, 'CR3 alignment')
        return fields, text


class F1Capture:
    def __init__(self, run, case, ram, identities, schedule, symbols, folder):
        self.run = run
        self.case = case
        self.ram = ram
        self.identities = identities
        self.schedule = tuple(schedule)
        self.symbols = symbols
        self.folder = Path(folder)
        self.next = 0
        self.authorized = False
        self.held = None
        self.previous = None
        self.cr3 = None
        self.captured_manifest_sha256 = None

    def capture(self, gdb, qmp, stopped):
        require(self.held is None and self.next < len(self.schedule), 'duplicate/extra capture')
        checkpoint = self.schedule[self.next]
        require(stopped.startswith(('T05', 'S05')), 'wrong GDB stop')
        registers = gdb.registers()
        expected = self.symbols['f1_' + checkpoint]['address']
        require(registers['eip'] == expected, 'wrong checkpoint EIP/order')
        status = qmp.call('query-status')
        require(status['running'] is False, 'vCPU not stopped')
        fields, text = qmp.hardware()
        require(fields['EIP'] == expected, 'HMP EIP mismatch')
        if self.cr3 is None:
            self.cr3 = fields['CR3']
        require(fields['CR3'] == self.cr3, 'alternate actual CR3')
        directory = self.folder / f'{self.next:02d}_{checkpoint}'
        directory.mkdir(exist_ok=False)
        def physical(pa, length, name):
            require(pa >= 4096 and pa + length <= self.ram * 1024 * 1024, 'physical capture outside configured RAM')
            target = directory / name
            qmp.call('pmemsave', val=pa, size=length, filename=target.as_posix())
            data = target.read_bytes()
            require(len(data) == length, 'short capture')
            return data
        inventory = list(struct.unpack('<16I', physical(self.symbols['F1_GUEST_INVENTORY']['address'], 64, 'inventory.bin')))
        require(inventory[0] == 0xf101b3 and inventory[1] == self.case and inventory[2] == self.cr3, 'guest/source/checkpoint identity')
        require(inventory[3] and inventory[3] != self.cr3 and inventory[12] == 1 and inventory[13] != 0, 'invalid alternate/guest state')
        pages = {}
        images = []
        for role, root in [('active', self.cr3), ('alternate', inventory[3])]:
            require(root % 4096 == 0 and root not in pages, 'directory overlap/alignment')
            raw = physical(root, 4096, f'{role}_directory.bin')
            pages[root] = (raw, 'PDE')
            images.append({'physical': root, 'role': role, 'kind': 'PDE', 'file': f'{role}_directory.bin', 'length': 4096, 'sha256': sha(raw)})
            count = 0
            for index, pde in enumerate(struct.unpack('<1024I', raw)):
                if pde & 1:
                    count += 1
                    pa = pde & 0xfffff000
                    require(not pde & 0x84 and pa not in pages and count <= 128, 'PDE/duplicate/table bound')
                    name = f'{role}_table_{index:04d}_{pa:08x}.bin'
                    data = physical(pa, 4096, name)
                    require(all(not pte & 4 for pte in struct.unpack('<1024I', data) if pte & 1), 'USER leaf')
                    pages[pa] = (data, 'PTE')
                    images.append({'physical': pa, 'role': role, 'kind': 'PTE', 'pde_index': index, 'file': name, 'length': 4096, 'sha256': sha(data)})
            require(count == (self.ram * 1024 * 1024 - 65536 + 4194303) // 4194304, 'unexpected directory table inventory')
        require(0 < len(images) <= 258, 'empty/overbound inventory')
        for image in images:
            repeat = physical(image['physical'], 4096, 'repeat_' + image['file'])
            require(repeat == pages[image['physical']][0], 'stopped bytes changed')
        after_fields, after_text = qmp.hardware()
        require(after_fields == fields and gdb.registers() == registers and qmp.call('query-status')['running'] is False, 'CPU advanced during capture')
        require(physical(self.symbols['F1_GUEST_INVENTORY']['address'], 64, 'inventory_after.bin') == struct.pack('<16I', *inventory), 'guest advanced before ack')
        differences = []
        raw_equal = None
        if self.previous is not None:
            require(pages.keys() == self.previous.keys(), 'table frame identity changed')
            raw_equal = True
            for pa, (raw, kind) in pages.items():
                old, old_kind = self.previous[pa]
                require(kind == old_kind, 'page role changed')
                if raw != old:
                    raw_equal = False
                    allowed = 0x20 if kind == 'PDE' else 0x60
                    for index, (a, b) in enumerate(zip(struct.unpack('<1024I', old), struct.unpack('<1024I', raw))):
                        if a != b:
                            require(not ((a ^ b) & ~allowed), 'software-controlled table mutation')
                            differences.append({'physical': pa, 'offset': index * 4, 'old': a, 'new': b, 'allowed_ad': allowed, 'kind': kind})
        manifest = {'run': self.run, 'case': self.case, 'ram_mib': self.ram, 'checkpoint': checkpoint,
                    'ordinal': self.next, 'identities': self.identities, 'stop_reply': stopped, 'query_status': status,
                    'actual_cr3': self.cr3, 'hardware': fields, 'hardware_after': after_fields,
                    'registers': text, 'registers_after': after_text, 'inventory': inventory,
                    'images': images, 'raw_equal_previous': raw_equal, 'differences': differences,
                    'capture_complete': True, 'failure_outcome': None}
        save(directory / 'snapshot.json', manifest)
        self.captured_manifest_sha256 = sha((directory / 'snapshot.json').read_bytes())
        self.previous = pages
        self.held = directory
        self.authorized = False
        return manifest

    def verified_ack(self, ack):
        require(self.held is not None, 'missing capture')
        path = self.held / 'snapshot.json'
        require(sha(path.read_bytes()) == self.captured_manifest_sha256, 'captured manifest changed')
        expected = {'run': self.run, 'case': self.case, 'checkpoint': self.schedule[self.next],
                    'ordinal': self.next, 'manifest_sha256': sha(path.read_bytes()), 'capture_complete': True}
        require(isinstance(ack, dict) and ack == expected, 'ack identity')
        manifest = json.loads(path.read_text())
        require(manifest['capture_complete'] is True and manifest['run'] == self.run and manifest['case'] == self.case and manifest['ordinal'] == self.next and manifest['checkpoint'] == self.schedule[self.next], 'manifest identity')
        require(isinstance(manifest['images'], list) and 0 < len(manifest['images']) <= 258, 'zero/overbound images')
        require(len({item['physical'] for item in manifest['images']}) == len(manifest['images']), 'duplicate physical images')
        require(len({item['file'] for item in manifest['images']}) == len(manifest['images']), 'duplicate image files')
        for image in manifest['images']:
            require(isinstance(image['file'], str) and Path(image['file']).name == image['file'], 'nonlocal image path')
            data = (self.held / image['file']).read_bytes()
            require(len(data) == image['length'] == 4096 and sha(data) == image['sha256'], 'image integrity')
            require(data == (self.held / ('repeat_' + image['file'])).read_bytes(), 'repeat integrity')
        return expected

    def acknowledge(self, ack):
        require(self.held is not None and not self.authorized, 'missing/replayed capture')
        expected = self.verified_ack(ack)
        save(self.held / 'ack.json', expected)
        self.authorized = True

    def continue_guest(self, gdb, *, final=False):
        require(self.authorized and self.held is not None, 'continue without acknowledgement')
        self.verified_ack(json.loads((self.held / 'ack.json').read_text()))
        expected_final = self.next == len(self.schedule) - 1
        require(final == expected_final, 'early/late final continue')
        checkpoint = self.schedule[self.next]
        require(gdb.registers()['eip'] == self.symbols['f1_' + checkpoint]['address'], 'resume EIP changed')
        require(gdb.command(f'z1,{self.symbols["f1_" + checkpoint]["address"]:x},1') == 'OK', 'breakpoint removal refused')
        self.next += 1
        self.held = None
        self.authorized = False
        if final:
            gdb.send('c')
            return None
        return gdb.command('c')
