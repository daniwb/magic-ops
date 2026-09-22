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
	"strconv"
	"strings"
	"sync"
	"time"
)

var (
	factoryNGRoot         = envOr("FACTORY_NG_ROOT", "/opt/development/magic-ops")
	factoryNGHistoryPath  = factoryNGRoot + "/state/factory-ng-card-history.jsonl"
	factoryNGRuntimePath  = factoryNGRoot + "/state/factory-ng-runtime.json"
	factoryNGCacheStatus  = factoryNGRoot + "/state/go-cache-maintenance.json"
	factoryNGCoveragePath = factoryNGRoot + "/state/factory-ng-coverage.json"
	factoryNGGalaxyPath   = factoryNGRoot + "/state/factory-ng-galaxy.json"
	openMagicRoot         = envOr("OPENMAGIC_ROOT", "/opt/development/test/openmagic")
	openMagicCardDB       = openMagicRoot + "/backend/data/carddb"
	openMagicRoundReport  = openMagicRoot + "/corpus/round_report.txt"
	magicNewRoot          = envOr("MAGIC_NEW_ROOT", "/opt/development/magic-new")
	goCacheRoot           = envOr("GO_CACHE_ROOT", "/opt/development/.gocache-magic")
)

// factoryNGServeSnapshot proxies a background-generated JSON snapshot file
// straight to the client. The snapshot scripts (factory-ng-coverage-snapshot.py,
// factory-ng-galaxy-snapshot.py) own regeneration on their own schedule; this
// handler never computes anything itself, it just serves whatever is on disk
// right now so the page can poll it cheaply.
func factoryNGServeSnapshot(path string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		raw, err := os.ReadFile(path)
		if err != nil {
			writeJSON(w, map[string]interface{}{"generated_at": nil, "error": "snapshot not generated yet"})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		w.Write(raw)
	}
}

type factoryNGWorker struct {
	ID                string   `json:"id"`
	Label             string   `json:"label"`
	Enabled           bool     `json:"enabled"`
	Profile           string   `json:"profile"`
	AlternateProfiles []string `json:"alternate_profiles,omitempty"`
	PreferEngine      bool     `json:"prefer_engine,omitempty"`
	RoutingMode       string   `json:"routing_mode,omitempty"`
	Model             string   `json:"model"`
	UsagePolicy       string   `json:"usage_policy"`
	WeeklyGateMode    string   `json:"weekly_gate_mode,omitempty"`
	WeeklyGatePct     int      `json:"weekly_gate_pct,omitempty"`
	Work              string   `json:"work"`
}

type factoryNGWorkerFile struct {
	Schema  string            `json:"schema"`
	Workers []factoryNGWorker `json:"workers"`
}

var (
	factoryNGMu               sync.Mutex
	factoryNGCodexUsageMu     sync.Mutex
	factoryNGWorkersPath      = factoryNGRoot + "/config/factory-ng-workers.json"
	factoryNGWorkerPausesPath = factoryNGRoot + "/state/factory-ng-worker-pauses.json"
)

type factoryNGWorkerPauseFile struct {
	Schema  string                            `json:"schema"`
	Workers map[string]map[string]interface{} `json:"workers"`
}

func loadFactoryNGWorkerPauses() factoryNGWorkerPauseFile {
	value := factoryNGWorkerPauseFile{Schema: "factory.ng-worker-pauses/v1", Workers: map[string]map[string]interface{}{}}
	raw, err := os.ReadFile(factoryNGWorkerPausesPath)
	if err == nil {
		_ = json.Unmarshal(raw, &value)
	}
	if value.Workers == nil {
		value.Workers = map[string]map[string]interface{}{}
	}
	return value
}

func writeFactoryNGWorkerPauses(value factoryNGWorkerPauseFile) error {
	raw, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	tmp := factoryNGWorkerPausesPath + ".tmp"
	if err := os.WriteFile(tmp, append(raw, '\n'), 0644); err != nil {
		return err
	}
	return os.Rename(tmp, factoryNGWorkerPausesPath)
}

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
		ID             string  `json:"id"`
		Enabled        *bool   `json:"enabled"`
		Profile        string  `json:"profile"`
		Model          string  `json:"model"`
		RoutingMode    *string `json:"routing_mode"`
		WeeklyGateMode string  `json:"weekly_gate_mode"`
		WeeklyGatePct  *int    `json:"weekly_gate_pct"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&change); err != nil {
		http.Error(w, "invalid worker update: "+err.Error(), http.StatusBadRequest)
		return
	}
	if len(change.ID) == 0 || len(change.ID) > 64 || len(change.Profile) > 160 || len(change.Model) > 160 {
		http.Error(w, "invalid worker update", http.StatusBadRequest)
		return
	}
	if change.WeeklyGateMode != "" && change.WeeklyGateMode != "paced" && change.WeeklyGateMode != "fixed" && change.WeeklyGateMode != "none" {
		http.Error(w, "weekly gate mode must be paced, fixed, or none", http.StatusBadRequest)
		return
	}
	if change.RoutingMode != nil && *change.RoutingMode != "auto" && *change.RoutingMode != "map" && *change.RoutingMode != "engine" {
		http.Error(w, "routing mode must be auto, map, or engine", http.StatusBadRequest)
		return
	}
	if change.WeeklyGatePct != nil && (*change.WeeklyGatePct < 1 || *change.WeeklyGatePct > 100) {
		http.Error(w, "weekly gate percentage must be between 1 and 100", http.StatusBadRequest)
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
		if change.RoutingMode != nil {
			worker.RoutingMode = *change.RoutingMode
		}
		if change.WeeklyGateMode != "" {
			if worker.UsagePolicy == "unmetered" {
				http.Error(w, "weekly gates apply only to metered workers", http.StatusBadRequest)
				return
			}
			worker.WeeklyGateMode = change.WeeklyGateMode
		}
		if change.WeeklyGatePct != nil {
			worker.WeeklyGatePct = *change.WeeklyGatePct
		}
		// Codex workers share an account and the dashboard has one Codex limit
		// control. Apply that control to every Codex lease, including disabled
		// workers, without changing their enabled state or execution profile.
		if worker.ID == "codex" && (change.WeeklyGateMode != "" || change.WeeklyGatePct != nil) {
			for sibling := range config.Workers {
				if config.Workers[sibling].UsagePolicy == "codex-weekly" {
					config.Workers[sibling].WeeklyGateMode = worker.WeeklyGateMode
					config.Workers[sibling].WeeklyGatePct = worker.WeeklyGatePct
				}
			}
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

func factoryNGWorkerPause(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST required", http.StatusMethodNotAllowed)
		return
	}
	var change struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&change); err != nil {
		http.Error(w, "invalid worker resume: "+err.Error(), http.StatusBadRequest)
		return
	}
	if change.ID == "" || len(change.ID) > 64 || strings.ContainsAny(change.ID, "/\\ \t\r\n") {
		http.Error(w, "invalid worker id", http.StatusBadRequest)
		return
	}
	factoryNGMu.Lock()
	defer factoryNGMu.Unlock()
	value := loadFactoryNGWorkerPauses()
	if _, ok := value.Workers[change.ID]; !ok {
		writeJSON(w, map[string]interface{}{"ok": true, "worker": change.ID, "state": "available"})
		return
	}
	delete(value.Workers, change.ID)
	if err := writeFactoryNGWorkerPauses(value); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, map[string]interface{}{"ok": true, "worker": change.ID, "state": "available", "message": "Authentication hold cleared. A new OAuth failure will pause the worker again without charging the ticket."})
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
	pauseFile := loadFactoryNGWorkerPauses()
	workerPauses := make([]map[string]interface{}, 0, len(pauseFile.Workers))
	for _, pause := range pauseFile.Workers {
		workerPauses = append(workerPauses, pause)
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
	cacheMaintenance := map[string]interface{}{"state": "idle", "cache_path": goCacheRoot}
	if raw, err := os.ReadFile(factoryNGCacheStatus); err == nil {
		_ = json.Unmarshal(raw, &cacheMaintenance)
	}
	writeJSON(w, map[string]interface{}{
		"state": state, "symbol": "▶", "active": active,
		"enabled_workers": enabled, "message": message,
		"phase": runtime["phase"], "queued": runtime["queued"], "deferred": runtime["deferred"],
		"queue": runtime["queue"], "results": runtime["results"],
		"worker_pauses": workerPauses, "authentication_recovery": runtime["authentication_recovery"],
		"updated_at":        runtime["updated_at"],
		"cache_maintenance": cacheMaintenance,
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
		if err := os.Remove(factoryNGRoot + "/state/factory-ng-paused"); err != nil && !os.IsNotExist(err) {
			http.Error(w, "could not clear operator pause: "+err.Error(), http.StatusInternalServerError)
			return
		}
		if factoryNGControllerRunning() {
			writeJSON(w, map[string]interface{}{"ok": true, "state": "running", "message": "Factory NG controller is already running."})
			return
		}
		command := "exec bash " + factoryNGRoot + "/launchers/launch-factory-ng.sh"
		out, err := exec.Command("tmux", "new-window", "-d", "-t", "dispatcher", "-n", "factory-ng", command).CombinedOutput()
		if err != nil {
			http.Error(w, fmt.Sprintf("could not start Factory NG controller: %s: %s", err, out), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"ok": true, "state": "running", "message": "Factory NG controller started."})
	case "stop":
		if err := os.WriteFile(factoryNGRoot+"/state/factory-ng-paused", []byte("operator paused Factory NG\n"), 0644); err != nil {
			http.Error(w, "could not retain operator pause: "+err.Error(), http.StatusInternalServerError)
			return
		}
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

// factoryNGDetail returns one immutable dashboard artifact on demand.  The
// overview stays compact, while the modal can still show the complete JSON
// without embedding every receipt and TicketSpec in the main response.
func factoryNGDetail(w http.ResponseWriter, r *http.Request) {
	relative := filepath.Clean(strings.TrimSpace(r.URL.Query().Get("path")))
	allowed := (strings.HasPrefix(relative, "docs/factory-ng/tickets/") ||
		strings.HasPrefix(relative, "docs/factory-ng/runs/") ||
		strings.HasPrefix(relative, "docs/factory-ng/measurements/"))
	if !allowed || relative == "." || filepath.IsAbs(relative) || strings.Contains(relative, "..") || filepath.Ext(relative) != ".json" {
		http.Error(w, "invalid Factory NG artifact path", http.StatusBadRequest)
		return
	}
	full := filepath.Join(factoryNGRoot, relative)
	info, err := os.Stat(full)
	if err != nil || !info.Mode().IsRegular() {
		http.Error(w, "Factory NG artifact not found", http.StatusNotFound)
		return
	}
	if info.Size() > 4<<20 {
		http.Error(w, "Factory NG artifact is too large for the dashboard", http.StatusRequestEntityTooLarge)
		return
	}
	raw, err := os.ReadFile(full)
	if err != nil || !json.Valid(raw) {
		http.Error(w, "Factory NG artifact is not readable JSON", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(raw)
}

func factoryQuotaBounds(now, reset time.Time, days, target int) (int, int, time.Time) {
	if reset.IsZero() || days < 1 {
		return 0, 0, time.Time{}
	}
	window := time.Duration(days) * 24 * time.Hour
	start := reset.Add(-window)
	elapsed := now.Sub(start)
	if elapsed < 0 {
		elapsed = 0
	}
	day := int(elapsed/(24*time.Hour)) + 1
	if day > days {
		day = days
	}
	allowed := ((day * target * 10 / days) + 5) / 10
	if allowed > target {
		allowed = target
	}
	next := start.Add(time.Duration(day) * 24 * time.Hour)
	if next.After(reset) {
		next = reset
	}
	return day, allowed, next
}

func factoryWeeklyGate(config factoryNGWorkerFile, workerID, fallbackMode string) (string, int) {
	mode, percentage := fallbackMode, 95
	for _, worker := range config.Workers {
		if worker.ID != workerID {
			continue
		}
		if worker.WeeklyGateMode == "paced" || worker.WeeklyGateMode == "fixed" || worker.WeeklyGateMode == "none" {
			mode = worker.WeeklyGateMode
		}
		if worker.WeeklyGatePct >= 1 && worker.WeeklyGatePct <= 100 {
			percentage = worker.WeeklyGatePct
		}
		break
	}
	return mode, percentage
}

func factoryLimitInt(name string, fallback int) int {
	value, err := strconv.Atoi(strings.TrimSpace(os.Getenv(name)))
	if err != nil {
		return fallback
	}
	return value
}

func factoryCacheAge(path string, now time.Time) int64 {
	info, err := os.Stat(path)
	if err != nil {
		return -1
	}
	age := int64(now.Sub(info.ModTime()).Seconds())
	if age < 0 {
		return 0
	}
	return age
}

func factoryUnixMarker(path string) int64 {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0
	}
	value, _ := strconv.ParseInt(strings.TrimSpace(string(raw)), 10, 64)
	return value
}

// fetchCodexUsage keeps the dashboard's cache current independently of the
// Codex worker.  The pace gate also refreshes this file, but a disabled worker
// never reaches that gate and used to leave the dashboard showing the last
// pre-reset percentage indefinitely.
func fetchCodexUsage(now time.Time) bool {
	cache := envOr("CODEX_USAGE_CACHE", "/tmp/codex-usage-gate.json")
	ttl := time.Duration(factoryLimitInt("CODEX_USAGE_GATE_TTL", 180)) * time.Second
	if ttl <= 0 {
		ttl = 180 * time.Second
	}
	isFresh := func() bool {
		info, err := os.Stat(cache)
		if err != nil {
			return false
		}
		age := now.Sub(info.ModTime())
		return age >= 0 && age < ttl
	}
	if isFresh() {
		return true
	}

	factoryNGCodexUsageMu.Lock()
	defer factoryNGCodexUsageMu.Unlock()
	if isFresh() {
		return true
	}

	fetcher := envOr("CODEX_USAGE_FETCH", factoryNGRoot+"/scripts/codex-usage-fetch.py")
	body, err := exec.Command("timeout", "20", "python3", fetcher, "--timeout", "15").Output()
	if err != nil {
		return false
	}
	var sample struct {
		UsedPct *float64 `json:"used_pct"`
	}
	if json.Unmarshal(body, &sample) != nil || sample.UsedPct == nil || *sample.UsedPct < 0 || *sample.UsedPct > 100 {
		return false
	}

	tmp, err := os.CreateTemp(filepath.Dir(cache), ".codex-usage-*.tmp")
	if err != nil {
		return false
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if err := tmp.Chmod(0644); err != nil {
		tmp.Close()
		return false
	}
	if _, err := tmp.Write(body); err != nil {
		tmp.Close()
		return false
	}
	if err := tmp.Close(); err != nil {
		return false
	}
	return os.Rename(tmpPath, cache) == nil
}

// Keep the primary account cards while exposing each worker's own dispatch gate.
func factoryQuotaWorkerIDs(config factoryNGWorkerFile, primary, policy string) []string {
	ids := []string{primary}
	for _, worker := range config.Workers {
		if worker.ID != primary && worker.UsagePolicy == policy {
			ids = append(ids, worker.ID)
		}
	}
	return ids
}

// factoryNGLimits presents the exact quota concepts used by the worker gates
// as structured data.  In particular, account headroom and currently unlocked
// pacing headroom remain separate so the dashboard cannot call both
// "remaining" and imply that a paused worker may dispatch.
func factoryNGLimits(w http.ResponseWriter, r *http.Request) {
	now := time.Now()
	result := map[string]interface{}{"updated_at": now.UTC().Format(time.RFC3339)}
	workerConfig, _ := loadFactoryNGWorkers()

	claudeCache := envOr("USAGE_CACHE", "/tmp/claude-usage-gate.json")
	claudeAge := factoryCacheAge(claudeCache, now)
	var claude struct {
		FiveHour struct {
			Utilization float64 `json:"utilization"`
			ResetsAt    string  `json:"resets_at"`
		} `json:"five_hour"`
		SevenDay struct {
			Utilization float64 `json:"utilization"`
			ResetsAt    string  `json:"resets_at"`
		} `json:"seven_day"`
	}
	if raw, err := os.ReadFile(claudeCache); err == nil && json.Unmarshal(raw, &claude) == nil {
		for _, workerID := range factoryQuotaWorkerIDs(workerConfig, "claude", "claude-weekly") {
			shortReset, _ := time.Parse(time.RFC3339Nano, claude.FiveHour.ResetsAt)
			weeklyReset, _ := time.Parse(time.RFC3339Nano, claude.SevenDay.ResetsAt)
			weeklyMode, weeklyPct := factoryWeeklyGate(workerConfig, workerID, "paced")
			day, unlocked, nextUnlock := factoryQuotaBounds(now, weeklyReset, 7, min(factoryLimitInt("PACE_TARGET_PCT", 100), weeklyPct))
			effectiveWeeklyCeiling := unlocked
			if weeklyMode == "fixed" {
				effectiveWeeklyCeiling = weeklyPct
			} else if weeklyMode == "none" {
				effectiveWeeklyCeiling = 100
			}
			location, err := time.LoadLocation("Europe/Zurich")
			if err != nil {
				location = time.UTC
			}
			hour := now.In(location).Hour()
			shortCeiling := factoryLimitInt("PACE_HARD5", 95)
			if hour >= 23 || hour < 6 {
				shortCeiling = 100
			}
			shortUsed, weeklyUsed := int(claude.FiveHour.Utilization), int(claude.SevenDay.Utilization)
			status, reason, resume := "available", "within both active limits", time.Time{}
			fresh := claudeAge >= 0 && claudeAge < 1800
			offUntil := time.Unix(factoryUnixMarker(envOr("PACE_OFF_FILE", factoryNGRoot+"/state/factory-ng-pace-"+workerID+".until")), 0)
			if !fresh {
				status, reason = "unknown", "usage data is stale; the worker gate decides fail-open independently"
			} else if shortUsed >= shortCeiling {
				status, reason, resume = "paused", "5-hour safety ceiling reached", shortReset
			} else if weeklyMode == "paced" && offUntil.After(now) {
				status, reason, resume = "paused", "weekly pacing tranche exhausted", offUntil
			} else if weeklyMode == "paced" && weeklyUsed >= unlocked && unlocked > 0 {
				status, reason, resume = "paused", "weekly pacing tranche exhausted", nextUnlock
			} else if weeklyMode == "fixed" && weeklyUsed >= weeklyPct {
				status, reason, resume = "paused", "fixed weekly usage ceiling reached", weeklyReset
			} else if weeklyMode == "none" {
				status, reason = "available", "weekly gate disabled; 5-hour safety ceiling remains active"
			}
			nextUnlockText := ""
			if weeklyMode == "paced" {
				nextUnlockText = nextUnlock.UTC().Format(time.RFC3339)
			}
			result[workerID] = map[string]interface{}{
				"status": status, "reason": reason, "cache_age_s": claudeAge,
				"short_used_pct": shortUsed, "short_remaining_pct": max(0, 100-shortUsed),
				"short_ceiling_pct": shortCeiling, "short_reset": shortReset.UTC().Format(time.RFC3339),
				"weekly_used_pct": weeklyUsed, "weekly_remaining_pct": max(0, 100-weeklyUsed),
				"weekly_unlocked_pct": unlocked, "weekly_headroom_pct": max(0, effectiveWeeklyCeiling-weeklyUsed),
				"weekly_day": day, "weekly_reset": weeklyReset.UTC().Format(time.RFC3339),
				"next_unlock": nextUnlockText, "resume_at": resume.UTC().Format(time.RFC3339),
				"weekly_gate_mode": weeklyMode, "weekly_gate_pct": weeklyPct,
				"weekly_effective_ceiling_pct": effectiveWeeklyCeiling,
			}
		}
	}

	// Unlike worker-driven refresh, this remains active while Codex is disabled.
	// A fetch failure preserves the old cache and the response marks it stale.
	fetchCodexUsage(now)
	codexCache := envOr("CODEX_USAGE_CACHE", "/tmp/codex-usage-gate.json")
	codexAge := factoryCacheAge(codexCache, now)
	var codex struct {
		UsedPct           *float64 `json:"used_pct"`
		ResetsAt          int64    `json:"resets_at"`
		WindowMins        int      `json:"window_mins"`
		SecondaryUsedPct  *float64 `json:"secondary_used_pct"`
		SecondaryResetsAt *int64   `json:"secondary_resets_at"`
		PlanType          string   `json:"plan_type"`
	}
	if raw, err := os.ReadFile(codexCache); err == nil && json.Unmarshal(raw, &codex) == nil && codex.UsedPct != nil {
		for _, workerID := range factoryQuotaWorkerIDs(workerConfig, "codex", "codex-weekly") {
			used := int(*codex.UsedPct)
			windowMins := codex.WindowMins
			if windowMins <= 0 {
				windowMins = 10080
			}
			windowDays := max(1, windowMins/(24*60))
			reset := time.Unix(codex.ResetsAt, 0).UTC()
			weeklyMode, weeklyPct := factoryWeeklyGate(workerConfig, workerID, "none")
			day, unlocked, nextUnlock := factoryQuotaBounds(now, reset, windowDays, min(factoryLimitInt("PACE_TARGET_PCT", 100), weeklyPct))
			effectiveWeeklyCeiling := unlocked
			if weeklyMode == "fixed" {
				effectiveWeeklyCeiling = weeklyPct
			} else if weeklyMode == "none" {
				effectiveWeeklyCeiling = 100
			}
			fresh := codexAge >= 0 && codexAge < 1800
			status, reason, resume := "available", "within configured weekly gate", time.Time{}
			if !fresh {
				status, reason = "unknown", "usage data is stale; the worker gate decides fail-open independently"
			} else if weeklyMode == "paced" && used >= unlocked {
				status, reason, resume = "paused", "weekly pacing tranche exhausted", nextUnlock
			} else if weeklyMode == "fixed" && used >= weeklyPct {
				status, reason, resume = "paused", "fixed weekly usage ceiling reached", reset
			} else if weeklyMode != "none" && codex.SecondaryUsedPct != nil && int(*codex.SecondaryUsedPct) >= factoryLimitInt("PACE_HARD_SECONDARY", 95) {
				status, reason = "paused", "secondary capacity safety ceiling reached"
				if codex.SecondaryResetsAt != nil {
					resume = time.Unix(*codex.SecondaryResetsAt, 0).UTC()
				}
			} else if weeklyMode == "none" {
				status, reason = "available", "weekly gate disabled; provider capacity may be fully used"
			}
			nextUnlockText := ""
			if weeklyMode == "paced" {
				nextUnlockText = nextUnlock.UTC().Format(time.RFC3339)
			}
			result[workerID] = map[string]interface{}{
				"status": status, "reason": reason, "resume_at": resume.UTC().Format(time.RFC3339), "mode": weeklyMode, "cache_age_s": codexAge,
				"used_pct": used, "remaining_pct": max(0, 100-used), "ceiling_pct": effectiveWeeklyCeiling,
				"headroom_pct": max(0, effectiveWeeklyCeiling-used), "reset": reset.Format(time.RFC3339),
				"window_mins": windowMins, "plan_type": codex.PlanType,
				"weekly_day": day, "weekly_unlocked_pct": unlocked,
				"weekly_schedule_headroom_pct": effectiveWeeklyCeiling - used, "next_unlock": nextUnlockText,
				"weekly_gate_mode": weeklyMode, "weekly_gate_pct": weeklyPct,
				"weekly_effective_ceiling_pct": effectiveWeeklyCeiling,
				"secondary_used_pct":           codex.SecondaryUsedPct, "secondary_reset": codex.SecondaryResetsAt,
			}
		}
	}

	writeJSON(w, result)
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

var factoryCardHistoryMu sync.Mutex

func shouldRecordCardSnapshot(previous, current factoryCardSnapshot) bool {
	return current.Ts-previous.Ts >= 900 || current.Auto != previous.Auto ||
		current.Imported != previous.Imported || current.Review != previous.Review ||
		current.Manual != previous.Manual
}

func cardHistory(snapshot factoryCardSnapshot) (*factoryCardSnapshot, error) {
	factoryCardHistoryMu.Lock()
	defer factoryCardHistoryMu.Unlock()
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

	// Record changes immediately; sample unchanged output every 15 minutes.
	if len(rows) == 0 || shouldRecordCardSnapshot(rows[len(rows)-1], snapshot) {
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
