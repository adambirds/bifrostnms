package scheduler

import (
	"context"
	"encoding/json"
	"sync/atomic"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type controlledProbe struct {
	runs    *atomic.Int32
	started chan struct{}
	release <-chan struct{}
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
	if err := scheduler.Reconcile([]Assignment{testAssignment("monitor-a")}, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	due := scheduler.NextDue()["monitor-a"]
	if missed := scheduler.Tick(context.Background(), due); len(missed) != 0 {
		t.Fatalf("initial missed runs = %#v", missed)
	}
	<-started
	missed := scheduler.Tick(context.Background(), due.Add(5*time.Second))
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
	if err := scheduler.Reconcile(assignments, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	due := scheduler.NextDue()
	latestDue := due["monitor-a"]
	if due["monitor-b"].After(latestDue) {
		latestDue = due["monitor-b"]
	}
	missed := scheduler.Tick(context.Background(), latestDue)
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
	if err := scheduler.Reconcile([]Assignment{assignment}, now); err != nil {
		t.Fatalf("reconcile scheduler: %v", err)
	}
	scheduler.Tick(context.Background(), scheduler.NextDue()["monitor-a"])
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
	if err := scheduler.Reconcile([]Assignment{assignment}, time.Now().UTC()); err == nil {
		t.Fatal("invalid scheduling bounds were accepted")
	}
}
