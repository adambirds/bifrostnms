package storage

import (
	"context"
	"database/sql"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

const (
	DefaultPath          = "/var/lib/bifrostnms-agent/agent.db"
	defaultBusyTimeout   = 5 * time.Second
	CurrentSchemaVersion = 2
)

var (
	ErrIdentityMismatch   = errors.New("stored agent identity does not match requested identity")
	ErrCredentialMismatch = errors.New("stored credential secret does not match")
	ErrNewerSchema        = errors.New("agent database schema is newer than this binary supports")
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

type Store struct {
	db *sql.DB
}

type Identity struct {
	AgentID         string
	RealmID         string
	ControlPlaneURL string
	EnrolledAt      time.Time
}

type Credential struct {
	CredentialID string
	Secret       string
	CreatedAt    time.Time
	ActivatedAt  *time.Time
	RetireAfter  *time.Time
}

func Open(ctx context.Context, path string) (*Store, error) {
	if path == "" {
		return nil, errors.New("agent database path is required")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("create agent database directory: %w", err)
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open agent database: %w", err)
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	store := &Store{db: db}
	if err := store.initialize(ctx); err != nil {
		_ = db.Close()
		return nil, err
	}
	if err := os.Chmod(path, 0o600); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("restrict agent database permissions: %w", err)
	}
	return store, nil
}

func (s *Store) Close() error {
	return s.db.Close()
}

func (s *Store) initialize(ctx context.Context) error {
	pragmas := []string{
		"PRAGMA journal_mode = WAL",
		"PRAGMA foreign_keys = ON",
		fmt.Sprintf("PRAGMA busy_timeout = %d", defaultBusyTimeout.Milliseconds()),
		"PRAGMA synchronous = FULL",
	}
	for _, statement := range pragmas {
		if _, err := s.db.ExecContext(ctx, statement); err != nil {
			return fmt.Errorf("configure agent database: %w", err)
		}
	}
	var integrity string
	if err := s.db.QueryRowContext(ctx, "PRAGMA quick_check").Scan(&integrity); err != nil {
		return fmt.Errorf("check agent database integrity: %w", err)
	}
	if integrity != "ok" {
		return fmt.Errorf("agent database integrity check failed: %s", integrity)
	}
	return s.migrate(ctx)
}

func (s *Store) migrate(ctx context.Context) error {
	if _, err := s.db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version INTEGER PRIMARY KEY,
			applied_at TEXT NOT NULL
		)`); err != nil {
		return fmt.Errorf("create schema migration table: %w", err)
	}
	entries, err := fs.Glob(migrationFiles, "migrations/*.sql")
	if err != nil {
		return fmt.Errorf("list embedded migrations: %w", err)
	}
	sort.Strings(entries)
	if len(entries) != CurrentSchemaVersion {
		return fmt.Errorf(
			"embedded migration count = %d, expected %d",
			len(entries), CurrentSchemaVersion,
		)
	}
	var current int
	if err := s.db.QueryRowContext(
		ctx, "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
	).Scan(&current); err != nil {
		return fmt.Errorf("read agent schema version: %w", err)
	}
	if current > CurrentSchemaVersion {
		return fmt.Errorf(
			"%w: database=%d supported=%d", ErrNewerSchema, current, CurrentSchemaVersion,
		)
	}
	for _, name := range entries[current:] {
		if err := s.applyMigration(ctx, name); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) applyMigration(ctx context.Context, name string) error {
	prefix, _, ok := strings.Cut(filepath.Base(name), "_")
	if !ok {
		return fmt.Errorf("invalid embedded migration name %q", name)
	}
	version, err := strconv.Atoi(prefix)
	if err != nil {
		return fmt.Errorf("invalid embedded migration version %q: %w", prefix, err)
	}
	content, err := migrationFiles.ReadFile(name)
	if err != nil {
		return fmt.Errorf("read embedded migration %q: %w", name, err)
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin migration %d: %w", version, err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, string(content)); err != nil {
		return fmt.Errorf("apply migration %d: %w", version, err)
	}
	if _, err := tx.ExecContext(
		ctx,
		"INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
		version,
		time.Now().UTC().Format(time.RFC3339Nano),
	); err != nil {
		return fmt.Errorf("record migration %d: %w", version, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit migration %d: %w", version, err)
	}
	return nil
}

func (s *Store) SchemaVersion(ctx context.Context) (int, error) {
	var version int
	err := s.db.QueryRowContext(
		ctx, "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
	).Scan(&version)
	return version, err
}
