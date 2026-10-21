"""Canonical eighteen-case F3 Ring-0 emulator aggregate (not CPL3 acceptance).

Explicit execution builds two copied fixtures and boots sequentially. Import
is side-effect free. Logs live outside frozen subordinate trees.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from f2_exception_guest import source_snapshot
from f3_gdt_guest import green_snapshot, save
from f3_evidence import require, sha, strict_json
from f3_full_evidence import CANONICAL_SOURCES, ROOT_FILES, REQUIRED, SUPPLEMENTAL_REQUIRED, validate
import f3_evidence

ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    # Independently enumerate on every call; never just rehash the old paths.
    first, second = source_snapshot(), green_snapshot()
    require(first == second and set(CANONICAL_SOURCES) <= first.keys(), 'canonical source enumeration mismatch')
    return first


def discover_objdump():
    """Discover installed LLVM/GNU tools; never install or consult ignored code."""
    for name in ('llvm-objdump','rust-objdump','objdump'):
        tool = shutil.which(name)
        if tool:
            return Path(tool).resolve()
    sysroot = Path(subprocess.check_output(['rustc','+nightly','--print','sysroot'], text=True, timeout=30).strip())
    tools = sorted((sysroot/'lib/rustlib').glob('*/bin/llvm-objdump*'))
    if not tools:
        # The existing reviewed tool can belong to a dated installed nightly,
        # independently of the active build toolchain. Discover installation
        # paths directly; never read historical ignored reports to find it.
        rustup_home = Path(os.environ.get('RUSTUP_HOME',str(Path.home()/'.rustup')))
        tools = sorted((rustup_home/'toolchains').glob('*/lib/rustlib/*/bin/llvm-objdump*'))
    require(bool(tools), 'installed objdump unavailable; install llvm-tools separately')
    return tools[0].resolve()


def run_owned(argv, log, timeout, record):
    """Retain the wrapper while capturing its descendants on timeout.

    subprocess.run(timeout=...) kills only its direct child. Killing the
    wrapper first would lose ownership ancestry and bypass a guest's finally.
    """
    import psutil
    proc = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Windows venv launchers can be wrappers around another interpreter.
        # Suspend top-down before enumerating each node's direct children, so
        # the actual driver cannot create another guest during tree cleanup.
        owned = []
        pending = [psutil.Process(proc.pid)]
        while pending:
            node = pending.pop(0)
            try:
                node.suspend()
                owned.append(node)
                pending.extend(node.children())
            except psutil.NoSuchProcess:
                pass
        record['timeout_cleanup'] = {'wrapper_pid':proc.pid,
            'descendant_pids':[p.pid for p in owned if p.pid != proc.pid],
            'suspended_pids':[p.pid for p in owned], 'owned_tree_exited':False}
        try:
            for child in reversed(owned):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(owned, timeout=10)
            require(not alive, 'owned descendant timeout cleanup incomplete')
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
        record['timeout_cleanup']['owned_tree_exited'] = not any(p.is_running() for p in owned) and proc.poll() is not None
        require(record['timeout_cleanup']['owned_tree_exited'], 'owned tree remains')
        raise


def run(output_dir):
    output_dir = Path(output_dir)
    require(output_dir.is_absolute(), 'absolute output required')
    output_dir = output_dir.resolve()
    evidence_root = (ROOT/'test_results').resolve()
    require(output_dir.is_relative_to(evidence_root) and output_dir != evidence_root, 'output must be invocation-owned within test_results')
    output_dir.mkdir(parents=True, exist_ok=True)
    require(not list(output_dir.iterdir()), 'output directory must be empty; refuse stale invocation')
    out = Path(tempfile.mkdtemp(prefix='f3_full_', dir=output_dir)).resolve()
    result = {'schema':'rosti.f3-full-ring0.v1','overall':'HARNESS_FAIL','driver_exit':2,
              'invocation_dir':str(out),'output_dir':str(output_dir),'scripts_dir':str(ROOT/'scripts'),
              'full_f3_acceptance':False,'planned_only':['incomplete full matrix'],
              'hardware_cpl3':False,'drivers':[],'scenarios':[],'scenario_count':0}
    before = snapshot()
    save(out/'source_freeze_before.json',before)
    result['source_sha256'] = before
    (out/'driver.py').write_bytes(Path(__file__).read_bytes())
    (out/'validator.py').write_bytes((ROOT/'scripts/f3_full_evidence.py').read_bytes())
    try:
        objdump = discover_objdump()
        result['objdump'] = str(objdump)
        def driver(component, args, timeout):
            require(snapshot() == before, 'source changed before '+component)
            argv = [sys.executable,'-B',*map(str,args)]
            record = {'component':component,'command':argv,'exit':None,'log':component+'.log'}
            result['drivers'].append(record)
            with (out/record['log']).open('wb') as log:
                record['exit'] = run_owned(argv, log, timeout, record)
            require(record['exit'] == 0, 'subordinate driver failed: '+component)
        driver('minimal',[ROOT/'scripts/f3_gdt_guest.py','--output-dir',out/'minimal'],600)
        minimal_paths = list((out/'minimal').glob('*/report.json'))
        require(len(minimal_paths) == 1, 'missing/ambiguous minimal report')
        result['minimal_report'] = minimal_paths[0].relative_to(out).as_posix()
        supplemental = out/'supplemental'/'f3_supplemental_owned'
        driver('supplemental_prepare',[ROOT/'scripts/f3_supplemental.py','prepare','--output-dir',supplemental],120)
        driver('supplemental_run',[ROOT/'scripts/f3_supplemental.py','run','--prepared-dir',supplemental,'--parent-ready','--objdump',objdump],1200)
        result['supplemental_report'] = (supplemental/'report.json').relative_to(out).as_posix()
        for component,names in (('minimal',f3_evidence.REQUIRED),('supplemental',SUPPLEMENTAL_REQUIRED)):
            child = out/result[component+'_report']
            require(strict_json(child)['source_sha256'] == before, 'subordinate source mismatch')
            for name in names:
                result['scenarios'].append({'name':name,'component':component,
                    'report':(child.parent/name/'guest_report.json').relative_to(out).as_posix()})
        result.update(scenario_count=len(REQUIRED),overall='FULL_RING0_GREEN',driver_exit=0,
                      full_f3_acceptance=True,planned_only=[])
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        after = snapshot()
        save(out/'source_freeze_after.json',after)
        result.update(source_freeze_stable=before == after,source_input_count=len(before))
        if before != after:
            result.update(overall='HARNESS_FAIL',driver_exit=2,full_f3_acceptance=False,planned_only=['source drift'])
        pins = {name:sha((out/name).read_bytes()) for name in ROOT_FILES if (out/name).is_file()}
        # The exact subordinate pin sets come from their validators, not a
        # recursive guess that could silently omit mandatory raw artifacts.
        try:
            if result['driver_exit'] == 0:
                import f3_supplemental_evidence
                for component,helper in (('minimal',f3_evidence),('supplemental',f3_supplemental_evidence)):
                    child = out/result[component+'_report']
                    checked = helper.validate(child,before)
                    pins.update({Path(p).relative_to(out).as_posix():digest for p,digest in checked['pins'].items()})
            result['frozen_bytes'] = pins
            save(out/'report.json',result)
            if result['driver_exit'] == 0:
                validate(out/'report.json',before)
        except Exception as exc:
            result.update(overall='HARNESS_FAIL',driver_exit=2,full_f3_acceptance=False,
                          planned_only=['independent validation failed'],error=repr(exc))
            save(out/'report.json',result)
        print(str(out/'report.json'))
    return result['driver_exit']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    return run(parser.parse_args().output_dir)


if __name__ == '__main__':
    sys.exit(main())
