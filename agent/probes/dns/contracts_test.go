package dns

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestSharedDNSConfigurationContract(t *testing.T) {
	var configuration Configuration
	loadSharedContract(t, "dns_configuration.json", &configuration)
	if configuration.ResolverMode != ResolverModeExplicit || configuration.ResolverAddress == nil ||
		*configuration.ResolverAddress != "127.0.0.1" || configuration.QueryType != QueryTypeA {
		t.Fatalf("unexpected configuration: %#v", configuration)
	}
	if len(configuration.ExpectedAnswers) != 1 {
		t.Fatalf("unexpected assertions: %#v", configuration.ExpectedAnswers)
	}
}

func TestSharedDNSResultContract(t *testing.T) {
	var result Result
	loadSharedContract(t, "dns_result.json", &result)
	if result.ResponseCode == nil || *result.ResponseCode != "NOERROR" || result.AnswerCount != 1 {
		t.Fatalf("unexpected result: %#v", result)
	}
	if len(result.Answers) != 1 || result.Answers[0].Value != "192.0.2.10" {
		t.Fatalf("unexpected answers: %#v", result.Answers)
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
