package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
)

type ScheduleState struct {
	MonitorID           string
	MonitorRevision     int64
	AgentConfigRevision int64
	NextDueAt           time.Time
	MissedRunCount      int64
}

func (s *Store) RestoreSchedule(
	ctx context.Context,
	monitorID string,
	monitorRevision int64,
	agentConfigRevision int64,
	initialDue time.Time,
	interval time.Duration,
	now time.Time,
) (time.Time, error) {
	if monitorID == "" || monitorRevision < 1 || agentConfigRevision < 1 || interval <= 0 {
		return time.Time{}, errors.New("valid schedule identity and interval are required")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return time.Time{}, fmt.Errorf("begin schedule restoration: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	var storedRevision, storedConfigRevision, missed int64
	var storedNextDue string
	err = tx.QueryRowContext(ctx, `
		SELECT monitor_revision, agent_config_revision, next_due_at, missed_run_count
		FROM scheduler_state WHERE monitor_id = ?`, monitorID,
	).Scan(&storedRevision, &storedConfigRevision, &storedNextDue, &missed)
	nextDue := initialDue
	if err == nil && storedRevision == monitorRevision && storedConfigRevision == agentConfigRevision {
		nextDue, err = parseTime(storedNextDue)
		if err != nil {
			return time.Time{}, err
		}
		for !nextDue.After(now) {
			nextDue = nextDue.Add(interval)
			missed++
		}
	} else if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return time.Time{}, fmt.Errorf("read schedule state: %w", err)
	} else {
		missed = 0
	}
	_, err = tx.ExecContext(ctx, `
		INSERT INTO scheduler_state (
			monitor_id, monitor_revision, agent_config_revision,
			next_due_at, missed_run_count, updated_at
		) VALUES (?, ?, ?, ?, ?, ?)
		ON CONFLICT (monitor_id) DO UPDATE SET
			monitor_revision = excluded.monitor_revision,
			agent_config_revision = excluded.agent_config_revision,
			next_due_at = excluded.next_due_at,
			missed_run_count = excluded.missed_run_count,
			updated_at = excluded.updated_at`,
		monitorID, monitorRevision, agentConfigRevision, formatTime(nextDue), missed,
		formatTime(now),
	)
	if err != nil {
		return time.Time{}, fmt.Errorf("save restored schedule state: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return time.Time{}, fmt.Errorf("commit schedule restoration: %w", err)
	}
	return nextDue, nil
}

func (s *Store) AdvanceSchedule(
	ctx context.Context,
	monitorID string,
	monitorRevision int64,
	agentConfigRevision int64,
	nextDue time.Time,
	missedRuns int64,
	now time.Time,
) error {
	result, err := s.db.ExecContext(ctx, `
		UPDATE scheduler_state SET
			next_due_at = ?, missed_run_count = missed_run_count + ?, updated_at = ?
		WHERE monitor_id = ? AND monitor_revision = ? AND agent_config_revision = ?`,
		formatTime(nextDue), missedRuns, formatTime(now), monitorID, monitorRevision,
		agentConfigRevision,
	)
	if err != nil {
		return fmt.Errorf("advance schedule state: %w", err)
	}
	updated, err := result.RowsAffected()
	if err != nil || updated != 1 {
		return errors.New("schedule state changed before it could be advanced")
	}
	return nil
}

func (s *Store) RemoveSchedulesExcept(ctx context.Context, monitorIDs []string) error {
	if len(monitorIDs) == 0 {
		_, err := s.db.ExecContext(ctx, "DELETE FROM scheduler_state")
		return err
	}
	placeholders := strings.TrimRight(strings.Repeat("?,", len(monitorIDs)), ",")
	values := make([]any, len(monitorIDs))
	for index, monitorID := range monitorIDs {
		values[index] = monitorID
	}
	// The placeholders are generated solely from the bounded assignment count.
	_, err := s.db.ExecContext(ctx,
		"DELETE FROM scheduler_state WHERE monitor_id NOT IN ("+placeholders+")", values...)
	if err != nil {
		return fmt.Errorf("remove obsolete schedule state: %w", err)
	}
	return nil
}

func (s *Store) ScheduleState(ctx context.Context, monitorID string) (ScheduleState, error) {
	var state ScheduleState
	var nextDue string
	err := s.db.QueryRowContext(ctx, `
		SELECT monitor_id, monitor_revision, agent_config_revision,
			next_due_at, missed_run_count
		FROM scheduler_state WHERE monitor_id = ?`, monitorID,
	).Scan(
		&state.MonitorID, &state.MonitorRevision, &state.AgentConfigRevision,
		&nextDue, &state.MissedRunCount,
	)
	if err != nil {
		return ScheduleState{}, err
	}
	state.NextDueAt, err = parseTime(nextDue)
	return state, err
}
