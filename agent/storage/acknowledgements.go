package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

const maxRejectionDetailsBytes = 2 * 1024

var ErrUntrustedAcknowledgement = errors.New("upload acknowledgement does not match batch")

type ObservationDisposition string

const (
	DispositionAccepted  ObservationDisposition = "accepted"
	DispositionDuplicate ObservationDisposition = "duplicate"
	DispositionRejected  ObservationDisposition = "rejected"
)

type ObservationAcknowledgement struct {
	ScheduledAt   time.Time
	ObservationID string
	Disposition   ObservationDisposition
	Code          string
	Retryable     bool
	Details       string
	NextAttemptAt time.Time
}

type SynchronizationState struct {
	LastSuccessfulContactAt *time.Time
	LastSuccessfulUploadAt  *time.Time
	ConsecutiveFailureCount int
	ServerBackoffUntil      *time.Time
}

func (s *Store) RecordSynchronizationFailure(
	ctx context.Context, backoffUntil time.Time,
) error {
	_, err := s.db.ExecContext(ctx, `
		UPDATE synchronization_state SET
			consecutive_failure_count = consecutive_failure_count + 1,
			server_backoff_until = ?
		WHERE singleton_id = 1`, formatTime(backoffUntil))
	if err != nil {
		return fmt.Errorf("record synchronization failure: %w", err)
	}
	return nil
}

func (s *Store) SynchronizationState(ctx context.Context) (SynchronizationState, error) {
	var state SynchronizationState
	var lastContact, lastUpload, backoff sql.NullString
	err := s.db.QueryRowContext(ctx, `
		SELECT last_successful_contact_at, last_successful_upload_at,
			consecutive_failure_count, server_backoff_until
		FROM synchronization_state WHERE singleton_id = 1`).Scan(
		&lastContact, &lastUpload, &state.ConsecutiveFailureCount, &backoff,
	)
	if err != nil {
		return SynchronizationState{}, fmt.Errorf("read synchronization state: %w", err)
	}
	var parseErr error
	if state.LastSuccessfulContactAt, parseErr = parseOptionalTime(lastContact); parseErr != nil {
		return SynchronizationState{}, parseErr
	}
	if state.LastSuccessfulUploadAt, parseErr = parseOptionalTime(lastUpload); parseErr != nil {
		return SynchronizationState{}, parseErr
	}
	if state.ServerBackoffUntil, parseErr = parseOptionalTime(backoff); parseErr != nil {
		return SynchronizationState{}, parseErr
	}
	return state, nil
}

func (s *Store) QuarantineObservation(
	ctx context.Context, observation Observation, code string, details string, now time.Time,
) error {
	if code == "" || len(details) > maxRejectionDetailsBytes {
		return errors.New("valid bounded rejection details are required")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin local observation quarantine: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	result, err := tx.ExecContext(ctx, `
		INSERT INTO rejected_observations (
			scheduled_at, observation_id, canonical_payload,
			payload_size_bytes, rejection_code, rejection_details, rejected_at
		)
		SELECT scheduled_at, observation_id, canonical_payload,
			payload_size_bytes, ?, ?, ?
		FROM pending_observations
		WHERE scheduled_at = ? AND observation_id = ?`,
		code, details, formatTime(now), formatTime(observation.ScheduledAt),
		observation.ObservationID,
	)
	if err != nil {
		return fmt.Errorf("quarantine local observation: %w", err)
	}
	inserted, err := result.RowsAffected()
	if err != nil || inserted != 1 {
		return fmt.Errorf("quarantine local observation: pending row not found")
	}
	if _, err := tx.ExecContext(ctx, `
		DELETE FROM pending_observations
		WHERE scheduled_at = ? AND observation_id = ?`,
		formatTime(observation.ScheduledAt), observation.ObservationID,
	); err != nil {
		return fmt.Errorf("remove locally quarantined observation: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit local observation quarantine: %w", err)
	}
	return nil
}

func (s *Store) ApplyAcknowledgements(
	ctx context.Context,
	batch []Observation,
	acknowledgements []ObservationAcknowledgement,
	now time.Time,
) error {
	if err := validateAcknowledgements(batch, acknowledgements); err != nil {
		return err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin acknowledgement cleanup: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	for index, acknowledgement := range acknowledgements {
		observation := batch[index]
		switch acknowledgement.Disposition {
		case DispositionAccepted, DispositionDuplicate:
			if _, err := tx.ExecContext(ctx, `
				DELETE FROM pending_observations
				WHERE scheduled_at = ? AND observation_id = ?`,
				formatTime(observation.ScheduledAt), observation.ObservationID,
			); err != nil {
				return fmt.Errorf("delete acknowledged observation: %w", err)
			}
		case DispositionRejected:
			if acknowledgement.Retryable {
				if _, err := tx.ExecContext(ctx, `
					UPDATE pending_observations SET
						attempt_count = attempt_count + 1,
						next_attempt_at = ?, last_attempt_at = ?, last_error_code = ?
					WHERE scheduled_at = ? AND observation_id = ?`,
					formatTime(acknowledgement.NextAttemptAt), formatTime(now),
					acknowledgement.Code, formatTime(observation.ScheduledAt),
					observation.ObservationID,
				); err != nil {
					return fmt.Errorf("schedule observation retry: %w", err)
				}
				continue
			}
			if _, err := tx.ExecContext(ctx, `
				INSERT INTO rejected_observations (
					scheduled_at, observation_id, canonical_payload,
					payload_size_bytes, rejection_code, rejection_details, rejected_at
				) VALUES (?, ?, ?, ?, ?, ?, ?)`,
				formatTime(observation.ScheduledAt), observation.ObservationID,
				observation.CanonicalPayload, len(observation.CanonicalPayload),
				acknowledgement.Code, acknowledgement.Details, formatTime(now),
			); err != nil {
				return fmt.Errorf("quarantine rejected observation: %w", err)
			}
			if _, err := tx.ExecContext(ctx, `
				DELETE FROM pending_observations
				WHERE scheduled_at = ? AND observation_id = ?`,
				formatTime(observation.ScheduledAt), observation.ObservationID,
			); err != nil {
				return fmt.Errorf("remove quarantined observation: %w", err)
			}
		}
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE synchronization_state SET
			last_successful_contact_at = ?,
			last_successful_upload_at = ?,
			consecutive_failure_count = 0,
			server_backoff_until = NULL
		WHERE singleton_id = 1`, formatTime(now), formatTime(now)); err != nil {
		return fmt.Errorf("update synchronization success: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit acknowledgement cleanup: %w", err)
	}
	return nil
}

func validateAcknowledgements(
	batch []Observation, acknowledgements []ObservationAcknowledgement,
) error {
	if len(batch) == 0 || len(batch) != len(acknowledgements) {
		return ErrUntrustedAcknowledgement
	}
	seen := make(map[string]struct{}, len(acknowledgements))
	for index, acknowledgement := range acknowledgements {
		identity := formatTime(acknowledgement.ScheduledAt) + "/" + acknowledgement.ObservationID
		if _, exists := seen[identity]; exists {
			return ErrUntrustedAcknowledgement
		}
		seen[identity] = struct{}{}
		observation := batch[index]
		// The control plane uses Python datetime/PostgreSQL, both of which preserve
		// microsecond precision. Older queued Go observations may contain nanoseconds,
		// so compare the protocol identity at the precision the server can round-trip.
		if !acknowledgement.ScheduledAt.Truncate(time.Microsecond).Equal(
			observation.ScheduledAt.Truncate(time.Microsecond),
		) || acknowledgement.ObservationID != observation.ObservationID {
			return ErrUntrustedAcknowledgement
		}
		switch acknowledgement.Disposition {
		case DispositionAccepted, DispositionDuplicate:
			if acknowledgement.Code != "" || acknowledgement.Retryable {
				return ErrUntrustedAcknowledgement
			}
		case DispositionRejected:
			if acknowledgement.Code == "" || len(acknowledgement.Details) > maxRejectionDetailsBytes {
				return ErrUntrustedAcknowledgement
			}
			if acknowledgement.Retryable && acknowledgement.NextAttemptAt.IsZero() {
				return ErrUntrustedAcknowledgement
			}
		default:
			return ErrUntrustedAcknowledgement
		}
	}
	return nil
}
