package synchronization

import (
	"context"
	"encoding/json"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/storage"
)

func TestBuildBatchHonoursCountRevisionAndExactByteLimits(t *testing.T) {
	store := openStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 16, 0, 0, 0, time.UTC)
	for index := 0; index < 4; index++ {
		revision := int64(1)
		if index == 3 {
			revision = 2
		}
		enqueue(t, store, now.Add(time.Duration(index)*time.Second), index, revision, `{"ok":true}`)
	}
	countLimited, err := BuildBatch(ctx, store, now.Add(time.Minute), 2, DefaultMaxBatchBytes)
	if err != nil {
		t.Fatalf("build count-limited batch: %v", err)
	}
	if len(countLimited.Observations) != 2 || countLimited.Upload.AgentConfigRevision != 1 {
		t.Fatalf("count-limited batch = %#v", countLimited)
	}
	if len(countLimited.Body) != len(mustMarshal(t, countLimited.Upload)) {
		t.Fatal("batch body is not the exact serialized upload")
	}

	revisionLimited, err := BuildBatch(ctx, store, now.Add(time.Minute), 10, DefaultMaxBatchBytes)
	if err != nil {
		t.Fatalf("build revision-limited batch: %v", err)
	}
	if len(revisionLimited.Observations) != 3 {
		t.Fatalf("revision-limited observation count = %d", len(revisionLimited.Observations))
	}

	exactLimit := len(mustMarshal(t, countLimited.Upload))
	byteLimited, err := BuildBatch(ctx, store, now.Add(time.Minute), 10, exactLimit)
	if err != nil {
		t.Fatalf("build byte-limited batch: %v", err)
	}
	if len(byteLimited.Observations) != 2 || len(byteLimited.Body) > exactLimit {
		t.Fatalf("byte-limited batch size = %d, observations = %d", len(byteLimited.Body), len(byteLimited.Observations))
	}
}

func TestBuildBatchReportsSingleOversizedObservation(t *testing.T) {
	store := openStore(t)
	now := time.Date(2026, 8, 16, 16, 0, 0, 0, time.UTC)
	enqueue(t, store, now, 1, 1, `{"value":"`+strings.Repeat("x", 512)+`"}`)
	batch, err := BuildBatch(context.Background(), store, now, 10, 128)
	if !errors.Is(err, ErrObservationTooLarge) || len(batch.Observations) != 0 {
		t.Fatalf("oversized batch = %#v, error = %v", batch, err)
	}
}

func TestRetryDelayUsesFullJitterCapAndServerGuidance(t *testing.T) {
	if got := RetryDelay(1, 0, 0.5); got != 500*time.Millisecond {
		t.Fatalf("initial jitter delay = %v", got)
	}
	if got := RetryDelay(20, 0, 1); got != MaximumRetryDelay {
		t.Fatalf("capped delay = %v", got)
	}
	if got := RetryDelay(2, 45*time.Second, 0.25); got != 45*time.Second {
		t.Fatalf("server-guided delay = %v", got)
	}
	if got := RetryDelay(2, 10*time.Minute, 0.25); got != MaximumRetryDelay {
		t.Fatalf("server-guided capped delay = %v", got)
	}
}

func openStore(t *testing.T) *storage.Store {
	t.Helper()
	store, err := storage.Open(context.Background(), filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func enqueue(
	t *testing.T, store *storage.Store, scheduledAt time.Time, index int, revision int64, payload string,
) {
	t.Helper()
	err := store.EnqueueObservation(context.Background(), storage.Observation{
		ScheduledAt: scheduledAt, ObservationID: strings.Repeat("a", 31) + string(rune('0'+index)),
		MonitorID: "monitor", MonitorRevision: 1, AgentConfigRevision: revision,
		ProbeType: "icmp", CanonicalPayload: []byte(payload), CreatedAt: scheduledAt,
	}, storage.DefaultQueueLimits())
	if err != nil {
		t.Fatalf("enqueue observation: %v", err)
	}
}

func mustMarshal(t *testing.T, value any) []byte {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal value: %v", err)
	}
	return encoded
}
