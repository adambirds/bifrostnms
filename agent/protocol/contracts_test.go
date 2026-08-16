package protocol

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func readContract(t *testing.T, name string, target any) {
	t.Helper()
	path := filepath.Join("..", "..", "contracts", "agent", "v1", name)
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read contract: %v", err)
	}
	if err := json.Unmarshal(content, target); err != nil {
		t.Fatalf("decode contract: %v", err)
	}
}

func TestEnrolmentRequestContract(t *testing.T) {
	var request EnrolmentRequest
	readContract(t, "enrolment_request.json", &request)
	if request.ProtocolVersion != Version || !request.Capabilities.Probes["icmp"].Available {
		t.Fatalf("unexpected enrolment contract: %#v", request)
	}
}

func TestHeartbeatRequestContract(t *testing.T) {
	var request HeartbeatRequest
	readContract(t, "heartbeat_request.json", &request)
	if request.ProtocolVersion != Version || request.QueueDepth != 2 {
		t.Fatalf("unexpected heartbeat contract: %#v", request)
	}
}

func TestConfigurationResponseContract(t *testing.T) {
	var response ConfigurationResponse
	readContract(t, "configuration_response.json", &response)
	if response.ProtocolVersion != Version || len(response.Monitors) != 1 {
		t.Fatalf("unexpected configuration contract: %#v", response)
	}
}

func TestObservationUploadContract(t *testing.T) {
	var upload ObservationUpload
	readContract(t, "observation_upload.json", &upload)
	if upload.ProtocolVersion != Version || upload.AgentConfigRevision != 7 ||
		len(upload.Observations) != 1 {
		t.Fatalf("unexpected observation upload contract: %#v", upload)
	}
}
