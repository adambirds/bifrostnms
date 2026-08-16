package synchronization

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/storage"
)

func TestUploaderPreservesDataDuringOutageThenAcknowledgesIt(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/api/v1/agent/observations" {
			http.NotFound(writer, request)
			return
		}
		if request.Header.Get("Authorization") != "Bearer credential.secret" {
			http.Error(writer, "unauthorized", http.StatusUnauthorized)
			return
		}
		if attempts.Add(1) == 1 {
			http.Error(writer, "temporarily unavailable", http.StatusServiceUnavailable)
			return
		}
		var upload protocol.ObservationUpload
		if err := json.NewDecoder(request.Body).Decode(&upload); err != nil {
			t.Errorf("decode upload: %v", err)
			return
		}
		var identity struct {
			ScheduledAt   time.Time `json:"scheduled_at"`
			ObservationID string    `json:"observation_id"`
		}
		if err := json.Unmarshal(upload.Observations[0], &identity); err != nil {
			t.Errorf("decode observation identity: %v", err)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(protocol.ObservationUploadResponse{
			ProtocolVersion: protocol.Version,
			BatchID:         upload.BatchID,
			Results: []protocol.ObservationResult{{
				ScheduledAt: identity.ScheduledAt, ObservationID: identity.ObservationID,
				Disposition: string(storage.DispositionAccepted),
			}},
		})
	}))
	t.Cleanup(server.Close)

	store := openStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 18, 0, 0, 0, time.UTC)
	if err := store.SaveIdentity(ctx, storage.Identity{
		AgentID: "agent", RealmID: "realm", ControlPlaneURL: server.URL, EnrolledAt: now,
	}); err != nil {
		t.Fatalf("save identity: %v", err)
	}
	if err := store.SaveCredential(ctx, storage.Credential{
		CredentialID: "credential", Secret: "secret", CreatedAt: now,
	}); err != nil {
		t.Fatalf("save credential: %v", err)
	}
	enqueue(t, store, now, 1, 1, `{"scheduled_at":"2026-08-16T18:00:00Z","observation_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"}`)
	clock := now
	client := Client{
		Store: store, HTTPClient: server.Client(), Now: func() time.Time { return clock },
		Random: func() float64 { return 0.5 },
	}
	if uploaded, err := client.UploadOnce(ctx); err == nil || uploaded != 0 {
		t.Fatalf("outage upload count = %d, error = %v", uploaded, err)
	}
	stats, err := store.QueueStats(ctx)
	if err != nil || stats.PendingCount != 1 {
		t.Fatalf("outage queue statistics = %#v, error = %v", stats, err)
	}
	if _, err := client.UploadOnce(ctx); err != ErrBackoffActive {
		t.Fatalf("active backoff error = %v", err)
	}
	clock = now.Add(time.Second)
	if uploaded, err := client.UploadOnce(ctx); err != nil || uploaded != 1 {
		t.Fatalf("reconnection upload count = %d, error = %v", uploaded, err)
	}
	stats, err = store.QueueStats(ctx)
	if err != nil || stats.PendingCount != 0 {
		t.Fatalf("reconnected queue statistics = %#v, error = %v", stats, err)
	}
	state, err := store.SynchronizationState(ctx)
	if err != nil || state.ConsecutiveFailureCount != 0 || state.ServerBackoffUntil != nil {
		t.Fatalf("reconnected synchronization state = %#v, error = %v", state, err)
	}
}
