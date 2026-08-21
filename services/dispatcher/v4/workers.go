package main

// Workers panel: GET /workers lists configured pipeline-lane workers
// (config/workers.json — the same file scripts/worker_ctl.py reads).
// "running" comes from `worker_ctl.py status --json` (tmux window / process
// presence) rather than recent ticket activity — a pace-gated worker (e.g.
// p1/pipe-codex sitting out a daily quota pause) is genuinely running but
// touches no ticket for a while, and deriving "running" from ticket
// recency (like stats()'s worker list does, a different purpose — that
// list answers "who's actively leasing a ticket right now") would show a
// false "stopped, click to start" and the click would then collide with
// the worker's own already-existing tmux window. Shelling out to
// worker_ctl.py rather than reimplementing the tmux check in Go keeps
// exactly one place that knows what "running" means for a worker.
// current_ticket/current_title (when present) are purely informational —
// the last ticket the worker touched — not a running/stopped signal.
//
// POST /action?do=start-worker&name=X launches a stopped one via
// worker_ctl.py, in a tmux window under the "dispatcher" session every
// other lane runs in — this process never holds the worker as its own
// child, so a dispatcher restart doesn't affect it.

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
)

var workersConfigPath = envOr("WORKERS_CONFIG", "/opt/development/magic-ops/config/workers.json")

type workerConfig struct {
	Name            string `json:"name"`
	Engine          string `json:"engine"`
	Model           string `json:"model"`
	BaseURL         string `json:"base_url,omitempty"`
	MaxTokens       int    `json:"max_tokens,omitempty"`
	ReasoningTokens int    `json:"reasoning_tokens,omitempty"`
	MaxTurns        int    `json:"max_turns,omitempty"`
	ClaudeMaxTurns  int    `json:"claude_max_turns,omitempty"`
	MaxNeedRounds   int    `json:"max_need_rounds,omitempty"`
}

func loadWorkerConfigs() ([]workerConfig, error) {
	raw, err := os.ReadFile(workersConfigPath)
	if err != nil {
		return nil, err
	}
	var cfgs []workerConfig
	if err := json.Unmarshal(raw, &cfgs); err != nil {
		return nil, err
	}
	return cfgs, nil
}

// workerCtlStatus shells out to `worker_ctl.py status --json` — the single
// place that knows how to determine whether a worker is actually running
// (tmux window or, for untracked stragglers, a matching process).
func workerCtlStatus() (map[string]bool, error) {
	out, err := exec.Command("python3", "/opt/development/magic-ops/scripts/worker_ctl.py",
		"status", "--json").Output()
	if err != nil {
		return nil, err
	}
	var rows []struct {
		Name    string `json:"name"`
		Running bool   `json:"running"`
	}
	if err := json.Unmarshal(out, &rows); err != nil {
		return nil, err
	}
	running := make(map[string]bool, len(rows))
	for _, r := range rows {
		running[r.Name] = r.Running
	}
	return running, nil
}

func workersHandler(w http.ResponseWriter, r *http.Request) {
	cfgs, err := loadWorkerConfigs()
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	running, err := workerCtlStatus()
	if err != nil {
		running = map[string]bool{} // fail open to "unknown" (shown as stopped), don't break the whole panel
	}

	// current_ticket/current_title: informational only, last ticket touched
	// in the last 30 min — same signal stats()'s worker list already uses,
	// just not treated as the running/stopped indicator here.
	mu.Lock()
	lastTouch := map[string]struct {
		ID    int64
		Title string
	}{}
	rows, _ := db.Query(`SELECT worker_id,id,title,MAX(updated_at) FROM tickets
	                     WHERE worker_id!='' AND updated_at>?
	                     GROUP BY worker_id`, now()-1800)
	for rows.Next() {
		var wid string
		var id int64
		var title string
		var ts int64
		rows.Scan(&wid, &id, &title, &ts)
		lastTouch[wid] = struct {
			ID    int64
			Title string
		}{id, title}
	}
	rows.Close()
	mu.Unlock()

	type out struct {
		workerConfig
		Running       bool   `json:"running"`
		CurrentTicket int64  `json:"current_ticket,omitempty"`
		CurrentTitle  string `json:"current_title,omitempty"`
	}
	result := make([]out, 0, len(cfgs))
	for _, c := range cfgs {
		o := out{workerConfig: c, Running: running[c.Name]}
		if l, ok := lastTouch[c.Name]; ok {
			o.CurrentTicket = l.ID
			o.CurrentTitle = l.Title
		}
		result = append(result, o)
	}
	b, _ := json.Marshal(result)
	w.Write(b)
}

// startWorker launches a configured-but-idle worker via worker_ctl.py —
// exactly the command an operator would type by hand. worker_ctl.py's own
// `start` already creates the detached tmux window (dispatcher session,
// window named after the worker) and returns immediately — this process
// never holds the worker as its own child, so a dispatcher restart
// (routine binary hot-swap) doesn't affect it, same as today.
func startWorker(name string) error {
	cfgs, err := loadWorkerConfigs()
	if err != nil {
		return err
	}
	found := false
	for _, c := range cfgs {
		if c.Name == name {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("unknown worker %q — not in %s", name, workersConfigPath)
	}
	cmd := exec.Command("python3", "/opt/development/magic-ops/scripts/worker_ctl.py", "start", name)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%s: %s", err, string(out))
	}
	return nil
}

// stopWorker kills a worker's whole process tree via worker_ctl.py stop —
// the tmux window first (owns the restart loop), then any stray leaf
// process, so nothing respawns behind it. This interrupts whatever ticket
// the worker is mid-flight on (its lease simply expires and the ticket
// gets reclaimed later) — a real, visible action, unlike start.
func stopWorker(name string) error {
	cfgs, err := loadWorkerConfigs()
	if err != nil {
		return err
	}
	found := false
	for _, c := range cfgs {
		if c.Name == name {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("unknown worker %q — not in %s", name, workersConfigPath)
	}
	cmd := exec.Command("python3", "/opt/development/magic-ops/scripts/worker_ctl.py", "stop", name)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%s: %s", err, string(out))
	}
	return nil
}
