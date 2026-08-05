#!/usr/bin/env python3
"""Anthropic->OpenAI translator shim on :4102 (replaces LiteLLM for the
llmproxy lane, 2026-08-04). Sends NO Authorization header (llmproxy is
keyless-open, rejects wrong keys). Title side-requests answered locally.
Streams the response as one buffered burst of Anthropic SSE events."""
import http.server, json, os, socketserver, time, urllib.request, uuid

UP = 'https://llm.k.ezq.ch/v1/chat/completions'
LOGDIR = '/tmp/orch/shim-log'
os.makedirs(LOGDIR, exist_ok=True)

def _excerpt(x, n=400):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return s[:n] + ('…' if len(s) > n else '')

def log_exchange(payload, resp, wall, err=None):
    """One JSONL line per exchange + full snapshot of the latest one."""
    try:
        msgs = payload.get('messages', [])
        sys_len = sum(len(m.get('content') or '') for m in msgs if m.get('role') == 'system')
        last = msgs[-1] if msgs else {}
        rec = {'ts': time.strftime('%H:%M:%S'), 'wall_s': round(wall, 1),
               'n_msgs': len(msgs), 'sys_kb': round(sys_len / 1024, 1),
               'last_role': last.get('role'), 'last_msg': _excerpt(last.get('content') or '')}
        if err:
            rec['error'] = _excerpt(str(err), 600)
            with open(f'{LOGDIR}/error-{int(time.time())}.json', 'w') as f:
                json.dump({'request': payload, 'error': str(err)}, f, ensure_ascii=False)
        elif resp:
            m = (resp.get('choices') or [{}])[0].get('message', {})
            u = resp.get('usage') or {}
            rec.update({'prompt_tok': u.get('prompt_tokens'), 'compl_tok': u.get('completion_tokens'),
                        'reply': _excerpt(m.get('content') or ''),
                        'tool_calls': [{'name': tc['function']['name'],
                                        'args': _excerpt(tc['function'].get('arguments') or '', 300)}
                                       for tc in m.get('tool_calls') or []]})
        with open(f'{LOGDIR}/traffic.jsonl', 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        with open(f'{LOGDIR}/last-exchange.json', 'w') as f:
            json.dump({'request': payload, 'response': resp, 'error': err and str(err)}, f,
                      ensure_ascii=False, indent=1)
    except Exception:
        pass  # Beobachtung darf den Traffic nie brechen

def sanitize_schema(s):
    """llama-server compiles tool schemas to a GBNF grammar; exotic JSON-Schema
    keywords (anyOf/const/pattern/propertyNames/type-unions...) make it 400 with
    'failed to parse grammar'. Keep only the grammar-safe subset."""
    if not isinstance(s, dict):
        return {'type': 'object', 'properties': {}}
    if 'anyOf' in s and isinstance(s['anyOf'], list) and s['anyOf']:
        return sanitize_schema(s['anyOf'][0])
    out = {}
    t = s.get('type')
    if isinstance(t, list) and t:
        t = t[0]
    if isinstance(t, str):
        out['type'] = t
    if isinstance(s.get('description'), str):
        out['description'] = s['description'][:1000]
    if isinstance(s.get('enum'), list):
        out['enum'] = s['enum']
    if out.get('type') == 'object' or 'properties' in s:
        out['type'] = 'object'
        props = s.get('properties') or {}
        out['properties'] = {k: sanitize_schema(v) for k, v in props.items()}
        req = [r for r in s.get('required') or [] if r in props]
        if req:
            out['required'] = req
    elif out.get('type') == 'array':
        out['items'] = sanitize_schema(s.get('items') or {})
    elif 'type' not in out:
        out = {'type': 'string'}
    return out

def a2o(d):
    msgs = []
    sys_ = d.get('system')
    if isinstance(sys_, list):
        sys_ = '\n\n'.join(b.get('text', '') for b in sys_ if isinstance(b, dict))
    if sys_:
        msgs.append({'role': 'system', 'content': sys_})
    for m in d.get('messages', []):
        c = m.get('content')
        if isinstance(c, str):
            msgs.append({'role': m['role'], 'content': c}); continue
        texts, calls, results = [], [], []
        for b in c or []:
            t = b.get('type')
            if t == 'text': texts.append(b.get('text', ''))
            elif t == 'tool_use':
                calls.append({'id': b['id'], 'type': 'function', 'function': {
                    'name': b['name'], 'arguments': json.dumps(b.get('input', {}))}})
            elif t == 'tool_result':
                rc = b.get('content')
                if isinstance(rc, list):
                    rc = '\n'.join(x.get('text', '') for x in rc if isinstance(x, dict))
                results.append({'role': 'tool', 'tool_call_id': b.get('tool_use_id', ''), 'content': str(rc or '')})
        if m['role'] == 'assistant':
            am = {'role': 'assistant', 'content': '\n'.join(texts) or None}
            if calls: am['tool_calls'] = calls
            msgs.append(am)
        else:
            if texts: msgs.append({'role': 'user', 'content': '\n'.join(texts)})
            msgs.extend(results)
    model = d.get('model') or ''
    if model.startswith('claude'):
        # Interactive claude sessions pointed at the shim send their normal
        # model ids (claude-fable-5 etc.) which llmproxy 404s (seen
        # 2026-08-05). Alias every claude-* id to the local lane's model.
        model = os.environ.get('SHIM_CLAUDE_ALIAS', 'gpt-oss:120b')
    out = {'model': model, 'messages': msgs,
           'max_tokens': min(int(d.get('max_tokens') or 4096), 16000)}
    tools = [{'type': 'function', 'function': {'name': t['name'],
              'description': t.get('description', ''), 'parameters': sanitize_schema(t.get('input_schema', {}))}}
             for t in d.get('tools', [])]
    if tools: out['tools'] = tools
    return out

def sse(w, ev, data):
    w.write(('event: %s\ndata: %s\n\n' % (ev, json.dumps(data))).encode())

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_POST(self):
        n = int(self.headers.get('content-length', 0))
        d = json.loads(self.rfile.read(n) or b'{}')
        txt = json.dumps(d.get('messages', []))[-3000:]
        if (d.get('max_tokens') or 9e9) <= 1024 and 'title' in txt.lower() and (
                'conversation' in txt.lower() or 'concise' in txt.lower() or '5-10 word' in txt.lower()):
            body = json.dumps({'id': 'msg_shim', 'type': 'message', 'role': 'assistant',
                'model': d.get('model'), 'stop_reason': 'end_turn', 'stop_sequence': None,
                'usage': {'input_tokens': 1, 'output_tokens': 1},
                'content': [{'type': 'text', 'text': 'Handler ticket work'}]}).encode()
            self.send_response(200); self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body))); self.end_headers()
            self.wfile.write(body); return
        payload = a2o(d)
        t0 = time.time()
        try:
            req = urllib.request.Request(UP, json.dumps(payload).encode(),
                                         {'content-type': 'application/json'})
            r = json.load(urllib.request.urlopen(req, timeout=3000))
        except urllib.error.HTTPError as e:
            body = e.read()
            log_exchange(payload, None, time.time() - t0, err=f'HTTP {e.code}: {body[:400]}')
            self.send_response(e.code); self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body))); self.end_headers()
            self.wfile.write(body); return
        except Exception as e:
            log_exchange(payload, None, time.time() - t0, err=e)
            body = json.dumps({'error': str(e)}).encode()
            self.send_response(502); self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body))); self.end_headers()
            self.wfile.write(body); return
        log_exchange(payload, r, time.time() - t0)
        ch = (r.get('choices') or [{}])[0]
        m = ch.get('message', {})
        blocks = []
        if m.get('content'):
            blocks.append({'type': 'text', 'text': m['content']})
        for tc in m.get('tool_calls') or []:
            try: args = json.loads(tc['function'].get('arguments') or '{}')
            except Exception: args = {}
            blocks.append({'type': 'tool_use', 'id': tc.get('id') or 'call_' + uuid.uuid4().hex[:12],
                           'name': tc['function']['name'], 'input': args})
        stop = 'tool_use' if m.get('tool_calls') else 'end_turn'
        u = r.get('usage') or {}
        usage = {'input_tokens': u.get('prompt_tokens', 0), 'output_tokens': u.get('completion_tokens', 0)}
        mid = 'msg_' + uuid.uuid4().hex[:16]
        self.send_response(200)
        self.send_header('content-type', 'text/event-stream')
        self.send_header('cache-control', 'no-cache')
        self.send_header('connection', 'close')
        self.end_headers()
        w = self.wfile
        sse(w, 'message_start', {'type': 'message_start', 'message': {
            'id': mid, 'type': 'message', 'role': 'assistant', 'model': d.get('model'),
            'content': [], 'stop_reason': None, 'stop_sequence': None,
            'usage': {'input_tokens': usage['input_tokens'], 'output_tokens': 0}}})
        for i, b in enumerate(blocks):
            if b['type'] == 'text':
                sse(w, 'content_block_start', {'type': 'content_block_start', 'index': i,
                    'content_block': {'type': 'text', 'text': ''}})
                sse(w, 'content_block_delta', {'type': 'content_block_delta', 'index': i,
                    'delta': {'type': 'text_delta', 'text': b['text']}})
            else:
                sse(w, 'content_block_start', {'type': 'content_block_start', 'index': i,
                    'content_block': {'type': 'tool_use', 'id': b['id'], 'name': b['name'], 'input': {}}})
                sse(w, 'content_block_delta', {'type': 'content_block_delta', 'index': i,
                    'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(b['input'])}})
            sse(w, 'content_block_stop', {'type': 'content_block_stop', 'index': i})
        sse(w, 'message_delta', {'type': 'message_delta',
            'delta': {'stop_reason': stop, 'stop_sequence': None},
            'usage': {'output_tokens': usage['output_tokens']}})
        sse(w, 'message_stop', {'type': 'message_stop'})
    def log_message(self, *a): pass

class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

S(('127.0.0.1', 4102), H).serve_forever()
