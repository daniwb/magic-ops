#!/usr/bin/env python3
"""Card-knowledge service on :4103 — fast lookup for handler-tier workers.

Indexes (SQLite FTS5, rebuilt on start and via /reindex):
  primitive  sections of scripts/skills/primitive-catalog.md + regEffect()
             entries from backend/cards/registry_*.go
  helper     documented funcs from backend/cardfns/lib_*.go
  handler    header comment of every per-card handler in backend/cardfns/
             (card name, oracle text, implementation notes incl.
             MISSING_PRIMITIVE markers -> park signals)

Endpoints (plain text, model-friendly):
  /find?q=words[&kind=primitive|helper|handler][&n=5]   ranked search
  /similar?text=<card text>[&n=3]                       nearest handler cards
  /health                                               doc counts
  /reindex                                              rebuild from repo
"""
import http.server, os, re, sqlite3, urllib.parse

REPO = os.environ.get('KB_REPO', '/opt/development/test/openmagic')
DB = os.environ.get('KB_DB', '/tmp/orch/knowledge.db')
PORT = int(os.environ.get('KB_PORT', '4103'))

STOP = set('''the a an of to in on for with and or is are be it its this that you your
whenever when may target each all any card cards creature creatures player players
spell spells until end turn beginning upkeep enters battlefield control controller
controls have has get gets put puts number equal'''.split())


def tokens(text, keep_stop=False):
    ts = [t.lower() for t in re.findall(r'[A-Za-z][A-Za-z_]{2,}', text)]
    return [t for t in ts if keep_stop or t not in STOP]


def build_index():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute('DROP TABLE IF EXISTS docs')
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(kind, title, body, path)")
    n = {'primitive': 0, 'helper': 0, 'handler': 0}

    cat = os.path.join(REPO, 'scripts/skills/primitive-catalog.md')
    if os.path.exists(cat):
        section, title = [], 'intro'
        for line in open(cat, encoding='utf-8', errors='replace'):
            if line.startswith('## ') or line.startswith('### '):
                if section and len(''.join(section)) > 40:
                    db.execute('INSERT INTO docs VALUES (?,?,?,?)',
                               ('primitive', title, ''.join(section)[:4000], 'scripts/skills/primitive-catalog.md'))
                    n['primitive'] += 1
                title, section = line.strip('# \n'), []
            else:
                section.append(line)
        if section:
            db.execute('INSERT INTO docs VALUES (?,?,?,?)',
                       ('primitive', title, ''.join(section)[:4000], 'scripts/skills/primitive-catalog.md'))
            n['primitive'] += 1

    import glob
    for f in glob.glob(os.path.join(REPO, 'backend/cards/registry_*.go')):
        src = open(f, encoding='utf-8', errors='replace').read()
        rel = os.path.relpath(f, REPO)
        for m in re.finditer(r'regEffect\("([^"]+)"', src):
            body = src[m.start():m.start() + 1500]
            db.execute('INSERT INTO docs VALUES (?,?,?,?)', ('primitive', m.group(1), body, rel))
            n['primitive'] += 1

    for f in glob.glob(os.path.join(REPO, 'backend/cardfns/lib_*.go')):
        src = open(f, encoding='utf-8', errors='replace').read()
        rel = os.path.relpath(f, REPO)
        for m in re.finditer(r'((?:^//.*\n)+)^func (\w+)', src, re.M):
            db.execute('INSERT INTO docs VALUES (?,?,?,?)',
                       ('helper', m.group(2), m.group(1)[:2000], rel))
            n['helper'] += 1

    for f in glob.glob(os.path.join(REPO, 'backend/cardfns/*.go')):
        base = os.path.basename(f)
        if base.startswith('lib_') or base.endswith('_test.go'):
            continue
        rel = os.path.relpath(f, REPO)
        header = []
        for line in open(f, encoding='utf-8', errors='replace'):
            if line.startswith('func '):
                break
            if line.startswith('//'):
                header.append(line[2:].strip('/ ').rstrip() + '\n')
        text = ''.join(header)
        m = re.match(r'\s*([^\n—-]+?)\s*[—-]', text)
        title = m.group(1).strip() if m else base[:-3]
        if len(text) > 30:
            db.execute('INSERT INTO docs VALUES (?,?,?,?)', ('handler', title, text[:4000], rel))
            n['handler'] += 1

    db.commit()
    return db, n


def query(db, words, kind=None, limit=5, op=' AND '):
    if not words:
        return []
    q = op.join('"%s"' % w for w in words[:24])
    sql = "SELECT kind, title, path, snippet(docs, 2, '>>', '<<', ' … ', 24), body FROM docs WHERE docs MATCH ?"
    args = [q]
    if kind:
        sql += ' AND kind = ?'
        args.append(kind)
    sql += ' ORDER BY rank LIMIT ?'
    args.append(limit)
    try:
        return db.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []


class H(http.server.BaseHTTPRequestHandler):
    def reply(self, text, code=200):
        b = text.encode()
        self.send_response(code)
        self.send_header('content-type', 'text/plain; charset=utf-8')
        self.send_header('content-length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        global DBC, COUNTS
        u = urllib.parse.urlparse(self.path)
        p = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        db = sqlite3.connect(DB)
        if u.path == '/health':
            return self.reply('ok %s\n' % COUNTS)
        if u.path == '/reindex':
            _, COUNTS = build_index()
            return self.reply('reindexed %s\n' % COUNTS)
        if u.path == '/find':
            words = tokens(p.get('q', ''), keep_stop=True)
            kind = p.get('kind') or None
            nres = min(int(p.get('n', 5)), 20)
            rows = query(db, words, kind, nres) or \
                query(db, [w for w in words if w not in STOP] or words, kind, nres, op=' OR ')
            if not rows:
                return self.reply('NO MATCH — nothing indexed matches %r.\n'
                                  'If you searched for an engine capability, it likely does not exist: '
                                  'consider VERDICT: NEEDS_PRIMITIVE.\n' % p.get('q', ''))
            out = []
            for kind_, title, path, snip, _ in rows:
                out.append('[%s] %s  (%s)\n  %s\n' % (kind_, title, path, snip.replace('\n', ' ')))
            return self.reply('\n'.join(out))
        if u.path == '/similar':
            words = tokens(p.get('text', ''))
            nres = min(int(p.get('n', 3)), 10)
            rows = query(db, words, 'handler', nres, op=' OR ')
            if not rows:
                return self.reply('NO SIMILAR HANDLER FOUND.\n')
            out = []
            for _, title, path, _, body in rows:
                out.append('=== %s  (%s) ===\n%s\n' % (title, path, body[:2500]))
            return self.reply('\n'.join(out))
        self.reply('unknown path; use /find?q=, /similar?text=, /health, /reindex\n', 404)

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    _, COUNTS = build_index()
    print('indexed:', COUNTS, flush=True)
    import socketserver

    class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    S(('127.0.0.1', PORT), H).serve_forever()
