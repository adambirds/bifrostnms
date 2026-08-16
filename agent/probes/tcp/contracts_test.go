package tcp

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func readProbeContract(t *testing.T, name string) []byte {
	t.Helper()
	path := filepath.Join("..", "..", "..", "contracts", "probes", "v1", name)
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read probe contract: %v", err)
	}
	return content
}

func TestTCPConfigurationContract(t *testing.T) {
	t.Parallel()
	configuration, err := DecodeConfiguration(readProbeContract(t, "tcp_configuration.json"))
	if err != nil {
		t.Fatal(err)
	}
	if configuration.SchemaVersion != 1 || configuration.Port != 443 ||
		configuration.AddressFamily != AddressFamilyAuto {
		t.Fatalf("configuration = %#v", configuration)
	}
}

func TestTCPResultContract(t *testing.T) {
	t.Parallel()
	var result Result
	if err := json.Unmarshal(readProbeContract(t, "tcp_result.json"), &result); err != nil {
		t.Fatal(err)
	}
	if result.Port != 443 || result.AddressUsed == nil || *result.AddressUsed != "2001:db8::1" ||
		result.ConnectMS == nil || *result.ConnectMS != 12.5 {
		t.Fatalf("result = %#v", result)
	}
}
