package main

import (
	"context"
	"database/sql"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"runtime"
	"runtime/debug"
	"strings"
	"syscall"
	"time"

	"github.com/adambirds/bifrostnms/agent/engine"
	"github.com/adambirds/bifrostnms/agent/probe"
	dnsprobe "github.com/adambirds/bifrostnms/agent/probes/dns"
	httpprobe "github.com/adambirds/bifrostnms/agent/probes/http"
	"github.com/adambirds/bifrostnms/agent/probes/icmp"
	tcpprobe "github.com/adambirds/bifrostnms/agent/probes/tcp"
	tlsprobe "github.com/adambirds/bifrostnms/agent/probes/tls"
	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/scheduler"
	"github.com/adambirds/bifrostnms/agent/storage"
	"github.com/adambirds/bifrostnms/agent/synchronization"
)

const (
	defaultMaximumConcurrent = 32
	configurationInterval    = 30 * time.Second
	heartbeatInterval        = 30 * time.Second
	uploadInterval           = 5 * time.Second
)

func main() {
	if err := execute(); err != nil {
		slog.Error("agent stopped", "error", err)
		os.Exit(1)
	}
}

func execute() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	store, err := storage.Open(
		ctx, environment("BIFROSTNMS_AGENT_DATABASE_PATH", storage.DefaultPath),
	)
	if err != nil {
		return err
	}
	defer func() { _ = store.Close() }()
	if len(os.Args) > 1 && os.Args[1] == "enrol" {
		return enrol(ctx, store, os.Args[2:])
	}
	return run(ctx, store)
}

func enrol(ctx context.Context, store *storage.Store, arguments []string) error {
	flags := flag.NewFlagSet("enrol", flag.ContinueOnError)
	controlPlaneURL := flags.String("control-plane", "", "control plane base URL")
	token := flags.String("token", "", "single-use enrolment token")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *token == "" {
		*token = os.Getenv("BIFROSTNMS_AGENT_ENROLMENT_TOKEN")
	}
	if *controlPlaneURL == "" || *token == "" {
		return errors.New(
			"enrol requires --control-plane and an enrolment token flag or environment variable",
		)
	}
	hostname, err := os.Hostname()
	if err != nil {
		return fmt.Errorf("read hostname: %w", err)
	}
	capabilities, _, err := agentCapabilities(ctx)
	if err != nil {
		return err
	}
	response, err := (&synchronization.ControlPlane{}).Enrol(
		ctx, *controlPlaneURL, protocol.EnrolmentRequest{
			ProtocolVersion: protocol.Version, EnrolmentToken: *token,
			AgentVersion: version(), Platform: runtime.GOOS, Architecture: runtime.GOARCH,
			Hostname: hostname, Capabilities: capabilities,
		},
	)
	if err != nil {
		return err
	}
	credentialSecret, err := issuedCredentialSecret(response)
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	if err := store.SaveIdentity(ctx, storage.Identity{
		AgentID: response.AgentID, RealmID: response.RealmID,
		ControlPlaneURL: *controlPlaneURL, EnrolledAt: now,
	}); err != nil {
		return err
	}
	if err := store.SaveCredential(ctx, storage.Credential{
		CredentialID: response.CredentialID, Secret: credentialSecret,
		CreatedAt: now, ActivatedAt: &now,
	}); err != nil {
		return err
	}
	slog.Info("agent enrolled", "agent_id", response.AgentID, "realm_id", response.RealmID)
	return nil
}

func issuedCredentialSecret(response protocol.EnrolmentResponse) (string, error) {
	identifier, secret, found := strings.Cut(response.Credential, ".")
	if !found || identifier != response.CredentialID || secret == "" {
		return "", errors.New("enrolment response credential does not match credential_id")
	}
	return secret, nil
}

func run(ctx context.Context, store *storage.Store) error {
	identity, credential, err := activeIdentity(ctx, store)
	if err != nil {
		return fmt.Errorf("agent is not enrolled; run the enrol command: %w", err)
	}
	capabilities, registry, err := agentCapabilities(ctx)
	if err != nil {
		return err
	}
	controlPlane := &synchronization.ControlPlane{}
	if err := sendHeartbeat(ctx, controlPlane, store, identity, credential, capabilities); err != nil {
		slog.Warn("initial heartbeat failed; continuing offline", "error", err)
	}
	if _, err := controlPlane.SynchronizeConfiguration(
		ctx, store, registry, capabilities, time.Now().UTC(),
	); err != nil {
		slog.Warn("initial configuration synchronization failed", "error", err)
	}
	probeEngine, err := engine.New(
		store, registry, defaultMaximumConcurrent, storage.DefaultQueueLimits(),
	)
	if err != nil {
		return err
	}
	if err := probeEngine.LoadActiveConfiguration(ctx, time.Now().UTC()); err != nil {
		return fmt.Errorf("load last valid configuration: %w", err)
	}
	uploader := &synchronization.Client{Store: store}
	engineErrors := make(chan error, 1)
	go func() { engineErrors <- probeEngine.Run(ctx, time.Second, reportMissedRuns) }()
	configurationTicker := time.NewTicker(configurationInterval)
	heartbeatTicker := time.NewTicker(heartbeatInterval)
	uploadTicker := time.NewTicker(uploadInterval)
	defer configurationTicker.Stop()
	defer heartbeatTicker.Stop()
	defer uploadTicker.Stop()
	slog.Info("agent monitoring started", "agent_id", identity.AgentID)
	for {
		select {
		case <-ctx.Done():
			return <-engineErrors
		case err := <-engineErrors:
			return err
		case <-configurationTicker.C:
			updated, syncErr := controlPlane.SynchronizeConfiguration(
				ctx, store, registry, capabilities, time.Now().UTC(),
			)
			if syncErr != nil {
				slog.Warn("configuration synchronization failed", "error", syncErr)
			} else if updated {
				if loadErr := probeEngine.LoadActiveConfiguration(ctx, time.Now().UTC()); loadErr != nil {
					return loadErr
				}
			}
		case <-heartbeatTicker.C:
			if heartbeatErr := sendHeartbeat(
				ctx, controlPlane, store, identity, credential, capabilities,
			); heartbeatErr != nil {
				slog.Warn("heartbeat failed", "error", heartbeatErr)
			}
		case <-uploadTicker.C:
			if _, uploadErr := uploader.UploadOnce(ctx); uploadErr != nil &&
				!errors.Is(uploadErr, synchronization.ErrNoReadyData) &&
				!errors.Is(uploadErr, synchronization.ErrBackoffActive) {
				slog.Warn("observation upload failed", "error", uploadErr)
			}
		}
	}
}

func activeIdentity(
	ctx context.Context, store *storage.Store,
) (storage.Identity, storage.Credential, error) {
	identity, err := store.Identity(ctx)
	if err != nil {
		return storage.Identity{}, storage.Credential{}, err
	}
	credentials, err := store.Credentials(ctx)
	if err != nil {
		return storage.Identity{}, storage.Credential{}, err
	}
	if len(credentials) == 0 {
		return storage.Identity{}, storage.Credential{}, errors.New("no credential is stored")
	}
	return identity, credentials[len(credentials)-1], nil
}

func agentCapabilities(
	ctx context.Context,
) (protocol.Capabilities, *probe.Registry, error) {
	registry, err := probe.NewRegistry(
		icmp.New(nil), httpprobe.New(nil), tcpprobe.New(nil), dnsprobe.New(nil), tlsprobe.New(nil, nil),
	)
	if err != nil {
		return protocol.Capabilities{}, nil, err
	}
	detected := registry.DetectCapabilities(ctx, map[probe.Type]probe.AvailabilityDetector{
		probe.TypeICMP: icmp.NativeSocketAvailable,
		probe.TypeHTTP: func(context.Context) bool { return true },
		probe.TypeTCP:  func(context.Context) bool { return true },
		probe.TypeDNS:  func(context.Context) bool { return true },
		probe.TypeTLS:  func(context.Context) bool { return true },
	})
	probes := make(map[string]protocol.ProbeCapability, len(detected))
	for probeType, capability := range detected {
		probes[string(probeType)] = protocol.ProbeCapability{
			SchemaVersions: []int{int(capability.ConfigurationSchemaVersion)},
			Available:      capability.Available,
		}
	}
	return protocol.Capabilities{
		Probes: probes, Runtime: map[string]bool{"sqlite": true},
		ExternalTools: map[string]string{},
	}, registry, nil
}

func sendHeartbeat(
	ctx context.Context, controlPlane *synchronization.ControlPlane, store *storage.Store,
	identity storage.Identity, credential storage.Credential, capabilities protocol.Capabilities,
) error {
	activeRevision := int64(0)
	active, err := store.ActiveConfiguration(ctx)
	if err == nil {
		activeRevision = active.Revision
	} else if !errors.Is(err, sql.ErrNoRows) {
		return err
	}
	stats, err := store.QueueStats(ctx)
	if err != nil {
		return err
	}
	hostname, err := os.Hostname()
	if err != nil {
		return err
	}
	_, err = controlPlane.Heartbeat(ctx, identity, credential, protocol.HeartbeatRequest{
		ProtocolVersion: protocol.Version, AgentVersion: version(),
		Platform: runtime.GOOS, Architecture: runtime.GOARCH, Hostname: hostname,
		Capabilities: capabilities, ActiveConfigurationRevision: activeRevision,
		KnownDesiredConfigurationRevision: activeRevision,
		QueueDepth:                        stats.PendingCount, QueueBytes: stats.PendingBytes,
		OldestPendingObservationAt: stats.OldestPendingAt,
		DatabaseHealth:             "healthy", SchedulerState: "running",
		AgentTime: time.Now().UTC(), Warnings: []string{},
	})
	return err
}

func reportMissedRuns(missed []scheduler.MissedRun) {
	if len(missed) > 0 {
		slog.Warn("monitor runs skipped", "count", len(missed))
	}
}

func version() string {
	value := "dev"
	if info, ok := debug.ReadBuildInfo(); ok && info.Main.Version != "" {
		value = info.Main.Version
	}
	return value
}

func environment(name string, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
