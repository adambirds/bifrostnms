package scheduler

import (
	"context"
	"encoding/json"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	"github.com/adambirds/bifrostnms/agent/storage"
)

type controlledProbe struct {
	runs    *atomic.Int32
	started chan struct{}
	release <-chan struct{}
}

type panicProbe struct{ controlledProbe }

func (panicProbe) Run(context.Context, probe.Request) probe.Result {
	panic("sensitive implementation detail")
}

func (controlledProbe) Type() probe.Type                   { return probe.TypeTCP }
func (controlledProbe) ConfigurationSchemaVersion() uint32 { return 1 }
func (controlledProbe) ResultSchemaVersion() uint32        { return 1 }
func (controlledProbe) Validate(json.RawMessage) error     { return nil }
func (p controlledProbe) Run(ctx context.Context, _ probe.Request) probe.Result {
	p.runs.Add(1)
	if p.started != nil {
		p.started <- struct{}{}
	}
	startedAt := time.Now().UTC()
	if p.release != nil {
		select {
		case <-p.release:
		case <-ctx.Done():
		}
	}
	return probe.Result{
		StartedAt: startedAt, FinishedAt: time.Now().UTC(),
		ExecutionStatus: probe.ExecutionCompleted, Assessment: probe.AssessmentHealthy,
	}
}

func testAssignment(monitorID string) Assignment {
	return Assignment{
		ProbeType: probe.TypeTCP, ConfigurationSchemaVersion: 1,
		AgentConfigRevision: 1, MonitorID: monitorID, MonitorRevision: 1,
		TargetID: "target", TargetAddress: "127.0.0.1",
		Interval: 5 * time.Second, Timeout: time.Second,
		Configuration: json.RawMessage(`{"port":443}`),
	}
}

func TestSchedulerUsesScheduledIntervalsWithoutOverlap(t *testing.T) {
	var runs atomic.Int32
	started := make(chan struct{}, 1)
	release := make(chan struct{})
	registry, _ := probe.NewRegistry(controlledProbe{
		runs: &runs, started: started, release: release,
	})
	scheduler, _ := New(registry, 2)
	now := time.Date(2026, 8, 16, 19, 0, 0, 0, time.UTC)
	if err := scheduler.Reconcile(context.Background(), []Assignment{testAssignment("monitor-a")}, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	due := scheduler.NextDue()["monitor-a"]
	if missed, err := scheduler.Tick(context.Background(), due); err != nil || len(missed) != 0 {
		t.Fatalf("initial missed runs = %#v", missed)
	}
	<-started
	missed, err := scheduler.Tick(context.Background(), due.Add(5*time.Second))
	if err != nil {
		t.Fatalf("tick scheduler: %v", err)
	}
	if len(missed) != 1 || missed[0].Reason != MissOverlap {
		t.Fatalf("overlap missed runs = %#v", missed)
	}
	close(release)
	scheduler.Wait()
	if runs.Load() != 1 {
		t.Fatalf("probe run count = %d", runs.Load())
	}
	result := <-scheduler.Results()
	if !result.Request.ScheduledAt.Equal(due) || result.Request.ObservationID == "" {
		t.Fatalf("probe request = %#v", result.Request)
	}
}

func TestSchedulerBoundsConcurrencyAndReportsCapacity(t *testing.T) {
	var runs atomic.Int32
	started := make(chan struct{}, 2)
	release := make(chan struct{})
	registry, _ := probe.NewRegistry(controlledProbe{
		runs: &runs, started: started, release: release,
	})
	scheduler, _ := New(registry, 1)
	now := time.Date(2026, 8, 16, 19, 0, 0, 0, time.UTC)
	assignments := []Assignment{testAssignment("monitor-a"), testAssignment("monitor-b")}
	if err := scheduler.Reconcile(context.Background(), assignments, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	due := scheduler.NextDue()
	latestDue := due["monitor-a"]
	if due["monitor-b"].After(latestDue) {
		latestDue = due["monitor-b"]
	}
	missed, err := scheduler.Tick(context.Background(), latestDue)
	if err != nil {
		t.Fatalf("tick scheduler: %v", err)
	}
	if len(missed) != 1 || missed[0].Reason != MissCapacity {
		t.Fatalf("capacity missed runs = %#v", missed)
	}
	<-started
	if runs.Load() != 1 {
		t.Fatalf("concurrent probe count = %d", runs.Load())
	}
	close(release)
	scheduler.Wait()
	<-scheduler.Results()
}

func TestSchedulerDeadlineCancelsProbe(t *testing.T) {
	var runs atomic.Int32
	release := make(chan struct{})
	registry, _ := probe.NewRegistry(controlledProbe{runs: &runs, release: release})
	scheduler, _ := New(registry, 1)
	now := time.Date(2026, 8, 16, 19, 0, 0, 0, time.UTC)
	assignment := testAssignment("monitor-a")
	assignment.Timeout = MinimumTimeout
	if err := scheduler.Reconcile(context.Background(), []Assignment{assignment}, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	if _, err := scheduler.Tick(context.Background(), scheduler.NextDue()["monitor-a"]); err != nil {
		t.Fatalf("tick scheduler: %v", err)
	}
	select {
	case <-scheduler.Results():
	case <-time.After(time.Second):
		t.Fatal("probe did not honor the scheduler deadline")
	}
	scheduler.Wait()
}

func TestReconcileRejectsInvalidSchedulingBounds(t *testing.T) {
	var runs atomic.Int32
	registry, _ := probe.NewRegistry(controlledProbe{runs: &runs})
	scheduler, _ := New(registry, 1)
	assignment := testAssignment("monitor-a")
	assignment.Timeout = assignment.Interval
	if err := scheduler.Reconcile(
		context.Background(), []Assignment{assignment}, time.Now().UTC(),
	); err == nil {
		t.Fatal("invalid scheduling bounds were accepted")
	}
}

func TestPersistedSchedulerSkipsElapsedRunsAfterRestart(t *testing.T) {
	ctx := context.Background()
	store, err := storage.Open(ctx, filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	var runs atomic.Int32
	registry, _ := probe.NewRegistry(controlledProbe{runs: &runs})
	first, _ := New(registry, 1, WithStateStore(store))
	now := time.Date(2026, 8, 16, 22, 0, 0, 0, time.UTC)
	assignment := testAssignment("monitor-a")
	if err := first.Reconcile(ctx, []Assignment{assignment}, now); err != nil {
		t.Fatalf("reconcile initial scheduler: %v", err)
	}
	due := first.NextDue()[assignment.MonitorID]
	if _, err := first.Tick(ctx, due); err != nil {
		t.Fatalf("run initial schedule: %v", err)
	}
	first.Wait()
	<-first.Results()

	restartedAt := due.Add(3*assignment.Interval + time.Second)
	restarted, _ := New(registry, 1, WithStateStore(store))
	if err := restarted.Reconcile(ctx, []Assignment{assignment}, restartedAt); err != nil {
		t.Fatalf("reconcile restarted scheduler: %v", err)
	}
	restoredDue := restarted.NextDue()[assignment.MonitorID]
	if !restoredDue.After(restartedAt) {
		t.Fatalf("restored due time %v does not skip restart time %v", restoredDue, restartedAt)
	}
	if missed, err := restarted.Tick(ctx, restartedAt); err != nil || len(missed) != 0 {
		t.Fatalf("restart tick missed = %#v, error = %v", missed, err)
	}
	state, err := store.ScheduleState(ctx, assignment.MonitorID)
	if err != nil || state.MissedRunCount != 3 {
		t.Fatalf("persisted schedule state = %#v, error = %v", state, err)
	}
}

func TestSchedulerRunCancelsActiveProbeOnShutdown(t *testing.T) {
	var runs atomic.Int32
	started := make(chan struct{}, 1)
	release := make(chan struct{})
	registry, _ := probe.NewRegistry(controlledProbe{
		runs: &runs, started: started, release: release,
	})
	scheduler, _ := New(registry, 1)
	assignment := testAssignment("monitor-a")
	assignment.Timeout = 4 * time.Second
	now := time.Now().UTC()
	if err := scheduler.Reconcile(context.Background(), []Assignment{assignment}, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- scheduler.Run(ctx, time.Millisecond, nil) }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("scheduled probe did not start")
	}
	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("stop scheduler: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("scheduler did not cancel active probe during shutdown")
	}
	<-scheduler.Results()
}

func TestSchedulerContainsProbePanic(t *testing.T) {
	registry, _ := probe.NewRegistry(panicProbe{})
	scheduler, _ := New(registry, 1)
	now := time.Now().UTC()
	if err := scheduler.Reconcile(
		context.Background(), []Assignment{testAssignment("monitor-a")}, now,
	); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	if _, err := scheduler.Tick(context.Background(), scheduler.NextDue()["monitor-a"]); err != nil {
		t.Fatalf("tick scheduler: %v", err)
	}
	result := <-scheduler.Results()
	if result.Result.ExecutionStatus != probe.ExecutionFailed ||
		result.Result.ErrorCode != "probe_panic" ||
		result.Result.ErrorMessage != "Probe stopped after an internal failure." {
		t.Fatalf("contained panic result = %#v", result.Result)
	}
	scheduler.Wait()
}
