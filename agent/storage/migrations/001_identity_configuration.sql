CREATE TABLE agent_identity (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    agent_id TEXT NOT NULL,
    realm_id TEXT NOT NULL,
    control_plane_url TEXT NOT NULL,
    enrolled_at TEXT NOT NULL
);

CREATE TABLE credentials (
    credential_id TEXT PRIMARY KEY,
    secret TEXT NOT NULL,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    retire_after TEXT
);

CREATE TABLE configuration_snapshots (
    revision INTEGER PRIMARY KEY CHECK (revision > 0),
    content_hash TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    canonical_payload BLOB NOT NULL,
    downloaded_at TEXT NOT NULL,
    validated_at TEXT,
    activated_at TEXT,
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    rejection_code TEXT,
    rejection_details TEXT
);

CREATE UNIQUE INDEX configuration_one_active_idx
    ON configuration_snapshots (active)
    WHERE active = 1;
