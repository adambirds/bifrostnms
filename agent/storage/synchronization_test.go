package storage

import (
	"context"
	"testing"
	"time"
)

func TestSynchronizationFailureAndLocalQuarantinePersist(t *testing.T) {
	store, path := openTestStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 17, 0, 0, 0, time.UTC)
	observation := testObservation(1)
	if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
		t.Fatalf("enqueue observation: %v", err)
	}
	backoffUntil := now.Add(time.Minute)
	if err := store.RecordSynchronizationFailure(ctx, backoffUntil); err != nil {
		t.Fatalf("record synchronization failure: %v", err)
	}
	if err := store.QuarantineObservation(
		ctx, observation, "local_payload_too_large", "serialized upload exceeds 1 MiB", now,
	); err != nil {
		t.Fatalf("quarantine observation: %v", err)
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}
	reopened, err := Open(ctx, path)
	if err != nil {
		t.Fatalf("reopen store: %v", err)
	}
	t.Cleanup(func() { _ = reopened.Close() })
	state, err := reopened.SynchronizationState(ctx)
	if err != nil {
		t.Fatalf("read synchronization state: %v", err)
	}
	if state.ConsecutiveFailureCount != 1 || state.ServerBackoffUntil == nil ||
		!state.ServerBackoffUntil.Equal(backoffUntil) {
		t.Fatalf("synchronization state = %#v", state)
	}
	stats, err := reopened.QueueStats(ctx)
	if err != nil {
		t.Fatalf("queue statistics: %v", err)
	}
	if stats.PendingCount != 0 || stats.RejectedCount != 1 {
		t.Fatalf("queue statistics = %#v", stats)
	}
}
