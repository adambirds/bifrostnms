package storage

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestIdentitySurvivesRestartAndCannotBeChanged(t *testing.T) {
	store, path := openTestStore(t)
	ctx := context.Background()
	identity := Identity{
		AgentID:         "11111111-1111-4111-8111-111111111111",
		RealmID:         "22222222-2222-4222-8222-222222222222",
		ControlPlaneURL: "https://bifrost.example.test",
		EnrolledAt:      time.Date(2026, 8, 16, 12, 0, 0, 0, time.UTC),
	}
	if err := store.SaveIdentity(ctx, identity); err != nil {
		t.Fatalf("save identity: %v", err)
	}
	if err := store.SaveIdentity(ctx, identity); err != nil {
		t.Fatalf("save same identity: %v", err)
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}
	reopened, err := Open(ctx, path)
	if err != nil {
		t.Fatalf("reopen store: %v", err)
	}
	t.Cleanup(func() { _ = reopened.Close() })
	got, err := reopened.Identity(ctx)
	if err != nil {
		t.Fatalf("load identity: %v", err)
	}
	if got.AgentID != identity.AgentID || !got.EnrolledAt.Equal(identity.EnrolledAt) {
		t.Fatalf("loaded identity = %#v, want %#v", got, identity)
	}
	changed := identity
	changed.RealmID = "33333333-3333-4333-8333-333333333333"
	if err := reopened.SaveIdentity(ctx, changed); !errors.Is(err, ErrIdentityMismatch) {
		t.Fatalf("changed identity error = %v, want ErrIdentityMismatch", err)
	}
}

func TestCredentialsSupportSafeRotationOverlap(t *testing.T) {
	store, _ := openTestStore(t)
	ctx := context.Background()
	now := time.Date(2026, 8, 16, 12, 0, 0, 0, time.UTC)
	activeAt := now.Add(time.Minute)
	retireAfter := now.Add(time.Hour)
	credentials := []Credential{
		{
			CredentialID: "old",
			Secret:       "old-secret",
			CreatedAt:    now,
			ActivatedAt:  &now,
			RetireAfter:  &retireAfter,
		},
		{
			CredentialID: "new",
			Secret:       "new-secret",
			CreatedAt:    activeAt,
			ActivatedAt:  &activeAt,
		},
	}
	for _, credential := range credentials {
		if err := store.SaveCredential(ctx, credential); err != nil {
			t.Fatalf("save credential: %v", err)
		}
	}
	got, err := store.Credentials(ctx)
	if err != nil {
		t.Fatalf("load credentials: %v", err)
	}
	if len(got) != 2 || got[0].Secret != "old-secret" || got[1].Secret != "new-secret" {
		t.Fatalf("credentials = %#v", got)
	}
	changed := credentials[0]
	changed.Secret = "different-secret"
	if err := store.SaveCredential(ctx, changed); !errors.Is(err, ErrCredentialMismatch) {
		t.Fatalf("changed credential error = %v, want ErrCredentialMismatch", err)
	}
}
