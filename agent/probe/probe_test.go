package probe

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"
)

type fakeConfiguration struct {
	Port int `json:"port"`
}

type fakeProbe struct{}

func (fakeProbe) Type() Type                          { return TypeTCP }
func (fakeProbe) ConfigurationSchemaVersion() uint32  { return 1 }
func (fakeProbe) ResultSchemaVersion() uint32         { return 1 }
func (fakeProbe) Run(context.Context, Request) Result { return Result{} }
func (fakeProbe) Validate(raw json.RawMessage) error {
	configuration, err := DecodeConfigurationStrict[fakeConfiguration](raw)
	if err != nil {
		return err
	}
	if configuration.Port < 1 || configuration.Port > 65535 {
		return errors.New("port is outside 1..65535")
	}
	return nil
}

func TestRegistryValidatesStrictVersionedConfiguration(t *testing.T) {
	registry, err := NewRegistry(fakeProbe{})
	if err != nil {
		t.Fatalf("create registry: %v", err)
	}
	if err := registry.Validate(TypeTCP, 1, json.RawMessage(`{"port":443}`)); err != nil {
		t.Fatalf("validate configuration: %v", err)
	}
	for name, test := range map[string]struct {
		probeType Type
		version   uint32
		content   string
	}{
		"unknown probe": {probeType: Type("smtp"), version: 1, content: `{"port":25}`},
		"old schema":    {probeType: TypeTCP, version: 2, content: `{"port":443}`},
		"unknown field": {probeType: TypeTCP, version: 1, content: `{"port":443,"secret":"x"}`},
		"invalid value": {probeType: TypeTCP, version: 1, content: `{"port":0}`},
		"trailing JSON": {probeType: TypeTCP, version: 1, content: `{"port":443} {}`},
	} {
		t.Run(name, func(t *testing.T) {
			if err := registry.Validate(test.probeType, test.version, json.RawMessage(test.content)); err == nil {
				t.Fatal("invalid configuration was accepted")
			}
		})
	}
}

func TestRegistryRejectsDuplicateProbeAndReportsCapabilities(t *testing.T) {
	if _, err := NewRegistry(fakeProbe{}, fakeProbe{}); err == nil {
		t.Fatal("duplicate probe registration was accepted")
	}
	registry, err := NewRegistry(fakeProbe{})
	if err != nil {
		t.Fatalf("create registry: %v", err)
	}
	capability := registry.Capabilities(map[Type]bool{TypeTCP: true})[TypeTCP]
	if !capability.Available || capability.ConfigurationSchemaVersion != 1 ||
		capability.ResultSchemaVersion != 1 {
		t.Fatalf("TCP capability = %#v", capability)
	}
}

func TestRegistryDetectsAvailabilityWithoutTrustingDetectorPanics(t *testing.T) {
	registry, err := NewRegistry(fakeProbe{})
	if err != nil {
		t.Fatalf("create registry: %v", err)
	}
	available := registry.DetectCapabilities(context.Background(), map[Type]AvailabilityDetector{
		TypeTCP: func(context.Context) bool { return true },
	})
	if !available[TypeTCP].Available {
		t.Fatal("available runtime capability was not reported")
	}
	unavailable := registry.DetectCapabilities(
		context.Background(), map[Type]AvailabilityDetector{
			TypeTCP: func(context.Context) bool { panic("runtime detector failed") },
		},
	)
	if unavailable[TypeTCP].Available {
		t.Fatal("panicking runtime detector reported availability")
	}
}

func TestResultValidationEnforcesCommonSemanticsAndBounds(t *testing.T) {
	now := time.Now().UTC()
	valid := Result{
		StartedAt: now, FinishedAt: now.Add(time.Millisecond),
		ExecutionStatus: ExecutionCompleted, Assessment: AssessmentHealthy,
		ProbeResult: struct{}{},
	}
	if err := valid.Validate(); err != nil {
		t.Fatalf("valid result: %v", err)
	}
	failed := valid
	failed.ExecutionStatus = ExecutionFailed
	if err := failed.Validate(); err == nil {
		t.Fatal("failed result with healthy assessment was accepted")
	}
	unbounded := valid
	unbounded.ErrorMessage = string(make([]byte, MaximumErrorMessageBytes+1))
	category := ErrorInternal
	unbounded.ErrorCategory = &category
	if err := unbounded.Validate(); err == nil {
		t.Fatal("unbounded error message was accepted")
	}
}
