// Dispatcher v3 — synchrones Kanboard-Interface für Card-Worker.
// Kanboard ist die einzige Queue (Single Source of Truth); hier leben nur
// Leases (in-memory) und Retry-Zähler (state.json, überlebt Restarts).
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	Port           = ":9999"
	LeaseDuration  = 180 * time.Second // Heartbeat alle 60s → 2 verpasste Beats erlaubt
	ReaperInterval = 30 * time.Second
	MaxFail        = 3
	StateFile      = "/opt/development/magic-claude/services/dispatcher/state.json"
)

const (
	ProjectID   = 2
	ColNewBug   = 14
	ColWorking  = 15
	ColTodo     = 16
	ColFinish   = 17
	ColPriority = 19
	ColQueued   = 20
	ColWait     = 21
	KBUserID    = 1
)

var (
	kbURL   = envOr("KB_URL", "https://kanboard.k.ezq.ch/jsonrpc.php")
	kbUser  = envOr("KB_USER", "admin")
	kbToken = envOr("KB_TOKEN", "fda650985874506da62a737b9a7befc39a5873735a253de80fa2d5ee5c20")
)

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

type Lease struct {
	ID       int
	Title    string
	Desc     string
	WorkerID string
	Exp      time.Time
}

var (
	mu         sync.Mutex
	leases     = map[int]*Lease{} // task_id → lease
	retryCount = map[int]int{}    // task_id → fails über Läufe hinweg (persistiert)
)

// ---- state persistence (retry counts überleben Dispatcher-Restarts) ----
func loadState() {
	b, err := os.ReadFile(StateFile)
	if err != nil {
		return
	}
	json.Unmarshal(b, &retryCount)
}

func saveState() {
	b, _ := json.Marshal(retryCount)
	os.WriteFile(StateFile, b, 0644)
}

// ---- Kanboard JSON-RPC ----
func kbCall(method string, params interface{}) (interface{}, error) {
	body, _ := json.Marshal(map[string]interface{}{
		"jsonrpc": "2.0", "id": 1, "method": method, "params": params,
	})
	req, err := http.NewRequest("POST", kbURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(kbUser, kbToken)
	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var out struct {
		Result interface{} `json:"result"`
		Error  interface{} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	if out.Error != nil {
		return nil, fmt.Errorf("kanboard: %v", out.Error)
	}
	return out.Result, nil
}

// moveTask: moveTaskPosition BRAUCHT swimlane_id (Kanboard-Gotcha) und wirft
// unter Last "database is locked" — 3 Versuche wie im Bugfixer.
func moveTask(taskID, colID int) bool {
	for try := 1; try <= 3; try++ {
		res, err := kbCall("moveTaskPosition", map[string]interface{}{
			"project_id": ProjectID, "task_id": taskID,
			"column_id": colID, "position": 1, "swimlane_id": 0,
		})
		if err == nil && res == true {
			return true
		}
		time.Sleep(time.Duration(try) * 2 * time.Second)
	}
	log.Printf("WARN: move #%d -> col %d failed after 3 tries", taskID, colID)
	return false
}

func addComment(taskID int, content string) {
	kbCall("createComment", map[string]interface{}{
		"task_id": taskID, "user_id": KBUserID, "content": content,
	})
}

// nil-sichere Feld-Extraktion (description kann null sein → kein Panic)
func fInt(m map[string]interface{}, k string) int {
	if v, ok := m[k].(float64); ok {
		return int(v)
	}
	if s, ok := m[k].(string); ok {
		var n int
		fmt.Sscanf(s, "%d", &n)
		return n
	}
	return 0
}

func fStr(m map[string]interface{}, k string) string {
	if v, ok := m[k].(string); ok {
		return v
	}
	return ""
}

func openTasks() ([]map[string]interface{}, error) {
	res, err := kbCall("getAllTasks", map[string]interface{}{
		"project_id": ProjectID, "status_id": 1,
	})
	if err != nil {
		return nil, err
	}
	list, ok := res.([]interface{})
	if !ok {
		return nil, fmt.Errorf("unexpected getAllTasks result")
	}
	out := make([]map[string]interface{}, 0, len(list))
	for _, t := range list {
		if m, ok := t.(map[string]interface{}); ok {
			out = append(out, m)
		}
	}
	return out, nil
}

// ---- /claim (synchron: erst wenn das Ticket in working-on liegt, geht die
// Antwort raus; gleicher Worker mit gültiger Lease bekommt DASSELBE Ticket) ----
func handleClaim(w http.ResponseWriter, r *http.Request) {
	workerID := r.URL.Query().Get("worker")
	if workerID == "" {
		http.Error(w, "missing worker param", http.StatusBadRequest)
		return
	}

	mu.Lock()
	defer mu.Unlock()

	now := time.Now()
	for _, l := range leases {
		if l.WorkerID == workerID && now.Before(l.Exp) {
			l.Exp = now.Add(LeaseDuration)
			respondTicket(w, l, retryCount[l.ID], true)
			return
		}
	}

	tasks, err := openTasks()
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}

	// Kandidaten: new-bug vor todo, je älteste zuerst; [VOCAB] wird nie verteilt
	var cands []map[string]interface{}
	for _, t := range tasks {
		col := fInt(t, "column_id")
		if col != ColNewBug && col != ColTodo {
			continue
		}
		if strings.HasPrefix(fStr(t, "title"), "[VOCAB]") {
			continue
		}
		if _, leased := leases[fInt(t, "id")]; leased {
			continue // gerade an anderen Worker verliehen
		}
		cands = append(cands, t)
	}
	if len(cands) == 0 {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"id": ""})
		return
	}
	sort.Slice(cands, func(i, j int) bool {
		ci, cj := fInt(cands[i], "column_id"), fInt(cands[j], "column_id")
		if ci != cj {
			return ci == ColNewBug // new-bug vor todo
		}
		return fInt(cands[i], "id") < fInt(cands[j], "id")
	})

	t := cands[0]
	id := fInt(t, "id")

	moveTask(id, ColWorking) // synchron VOR der Antwort

	l := &Lease{
		ID: id, Title: fStr(t, "title"), Desc: fStr(t, "description"),
		WorkerID: workerID, Exp: now.Add(LeaseDuration),
	}
	leases[id] = l
	addComment(id, fmt.Sprintf("Dispatcher: claimed by worker %s at %s (fail count %d)", workerID, now.Format(time.RFC3339), retryCount[id]))
	log.Printf("claim: #%d -> %s (retry %d)", id, workerID, retryCount[id])
	respondTicket(w, l, retryCount[id], false)
}

func respondTicket(w http.ResponseWriter, l *Lease, retries int, resumed bool) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id": l.ID, "title": l.Title, "desc": l.Desc,
		"lease_exp": l.Exp.Unix(), "retry_count": retries, "resumed": resumed,
	})
}

// ---- /heartbeat ----
func handleHeartbeat(w http.ResponseWriter, r *http.Request) {
	var tid int
	fmt.Sscanf(r.URL.Query().Get("ticket"), "%d", &tid)
	mu.Lock()
	if l, ok := leases[tid]; ok {
		l.Exp = time.Now().Add(LeaseDuration)
	}
	mu.Unlock()
	w.Write([]byte(`{"ok":true}`))
}

// ---- /report ----
func handleReport(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		TicketID         string `json:"ticket_id"`
		WorkerID         string `json:"worker_id"`
		Status           string `json:"status"` // fixed | parked | retry
		Reason           string `json:"reason"` // missing_primitive | max_retry_reached
		MissingPrimitive string `json:"missing_primitive"`
		PrimitiveWhy     string `json:"primitive_why"`
		BlockedCardTitle string `json:"blocked_card_title"`
		Note             string `json:"note"`
		// Bundle-Teilfix: Karten, die wegen fehlendem Primitiv geskippt wurden
		Skipped []struct {
			Card      string `json:"card"`
			Primitive string `json:"primitive"`
			Why       string `json:"why"`
			Desc      string `json:"desc"`
		} `json:"skipped"`
	}
	body, _ := io.ReadAll(r.Body)
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	var tid int
	fmt.Sscanf(req.TicketID, "%d", &tid)

	mu.Lock()
	defer mu.Unlock()

	l, ok := leases[tid]
	if !ok {
		http.Error(w, "no lease for ticket", http.StatusConflict)
		return
	}
	// Ownership-Check: nur der Lease-Halter darf melden. Fremde/alte Prozesse
	// können die Lease nicht mehr zerstören (Vorfall 2026-07-19 Nacht).
	if l.WorkerID != req.WorkerID {
		log.Printf("report REJECTED: #%d von %q, Lease gehört %q", tid, req.WorkerID, l.WorkerID)
		http.Error(w, "lease owned by other worker", http.StatusConflict)
		return
	}

	switch {
	case req.Status == "fixed":
		delete(leases, tid)
		delete(retryCount, tid)
		saveState()
		moveTask(tid, ColFinish)
		addComment(tid, fmt.Sprintf("Dispatcher: fixed by %s, merged to main. %s", req.WorkerID, req.Note))
		log.Printf("report: #%d FIXED (%s)", tid, req.WorkerID)
		// Teilfix eines Bundles: geskippte Karten als eigene Tickets abspalten,
		// damit sie nicht im finished-Ticket verschwinden. Split-Ticket → col 20
		// (queued), [VOCAB] verweist auf das Split-Ticket → vocab-requeue holt
		// es nach dem Primitiv-Bau automatisch zurück.
		for _, sk := range req.Skipped {
			splitTitle := fmt.Sprintf("DSL-SPLIT: %s (from #%d)", sk.Card, tid)
			splitDesc := fmt.Sprintf("Split from bundle #%d: this card was skipped by the fixer because a primitive is missing (%s).\n\n%s", tid, sk.Primitive, sk.Desc)
			res, err := kbCall("createTask", map[string]interface{}{
				"project_id": ProjectID, "title": splitTitle,
				"description": splitDesc, "column_id": ColQueued,
			})
			if err != nil {
				log.Printf("ERROR split createTask (%s): %v", sk.Card, err)
				continue
			}
			splitID := 0
			if f, ok := res.(float64); ok {
				splitID = int(f)
			}
			vocabID := fileVocabTicket(sk.Primitive, sk.Why, splitID, splitTitle)
			addComment(tid, fmt.Sprintf("Dispatcher: skipped card %q split to #%d (blocked on %q, [VOCAB] #%d)", sk.Card, splitID, sk.Primitive, vocabID))
			log.Printf("split: #%d card %q -> #%d (vocab #%d)", tid, sk.Card, splitID, vocabID)
		}

	case req.Status == "parked" && req.Reason == "missing_primitive":
		delete(leases, tid)
		saveState()
		vocabID := fileVocabTicket(req.MissingPrimitive, req.PrimitiveWhy, tid, req.BlockedCardTitle)
		moveTask(tid, ColQueued)
		addComment(tid, fmt.Sprintf("Dispatcher: parked, missing primitive %q -> [VOCAB] #%d", req.MissingPrimitive, vocabID))
		log.Printf("report: #%d PARKED missing_primitive=%q -> vocab #%d", tid, req.MissingPrimitive, vocabID)

	case req.Status == "parked" && req.Reason == "max_retry_reached":
		delete(leases, tid)
		delete(retryCount, tid)
		saveState()
		moveTask(tid, ColWait)
		addComment(tid, fmt.Sprintf("Dispatcher: %d local attempts failed (worker %s) -> wait-triage. %s", MaxFail, req.WorkerID, req.Note))
		log.Printf("report: #%d PARKED max_retry -> wait-triage", tid)

	case req.Status == "retry" && req.Reason == "infra":
		// API-/Quota-Ausfall beim Worker: NICHT dem Ticket anlasten — zurück
		// zu todo ohne Fail-Zähler (sonst füllt eine erschöpfte Ollama-Quota
		// stundenlang die wait-triage mit unschuldigen Tickets).
		delete(leases, tid)
		moveTask(tid, ColTodo)
		addComment(tid, fmt.Sprintf("Dispatcher: worker %s API/Quota-Ausfall — zurück zu todo, kein Fail-Zähler. %s", req.WorkerID, req.Note))
		log.Printf("report: #%d RETRY (infra, kein Zähler)", tid)

	case req.Status == "retry":
		delete(leases, tid)
		retryCount[tid]++
		saveState()
		if retryCount[tid] >= MaxFail {
			moveTask(tid, ColWait)
			addComment(tid, fmt.Sprintf("Dispatcher: retry #%d >= MAX_FAIL -> wait-triage. %s", retryCount[tid], req.Note))
		} else {
			moveTask(tid, ColTodo)
			addComment(tid, fmt.Sprintf("Dispatcher: worker %s gave ticket back (retry %d). %s", req.WorkerID, retryCount[tid], req.Note))
		}
		log.Printf("report: #%d RETRY (count %d)", tid, retryCount[tid])

	default:
		http.Error(w, "unknown status/reason", http.StatusBadRequest)
		return
	}

	w.Write([]byte(`{"ok":true}`))
}

// ---- [VOCAB]-Ticket mit Dedup (wie Bugfixer: existiert ein offenes Ticket
// für dasselbe Primitiv, wird nur die blockierte Karte angehängt) ----
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

func fileVocabTicket(primitive, why string, blockedID int, blockedTitle string) int {
	key := normKey(primitive)
	if tasks, err := openTasks(); err == nil {
		for _, t := range tasks {
			title := fStr(t, "title")
			if strings.HasPrefix(title, "[VOCAB]") && strings.Contains(normKey(title), key) {
				existing := fInt(t, "id")
				addComment(existing, fmt.Sprintf("Also blocked: task #%d — %s\nBLOCKED_CARDS: %d", blockedID, blockedTitle, blockedID))
				log.Printf("vocab: appended blocked #%d to existing [VOCAB] #%d", blockedID, existing)
				return existing
			}
		}
	}
	desc := fmt.Sprintf(`Auto-filed by the dispatcher: a card could not be written as a handler because a reusable engine PRIMITIVE/HOOK is missing.

Missing capability: %s
Why: %s

This is an ENGINE/VOCABULARY change and is REVIEW-GATED (card workers skip [VOCAB] tickets). A human implements the primitive in backend/cardfns/lib_*.go (add a backend/game hook only if unavoidable) + a behavioral test.

PFLICHT nach dem Bau: scripts/skills/primitive-catalog.md um das neue Primitiv ergänzen (Signatur + Dauer-Tag [dur: ...]) — sonst kennt kein Worker das neue Primitiv!

Then CLOSE this ticket. Closing re-queues the blocked cards below (scripts/kanboard-vocab-requeue.sh).

BLOCKED_CARDS: %d`, primitive, why, blockedID)

	// createTask lehnt swimlane_id:0 ab — weglassen (Gotcha, anders als moveTaskPosition)
	res, err := kbCall("createTask", map[string]interface{}{
		"project_id": ProjectID, "title": "[VOCAB] " + primitive,
		"description": desc, "column_id": ColPriority, "priority": 3,
	})
	if err != nil {
		log.Printf("ERROR vocab createTask: %v", err)
		return 0
	}
	id := 0
	if f, ok := res.(float64); ok {
		id = int(f)
	}
	log.Printf("vocab: filed [VOCAB] #%d %q (blocked #%d)", id, primitive, blockedID)
	return id
}

// ---- Reaper: abgelaufene Leases → retry_count++ → todo oder wait-triage ----
func reaperLoop() {
	for range time.Tick(ReaperInterval) {
		mu.Lock()
		now := time.Now()
		for tid, l := range leases {
			if now.Before(l.Exp) {
				continue
			}
			delete(leases, tid)
			retryCount[tid]++
			saveState()
			if retryCount[tid] >= MaxFail {
				moveTask(tid, ColWait)
				addComment(tid, fmt.Sprintf("Dispatcher: lease expired (worker %s), fail #%d >= MAX_FAIL -> wait-triage", l.WorkerID, retryCount[tid]))
			} else {
				moveTask(tid, ColTodo)
				addComment(tid, fmt.Sprintf("Dispatcher: lease expired (worker %s), requeued (fail #%d)", l.WorkerID, retryCount[tid]))
			}
			log.Printf("reaper: #%d lease expired (%s), fail #%d", tid, l.WorkerID, retryCount[tid])
		}
		mu.Unlock()
	}
}

// ---- Startup-Recovery: Tickets, die ein Crash in working-on hinterließ ----
func recoverStuck() {
	tasks, err := openTasks()
	if err != nil {
		log.Printf("recovery: getAllTasks failed: %v", err)
		return
	}
	for _, t := range tasks {
		if fInt(t, "column_id") == ColWorking {
			id := fInt(t, "id")
			moveTask(id, ColTodo)
			addComment(id, "Dispatcher: recovered from working-on after restart -> todo")
			log.Printf("recovery: #%d working-on -> todo", id)
		}
	}
}

// ---- /status ----
func handleStatus(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	ls := make([]map[string]interface{}, 0, len(leases))
	for _, l := range leases {
		ls = append(ls, map[string]interface{}{
			"id": l.ID, "worker": l.WorkerID, "exp": l.Exp.Unix(), "title": l.Title,
		})
	}
	rc := map[int]int{}
	for k, v := range retryCount {
		rc[k] = v
	}
	mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{"leases": ls, "retry_counts": rc})
}

func main() {
	loadState()
	log.Printf("Dispatcher v3 — KB=%s project=%d", kbURL, ProjectID)
	recoverStuck()
	go reaperLoop()

	http.HandleFunc("/claim", handleClaim)
	http.HandleFunc("/heartbeat", handleHeartbeat)
	http.HandleFunc("/report", handleReport)
	http.HandleFunc("/status", handleStatus)
	log.Printf("listening on %s", Port)
	log.Fatal(http.ListenAndServe(Port, nil))
}
