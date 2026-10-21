"""Complete aggregate pure models. Mocked success is NOT hardware acceptance."""
import contextlib
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import f3_evidence as minimal
import f3_full_evidence as ev
import f3_full_guest as driver
import f3_supplemental as supplement_guest
import f3_supplemental_evidence as supplement_ev
import test_f3_evidence as models
import test_f3_supplemental as supplement_models


def default_sources():
    names={'src/main.rs','src/gdt.rs','src/gdt_tss.rs','src/f3_entry.s','src/exception_entry.s',
           'src/interrupt.rs','src/memory/mod.rs','src/memory/paging.rs','src/memory/retained_owner.rs',
           'Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml',*ev.CANONICAL_SOURCES}
    source={n:('UNIT MODEL ONLY '+n+'\n').encode() for n in names}
    source['src/main.rs']+=b'    // stub: enable ps2 & interrupts\n'
    source['src/exception_entry.s']=b'F2_STUB 2\nF2_STUB 12,1\nf2_normalized:\npushal\n.if {frame_size} != 68\n'
    source['src/f3_entry.s']=b'f3_emergency_entry:\nout %al,%dx\n'
    return source


def matrix_model(folder, source_bytes=None):
    source_bytes=default_sources() if source_bytes is None else source_bytes
    before={n:minimal.sha(raw) for n,raw in source_bytes.items()}
    first=folder/'minimal'/'f3_minimal_UNIT_MODEL'
    first.mkdir(parents=True)
    report,_=models.matrix_model(first)
    for name,raw in source_bytes.items():
        models.write(first/'frozen_inputs'/name,raw)
        if name.startswith(('src/','crates/','system/')) or name in ('Cargo.toml','Cargo.lock','rust-toolchain.toml','target.json','linker.ld','.cargo/config.toml'):
            if name=='src/main.rs': raw=raw.replace(b'    // stub: enable ps2 & interrupts',minimal.CALL+b'    // stub: enable ps2 & interrupts')+models.green_assembly()
            models.write(first/'fixture/source'/name,raw)
    # matrix_model's original synthetic manifest must not leave stale inputs.
    for p in (first/'frozen_inputs').rglob('*'):
        if p.is_file() and p.relative_to(first/'frozen_inputs').as_posix() not in source_bytes: p.unlink()
    for name in ('source_freeze_before.json','source_freeze_after.json'): models.dump(first/name,before)
    models.write(first/'driver.py',source_bytes['scripts/f3_gdt_guest.py'])
    models.write(first/'validator.py',source_bytes['scripts/f3_evidence.py'])
    report.update(source_sha256=before,source_input_count=len(before),original_main_sha256=before['src/main.rs'],injected_main_sha256=minimal.sha((first/'fixture/source/src/main.rs').read_bytes()))
    report['frozen_bytes']=models.pins(first)
    models.dump(first/'report.json',report)
    second=folder/'supplemental'/'f3_supplemental_UNIT_MODEL'
    supplemental=supplement_models.matrix_model(second,source_bytes)
    for name in ('source_freeze_before.json','source_freeze_after.json'): models.dump(folder/name,before)
    models.write(folder/'driver.py',source_bytes['scripts/f3_full_guest.py'])
    models.write(folder/'validator.py',source_bytes['scripts/f3_full_evidence.py'])
    for name in ('minimal.log','supplemental_prepare.log','supplemental_run.log'): models.write(folder/name,b'UNIT MODEL ONLY; NO BUILD/QEMU RAN\n')
    scripts=Path(__file__).resolve().parent; python='C:/UNIT_MODEL/python.exe'; objdump='C:/UNIT_MODEL/llvm-objdump.exe'
    result={'schema':'rosti.f3-full-ring0.v1','overall':'FULL_RING0_GREEN','driver_exit':0,
            'invocation_dir':str(folder),'output_dir':str(folder.parent),'scripts_dir':str(scripts),
            'source_sha256':before,'source_freeze_stable':True,'source_input_count':len(before),
            'full_f3_acceptance':True,'hardware_cpl3':False,'planned_only':[],'scenario_count':18,
            'minimal_report':(first/'report.json').relative_to(folder).as_posix(),
            'supplemental_report':(second/'report.json').relative_to(folder).as_posix(),'objdump':objdump,'drivers':[],'scenarios':[]}
    commands=[[python,'-B',str(scripts/'f3_gdt_guest.py'),'--output-dir',str(folder/'minimal')],
              [python,'-B',str(scripts/'f3_supplemental.py'),'prepare','--output-dir',str(second)],
              [python,'-B',str(scripts/'f3_supplemental.py'),'run','--prepared-dir',str(second),'--parent-ready','--objdump',objdump]]
    for component,command in zip(('minimal','supplemental_prepare','supplemental_run'),commands):
        result['drivers'].append({'component':component,'command':command,'exit':0,'log':component+'.log'})
    for component,child,names in (('minimal',first,minimal.REQUIRED),('supplemental',second,ev.SUPPLEMENTAL_REQUIRED)):
        for name in names: result['scenarios'].append({'component':component,'name':name,'report':(child/name/'guest_report.json').relative_to(folder).as_posix()})
    pins={n:minimal.sha((folder/n).read_bytes()) for n in ev.ROOT_FILES}
    for child,r in ((first,report),(second,supplemental)):
        pins.update({(child/n).relative_to(folder).as_posix():d for n,d in r['frozen_bytes'].items()})
        pins[(child/'report.json').relative_to(folder).as_posix()]=minimal.sha((child/'report.json').read_bytes())
    result['frozen_bytes']=pins
    models.dump(folder/'report.json',result)
    return result


@contextlib.contextmanager
def model_environment(root):
    with patch.object(supplement_guest,'ROOT',root), patch('b13_entry_inject.elf_symbols',return_value=models.symbols()), patch.object(supplement_ev,'elf_symbols',return_value=supplement_models.symbols()):
        yield


class FullEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='f3_FULL_UNIT_MODEL_'); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.folder=self.root/'test_results'/'gate'/'f3_full_UNIT_MODEL'
        self.context=model_environment(self.root); self.context.__enter__(); self.addCleanup(self.context.__exit__,None,None,None)
        self.report=matrix_model(self.folder); self.source=self.report['source_sha256']

    def validate(self): return ev.validate(self.folder/'report.json',self.source)

    def test_complete_models_validate_raw_and_exact_pins(self):
        result=self.validate()
        self.assertTrue(result['full_f3_acceptance']); self.assertEqual(result['planned_only'],[])
        self.assertEqual(result['scenario_count'],18)
        expected={str(self.folder/n):d for n,d in self.report['frozen_bytes'].items()}
        expected[str(self.folder/'report.json')]=minimal.sha((self.folder/'report.json').read_bytes())
        self.assertEqual(result['pins'],expected)
        partial=minimal.validate(self.folder/self.report['minimal_report'],self.source)
        self.assertIs(partial['full_f3_acceptance'],False)
        self.assertIs(supplement_ev.validate(self.folder/self.report['supplemental_report'],self.source)['full_f3_acceptance'],False)

    def test_missing_duplicate_substituted_and_scope_controls(self):
        mutations=[lambda r:r['scenarios'].pop(),lambda r:r['scenarios'].__setitem__(-1,r['scenarios'][0]),
                   lambda r:r['scenarios'][0].update(name='substitute'),lambda r:r.update(full_f3_acceptance=False),
                   lambda r:r.update(planned_only=['ss']),lambda r:r.update(hardware_cpl3=True),
                   lambda r:r.update(driver_exit=None),lambda r:r['drivers'][0].update(exit=1),
                   lambda r:r.update(invocation_dir=str(self.folder.parent)),lambda r:r.update(scenario_count=17),
                   lambda r:r.update(minimal_report=r['supplemental_report'])]
        for i,mutate in enumerate(mutations):
            report=copy.deepcopy(self.report); mutate(report); models.dump(self.folder/'report.json',report)
            with self.subTest(control=i),self.assertRaises((ValueError,KeyError)): self.validate()

    def test_external_source_mismatch(self):
        with self.assertRaises(ValueError): ev.validate(self.folder/'report.json',{'wrong':'0'*64})

    def test_missing_and_frozen_mutation(self):
        for name in (self.report['minimal_report'],self.report['supplemental_report'],'driver.py','minimal.log'):
            p=self.folder/name; original=p.read_bytes()
            for mutation in ('missing','modified'):
                if mutation=='missing': p.unlink()
                else: p.write_bytes(original+b' ')
                try:
                    with self.subTest(name=name,control=mutation),self.assertRaises((ValueError,OSError)): self.validate()
                finally:p.write_bytes(original)

    def test_raw_cleanup_refusal_despite_consistent_hashes(self):
        child=self.folder/self.report['supplemental_report']; report=minimal.strict_json(child)
        row=report['scenarios'][0]; row['owned_qemu_exited']=False
        guest=child.parent/row['name']/'guest_report.json'; models.dump(guest,row)
        report['frozen_bytes'][guest.relative_to(child.parent).as_posix()]=minimal.sha(guest.read_bytes()); models.dump(child,report)
        for p in (guest,child):self.report['frozen_bytes'][p.relative_to(self.folder).as_posix()]=minimal.sha(p.read_bytes())
        models.dump(self.folder/'report.json',self.report)
        with self.assertRaisesRegex(ValueError,'cleanup'):self.validate()

    def test_duplicate_stale_and_unowned_reports(self):
        for p in (self.folder.parent/'f3_full_STALE'/'report.json', self.folder/'impostor'/'report.json'):
            models.dump(p,{'overall':'FULL_RING0_GREEN'})
            try:
                with self.subTest(path=p),self.assertRaises(ValueError):self.validate()
            finally:p.unlink()

    def test_unfrozen_artifacts_and_subordinate_wrong_source_refuse(self):
        child=self.folder/self.report['minimal_report']
        for p in (self.folder/'unowned.bin',child.parent/'unfrozen.bin'):
            p.write_bytes(b'UNOWNED UNIT MODEL')
            try:
                with self.subTest(path=p),self.assertRaises(ValueError):self.validate()
            finally:p.unlink()
        report=minimal.strict_json(child); report['source_sha256']={'wrong':'0'*64}; models.dump(child,report)
        self.report['frozen_bytes'][child.relative_to(self.folder).as_posix()]=minimal.sha(child.read_bytes())
        models.dump(self.folder/'report.json',self.report)
        with self.assertRaisesRegex(ValueError,'source mismatch'):self.validate()

    def test_wrapper_driver_refuses_relative_and_stale_without_build(self):
        with patch.object(driver,'ROOT',self.root),patch.object(driver.subprocess,'run') as run:
            with self.assertRaises(ValueError):driver.run(Path('relative'))
            with self.assertRaises(ValueError):driver.run(self.folder.parent)
            run.assert_not_called()


class FullDriverLifetimeTests(unittest.TestCase):
    def test_timeout_kills_and_reaps_only_owned_descendants(self):
        import subprocess
        import sys
        import psutil
        for interpreter in dict.fromkeys((sys._base_executable, sys.executable)):
            with self.subTest(interpreter=interpreter), tempfile.TemporaryDirectory() as name:
                log = Path(name)/'owned.log'
                code = ('import subprocess,sys,time; '
                        'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                        'print(child.pid,flush=True); time.sleep(30)')
                record = {}
                with log.open('wb') as stream:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        driver.run_owned([interpreter,'-c',code],stream,1,record)
                child_pid = int(log.read_text().strip())
                cleanup = record['timeout_cleanup']
                self.assertIn(child_pid,cleanup['descendant_pids'])
                self.assertTrue(set(cleanup['descendant_pids']) <= set(cleanup['suspended_pids']))
                self.assertTrue(cleanup['owned_tree_exited'])
                self.assertFalse(psutil.pid_exists(child_pid))

    def test_normal_owned_driver_exit_is_preserved(self):
        import sys
        with tempfile.TemporaryDirectory() as name:
            with (Path(name)/'out.log').open('wb') as stream:
                self.assertEqual(driver.run_owned([sys._base_executable,'-c','raise SystemExit(7)'],stream,10,{}),7)


if __name__ == '__main__':unittest.main()
