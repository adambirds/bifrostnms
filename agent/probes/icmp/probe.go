package icmp

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"os"
	"syscall"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type Transport interface {
	Exchange(
		ctx context.Context,
		target string,
		family AddressFamily,
		packetCount int,
		packetInterval time.Duration,
		packetTimeout time.Duration,
		payloadSize int,
	) ([]float64, error)
}

type Probe struct {
	transport Transport
	now       func() time.Time
}

func New(transport Transport) *Probe {
	if transport == nil {
		transport = NativeTransport{}
	}
	return &Probe{transport: transport, now: time.Now}
}

func (*Probe) Type() probe.Type                   { return probe.TypeICMP }
func (*Probe) ConfigurationSchemaVersion() uint32 { return ConfigurationSchemaVersion }
func (*Probe) ResultSchemaVersion() uint32        { return ResultSchemaVersion }
func (*Probe) Validate(raw json.RawMessage) error { _, err := DecodeConfiguration(raw); return err }

func (p *Probe) Run(ctx context.Context, request probe.Request) probe.Result {
	startedAt := p.now().UTC()
	configuration, err := DecodeConfiguration(request.Configuration)
	if err != nil {
		return failedResult(startedAt, p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_icmp_configuration", "ICMP configuration is invalid.")
	}
	packetTimeout, err := configuration.Timeout(request.Timeout)
	if err != nil {
		return failedResult(startedAt, p.now().UTC(), probe.ErrorInvalidConfiguration,
			"icmp_sequence_exceeds_timeout", "ICMP packet sequence exceeds the monitor timeout.")
	}
	samples, err := p.transport.Exchange(
		ctx, request.TargetAddress, configuration.AddressFamily,
		configuration.PacketCount, time.Duration(configuration.PacketIntervalMS)*time.Millisecond,
		packetTimeout, configuration.PayloadSizeBytes,
	)
	finishedAt := p.now().UTC()
	if err != nil {
		return classifyTransportError(ctx, startedAt, finishedAt, err)
	}
	result, err := CalculateResult(configuration.PacketCount, samples)
	if err != nil {
		return failedResult(startedAt, finishedAt, probe.ErrorInternal,
			"invalid_icmp_samples", "ICMP transport returned invalid samples.")
	}
	assessment := probe.AssessmentUnhealthy
	if Assess(configuration, result) {
		assessment = probe.AssessmentHealthy
	}
	return probe.Result{
		StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionCompleted, Assessment: assessment,
		ProbeResult: result,
	}
}

func classifyTransportError(
	ctx context.Context, startedAt time.Time, finishedAt time.Time, err error,
) probe.Result {
	if errors.Is(ctx.Err(), context.Canceled) {
		return failedResult(startedAt, finishedAt, probe.ErrorInternal,
			"probe_cancelled", "ICMP probe was cancelled.")
	}
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return failedResult(startedAt, finishedAt, probe.ErrorTimeout,
			"icmp_timeout", "ICMP probe timed out.")
	}
	if errors.Is(err, os.ErrPermission) || errors.Is(err, syscall.EPERM) ||
		errors.Is(err, syscall.EACCES) {
		return failedResult(startedAt, finishedAt, probe.ErrorPermission,
			"icmp_permission_denied", "ICMP raw socket permission is unavailable.")
	}
	var dnsError *net.DNSError
	if errors.As(err, &dnsError) {
		return failedResult(startedAt, finishedAt, probe.ErrorResolution,
			"icmp_resolution_failed", "ICMP target resolution failed.")
	}
	return failedResult(startedAt, finishedAt, probe.ErrorConnection,
		"icmp_network_error", "ICMP exchange failed.")
}

func failedResult(
	startedAt time.Time, finishedAt time.Time, category probe.ErrorCategory,
	code string, message string,
) probe.Result {
	return probe.Result{
		StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionFailed, Assessment: probe.AssessmentUnknown,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message,
	}
}
