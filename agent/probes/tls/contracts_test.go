package tls

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestSharedTLSConfigurationContract(t *testing.T) {
	var configuration Configuration
	loadSharedContract(t, "tls_configuration.json", &configuration)
	if configuration.Port != 8443 || configuration.ServerName == nil ||
		*configuration.ServerName != "monitor.example.com" || configuration.MinimumTLSVersion != MinimumTLS12 {
		t.Fatalf("unexpected configuration: %#v", configuration)
	}
	if configuration.ExpiryWarningDays != 30 {
		t.Fatalf("unexpected expiry warning: %#v", configuration)
	}
}

func TestSharedTLSResultContract(t *testing.T) {
	var result Result
	loadSharedContract(t, "tls_result.json", &result)
	if result.ProtocolVersion == nil || *result.ProtocolVersion != "TLS 1.3" || !result.CertificatePresent {
		t.Fatalf("unexpected result: %#v", result)
	}
	if result.FingerprintSHA256 == nil || len(*result.FingerprintSHA256) != 64 {
		t.Fatalf("unexpected fingerprint: %#v", result.FingerprintSHA256)
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
