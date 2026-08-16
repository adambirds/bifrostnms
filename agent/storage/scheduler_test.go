package storage

import (
	"context"
	"testing"
	"time"
)

func TestScheduleRestorationSkipsElapsedRunsAndPersistsCoverage(t *testing.T) {
	store, path := openTestStore(t)
	ctx := context.Background()
	initial := time.Date(2026, 8, 16, 20, 0, 0, 0, time.UTC)
	nextDue, err := store.RestoreSchedule(ctx, "monitor", 1, 1, initial, time.Minute, initial)
	if err != nil || !nextDue.Equal(initial) {
		t.Fatalf("initial schedule = %v, error = %v", nextDue, err)
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}
	reopened, err := Open(ctx, path)
	if err != nil {
		t.Fatalf("reopen store: %v", err)
	}
	t.Cleanup(func() { _ = reopened.Close() })
	restartedAt := initial.Add(3*time.Minute + 30*time.Second)
	nextDue, err = reopened.RestoreSchedule(
		ctx, "monitor", 1, 1, initial, time.Minute, restartedAt,
	)
	if err != nil {
		t.Fatalf("restore schedule: %v", err)
	}
	if !nextDue.Equal(initial.Add(4 * time.Minute)) {
		t.Fatalf("restored next due = %v", nextDue)
	}
	state, err := reopened.ScheduleState(ctx, "monitor")
	if err != nil {
		t.Fatalf("read schedule state: %v", err)
	}
	if state.MissedRunCount != 4 {
		t.Fatalf("missed run count = %d", state.MissedRunCount)
	}
}

func TestScheduleRevisionChangeStartsFreshCursor(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 20, 0, 0, 0, time.UTC)
	if _, err := store.RestoreSchedule(ctx, "monitor", 1, 1, now, time.Minute, now); err != nil {
		t.Fatalf("create schedule: %v", err)
	}
	newDue := now.Add(10 * time.Minute)
	restored, err := store.RestoreSchedule(ctx, "monitor", 2, 2, newDue, time.Minute, newDue)
	if err != nil || !restored.Equal(newDue) {
		t.Fatalf("revision schedule = %v, error = %v", restored, err)
	}
	state, err := store.ScheduleState(ctx, "monitor")
	if err != nil || state.MissedRunCount != 0 || state.MonitorRevision != 2 {
		t.Fatalf("revision schedule state = %#v, error = %v", state, err)
	}
}
