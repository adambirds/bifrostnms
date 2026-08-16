package scheduler

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

const (
	MinimumInterval = 5 * time.Second
	MaximumInterval = 24 * time.Hour
	MinimumTimeout  = 100 * time.Millisecond
)

type Assignment struct {
	ProbeType                  probe.Type
	ConfigurationSchemaVersion uint32
	AgentConfigRevision        int64
	MonitorID                  string
	MonitorRevision            int64
	TargetID                   string
	TargetAddress              string
	Interval                   time.Duration
	Timeout                    time.Duration
	Configuration              json.RawMessage
}

type MissReason string

const (
	MissOverlap  MissReason = "overlap"
	MissCapacity MissReason = "capacity"
)

type MissedRun struct {
	MonitorID   string
	ScheduledAt time.Time
	Reason      MissReason
}

type Execution struct {
	Request probe.Request
	Result  probe.Result
}

type job struct {
	assignment Assignment
	nextDue    time.Time
}

type Scheduler struct {
	registry *probe.Registry
	workers  chan struct{}
	results  chan Execution
	mu       sync.Mutex
	jobs     map[string]*job
	running  map[string]bool
	wait     sync.WaitGroup
}

func New(registry *probe.Registry, maximumConcurrent int) (*Scheduler, error) {
	if registry == nil || maximumConcurrent < 1 {
		return nil, errors.New("registry and positive concurrency limit are required")
	}
	return &Scheduler{
		registry: registry,
		workers:  make(chan struct{}, maximumConcurrent),
		results:  make(chan Execution, maximumConcurrent),
		jobs:     make(map[string]*job),
		running:  make(map[string]bool),
	}, nil
}

func (s *Scheduler) Reconcile(assignments []Assignment, now time.Time) error {
	validated := make(map[string]*job, len(assignments))
	for _, assignment := range assignments {
		if assignment.MonitorID == "" || assignment.MonitorRevision < 1 ||
			assignment.AgentConfigRevision < 1 || assignment.TargetID == "" ||
			assignment.TargetAddress == "" {
			return errors.New("scheduler assignment identity is incomplete")
		}
		if assignment.Interval < MinimumInterval || assignment.Interval > MaximumInterval ||
			assignment.Timeout < MinimumTimeout || assignment.Timeout >= assignment.Interval {
			return fmt.Errorf("monitor %s has invalid scheduling bounds", assignment.MonitorID)
		}
		if _, exists := validated[assignment.MonitorID]; exists {
			return fmt.Errorf("monitor %s is assigned more than once", assignment.MonitorID)
		}
		if err := s.registry.Validate(
			assignment.ProbeType, assignment.ConfigurationSchemaVersion,
			assignment.Configuration,
		); err != nil {
			return err
		}
		validated[assignment.MonitorID] = &job{
			assignment: assignment,
			nextDue:    now.Add(deterministicJitter(assignment.MonitorID, assignment.Interval)),
		}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for monitorID, candidate := range validated {
		if existing, ok := s.jobs[monitorID]; ok &&
			existing.assignment.MonitorRevision == candidate.assignment.MonitorRevision &&
			existing.assignment.AgentConfigRevision == candidate.assignment.AgentConfigRevision {
			candidate.nextDue = existing.nextDue
		}
	}
	s.jobs = validated
	return nil
}

func (s *Scheduler) Tick(ctx context.Context, now time.Time) []MissedRun {
	s.mu.Lock()
	defer s.mu.Unlock()
	var missed []MissedRun
	for _, current := range s.jobs {
		if current.nextDue.After(now) {
			continue
		}
		scheduledAt := current.nextDue
		current.nextDue = scheduledAt.Add(current.assignment.Interval)
		for !current.nextDue.After(now) {
			missed = append(missed, MissedRun{
				MonitorID:   current.assignment.MonitorID,
				ScheduledAt: current.nextDue,
				Reason:      MissCapacity,
			})
			current.nextDue = current.nextDue.Add(current.assignment.Interval)
		}
		if s.running[current.assignment.MonitorID] {
			missed = append(missed, MissedRun{
				MonitorID: current.assignment.MonitorID, ScheduledAt: scheduledAt, Reason: MissOverlap,
			})
			continue
		}
		select {
		case s.workers <- struct{}{}:
			s.running[current.assignment.MonitorID] = true
			s.start(ctx, current, scheduledAt)
		default:
			missed = append(missed, MissedRun{
				MonitorID: current.assignment.MonitorID, ScheduledAt: scheduledAt, Reason: MissCapacity,
			})
		}
	}
	return missed
}

func (s *Scheduler) start(parent context.Context, current *job, scheduledAt time.Time) {
	assignment := current.assignment
	implementation, _ := s.registry.Probe(assignment.ProbeType)
	request := probe.Request{
		ObservationID: newObservationID(assignment.MonitorID, scheduledAt),
		ScheduledAt:   scheduledAt, AgentConfigRevision: assignment.AgentConfigRevision,
		MonitorID: assignment.MonitorID, MonitorRevision: assignment.MonitorRevision,
		TargetID: assignment.TargetID, TargetAddress: assignment.TargetAddress,
		Timeout: assignment.Timeout, Configuration: assignment.Configuration,
	}
	s.wait.Add(1)
	go func() {
		defer s.wait.Done()
		defer func() { <-s.workers }()
		ctx, cancel := context.WithTimeout(parent, assignment.Timeout)
		defer cancel()
		result := implementation.Run(ctx, request)
		if err := result.Validate(); err != nil {
			category := probe.ErrorInternal
			now := time.Now().UTC()
			result = probe.Result{
				StartedAt: now, FinishedAt: now,
				ExecutionStatus: probe.ExecutionFailed, Assessment: probe.AssessmentUnknown,
				ErrorCategory: &category, ErrorCode: "invalid_probe_result",
				ErrorMessage: "Probe returned an invalid result.",
			}
		}
		s.results <- Execution{Request: request, Result: result}
		s.mu.Lock()
		s.running[assignment.MonitorID] = false
		s.mu.Unlock()
	}()
}

func (s *Scheduler) Results() <-chan Execution { return s.results }

func (s *Scheduler) NextDue() map[string]time.Time {
	s.mu.Lock()
	defer s.mu.Unlock()
	result := make(map[string]time.Time, len(s.jobs))
	for monitorID, current := range s.jobs {
		result[monitorID] = current.nextDue
	}
	return result
}

func (s *Scheduler) Wait() { s.wait.Wait() }

func deterministicJitter(identity string, interval time.Duration) time.Duration {
	maximum := interval / 10
	if maximum <= 0 {
		return 0
	}
	digest := sha256.Sum256([]byte(identity))
	return time.Duration(binary.BigEndian.Uint64(digest[:8]) % uint64(maximum))
}

func newObservationID(monitorID string, scheduledAt time.Time) string {
	digest := sha256.Sum256([]byte(monitorID + "/" + scheduledAt.UTC().Format(time.RFC3339Nano)))
	return fmt.Sprintf("%x-%x-%x-%x-%x", digest[:4], digest[4:6], digest[6:8], digest[8:10], digest[10:16])
}
