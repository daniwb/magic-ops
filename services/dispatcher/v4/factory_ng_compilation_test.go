package main

import (
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func TestCompilationSwitchPersistsAndPreservesPolicy(t *testing.T) {
	dir := t.TempDir()
	oldPolicy, oldLock := factoryNGPolicyPath, factoryNGAdminLockPath
	factoryNGPolicyPath, factoryNGAdminLockPath = filepath.Join(dir, "policy.json"), filepath.Join(dir, "admin.lock")
	defer func() { factoryNGPolicyPath, factoryNGAdminLockPath = oldPolicy, oldLock }()
	os.WriteFile(factoryNGPolicyPath, []byte(`{"integration":{"automatic":true,"deploy_after_push":false},"resources":{"nice":10},"work_schedule":{"enabled":true}}`), 0644)
	for _, enabled := range []string{"false", "true", "false"} {
		response := httptest.NewRecorder()
		factoryNGCompilation(response, httptest.NewRequest("POST", "/factory-ng/compilation", strings.NewReader(`{"enabled":`+enabled+`}`)))
		if response.Code != 200 {
			t.Fatal(response.Code, response.Body.String())
		}
		response = httptest.NewRecorder()
		factoryNGCompilation(response, httptest.NewRequest("GET", "/factory-ng/compilation", nil))
		if !strings.Contains(response.Body.String(), `"enabled":`+enabled) {
			t.Fatal(response.Body.String())
		}
	}
	raw, _ := os.ReadFile(factoryNGPolicyPath)
	var value map[string]interface{}
	json.Unmarshal(raw, &value)
	if value["work_schedule"] != nil || value["resources"] == nil || value["integration"] == nil {
		t.Fatal(string(raw))
	}
	for _, body := range []string{`{}`, `{"enabled":"true"}`, `{"enabled":true,"extra":1}`, `{"enabled":true} {}`} {
		response := httptest.NewRecorder()
		factoryNGCompilation(response, httptest.NewRequest("POST", "/factory-ng/compilation", strings.NewReader(body)))
		if response.Code != 400 {
			t.Fatal(body, response.Code)
		}
	}
	enabled, err := compilationSetting()
	if err != nil || enabled {
		t.Fatal(enabled, err)
	}
	lock, _ := os.OpenFile(factoryNGAdminLockPath, os.O_RDWR, 0644)
	defer lock.Close()
	syscall.Flock(int(lock.Fd()), syscall.LOCK_EX)
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	response := httptest.NewRecorder()
	factoryNGCompilation(response, httptest.NewRequest("POST", "/factory-ng/compilation", strings.NewReader(`{"enabled":true}`)))
	if response.Code != 503 {
		t.Fatal("must respect dispatcher-admin lock", response.Code)
	}
}
