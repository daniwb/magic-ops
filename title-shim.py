#!/usr/bin/env python3
"""Tiny Anthropic-API shim on :4102 in front of LiteLLM (:4100).

Claude Code fires a hidden conversation-title side-request alongside the main
run. On the single-slot 395+ server the responses raced and the TITLE answer
came back as the worker's main result (turns=1 no-ops, 2026-08-03). The shim
answers anything title-shaped instantly and locally; real requests stream
through to LiteLLM untouched.
"""
import http.server, json, socketserver, urllib.request

UP = 'http://127.0.0.1:4100'

def is_title_request(d):
    try:
        if (d.get('max_tokens') or 99999) > 1024:
            return False
        txt = json.dumps(d.get('messages', []))[-4000:] + json.dumps(d.get('system', ''))[:2000]
        return ('title' in txt.lower() and ('conversation' in txt.lower() or 'summariz' in txt.lower() or '5-10 word' in txt.lower() or 'concise' in txt.lower()))
    except Exception:
        return False

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_POST(self):
        n = int(self.headers.get('content-length', 0))
        body = self.rfile.read(n)
        try:
            d = json.loads(body)
        except Exception:
            d = {}
        if self.path.startswith('/v1/messages') and is_title_request(d):
            resp = json.dumps({"id": "msg_shim_title", "type": "message", "role": "assistant",
                "model": d.get('model', 'shim'), "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": [{"type": "text", "text": "Handler ticket work"}]}).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return
        req = urllib.request.Request(UP + self.path, body,
            {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length')})
        try:
            up = urllib.request.urlopen(req, timeout=3000)
            self.send_response(up.status)
            hop = ('transfer-encoding', 'connection', 'content-length')
            data = up.read()
            for k, v in up.headers.items():
                if k.lower() not in hop:
                    self.send_header(k, v)
            self.send_header('content-length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    def log_message(self, *a):
        pass

class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

S(('127.0.0.1', 4102), H).serve_forever()
