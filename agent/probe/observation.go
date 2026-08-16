package probe

import (
	"encoding/json"
	"fmt"
)

type observationEnvelope struct {
	ScheduledAt        string          `json:"scheduled_at"`
	ObservationID      string          `json:"observation_id"`
	MonitorID          string          `json:"monitor_id"`
	MonitorRevision    int64           `json:"monitor_revision"`
	ProbeType          Type            `json:"probe_type"`
	StartedAt          string          `json:"started_at"`
	FinishedAt         string          `json:"finished_at"`
	ExecutionStatus    ExecutionStatus `json:"execution_status"`
	Assessment         Assessment      `json:"assessment"`
	ErrorCategory      *ErrorCategory  `json:"error_category"`
	ErrorCode          *string         `json:"error_code"`
	ErrorMessage       *string         `json:"error_message"`
	AgentClockOffsetMS *int64          `json:"agent_clock_offset_ms"`
	Result             any             `json:"result"`
}

func EncodeObservation(
	probeType Type, request Request, result Result, agentClockOffsetMS *int64,
) ([]byte, error) {
	if probeType == "" || request.ObservationID == "" || request.MonitorID == "" ||
		request.MonitorRevision < 1 || request.AgentConfigRevision < 1 {
		return nil, fmt.Errorf("observation identity is incomplete")
	}
	if err := result.Validate(); err != nil {
		return nil, fmt.Errorf("validate observation result: %w", err)
	}
	var errorCode, errorMessage *string
	if result.ErrorCode != "" {
		errorCode = &result.ErrorCode
	}
	if result.ErrorMessage != "" {
		errorMessage = &result.ErrorMessage
	}
	encoded, err := json.Marshal(observationEnvelope{
		ScheduledAt:   request.ScheduledAt.UTC().Format(timeFormat),
		ObservationID: request.ObservationID, MonitorID: request.MonitorID,
		MonitorRevision: request.MonitorRevision, ProbeType: probeType,
		StartedAt:       result.StartedAt.UTC().Format(timeFormat),
		FinishedAt:      result.FinishedAt.UTC().Format(timeFormat),
		ExecutionStatus: result.ExecutionStatus, Assessment: result.Assessment,
		ErrorCategory: result.ErrorCategory, ErrorCode: errorCode, ErrorMessage: errorMessage,
		AgentClockOffsetMS: agentClockOffsetMS, Result: result.ProbeResult,
	})
	if err != nil {
		return nil, fmt.Errorf("encode observation: %w", err)
	}
	return encoded, nil
}

const timeFormat = "2006-01-02T15:04:05.999999999Z07:00"
