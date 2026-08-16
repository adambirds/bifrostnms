package storage

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestAcknowledgementsApplyMixedResultsAtomically(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 14, 0, 0, 0, time.UTC)
	batch := []Observation{
		testObservation(1),
		testObservation(2),
		testObservation(3),
		testObservation(4),
	}
	for _, observation := range batch {
		if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
			t.Fatalf("enqueue observation: %v", err)
		}
	}
	results := []ObservationAcknowledgement{
		{
			ScheduledAt: batch[0].ScheduledAt, ObservationID: batch[0].ObservationID,
			Disposition: DispositionAccepted,
		},
		{
			ScheduledAt: batch[1].ScheduledAt, ObservationID: batch[1].ObservationID,
			Disposition: DispositionDuplicate,
		},
		{
			ScheduledAt: batch[2].ScheduledAt, ObservationID: batch[2].ObservationID,
			Disposition: DispositionRejected, Code: "server_busy", Retryable: true,
			NextAttemptAt: now.Add(time.Minute),
		},
		{
			ScheduledAt: batch[3].ScheduledAt, ObservationID: batch[3].ObservationID,
			Disposition: DispositionRejected, Code: "invalid_result", Details: "out of range",
		},
	}
	if err := store.ApplyAcknowledgements(ctx, batch, results, now); err != nil {
		t.Fatalf("apply acknowledgements: %v", err)
	}
	stats, err := store.QueueStats(ctx)
	if err != nil {
		t.Fatalf("queue statistics: %v", err)
	}
	if stats.PendingCount != 1 || stats.RejectedCount != 1 {
		t.Fatalf("queue statistics = %#v", stats)
	}
	ready, err := store.ReadyObservations(ctx, now.Add(2*time.Minute), 10)
	if err != nil {
		t.Fatalf("ready observations: %v", err)
	}
	if len(ready) != 1 || ready[0].AttemptCount != 1 ||
		ready[0].LastErrorCode == nil || *ready[0].LastErrorCode != "server_busy" {
		t.Fatalf("retry observation = %#v", ready)
	}
}

func TestAcknowledgementAcceptsServerMicrosecondPrecision(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 14, 0, 0, 0, time.UTC)
	observation := testObservation(1)
	observation.ScheduledAt = time.Date(2026, 8, 16, 14, 0, 0, 123456789, time.UTC)
	if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
		t.Fatalf("enqueue observation: %v", err)
	}
	acknowledgements := []ObservationAcknowledgement{{
		ScheduledAt:   observation.ScheduledAt.Truncate(time.Microsecond),
		ObservationID: observation.ObservationID,
		Disposition:   DispositionAccepted,
	}}
	if err := store.ApplyAcknowledgements(
		ctx, []Observation{observation}, acknowledgements, now,
	); err != nil {
		t.Fatalf("apply microsecond acknowledgement: %v", err)
	}
	stats, err := store.QueueStats(ctx)
	if err != nil {
		t.Fatalf("queue statistics: %v", err)
	}
	if stats.PendingCount != 0 {
		t.Fatalf("acknowledged observation remained queued: %#v", stats)
	}
}

func TestMalformedAcknowledgementPerformsNoCleanup(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	batch := []Observation{testObservation(1), testObservation(2)}
	for _, observation := range batch {
		if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
			t.Fatalf("enqueue observation: %v", err)
		}
	}
	malformed := []ObservationAcknowledgement{
		{
			ScheduledAt:   batch[0].ScheduledAt,
			ObservationID: batch[0].ObservationID,
			Disposition:   DispositionAccepted,
		},
	}
	if err := store.ApplyAcknowledgements(
		ctx, batch, malformed, time.Now().UTC(),
	); !errors.Is(err, ErrUntrustedAcknowledgement) {
		t.Fatalf("malformed acknowledgement error = %v", err)
	}
	stats, err := store.QueueStats(ctx)
	if err != nil {
		t.Fatalf("queue statistics: %v", err)
	}
	if stats.PendingCount != 2 || stats.RejectedCount != 0 {
		t.Fatalf("malformed response changed queue: %#v", stats)
	}
}

func TestPowerLossBeforeCleanupLeavesRowsForSafeRetry(t *testing.T) {
	store, path := openTestStore(t)
	ctx := context.Background()
	observation := testObservation(1)
	if err := store.EnqueueObservation(ctx, observation, DefaultQueueLimits()); err != nil {
		t.Fatalf("enqueue observation: %v", err)
	}
	// A server may have durably accepted this observation, but without a parsed
	// acknowledgement the local row is intentionally untouched.
	if err := store.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}
	reopened, err := Open(ctx, path)
	if err != nil {
		t.Fatalf("reopen store: %v", err)
	}
	t.Cleanup(func() { _ = reopened.Close() })
	ready, err := reopened.ReadyObservations(ctx, observation.ScheduledAt, 10)
	if err != nil || len(ready) != 1 {
		t.Fatalf("safe retry rows = %#v, error = %v", ready, err)
	}
}
