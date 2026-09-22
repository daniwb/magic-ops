package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"syscall"
)

var factoryNGPolicyPath = factoryNGRoot + "/config/factory-ng-policy.json"
var factoryNGAdminLockPath = "/tmp/orch/dispatcher-admin.lock"

func compilationSetting() (bool, error) {
	raw, err := os.ReadFile(factoryNGPolicyPath)
	if err != nil {
		return false, err
	}
	var policy map[string]json.RawMessage
	if err = json.Unmarshal(raw, &policy); err != nil {
		return false, err
	}
	if policy["compilation"] == nil {
		return true, nil
	}
	var setting struct {
		Enabled *bool `json:"enabled"`
	}
	if err = json.Unmarshal(policy["compilation"], &setting); err != nil {
		return false, err
	}
	if setting.Enabled == nil {
		return false, fmt.Errorf("compilation.enabled is missing")
	}
	return *setting.Enabled, nil
}

func setCompilation(enabled bool) error {
	lock, err := os.OpenFile(factoryNGAdminLockPath, os.O_CREATE|os.O_RDWR, 0644)
	if err != nil {
		return err
	}
	defer lock.Close()
	if err = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return err
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	raw, err := os.ReadFile(factoryNGPolicyPath)
	if err != nil {
		return err
	}
	var policy map[string]json.RawMessage
	if err = json.Unmarshal(raw, &policy); err != nil {
		return err
	}
	if policy == nil {
		return fmt.Errorf("invalid Factory policy")
	}
	value, _ := json.Marshal(map[string]bool{"enabled": enabled})
	policy["compilation"] = value
	// The manual switch replaces the schedule, including old persisted settings.
	delete(policy, "work_schedule")
	raw, err = json.MarshalIndent(policy, "", "  ")
	if err != nil {
		return err
	}
	temp, err := os.CreateTemp(filepath.Dir(factoryNGPolicyPath), ".compilation-*.tmp")
	if err != nil {
		return err
	}
	defer os.Remove(temp.Name())
	if err = temp.Chmod(0644); err == nil {
		_, err = temp.Write(append(raw, '\n'))
	}
	if err == nil {
		err = temp.Sync()
	}
	closeErr := temp.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(temp.Name(), factoryNGPolicyPath)
}

func factoryNGCompilation(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	switch r.Method {
	case http.MethodGet:
	case http.MethodPost:
		var change struct {
			Enabled *bool `json:"enabled"`
		}
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1024))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&change); err != nil || change.Enabled == nil {
			http.Error(w, "enabled must be a boolean", http.StatusBadRequest)
			return
		}
		if decoder.Decode(&struct{}{}) != io.EOF {
			http.Error(w, "one JSON object required", http.StatusBadRequest)
			return
		}
		if err := setCompilation(*change.Enabled); err != nil {
			http.Error(w, err.Error(), http.StatusServiceUnavailable)
			return
		}
	default:
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	enabled, err := compilationSetting()
	if err != nil {
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return
	}
	writeJSON(w, map[string]interface{}{"enabled": enabled, "mode": "manual"})
}
