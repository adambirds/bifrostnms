package storage

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

var ErrConfigurationConflict = errors.New("configuration revision has different content")

type ConfigurationSnapshot struct {
	Revision         int64
	ContentHash      string
	SchemaVersion    int
	CanonicalPayload []byte
	DownloadedAt     time.Time
	ValidatedAt      *time.Time
	ActivatedAt      *time.Time
	Active           bool
	RejectionCode    *string
	RejectionDetails *string
}

func (s *Store) ActivateConfiguration(
	ctx context.Context, snapshot ConfigurationSnapshot,
) error {
	if snapshot.Revision < 1 || snapshot.ContentHash == "" || len(snapshot.CanonicalPayload) == 0 ||
		snapshot.SchemaVersion < 1 || snapshot.ValidatedAt == nil || snapshot.ActivatedAt == nil {
		return errors.New("validated configuration snapshot fields are required")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin configuration activation: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	if err := ensureConfigurationContent(ctx, tx, snapshot); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, "UPDATE configuration_snapshots SET active = 0 WHERE active = 1"); err != nil {
		return fmt.Errorf("clear active configuration: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE configuration_snapshots SET
			validated_at = ?, activated_at = ?, active = 1,
			rejection_code = NULL, rejection_details = NULL
		WHERE revision = ?`,
		optionalTime(snapshot.ValidatedAt),
		optionalTime(snapshot.ActivatedAt),
		snapshot.Revision,
	); err != nil {
		return fmt.Errorf("activate configuration: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `
		DELETE FROM configuration_snapshots
		WHERE active = 0 AND validated_at IS NOT NULL AND revision NOT IN (
			SELECT revision FROM configuration_snapshots
			WHERE active = 0 AND validated_at IS NOT NULL
			ORDER BY revision DESC LIMIT 1
		)`); err != nil {
		return fmt.Errorf("prune old configurations: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit configuration activation: %w", err)
	}
	return nil
}

func ensureConfigurationContent(
	ctx context.Context, tx *sql.Tx, snapshot ConfigurationSnapshot,
) error {
	var hash string
	var payload []byte
	err := tx.QueryRowContext(ctx, `
		SELECT content_hash, canonical_payload FROM configuration_snapshots
		WHERE revision = ?`, snapshot.Revision).Scan(&hash, &payload)
	if err == nil {
		if hash != snapshot.ContentHash || !bytes.Equal(payload, snapshot.CanonicalPayload) {
			return ErrConfigurationConflict
		}
		return nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return fmt.Errorf("read configuration revision: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
		INSERT INTO configuration_snapshots (
			revision, content_hash, schema_version, canonical_payload, downloaded_at
		) VALUES (?, ?, ?, ?, ?)`,
		snapshot.Revision,
		snapshot.ContentHash,
		snapshot.SchemaVersion,
		snapshot.CanonicalPayload,
		snapshot.DownloadedAt.UTC().Format(time.RFC3339Nano),
	)
	if err != nil {
		return fmt.Errorf("store configuration snapshot: %w", err)
	}
	return nil
}

func (s *Store) ActiveConfiguration(ctx context.Context) (ConfigurationSnapshot, error) {
	return s.configuration(ctx, "WHERE active = 1")
}

func (s *Store) configuration(
	ctx context.Context, clause string, arguments ...any,
) (ConfigurationSnapshot, error) {
	var snapshot ConfigurationSnapshot
	var downloadedAt string
	var validatedAt, activatedAt, rejectionCode, rejectionDetails sql.NullString
	err := s.db.QueryRowContext(ctx, `
		SELECT revision, content_hash, schema_version, canonical_payload,
			downloaded_at, validated_at, activated_at, active,
			rejection_code, rejection_details
		FROM configuration_snapshots `+clause,
		arguments...,
	).Scan(
		&snapshot.Revision,
		&snapshot.ContentHash,
		&snapshot.SchemaVersion,
		&snapshot.CanonicalPayload,
		&downloadedAt,
		&validatedAt,
		&activatedAt,
		&snapshot.Active,
		&rejectionCode,
		&rejectionDetails,
	)
	if err != nil {
		return ConfigurationSnapshot{}, err
	}
	snapshot.DownloadedAt, err = time.Parse(time.RFC3339Nano, downloadedAt)
	if err != nil {
		return ConfigurationSnapshot{}, fmt.Errorf("parse configuration download time: %w", err)
	}
	snapshot.ValidatedAt, err = parseOptionalTime(validatedAt)
	if err != nil {
		return ConfigurationSnapshot{}, fmt.Errorf("parse configuration validation time: %w", err)
	}
	snapshot.ActivatedAt, err = parseOptionalTime(activatedAt)
	if err != nil {
		return ConfigurationSnapshot{}, fmt.Errorf("parse configuration activation time: %w", err)
	}
	if rejectionCode.Valid {
		snapshot.RejectionCode = &rejectionCode.String
	}
	if rejectionDetails.Valid {
		snapshot.RejectionDetails = &rejectionDetails.String
	}
	return snapshot, nil
}
