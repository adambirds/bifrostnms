package engine

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	icmpprobe "github.com/adambirds/bifrostnms/agent/probes/icmp"
	"github.com/adambirds/bifrostnms/agent/storage"
)

type syntheticICMPTransport struct{ samples []float64 }

func (t syntheticICMPTransport) Exchange(
	context.Context, string, icmpprobe.AddressFamily, int,
	time.Duration, time.Duration, int,
) ([]float64, error) {
	return t.samples, nil
}

func TestLoadActiveConfigurationAllowsNoConfiguration(t *testing.T) {
	ctx := context.Background()
	store, err := storage.Open(ctx, filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	registry, err := probe.NewRegistry(
		icmpprobe.New(syntheticICMPTransport{samples: []float64{8, 10, 12}}),
	)
	if err != nil {
		t.Fatalf("create probe registry: %v", err)
	}
	engine, err := New(store, registry, 1, storage.DefaultQueueLimits())
	if err != nil {
		t.Fatalf("create engine: %v", err)
	}
	if err := engine.LoadActiveConfiguration(ctx, time.Now().UTC()); err != nil {
		t.Fatalf("load empty active configuration: %v", err)
	}
	if len(engine.NextDue()) != 0 {
		t.Fatalf("empty configuration scheduled monitors = %#v", engine.NextDue())
	}
}

func TestICMPExecutionFlowsFromActiveConfigurationToDurableQueue(t *testing.T) {
	ctx := context.Background()
	store, err := storage.Open(ctx, filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	now := time.Date(2026, 8, 16, 23, 0, 0, 0, time.UTC)
	payload := []byte(`{
		"configuration_schema_version":1,
		"agent_id":"agent",
		"realm_id":"realm",
		"monitors":[{
			"monitor_id":"monitor","target_id":"target","monitor_revision":2,
			"target_address":"192.0.2.1","probe_type":"icmp","probe_schema_version":1,
			"interval_seconds":5,"timeout_seconds":2,"missed_run_policy":"skip",
			"configuration":{
				"schema_version":1,"packet_count":3,"packet_interval_ms":50,
				"per_packet_timeout_ms":500,"payload_size_bytes":56,"address_family":"ipv4"
			}
		}]
	}`)
	if err := store.ActivateConfiguration(ctx, storage.ConfigurationSnapshot{
		Revision: 7, ContentHash: "hash", SchemaVersion: 1,
		CanonicalPayload: payload, DownloadedAt: now, ValidatedAt: &now, ActivatedAt: &now,
	}); err != nil {
		t.Fatalf("activate configuration: %v", err)
	}
	registry, err := probe.NewRegistry(
		icmpprobe.New(syntheticICMPTransport{samples: []float64{8, 10, 12}}),
	)
	if err != nil {
		t.Fatalf("create probe registry: %v", err)
	}
	engine, err := New(store, registry, 1, storage.DefaultQueueLimits())
	if err != nil {
		t.Fatalf("create engine: %v", err)
	}
	if err := engine.LoadActiveConfiguration(ctx, now); err != nil {
		t.Fatalf("load active configuration: %v", err)
	}
	due := engine.NextDue()["monitor"]
	if missed, err := engine.Tick(ctx, due); err != nil || len(missed) != 0 {
		t.Fatalf("tick engine missed = %#v, error = %v", missed, err)
	}
	execution := <-engine.Results()
	engine.Wait()
	if err := engine.RecordExecution(ctx, execution, due); err != nil {
		t.Fatalf("record execution: %v", err)
	}
	queued, err := store.ReadyObservations(ctx, due, 10)
	if err != nil || len(queued) != 1 {
		t.Fatalf("queued observations = %#v, error = %v", queued, err)
	}
	if queued[0].AgentConfigRevision != 7 || queued[0].MonitorRevision != 2 ||
		queued[0].ProbeType != "icmp" {
		t.Fatalf("queued observation identity = %#v", queued[0])
	}
	var observation struct {
		Assessment string `json:"assessment"`
		Result     struct {
			RTTSamples []float64 `json:"rtt_samples_ms"`
		} `json:"result"`
	}
	if err := json.Unmarshal(queued[0].CanonicalPayload, &observation); err != nil {
		t.Fatalf("decode queued observation: %v", err)
	}
	if observation.Assessment != "healthy" || len(observation.Result.RTTSamples) != 3 {
		t.Fatalf("queued observation payload = %#v", observation)
	}
}
