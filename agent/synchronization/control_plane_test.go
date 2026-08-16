package synchronization

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/storage"
)

func TestSynchronizeConfigurationActivatesAndAcknowledges(t *testing.T) {
	t.Parallel()
	canonical, err := json.Marshal(map[string]any{
		"configuration_schema_version": 1,
		"agent_id":                     "agent", "realm_id": "realm", "monitors": []any{},
	})
	if err != nil {
		t.Fatal(err)
	}
	hash := fmt.Sprintf("sha256:%x", sha256.Sum256(canonical))
	acknowledged := false
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		if request.URL.Path == "/api/v1/agent/config" {
			_ = json.NewEncoder(writer).Encode(protocol.ConfigurationResponse{
				ProtocolVersion: 1, ConfigurationSchemaVersion: 1,
				AgentID: "agent", RealmID: "realm", Revision: 1,
				ContentHash: hash, GeneratedAt: time.Now().UTC(),
				Monitors: []protocol.MonitorConfiguration{},
			})
			return
		}
		acknowledged = true
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"protocol_version": 1, "acknowledged_revision": 1,
			"acknowledged_content_hash": hash,
		})
	}))
	defer server.Close()
	store, err := storage.Open(context.Background(), t.TempDir()+"/agent.db")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = store.Close() }()
	now := time.Now().UTC()
	if err := store.SaveIdentity(context.Background(), storage.Identity{
		AgentID: "agent", RealmID: "realm", ControlPlaneURL: server.URL, EnrolledAt: now,
	}); err != nil {
		t.Fatal(err)
	}
	if err := store.SaveCredential(context.Background(), storage.Credential{
		CredentialID: "credential", Secret: "secret", CreatedAt: now,
	}); err != nil {
		t.Fatal(err)
	}
	registry, err := probe.NewRegistry()
	if err != nil {
		t.Fatal(err)
	}
	client := ControlPlane{HTTPClient: server.Client()}
	updated, err := client.SynchronizeConfiguration(
		context.Background(), store, registry, protocol.Capabilities{
			Probes: map[string]protocol.ProbeCapability{},
		}, now,
	)
	if err != nil {
		t.Fatal(err)
	}
	if !updated || !acknowledged {
		t.Fatalf("updated = %t, acknowledged = %t", updated, acknowledged)
	}
	active, err := store.ActiveConfiguration(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if active.Revision != 1 || string(active.CanonicalPayload) != string(canonical) {
		t.Fatalf("unexpected active configuration: %+v", active)
	}
}

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
