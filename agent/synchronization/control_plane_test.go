package synchronization

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/storage"
)

func TestConfigurationUsesIdentityCredentialAndCurrentRevision(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer credential.secret" {
			t.Errorf("authorization = %q", request.Header.Get("Authorization"))
		}
		if request.URL.Query().Get("active_revision") != "4" ||
			request.URL.Query().Get("content_hash") != "sha256:current" {
			t.Errorf("unexpected query: %s", request.URL.RawQuery)
		}
		writer.WriteHeader(http.StatusNotModified)
	}))
	defer server.Close()

	client := ControlPlane{HTTPClient: server.Client()}
	configuration, err := client.Configuration(context.Background(), storage.Identity{
		ControlPlaneURL: server.URL,
	}, storage.Credential{CredentialID: "credential", Secret: "secret"}, 4, "sha256:current")
	if err != nil {
		t.Fatal(err)
	}
	if configuration != nil {
		t.Fatal("expected a not-modified configuration")
	}
}

func TestAcknowledgeConfigurationRejectsMismatchedResponse(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"protocol_version":          1,
			"acknowledged_revision":     8,
			"acknowledged_content_hash": "sha256:different",
		})
	}))
	defer server.Close()

	client := ControlPlane{HTTPClient: server.Client()}
	err := client.AcknowledgeConfiguration(
		context.Background(), storage.Identity{ControlPlaneURL: server.URL},
		storage.Credential{}, protocol.ConfigurationAcknowledgement{
			ProtocolVersion: protocol.Version,
			Revision:        8, ContentHash: "sha256:expected", ActivatedAt: time.Now().UTC(),
		},
	)
	if err == nil {
		t.Fatal("expected mismatched acknowledgement to fail")
	}
}

func TestEnrolRejectsIncompleteResponse(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"protocol_version":1}`))
	}))
	defer server.Close()

	client := ControlPlane{HTTPClient: server.Client()}
	_, err := client.Enrol(context.Background(), server.URL, protocol.EnrolmentRequest{
		ProtocolVersion: protocol.Version,
	})
	if err == nil {
		t.Fatal("expected incomplete enrolment response to fail")
	}
}
