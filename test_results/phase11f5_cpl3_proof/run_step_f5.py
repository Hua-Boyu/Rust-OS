"""Capture an exact command, log, timestamp and actual subprocess status.
Same verified child-CWD semantics as test_results/phase11a2_continuation/run_step.py;
writes evidence under this task root only."""
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
name, cwd, expected, *command = sys.argv[1:]
log = ROOT / (name + '.log')
report = ROOT / (name + '.json')
if log.exists() or report.exists():
    raise SystemExit('refuse evidence overwrite: ' + name)
row = {'name': name, 'command': command, 'cwd': cwd,
       'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'status': 'RUNNING'}
report.write_text(json.dumps(row, indent=2) + '\n')
with log.open('wb') as output:
    result = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
text = log.read_text(errors='replace')
row.update(exit_code=result.returncode,
           ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
           log=str(log),
           totals=re.findall(r'test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored', text),
           status='EXPECTED' if result.returncode == int(expected) else 'UNEXPECTED')
report.write_text(json.dumps(row, indent=2) + '\n')
print(json.dumps(row, indent=2), flush=True)
print(text[-4500:], flush=True)
sys.exit(0 if row['status'] == 'EXPECTED' else 1)
