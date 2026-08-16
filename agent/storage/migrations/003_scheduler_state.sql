CREATE TABLE scheduler_state (
    monitor_id TEXT PRIMARY KEY,
    monitor_revision INTEGER NOT NULL CHECK (monitor_revision > 0),
    agent_config_revision INTEGER NOT NULL CHECK (agent_config_revision > 0),
    next_due_at TEXT NOT NULL,
    missed_run_count INTEGER NOT NULL DEFAULT 0 CHECK (missed_run_count >= 0),
    updated_at TEXT NOT NULL
);
