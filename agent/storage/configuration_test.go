package storage

import (
	"context"
	"errors"
	"testing"
	"time"
)

func configurationSnapshot(revision int64, payload string) ConfigurationSnapshot {
	now := time.Date(2026, 8, 16, 12, int(revision), 0, 0, time.UTC)
	return ConfigurationSnapshot{
		Revision:         revision,
		ContentHash:      "hash-" + payload,
		SchemaVersion:    1,
		CanonicalPayload: []byte(payload),
		DownloadedAt:     now,
		ValidatedAt:      &now,
		ActivatedAt:      &now,
	}
}

func TestConfigurationActivationIsAtomicAndSurvivesRestart(t *testing.T) {
	store, path := openTestStore(t)
	ctx := context.Background()
	first := configurationSnapshot(1, "first")
	second := configurationSnapshot(2, "second")
	if err := store.ActivateConfiguration(ctx, first); err != nil {
		t.Fatalf("activate first configuration: %v", err)
	}
	if err := store.ActivateConfiguration(ctx, second); err != nil {
		t.Fatalf("activate second configuration: %v", err)
	}
	active, err := store.ActiveConfiguration(ctx)
	if err != nil {
		t.Fatalf("active configuration: %v", err)
	}
	if active.Revision != 2 || string(active.CanonicalPayload) != "second" {
		t.Fatalf("active configuration = %#v", active)
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}
	reopened, err := Open(ctx, path)
	if err != nil {
		t.Fatalf("reopen store: %v", err)
	}
	t.Cleanup(func() { _ = reopened.Close() })
	active, err = reopened.ActiveConfiguration(ctx)
	if err != nil || active.Revision != 2 {
		t.Fatalf("reopened active configuration = %#v, error = %v", active, err)
	}
}

func TestInvalidReplacementLeavesLastKnownGoodActive(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	first := configurationSnapshot(1, "first")
	if err := store.ActivateConfiguration(ctx, first); err != nil {
		t.Fatalf("activate first configuration: %v", err)
	}
	conflict := configurationSnapshot(1, "different")
	if err := store.ActivateConfiguration(ctx, conflict); !errors.Is(
		err, ErrConfigurationConflict,
	) {
		t.Fatalf("conflicting activation error = %v", err)
	}
	active, err := store.ActiveConfiguration(ctx)
	if err != nil {
		t.Fatalf("active configuration: %v", err)
	}
	if active.Revision != 1 || string(active.CanonicalPayload) != "first" {
		t.Fatalf("last known good configuration changed: %#v", active)
	}
}

func TestConfigurationRetentionKeepsActiveAndPrevious(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	for revision := int64(1); revision <= 3; revision++ {
		if err := store.ActivateConfiguration(
			ctx, configurationSnapshot(revision, string(rune('a'+revision))),
		); err != nil {
			t.Fatalf("activate revision %d: %v", revision, err)
		}
	}
	var count int
	if err := store.db.QueryRowContext(
		ctx, "SELECT COUNT(*) FROM configuration_snapshots",
	).Scan(&count); err != nil {
		t.Fatalf("count configurations: %v", err)
	}
	if count != 2 {
		t.Fatalf("retained configurations = %d, want 2", count)
	}
}
