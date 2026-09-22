"""Read-only closing audit. Refuses to close before the observation endpoint."""
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
read = lambda path: json.loads(Path(path).read_text())
window = read(HERE / "window.json")
parse = lambda value: dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
now = dt.datetime.now(dt.timezone.utc)
assert now >= parse(window["end"]), "Observation window remains open"
rows = [json.loads(x) for x in (HERE / "occupancy.jsonl").read_text().splitlines()]
assert parse(rows[-1]["at"]) >= parse(window["end"]), "Observer has not recorded the endpoint"
measured = [r for r in rows if parse(r["at"]) >= parse(window["stability_start"]) and "occupied" in r]
status = json.loads(subprocess.check_output(["python3", str(HERE / "status.py")], text=True))
jobs = read(ROOT / "state/factory-ng-jobs.json")["jobs"]
completed = {k:j for k,j in jobs.items() if not j.get("superseded_by") and j.get("state")=="completed" and j.get("finished_at", "") >= window["start"]}
policy = read(ROOT / "config/factory-ng-policy.json")
previous = read(HERE / "policy-audit-2242.json")
workers = read(ROOT / "config/factory-ng-workers.json")["workers"]
codex = [w for w in workers if w["id"] in window["workers"]]
implementation = read(HERE / "implementation-hashes.json")
hashes = {path: "sha256:"+hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected for path,expected in implementation.items()}
controller_pid = 3396268
controller = {"pid":controller_pid, "argv":Path(f"/proc/{controller_pid}/cmdline").read_bytes().replace(bytes([0]),b" ").decode(), "affinity":sorted(os.sched_getaffinity(controller_pid)), "nice":os.getpriority(os.PRIO_PROCESS,controller_pid)}
http = {}
for endpoint in ["dashboard", "factory-ng/status", "factory-ng/workers"]:
    with urllib.request.urlopen("http://localhost:9999/"+endpoint,timeout=20) as response:
        payload=response.read()
        http[endpoint]={"status":response.status,"bytes":len(payload)}
health=subprocess.run(["bash","scripts/session-health-check.sh"],cwd=ROOT,text=True,capture_output=True)
(HERE/"final-health-check.txt").write_text(health.stdout+health.stderr)
per_worker={}
for w in window["workers"]:
    live=[r for r in measured if any(j.get("alive") for j in r["leases"][w])]
    per_worker[w]={"live_samples":len(live),"samples":len(measured),"sampled_lease_occupancy_pct":round(100*len(live)/len(measured),1),"distinct_live_tickets":len({j["ticket"] for r in live for j in r["leases"][w] if j.get("alive")}),"completed_since_request":sum(j.get("worker")==w for j in completed.values())}
result={"at":now.isoformat(),"window":window,"observed_until":rows[-1]["at"],"window_elapsed":True,"continuous_four_worker_occupancy":False,"occupancy_note":"Actual non-zombie model/individual-repair leases sampled about every 30 seconds. Excludes model-free verification batches. Leases include harness processing, not only model inference. Idle gaps remain visible.","occupancy_distribution":dict(collections.Counter(r["occupied"] for r in measured)),"per_worker":per_worker,"current":status,"controller":controller,"checks":{"policy_unchanged_since_2242":policy==previous["policy"],"codex_workers_unchanged_since_2242":codex==previous["codex_workers"],"claude_enabled":all(w.get("enabled") for w in workers if w["id"] in ["claude","claude-2"]),"controller_resources":controller["affinity"]==[6,11,12,19] and controller["nice"]==10,"all_implementation_hashes_match":all(hashes.values()),"health_check_exit_zero":health.returncode==0},"implementation_hashes":hashes,"http":http,"remote":read(ROOT/"state/factory-ng-remote-status.json"),"watchdog":read(ROOT/"state/factory-ng-watchdog.json"),"cache_maintenance":read(ROOT/"state/go-cache-maintenance.json"),"completed_by_worker":dict(collections.Counter(j.get("worker","unattributed") for j in completed.values())),"candidate_integration_failures":{k:j.get("reason") for k,j in jobs.items() if not j.get("superseded_by") and j.get("state")=="integration_failed"}}
(HERE/"final-audit.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:result[k] for k in ["at","observed_until","occupancy_distribution","per_worker","checks","completed_by_worker"]},indent=2))
print(health.stdout)
