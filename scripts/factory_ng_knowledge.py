"""The factory's HTTP knowledge client and per-attempt lookup trace."""
import json
import os
import re
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from factory_ng_symbols import resolve, render

CONTEXT = ContextVar('knowledge_trace_context',default={})


@contextmanager
def lookup_context(values):
    token=CONTEXT.set(values)
    try: yield
    finally: CONTEXT.reset(token)


def setting(name, default=''):
    return CONTEXT.get().get(name,os.environ.get(name,default))


def trace(event):
    path = setting('KB_TRACE_FILE')
    if path:
        event = dict(event, recorded_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                     ticket=setting('KB_TICKET'), attempt=setting('KB_ATTEMPT'))
        with open(path,'a') as handle:
            handle.write(json.dumps(event,sort_keys=True)+'\n')


def request(endpoint, params, caller, base=None):
    params = dict(params, caller=caller, ticket=setting('KB_TICKET'),
                  attempt=setting('KB_ATTEMPT'), request_id=uuid.uuid4().hex)
    base = base or os.environ.get('KB_URL','http://127.0.0.1:4103')
    try:
        with urllib.request.urlopen(base+endpoint+'?'+urllib.parse.urlencode(params),timeout=15) as response:
            body = response.read().decode()
        result = json.loads(body) if endpoint == '/search' else {'status':'ok','text':body}
        if endpoint == '/search' and (not isinstance(result,dict) or result.get('schema') != 'factory.knowledge-search/v1'):
            raise ValueError('unsupported knowledge service response')
    except Exception as exc:
        result = {'status':'service_error','error':str(exc),'candidates':[]}
    event = dict(endpoint=endpoint, caller=caller, request=params, response=result)
    trace(event)
    result['request_id'] = params['request_id']
    result['request'] = params
    return result


def search(query, caller, kind=None, limit=5, base=None, fallback=False):
    return request('/search', {'q':query,'kind':kind or '', 'n':limit,
                              'fallback':'1' if fallback else '0'},caller,base)


def capability_queries(capability):
    """Bounded discovery of a contract's parts, not only its invented label.

    Exact identifiers come from the requirement itself. The operation query
    is explicitly broader and never claims to satisfy the whole requirement.
    """
    key = capability.get('key', '')
    spec = capability.get('specification', capability)
    required = spec.get('required_behavior', '')
    if isinstance(required, list): required = ' '.join(required)
    named = re.findall(r'\b(?:[a-z]+[A-Z][A-Za-z0-9]*|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b', required)
    named += re.findall(r'`([A-Za-z_]\w*(?:\.\w+)*)`', required)
    queries = [(key, 'capability_label')] if key else []
    queries += [(name, 'requirement_symbol') for name in dict.fromkeys(named)][:3]
    parts = [p for p in key.split('_') if p]
    if parts:
        operation = '_'.join(parts[:2]) if parts[0] in ('put', 'grant', 'remove') else parts[0]
        if operation not in ('spell', 'auto', 'target', 'filter'):
            queries.append((operation, 'operation_only'))
    seen = set()
    return [(q, role) for q, role in queries if q and not (q in seen or seen.add(q))][:5]


def discover_capability(capability, caller, limit=5, base=None):
    """All discovery stays behind the service; every query remains visible."""
    lookups, groups = [], []
    for query, role in capability_queries(capability):
        result = search(query, caller + ':' + role, kind='engine', limit=limit, base=base)
        result['discovery_role'] = role
        lookups.append(result)
        if result['status'] == 'service_error': break
        if role == 'capability_label' and result['status'] == 'not_found':
            result = search(query, caller + ':label_fallback', kind='engine', limit=limit, base=base, fallback=True)
            result['discovery_role'] = 'label_fallback'
            lookups.append(result)
            if result['status'] == 'service_error': break
        groups.append([dict(candidate, discovery_role=result['discovery_role'], request_id=result['request_id'])
                       for candidate in result.get('candidates', []) if candidate.get('symbol_id')])
    # Reserve room for each query: a noisy first result must not crowd every
    # explicitly named implementation out of the packet again.
    candidates, seen = [], set()
    for index in range(limit):
        for group in groups:
            if index < len(group) and group[index]['symbol_id'] not in seen:
                seen.add(group[index]['symbol_id'])
                candidates.append(group[index])
    error = next((r for r in lookups if r['status'] == 'service_error'), None)
    result = {'status': 'service_error' if error else 'found' if candidates else 'not_found',
              'semantic_coverage': 'unverified', 'lookups': lookups, 'candidates': candidates[:limit]}
    if error: result['error'] = error['error']
    trace({'caller': caller, 'capability_discovery': result})
    return result


def capability_assessment(reply):
    """Retain a worker's claim as telemetry; it never replaces a gate result."""
    match = re.search(r'^CAPABILITY_ASSESSMENT:\s*(\{[^\n]*\})\s*$', reply, re.M)
    if not match: return None
    try: value = json.loads(match[1])
    except ValueError: return {'status': 'invalid', 'raw': match[1][:2000]}
    if (value.get('classification') not in ('reuse', 'connection', 'engine_gap', 'insufficient_evidence')
            or not isinstance(value.get('existing_symbols'), list)
            or not all(isinstance(s, str) for s in value['existing_symbols'])
            or not isinstance(value.get('remaining_gap'), str)
            or not isinstance(value.get('verification'), str)):
        return {'status': 'invalid', 'raw': match[1][:2000]}
    return dict(value, status='worker_claim_requires_gates')


def describe(result):
    if result['status'] == 'service_error':
        return 'KNOWLEDGE SERVICE ERROR: '+result['error']+'; this is not evidence of a missing capability.'
    lines = ['Lookup %s: %s; strategy=%s; indexed revision=%s' % (
        result.get('request_id',''),result['status'],result.get('strategy',''),result.get('indexed_revision','unavailable'))]
    for row in result.get('candidates',[]):
        lines.append('[%s] %s (%s) — %s' % (row['kind'],row.get('qualified') or row['title'],row['path'],row.get('description','')))
        if row.get('symbol_id'): lines.append('  symbol_id: '+row['symbol_id'])
    if result.get('index_stale'):
        lines.append('Index is behind canonical source; verify candidates locally. '+result.get('refresh_error',''))
    if not result.get('candidates'):
        lines.append('No candidate found by this search. This does not establish a missing engine capability.')
    return '\n'.join(lines)


def resolve_candidate(repo, candidate, request_id='', caller='source-resolver', budget=180):
    result = resolve(repo,candidate,budget)
    trace({'caller':caller,'request_id':request_id,'selected_symbol':candidate,
           'resolution':result})
    return result


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('command'); p.add_argument('words',nargs='*')
    args=p.parse_args(); query=' '.join(args.words)
    if args.command == 'find' or args.command.startswith('find-'):
        kind=args.command[5:] if args.command.startswith('find-') else None
        print(describe(search(query,'worker-cli',kind,8)))
    elif args.command == 'source':
        path,sep,qualified=query.partition('::')
        if not sep: p.error('source expects path::qualified-symbol from search')
        print(render(resolve_candidate(Path.cwd(),{'path':path,'symbol_id':query},caller='worker-cli')))
    elif args.command in ('caps','similar','toc'):
        params={'name':query} if args.command == 'caps' else {'text':query,'n':3}
        result=request('/'+args.command,params,'worker-cli')
        print(result.get('text') or describe(result))
    else: p.error('unknown knowledge command')


if __name__ == '__main__': main()
