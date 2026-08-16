package tcp

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"strconv"
	"syscall"
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

type errorClassification struct {
	category probe.ErrorCategory
	code     string
	message  string
	failed   bool
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
	startedAt := p.now()
	configuration, err := DecodeConfiguration(request.Configuration)
	if err != nil {
		return failed(
			startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_tcp_configuration", "TCP configuration is invalid.",
		)
	}

	network := networkForAddressFamily(configuration.AddressFamily)
	address := net.JoinHostPort(request.TargetAddress, strconv.Itoa(configuration.Port))
	dialStartedAt := p.now()
	connection, err := p.dialer.DialContext(ctx, network, address)
	finishedAt := p.now()
	if err != nil {
		classification := classifyError(ctx, err)
		if classification.failed {
			return failed(
				startedAt.UTC(), finishedAt.UTC(), classification.category,
				classification.code, classification.message,
			)
		}
		return completedUnhealthy(
			startedAt.UTC(), finishedAt.UTC(), configuration.Port,
			classification.category, classification.code, classification.message,
		)
	}

	addressUsed := remoteHost(connection.RemoteAddr())
	_ = connection.Close()
	connectMS := float64(finishedAt.Sub(dialStartedAt)) / float64(time.Millisecond)
	return probe.Result{
		StartedAt:       startedAt.UTC(),
		FinishedAt:      finishedAt.UTC(),
		ExecutionStatus: probe.ExecutionCompleted,
		Assessment:      probe.AssessmentHealthy,
		ProbeResult: Result{
			Port: configuration.Port, AddressUsed: &addressUsed, ConnectMS: &connectMS,
		},
	}
}

func networkForAddressFamily(addressFamily AddressFamily) string {
	switch addressFamily {
	case AddressFamilyIPv4:
		return "tcp4"
	case AddressFamilyIPv6:
		return "tcp6"
	default:
		return "tcp"
	}
}

func classifyError(ctx context.Context, err error) errorClassification {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return errorClassification{
			category: probe.ErrorTimeout,
			code:     "tcp_connect_timeout",
			message:  "TCP connection timed out.",
		}
	}
	if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
		return errorClassification{
			category: probe.ErrorInternal,
			code:     "tcp_cancelled",
			message:  "TCP connection was cancelled locally.",
			failed:   true,
		}
	}
	if isLocalResourceError(err) {
		return errorClassification{
			category: probe.ErrorResourceLimit,
			code:     "tcp_local_resource_exhausted",
			message:  "TCP connection could not start because local resources are exhausted.",
			failed:   true,
		}
	}
	var dnsError *net.DNSError
	if errors.As(err, &dnsError) {
		return errorClassification{
			category: probe.ErrorResolution,
			code:     "tcp_resolution_failed",
			message:  "TCP target resolution failed.",
		}
	}
	if errors.Is(err, syscall.ECONNREFUSED) {
		return errorClassification{
			category: probe.ErrorConnection,
			code:     "tcp_connection_refused",
			message:  "TCP connection was refused.",
		}
	}
	if errors.Is(err, syscall.ENETUNREACH) {
		return errorClassification{
			category: probe.ErrorConnection,
			code:     "tcp_network_unreachable",
			message:  "TCP target network is unreachable.",
		}
	}
	if errors.Is(err, syscall.EHOSTUNREACH) {
		return errorClassification{
			category: probe.ErrorConnection,
			code:     "tcp_host_unreachable",
			message:  "TCP target host is unreachable.",
		}
	}
	return errorClassification{
		category: probe.ErrorConnection,
		code:     "tcp_connection_failed",
		message:  "TCP connection failed.",
	}
}

func isLocalResourceError(err error) bool {
	return errors.Is(err, syscall.EMFILE) ||
		errors.Is(err, syscall.ENFILE) ||
		errors.Is(err, syscall.ENOBUFS) ||
		errors.Is(err, syscall.ENOMEM)
}

func completedUnhealthy(
	startedAt time.Time, finishedAt time.Time, port int,
	category probe.ErrorCategory, code string, message string,
) probe.Result {
	return probe.Result{
		StartedAt:       startedAt,
		FinishedAt:      finishedAt,
		ExecutionStatus: probe.ExecutionCompleted,
		Assessment:      probe.AssessmentUnhealthy,
		ErrorCategory:   &category,
		ErrorCode:       code,
		ErrorMessage:    message,
		ProbeResult:     Result{Port: port, AddressUsed: nil, ConnectMS: nil},
	}
}

func failed(
	startedAt time.Time, finishedAt time.Time, category probe.ErrorCategory,
	code string, message string,
) probe.Result {
	return probe.Result{
		StartedAt:       startedAt,
		FinishedAt:      finishedAt,
		ExecutionStatus: probe.ExecutionFailed,
		Assessment:      probe.AssessmentUnknown,
		ErrorCategory:   &category,
		ErrorCode:       code,
		ErrorMessage:    message,
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
