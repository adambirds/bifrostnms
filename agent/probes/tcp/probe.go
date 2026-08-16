package tcp

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"strconv"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type Dialer interface {
	DialContext(ctx context.Context, network string, address string) (net.Conn, error)
}

type Result struct {
	Port        int      `json:"port"`
	AddressUsed *string  `json:"address_used"`
	ConnectMS   *float64 `json:"connect_ms"`
}

type Probe struct {
	dialer Dialer
	now    func() time.Time
}

func New(dialer Dialer) *Probe {
	if dialer == nil {
		dialer = &net.Dialer{}
	}
	return &Probe{dialer: dialer, now: time.Now}
}

func (*Probe) Type() probe.Type                   { return probe.TypeTCP }
func (*Probe) ConfigurationSchemaVersion() uint32 { return ConfigurationSchemaVersion }
func (*Probe) ResultSchemaVersion() uint32        { return ResultSchemaVersion }
func (*Probe) Validate(raw json.RawMessage) error { _, err := DecodeConfiguration(raw); return err }

func (p *Probe) Run(ctx context.Context, request probe.Request) probe.Result {
	startedAt := p.now().UTC()
	configuration, err := DecodeConfiguration(request.Configuration)
	if err != nil {
		return failed(startedAt, p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_tcp_configuration", "TCP configuration is invalid.")
	}
	network := "tcp"
	if configuration.AddressFamily == AddressFamilyIPv4 {
		network = "tcp4"
	} else if configuration.AddressFamily == AddressFamilyIPv6 {
		network = "tcp6"
	}
	connection, err := p.dialer.DialContext(
		ctx, network, net.JoinHostPort(request.TargetAddress, strconv.Itoa(configuration.Port)),
	)
	finishedAt := p.now().UTC()
	if err != nil {
		category, code, message := classifyError(ctx, err)
		return completedUnhealthy(startedAt, finishedAt, configuration.Port, category, code, message)
	}
	addressUsed := remoteHost(connection.RemoteAddr())
	_ = connection.Close()
	connectMS := float64(finishedAt.Sub(startedAt)) / float64(time.Millisecond)
	return probe.Result{
		StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionCompleted, Assessment: probe.AssessmentHealthy,
		ProbeResult: Result{
			Port: configuration.Port, AddressUsed: &addressUsed, ConnectMS: &connectMS,
		},
	}
}

func classifyError(
	ctx context.Context, err error,
) (probe.ErrorCategory, string, string) {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return probe.ErrorTimeout, "tcp_connect_timeout", "TCP connection timed out."
	}
	var operationError *net.OpError
	if errors.As(err, &operationError) {
		if operationError.Op == "dial" {
			return probe.ErrorConnection, "tcp_connection_failed", "TCP connection failed."
		}
	}
	return probe.ErrorConnection, "tcp_connection_failed", "TCP connection failed."
}

func completedUnhealthy(
	startedAt time.Time, finishedAt time.Time, port int,
	category probe.ErrorCategory, code string, message string,
) probe.Result {
	return probe.Result{
		StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionCompleted, Assessment: probe.AssessmentUnhealthy,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message,
		ProbeResult: Result{Port: port, AddressUsed: nil, ConnectMS: nil},
	}
}

func failed(
	startedAt time.Time, finishedAt time.Time, category probe.ErrorCategory,
	code string, message string,
) probe.Result {
	return probe.Result{
		StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionFailed, Assessment: probe.AssessmentUnknown,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message,
	}
}

func remoteHost(address net.Addr) string {
	if address == nil {
		return "unknown"
	}
	host, _, err := net.SplitHostPort(address.String())
	if err == nil && host != "" {
		return host
	}
	return address.String()
}
