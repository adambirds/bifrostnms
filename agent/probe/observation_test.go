package probe

import (
	"encoding/json"
	"testing"
	"time"
)

func TestObservationSerializationProducesBoundedTypedEnvelope(t *testing.T) {
	scheduledAt := time.Date(2026, 8, 16, 21, 0, 0, 123456789, time.UTC)
	request := Request{
		ObservationID: "00000000-0000-4000-8000-000000000001",
		ScheduledAt:   scheduledAt, AgentConfigRevision: 3,
		MonitorID: "00000000-0000-4000-8000-000000000002", MonitorRevision: 2,
	}
	result := Result{
		StartedAt: scheduledAt.Add(time.Millisecond), FinishedAt: scheduledAt.Add(2 * time.Millisecond),
		ExecutionStatus: ExecutionCompleted, Assessment: AssessmentHealthy,
		ProbeResult: map[string]any{"port": 443, "address_used": "192.0.2.1", "connect_ms": 1.0},
	}
	offset := int64(12)
	encoded, err := EncodeObservation(TypeTCP, request, result, &offset)
	if err != nil {
		t.Fatalf("encode observation: %v", err)
	}
	var content map[string]any
	if err := json.Unmarshal(encoded, &content); err != nil {
		t.Fatalf("decode observation: %v", err)
	}
	if content["probe_type"] != "tcp" || content["execution_status"] != "completed" ||
		content["agent_clock_offset_ms"] != float64(12) {
		t.Fatalf("observation content = %#v", content)
	}
	if content["scheduled_at"] != "2026-08-16T21:00:00.123456Z" {
		t.Fatalf("scheduled_at = %q", content["scheduled_at"])
	}
	if _, present := content["target_address"]; present {
		t.Fatal("observation leaked target configuration")
	}
}

func TestObservationSerializationRejectsInvalidProbeResult(t *testing.T) {
	now := time.Now().UTC()
	_, err := EncodeObservation(TypeTCP, Request{
		ObservationID: "observation", ScheduledAt: now, AgentConfigRevision: 1,
		MonitorID: "monitor", MonitorRevision: 1,
	}, Result{
		StartedAt: now, FinishedAt: now,
		ExecutionStatus: ExecutionFailed, Assessment: AssessmentUnknown,
		ProbeResult: map[string]any{"unexpected": true},
	}, nil)
	if err == nil {
		t.Fatal("failed execution with a typed result was serialized")
	}
}
