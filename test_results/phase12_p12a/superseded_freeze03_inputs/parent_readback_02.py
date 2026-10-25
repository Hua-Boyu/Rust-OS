"""Read-only P12-A parent verifier. External index owns manifest raw digest."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / 'test_results/phase12_p12a'
sys.path.insert(0, str(TASK))

def main():
    if sys.flags.optimize:
        raise RuntimeError('optimized execution refused')
    import integrity_02 as integrity
    index_path = Path(sys.argv[1])
    index = json.loads(index_path.read_bytes())
    manifest = ROOT / index['manifest_path']
    integrity.verify_manifest(manifest, index['manifest_sha256'])
    integrity.verify_freeze(TASK / 'source_freeze_03.json')
    predecessor = integrity.verify_predecessor()
    protected = integrity.verify_protected()
    processes = integrity.observe_processes()
    print(json.dumps({'overall': 'PASS', 'manifest_path': index['manifest_path'], 'manifest_sha256': index['manifest_sha256'], 'source_before_equals_after': True, 'predecessor': predecessor, 'protected': protected, 'processes': processes}, indent=2))

if __name__ == '__main__':
    main()
