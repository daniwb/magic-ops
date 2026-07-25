package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

// Treibt die echten HTTP-Handler in-process — deckt genau die im Smoke-Test
// ungetesteten Pfade ab: Dedup (der hing!), Ownership, Retry-Zähler, Requeue.

func setup(t *testing.T) {
	f, _ := os.CreateTemp("", "v4test-*.db")
	f.Close()
	dbPath = f.Name()
	os.Remove(dbPath)
	backlog = f.Name() + ".backlog"
	// Mini-Backlog: 20 Karten
	var b strings.Builder
	for i := 1; i <= 20; i++ {
		b.WriteString(fmt.Sprintf(`{"title":"DSL-BUNDLE: [draw] Card%d","description":"### Card%d"}`+"\n", i, i))
	}
	os.WriteFile(backlog, []byte(b.String()), 0644)
	initDB()
	db.Exec(`DELETE FROM tickets`)
	db.Exec(`DELETE FROM meta`)
	ingestBacklog(500)
	t.Cleanup(func() { db.Close(); os.Remove(dbPath); os.Remove(backlog) })
}

func doClaim(t *testing.T, worker string) (int64, bool) {
	rec := httptest.NewRecorder()
	claim(rec, httptest.NewRequest("GET", "/claim?worker="+worker, nil))
	var r struct {
		ID    json.Number `json:"id"`
		Title string      `json:"title"`
	}
	json.Unmarshal(rec.Body.Bytes(), &r)
	if r.ID == "" {
		return 0, false
	}
	id, _ := r.ID.Int64()
	return id, true
}

func doReport(body string) int {
	rec := httptest.NewRecorder()
	report(rec, httptest.NewRequest("POST", "/report", strings.NewReader(body)))
	return rec.Code
}

func state(id int64) string {
	var s string
	db.QueryRow(`SELECT state FROM tickets WHERE id=?`, id).Scan(&s)
	return s
}
func retryOf(id int64) int {
	var n int
	db.QueryRow(`SELECT retry_count FROM tickets WHERE id=?`, id).Scan(&n)
	return n
}
func count(where string) int {
	var n int
	db.QueryRow(`SELECT COUNT(*) FROM tickets WHERE ` + where).Scan(&n)
	return n
}

func TestFixedAndBundleSplit(t *testing.T) {
	setup(t)
	id, _ := doClaim(t, "w1")
	code := doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"w1","status":"fixed",
	  "skipped":[{"card":"SkipA","primitive":"prim-x","why":"gap","desc":"### SkipA"}]}`, id))
	if code != 200 {
		t.Fatalf("fixed report code %d", code)
	}
	if state(id) != "done" {
		t.Fatalf("ticket not done: %s", state(id))
	}
	if count(`type='split'`) != 1 {
		t.Fatalf("expected 1 split ticket, got %d", count(`type='split'`))
	}
	if count(`type='vocab'`) != 1 {
		t.Fatalf("expected 1 vocab ticket, got %d", count(`type='vocab'`))
	}
}

func TestVocabDedup(t *testing.T) {
	setup(t)
	// Zwei verschiedene Tickets melden dasselbe Primitiv unterschiedlich geschrieben
	id1, _ := doClaim(t, "a")
	if c := doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"a","status":"parked","reason":"missing_primitive","missing_primitive":"foo-bar","primitive_why":"x"}`, id1)); c != 200 {
		t.Fatalf("parked1 code %d", c)
	}
	id2, _ := doClaim(t, "b")
	// "foo bar" normalisiert == "foo-bar" → muss DEDUPEN (der Pfad, der hing)
	if c := doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"b","status":"parked","reason":"missing_primitive","missing_primitive":"foo bar","primitive_why":"y"}`, id2)); c != 200 {
		t.Fatalf("parked2 code %d", c)
	}
	if v := count(`type='vocab'`); v != 1 {
		t.Fatalf("dedup failed: expected 1 vocab, got %d", v)
	}
	if state(id1) != "blocked" || state(id2) != "blocked" {
		t.Fatalf("cards not blocked: %s %s", state(id1), state(id2))
	}
}

func TestOwnershipGuard(t *testing.T) {
	setup(t)
	id, _ := doClaim(t, "owner")
	code := doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"HACKER","status":"fixed"}`, id))
	if code != 409 {
		t.Fatalf("expected 409 for foreign worker, got %d", code)
	}
	if state(id) != "working" {
		t.Fatalf("ticket state changed by hacker: %s", state(id))
	}
}

func TestRetryCounterToWait(t *testing.T) {
	setup(t)
	var lastID int64
	for i := 1; i <= 3; i++ {
		id, ok := doClaim(t, "r")
		if !ok {
			t.Fatalf("claim %d failed", i)
		}
		lastID = id
		code := doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"r","status":"retry","note":"fail%d"}`, id, i))
		if code != 200 {
			t.Fatalf("retry %d code %d", i, code)
		}
		// nach retry ist es wieder todo (bis 3) — re-claim holt evtl. dasselbe (id-order)
		if i < 3 && state(id) != "todo" {
			t.Fatalf("after retry %d expected todo, got %s (rc=%d)", i, state(id), retryOf(id))
		}
	}
	if state(lastID) != "wait" {
		t.Fatalf("after 3 retries expected wait, got %s (rc=%d)", state(lastID), retryOf(lastID))
	}
}

func TestInfraRetryNoCounter(t *testing.T) {
	setup(t)
	id, _ := doClaim(t, "i")
	for i := 0; i < 5; i++ {
		doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"i","status":"retry","reason":"infra","note":"outage"}`, id))
		doClaim(t, "i") // re-claim (id-order → dasselbe)
	}
	if retryOf(id) != 0 {
		t.Fatalf("infra retries must not increment counter, got %d", retryOf(id))
	}
}

func TestVocabCloseRequeue(t *testing.T) {
	setup(t)
	// Karte blockieren
	id, _ := doClaim(t, "w")
	doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"w","status":"parked","reason":"missing_primitive","missing_primitive":"needthis","primitive_why":"z"}`, id))
	var vid int64
	db.QueryRow(`SELECT vocab_id FROM tickets WHERE id=?`, id).Scan(&vid)
	if vid == 0 {
		t.Fatal("card not linked to vocab")
	}
	// VOCAB schließen → Karte muss zurück zu todo
	rec := httptest.NewRecorder()
	vocabClose(rec, httptest.NewRequest("GET", fmt.Sprintf("/vocab-close?id=%d", vid), nil))
	if state(id) != "todo" {
		t.Fatalf("card not requeued after vocab-close: %s", state(id))
	}
	if state(vid) != "done" {
		t.Fatalf("vocab not closed: %s", state(vid))
	}
}

func TestStatsEndpoint(t *testing.T) {
	setup(t)
	rec := httptest.NewRecorder()
	stats(rec, httptest.NewRequest("GET", "/stats", nil))
	if rec.Code != 200 {
		t.Fatalf("stats code %d", rec.Code)
	}
	var s map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &s); err != nil {
		t.Fatalf("stats not JSON: %v", err)
	}
	if _, ok := s["states"]; !ok {
		t.Fatal("stats missing 'states'")
	}
}

var _ = http.StatusOK

func TestVocabListAndFail(t *testing.T) {
	setup(t)
	// zwei Karten blockieren auf verschiedene Primitive
	id1, _ := doClaim(t, "a")
	doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"a","status":"parked","reason":"missing_primitive","missing_primitive":"alpha","primitive_why":"x"}`, id1))
	id2, _ := doClaim(t, "b")
	doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"b","status":"parked","reason":"missing_primitive","missing_primitive":"beta","primitive_why":"y"}`, id2))

	rec := httptest.NewRecorder()
	vocabList(rec, httptest.NewRequest("GET", "/vocab-list", nil))
	var list []map[string]any
	json.Unmarshal(rec.Body.Bytes(), &list)
	if len(list) != 2 {
		t.Fatalf("expected 2 open vocab, got %d", len(list))
	}
	if list[0]["blocked"].(float64) != 1 {
		t.Fatalf("expected blocked=1 on first vocab, got %v", list[0]["blocked"])
	}
	// einen als failed markieren → verschwindet aus default-Liste
	vid := int64(list[0]["id"].(float64))
	rec = httptest.NewRecorder()
	vocabFail(rec, httptest.NewRequest("POST", fmt.Sprintf("/vocab-fail?id=%d&reason=engine-hook", vid), nil))
	rec = httptest.NewRecorder()
	vocabList(rec, httptest.NewRequest("GET", "/vocab-list", nil))
	json.Unmarshal(rec.Body.Bytes(), &list)
	if len(list) != 1 {
		t.Fatalf("failed vocab should be skipped, expected 1, got %d", len(list))
	}
	// mit ?all=1 wieder sichtbar
	rec = httptest.NewRecorder()
	vocabList(rec, httptest.NewRequest("GET", "/vocab-list?all=1", nil))
	json.Unmarshal(rec.Body.Bytes(), &list)
	if len(list) != 2 {
		t.Fatalf("all=1 should show 2, got %d", len(list))
	}
}

func TestVocabMerge(t *testing.T) {
	setup(t)
	// zwei Karten auf zwei verschiedene (aber semantisch gleiche) Primitive blockieren
	id1,_ := doClaim(t,"a")
	doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"a","status":"parked","reason":"missing_primitive","missing_primitive":"alpha-one","primitive_why":"x"}`,id1))
	id2,_ := doClaim(t,"b")
	doReport(fmt.Sprintf(`{"ticket_id":"%d","worker_id":"b","status":"parked","reason":"missing_primitive","missing_primitive":"alpha-two-different","primitive_why":"y"}`,id2))
	// vocab-ids ermitteln
	var v1,v2 int64
	db.QueryRow(`SELECT vocab_id FROM tickets WHERE id=?`,id1).Scan(&v1)
	db.QueryRow(`SELECT vocab_id FROM tickets WHERE id=?`,id2).Scan(&v2)
	if v1==v2 { t.Fatal("should be two distinct vocabs") }
	// v2 in v1 mergen
	rec:=httptest.NewRecorder()
	vocabMerge(rec,httptest.NewRequest("GET",fmt.Sprintf("/vocab-merge?from=%d&to=%d",v2,v1),nil))
	if rec.Code!=200 { t.Fatalf("merge code %d",rec.Code) }
	// v2 geschlossen, dessen Karte hängt jetzt an v1
	if state(v2)!="done" { t.Fatalf("dupe not closed: %s",state(v2)) }
	var vc int64; db.QueryRow(`SELECT vocab_id FROM tickets WHERE id=?`,id2).Scan(&vc)
	if vc!=v1 { t.Fatalf("card2 not moved to canonical: %d != %d",vc,v1) }
	// vocab-close v1 muss jetzt BEIDE Karten requeuen
	rec=httptest.NewRecorder()
	vocabClose(rec,httptest.NewRequest("GET",fmt.Sprintf("/vocab-close?id=%d",v1),nil))
	if state(id1)!="todo" || state(id2)!="todo" { t.Fatalf("both cards should requeue: %s %s",state(id1),state(id2)) }
}
