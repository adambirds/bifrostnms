package icmp

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type fakeTransport struct {
	samples []float64
	err     error
	request transportRequest
}

type transportRequest struct {
	target        string
	family        AddressFamily
	packetCount   int
	packetTimeout time.Duration
}

func (f *fakeTransport) Exchange(
	_ context.Context, target string, family AddressFamily, packetCount int,
	_ time.Duration, packetTimeout time.Duration, _ int,
) ([]float64, error) {
	f.request = transportRequest{
		target: target, family: family, packetCount: packetCount, packetTimeout: packetTimeout,
	}
	return f.samples, f.err
}

func probeRequest() probe.Request {
	return probe.Request{
		TargetAddress: "example.test", Timeout: 2 * time.Second,
		Configuration: json.RawMessage(`{
			"schema_version":1,
			"packet_count":3,
			"packet_interval_ms":50,
			"per_packet_timeout_ms":500,
			"payload_size_bytes":56,
			"address_family":"ipv4"
		}`),
	}
}

func TestProbeRunsNativeTransportAndAssessesReplies(t *testing.T) {
	transport := &fakeTransport{samples: []float64{10, 12, 14}}
	implementation := New(transport)
	result := implementation.Run(context.Background(), probeRequest())
	if err := result.Validate(); err != nil {
		t.Fatalf("validate probe result: %v", err)
	}
	if result.ExecutionStatus != probe.ExecutionCompleted ||
		result.Assessment != probe.AssessmentHealthy {
		t.Fatalf("probe result = %#v", result)
	}
	if transport.request.target != "example.test" ||
		transport.request.family != AddressFamilyIPv4 || transport.request.packetCount != 3 ||
		transport.request.packetTimeout != 500*time.Millisecond {
		t.Fatalf("transport request = %#v", transport.request)
	}
}

func TestProbeTreatsCompleteLossAsCompletedUnhealthy(t *testing.T) {
	result := New(&fakeTransport{}).Run(context.Background(), probeRequest())
	if result.ExecutionStatus != probe.ExecutionCompleted ||
		result.Assessment != probe.AssessmentUnhealthy || result.ProbeResult == nil {
		t.Fatalf("complete-loss result = %#v", result)
	}
}

func TestProbeClassifiesPermissionAsFailedUnknown(t *testing.T) {
	result := New(&fakeTransport{err: os.ErrPermission}).Run(
		context.Background(), probeRequest(),
	)
	if result.ExecutionStatus != probe.ExecutionFailed ||
		result.Assessment != probe.AssessmentUnknown || result.ErrorCategory == nil ||
		*result.ErrorCategory != probe.ErrorPermission || result.ErrorCode != "icmp_permission_denied" {
		t.Fatalf("permission result = %#v", result)
	}
	if err := result.Validate(); err != nil {
		t.Fatalf("validate permission result: %v", err)
	}
}

func TestProbeRejectsInvalidRuntimeConfigurationBeforeTransport(t *testing.T) {
	transport := &fakeTransport{}
	request := probeRequest()
	request.Configuration = json.RawMessage(`{"schema_version":1,"packet_count":0}`)
	result := New(transport).Run(context.Background(), request)
	if result.ExecutionStatus != probe.ExecutionFailed ||
		result.ErrorCode != "invalid_icmp_configuration" || transport.request.target != "" {
		t.Fatalf("invalid configuration result = %#v", result)
	}
}

func TestProbeClassifiesCancellationWithoutLeakingRawError(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result := New(&fakeTransport{err: errors.New("secret raw error")}).Run(ctx, probeRequest())
	if result.ErrorCode != "probe_cancelled" ||
		result.ErrorMessage != "ICMP probe was cancelled." {
		t.Fatalf("cancellation result = %#v", result)
	}
}

func TestNativeTransportResolvesRequestedAddressFamily(t *testing.T) {
	transport := NativeTransport{}
	ipv4Target, err := transport.resolve(context.Background(), "192.0.2.1", AddressFamilyIPv4)
	if err != nil || ipv4Target.Network != "ip4:icmp" {
		t.Fatalf("IPv4 target = %#v, error = %v", ipv4Target, err)
	}
	ipv6Target, err := transport.resolve(context.Background(), "2001:db8::1", AddressFamilyIPv6)
	if err != nil || ipv6Target.Network != "ip6:ipv6-icmp" {
		t.Fatalf("IPv6 target = %#v, error = %v", ipv6Target, err)
	}
	if _, err := transport.resolve(
		context.Background(), "192.0.2.1", AddressFamilyIPv6,
	); err == nil {
		t.Fatal("IPv4 target was accepted for IPv6-only configuration")
	}
}
