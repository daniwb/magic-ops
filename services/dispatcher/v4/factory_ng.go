package main

// Factory NG dashboard endpoints.  They deliberately keep the NG control
// plane separate from the legacy dispatcher queue: Factory NG has immutable
// TicketSpecs and supervised isolated-clone runs, not dispatcher rows.

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	factoryNGRoot        = "/opt/development/magic-ops"
	factoryNGWorkersPath = factoryNGRoot + "/config/factory-ng-workers.json"
	factoryNGHistoryPath = factoryNGRoot + "/state/factory-ng-card-history.jsonl"
	factoryNGRuntimePath = factoryNGRoot + "/state/factory-ng-runtime.json"
	openMagicCardDB      = "/opt/development/test/openmagic/backend/data/carddb"
	openMagicRoundReport = "/opt/development/test/openmagic/corpus/round_report.txt"
)

type factoryNGWorker struct {
	ID          string `json:"id"`
	Label       string `json:"label"`
	Enabled     bool   `json:"enabled"`
	Profile     string `json:"profile"`
	Model       string `json:"model"`
	UsagePolicy string `json:"usage_policy"`
	Work        string `json:"work"`
}

type factoryNGWorkerFile struct {
	Schema  string            `json:"schema"`
	Workers []factoryNGWorker `json:"workers"`
}

var factoryNGMu sync.Mutex

func loadFactoryNGWorkers() (factoryNGWorkerFile, error) {
	var config factoryNGWorkerFile
	raw, err := os.ReadFile(factoryNGWorkersPath)
	if err != nil {
		return config, err
	}
	if err := json.Unmarshal(raw, &config); err != nil {
		return config, err
	}
	if config.Schema != "factory-ng-workers/v1" {
		return config, fmt.Errorf("unexpected Factory NG workers schema %q", config.Schema)
	}
	return config, nil
}

func writeFactoryNGWorkers(config factoryNGWorkerFile) error {
	raw, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return err
	}
	tmp := factoryNGWorkersPath + ".tmp"
	if err := os.WriteFile(tmp, append(raw, '\n'), 0644); err != nil {
		return err
	}
	return os.Rename(tmp, factoryNGWorkersPath)
}

// factoryNGProfiles returns only the operator-relevant identity fields.  The
// profile JSON remains the source of truth for the adapter contract.
func factoryNGProfiles() []map[string]string {
	paths, _ := filepath.Glob(factoryNGRoot + "/docs/factory-ng/model-profiles/v1/*.json")
	profiles := make([]map[string]string, 0, len(paths))
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var p struct {
			ID      string `json:"id"`
			Version string `json:"version"`
			Adapter struct {
				Engine string `json:"engine"`
			} `json:"adapter"`
		}
		if json.Unmarshal(raw, &p) != nil || p.ID == "" || p.Version == "" {
			continue
		}
		profiles = append(profiles, map[string]string{
			"id": p.ID + "@" + p.Version, "engine": p.Adapter.Engine,
		})
	}
	sort.Slice(profiles, func(i, j int) bool { return profiles[i]["id"] < profiles[j]["id"] })
	return profiles
}

func factoryNGWorkersHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	factoryNGMu.Lock()
	defer factoryNGMu.Unlock()
	config, err := loadFactoryNGWorkers()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if r.Method == http.MethodGet {
		writeJSON(w, map[string]interface{}{
			"workers":  config.Workers,
			"profiles": factoryNGProfiles(),
			"note":     "Settings apply to the next supervised Factory NG cycle. They do not start legacy dispatcher lanes.",
		})
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	var change struct {
		ID      string `json:"id"`
		Enabled *bool  `json:"enabled"`
		Profile string `json:"profile"`
		Model   string `json:"model"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&change); err != nil {
		http.Error(w, "invalid worker update: "+err.Error(), http.StatusBadRequest)
		return
	}
	if len(change.ID) == 0 || len(change.ID) > 64 || len(change.Profile) > 160 || len(change.Model) > 160 {
		http.Error(w, "invalid worker update", http.StatusBadRequest)
		return
	}
	knownProfiles := map[string]bool{}
	for _, p := range factoryNGProfiles() {
		knownProfiles[p["id"]] = true
	}
	for i := range config.Workers {
		worker := &config.Workers[i]
		if worker.ID != change.ID {
			continue
		}
		if change.Enabled != nil {
			worker.Enabled = *change.Enabled
		}
		if change.Profile != "" {
			if !knownProfiles[change.Profile] {
				http.Error(w, "unknown Factory NG profile", http.StatusBadRequest)
				return
			}
			worker.Profile = change.Profile
		}
		if change.Model != "" {
			worker.Model = change.Model
		}
		if err := writeFactoryNGWorkers(config); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"ok": true, "worker": worker})
		return
	}
	http.Error(w, "unknown Factory NG worker", http.StatusNotFound)
}

// factoryNGStatus is intentionally about supervised NG execution only.  The
// legacy dispatcher has its own workers and queue; presenting those here as
// active NG work would make the control dashboard lie.  The forthcoming
// run-once harness will write factory-ng-runtime.json while it owns a ticket.
func factoryNGStatus(w http.ResponseWriter, r *http.Request) {
	config, err := loadFactoryNGWorkers()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	enabled := 0
	for _, worker := range config.Workers {
		if worker.Enabled {
			enabled++
		}
	}
	runtime := map[string]interface{}{}
	if raw, err := os.ReadFile(factoryNGRuntimePath); err == nil {
		json.Unmarshal(raw, &runtime)
	}
	running := factoryNGControllerRunning()
	state := "idle"
	message := "No supervised Factory NG ticket is running. Start the controller to produce fresh TicketSpecs."
	if running {
		state = "running"
		if value, ok := runtime["message"].(string); ok && value != "" {
			message = value
		}
	}
	active, ok := runtime["active"]
	if !ok {
		active = []interface{}{}
	}
	writeJSON(w, map[string]interface{}{
		"state": state, "symbol": "▶", "active": active,
		"enabled_workers": enabled, "message": message,
		"phase": runtime["phase"], "queued": runtime["queued"], "results": runtime["results"],
	})
}

func factoryNGControllerRunning() bool {
	out, err := exec.Command("tmux", "list-windows", "-t", "dispatcher", "-F", "#{window_name}").Output()
	if err != nil {
		return false
	}
	for _, name := range strings.Fields(string(out)) {
		if name == "factory-ng" {
			return true
		}
	}
	return false
}

// The controller persists in its own tmux window so a routine dispatcher
// binary restart neither aborts ticket production nor makes the dashboard
// claim that the process is still alive. Harness-owned integration and push
// are policy controlled; models themselves never receive that authority.
func factoryNGControl(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST required", http.StatusMethodNotAllowed)
		return
	}
	action := r.URL.Query().Get("action")
	switch action {
	case "start":
		if factoryNGControllerRunning() {
			writeJSON(w, map[string]interface{}{"ok": true, "state": "running", "message": "Factory NG controller is already running."})
			return
		}
		command := "cd " + factoryNGRoot + " && exec python3 scripts/factory-ng-controller.py >> state/factory-ng-controller.log 2>&1"
		out, err := exec.Command("tmux", "new-window", "-d", "-t", "dispatcher", "-n", "factory-ng", command).CombinedOutput()
		if err != nil {
			http.Error(w, fmt.Sprintf("could not start Factory NG controller: %s: %s", err, out), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"ok": true, "state": "running", "message": "Factory NG controller started."})
	case "stop":
		if !factoryNGControllerRunning() {
			writeJSON(w, map[string]interface{}{"ok": true, "state": "stopped", "message": "Factory NG controller is already stopped."})
			return
		}
		out, err := exec.Command("tmux", "kill-window", "-t", "dispatcher:factory-ng").CombinedOutput()
		if err != nil {
			http.Error(w, fmt.Sprintf("could not stop Factory NG controller: %s: %s", err, out), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"ok": true, "state": "stopped", "message": "Factory NG controller stopped."})
	default:
		http.Error(w, "action=start or action=stop required", http.StatusBadRequest)
	}
}

// factoryNGData exposes the existing receipt-derived renderer as structured
// data. Keeping this one command as the data source prevents a second,
// divergent interpretation of TicketSpecs and receipts in the web layer.
func factoryNGData(w http.ResponseWriter, r *http.Request) {
	out, err := exec.Command("python3", factoryNGRoot+"/scripts/factory-ng-dashboard.py", "--format", "json").Output()
	if err != nil {
		http.Error(w, "Factory NG receipt read failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(out)
}

type factoryCardSnapshot struct {
	Ts               int64 `json:"ts"`
	CorpusTotal      int   `json:"corpus_total"`
	CorpusClassified int   `json:"corpus_classified"`
	Imported         int   `json:"imported"`
	Auto             int   `json:"auto"`
	Review           int   `json:"review"`
	Manual           int   `json:"manual"`
}

func currentFactoryCardSnapshot() (factoryCardSnapshot, error) {
	result := factoryCardSnapshot{Ts: time.Now().Unix()}
	entries, err := os.ReadDir(openMagicCardDB)
	if err != nil {
		return result, err
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") || strings.HasPrefix(entry.Name(), "_") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(openMagicCardDB, entry.Name()))
		if err != nil {
			continue
		}
		var cards map[string]struct {
			Status string `json:"status"`
		}
		if json.Unmarshal(raw, &cards) != nil {
			continue
		}
		for _, card := range cards {
			result.Imported++
			switch card.Status {
			case "auto":
				result.Auto++
			case "review":
				result.Review++
			case "manual":
				result.Manual++
			}
		}
	}
	if raw, err := os.ReadFile(openMagicRoundReport); err == nil {
		re := regexp.MustCompile(`(?m)^cards:\s+(\d+).*\ncards fully classified:\s+(\d+)`)
		if hit := re.FindStringSubmatch(string(raw)); len(hit) == 3 {
			fmt.Sscanf(hit[1], "%d", &result.CorpusTotal)
			fmt.Sscanf(hit[2], "%d", &result.CorpusClassified)
		}
	}
	return result, nil
}

func cardHistory(snapshot factoryCardSnapshot) (*factoryCardSnapshot, error) {
	if err := os.MkdirAll(filepath.Dir(factoryNGHistoryPath), 0755); err != nil {
		return nil, err
	}
	var rows []factoryCardSnapshot
	if f, err := os.Open(factoryNGHistoryPath); err == nil {
		scanner := bufio.NewScanner(f)
		for scanner.Scan() {
			var row factoryCardSnapshot
			if json.Unmarshal(scanner.Bytes(), &row) == nil {
				rows = append(rows, row)
			}
		}
		f.Close()
	}
	// Select the old baseline before appending this reading.  On the first
	// visit there is no 24-hour comparison yet; reporting a fabricated zero
	// would make an unmeasured dashboard look like no cards changed.
	cutoff := snapshot.Ts - 86400
	var baseline *factoryCardSnapshot
	for _, row := range rows {
		if row.Ts >= cutoff {
			copy := row
			baseline = &copy
			break
		}
	}

	// One point every 15 minutes is enough for a useful daily trend and avoids
	// recording a row for every browser refresh.
	if len(rows) == 0 || snapshot.Ts-rows[len(rows)-1].Ts >= 900 {
		f, err := os.OpenFile(factoryNGHistoryPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
		if err != nil {
			return nil, err
		}
		encoded, _ := json.Marshal(snapshot)
		_, err = f.Write(append(encoded, '\n'))
		f.Close()
		if err != nil {
			return nil, err
		}
		rows = append(rows, snapshot)
	}
	return baseline, nil
}

func factoryNGCards(w http.ResponseWriter, r *http.Request) {
	snapshot, err := currentFactoryCardSnapshot()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	baseline, err := cardHistory(snapshot)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	response := map[string]interface{}{"current": snapshot, "baseline_24h": baseline}
	if baseline != nil {
		response["change_24h"] = map[string]int{
			"imported": snapshot.Imported - baseline.Imported,
			"auto":     snapshot.Auto - baseline.Auto,
			"review":   snapshot.Review - baseline.Review,
			"manual":   snapshot.Manual - baseline.Manual,
		}
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, response)
}
