#!/usr/bin/env python3
"""Anthropic->OpenAI translator shim on :4102 (replaces LiteLLM for the
llmproxy lane, 2026-08-04). Sends NO Authorization header (llmproxy is
keyless-open, rejects wrong keys). Title side-requests answered locally.
Streams the response as one buffered burst of Anthropic SSE events."""
import http.server, json, socketserver, urllib.request, uuid

UP = 'https://llm.k.ezq.ch/v1/chat/completions'

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
    out = {'model': d.get('model'), 'messages': msgs,
           'max_tokens': min(int(d.get('max_tokens') or 4096), 16000)}
    tools = [{'type': 'function', 'function': {'name': t['name'],
              'description': t.get('description', ''), 'parameters': t.get('input_schema', {})}}
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
        try:
            req = urllib.request.Request(UP, json.dumps(a2o(d)).encode(),
                                         {'content-type': 'application/json'})
            r = json.load(urllib.request.urlopen(req, timeout=3000))
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code); self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(body))); self.end_headers()
            self.wfile.write(body); return
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
