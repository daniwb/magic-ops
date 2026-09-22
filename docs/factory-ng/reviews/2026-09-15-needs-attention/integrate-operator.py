"""Wait briefly for the normal integrator's scoped lock; retain each result."""
import json,subprocess,sys,time
from pathlib import Path
ops=Path('/opt/development/magic-ops');review=Path(__file__).resolve().parent/sys.argv[1]
ticket=json.loads((review/'ticket.json').read_text())
command=[sys.executable,str(ops/'scripts/factory-ng-integrate.py'),'--receipt',(review/'receipt.txt').read_text().strip()]
for parent in ticket['parents']:command+=['--parent',parent]
for attempt in range(60):
 result=subprocess.run(command,cwd=ops,text=True,capture_output=True)
 with (review/'integration-attempts.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})+'\n')
 (review/'integration.log').write_text(result.stdout+result.stderr)
 if result.returncode!=75:
  print(result.stdout+result.stderr,flush=True);sys.exit(result.returncode)
 time.sleep(10)
raise SystemExit('normal integration lock remained busy for ten minutes; accepted correction remains pending')
