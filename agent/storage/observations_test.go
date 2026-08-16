package storage

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"
)

func testObservation(index int) Observation {
	scheduled := time.Date(2026, 8, 16, 12, index, 0, 0, time.UTC)
	return Observation{
		ScheduledAt:         scheduled,
		ObservationID:       fmt.Sprintf("observation-%d", index),
		MonitorID:           "monitor-id",
		MonitorRevision:     1,
		AgentConfigRevision: 1,
		ProbeType:           "icmp",
		CanonicalPayload:    []byte(fmt.Sprintf(`{"sequence":%d}`, index)),
		CreatedAt:           scheduled,
		NextAttemptAt:       scheduled,
	}
}

func TestPendingObservationsSurviveRestart(t *testing.T) {
	store, path := openTestStore(t)
	ctx := context.Background()
	observation := testObservation(1)
	if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
		t.Fatalf("enqueue observation: %v", err)
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}
	reopened, err := Open(ctx, path)
	if err != nil {
		t.Fatalf("reopen store: %v", err)
	}
	t.Cleanup(func() { _ = reopened.Close() })
	ready, err := reopened.ReadyObservations(ctx, observation.ScheduledAt, 10)
	if err != nil {
		t.Fatalf("load ready observations: %v", err)
	}
	if len(ready) != 1 || ready[0].ObservationID != observation.ObservationID {
		t.Fatalf("ready observations = %#v", ready)
	}
}

func TestObservationIdentityIsIdempotentAndImmutable(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	observation := testObservation(1)
	if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
		t.Fatalf("enqueue observation: %v", err)
	}
	if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
		t.Fatalf("repeat observation: %v", err)
	}
	observation.CanonicalPayload = []byte(`{"different":true}`)
	if err := store.EnqueueObservation(
		ctx, observation, DefaultQueueLimits(),
	); !errors.Is(err, ErrObservationConflict) {
		t.Fatalf("changed observation error = %v", err)
	}
	stats, err := store.QueueStats(ctx)
	if err != nil {
		t.Fatalf("queue statistics: %v", err)
	}
	if stats.PendingCount != 1 {
		t.Fatalf("pending count = %d, want 1", stats.PendingCount)
	}
}

func TestQueueLimitsPauseWithoutDeletingPendingData(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	first := testObservation(1)
	limits := QueueLimits{MaxCount: 1, MaxBytes: int64(len(first.CanonicalPayload))}
	if err := store.EnqueueObservation(ctx, first, limits); err != nil {
		t.Fatalf("enqueue first observation: %v", err)
	}
	if err := store.EnqueueObservation(
		ctx, testObservation(2), limits,
	); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("full queue error = %v, want ErrQueueFull", err)
	}
	stats, err := store.QueueStats(ctx)
	if err != nil {
		t.Fatalf("queue statistics: %v", err)
	}
	if stats.PendingCount != 1 || stats.PendingBytes != int64(len(first.CanonicalPayload)) {
		t.Fatalf("queue statistics = %#v", stats)
	}
}

func TestReadyObservationsAreOldestFirstAndSkipBackoff(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 13, 0, 0, 0, time.UTC)
	for index := 3; index >= 1; index-- {
		observation := testObservation(index)
		if index == 2 {
			observation.NextAttemptAt = now.Add(time.Minute)
		}
		if err := store.EnqueueObservation(
			ctx, observation, DefaultQueueLimits(),
		); err != nil {
			t.Fatalf("enqueue observation %d: %v", index, err)
		}
	}
	ready, err := store.ReadyObservations(ctx, now, 10)
	if err != nil {
		t.Fatalf("ready observations: %v", err)
	}
	if len(ready) != 2 || ready[0].ObservationID != "observation-1" ||
		ready[1].ObservationID != "observation-3" {
		t.Fatalf("ready observation order = %#v", ready)
	}
}
