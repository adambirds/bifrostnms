package http

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestSharedHTTPConfigurationContract(t *testing.T) {
	var configuration Configuration
	loadSharedContract(t, "http_configuration.json", &configuration)
	if configuration.Scheme != "https" || configuration.Port == nil || *configuration.Port != 8443 {
		t.Fatalf("unexpected configuration: %#v", configuration)
	}
	if len(configuration.ExpectedHeaderValues) != 1 || len(configuration.ExpectedBodyContains) != 1 {
		t.Fatalf("unexpected assertions: %#v", configuration)
	}
}

func TestSharedHTTPResultContract(t *testing.T) {
	var result Result
	loadSharedContract(t, "http_result.json", &result)
	if result.StatusCode == nil || *result.StatusCode != 200 || result.AssertionsFailed != 0 {
		t.Fatalf("unexpected result: %#v", result)
	}
}

func loadSharedContract(t *testing.T, name string, target any) {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate contract test source")
	}
	path := filepath.Join(filepath.Dir(source), "..", "..", "..", "contracts", "probes", "v1", name)
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(content, target); err != nil {
		t.Fatal(err)
	}
}
