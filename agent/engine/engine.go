package engine

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	"github.com/adambirds/bifrostnms/agent/scheduler"
	"github.com/adambirds/bifrostnms/agent/storage"
)

type activeConfiguration struct {
	ConfigurationSchemaVersion int                 `json:"configuration_schema_version"`
	Monitors                   []monitorAssignment `json:"monitors"`
}

type monitorAssignment struct {
	MonitorID          string          `json:"monitor_id"`
	TargetID           string          `json:"target_id"`
	MonitorRevision    int64           `json:"monitor_revision"`
	TargetAddress      string          `json:"target_address"`
	ProbeType          probe.Type      `json:"probe_type"`
	ProbeSchemaVersion uint32          `json:"probe_schema_version"`
	IntervalSeconds    int             `json:"interval_seconds"`
	TimeoutSeconds     int             `json:"timeout_seconds"`
	MissedRunPolicy    string          `json:"missed_run_policy"`
	Configuration      json.RawMessage `json:"configuration"`
}

type Engine struct {
	store     *storage.Store
	scheduler *scheduler.Scheduler
	limits    storage.QueueLimits
}

func New(
	store *storage.Store, registry *probe.Registry, maximumConcurrent int,
	limits storage.QueueLimits,
) (*Engine, error) {
	if store == nil {
		return nil, errors.New("agent store is required")
	}
	schedule, err := scheduler.New(
		registry, maximumConcurrent, scheduler.WithStateStore(store),
	)
	if err != nil {
		return nil, err
	}
	return &Engine{store: store, scheduler: schedule, limits: limits}, nil
}

func (e *Engine) LoadActiveConfiguration(ctx context.Context, now time.Time) error {
	snapshot, err := e.store.ActiveConfiguration(ctx)
	if errors.Is(err, sql.ErrNoRows) {
		return e.scheduler.Reconcile(ctx, nil, now)
	}
	if err != nil {
		return fmt.Errorf("read active configuration: %w", err)
	}
	var configuration activeConfiguration
	if err := json.Unmarshal(snapshot.CanonicalPayload, &configuration); err != nil {
		return fmt.Errorf("decode active configuration: %w", err)
	}
	if configuration.ConfigurationSchemaVersion != 1 {
		return errors.New("active configuration schema is unsupported")
	}
	assignments := make([]scheduler.Assignment, 0, len(configuration.Monitors))
	for _, monitor := range configuration.Monitors {
		if monitor.MissedRunPolicy != "skip" {
			return fmt.Errorf("monitor %s has unsupported missed-run policy", monitor.MonitorID)
		}
		assignments = append(assignments, scheduler.Assignment{
			ProbeType: monitor.ProbeType, ConfigurationSchemaVersion: monitor.ProbeSchemaVersion,
			AgentConfigRevision: snapshot.Revision,
			MonitorID:           monitor.MonitorID, MonitorRevision: monitor.MonitorRevision,
			TargetID: monitor.TargetID, TargetAddress: monitor.TargetAddress,
			Interval:      time.Duration(monitor.IntervalSeconds) * time.Second,
			Timeout:       time.Duration(monitor.TimeoutSeconds) * time.Second,
			Configuration: monitor.Configuration,
		})
	}
	return e.scheduler.Reconcile(ctx, assignments, now)
}

func (e *Engine) Tick(ctx context.Context, now time.Time) ([]scheduler.MissedRun, error) {
	return e.scheduler.Tick(ctx, now)
}

func (e *Engine) Results() <-chan scheduler.Execution { return e.scheduler.Results() }
func (e *Engine) NextDue() map[string]time.Time       { return e.scheduler.NextDue() }

func (e *Engine) RecordExecution(
	ctx context.Context, execution scheduler.Execution, createdAt time.Time,
) error {
	request := execution.Request
	request.ScheduledAt = request.ScheduledAt.Truncate(time.Microsecond)
	execution.Result.StartedAt = execution.Result.StartedAt.Truncate(time.Microsecond)
	execution.Result.FinishedAt = execution.Result.FinishedAt.Truncate(time.Microsecond)
	if execution.Result.ExecutionStatus == probe.ExecutionFailed {
		attributes := []any{
			"monitor_id", request.MonitorID,
			"target_id", request.TargetID,
			"target_address", request.TargetAddress,
			"probe_type", execution.ProbeType,
			"error_code", execution.Result.ErrorCode,
			"error_message", execution.Result.ErrorMessage,
		}
		if execution.Result.ErrorCategory != nil {
			attributes = append(attributes, "error_category", *execution.Result.ErrorCategory)
		}
		if execution.Result.DiagnosticError != "" {
			attributes = append(attributes, "diagnostic_error", execution.Result.DiagnosticError)
		}
		slog.Warn("probe execution failed", attributes...)
	}
	payload, err := probe.EncodeObservation(
		execution.ProbeType, request, execution.Result, nil,
	)
	if err != nil {
		return fmt.Errorf("encode completed probe execution: %w", err)
	}
	return e.store.EnqueueObservation(ctx, storage.Observation{
		ScheduledAt:         request.ScheduledAt,
		ObservationID:       request.ObservationID,
		MonitorID:           request.MonitorID,
		MonitorRevision:     request.MonitorRevision,
		AgentConfigRevision: request.AgentConfigRevision,
		ProbeType:           string(execution.ProbeType), CanonicalPayload: payload,
		CreatedAt: createdAt,
	}, e.limits)
}

func (e *Engine) Wait() { e.scheduler.Wait() }

func (e *Engine) Run(
	ctx context.Context, tickInterval time.Duration,
	reportMissed func([]scheduler.MissedRun),
) error {
	runContext, cancel := context.WithCancel(ctx)
	defer cancel()
	schedulerErrors := make(chan error, 1)
	go func() {
		schedulerErrors <- e.scheduler.Run(runContext, tickInterval, reportMissed)
	}()
	for {
		select {
		case execution := <-e.Results():
			if err := e.RecordExecution(runContext, execution, time.Now().UTC()); err != nil {
				cancel()
				<-schedulerErrors
				return err
			}
		case err := <-schedulerErrors:
			for {
				select {
				case execution := <-e.Results():
					if recordErr := e.RecordExecution(
						context.WithoutCancel(ctx), execution, time.Now().UTC(),
					); recordErr != nil {
						return recordErr
					}
				default:
					return err
				}
			}
		}
	}
}
