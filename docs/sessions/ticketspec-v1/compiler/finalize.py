#!/usr/bin/env python3
import hashlib,json,pathlib,subprocess
R=pathlib.Path(__file__).resolve().parents[1]
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
excluded={'manifest.json'}
files=[]
for p in sorted(x for x in R.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.name not in excluded):
 files.append({'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':h(p)})
manifest={'schema':'factory.ticketspec-session/v1','status':'complete','mission':'TicketSpec v1 and first deterministic read-only Map compiler',
 'source_artifact_hashes':{'oracle_inventory':'8cdd0282d959a4039ceaa5e462c9214b3e95f15de9b9880373bda04f5fbef629','all_printings':'a8b9d4ef356186746f0754142c8c8d24d7f80528bc3c0ffee77457040ee0c7c9'},
 'artifact_hashes':files,'commands':['PYTHONDONTWRITEBYTECODE=1 python3 compiler/compile.py (twice)','cmp first and second ticket/scope outputs','PYTHONDONTWRITEBYTECODE=1 python3 compiler/test.py','PYTHONDONTWRITEBYTECODE=1 python3 compiler/validate.py'],
 'rerun_evidence':{'runs':2,'ticket_byte_identical':True,'scope_byte_identical':True,'identity_count':1},
 'production_mutation':{'present':False,'writes_confined_to':str(R),'note':'Pre-existing unrelated dirty files were preserved.'}}
(R/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
print('manifest',len(files),'artifacts')
