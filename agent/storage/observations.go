package storage

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

const (
	DefaultMaxPendingObservations int64 = 1_000_000
	DefaultMaxPendingBytes        int64 = 1 << 30
)

var (
	ErrObservationConflict = errors.New("observation identity has different content")
	ErrQueueFull           = errors.New("pending observation queue limit reached")
)

type QueueLimits struct {
	MaxCount int64
	MaxBytes int64
}

func DefaultQueueLimits() QueueLimits {
	return QueueLimits{
		MaxCount: DefaultMaxPendingObservations,
		MaxBytes: DefaultMaxPendingBytes,
	}
}

type Observation struct {
	ScheduledAt         time.Time
	ObservationID       string
	MonitorID           string
	MonitorRevision     int64
	AgentConfigRevision int64
	ProbeType           string
	CanonicalPayload    []byte
	CreatedAt           time.Time
	AttemptCount        int
	NextAttemptAt       time.Time
	LastAttemptAt       *time.Time
	LastErrorCode       *string
}

type QueueStats struct {
	PendingCount    int64
	PendingBytes    int64
	OldestPendingAt *time.Time
	RejectedCount   int64
	RejectedBytes   int64
}

func (s *Store) EnqueueObservation(
	ctx context.Context, observation Observation, limits QueueLimits,
) error {
	if observation.ObservationID == "" || observation.MonitorID == "" ||
		observation.MonitorRevision < 1 || observation.AgentConfigRevision < 1 ||
		observation.ProbeType == "" || len(observation.CanonicalPayload) == 0 {
		return errors.New("observation fields are required")
	}
	if limits.MaxCount < 1 || limits.MaxBytes < 1 {
		return errors.New("positive queue limits are required")
	}
	if observation.CreatedAt.IsZero() {
		observation.CreatedAt = time.Now().UTC()
	}
	if observation.NextAttemptAt.IsZero() {
		observation.NextAttemptAt = observation.CreatedAt
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin observation enqueue: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	duplicate, err := observationAlreadyQueued(ctx, tx, observation)
	if err != nil {
		return err
	}
	if duplicate {
		return tx.Commit()
	}
	var count, size int64
	if err := tx.QueryRowContext(ctx, `
		SELECT COUNT(*), COALESCE(SUM(payload_size_bytes), 0)
		FROM pending_observations`).Scan(&count, &size); err != nil {
		return fmt.Errorf("read pending queue size: %w", err)
	}
	payloadSize := int64(len(observation.CanonicalPayload))
	if count+1 > limits.MaxCount || size+payloadSize > limits.MaxBytes {
		return ErrQueueFull
	}
	_, err = tx.ExecContext(ctx, `
		INSERT INTO pending_observations (
			scheduled_at, observation_id, monitor_id, monitor_revision,
			agent_config_revision, probe_type, canonical_payload,
			payload_size_bytes, created_at, attempt_count, next_attempt_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		formatTime(observation.ScheduledAt),
		observation.ObservationID,
		observation.MonitorID,
		observation.MonitorRevision,
		observation.AgentConfigRevision,
		observation.ProbeType,
		observation.CanonicalPayload,
		payloadSize,
		formatTime(observation.CreatedAt),
		observation.AttemptCount,
		formatTime(observation.NextAttemptAt),
	)
	if err != nil {
		return fmt.Errorf("insert pending observation: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit observation enqueue: %w", err)
	}
	return nil
}

func observationAlreadyQueued(
	ctx context.Context, tx *sql.Tx, observation Observation,
) (bool, error) {
	var payload []byte
	err := tx.QueryRowContext(ctx, `
		SELECT canonical_payload FROM pending_observations
		WHERE scheduled_at = ? AND observation_id = ?`,
		formatTime(observation.ScheduledAt), observation.ObservationID,
	).Scan(&payload)
	if err == nil {
		if !bytes.Equal(payload, observation.CanonicalPayload) {
			return false, ErrObservationConflict
		}
		return true, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return false, fmt.Errorf("check pending observation identity: %w", err)
	}
	return false, nil
}

func (s *Store) ReadyObservations(
	ctx context.Context, now time.Time, limit int,
) ([]Observation, error) {
	if limit < 1 {
		return nil, errors.New("positive batch limit is required")
	}
	rows, err := s.db.QueryContext(ctx, `
		SELECT scheduled_at, observation_id, monitor_id, monitor_revision,
			agent_config_revision, probe_type, canonical_payload, created_at,
			attempt_count, next_attempt_at, last_attempt_at, last_error_code
		FROM pending_observations
		WHERE next_attempt_at <= ?
		ORDER BY scheduled_at, observation_id
		LIMIT ?`, formatTime(now), limit)
	if err != nil {
		return nil, fmt.Errorf("query ready observations: %w", err)
	}
	defer func() { _ = rows.Close() }()
	var observations []Observation
	for rows.Next() {
		observation, err := scanObservation(rows)
		if err != nil {
			return nil, err
		}
		observations = append(observations, observation)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate ready observations: %w", err)
	}
	return observations, nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanObservation(row rowScanner) (Observation, error) {
	var observation Observation
	var scheduledAt, createdAt, nextAttemptAt string
	var lastAttemptAt, lastErrorCode sql.NullString
	if err := row.Scan(
		&scheduledAt, &observation.ObservationID, &observation.MonitorID,
		&observation.MonitorRevision, &observation.AgentConfigRevision,
		&observation.ProbeType, &observation.CanonicalPayload, &createdAt,
		&observation.AttemptCount, &nextAttemptAt, &lastAttemptAt, &lastErrorCode,
	); err != nil {
		return Observation{}, fmt.Errorf("scan pending observation: %w", err)
	}
	var err error
	if observation.ScheduledAt, err = parseTime(scheduledAt); err != nil {
		return Observation{}, err
	}
	if observation.CreatedAt, err = parseTime(createdAt); err != nil {
		return Observation{}, err
	}
	if observation.NextAttemptAt, err = parseTime(nextAttemptAt); err != nil {
		return Observation{}, err
	}
	if observation.LastAttemptAt, err = parseOptionalTime(lastAttemptAt); err != nil {
		return Observation{}, err
	}
	if lastErrorCode.Valid {
		observation.LastErrorCode = &lastErrorCode.String
	}
	return observation, nil
}

func (s *Store) QueueStats(ctx context.Context) (QueueStats, error) {
	var stats QueueStats
	var oldest sql.NullString
	if err := s.db.QueryRowContext(ctx, `
		SELECT COUNT(*), COALESCE(SUM(payload_size_bytes), 0), MIN(scheduled_at)
		FROM pending_observations`).Scan(
		&stats.PendingCount, &stats.PendingBytes, &oldest,
	); err != nil {
		return QueueStats{}, fmt.Errorf("read pending queue statistics: %w", err)
	}
	if oldest.Valid {
		parsed, err := parseTime(oldest.String)
		if err != nil {
			return QueueStats{}, err
		}
		stats.OldestPendingAt = &parsed
	}
	if err := s.db.QueryRowContext(ctx, `
		SELECT COUNT(*), COALESCE(SUM(payload_size_bytes), 0)
		FROM rejected_observations`).Scan(
		&stats.RejectedCount, &stats.RejectedBytes,
	); err != nil {
		return QueueStats{}, fmt.Errorf("read rejected queue statistics: %w", err)
	}
	return stats, nil
}

func formatTime(value time.Time) string {
	return value.UTC().Format(time.RFC3339Nano)
}

func parseTime(value string) (time.Time, error) {
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("parse stored time: %w", err)
	}
	return parsed, nil
}
