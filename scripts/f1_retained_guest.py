"""F1-only workflow invoked by boot_metadata_test --f1 (no shell workflow)."""
from pathlib import Path
import json
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

from b13_entry_inject import Gdb, QEMU, elf_symbols
from f1_capture import F1Capture, Qmp, require, save, sha

CASES = ('success', 'deny_first', 'deny_second', 'deny_alias', 'deny_final_identity')
OPERATIONS = ('admit', 'release', 'unmap', 'matrix', 'enable', 'reload')


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def connect(number, proc, deadline):
    while time.monotonic() < deadline:
        require(proc.poll() is None, 'QEMU exited before control connection')
        try:
            return socket.create_connection(('127.0.0.1', number), timeout=0.2)
        except OSError:
            pass
    raise TimeoutError('control connection deadline')


def inject(path, anchor, payload, changes):
    original = path.read_bytes()
    require(original.count(anchor) == 1 and b'F1_GUEST_ONLY_BEGIN' not in payload, 'unique injection anchor')
    block = b'// F1_GUEST_ONLY_BEGIN\n' + payload + b'\n// F1_GUEST_ONLY_END\n'
    changed = original.replace(anchor, block + anchor, 1)
    require(changed.replace(block, b'', 1) == original, 'injection stripping')
    path.write_bytes(changed)
    changes.setdefault(path.as_posix(), []).append({'anchor': anchor.decode(), 'block_hex': block.hex(), 'sha256': sha(block)})


def build_case(root, stage, source_hashes, case, folder, deadline):
    source = stage / 'source'
    source.mkdir()
    copied = {}
    for name, digest in source_hashes.items():
        if name.startswith(('src/', 'crates/', 'system/')) or name in ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', 'target.json', 'linker.ld', '.cargo/config.toml'):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not (root / name).is_symlink(), 'symlink source input')
            shutil.copyfile(root / name, target)
            require(sha(target.read_bytes()) == digest, 'copy identity')
            copied[name] = digest
    changes = {}
    main = source / 'src/main.rs'
    inject(main, b'    // stub: enable ps2 & interrupts', b'    memory::paging::retained_owner::guest::setup();\n    memory::run_retained_owner();', changes)
    owner = source / 'src/memory/retained_owner.rs'
    inject(owner, b'// Caller continuously owns smoke', b'#[path = "f1_guest.rs"]\npub(crate) mod guest;', changes)
    inject(owner, b'    // F1_GUEST_PRE_SEAL', b'    guest::pre_seal(owner);', changes)
    inject(owner, b'    // F1_GUEST_POST_UNLOCK_PROBES', b'    let success = guest::probes(success);', changes)
    failure = {1: ('FIRST', 2), 2: ('SECOND', 4), 3: ('ALIAS', 3), 4: ('IDENTITY', 6)}
    if case in failure:
        hook, code = failure[case]
        inject(owner, ('    // F1_GUEST_DENY_' + hook).encode(), f'    return close_failure(owner, fa, {code});'.encode(), changes)
    frame = source / 'src/memory/frame.rs'
    inject(frame, b'    /// Only negative host probes may duplicate authority;', b'    pub(super) fn duplicate_for_guest(&self) -> Self { Self { addr: self.addr, id: self.id, domain: self.domain } }', changes)
    template = (root / 'scripts/f1_guest_fixture.rs').read_bytes()
    require(template.count(b'F1_CASE_PLACEHOLDER') == 1, 'case injection identity')
    guest = template.replace(b'F1_CASE_PLACEHOLDER', str(case).encode())
    added = source / 'src/memory/f1_guest.rs'
    added.write_bytes(guest)
    # Strip precisely the declared instrumentation; compare EVERY copied input.
    for name, digest in copied.items():
        path = source / name
        raw = path.read_bytes()
        for entry in reversed(changes.get(path.as_posix(), [])):
            block = bytes.fromhex(entry['block_hex'])
            require(raw.count(block) == 1, 'duplicate/missing delimited injection')
            raw = raw.replace(block, b'', 1)
        require(sha(raw) == digest, 'canonical body drift after stripping')
    require(not any(os.environ.get(k) for k in ('RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_DIR')), 'unrecorded build override')
    argv = ['cargo', '+nightly', 'build', '--locked', '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(stage / 'build')]
    with (folder / 'build.log').open('wb') as log:
        built = subprocess.run(argv, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=max(1, deadline - time.monotonic()))
    manifest = {'case': case, 'name': CASES[case], 'command': argv, 'cwd': str(source), 'exit': built.returncode,
                'stage': str(stage), 'copied': copied, 'injections': changes, 'added_guest_sha256': sha(guest),
                'kernel_sha256': sha((stage / 'build/target/debug/kernel').read_bytes()) if built.returncode == 0 else None,
                'source_snapshot': source_hashes,
                'staged_snapshot': {p.relative_to(source).as_posix(): sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}}
    save(folder / 'build.json', manifest)
    require(built.returncode == 0, 'copied F1 guest build failed')
    return stage / 'build/target/debug/kernel'


def run_guest(kernel, symbol_kernel, ram, case, folder, identities, timeout):
    folder.mkdir()
    schedule = (['pre_seal'] if case == 0 else []) + ['pre_probe']
    for operation in OPERATIONS:
        schedule += ['before_' + operation, 'after_' + operation]
    schedule += ['post_probes']
    symbols = elf_symbols(symbol_kernel)
    addresses = [symbols['f1_' + name]['address'] for name in schedule]
    require(len(set(addresses)) == len(addresses), 'checkpoint symbol identity collision')
    gp, qp = port(), port()
    command = [str(QEMU), '-kernel', str(kernel), '-m', str(ram), '-smp', '1', '-machine', 'pc',
               '-display', 'none', '-nic', 'none', '-monitor', 'none', '-no-reboot', '-no-shutdown',
               '-serial', f'file:{folder / "serial.txt"}', '-d', 'int,guest_errors', '-D', str(folder / 'qemu.log'),
               '-S', '-gdb', f'tcp:127.0.0.1:{gp}', '-qmp', f'tcp:127.0.0.1:{qp},server=on,wait=off']
    report = {'overall': 'FAIL', 'argv': command, 'case': case, 'name': CASES[case], 'ram_mib': ram,
              'identities': identities, 'schedule': schedule, 'checkpoints': [], 'owned_qemu_exited': False}
    save(folder / 'planned.json', report)
    proc = None
    sockets = []
    deadline = time.monotonic() + timeout
    try:
        with (folder / 'qemu_stderr.txt').open('wb') as stream:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stream)
        report['qemu_pid'] = proc.pid
        gs, qs = connect(gp, proc, deadline), connect(qp, proc, deadline)
        sockets = [gs, qs]
        gs.settimeout(max(1, deadline - time.monotonic()))
        qs.settimeout(10)
        gdb, qmp = Gdb(gs), Qmp(qs)
        gdb.command('?')
        for address in addresses:
            require(gdb.command(f'Z1,{address:x},1') == 'OK', 'checkpoint execute-breakpoint unsupported')
        controller = F1Capture(folder.name, case, ram, identities, schedule, symbols, folder)
        stopped = gdb.command('c')
        for ordinal, checkpoint in enumerate(schedule):
            require(time.monotonic() < deadline, 'guest capture deadline')
            snapshot = controller.capture(gdb, qmp, stopped)
            report['checkpoints'].append({'checkpoint': checkpoint, 'ordinal': ordinal,
                                          'snapshot': str(controller.held / 'snapshot.json')})
            ack = {'run': folder.name, 'case': case, 'checkpoint': checkpoint, 'ordinal': ordinal,
                   'manifest_sha256': sha((controller.held / 'snapshot.json').read_bytes()), 'capture_complete': True}
            controller.acknowledge(ack)
            stopped = controller.continue_guest(gdb, final=checkpoint == 'post_probes')
        require(controller.next == len(schedule), 'incomplete capture schedule')
        inventory = snapshot['inventory']
        require(inventory[9] == (2, 0, 1, 1, 2)[case] and inventory[10] == (0, 2, 4, 3, 6)[case] and inventory[11] == 127, 'guest acquisitions/failure/refusal mask')
        fields = None
        while time.monotonic() < deadline:
            require(proc.poll() is None, 'guest exited instead of nonreturning halt')
            text = (folder / 'serial.txt').read_text(errors='replace')
            if 'F1OWNER TERMINAL\n' in text:
                fields, hardware = qmp.hardware()
                if 'HLT=1' in hardware:
                    break
        require(fields is not None and 'HLT=1' in hardware, 'missing terminal halted CPU')
        second_fields, second_hardware = qmp.hardware()
        require(fields['CR3'] == second_fields['CR3'] == controller.cr3 and 'HLT=1' in second_hardware, 'nonstable terminal CPU')
        require(text.count('F1OWNER TERMINAL\n') == 1 and text.count('F1OWNER PROBES PASS\n') == 1, 'terminal/probe marker identity')
        require('F1OWNER PROBES FAIL' not in text and 'F1OWNER FIXTURE FAIL' not in text and 'rosti>' not in text and 'page fault:' not in text and 'CPU exception' not in text and 'PANIC:' not in text, 'unexpected continuation/fault')
        if case == 0:
            require(text.count('F1OWNER PASS cpl=0 terminal=halt ') == 1 and 'F1OWNER FAIL' not in text and 'EXPECTED_REFUSAL' not in text, 'success marker')
        else:
            require(text.count('F1OWNER EXPECTED_REFUSAL\n') == 1 and text.count('F1OWNER FAIL terminal=halt ') == 1 and 'F1OWNER PASS' not in text, 'expected-refusal marker')
        records = re.findall(r'^F1OWNER (?:PASS cpl=0|FAIL) terminal=halt ((?:[0-9a-f]{8} ){16})$', text, re.M)
        require(len(records) == 1, 'exact terminal scalar record')
        scalars = [int(value, 16) for value in records[0].split()]
        acquired = (2, 0, 1, 1, 2)[case]
        require(scalars[1] == acquired and scalars[10:12] == inventory[5:7], 'resource baseline/acquisition identity')
        require(scalars[12] == scalars[10] - acquired and scalars[13] == scalars[11] + acquired, 'measured F1 frame delta')
        require(scalars[14] == 12 and inventory[4] <= 130, 'finite production/fixture policy ceiling')
        report['resource_scalars'] = scalars
        report['terminal_hardware'] = [hardware, second_hardware]
        report['inventory'] = inventory
        report['overall'] = 'PASS'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            report['actual_qemu_exit'] = proc.wait(timeout=10)
            report['owned_qemu_exited'] = proc.poll() is not None
        for sock in sockets:
            sock.close()
        save(folder / 'report.json', report)
    require(report['overall'] == 'PASS' and report['owned_qemu_exited'], report.get('error', 'guest failure'))
    return report


def no_reparse(path):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
            'F1 cleanup symlink/junction/reparse point refused')
    return info


class OwnedStage:
    """Current-process creation record; never adopt a caller-supplied stage."""
    def __init__(self, dist):
        dist = Path(dist).absolute()
        for ancestor in reversed((dist, *dist.parents)):
            no_reparse(ancestor)
        require(dist.resolve() == dist and dist.is_dir(), 'F1 cleanup root identity')
        self.path = Path(tempfile.mkdtemp(prefix='phase11f1_guest_', dir=dist))
        info = no_reparse(self.path)
        self._created = (self.path, dist, info.st_dev, info.st_ino, os.getpid())

    def remove(self):
        created, dist, device, inode, pid = self._created
        require(self.path == created and pid == os.getpid(), 'F1 stage not owned by invocation')
        require(created.parent == dist and created.name.startswith('phase11f1_guest_')
                and created.resolve().parent == dist, 'F1 stage outside approved root/prefix')
        for ancestor in reversed((dist, *dist.parents)):
            no_reparse(ancestor)
        info = no_reparse(created)
        require((info.st_dev, info.st_ino) == (device, inode) and stat.S_ISDIR(info.st_mode),
                'F1 stage creation identity changed')
        # Refuse ALL reparse entries before deletion, including nested junctions.
        # shutil.rmtree on supported Python also refuses directory-symlink roots
        # and does not recurse through Windows directory junctions.
        pending = [created]
        while pending:
            here = pending.pop()
            no_reparse(here)
            with os.scandir(here) as entries:
                for entry in entries:
                    child = Path(entry.path)
                    child_info = no_reparse(child)
                    require(child.resolve().is_relative_to(created), 'F1 cleanup path escape')
                    if stat.S_ISDIR(child_info.st_mode):
                        pending.append(child)
        require((no_reparse(created).st_dev, no_reparse(created).st_ino) == (device, inode),
                'F1 stage identity changed before removal')
        shutil.rmtree(created)
        require(not os.path.lexists(created), 'F1 stage still present after removal')


def retained_complete(report, run, before, default_hash):
    """Check durable reader inputs before discarding disposable compiler output."""
    require(report['overall'] == 'PASS' and report['source_unchanged'] is True
            and report['default_elf_unchanged'] is True
            and report['source_snapshot'] == before and report['default_elf_sha256'] == default_hash,
            'F1 failed matrix/preservation must retain stage')
    expected = {(case, ram) for case in range(5) for ram in (128, 512)}
    require(len(report['scenarios']) == 10
            and {(r['case'], r['ram_mib']) for r in report['scenarios']} == expected,
            'F1 cleanup requires ten exact scenarios')
    require(report['checks'] and all(r.get('pass') is True for r in report['checks']),
            'F1 failed/empty checks must retain stage')
    for row in report['scenarios']:
        case, ram = row['case'], row['ram_mib']
        child_path = run / f'{case}_{ram}' / 'report.json'
        require(Path(row['report']).resolve() == child_path.resolve()
                and row['overall'] == 'PASS' and row['name'] == CASES[case], 'F1 child path/state')
        child = json.loads(child_path.read_bytes())
        require(child['overall'] == 'PASS' and child['owned_qemu_exited'] is True
                and child['actual_qemu_exit'] == 1
                and (child['case'], child['ram_mib'], child['name']) == (case, ram, CASES[case]),
                'F1 missing/failed/unexited child must retain stage')
        build_root = run / f'build_{case}'
        build_path = build_root / 'build.json'
        build = json.loads(build_path.read_bytes())
        require(build['exit'] == 0 and build['case'] == case, 'F1 failed build must retain stage')
        identity = child['identities']
        require(sha((build_root / 'kernel.elf').read_bytes()) == build['kernel_sha256'] == identity['kernel_sha256']
                and sha((build_root / f'fixture_{ram}.elf').read_bytes()) == identity['boot_fixture_sha256']
                and sha(build_path.read_bytes()) == identity['build_manifest_sha256']
                and identity['source_snapshot_sha256'] == sha(json.dumps(before, sort_keys=True).encode()),
                'F1 retained source/build/ELF identity')


def workflow(args):
    from boot_metadata_test import PROJECT, build_fixture, parse_elf
    from phase6_verify import source_snapshot
    require(not sys.flags.optimize, 'optimized F1 runner refused')
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='f1_retained_', dir=root))
    report = {'overall': 'FAIL', 'run': str(run), 'scenarios': [], 'checks': []}
    started = time.monotonic()
    deadline = started + args.timeout
    before = source_snapshot()
    default_elf = args.kernel.resolve()
    default_hash = sha(default_elf.read_bytes())
    owned = OwnedStage(PROJECT / 'dist')
    stage = owned.path
    report['stage_removed'] = False
    try:
        report['source_snapshot'] = before
        report['default_elf_sha256'] = default_hash
        report['owned_stage'] = str(stage)
        created, dist, device, inode, pid = owned._created
        report['stage_creation'] = {'path':str(created), 'root':str(dist),
                                    'device':device, 'inode':inode, 'creator_pid':pid,
                                    'tracking':'current-process mkdtemp creation, never adopted'}
        for case in range(5):
            build_folder = run / f'build_{case}'
            build_folder.mkdir()
            case_stage = stage / str(case)
            case_stage.mkdir()
            kernel = build_case(PROJECT, case_stage, before, case, build_folder, deadline)
            original = kernel.read_bytes()
            parse_elf(original)
            retained_kernel = build_folder / 'kernel.elf'
            shutil.copyfile(kernel, retained_kernel)
            require(sha(retained_kernel.read_bytes()) == sha(original), 'retained F1 kernel copy')
            build_report = json.loads((build_folder / 'build.json').read_bytes())
            require(build_report['kernel_sha256'] == sha(original), 'F1 build kernel identity')
            for ram in list(dict.fromkeys(args.ram)):
                artifact = case_stage / f'ram{ram}'
                artifact.mkdir()
                data, metadata = build_fixture(original, 'nomodule', ram)
                boot = artifact / 'fixture.elf'
                boot.write_bytes(data)
                retained_boot = build_folder / f'fixture_{ram}.elf'
                shutil.copyfile(boot, retained_boot)
                require(sha(retained_boot.read_bytes()) == sha(data), 'retained F1 fixture copy')
                identities = {'source_snapshot_sha256': sha(json.dumps(before, sort_keys=True).encode()),
                              'build_manifest_sha256': sha((build_folder / 'build.json').read_bytes()),
                              'kernel_sha256': sha(original), 'boot_fixture_sha256': sha(data),
                              'iso_sha256': None, 'boot': 'elf', 'metadata': metadata}
                row = run_guest(boot, kernel, ram, case, run / f'{case}_{ram}', identities,
                                min(args.guest_timeout, deadline - time.monotonic()))
                report['scenarios'].append({'name': CASES[case], 'case': case, 'ram_mib': ram,
                                            'overall': row['overall'], 'report': str(run / f'{case}_{ram}/report.json')})
        require(source_snapshot() == before and sha(default_elf.read_bytes()) == default_hash, 'source/default ELF drift')
        require(len(report['scenarios']) == 5 * len(set(args.ram)), 'incomplete F1 guest matrix')
        report['checks'].append({'name': 'complete F1 copied-source Ring0 matrix and exact capture', 'pass': True})
        report['overall'] = 'PASS'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        try:
            report['source_unchanged'] = source_snapshot() == before
            report['default_elf_unchanged'] = sha(default_elf.read_bytes()) == default_hash
            retained_complete(report, run, before, default_hash)
            # Persist the completed matrix before removing disposable build data.
            save(run / 'matrix_complete.json', report)
            owned.remove()
            report['stage_removed'] = not os.path.lexists(stage)
            require(report['stage_removed'], 'F1 cleanup did not complete')
        except BaseException as error:
            report['overall'] = 'FAIL'
            report['cleanup_error'] = repr(error)
        if not report['stage_removed']:
            report['stage_retained'] = str(stage)
        report['elapsed_s'] = time.monotonic() - started
        save(run / 'report.json', report)
    print(f"{report['overall']}: F1 retained guest {run}")
    if report['overall'] != 'PASS':
        print(report.get('error', 'preservation failure'))
    return 0 if report['overall'] == 'PASS' else 1
