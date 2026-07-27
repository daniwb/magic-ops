// Dispatcher v4 — eigener SQLite-Store, ersetzt Kanboard als Source of Truth.
// EIN Prozess = EIN Schreiber (serialisiert durch Go + SQLite WAL) → keine
// "database is locked"-Kämpfe wie bei Kanboard. Enthält Queue, Leases,
// Retry-Zähler, [VOCAB]-Loop, Splits, Stats-API und eine kleine GUI.
package main

import (
	"database/sql"
	"embed"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

const (
	LeaseDuration = 180 * time.Second
	ReaperTick    = 30 * time.Second
	MaxFail       = 3
)

// Port aus Env: Test :9998, Live-Cutover :9999
var Port = envOr("PORT", ":9998")

// Zustände (ersetzen die Kanboard-Spalten)
const (
	StTodo    = "todo"    // wartet auf Bearbeitung (col 14/16)
	StWorking = "working" // an Worker verliehen (col 15)
	StBlocked = "blocked" // wartet auf Primitiv (col 20)
	StWait    = "wait"    // wait-triage (col 21)
	StDone    = "done"    // gefixt+gemerged (col 17)
	StVocab   = "vocab"   // [VOCAB]-Primitiv-Ticket (col 19)
)

const (
	TypeCard  = "card"
	TypeVocab = "vocab"
	TypeSplit = "split"
)

//go:embed gui.html
var guiFS embed.FS

var (
	db      *sql.DB
	mu      sync.Mutex
	dbPath  = envOr("DB_PATH", "/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db")
	backlog = envOr("BACKLOG", "/opt/development/kanboard-backlog/backlog.jsonl")
)

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

// ---- Schema ----
func initDB() {
	var err error
	db, err = sql.Open("sqlite3", dbPath+"?_journal=WAL&_busy_timeout=5000")
	if err != nil {
		log.Fatal(err)
	}
	db.SetMaxOpenConns(1) // EIN Schreiber — die ganze Pointe
	_, err = db.Exec(`
CREATE TABLE IF NOT EXISTS tickets (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  type         TEXT NOT NULL DEFAULT 'card',
  title        TEXT NOT NULL,
  descr        TEXT NOT NULL DEFAULT '',
  mechanic     TEXT DEFAULT '',
  state        TEXT NOT NULL DEFAULT 'todo',
  worker_id    TEXT DEFAULT '',
  lease_exp    INTEGER DEFAULT 0,
  retry_count  INTEGER DEFAULT 0,
  missing_prim TEXT DEFAULT '',
  vocab_id     INTEGER DEFAULT 0,   -- card: welches VOCAB blockiert; split: dito
  parent_id    INTEGER DEFAULT 0,   -- split: aus welchem Bundle
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_state ON tickets(state);
CREATE INDEX IF NOT EXISTS idx_type  ON tickets(type);
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL,
  ts        INTEGER NOT NULL,
  msg       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_ticket ON events(ticket_id);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS snapshots (ts INTEGER PRIMARY KEY, counts TEXT, fixed_total INTEGER);
`)
	if err != nil {
		log.Fatal(err)
	}
	// Migration: priority-Spalte (requeuete Karten werden bevorzugt geclaimt)
	db.Exec(`ALTER TABLE tickets ADD COLUMN priority INTEGER DEFAULT 0`)
	// Migration: build_model (welches Modell baut gerade dieses [VOCAB])
	db.Exec(`ALTER TABLE tickets ADD COLUMN build_model TEXT DEFAULT ''`)
	// Migration: tokens (kumulierte Claude-Token, die dieses Ticket gekostet hat)
	db.Exec(`ALTER TABLE tickets ADD COLUMN tokens INTEGER DEFAULT 0`)
}

func now() int64 { return time.Now().Unix() }

func addEvent(tid int64, msg string) {
	db.Exec(`INSERT INTO events(ticket_id,ts,msg) VALUES(?,?,?)`, tid, now(), msg)
}

func metaGet(k string) string {
	var v string
	db.QueryRow(`SELECT v FROM meta WHERE k=?`, k).Scan(&v)
	return v
}
func metaSet(k, v string) { db.Exec(`INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=?`, k, v, v) }

// ---- Backlog-Ingest: liest backlog.jsonl ab gespeichertem Offset ----
func ingestBacklog(limit int) int {
	f, err := os.Open(backlog)
	if err != nil {
		return 0
	}
	defer f.Close()
	data, _ := io.ReadAll(f)
	lines := strings.Split(string(data), "\n")
	var off int
	fmt.Sscanf(metaGet("backlog_offset"), "%d", &off)
	added := 0
	for off < len(lines) && added < limit {
		line := strings.TrimSpace(lines[off])
		off++
		if line == "" {
			continue
		}
		var t struct {
			Title       string `json:"title"`
			Description string `json:"description"`
		}
		if json.Unmarshal([]byte(line), &t) != nil || t.Title == "" {
			continue
		}
		mech := parseMechanic(t.Title)
		db.Exec(`INSERT INTO tickets(type,title,descr,mechanic,state,created_at,updated_at)
		         VALUES('card',?,?,?,'todo',?,?)`, t.Title, t.Description, mech, now(), now())
		added++
	}
	metaSet("backlog_offset", fmt.Sprintf("%d", off))
	return added
}

func parseMechanic(title string) string {
	// "DSL-BUNDLE: [mech] ..." → mech
	if i := strings.Index(title, "["); i >= 0 {
		if j := strings.Index(title[i:], "]"); j > 0 {
			return title[i+1 : i+j]
		}
	}
	return ""
}

func openCount() int {
	var n int
	db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE state IN('todo','working')`).Scan(&n)
	return n
}

// ---- HTTP: /claim ----
func claim(w http.ResponseWriter, r *http.Request) {
	worker := r.URL.Query().Get("worker")
	if worker == "" {
		http.Error(w, "missing worker", 400)
		return
	}
	mu.Lock()
	defer mu.Unlock()

	// gleicher Worker mit lebender Lease → dasselbe Ticket
	var t struct {
		ID              int64
		Title, Descr    string
		Retry           int
	}
	row := db.QueryRow(`SELECT id,title,descr,retry_count FROM tickets
	                    WHERE state='working' AND worker_id=? AND lease_exp>? LIMIT 1`, worker, now())
	if row.Scan(&t.ID, &t.Title, &t.Descr, &t.Retry) == nil {
		exp := now() + int64(LeaseDuration.Seconds())
		db.Exec(`UPDATE tickets SET lease_exp=? WHERE id=?`, exp, t.ID)
		writeJSON(w, map[string]any{"id": t.ID, "title": t.Title, "desc": t.Descr, "retry_count": t.Retry, "lease_exp": exp, "resumed": true})
		return
	}

	// Auto-Refill wenn Queue niedrig
	if openCount() < 75 {
		if n := ingestBacklog(500); n > 0 {
			log.Printf("ingest: +%d aus backlog", n)
		}
	}

	// ältestes todo Card/Split (VOCAB wird nie an Card-Worker verteilt)
	row = db.QueryRow(`SELECT id,title,descr,retry_count FROM tickets
	                   WHERE state='todo' AND type IN('card','split')
	                   ORDER BY priority DESC, id ASC LIMIT 1`)
	if row.Scan(&t.ID, &t.Title, &t.Descr, &t.Retry) != nil {
		writeJSON(w, map[string]any{"id": ""})
		return
	}
	exp := now() + int64(LeaseDuration.Seconds())
	db.Exec(`UPDATE tickets SET state='working',worker_id=?,lease_exp=?,updated_at=? WHERE id=?`, worker, exp, now(), t.ID)
	addEvent(t.ID, "claimed by "+worker)
	log.Printf("claim: #%d -> %s (retry %d)", t.ID, worker, t.Retry)
	writeJSON(w, map[string]any{"id": t.ID, "title": t.Title, "desc": t.Descr, "retry_count": t.Retry, "lease_exp": exp})
}

// ---- /heartbeat ----
func heartbeat(w http.ResponseWriter, r *http.Request) {
	var tid int64
	fmt.Sscanf(r.URL.Query().Get("ticket"), "%d", &tid)
	mu.Lock()
	db.Exec(`UPDATE tickets SET lease_exp=? WHERE id=? AND state='working'`, now()+int64(LeaseDuration.Seconds()), tid)
	mu.Unlock()
	w.Write([]byte(`{"ok":true}`))
}

// ---- /report ----
func report(w http.ResponseWriter, r *http.Request) {
	var q struct {
		TicketID         string `json:"ticket_id"`
		WorkerID         string `json:"worker_id"`
		Status           string `json:"status"`
		Reason           string `json:"reason"`
		MissingPrimitive string `json:"missing_primitive"`
		PrimitiveWhy     string `json:"primitive_why"`
		Note             string `json:"note"`
		Tokens           int64  `json:"tokens"`
		BlockedCardTitle string `json:"blocked_card_title"`
		Skipped          []struct {
			Card      string `json:"card"`
			Primitive string `json:"primitive"`
			Why       string `json:"why"`
			Desc      string `json:"desc"`
		} `json:"skipped"`
	}
	body, _ := io.ReadAll(r.Body)
	json.Unmarshal(body, &q)
	var tid int64
	fmt.Sscanf(q.TicketID, "%d", &tid)

	mu.Lock()
	defer mu.Unlock()

	var owner, title string
	if db.QueryRow(`SELECT worker_id,title FROM tickets WHERE id=? AND state='working'`, tid).Scan(&owner, &title) != nil {
		http.Error(w, "no working ticket", 409)
		return
	}
	if owner != q.WorkerID {
		http.Error(w, "lease owned by other", 409)
		return
	}

	// Token-Verbrauch dieses Report-Zyklus aufs Ticket kumulieren (über Retries hinweg).
	if q.Tokens > 0 {
		db.Exec(`UPDATE tickets SET tokens=tokens+? WHERE id=?`, q.Tokens, tid)
	}

	switch {
	case q.Status == "fixed":
		db.Exec(`UPDATE tickets SET state='done',updated_at=? WHERE id=?`, now(), tid)
		addEvent(tid, fmt.Sprintf("FIXED by %s [%d tok]; %s", q.WorkerID, q.Tokens, q.Note))
		for _, s := range q.Skipped {
			splitTitle := fmt.Sprintf("DSL-SPLIT: %s (from #%d)", s.Card, tid)
			res, _ := db.Exec(`INSERT INTO tickets(type,title,descr,state,parent_id,created_at,updated_at)
			                   VALUES('split',?,?,'blocked',?,?,?)`, splitTitle, s.Desc, tid, now(), now())
			sid, _ := res.LastInsertId()
			vid := fileVocab(s.Primitive, s.Why, sid, splitTitle)
			db.Exec(`UPDATE tickets SET vocab_id=? WHERE id=?`, vid, sid)
		}
		log.Printf("report #%d FIXED", tid)

	case q.Status == "parked" && q.Reason == "missing_primitive":
		vid := fileVocab(q.MissingPrimitive, q.PrimitiveWhy, tid, title)
		db.Exec(`UPDATE tickets SET state='blocked',missing_prim=?,vocab_id=?,updated_at=? WHERE id=?`, q.MissingPrimitive, vid, now(), tid)
		addEvent(tid, "BLOCKED on "+q.MissingPrimitive)
		log.Printf("report #%d BLOCKED (%s)", tid, q.MissingPrimitive)

	case q.Status == "parked" && q.Reason == "max_retry_reached":
		db.Exec(`UPDATE tickets SET state='wait',updated_at=? WHERE id=?`, now(), tid)
		addEvent(tid, "WAIT-TRIAGE; "+q.Note)

	case q.Status == "retry" && q.Reason == "infra":
		db.Exec(`UPDATE tickets SET state='todo',worker_id='',lease_exp=0,updated_at=? WHERE id=?`, now(), tid)
		addEvent(tid, "infra retry (no counter); "+q.Note)

	case q.Status == "retry":
		var rc int
		db.QueryRow(`SELECT retry_count FROM tickets WHERE id=?`, tid).Scan(&rc)
		rc++
		st := StTodo
		if rc >= MaxFail {
			st = StWait
		}
		db.Exec(`UPDATE tickets SET state=?,worker_id='',lease_exp=0,retry_count=?,updated_at=? WHERE id=?`, st, rc, now(), tid)
		addEvent(tid, fmt.Sprintf("retry #%d -> %s", rc, st))

	default:
		http.Error(w, "unknown status", 400)
		return
	}
	w.Write([]byte(`{"ok":true}`))
}

// ---- [VOCAB]-Filing mit Dedup (semantisch grob über normalisierten Titel) ----
func fileVocab(primitive, why string, blockedID int64, blockedTitle string) int64 {
	key := normKey(primitive)
	// Erst alle Kandidaten einlesen und Rows schließen — KEINE DB-Writes bei
	// offener Query (MaxOpenConns=1 → sonst Deadlock auf der einzigen Conn).
	type cand struct {
		id int64
		tt string
	}
	var cands []cand
	rows, _ := db.Query(`SELECT id,title FROM tickets WHERE type='vocab' AND state='vocab'`)
	for rows.Next() {
		var c cand
		rows.Scan(&c.id, &c.tt)
		cands = append(cands, c)
	}
	rows.Close()
	for _, c := range cands {
		if strings.Contains(normKey(c.tt), key) || strings.Contains(key, normKey(strings.TrimPrefix(c.tt, "[VOCAB] "))) {
			addEvent(c.id, fmt.Sprintf("also blocks #%d (%s)", blockedID, blockedTitle))
			return c.id
		}
	}
	res, _ := db.Exec(`INSERT INTO tickets(type,title,descr,state,created_at,updated_at)
	                   VALUES('vocab',?,?,'vocab',?,?)`, "[VOCAB] "+primitive, why, now(), now())
	id, _ := res.LastInsertId()
	log.Printf("vocab: filed #%d %q (blocked #%d)", id, primitive, blockedID)
	return id
}

func normKey(s string) string {
	var b strings.Builder
	for _, r := range strings.ToLower(s) {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		} else {
			b.WriteRune(' ')
		}
	}
	return strings.Join(strings.Fields(b.String()), " ")
}

// ---- Reaper ----
func reaper() {
	for range time.Tick(ReaperTick) {
		mu.Lock()
		rows, _ := db.Query(`SELECT id,worker_id,retry_count FROM tickets WHERE state='working' AND lease_exp<?`, now())
		type ex struct {
			id    int64
			w     string
			rc    int
		}
		var list []ex
		for rows.Next() {
			var e ex
			rows.Scan(&e.id, &e.w, &e.rc)
			list = append(list, e)
		}
		rows.Close()
		for _, e := range list {
			rc := e.rc + 1
			st := StTodo
			if rc >= MaxFail {
				st = StWait
			}
			db.Exec(`UPDATE tickets SET state=?,worker_id='',lease_exp=0,retry_count=?,updated_at=? WHERE id=?`, st, rc, now(), e.id)
			addEvent(e.id, fmt.Sprintf("lease expired (%s) -> %s", e.w, st))
			log.Printf("reaper #%d lease expired (%s)", e.id, e.w)
		}
		// verwaiste Build-Marker (Builder gecrasht) freigeben → wieder baubar
		db.Exec(`UPDATE tickets SET worker_id='',build_model='',lease_exp=0 WHERE type='vocab' AND worker_id!='' AND lease_exp<?`, now())
		mu.Unlock()
	}
}

// ---- /vocab-close: schließt VOCAB + requeued blockierte Karten (ersetzt requeue-cron) ----
func vocabClose(w http.ResponseWriter, r *http.Request) {
	var vid int64
	fmt.Sscanf(r.URL.Query().Get("id"), "%d", &vid)
	mu.Lock()
	defer mu.Unlock()
	// state=done UND Build-Marker räumen (sonst zeigt das Board fertige Builds
	// weiter als "in Bau", bis die 90min-Lease abläuft — 2026-07-21).
	db.Exec(`UPDATE tickets SET state='done',worker_id='',build_model='',lease_exp=0,updated_at=? WHERE id=? AND type='vocab'`, now(), vid)
	res, _ := db.Exec(`UPDATE tickets SET state='todo',retry_count=0,priority=1,updated_at=? WHERE vocab_id=? AND state='blocked'`, now(), vid)
	n, _ := res.RowsAffected()
	log.Printf("vocab-close #%d: %d Karten requeued", vid, n)
	writeJSON(w, map[string]any{"requeued": n})
}

// ---- /vocab-list: offene [VOCAB] für den Primitive-Builder (älteste zuerst).
// Überspringt schon gescheiterte (retry_count>0) außer ?all=1. ----
func vocabList(w http.ResponseWriter, r *http.Request) {
	all := r.URL.Query().Get("all") == "1"
	mu.Lock()
	defer mu.Unlock()
	q := `SELECT v.id,v.title,v.descr,v.retry_count,
	        (SELECT COUNT(*) FROM tickets c WHERE c.vocab_id=v.id AND c.state='blocked')
	      FROM tickets v WHERE v.type='vocab' AND v.state='vocab'
	        AND NOT (v.worker_id!='' AND v.lease_exp>` + fmt.Sprintf("%d", now()) + `)` // nicht gerade in Bau
	if !all {
		q += ` AND v.retry_count=0`
	}
	q += ` ORDER BY v.id ASC`
	rows, err := db.Query(q)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer rows.Close()
	type vt struct {
		ID      int64  `json:"id"`
		Title   string `json:"title"`
		Descr   string `json:"descr"`
		Fails   int    `json:"fails"`
		Blocked int    `json:"blocked"`
	}
	var out []vt
	for rows.Next() {
		var v vt
		rows.Scan(&v.ID, &v.Title, &v.Descr, &v.Fails, &v.Blocked)
		out = append(out, v)
	}
	writeJSON(w, out)
}

// ---- /vocab-merge?from=&to= : semantisches Duplikat zusammenführen.
// Blockierte Karten von `from` wandern auf das kanonische `to`, `from` wird
// geschlossen. Idempotent-sicher: nur offene vocab-Tickets, from!=to. ----
func vocabMerge(w http.ResponseWriter, r *http.Request) {
	var from, to int64
	fmt.Sscanf(r.URL.Query().Get("from"), "%d", &from)
	fmt.Sscanf(r.URL.Query().Get("to"), "%d", &to)
	if from == 0 || to == 0 || from == to {
		http.Error(w, "bad from/to", 400)
		return
	}
	mu.Lock()
	defer mu.Unlock()
	// beide müssen offene vocab-Tickets sein
	var ok1, ok2 int
	db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE id=? AND type='vocab' AND state='vocab'`, from).Scan(&ok1)
	db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE id=? AND type='vocab' AND state='vocab'`, to).Scan(&ok2)
	if ok1 == 0 || ok2 == 0 {
		http.Error(w, "from/to not both open vocab", 409)
		return
	}
	res, _ := db.Exec(`UPDATE tickets SET vocab_id=?,updated_at=? WHERE vocab_id=? AND state='blocked'`, to, now(), from)
	moved, _ := res.RowsAffected()
	db.Exec(`UPDATE tickets SET state='done',updated_at=? WHERE id=?`, now(), from)
	addEvent(to, fmt.Sprintf("merged duplicate #%d (%d cards moved here)", from, moved))
	addEvent(from, fmt.Sprintf("semantic duplicate -> merged into #%d", to))
	log.Printf("vocab-merge #%d -> #%d (%d cards)", from, to, moved)
	writeJSON(w, map[string]any{"ok": true, "moved": moved})
}

// ---- /vocab-reset?id= : retry_count=0 + Build-Marker frei (holt ein VOCAB
// zurück in die Standard-Bauliste; für Aufräum-Fälle wie stale-marker). ----
func vocabReset(w http.ResponseWriter, r *http.Request) {
	var vid int64
	fmt.Sscanf(r.URL.Query().Get("id"), "%d", &vid)
	mu.Lock()
	res, _ := db.Exec(`UPDATE tickets SET retry_count=0,worker_id='',build_model='',lease_exp=0,updated_at=? WHERE id=? AND type='vocab' AND state='vocab'`, now(), vid)
	n, _ := res.RowsAffected()
	if n > 0 {
		addEvent(vid, "manuell zurückgesetzt (retry=0, Marker frei)")
	}
	mu.Unlock()
	writeJSON(w, map[string]any{"reset": n})
}

// ---- /vocab-claim: Builder markiert ein [VOCAB] als "in Bau" (Sichtbarkeit +
// verhindert Doppel-Bau durch zwei Builder). Lease 90min, Reaper räumt stale. ----
func vocabClaim(w http.ResponseWriter, r *http.Request) {
	var vid int64
	fmt.Sscanf(r.URL.Query().Get("id"), "%d", &vid)
	worker := r.URL.Query().Get("worker")
	model := r.URL.Query().Get("model")
	mu.Lock()
	db.Exec(`UPDATE tickets SET worker_id=?,build_model=?,lease_exp=?,updated_at=? WHERE id=? AND type='vocab'`,
		worker, model, now()+5400, now(), vid)
	addEvent(vid, "PRIM-BUILD start: "+worker+" ("+model+")")
	mu.Unlock()
	w.Write([]byte(`{"ok":true}`))
}

// ---- /vocab-fail: Builder meldet Fehlschlag/Engine-Hook → retry_count++, Marker frei ----
func vocabFail(w http.ResponseWriter, r *http.Request) {
	var vid int64
	fmt.Sscanf(r.URL.Query().Get("id"), "%d", &vid)
	reason := r.URL.Query().Get("reason")
	mu.Lock()
	db.Exec(`UPDATE tickets SET retry_count=retry_count+1,worker_id='',build_model='',lease_exp=0,updated_at=? WHERE id=? AND type='vocab'`, now(), vid)
	addEvent(vid, "PRIM-BUILDER fail: "+reason)
	mu.Unlock()
	w.Write([]byte(`{"ok":true}`))
}

// ---- /stats ----
func stats(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	defer mu.Unlock()
	counts := map[string]int{}
	rows, _ := db.Query(`SELECT state,COUNT(*) FROM tickets WHERE type IN('card','split') GROUP BY state`)
	for rows.Next() {
		var s string
		var n int
		rows.Scan(&s, &n)
		counts[s] = n
	}
	rows.Close()
	var vocabOpen, doneTotal int
	db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE type='vocab' AND state='vocab'`).Scan(&vocabOpen)
	db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE state='done'`).Scan(&doneTotal)

	// aktive Worker
	type wk struct {
		Worker string `json:"worker"`
		ID     int64  `json:"id"`
		Title  string `json:"title"`
	}
	var workers []wk
	wr, _ := db.Query(`SELECT worker_id,id,title FROM tickets WHERE state='working' ORDER BY worker_id`)
	for wr.Next() {
		var x wk
		wr.Scan(&x.Worker, &x.ID, &x.Title)
		workers = append(workers, x)
	}
	wr.Close()

	// Top-VOCAB-Blocker (nach #blockierter Karten)
	type vb struct {
		ID    int64  `json:"id"`
		Title string `json:"title"`
		Cards int    `json:"cards"`
	}
	var topVocab []vb
	tr, _ := db.Query(`SELECT v.id,v.title,COUNT(c.id) c FROM tickets v
	                   LEFT JOIN tickets c ON c.vocab_id=v.id AND c.state='blocked'
	                   WHERE v.type='vocab' AND v.state='vocab'
	                   GROUP BY v.id ORDER BY c DESC LIMIT 10`)
	for tr.Next() {
		var x vb
		tr.Scan(&x.ID, &x.Title, &x.Cards)
		topVocab = append(topVocab, x)
	}
	tr.Close()

	// Durchsatz letzte 24h (done-events)
	var fixed24 int
	db.QueryRow(`SELECT COUNT(*) FROM events WHERE msg LIKE 'FIXED%' AND ts>?`, now()-86400).Scan(&fixed24)

	// aktive Primitive-Builder (VOCABs gerade in Bau)
	type bld struct {
		Worker string `json:"worker"`
		ID     int64  `json:"id"`
		Title  string `json:"title"`
		Model  string `json:"model"`
		Cards  int    `json:"cards"`
	}
	var builders []bld
	br, _ := db.Query(`SELECT worker_id,id,title,build_model,
	                   (SELECT COUNT(*) FROM tickets c WHERE c.vocab_id=v.id AND c.state='blocked')
	                   FROM tickets v WHERE type='vocab' AND state='vocab' AND worker_id!='' AND lease_exp>? ORDER BY worker_id`, now())
	for br.Next() {
		var b bld
		br.Scan(&b.Worker, &b.ID, &b.Title, &b.Model, &b.Cards)
		builders = append(builders, b)
	}
	br.Close()

	// Backlog-Restvorrat: Zeilen in backlog.jsonl minus verbrauchtem Offset
	backlogRemaining := 0
	if b, err := os.ReadFile(backlog); err == nil {
		total := strings.Count(string(b), "\n")
		var off int
		fmt.Sscanf(metaGet("backlog_offset"), "%d", &off)
		if backlogRemaining = total - off; backlogRemaining < 0 {
			backlogRemaining = 0
		}
	}
	writeJSON(w, map[string]any{
		"states": counts, "vocab_open": vocabOpen, "done_total": doneTotal,
		"fixed_24h": fixed24, "workers": workers, "builders": builders, "top_vocab": topVocab,
		"backlog_remaining": backlogRemaining,
	})
}

// ---- /tickets?state=&q=&limit= : Ticket-Browser für die GUI ----
func tickets(w http.ResponseWriter, r *http.Request) {
	st := r.URL.Query().Get("state")
	q := r.URL.Query().Get("q")
	limit := 50
	fmt.Sscanf(r.URL.Query().Get("limit"), "%d", &limit)
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	mu.Lock()
	defer mu.Unlock()
	sql := `SELECT id,title,state,mechanic,retry_count,tokens,
	          (SELECT COUNT(*) FROM tickets c WHERE c.vocab_id=t.id AND c.state='blocked')
	        FROM tickets t WHERE 1=1`
	var args []any
	if st != "" {
		sql += ` AND state=?`
		args = append(args, st)
	}
	if q != "" {
		sql += ` AND title LIKE ?`
		args = append(args, "%"+q+"%")
	}
	sql += ` ORDER BY id DESC LIMIT ?`
	args = append(args, limit)
	rows, err := db.Query(sql, args...)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer rows.Close()
	type tk struct {
		ID       int64  `json:"id"`
		Title    string `json:"title"`
		State    string `json:"state"`
		Mechanic string `json:"mechanic"`
		Fails    int    `json:"fails"`
		Tokens   int64  `json:"tokens"`
		Blocked  int    `json:"blocked"`
	}
	var out []tk
	for rows.Next() {
		var t tk
		rows.Scan(&t.ID, &t.Title, &t.State, &t.Mechanic, &t.Fails, &t.Tokens, &t.Blocked)
		out = append(out, t)
	}
	writeJSON(w, out)
}

// ---- /action : manuelle Eingriffe aus der GUI ----
func action(w http.ResponseWriter, r *http.Request) {
	do := r.URL.Query().Get("do")
	mu.Lock()
	defer mu.Unlock()
	switch do {
	case "requeue": // wait-triage / blocked → todo, Zähler zurück
		var id int64
		fmt.Sscanf(r.URL.Query().Get("id"), "%d", &id)
		db.Exec(`UPDATE tickets SET state='todo',retry_count=0,priority=1,worker_id='',lease_exp=0,updated_at=? WHERE id=?`, now(), id)
		addEvent(id, "manuell nach todo requeued (GUI, priorisiert)")
		writeJSON(w, map[string]any{"ok": true})
	case "ingest": // Backlog-Nachschub von Hand
		n := 200
		fmt.Sscanf(r.URL.Query().Get("n"), "%d", &n)
		added := ingestBacklog(n)
		writeJSON(w, map[string]any{"ok": true, "added": added})
	default:
		http.Error(w, "unknown action", 400)
	}
}

// ---- /history : Durchsatz-Kurve (Snapshots) ----
func history(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	defer mu.Unlock()
	rows, _ := db.Query(`SELECT ts,counts,fixed_total FROM snapshots ORDER BY ts DESC LIMIT 48`)
	defer rows.Close()
	type sn struct {
		Ts     int64  `json:"ts"`
		Counts string `json:"counts"`
		Fixed  int    `json:"fixed"`
	}
	var out []sn
	for rows.Next() {
		var s sn
		rows.Scan(&s.Ts, &s.Counts, &s.Fixed)
		out = append(out, s)
	}
	writeJSON(w, out)
}

// alle 15 min einen Snapshot (Durchsatz-Historie)
func snapshotLoop() {
	for range time.Tick(15 * time.Minute) {
		mu.Lock()
		counts := map[string]int{}
		rows, _ := db.Query(`SELECT state,COUNT(*) FROM tickets WHERE type IN('card','split') GROUP BY state`)
		for rows.Next() {
			var s string
			var n int
			rows.Scan(&s, &n)
			counts[s] = n
		}
		rows.Close()
		var doneTotal int
		db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE state='done'`).Scan(&doneTotal)
		cj, _ := json.Marshal(counts)
		db.Exec(`INSERT OR REPLACE INTO snapshots(ts,counts,fixed_total) VALUES(?,?,?)`, now()/900*900, string(cj), doneTotal)
		mu.Unlock()
	}
}

// fetchClaudeUsage aktualisiert den Usage-Cache selbst (TTL 90s), damit die
// Anzeige stimmt, auch wenn keine Claude-Worker laufen (die sonst den Cache pflegen).
func fetchClaudeUsage() {
	cache := envOr("USAGE_CACHE", "/tmp/claude-usage-gate.json")
	if fi, err := os.Stat(cache); err == nil && time.Since(fi.ModTime()) < 90*time.Second {
		return // frisch genug
	}
	tb, err := os.ReadFile(envOr("HOME", "/home/dev") + "/.claude/.credentials.json")
	if err != nil {
		return
	}
	var cred struct {
		ClaudeAiOauth struct {
			AccessToken string `json:"accessToken"`
		} `json:"claudeAiOauth"`
	}
	if json.Unmarshal(tb, &cred) != nil || cred.ClaudeAiOauth.AccessToken == "" {
		return
	}
	req, _ := http.NewRequest("GET", "https://api.anthropic.com/api/oauth/usage", nil)
	req.Header.Set("Authorization", "Bearer "+cred.ClaudeAiOauth.AccessToken)
	req.Header.Set("anthropic-beta", "oauth-2025-04-20")
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == 200 && len(body) > 10 {
		os.WriteFile(cache, body, 0644)
	}
}

// ---- /usage : Claude-Kontingent (selbst aktualisiert) + Ollama-Status ----
func usage(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	fetchClaudeUsage()
	cache := envOr("USAGE_CACHE", "/tmp/claude-usage-gate.json")
	if fi, err := os.Stat(cache); err == nil {
		out["claude_age_s"] = int(time.Since(fi.ModTime()).Seconds())
	}
	// Claude: der Usage-Gate-Cache (gerade aktualisiert)
	if b, err := os.ReadFile(cache); err == nil {
		var u struct {
			FiveHour struct {
				Utilization float64 `json:"utilization"`
				ResetsAt    string  `json:"resets_at"`
			} `json:"five_hour"`
			SevenDay struct {
				Utilization float64 `json:"utilization"`
				ResetsAt    string  `json:"resets_at"`
			} `json:"seven_day"`
		}
		if json.Unmarshal(b, &u) == nil {
			out["claude"] = map[string]any{
				"h5_pct": int(u.FiveHour.Utilization), "h5_reset": u.FiveHour.ResetsAt,
				"d7_pct": int(u.SevenDay.Utilization), "d7_reset": u.SevenDay.ResetsAt,
			}
		}
	}
	// Ollama: Erreichbarkeit (Kontingent gibt die API nicht her)
	oll := map[string]any{"reachable": false}
	c := &http.Client{Timeout: 3 * time.Second}
	if resp, err := c.Get(envOr("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/version"); err == nil {
		resp.Body.Close()
		oll["reachable"] = resp.StatusCode == 200
	}
	// w3-Status aus Marker (Worker schreibt /tmp/w3-status: working|paused)
	if b, err := os.ReadFile("/tmp/w3-status"); err == nil {
		oll["worker"] = strings.TrimSpace(string(b))
	}
	out["ollama"] = oll
	writeJSON(w, out)
}

func gui(w http.ResponseWriter, r *http.Request) {
	b, _ := guiFS.ReadFile("gui.html")
	w.Header().Set("Content-Type", "text/html")
	w.Write(b)
}

// ---- Ticket-Detailansicht: GET /ticket?id=N -> volle Zeile + Events + Triage ----
func ticketDetail(w http.ResponseWriter, r *http.Request) {
	var id int64
	fmt.Sscanf(r.URL.Query().Get("id"), "%d", &id)
	if id <= 0 {
		http.Error(w, "id?", 400)
		return
	}
	mu.Lock()
	defer mu.Unlock()
	out := map[string]any{}
	row := db.QueryRow(`SELECT id,type,title,descr,mechanic,state,worker_id,lease_exp,
	        retry_count,missing_prim,vocab_id,parent_id,priority,build_model,tokens,
	        created_at,updated_at FROM tickets WHERE id=?`, id)
	var t struct {
		ID, LeaseExp, VocabID, ParentID, Prio, Tokens, Created, Updated int64
		Retry                                                          int
		Type, Title, Descr, Mech, State, Worker, Missing, Model        string
	}
	if err := row.Scan(&t.ID, &t.Type, &t.Title, &t.Descr, &t.Mech, &t.State, &t.Worker,
		&t.LeaseExp, &t.Retry, &t.Missing, &t.VocabID, &t.ParentID, &t.Prio,
		&t.Model, &t.Tokens, &t.Created, &t.Updated); err != nil {
		http.Error(w, "ticket nicht gefunden", 404)
		return
	}
	out["ticket"] = map[string]any{"id": t.ID, "type": t.Type, "title": t.Title,
		"descr": t.Descr, "mechanic": t.Mech, "state": t.State, "worker_id": t.Worker,
		"lease_exp": t.LeaseExp, "retry_count": t.Retry, "missing_prim": t.Missing,
		"vocab_id": t.VocabID, "parent_id": t.ParentID, "priority": t.Prio,
		"build_model": t.Model, "tokens": t.Tokens, "created_at": t.Created, "updated_at": t.Updated}
	evs := []map[string]any{}
	if rows, err := db.Query(`SELECT ts,msg FROM events WHERE ticket_id=? ORDER BY id`, id); err == nil {
		for rows.Next() {
			var ts int64
			var msg string
			rows.Scan(&ts, &msg)
			evs = append(evs, map[string]any{"ts": ts, "msg": msg})
		}
		rows.Close()
	}
	out["events"] = evs
	// local_triage-Sidecar existiert erst nach dem ersten Lauf von local-triage-queue.sh
	if rows, err := db.Query(`SELECT ts,model,verdict,tier,evidence FROM local_triage WHERE ticket_id=?`, id); err == nil {
		for rows.Next() {
			var ts int64
			var model, verdict string
			var tier, evidence any
			rows.Scan(&ts, &model, &verdict, &tier, &evidence)
			out["local_triage"] = map[string]any{"ts": ts, "model": model,
				"verdict": verdict, "tier": tier, "evidence": evidence}
		}
		rows.Close()
	}
	writeJSON(w, out)
}

// ---- Local-GPU-Kill-Switch (Datei LOCAL_GPU_OFF, Home-Office-Modus) ----
// GET /local-gpu            -> {"local_gpu_enabled": bool}
// GET /local-gpu?set=off|on -> Datei anlegen/entfernen, neuer Zustand zurück
const localGPUOffFile = "/opt/development/magic-ops/LOCAL_GPU_OFF"

func localGPU(w http.ResponseWriter, r *http.Request) {
	switch r.URL.Query().Get("set") {
	case "off":
		os.WriteFile(localGPUOffFile, []byte("set via dispatcher GUI\n"), 0644)
	case "on":
		os.Remove(localGPUOffFile)
	}
	_, err := os.Stat(localGPUOffFile)
	writeJSON(w, map[string]any{"local_gpu_enabled": err != nil})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store") // sonst zeigt der Browser stale Zahlen
	json.NewEncoder(w).Encode(v)
}

// ---- Kanboard-Einmalimport (Subcommand: dispatcher-v4 import) ----
func kbCall(method string, params any) (any, error) {
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
	req, _ := http.NewRequest("POST", envOr("KB_URL", "https://kanboard.k.ezq.ch/jsonrpc.php"), strings.NewReader(string(body)))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(envOr("KB_USER", "admin"), envOr("KB_TOKEN", "fda650985874506da62a737b9a7befc39a5873735a253de80fa2d5ee5c20"))
	resp, err := (&http.Client{Timeout: 60 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var out struct{ Result any }
	json.NewDecoder(resp.Body).Decode(&out)
	return out.Result, nil
}

func colToState(col int, title string) (string, string) {
	typ := TypeCard
	if strings.HasPrefix(title, "[VOCAB]") {
		return TypeVocab, StVocab
	}
	if strings.HasPrefix(title, "DSL-SPLIT") {
		typ = TypeSplit
	}
	switch col {
	case 15:
		return typ, StTodo // working → todo (kein laufender Worker nach Migration)
	case 17:
		return typ, StDone
	case 20:
		return typ, StBlocked
	case 21:
		return typ, StWait
	default:
		return typ, StTodo
	}
}

var blockedRE = func() func(string) []string {
	return func(s string) []string {
		var ids []string
		for _, line := range strings.Split(s, "\n") {
			i := strings.Index(strings.ToUpper(line), "BLOCKED_CARDS:")
			if i < 0 {
				continue
			}
			for _, tok := range strings.FieldsFunc(line[i+14:], func(r rune) bool { return r < '0' || r > '9' }) {
				if tok != "" {
					ids = append(ids, tok)
				}
			}
		}
		return ids
	}
}()

func importKanboard() {
	res, err := kbCall("getAllTasks", map[string]any{"project_id": 2, "status_id": 1})
	if err != nil {
		log.Fatalf("kanboard: %v", err)
	}
	list, _ := res.([]any)
	log.Printf("import: %d offene Kanboard-Tickets", len(list))

	kbmap := map[int]int64{} // kanboard-id → v4-id
	for _, x := range list {
		m := x.(map[string]any)
		kbid := int(m["id"].(float64))
		title, _ := m["title"].(string)
		descr, _ := m["description"].(string)
		col := int(m["column_id"].(float64))
		typ, st := colToState(col, title)
		mech := parseMechanic(title)
		r, _ := db.Exec(`INSERT INTO tickets(type,title,descr,mechanic,state,created_at,updated_at)
		                 VALUES(?,?,?,?,?,?,?)`, typ, title, descr, mech, st, now(), now())
		v4id, _ := r.LastInsertId()
		kbmap[kbid] = v4id
	}
	log.Printf("import Pass1: %d Tickets", len(kbmap))

	// Pass 2: Blocked-Links (Desc + Kommentare)
	linked := 0
	for _, x := range list {
		m := x.(map[string]any)
		title, _ := m["title"].(string)
		if !strings.HasPrefix(title, "[VOCAB]") {
			continue
		}
		kbid := int(m["id"].(float64))
		v4vid := kbmap[kbid]
		descr, _ := m["description"].(string)
		blob := descr
		if cres, err := kbCall("getAllComments", map[string]any{"task_id": kbid}); err == nil {
			if cl, ok := cres.([]any); ok {
				for _, c := range cl {
					if cm, ok := c.(map[string]any); ok {
						if txt, ok := cm["comment"].(string); ok {
							blob += "\n" + txt
						}
					}
				}
			}
		}
		for _, cardStr := range blockedRE(blob) {
			var kbcard int
			fmt.Sscanf(cardStr, "%d", &kbcard)
			if v4card, ok := kbmap[kbcard]; ok {
				db.Exec(`UPDATE tickets SET vocab_id=? WHERE id=?`, v4vid, v4card)
				linked++
			}
		}
	}
	log.Printf("import Pass2: %d Blocked-Card-Links", linked)
	metaSet("kanboard_imported", fmt.Sprintf("%d", now()))
	rows, _ := db.Query(`SELECT state,COUNT(*) FROM tickets GROUP BY state`)
	defer rows.Close()
	for rows.Next() {
		var s string
		var n int
		rows.Scan(&s, &n)
		log.Printf("  %s: %d", s, n)
	}
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "import" {
		initDB()
		importKanboard()
		return
	}
	initDB()
	log.Printf("Dispatcher v4 — DB=%s port=%s", dbPath, Port)
	// Startup-Recovery: hängende working → todo
	db.Exec(`UPDATE tickets SET state='todo',worker_id='',lease_exp=0 WHERE state='working'`)
	if openCount() == 0 {
		log.Printf("Queue leer — initialer Ingest: +%d", ingestBacklog(500))
	}
	go reaper()
	go snapshotLoop()

	http.HandleFunc("/claim", claim)
	http.HandleFunc("/heartbeat", heartbeat)
	http.HandleFunc("/report", report)
	http.HandleFunc("/vocab-close", vocabClose)
	http.HandleFunc("/vocab-list", vocabList)
	http.HandleFunc("/vocab-fail", vocabFail)
	http.HandleFunc("/vocab-claim", vocabClaim)
	http.HandleFunc("/vocab-merge", vocabMerge)
	http.HandleFunc("/vocab-reset", vocabReset)
	http.HandleFunc("/stats", stats)
	http.HandleFunc("/tickets", tickets)
	http.HandleFunc("/action", action)
	http.HandleFunc("/history", history)
	http.HandleFunc("/usage", usage)
	http.HandleFunc("/local-gpu", localGPU)
	http.HandleFunc("/ticket", ticketDetail)
	http.HandleFunc("/", gui)
	log.Fatal(http.ListenAndServe(Port, nil))
}
