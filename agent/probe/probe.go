package probe

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"slices"
	"time"
)

const MaximumErrorMessageBytes = 500

type Type string

const (
	TypeICMP Type = "icmp"
	TypeHTTP Type = "http"
	TypeTCP  Type = "tcp"
	TypeDNS  Type = "dns"
	TypeTLS  Type = "tls"
)

type ExecutionStatus string

const (
	ExecutionCompleted ExecutionStatus = "completed"
	ExecutionFailed    ExecutionStatus = "failed"
)

type Assessment string

const (
	AssessmentHealthy   Assessment = "healthy"
	AssessmentUnhealthy Assessment = "unhealthy"
	AssessmentUnknown   Assessment = "unknown"
)

type ErrorCategory string

const (
	ErrorTimeout              ErrorCategory = "timeout"
	ErrorResolution           ErrorCategory = "resolution"
	ErrorConnection           ErrorCategory = "connection"
	ErrorTLS                  ErrorCategory = "tls"
	ErrorProtocol             ErrorCategory = "protocol"
	ErrorAssertion            ErrorCategory = "assertion"
	ErrorPermission           ErrorCategory = "permission"
	ErrorInvalidConfiguration ErrorCategory = "invalid_configuration"
	ErrorResourceLimit        ErrorCategory = "resource_limit"
	ErrorInternal             ErrorCategory = "internal"
)

type Request struct {
	ObservationID       string
	ScheduledAt         time.Time
	AgentConfigRevision int64
	MonitorID           string
	MonitorRevision     int64
	TargetID            string
	TargetAddress       string
	Timeout             time.Duration
	Configuration       json.RawMessage
}

type Result struct {
	StartedAt       time.Time
	FinishedAt      time.Time
	ExecutionStatus ExecutionStatus
	Assessment      Assessment
	ErrorCategory   *ErrorCategory
	ErrorCode       string
	ErrorMessage    string
	ProbeResult     any
}

func (r Result) Validate() error {
	if r.StartedAt.IsZero() || r.FinishedAt.Before(r.StartedAt) {
		return errors.New("probe result timestamps are invalid")
	}
	if !slices.Contains(
		[]ExecutionStatus{ExecutionCompleted, ExecutionFailed}, r.ExecutionStatus,
	) {
		return errors.New("probe execution status is invalid")
	}
	if !slices.Contains(
		[]Assessment{AssessmentHealthy, AssessmentUnhealthy, AssessmentUnknown}, r.Assessment,
	) {
		return errors.New("probe assessment is invalid")
	}
	if r.ExecutionStatus == ExecutionFailed && r.Assessment != AssessmentUnknown {
		return errors.New("failed probe execution must have unknown assessment")
	}
	if r.ExecutionStatus == ExecutionFailed && r.ProbeResult != nil {
		return errors.New("failed probe execution cannot include a typed result")
	}
	if r.ExecutionStatus == ExecutionCompleted && r.ProbeResult == nil {
		return errors.New("completed probe execution requires a typed result")
	}
	if len(r.ErrorMessage) > MaximumErrorMessageBytes {
		return errors.New("probe error message exceeds the safe bound")
	}
	if r.ErrorCategory == nil && (r.ErrorCode != "" || r.ErrorMessage != "") {
		return errors.New("probe error details require an error category")
	}
	if r.ErrorCategory != nil && !slices.Contains([]ErrorCategory{
		ErrorTimeout, ErrorResolution, ErrorConnection, ErrorTLS, ErrorProtocol,
		ErrorAssertion, ErrorPermission, ErrorInvalidConfiguration, ErrorResourceLimit,
		ErrorInternal,
	}, *r.ErrorCategory) {
		return errors.New("probe error category is invalid")
	}
	return nil
}

type Probe interface {
	Type() Type
	ConfigurationSchemaVersion() uint32
	ResultSchemaVersion() uint32
	Validate(raw json.RawMessage) error
	Run(ctx context.Context, request Request) Result
}

type Capability struct {
	ConfigurationSchemaVersion uint32
	ResultSchemaVersion        uint32
	Available                  bool
}

type AvailabilityDetector func(context.Context) bool

type Registry struct {
	probes map[Type]Probe
}

func NewRegistry(probes ...Probe) (*Registry, error) {
	registry := &Registry{probes: make(map[Type]Probe, len(probes))}
	for _, implementation := range probes {
		if implementation == nil || implementation.Type() == "" ||
			implementation.ConfigurationSchemaVersion() == 0 ||
			implementation.ResultSchemaVersion() == 0 {
			return nil, errors.New("probe registration is incomplete")
		}
		if _, exists := registry.probes[implementation.Type()]; exists {
			return nil, fmt.Errorf("probe type %q is registered more than once", implementation.Type())
		}
		registry.probes[implementation.Type()] = implementation
	}
	return registry, nil
}

func (r *Registry) Probe(probeType Type) (Probe, bool) {
	implementation, ok := r.probes[probeType]
	return implementation, ok
}

func (r *Registry) Validate(
	probeType Type, configurationSchemaVersion uint32, raw json.RawMessage,
) error {
	implementation, ok := r.Probe(probeType)
	if !ok {
		return fmt.Errorf("probe type %q is unsupported", probeType)
	}
	if implementation.ConfigurationSchemaVersion() != configurationSchemaVersion {
		return fmt.Errorf(
			"probe %q configuration schema %d is unsupported",
			probeType, configurationSchemaVersion,
		)
	}
	if err := implementation.Validate(raw); err != nil {
		return fmt.Errorf("validate probe %q configuration: %w", probeType, err)
	}
	return nil
}

func (r *Registry) Capabilities(availability map[Type]bool) map[Type]Capability {
	capabilities := make(map[Type]Capability, len(r.probes))
	for probeType, implementation := range r.probes {
		capabilities[probeType] = Capability{
			ConfigurationSchemaVersion: implementation.ConfigurationSchemaVersion(),
			ResultSchemaVersion:        implementation.ResultSchemaVersion(),
			Available:                  availability[probeType],
		}
	}
	return capabilities
}

func (r *Registry) DetectCapabilities(
	ctx context.Context, detectors map[Type]AvailabilityDetector,
) map[Type]Capability {
	availability := make(map[Type]bool, len(r.probes))
	for probeType := range r.probes {
		if detector := detectors[probeType]; detector != nil {
			availability[probeType] = detectSafely(ctx, detector)
		}
	}
	return r.Capabilities(availability)
}

func detectSafely(ctx context.Context, detector AvailabilityDetector) (available bool) {
	defer func() {
		if recover() != nil {
			available = false
		}
	}()
	return detector(ctx)
}

func DecodeConfigurationStrict[T any](raw json.RawMessage) (T, error) {
	var configuration T
	if err := DecodeConfigurationStrictInto(raw, &configuration); err != nil {
		return configuration, err
	}
	return configuration, nil
}

func DecodeConfigurationStrictInto(raw json.RawMessage, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode configuration: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("configuration contains trailing data")
	}
	return nil
}
