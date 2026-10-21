"""Fail-closed complete F3 Ring-0 aggregate; no builds/guests on import.

Full means the bounded eighteen-case emulator contract, never CPL3, physical
Intel/AMD, mid-task-switch NMI, or general teardown/stack high-water proof.
"""
from pathlib import Path
import f3_evidence as minimal
import f3_supplemental_evidence as supplemental
from f3_evidence import require, sha, strict_json, local, pin_tree

CANONICAL_SOURCES = (
    'scripts/f3_gdt_guest.py', 'scripts/f3_evidence.py', 'scripts/test_f3_evidence.py',
    'scripts/f3_full_guest.py', 'scripts/f3_full_evidence.py',
    'scripts/f3_supplemental.py', 'scripts/f3_supplemental_evidence.py',
    'scripts/test_f3_full_evidence.py', 'scripts/test_f3_supplemental.py',
    'scripts/phase6_verify.py', 'scripts/test_acceptance_harness.py')
SUPPLEMENTAL_REQUIRED = tuple(f'{case}_{ram}' for ram in supplemental.RAMS for case in supplemental.CASES)
REQUIRED = minimal.REQUIRED + SUPPLEMENTAL_REQUIRED
ROOT_FILES = {'driver.py','validator.py','source_freeze_before.json','source_freeze_after.json',
              'minimal.log','supplemental_prepare.log','supplemental_run.log'}


def validate(report_path, expected_source_sha256):
    """Return exact absolute pins only after both independent raw validators pass.

    Raises on incomplete, ambiguous, substituted, unowned or changed evidence.
    Subordinate minimal/supplemental helpers deliberately retain full=False.
    """
    path = Path(report_path).resolve()
    folder = path.parent
    report = strict_json(path)
    require(path.name == 'report.json', 'aggregate filename')
    require(report['schema'] == 'rosti.f3-full-ring0.v1', 'full schema')
    require(report['overall'] == 'FULL_RING0_GREEN' and type(report['driver_exit']) is int and report['driver_exit'] == 0, 'incomplete full driver')
    require(report['invocation_dir'] == str(folder) and report['output_dir'] == str(folder.parent), 'full invocation ownership')
    require(folder.name.startswith('f3_full_') and folder.name != 'f3_full_', 'unique full invocation')
    require(list(folder.parent.glob('*/report.json')) == [path], 'duplicate/stale full invocation')
    require(report['full_f3_acceptance'] is True and report['planned_only'] == [] and report['hardware_cpl3'] is False, 'full scope')
    require(type(expected_source_sha256) is dict and bool(expected_source_sha256), 'missing external source freeze')
    before = strict_json(folder/'source_freeze_before.json')
    require(before == strict_json(folder/'source_freeze_after.json') == report['source_sha256'] == expected_source_sha256, 'wrapper/external source mismatch')
    require(report['source_freeze_stable'] is True and type(report['source_input_count']) is int and report['source_input_count'] == len(before), 'source freeze/count')
    require(set(CANONICAL_SOURCES) <= before.keys(), 'missing full canonical sources')
    pin_tree(folder, report['frozen_bytes'])
    require(sha((folder/'driver.py').read_bytes()) == before['scripts/f3_full_guest.py'], 'full driver provenance')
    require(sha((folder/'validator.py').read_bytes()) == before['scripts/f3_full_evidence.py'], 'full validator provenance')
    drivers = report['drivers']
    require(type(drivers) is list and [d['component'] for d in drivers] == ['minimal','supplemental_prepare','supplemental_run'], 'driver order/completeness')
    for driver in drivers:
        require(type(driver['exit']) is int and driver['exit'] == 0, 'failed subordinate driver')
        require(driver['log'] == driver['component']+'.log' and driver['log'] in report['frozen_bytes'], 'driver log pin')
    child_paths = {}
    for component in ('minimal','supplemental'):
        children = list((folder/component).glob('*/report.json'))
        require(len(children) == 1, 'missing/ambiguous subordinate '+component)
        child = children[0].resolve()
        require(child.is_relative_to(folder/component) and report[component+'_report'] == child.relative_to(folder).as_posix(), 'subordinate invocation ownership')
        require(strict_json(child)['source_sha256'] == before, 'subordinate source mismatch')
        child_paths[component] = child
    # Commands bind the actual drivers and their exact output operands to this
    # invocation. Do not infer ownership from a matching basename or old JSON.
    commands = [d['command'] for d in drivers]
    for command in commands:
        require(type(command) is list and len(command) >= 4 and all(type(a) is str for a in command) and Path(command[0]).is_absolute() and command[1] == '-B', 'driver argv')
    scripts = Path(report['scripts_dir'])
    require(scripts == Path(__file__).resolve().parent, 'canonical scripts path')
    require(commands[0] == [commands[0][0],'-B',str(scripts/'f3_gdt_guest.py'),'--output-dir',str(folder/'minimal')], 'minimal command ownership')
    supplement_dir = child_paths['supplemental'].parent
    require(commands[1] == [commands[0][0],'-B',str(scripts/'f3_supplemental.py'),'prepare','--output-dir',str(supplement_dir)], 'prepare command ownership')
    require(commands[2] == [commands[0][0],'-B',str(scripts/'f3_supplemental.py'),'run','--prepared-dir',str(supplement_dir),'--parent-ready','--objdump',report['objdump']], 'run command ownership')
    require(Path(report['objdump']).is_absolute(), 'objdump path')
    first = minimal.validate(child_paths['minimal'], before)
    second = supplemental.validate(child_paths['supplemental'], before)
    require(first['full_f3_acceptance'] is False and first['planned_only'] == minimal.PLANNED and first['scenario_count'] == 10, 'minimal scope/count')
    require(second['full_f3_acceptance'] is False and second['guest_count'] == 8, 'supplemental scope/count')
    expected_rows = []
    child_reports = {path, *child_paths.values()}
    for component, names in (('minimal',minimal.REQUIRED),('supplemental',SUPPLEMENTAL_REQUIRED)):
        child_folder = child_paths[component].parent
        require({p for p in (folder/component).iterdir()} == {child_folder}, 'unowned component sibling')
        child_report = strict_json(child_paths[component])
        actual_files = {p.relative_to(child_folder).as_posix() for p in child_folder.rglob('*')
                        if p.is_file() and not p.relative_to(child_folder).as_posix().startswith('fixture/build/')
                        and p.relative_to(child_folder).as_posix() not in ('report.json','running.json','validation.json')}
        require(actual_files == set(child_report['frozen_bytes']), 'unfrozen subordinate artifact')
        for name in names:
            child = child_paths[component].parent/name/'guest_report.json'
            expected_rows.append({'name':name,'component':component,'report':child.relative_to(folder).as_posix()})
            child_reports.add(child)
    require(type(report['scenario_count']) is int and report['scenario_count'] == 18 and report['scenarios'] == expected_rows, 'exact eighteen rows; no missing/duplicate/substituted identities')
    require(set(folder.rglob('report.json')) | set(folder.rglob('guest_report.json')) == child_reports, 'unowned extra report')
    require({p.name for p in folder.iterdir()} == ROOT_FILES | {'report.json','minimal','supplemental'}, 'unowned full root artifact')
    pins = {}
    for result in (first,second):
        for name,digest in result['pins'].items():
            target = Path(name)
            require(target.is_absolute() and target.is_relative_to(folder) and name not in pins, 'duplicate/unowned subordinate pin')
            pins[name] = digest
    for name in ROOT_FILES:
        pins[str(folder/name)] = sha((folder/name).read_bytes())
    expected = {Path(p).relative_to(folder).as_posix():digest for p,digest in pins.items()}
    require(report['frozen_bytes'] == expected, 'full subordinate/root pins mismatch')
    # Recheck every returned pin after validators, including immutable driver
    # logs outside their pinned subtrees; root report joins the pin set last.
    pin_tree(folder, expected)
    pins[str(path)] = sha(path.read_bytes())
    return {'schema':'rosti.f3-full-evidence-validation.v1','overall':'PASS',
            'scenario_count':18,'full_f3_acceptance':True,'planned_only':[],
            'hardware_cpl3':False,'pins':pins,'limitations':second['limitations']}
