from pathlib import Path
import sqlite3,json,collections
out=Path(__file__).resolve().parent;root=Path('/tmp/goose-factory-staged-corrected')
c=sqlite3.connect(root/'data/sessions/sessions.db');c.row_factory=sqlite3.Row
results=[]
for s in c.execute('select * from sessions'):
 usages=[dict(x) for x in c.execute('select * from usage_ledger where session_id=?',(s['id'],))]
 row={k:s[k] for k in ['id','name','working_dir','created_at','updated_at','accumulated_input_tokens','accumulated_output_tokens','accumulated_total_tokens','accumulated_cache_read_tokens','accumulated_cache_write_tokens']};row['usage_ledger']=usages;results.append(row)
(out/'usage.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
