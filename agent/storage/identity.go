package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

func (s *Store) SaveIdentity(ctx context.Context, identity Identity) error {
	if identity.AgentID == "" || identity.RealmID == "" || identity.ControlPlaneURL == "" {
		return errors.New("agent identity fields are required")
	}
	existing, err := s.Identity(ctx)
	if err == nil {
		if existing.AgentID == identity.AgentID &&
			existing.RealmID == identity.RealmID &&
			existing.ControlPlaneURL == identity.ControlPlaneURL &&
			existing.EnrolledAt.Equal(identity.EnrolledAt) {
			return nil
		}
		return ErrIdentityMismatch
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return err
	}
	_, err = s.db.ExecContext(ctx, `
		INSERT INTO agent_identity (
			singleton_id, agent_id, realm_id, control_plane_url, enrolled_at
		) VALUES (1, ?, ?, ?, ?)`,
		identity.AgentID,
		identity.RealmID,
		identity.ControlPlaneURL,
		identity.EnrolledAt.UTC().Format(time.RFC3339Nano),
	)
	if err != nil {
		return fmt.Errorf("save agent identity: %w", err)
	}
	return nil
}

func (s *Store) Identity(ctx context.Context) (Identity, error) {
	var identity Identity
	var enrolledAt string
	err := s.db.QueryRowContext(ctx, `
		SELECT agent_id, realm_id, control_plane_url, enrolled_at
		FROM agent_identity WHERE singleton_id = 1`,
	).Scan(
		&identity.AgentID,
		&identity.RealmID,
		&identity.ControlPlaneURL,
		&enrolledAt,
	)
	if err != nil {
		return Identity{}, err
	}
	identity.EnrolledAt, err = time.Parse(time.RFC3339Nano, enrolledAt)
	if err != nil {
		return Identity{}, fmt.Errorf("parse stored enrolment time: %w", err)
	}
	return identity, nil
}

func (s *Store) SaveCredential(ctx context.Context, credential Credential) error {
	if credential.CredentialID == "" || credential.Secret == "" {
		return errors.New("agent credential fields are required")
	}
	result, err := s.db.ExecContext(ctx, `
		INSERT INTO credentials (
			credential_id, secret, created_at, activated_at, retire_after
		) VALUES (?, ?, ?, ?, ?)
		ON CONFLICT (credential_id) DO UPDATE SET
			activated_at = excluded.activated_at,
			retire_after = excluded.retire_after
		WHERE credentials.secret = excluded.secret`,
		credential.CredentialID,
		credential.Secret,
		credential.CreatedAt.UTC().Format(time.RFC3339Nano),
		optionalTime(credential.ActivatedAt),
		optionalTime(credential.RetireAfter),
	)
	if err != nil {
		return fmt.Errorf("save agent credential: %w", err)
	}
	changed, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("inspect saved agent credential: %w", err)
	}
	if changed == 0 {
		return ErrCredentialMismatch
	}
	return nil
}

func (s *Store) Credentials(ctx context.Context) ([]Credential, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT credential_id, secret, created_at, activated_at, retire_after
		FROM credentials ORDER BY created_at, credential_id`)
	if err != nil {
		return nil, fmt.Errorf("query agent credentials: %w", err)
	}
	defer func() { _ = rows.Close() }()
	var credentials []Credential
	for rows.Next() {
		var credential Credential
		var createdAt string
		var activatedAt, retireAfter sql.NullString
		if err := rows.Scan(
			&credential.CredentialID,
			&credential.Secret,
			&createdAt,
			&activatedAt,
			&retireAfter,
		); err != nil {
			return nil, fmt.Errorf("scan agent credential: %w", err)
		}
		credential.CreatedAt, err = time.Parse(time.RFC3339Nano, createdAt)
		if err != nil {
			return nil, fmt.Errorf("parse credential creation time: %w", err)
		}
		credential.ActivatedAt, err = parseOptionalTime(activatedAt)
		if err != nil {
			return nil, fmt.Errorf("parse credential activation time: %w", err)
		}
		credential.RetireAfter, err = parseOptionalTime(retireAfter)
		if err != nil {
			return nil, fmt.Errorf("parse credential retirement time: %w", err)
		}
		credentials = append(credentials, credential)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate agent credentials: %w", err)
	}
	return credentials, nil
}

func optionalTime(value *time.Time) any {
	if value == nil {
		return nil
	}
	return value.UTC().Format(time.RFC3339Nano)
}

func parseOptionalTime(value sql.NullString) (*time.Time, error) {
	if !value.Valid {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, value.String)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}
