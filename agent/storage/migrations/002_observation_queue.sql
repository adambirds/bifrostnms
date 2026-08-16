CREATE TABLE pending_observations (
    scheduled_at TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    monitor_id TEXT NOT NULL,
    monitor_revision INTEGER NOT NULL CHECK (monitor_revision > 0),
    agent_config_revision INTEGER NOT NULL CHECK (agent_config_revision > 0),
    probe_type TEXT NOT NULL,
    canonical_payload BLOB NOT NULL,
    payload_size_bytes INTEGER NOT NULL CHECK (payload_size_bytes > 0),
    created_at TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TEXT NOT NULL,
    last_attempt_at TEXT,
    last_error_code TEXT,
    PRIMARY KEY (scheduled_at, observation_id)
);

CREATE INDEX pending_observations_ready_idx
    ON pending_observations (next_attempt_at, scheduled_at, observation_id);

CREATE TABLE rejected_observations (
    scheduled_at TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    canonical_payload BLOB NOT NULL,
    payload_size_bytes INTEGER NOT NULL CHECK (payload_size_bytes > 0),
    rejection_code TEXT NOT NULL,
    rejection_details TEXT,
    rejected_at TEXT NOT NULL,
    PRIMARY KEY (scheduled_at, observation_id)
);

CREATE TABLE synchronization_state (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    last_successful_contact_at TEXT,
    last_successful_upload_at TEXT,
    consecutive_failure_count INTEGER NOT NULL DEFAULT 0,
    server_backoff_until TEXT
);

INSERT INTO synchronization_state (singleton_id) VALUES (1);
