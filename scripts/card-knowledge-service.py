#!/usr/bin/env python3
"""Card-knowledge service on :4103 — fast lookup for handler-tier workers.

Indexes (SQLite FTS5, rebuilt on start and via /reindex):
  primitive  sections of scripts/skills/primitive-catalog.md + regEffect()
             entries from backend/cards/registry_*.go
  helper     documented funcs from backend/cardfns/lib_*.go
  engine     parsed functions, types and string case labels from backend/game/*.go
  handler    header comment of every per-card handler in backend/cardfns/
             (card name, oracle text, implementation notes incl.
             MISSING_PRIMITIVE markers -> park signals)

Endpoints (plain text, model-friendly):
  /search?q=words[&kind=engine][&fallback=1]          structured symbol discovery
  /find?q=words[&kind=primitive|helper|handler][&n=5]   ranked search
  /similar?text=<card text>[&n=3]                       nearest handler cards
  /health                                               doc counts
  /reindex                                              rebuild from repo
  /caps?name=<event_or_case>                            engine-readiness check
             (exact match against game/events.go EventType constants and
             converter case labels; a miss is not proof of missing behavior)
"""
import http.server, os, re, sqlite3, threading, time, urllib.parse, json, tempfile, uuid
from factory_ng_symbols import symbols, normalize, revision
from factory_ng_safety import source_problem
from contextlib import closing
from pathlib import Path

REPO = os.environ.get('KB_REPO', '/opt/development/test/openmagic')
DB = os.environ.get('KB_DB', '/tmp/orch/knowledge.db')
PORT = int(os.environ.get('KB_PORT', '4103'))
REINDEX_INTERVAL = int(os.environ.get('KB_REINDEX_INTERVAL', '1800'))

STOP = set('''the a an of to in on for with and or is are be it its this that you your
whenever when may target each all any card cards creature creatures player players
spell spells until end turn beginning upkeep enters battlefield control controller
controls have has get gets put puts number equal'''.split())


def tokens(text, keep_stop=False):
    ts = [t.lower() for t in re.findall(r'[A-Za-z][A-Za-z_]{2,}', text)]
    return [t for t in ts if keep_stop or t not in STOP]


def _build_index(target):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(target)
    db.execute('DROP TABLE IF EXISTS docs')
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(kind, title, body, path, search_terms)")
    n = {'primitive': 0, 'helper': 0, 'handler': 0}

    cat = os.path.join(REPO, 'scripts/skills/primitive-catalog.md')
    if os.path.exists(cat):
        section, title = [], 'intro'
        for line in Path(cat).read_text(encoding='utf-8', errors='replace').splitlines(keepends=True):
            if line.startswith('## ') or line.startswith('### '):
                if section and len(''.join(section)) > 40:
                    db.execute('INSERT INTO docs(kind,title,body,path) VALUES (?,?,?,?)',
                               ('primitive', title, ''.join(section)[:4000], 'scripts/skills/primitive-catalog.md'))
                    n['primitive'] += 1
                title, section = line.strip('# \n'), []
            else:
                section.append(line)
        if section:
            db.execute('INSERT INTO docs(kind,title,body,path) VALUES (?,?,?,?)',
                       ('primitive', title, ''.join(section)[:4000], 'scripts/skills/primitive-catalog.md'))
            n['primitive'] += 1

    import glob
    for f in glob.glob(os.path.join(REPO, 'backend/cards/registry_*.go')):
        src = Path(f).read_text(encoding='utf-8', errors='replace')
        rel = os.path.relpath(f, REPO)
        for m in re.finditer(r'regEffect\("([^"]+)"', src):
            body = src[m.start():m.start() + 1500]
            db.execute('INSERT INTO docs(kind,title,body,path) VALUES (?,?,?,?)', ('primitive', m.group(1), body, rel))
            n['primitive'] += 1

    for f in glob.glob(os.path.join(REPO, 'backend/cardfns/lib_*.go')):
        src = Path(f).read_text(encoding='utf-8', errors='replace')
        rel = os.path.relpath(f, REPO)
        for m in re.finditer(r'((?:^//.*\n)+)^func (\w+)', src, re.M):
            db.execute('INSERT INTO docs(kind,title,body,path) VALUES (?,?,?,?)',
                       ('helper', m.group(2), m.group(1)[:2000], rel))
            n['helper'] += 1

    # Parse declarations, retaining receiver-qualified identity. The index
    # supplies candidates; consumers re-resolve code in their pinned checkout.
    paths = [str(p.relative_to(REPO)) for prefix in ('backend/game','backend/cardfns')
             for p in Path(REPO, prefix).glob('*.go')
             if not p.name.endswith('_test.go') and (prefix.endswith('game') or p.name.startswith('lib_'))]
    rows = symbols(REPO, paths)
    db.execute('CREATE TABLE symbols(symbol_id TEXT PRIMARY KEY, name TEXT, path TEXT, data TEXT)')
    db.execute('CREATE INDEX symbols_name_path ON symbols(name,path)')
    for row in rows:
        db.execute('INSERT OR IGNORE INTO symbols VALUES (?,?,?,?)',
                   (row['symbol_id'],row['name'],row['path'],json.dumps(row)))
        if row['path'].startswith('backend/game/'):
            kind = 'engine'
            body = (row['doc'] + '\n' + row['signature'])[:2000]
            db.execute('INSERT INTO docs(kind,title,body,path) VALUES (?,?,?,?)',
                       (kind,row['name'],body,row['path']))
            n[kind] = n.get(kind,0)+1

    for f in glob.glob(os.path.join(REPO, 'backend/cardfns/*.go')):
        base = os.path.basename(f)
        if base.startswith('lib_') or base.endswith('_test.go'):
            continue
        rel = os.path.relpath(f, REPO)
        header = []
        for line in Path(f).read_text(encoding='utf-8', errors='replace').splitlines(keepends=True):
            if line.startswith('func '):
                break
            if line.startswith('//'):
                header.append(line[2:].strip('/ ').rstrip() + '\n')
        text = ''.join(header)
        m = re.match(r'\s*([^\n—-]+?)\s*[—-]', text)
        title = m.group(1).strip() if m else base[:-3]
        if len(text) > 30:
            db.execute('INSERT INTO docs(kind,title,body,path) VALUES (?,?,?,?)', ('handler', title, text[:4000], rel))
            n['handler'] += 1

    for rowid,title,body in db.execute('SELECT rowid,title,body FROM docs').fetchall():
        db.execute('UPDATE docs SET search_terms=? WHERE rowid=?', (normalize(title+' '+body),rowid))
    db.commit()

    # Engine capability sets for /caps fail-fast: which trigger events exist
    # in the engine, and which shape/case labels the converter already maps.
    caps = {'event': set(), 'case': set()}
    ev = os.path.join(REPO, 'backend/game/events.go')
    if os.path.exists(ev):
        src = Path(ev).read_text(encoding='utf-8', errors='replace')
        caps['event'] = set(re.findall(r'Event\w+\s+EventType\s*=\s*"([a-z_]+)"', src))
    for base in ('backend/cards/converter.go', 'backend/cards/v2.go'):
        f = os.path.join(REPO, base)
        if os.path.exists(f):
            src = Path(f).read_text(encoding='utf-8', errors='replace')
            caps['case'] |= set(re.findall(r'case "([a-z_]+)"', src))
    n['event'] = len(caps['event'])
    n['case'] = len(caps['case'])
    db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)')
    for key,value in {'revision':revision(REPO),'built_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                      'counts':n,'caps':{k:sorted(v) for k,v in caps.items()}}.items():
        db.execute('INSERT INTO metadata VALUES (?,?)',(key,json.dumps(value)))
    db.commit()
    return db, n


BUILD_LOCK = threading.Lock()
REFRESH_LOCK = threading.Lock()
TRACE_LOCK = threading.Lock()
TRACE_PATH = os.environ.get('KB_SERVICE_TRACE','/tmp/orch/knowledge-lookups.jsonl')


def build_index():
    # Publish one complete snapshot. Readers never observe a dropped/empty FTS table.
    with BUILD_LOCK:
        before = revision(REPO)
        problem=source_problem(REPO)
        if problem: raise RuntimeError('Cannot index an unsettled source checkout: '+problem)
        Path(DB).parent.mkdir(parents=True,exist_ok=True)
        fd,temp = tempfile.mkstemp(prefix='.knowledge-',suffix='.db',dir=Path(DB).parent)
        os.close(fd)
        try:
            db,counts = _build_index(temp)
            db.close()
            if revision(REPO) != before or source_problem(REPO):
                raise RuntimeError('source changed during knowledge indexing; retaining previous index')
            os.replace(temp,DB)
            return sqlite3.connect(DB),counts
        finally:
            if os.path.exists(temp): os.unlink(temp)


def metadata(db):
    return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}


def refresh_if_changed():
    """New canonical revisions become discoverable without waiting 30 minutes."""
    with REFRESH_LOCK:
        with closing(sqlite3.connect('file:'+DB+'?mode=ro',uri=True)) as db:
            indexed=metadata(db)['revision']
        if indexed != revision(REPO):
            db,_=build_index()
            db.close()


SEARCH_STOP = (STOP - {'card','cards','turn','player','players','target','targets'}) | set('this that support ability only more than computes minus resolution time beginning effect amount'.split())


def search(db, query_text, kind=None, limit=5, fallback=False):
    meta = metadata(db)
    words = list(dict.fromkeys(w for w in normalize(query_text).split() if w not in SEARCH_STOP))[:12]
    filters = ' AND kind=?' if kind else ''
    extra = [kind] if kind else []
    rows = db.execute('SELECT kind,title,path,body FROM docs WHERE (lower(title)=lower(?) OR EXISTS '
                      '(SELECT 1 FROM symbols WHERE symbols.name=docs.title AND symbols.path=docs.path '
                      "AND (symbol_id=? OR json_extract(data,'$.qualified')=?)))"+filters+' LIMIT ?',
                      [query_text,query_text,query_text,*extra,limit]).fetchall()
    strategy='exact_symbol'
    queries=[]
    if not rows and words:
        # Require the action's words together, never broad OR over a requirement.
        q=' AND '.join('"'+w+'"' for w in words)
        queries.append(q)
        rows = db.execute('SELECT kind,title,path,body FROM docs WHERE docs MATCH ?'+filters+' ORDER BY rank LIMIT ?',
                          ['search_terms : ('+q+')',*extra,min(80,limit*8)]).fetchall()
        strategy='normalized_all_terms'
    if not rows and words and fallback:
        # An explicit fallback keeps three leading capability terms together.
        q=' AND '.join('"'+w+'"' for w in words[:3])
        queries.append(q)
        rows=db.execute('SELECT kind,title,path,body FROM docs WHERE docs MATCH ?'+filters+' ORDER BY rank LIMIT ?',
                        ['search_terms : ('+q+')',*extra,min(80,limit*8)]).fetchall()
        strategy='explicit_leading_terms'
    candidates=[]
    for kind_,title,path,body in rows:
        entries=db.execute('SELECT data FROM symbols WHERE name=? AND path=?',(title,path)).fetchall()
        for entry in entries or [None]:
            data=json.loads(entry[0]) if entry else {}
            if strategy=='exact_symbol' and query_text != title and data and query_text not in (data['symbol_id'],data['qualified']):
                continue
            candidates.append(dict(data,kind=kind_,title=title,path=path,
                                   symbol_kind=data.get('kind'),
                                   description=next((l.strip() for l in body.splitlines() if l.strip()),'')[:220]))
    if strategy != 'exact_symbol':
        active_words=words[:3] if strategy=='explicit_leading_terms' else words
        def relevance(row):
            title_words=[w for w in normalize(row['title']).split() if w not in SEARCH_STOP]
            name_match=all(w in title_words for w in active_words)
            # Names matching the requested action outrank incidental prose.
            # Among equivalent names, present GameState entry points first.
            return (title_words[:len(active_words)] != active_words,not name_match, row.get('receiver') != 'GameState')
        candidates.sort(key=relevance)
    candidates=list({r.get('symbol_id') or (r['kind'],r['title'],r['path']):r for r in reversed(candidates)}.values())[::-1]
    return {'schema':'factory.knowledge-search/v1','status':'found' if candidates else 'not_found',
            'query':query_text,'normalized_words':words,'fts_queries':queries,'strategy':strategy,
            'indexed_revision':meta['revision'],'indexed_at':meta['built_at'],
            'candidates':candidates[:limit]}


def record_lookup(endpoint, params, result):
    record={'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'endpoint':endpoint,
            'request':params,'response':result}
    with TRACE_LOCK:
        Path(TRACE_PATH).parent.mkdir(parents=True,exist_ok=True)
        with open(TRACE_PATH,'a') as handle: handle.write(json.dumps(record,sort_keys=True)+'\n')


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
        if getattr(self,'lookup_endpoint','') in ('/caps','/similar','/toc'):
            record_lookup(self.lookup_endpoint,self.lookup_params,{'status':code,'text':text})
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
        self.lookup_endpoint,self.lookup_params=u.path,p
        self.refresh_error=''
        if u.path in ('/search','/find','/caps','/similar','/toc'):
            try: refresh_if_changed()
            except Exception as exc: self.refresh_error=str(exc)
        with closing(sqlite3.connect('file:'+DB+'?mode=ro',uri=True)) as db:
            return self.handle_request(u, p, db)

    def handle_request(self, u, p, db):
        global COUNTS
        meta = metadata(db)
        if u.path == '/health':
            return self.reply('ok %s; revision=%s; indexed_at=%s\n' % (meta['counts'],meta['revision'],meta['built_at']))
        if u.path == '/reindex':
            refreshed, COUNTS = build_index()
            refreshed.close()
            return self.reply('reindexed %s\n' % COUNTS)
        if u.path == '/toc':
            # Compact primitive index for briefings: every primitive name +
            # first body line. Replaces the 169KB catalog digest; details are
            # one /find query away.
            out, seen = [], set()
            for title, body in db.execute("SELECT title, body FROM docs WHERE kind='primitive' ORDER BY title"):
                if title in seen:
                    continue
                seen.add(title)
                first = next((l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith('regEffect')), '')
                out.append('%s — %s' % (title, first[:90]))
            return self.reply('# Primitive index (%d entries; query /find?q=&kind=primitive for details)\n%s\n'
                              % (len(out), '\n'.join(out)))
        if u.path in ('/search','/find'):
            result=search(db,p.get('q',''),p.get('kind') or None,
                          max(1,min(int(p.get('n',5)),20)),p.get('fallback') == '1')
            result['request_id']=p.get('request_id') or uuid.uuid4().hex
            result['current_source_revision']=revision(REPO)
            result['index_stale']=result['indexed_revision'] != result['current_source_revision']
            if self.refresh_error: result['refresh_error']=self.refresh_error
            record_lookup(u.path,p,result)
            if u.path == '/search': return self.reply(json.dumps(result))
            from factory_ng_knowledge import describe
            return self.reply(describe(result)+'\n')
        if u.path == '/caps':
            # Deterministic engine-readiness check for map-lane fail-fast:
            # exact match against engine EventType constants + converter cases.
            name = p.get('name', '').strip().lower()
            if not name:
                return self.reply('usage: /caps?name=<event_or_case_label>\n')
            hits = [k for k in ('event', 'case') if name in meta['caps'].get(k, ())]
            if hits:
                return self.reply('SUPPORTED (%s): %r is indexed; verify behavior in the pinned source.\n'
                                  % ('+'.join(hits), name))
            near = sorted({c for k in meta['caps'] for c in meta['caps'][k]
                           if name in c or c in name or name.replace('becomes_', '') in c})[:6]
            return self.reply('MISSING: %r is neither an engine EventType nor a converter case.\n'
                              'This limited index does not establish a missing capability; verify the pinned source.\n'
                              '%s' % (name, ('Near names (check these first): %s\n' % ', '.join(near)) if near else ''))
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


def periodic_reindex():
    """Keep the index from going stale between manual /reindex calls.

    Nothing else in the repo ever hits /reindex on a schedule, so a long-lived
    service otherwise serves a fixed snapshot from whenever it last started.
    """
    global COUNTS
    while True:
        time.sleep(REINDEX_INTERVAL)
        try:
            refreshed, COUNTS = build_index()
            refreshed.close()
            print('periodic reindex:', COUNTS, flush=True)
        except Exception as exc:
            print('periodic reindex failed:', exc, flush=True)


if __name__ == '__main__':
    initial, COUNTS = build_index()
    initial.close()
    print('indexed:', COUNTS, flush=True)
    threading.Thread(target=periodic_reindex, daemon=True).start()
    import socketserver

    class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    S(('127.0.0.1', PORT), H).serve_forever()
