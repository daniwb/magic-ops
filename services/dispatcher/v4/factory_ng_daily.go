package main

import (
	"context"
	"log"
	"os/exec"
	"time"
)

var factoryNGDailyPath = factoryNGRoot + "/state/factory-ng-daily-activations.json"

// Read immutable Git blobs in the background; dashboard requests only read a
// small atomic snapshot. Failed refreshes preserve the dated previous result.
func factoryNGDailyLoop() {
	for {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		out, err := exec.CommandContext(ctx, "python3", factoryNGRoot+"/scripts/factory-ng-daily-activations.py", "--repo", openMagicRoot).CombinedOutput()
		cancel()
		if err != nil {
			log.Printf("Factory NG daily activations refresh: %v: %.1000s", err, out)
		}
		time.Sleep(5 * time.Minute)
	}
}
