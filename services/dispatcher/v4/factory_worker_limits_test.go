package main

import (
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

func TestFactoryLimitsRespectEachWorkersCeiling(t *testing.T) {
	dir := t.TempDir()
	original := factoryNGWorkersPath
	factoryNGWorkersPath = dir + "/workers.json"
	t.Cleanup(func() { factoryNGWorkersPath = original })
	config := factoryNGWorkerFile{Schema: "factory-ng-workers/v1", Workers: []factoryNGWorker{
		{ID: "codex", UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 95},
		{ID: "codex-2", UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 70},
		{ID: "codex-3", UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 70},
		{ID: "codex-4", UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 70},
		{ID: "claude", UsagePolicy: "claude-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 95},
		{ID: "claude-2", UsagePolicy: "claude-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 70},
	}}
	if err := writeFactoryNGWorkers(config); err != nil {
		t.Fatal(err)
	}
	reset := time.Now().Add(6 * 24 * time.Hour).UTC().Truncate(time.Second)
	codexCache, claudeCache := dir+"/codex.json", dir+"/claude.json"
	for path, body := range map[string]string{
		codexCache:  fmt.Sprintf(`{"used_pct":80,"resets_at":%d,"window_mins":10080}`, reset.Unix()),
		claudeCache: fmt.Sprintf(`{"five_hour":{"utilization":0,"resets_at":%q},"seven_day":{"utilization":80,"resets_at":%q}}`, reset.Format(time.RFC3339), reset.Format(time.RFC3339)),
	} {
		if err := os.WriteFile(path, []byte(body), 0600); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("CODEX_USAGE_CACHE", codexCache)
	t.Setenv("USAGE_CACHE", claudeCache)
	t.Setenv("CODEX_USAGE_GATE_TTL", "180")
	// A failed refresh must never reach real account credentials from a unit test.
	fetcher := dir + "/no-fetch.py"
	if err := os.WriteFile(fetcher, []byte("raise SystemExit(1)\n"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CODEX_USAGE_FETCH", fetcher)
	readLimits := func() map[string]json.RawMessage {
		t.Helper()
		recorder := httptest.NewRecorder()
		factoryNGLimits(recorder, httptest.NewRequest("GET", "/factory-ng/limits", nil))
		var result map[string]json.RawMessage
		if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		return result
	}
	check := func(result map[string]json.RawMessage, id, status string, ceiling int) {
		t.Helper()
		var limit struct {
			Status  string `json:"status"`
			Ceiling int    `json:"weekly_effective_ceiling_pct"`
			Resume  string `json:"resume_at"`
		}
		if err := json.Unmarshal(result[id], &limit); err != nil {
			t.Fatalf("%s missing/invalid: %v", id, err)
		}
		if limit.Status != status || limit.Ceiling != ceiling {
			t.Fatalf("%s: %+v, want %s/%d", id, limit, status, ceiling)
		}
		if status == "paused" && limit.Resume != reset.Format(time.RFC3339) {
			t.Fatalf("%s wrong resume: %s", id, limit.Resume)
		}
	}
	result := readLimits()
	for _, worker := range config.Workers {
		status := "available"
		if worker.WeeklyGatePct == 70 {
			status = "paused"
		}
		check(result, worker.ID, status, worker.WeeklyGatePct)
	}
	// Changing one secondary worker must not change a sibling or the account card.
	config.Workers[1].WeeklyGatePct = 95
	if err := writeFactoryNGWorkers(config); err != nil {
		t.Fatal(err)
	}
	result = readLimits()
	check(result, "codex-2", "available", 95)
	check(result, "codex-3", "paused", 70)
	check(result, "codex", "available", 95)
	// Stale account data must remain unknown on every worker, not look paused/ready.
	stale := time.Now().Add(-time.Hour)
	if err := os.Chtimes(codexCache, stale, stale); err != nil {
		t.Fatal(err)
	}
	result = readLimits()
	for _, worker := range config.Workers[:4] {
		check(result, worker.ID, "unknown", worker.WeeklyGatePct)
	}
}

func TestPrimaryCodexLimitUpdateKeepsWorkersInSync(t *testing.T) {
	original := factoryNGWorkersPath
	factoryNGWorkersPath = t.TempDir() + "/workers.json"
	t.Cleanup(func() { factoryNGWorkersPath = original })
	config := factoryNGWorkerFile{Schema: "factory-ng-workers/v1", Workers: []factoryNGWorker{
		{ID: "codex", Enabled: true, UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 95, Model: "primary"},
		{ID: "codex-2", Enabled: true, UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 70, Model: "secondary"},
		{ID: "codex-3", Enabled: false, UsagePolicy: "codex-weekly", WeeklyGateMode: "fixed", WeeklyGatePct: 70, Model: "disabled"},
		{ID: "claude", Enabled: true, UsagePolicy: "claude-weekly", WeeklyGateMode: "paced", WeeklyGatePct: 95},
	}}
	if err := writeFactoryNGWorkers(config); err != nil {
		t.Fatal(err)
	}
	for _, body := range []string{`{"id":"codex","weekly_gate_pct":90}`, `{"id":"codex","weekly_gate_mode":"paced"}`, `{"id":"codex","weekly_gate_mode":"none"}`} {
		response := postJSON(factoryNGWorkersHandler, "/factory-ng/workers", body)
		if response.Code != 200 {
			t.Fatalf("update failed: %s", response.Body.String())
		}
		got, err := loadFactoryNGWorkers()
		if err != nil {
			t.Fatal(err)
		}
		for i, worker := range got.Workers {
			if worker.Enabled != config.Workers[i].Enabled || worker.Model != config.Workers[i].Model {
				t.Fatalf("changed unrelated worker settings: %+v", worker)
			}
			if worker.UsagePolicy == "codex-weekly" && (worker.WeeklyGateMode != got.Workers[0].WeeklyGateMode || worker.WeeklyGatePct != 90) {
				t.Fatalf("worker limit diverged: %+v", worker)
			}
			if worker.UsagePolicy == "claude-weekly" && (worker.WeeklyGateMode != "paced" || worker.WeeklyGatePct != 95) {
				t.Fatalf("changed Claude limit: %+v", worker)
			}
		}
	}
	// Toggling the primary worker must not toggle secondary workers.
	response := postJSON(factoryNGWorkersHandler, "/factory-ng/workers", `{"id":"codex","enabled":false}`)
	if response.Code != 200 {
		t.Fatal(response.Body.String())
	}
	got, err := loadFactoryNGWorkers()
	if err != nil {
		t.Fatal(err)
	}
	if got.Workers[0].Enabled || !got.Workers[1].Enabled || got.Workers[2].Enabled {
		t.Fatalf("unexpected enabled states: %+v", got.Workers)
	}
}
