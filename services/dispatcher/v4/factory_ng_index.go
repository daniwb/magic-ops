package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os/exec"
	"strconv"
	"time"
)

var factoryNGIndexScript = factoryNGRoot + "/scripts/factory_ng_dashboard_index.py"

// A single background writer incrementally projects durable receipts. Requests
// never scan the artifact directories, and WAL readers retain the last snapshot.
func factoryNGIndexLoop() {
	for {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		out, err := exec.CommandContext(ctx, "python3", factoryNGIndexScript, "--refresh").CombinedOutput()
		cancel()
		if err != nil {
			log.Printf("Factory NG dashboard index refresh: %v: %.1000s", err, out)
		}
		time.Sleep(15 * time.Second)
	}
}

func factoryNGIndexArgs(r *http.Request) ([]string, error) {
	q := r.URL.Query()
	args := []string{factoryNGIndexScript}
	filter := q.Get("filter")
	if filter == "" {
		filter = "active"
	}
	if filter != "active" && filter != "attention" && filter != "recent" {
		return nil, fmt.Errorf("invalid work filter")
	}
	args = append(args, "--filter", filter)
	for _, name := range []string{"jobs", "attempts", "integrations"} {
		if raw := q.Get(name + "_offset"); raw != "" {
			n, err := strconv.Atoi(raw)
			if err != nil || n < 0 || n > 10000000 {
				return nil, fmt.Errorf("invalid %s offset", name)
			}
			args = append(args, "--"+name+"-offset", strconv.Itoa(n))
		}
	}
	for _, name := range []string{"focus", "search"} {
		if value := q.Get(name); value != "" {
			if len(value) > 300 {
				return nil, fmt.Errorf("%s is too long", name)
			}
			args = append(args, "--"+name+"="+value)
		}
	}
	if q.Get("attempts") == "1" {
		args = append(args, "--attempts")
	}
	return args, nil
}

func factoryNGData(w http.ResponseWriter, r *http.Request) {
	args, err := factoryNGIndexArgs(r)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, "python3", args...).Output()
	if err != nil {
		w.Header().Set("Retry-After", "15")
		http.Error(w, "Dashboard index is unavailable; background refresh will retry.", http.StatusServiceUnavailable)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(out)
}
