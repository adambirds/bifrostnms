package protocol

import (
	"encoding/json"
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
