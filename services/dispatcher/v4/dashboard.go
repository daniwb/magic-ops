package main

// Dashboard: die Artifact-Ansicht (Card-Browser + Fleet-Status) direkt am
// Dispatcher. /dashboard = eingebettete Seite, /carddb = kompaktes
// [[name,status,cost,type,v2],...]-Array aus den carddb-Shards (60s-Cache).

import (
	"embed"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
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

func dashboard(w http.ResponseWriter, r *http.Request) {
	b, _ := dashFS.ReadFile("dashboard.html")
	w.Header().Set("Content-Type", "text/html")
	w.Write(b)
}
