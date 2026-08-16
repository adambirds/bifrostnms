package protocol

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"
)

func validConfiguration() ConfigurationResponse {
	response := ConfigurationResponse{
		ProtocolVersion:            1,
		ConfigurationSchemaVersion: 1,
		AgentID:                    "agent-id",
		RealmID:                    "realm-id",
		Revision:                   2,
		GeneratedAt:                time.Now().UTC(),
		Monitors: []MonitorConfiguration{
			{
				MonitorID:          "monitor-id",
				TargetID:           "target-id",
				MonitorRevision:    3,
				TargetAddress:      "example.com",
				ProbeType:          "icmp",
				ProbeSchemaVersion: 1,
				IntervalSeconds:    30,
				TimeoutSeconds:     5,
				MissedRunPolicy:    "skip",
				Configuration: map[string]json.RawMessage{
					"packet_count":   json.RawMessage("5"),
					"schema_version": json.RawMessage("1"),
				},
			},
		},
	}
	canonical := []byte(`{"agent_id":"agent-id","configuration_schema_version":1,"monitors":[{"configuration":{"packet_count":5,"schema_version":1},"interval_seconds":30,"missed_run_policy":"skip","monitor_id":"monitor-id","monitor_revision":3,"probe_schema_version":1,"probe_type":"icmp","target_address":"example.com","target_id":"target-id","timeout_seconds":5}],"realm_id":"realm-id"}`)
	response.ContentHash = fmt.Sprintf("sha256:%x", sha256.Sum256(canonical))
	return response
}

func testCapabilities() Capabilities {
	return Capabilities{Probes: map[string]ProbeCapability{
		"icmp": {SchemaVersions: []int{1}, Available: true},
	}}
}

func TestConfigurationValidationAcceptsCanonicalPayload(t *testing.T) {
	response := validConfiguration()
	canonical, err := response.Validate("agent-id", "realm-id", testCapabilities())
	if err != nil {
		t.Fatalf("validate configuration: %v", err)
	}
	if len(canonical) == 0 {
		t.Fatal("canonical configuration is empty")
	}
}

func TestConfigurationValidationPreservesLastKnownGoodInputs(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*ConfigurationResponse)
		want   error
	}{
		{"identity", func(value *ConfigurationResponse) { value.RealmID = "other" }, ErrConfigurationIdentity},
		{"hash", func(value *ConfigurationResponse) { value.ContentHash = "sha256:bad" }, ErrConfigurationHash},
		{"capability", func(value *ConfigurationResponse) { value.Monitors[0].ProbeType = "http" }, ErrConfigurationCapability},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			response := validConfiguration()
			test.mutate(&response)
			_, err := response.Validate("agent-id", "realm-id", testCapabilities())
			if !errors.Is(err, test.want) {
				t.Fatalf("Validate() error = %v, want %v", err, test.want)
			}
		})
	}
}
