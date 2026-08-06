package main

// Dashboard: die Artifact-Ansicht (Card-Browser + Fleet-Status) direkt am
// Dispatcher. /dashboard = eingebettete Seite, /carddb = kompaktes
// [[name,status,cost,type,v2],...]-Array aus den carddb-Shards (60s-Cache).

import (
	"embed"
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

//go:embed dashboard.html
var dashFS embed.FS

var carddbDir = envOr("CARDDB", "/opt/development/magic-new/backend/data/carddb")

var cardCache struct {
	mu   sync.Mutex
	ts   time.Time
	data []byte
}

func costString(mc map[string]interface{}) string {
	n := func(k string) int {
		if v, ok := mc[k].(float64); ok {
			return int(v)
		}
		return 0
	}
	var b strings.Builder
	for i := 0; i < n("x_count"); i++ {
		b.WriteByte('X')
	}
	if g := n("generic"); g > 0 {
		b.WriteString(strconv.Itoa(g))
	}
	for _, p := range [][2]string{{"white", "W"}, {"blue", "U"}, {"black", "B"}, {"red", "R"}, {"green", "G"}, {"colorless", "C"}} {
		for i := 0; i < n(p[0]); i++ {
			b.WriteString(p[1])
		}
	}
	return b.String()
}

func buildCardData() []byte {
	entries, err := os.ReadDir(carddbDir)
	if err != nil {
		return []byte("[]")
	}
	type row = [5]interface{}
	var rows []row
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() || !strings.HasSuffix(name, ".json") || strings.HasPrefix(name, "_") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(carddbDir, name))
		if err != nil {
			continue
		}
		var shard map[string]map[string]interface{}
		if json.Unmarshal(raw, &shard) != nil {
			continue
		}
		for nm, c := range shard {
			status, _ := c["status"].(string)
			st := "?"
			if status != "" {
				st = status[:1]
			}
			cost := ""
			if mc, ok := c["mana_cost"].(map[string]interface{}); ok {
				cost = costString(mc)
			}
			typ := ""
			if tl, ok := c["types"].([]interface{}); ok {
				parts := make([]string, 0, len(tl))
				for _, t := range tl {
					if s, ok := t.(string); ok {
						parts = append(parts, s)
					}
				}
				typ = strings.Join(parts, " ")
			}
			if typ == "" {
				if s, ok := c["type"].(string); ok {
					typ = s
				}
			}
			v2 := 0
			if abs, ok := c["abilities"].([]interface{}); ok {
				for _, a := range abs {
					if am, ok := a.(map[string]interface{}); ok {
						if am["trigger_v2"] != nil || am["effects"] != nil {
							v2 = 1
							break
						}
					}
				}
			}
			rows = append(rows, row{nm, st, cost, typ, v2})
		}
	}
	sort.Slice(rows, func(i, j int) bool {
		return strings.ToLower(rows[i][0].(string)) < strings.ToLower(rows[j][0].(string))
	})
	b, err := json.Marshal(rows)
	if err != nil {
		return []byte("[]")
	}
	return b
}

func carddb(w http.ResponseWriter, r *http.Request) {
	cardCache.mu.Lock()
	if time.Since(cardCache.ts) > 60*time.Second || cardCache.data == nil {
		cardCache.data = buildCardData()
		cardCache.ts = time.Now()
	}
	data := cardCache.data
	cardCache.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(data)
}

var pileCache struct {
	mu   sync.Mutex
	ts   time.Time
	data []byte
}

// pilestats — demand-pile health for the dashboard tiles (Dani 2026-08-02):
// UNCLASSIFIED + kind_unsupported:* rows are SESSION-gated work (the fleet
// cannot map them by contract), so their share of total-misses is the
// engine-round trigger metric. Runs reparse.py --review-pile in the live
// checkout, cached 10 minutes.
func pilestats(w http.ResponseWriter, r *http.Request) {
	pileCache.mu.Lock()
	defer pileCache.mu.Unlock()
	if time.Since(pileCache.ts) > 10*time.Minute || pileCache.data == nil {
		out, err := exec.Command("python3", "/opt/development/magic-new/scripts/paragraph/reparse.py", "--review-pile").Output()
		if err == nil {
			stats := map[string]int{}
			reNum := regexp.MustCompile(`^\s*(\d+)\s+(\S+)`)
			for _, line := range strings.Split(string(out), "\n") {
				if strings.HasPrefix(line, "review-pile cards scanned:") {
					var n int
					fmt.Sscanf(line, "review-pile cards scanned: %d", &n)
					stats["review_cards"] = n
				} else if strings.HasPrefix(line, "total-misses:") {
					var n int
					fmt.Sscanf(line, "total-misses: %d", &n)
					stats["total_misses"] = n
				} else if strings.HasPrefix(line, "flip-ELIGIBLE") {
					var n int
					if _, err := fmt.Sscanf(line[strings.Index(line, ":")+1:], " %d", &n); err == nil {
						stats["flip_eligible"] = n
					}
				} else if m := reNum.FindStringSubmatch(line); m != nil {
					n := 0
					fmt.Sscanf(m[1], "%d", &n)
					if m[2] == "kind_unsupported:UNCLASSIFIED" {
						stats["unclassified"] = n
					}
					if strings.HasPrefix(m[2], "kind_unsupported:") || strings.HasPrefix(m[2], "condition_referent") || strings.HasPrefix(m[2], "spell_seq_targeted") {
						stats["session_gated"] += n
					}
				}
			}
			// flip-frontier merge (Dani 2026-08-06): cron-computed
			// misses-per-review-card histogram — the 1-miss bucket is the
			// "flips on next relevant landing" frontier.
			merged := map[string]interface{}{}
			for k, v := range stats {
				merged[k] = v
			}
			if fb, err := os.ReadFile("/tmp/orch/flip-frontier.json"); err == nil {
				var fr map[string]interface{}
				if json.Unmarshal(fb, &fr) == nil {
					for k, v := range fr {
						merged[k] = v
					}
				}
			}
			pileCache.data, _ = json.Marshal(merged)
			pileCache.ts = time.Now()
		}
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if pileCache.data == nil {
		w.Write([]byte("{}"))
		return
	}
	w.Write(pileCache.data)
}

// buildplan — the deterministic build order (coverage_planner.py output),
// straight from the live checkout so the dashboard always shows the current
// committed plan ("what must be done", Dani 2026-08-02).
func buildplan(w http.ResponseWriter, r *http.Request) {
	data, err := os.ReadFile("/opt/development/magic-new/corpus/build-plan.jsonl")
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if err != nil {
		w.Write([]byte("[]"))
		return
	}
	var items []map[string]interface{}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var it map[string]interface{}
		if json.Unmarshal([]byte(line), &it) == nil {
			delete(it, "examples")
			items = append(items, it)
		}
	}
	out, _ := json.Marshal(items)
	w.Write(out)
}

func dashboard(w http.ResponseWriter, r *http.Request) {
	b, _ := dashFS.ReadFile("dashboard.html")
	w.Header().Set("Content-Type", "text/html")
	w.Write(b)
}
