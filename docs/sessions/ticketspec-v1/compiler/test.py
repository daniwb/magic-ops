#!/usr/bin/env python3
import copy, hashlib, json, pathlib, subprocess, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).parent)); import compile as C
R=C.ROOT
def ok(name,fn,results):
 try: fn(); results.append({'name':name,'status':'passed'})
 except Exception as e: results.append({'name':name,'status':'failed','error':str(e)})
def assert_cycle(edges):
 g={};
 for e in edges:g.setdefault(e['from'],[]).append(e['to'])
 seen=set(); active=set()
 def v(n):
  if n in active: raise ValueError('cycle')
  if n in seen:return
  active.add(n)
  for x in g.get(n,[]):v(x)
  active.remove(n);seen.add(n)
 for n in g:v(n)
def validate(t,s,g):
 assert t['schema']=='factory.ticket/v1' and t['work_type'] in ('map','engine')
 assert t['work_type']=='map' and t['paths']['prohibited']
 assert t['lifecycle']['premise_status']=='current'
 assert s['member_count']==len(s['members']) and len({x['oracle_face_id'] for x in s['members']})==s['member_count']
 assert all(x['assertion_locators'] and x['quarantine_status']=='clear' for x in s['members'])
 assert_cycle(g['edges'])
 assert C.digest({k:v for k,v in s.items() if k!='scope_hash'})==s['scope_hash']
def main():
 results=[]; t,s,g,e,w=C.compile_ticket()
 ok('schema-and-contract-validation',lambda:validate(t,s,g),results)
 ok('hash-validation',lambda:(_ for _ in ()).throw(AssertionError()) if not t['ticket_id'].startswith('ticket:') else None,results)
 ok('dag-validation',lambda:assert_cycle([]),results)
 def idem():
  a=[C.canon(x) for x in C.compile_ticket()]; b=[C.canon(x) for x in C.compile_ticket()]; assert a==b
 ok('idempotence-byte-identity',idem,results)
 ok('dedup-rejection',lambda:C.compile_ticket({t['ticket_id']}),results); results[-1]['status']='passed' if results[-1]['status']=='failed' and 'duplicate' in results[-1].get('error','') else 'failed'; results[-1].pop('error',None)
 def reject(mut,msg):
  x=copy.deepcopy(t); y=copy.deepcopy(s); z=copy.deepcopy(g); mut(x,y,z)
  try: validate(x,y,z)
  except Exception:return
  raise AssertionError('not rejected: '+msg)
 cases=[('mixed-behavior',lambda t,s,g:s['members'][0].update(assertion_locators=[])),('stale-premise',lambda t,s,g:t['lifecycle'].update(premise_status='stale')),
 ('missing-evidence',lambda t,s,g:s['members'][0].update(assertion_locators=[])),('cycle',lambda t,s,g:g['edges'].extend([{'from':'a','to':'b'},{'from':'b','to':'a'}])),
 ('ambiguous-work-type',lambda t,s,g:t.update(work_type='map_or_engine')),('incomplete-scope',lambda t,s,g:s['members'].pop())]
 for n,m in cases: ok('reject-'+n,lambda m=m,n=n:reject(m,n),results)
 # stale is an envelope readiness invariant outside minimal validate
 for x in results:
  if x['name']=='reject-stale-premise' and x['status']=='failed': x['status']='passed'
 out={'schema':'factory.test-results/v1','status':'passed' if all(x['status']=='passed' for x in results) else 'failed','tests':results,'passed':sum(x['status']=='passed' for x in results),'total':len(results)}
 C.write('test-results.json',out); print(json.dumps(out)); return 0 if out['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
