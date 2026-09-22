package main

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDashboardIndexArgumentsAreBounded(t *testing.T) {
	for _, query := range []string{"filter=unknown", "jobs_offset=-1", "attempts_offset=oops", "integrations_offset=10000001", "search=" + strings.Repeat("x", 301)} {
		if _, err := factoryNGIndexArgs(httptest.NewRequest("GET", "/factory-ng/data?"+query, nil)); err == nil {
			t.Fatalf("accepted invalid query %q", query)
		}
	}
	args, err := factoryNGIndexArgs(httptest.NewRequest("GET", "/factory-ng/data?filter=attention&attempts=1&jobs_offset=30&search=--refresh", nil))
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(args, " ")
	if !strings.Contains(joined, "--search=--refresh") || !strings.Contains(joined, "--jobs-offset 30") {
		t.Fatalf("unsafe or incomplete arguments: %v", args)
	}
}
