package protocol

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"
)

const Version = 1

type ProbeCapability struct {
	SchemaVersions []int `json:"schema_versions"`
	Available      bool  `json:"available"`
}

type Capabilities struct {
	Probes        map[string]ProbeCapability `json:"probes"`
	Runtime       map[string]bool            `json:"runtime"`
	ExternalTools map[string]string          `json:"external_tools"`
}

type EnrolmentRequest struct {
	ProtocolVersion int          `json:"protocol_version"`
	EnrolmentToken  string       `json:"enrolment_token"`
	AgentVersion    string       `json:"agent_version"`
	Platform        string       `json:"platform"`
	Architecture    string       `json:"architecture"`
	Hostname        string       `json:"hostname"`
	Capabilities    Capabilities `json:"capabilities"`
}

type EnrolmentResponse struct {
	ProtocolVersion                  int       `json:"protocol_version"`
	RealmID                          string    `json:"realm_id"`
	AgentID                          string    `json:"agent_id"`
	CredentialID                     string    `json:"credential_id"`
	Credential                       string    `json:"credential"`
	ServerTime                       time.Time `json:"server_time"`
	HeartbeatIntervalSeconds         int       `json:"heartbeat_interval_seconds"`
	ConfigurationPollIntervalSeconds int       `json:"configuration_poll_interval_seconds"`
}

type HeartbeatRequest struct {
	ProtocolVersion                   int          `json:"protocol_version"`
	AgentVersion                      string       `json:"agent_version"`
	Platform                          string       `json:"platform"`
	Architecture                      string       `json:"architecture"`
	Hostname                          string       `json:"hostname"`
	Capabilities                      Capabilities `json:"capabilities"`
	ActiveConfigurationRevision       int64        `json:"active_configuration_revision"`
	KnownDesiredConfigurationRevision int64        `json:"known_desired_configuration_revision"`
	QueueDepth                        int64        `json:"queue_depth"`
	QueueBytes                        int64        `json:"queue_bytes"`
	OldestPendingObservationAt        *time.Time   `json:"oldest_pending_observation_at"`
	DatabaseHealth                    string       `json:"database_health"`
	SchedulerState                    string       `json:"scheduler_state"`
	AgentTime                         time.Time    `json:"agent_time"`
	Warnings                          []string     `json:"warnings"`
}

type HeartbeatResponse struct {
	ProtocolVersion                  int       `json:"protocol_version"`
	MinimumProtocolVersion           int       `json:"minimum_protocol_version"`
	MaximumProtocolVersion           int       `json:"maximum_protocol_version"`
	ServerTime                       time.Time `json:"server_time"`
	HeartbeatIntervalSeconds         int       `json:"heartbeat_interval_seconds"`
	ConfigurationPollIntervalSeconds int       `json:"configuration_poll_interval_seconds"`
	DesiredConfigurationRevision     int64     `json:"desired_configuration_revision"`
	DesiredConfigurationHash         string    `json:"desired_configuration_hash"`
	ConfigurationUpdateAvailable     bool      `json:"configuration_update_available"`
}

type MonitorConfiguration struct {
	MonitorID          string                     `json:"monitor_id"`
	TargetID           string                     `json:"target_id"`
	MonitorRevision    int64                      `json:"monitor_revision"`
	TargetAddress      string                     `json:"target_address"`
	ProbeType          string                     `json:"probe_type"`
	ProbeSchemaVersion int                        `json:"probe_schema_version"`
	IntervalSeconds    int                        `json:"interval_seconds"`
	TimeoutSeconds     int                        `json:"timeout_seconds"`
	MissedRunPolicy    string                     `json:"missed_run_policy"`
	Configuration      map[string]json.RawMessage `json:"configuration"`
}

type ConfigurationResponse struct {
	ProtocolVersion            int                    `json:"protocol_version"`
	ConfigurationSchemaVersion int                    `json:"configuration_schema_version"`
	AgentID                    string                 `json:"agent_id"`
	RealmID                    string                 `json:"realm_id"`
	Revision                   int64                  `json:"revision"`
	ContentHash                string                 `json:"content_hash"`
	GeneratedAt                time.Time              `json:"generated_at"`
	Monitors                   []MonitorConfiguration `json:"monitors"`
}

type ConfigurationAcknowledgement struct {
	ProtocolVersion int       `json:"protocol_version"`
	Revision        int64     `json:"revision"`
	ContentHash     string    `json:"content_hash"`
	ActivatedAt     time.Time `json:"activated_at"`
}

type ErrorBody struct {
	Code      string                     `json:"code"`
	Message   string                     `json:"message"`
	Retryable bool                       `json:"retryable"`
	Details   map[string]json.RawMessage `json:"details"`
}

type ErrorResponse struct {
	Error ErrorBody `json:"error"`
}

var (
	ErrConfigurationIdentity   = errors.New("configuration identity does not match enrolled agent")
	ErrConfigurationHash       = errors.New("configuration content hash is invalid")
	ErrConfigurationCapability = errors.New("configuration requires an unsupported capability")
)

func (c ConfigurationResponse) Validate(
	agentID string, realmID string, capabilities Capabilities,
) ([]byte, error) {
	if c.ProtocolVersion != Version || c.ConfigurationSchemaVersion != 1 || c.Revision < 1 {
		return nil, fmt.Errorf("unsupported configuration protocol or schema version")
	}
	if c.AgentID != agentID || c.RealmID != realmID {
		return nil, ErrConfigurationIdentity
	}
	seen := make(map[string]struct{}, len(c.Monitors))
	monitors := make([]any, 0, len(c.Monitors))
	for _, monitor := range c.Monitors {
		if _, exists := seen[monitor.MonitorID]; exists {
			return nil, fmt.Errorf("duplicate monitor %s", monitor.MonitorID)
		}
		seen[monitor.MonitorID] = struct{}{}
		capability, ok := capabilities.Probes[monitor.ProbeType]
		if !ok || !capability.Available || !slices.Contains(
			capability.SchemaVersions, monitor.ProbeSchemaVersion,
		) {
			return nil, fmt.Errorf("%w: monitor=%s probe=%s", ErrConfigurationCapability,
				monitor.MonitorID, monitor.ProbeType)
		}
		if monitor.IntervalSeconds < 1 || monitor.TimeoutSeconds < 1 ||
			monitor.TimeoutSeconds >= monitor.IntervalSeconds || monitor.MissedRunPolicy != "skip" {
			return nil, fmt.Errorf("invalid scheduling policy for monitor %s", monitor.MonitorID)
		}
		var configuration any
		encodedConfiguration, err := json.Marshal(monitor.Configuration)
		if err != nil {
			return nil, fmt.Errorf("encode monitor %s configuration: %w", monitor.MonitorID, err)
		}
		if err := json.Unmarshal(encodedConfiguration, &configuration); err != nil {
			return nil, fmt.Errorf("decode monitor %s configuration: %w", monitor.MonitorID, err)
		}
		monitors = append(monitors, map[string]any{
			"monitor_id":           monitor.MonitorID,
			"target_id":            monitor.TargetID,
			"monitor_revision":     monitor.MonitorRevision,
			"target_address":       monitor.TargetAddress,
			"probe_type":           monitor.ProbeType,
			"probe_schema_version": monitor.ProbeSchemaVersion,
			"interval_seconds":     monitor.IntervalSeconds,
			"timeout_seconds":      monitor.TimeoutSeconds,
			"missed_run_policy":    monitor.MissedRunPolicy,
			"configuration":        configuration,
		})
	}
	canonical, err := json.Marshal(map[string]any{
		"configuration_schema_version": c.ConfigurationSchemaVersion,
		"agent_id":                     c.AgentID,
		"realm_id":                     c.RealmID,
		"monitors":                     monitors,
	})
	if err != nil {
		return nil, fmt.Errorf("canonicalize configuration: %w", err)
	}
	digest := fmt.Sprintf("sha256:%x", sha256.Sum256(canonical))
	if !strings.EqualFold(digest, c.ContentHash) {
		return nil, ErrConfigurationHash
	}
	return canonical, nil
}
