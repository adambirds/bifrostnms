package http

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"io"
	"net"
	nethttp "net/http"
	"net/http/httptrace"
	"net/url"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type Result struct {
	Method            string   `json:"method"`
	Scheme            string   `json:"scheme"`
	StatusCode        *int     `json:"status_code"`
	RedirectCount     int      `json:"redirect_count"`
	ResponseSizeBytes *int64   `json:"response_size_bytes"`
	DNSMS             *float64 `json:"dns_ms"`
	ConnectMS         *float64 `json:"connect_ms"`
	TLSMS             *float64 `json:"tls_ms"`
	TTFBMS            *float64 `json:"ttfb_ms"`
	TotalMS           *float64 `json:"total_ms"`
	AssertionsTotal   int      `json:"assertions_total"`
	AssertionsFailed  int      `json:"assertions_failed"`
	FinalURLRedacted  *string  `json:"final_url_redacted"`
}

type Probe struct {
	rootCAs *x509.CertPool
	now     func() time.Time
}

type timings struct {
	dnsStarted     time.Time
	connectStarted time.Time
	tlsStarted     time.Time
	firstByteAt    time.Time
	dns            time.Duration
	connect        time.Duration
	tls            time.Duration
}

type errorClassification struct {
	category probe.ErrorCategory
	code     string
	message  string
	failed   bool
}

func New(rootCAs *x509.CertPool) *Probe {
	return &Probe{rootCAs: rootCAs, now: time.Now}
}

func (*Probe) Type() probe.Type                   { return probe.TypeHTTP }
func (*Probe) ConfigurationSchemaVersion() uint32 { return ConfigurationSchemaVersion }
func (*Probe) ResultSchemaVersion() uint32        { return ResultSchemaVersion }
func (*Probe) Validate(raw json.RawMessage) error { _, err := DecodeConfiguration(raw); return err }

func (p *Probe) Run(ctx context.Context, request probe.Request) probe.Result {
	startedAt := p.now()
	configuration, err := DecodeConfiguration(request.Configuration)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_http_configuration", "HTTP configuration is invalid.")
	}

	requestURL, err := buildURL(request.TargetAddress, configuration)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_http_target", "HTTP target could not be represented safely.")
	}

	traceTimings := &timings{}
	trace := &httptrace.ClientTrace{
		DNSStart: func(httptrace.DNSStartInfo) { traceTimings.dnsStarted = p.now() },
		DNSDone: func(httptrace.DNSDoneInfo) {
			if !traceTimings.dnsStarted.IsZero() {
				traceTimings.dns += p.now().Sub(traceTimings.dnsStarted)
			}
		},
		ConnectStart: func(_, _ string) { traceTimings.connectStarted = p.now() },
		ConnectDone: func(_, _ string, _ error) {
			if !traceTimings.connectStarted.IsZero() {
				traceTimings.connect += p.now().Sub(traceTimings.connectStarted)
			}
		},
		TLSHandshakeStart: func() { traceTimings.tlsStarted = p.now() },
		TLSHandshakeDone: func(tls.ConnectionState, error) {
			if !traceTimings.tlsStarted.IsZero() {
				traceTimings.tls += p.now().Sub(traceTimings.tlsStarted)
			}
		},
		GotFirstResponseByte: func() { traceTimings.firstByteAt = p.now() },
	}

	httpRequest, err := nethttp.NewRequestWithContext(
		httptrace.WithClientTrace(ctx, trace), configuration.Method, requestURL.String(), nil,
	)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"http_request_creation_failed", "HTTP request could not be created safely.")
	}
	if configuration.HostHeader != nil {
		httpRequest.Host = *configuration.HostHeader
	}
	for name, value := range configuration.RequestHeaders {
		httpRequest.Header.Set(name, value)
	}

	redirectCount := 0
	client := &nethttp.Client{
		Transport: p.transport(configuration),
		CheckRedirect: func(_ *nethttp.Request, via []*nethttp.Request) error {
			redirectCount = len(via)
			if !configuration.FollowRedirects {
				return nethttp.ErrUseLastResponse
			}
			if len(via) > configuration.MaximumRedirects {
				return errors.New("maximum redirects exceeded")
			}
			return nil
		},
	}

	response, err := client.Do(httpRequest)
	finishedAt := p.now()
	if err != nil {
		classification := classifyError(ctx, err)
		if classification.failed {
			return failed(startedAt.UTC(), finishedAt.UTC(), classification.category,
				classification.code, classification.message)
		}
		result := baseResult(configuration, startedAt, finishedAt, traceTimings, redirectCount)
		return completedUnhealthy(startedAt.UTC(), finishedAt.UTC(), result, classification.category,
			classification.code, classification.message)
	}
	defer func() { _ = response.Body.Close() }()

	body, exceeded, readErr := readBounded(response.Body, configuration.MaximumResponseBytes)
	if readErr != nil {
		classification := classifyError(ctx, readErr)
		if classification.failed {
			return failed(startedAt.UTC(), p.now().UTC(), classification.category,
				classification.code, classification.message)
		}
		result := baseResult(configuration, startedAt, p.now(), traceTimings, redirectCount)
		status := response.StatusCode
		result.StatusCode = &status
		return completedUnhealthy(startedAt.UTC(), p.now().UTC(), result, classification.category,
			classification.code, classification.message)
	}
	finishedAt = p.now()
	result := baseResult(configuration, startedAt, finishedAt, traceTimings, redirectCount)
	status := response.StatusCode
	result.StatusCode = &status
	responseSize := response.ContentLength
	if responseSize < 0 {
		responseSize = int64(len(body))
		if exceeded {
			responseSize = int64(configuration.MaximumResponseBytes + 1)
		}
	}
	result.ResponseSizeBytes = &responseSize
	redacted := redactURL(response.Request.URL)
	result.FinalURLRedacted = &redacted

	assertionsTotal, assertionsFailed := evaluateAssertions(configuration, response, body)
	result.AssertionsTotal = assertionsTotal
	result.AssertionsFailed = assertionsFailed
	if exceeded {
		return completedUnhealthy(startedAt.UTC(), finishedAt.UTC(), result, probe.ErrorProtocol,
			"http_response_limit_exceeded", "HTTP response exceeded the configured read limit.")
	}
	if assertionsFailed > 0 {
		return completedUnhealthy(startedAt.UTC(), finishedAt.UTC(), result, probe.ErrorAssertion,
			"http_assertion_failed", "One or more HTTP assertions failed.")
	}
	return probe.Result{
		StartedAt:       startedAt.UTC(),
		FinishedAt:      finishedAt.UTC(),
		ExecutionStatus: probe.ExecutionCompleted,
		Assessment:      probe.AssessmentHealthy,
		ProbeResult:     result,
	}
}

func (p *Probe) transport(configuration Configuration) *nethttp.Transport {
	transport := nethttp.DefaultTransport.(*nethttp.Transport).Clone()
	network := "tcp"
	switch configuration.AddressFamily {
	case AddressFamilyIPv4:
		network = "tcp4"
	case AddressFamilyIPv6:
		network = "tcp6"
	}
	dialer := &net.Dialer{}
	transport.DialContext = func(ctx context.Context, _ string, address string) (net.Conn, error) {
		return dialer.DialContext(ctx, network, address)
	}
	transport.Proxy = nil
	transport.DisableCompression = true
	transport.TLSClientConfig = &tls.Config{RootCAs: p.rootCAs, MinVersion: tls.VersionTLS12}
	if configuration.HostHeader != nil && configuration.Scheme == "https" {
		transport.TLSClientConfig.ServerName = *configuration.HostHeader
	}
	return transport
}

func buildURL(target string, configuration Configuration) (*url.URL, error) {
	path, err := url.ParseRequestURI(configuration.Path)
	if err != nil || path.IsAbs() || path.Host != "" || path.User != nil {
		return nil, errors.New("invalid request path")
	}
	host := target
	if configuration.Port != nil {
		host = net.JoinHostPort(target, strconv.Itoa(*configuration.Port))
	} else if parsed := net.ParseIP(target); parsed != nil && strings.Contains(target, ":") {
		host = "[" + target + "]"
	}
	return &url.URL{Scheme: configuration.Scheme, Host: host, Path: path.Path,
		RawPath: path.RawPath, RawQuery: path.RawQuery}, nil
}

func readBounded(reader io.Reader, maximum int) ([]byte, bool, error) {
	var buffer bytes.Buffer
	_, err := io.Copy(&buffer, io.LimitReader(reader, int64(maximum)+1))
	if err != nil {
		return nil, false, err
	}
	content := buffer.Bytes()
	if len(content) > maximum {
		return content[:maximum], true, nil
	}
	return content, false, nil
}

func evaluateAssertions(configuration Configuration, response *nethttp.Response, body []byte) (int, int) {
	total := 1 + len(configuration.ExpectedHeaderValues) + len(configuration.ExpectedBodyContains)
	failedCount := 0
	if !containsStatus(configuration.ExpectedStatusCodes, response.StatusCode) {
		failedCount++
	}
	for _, assertion := range configuration.ExpectedHeaderValues {
		matched := false
		for _, value := range response.Header.Values(assertion.Name) {
			if value == assertion.Value {
				matched = true
				break
			}
		}
		if !matched {
			failedCount++
		}
	}
	for _, expected := range configuration.ExpectedBodyContains {
		if !bytes.Contains(body, []byte(expected)) {
			failedCount++
		}
	}
	return total, failedCount
}

func containsStatus(expected []int, actual int) bool {
	for _, status := range expected {
		if status == actual {
			return true
		}
	}
	return false
}

func baseResult(
	configuration Configuration, startedAt, finishedAt time.Time, measured *timings, redirectCount int,
) Result {
	result := Result{Method: configuration.Method, Scheme: configuration.Scheme,
		RedirectCount: redirectCount}
	result.DNSMS = durationPointer(measured.dns)
	result.ConnectMS = durationPointer(measured.connect)
	result.TLSMS = durationPointer(measured.tls)
	if !measured.firstByteAt.IsZero() {
		value := float64(measured.firstByteAt.Sub(startedAt)) / float64(time.Millisecond)
		result.TTFBMS = &value
	}
	total := float64(finishedAt.Sub(startedAt)) / float64(time.Millisecond)
	result.TotalMS = &total
	return result
}

func durationPointer(duration time.Duration) *float64 {
	if duration <= 0 {
		return nil
	}
	value := float64(duration) / float64(time.Millisecond)
	return &value
}

func redactURL(value *url.URL) string {
	if value == nil {
		return ""
	}
	redacted := *value
	redacted.User = nil
	if redacted.RawQuery != "" {
		query := redacted.Query()
		for key := range query {
			query.Set(key, "REDACTED")
		}
		redacted.RawQuery = query.Encode()
	}
	return redacted.String()
}

func classifyError(ctx context.Context, err error) errorClassification {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return errorClassification{category: probe.ErrorTimeout, code: "http_timeout",
			message: "HTTP request timed out."}
	}
	if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
		return errorClassification{category: probe.ErrorInternal, code: "http_cancelled",
			message: "HTTP request was cancelled locally.", failed: true}
	}
	if isLocalResourceError(err) {
		return errorClassification{category: probe.ErrorResourceLimit, code: "http_local_resource_exhausted",
			message: "HTTP request could not start because local resources are exhausted.", failed: true}
	}
	var verificationError *tls.CertificateVerificationError
	if errors.As(err, &verificationError) {
		var hostnameError x509.HostnameError
		if errors.As(verificationError.Err, &hostnameError) {
			return errorClassification{category: probe.ErrorTLS, code: "http_tls_hostname_mismatch",
				message: "HTTPS certificate does not match the requested hostname."}
		}
		var unknownAuthority x509.UnknownAuthorityError
		if errors.As(verificationError.Err, &unknownAuthority) {
			return errorClassification{category: probe.ErrorTLS, code: "http_tls_untrusted",
				message: "HTTPS certificate chain is not trusted."}
		}
		return errorClassification{category: probe.ErrorTLS, code: "http_tls_verification_failed",
			message: "HTTPS certificate verification failed."}
	}
	var dnsError *net.DNSError
	if errors.As(err, &dnsError) {
		return errorClassification{category: probe.ErrorResolution, code: "http_resolution_failed",
			message: "HTTP target resolution failed."}
	}
	if errors.Is(err, syscall.ECONNREFUSED) {
		return errorClassification{category: probe.ErrorConnection, code: "http_connection_refused",
			message: "HTTP connection was refused."}
	}
	if errors.Is(err, syscall.ENETUNREACH) || errors.Is(err, syscall.EHOSTUNREACH) {
		return errorClassification{category: probe.ErrorConnection, code: "http_target_unreachable",
			message: "HTTP target is unreachable."}
	}
	if strings.Contains(err.Error(), "maximum redirects exceeded") {
		return errorClassification{category: probe.ErrorProtocol, code: "http_redirect_limit_exceeded",
			message: "HTTP redirect limit was exceeded."}
	}
	return errorClassification{category: probe.ErrorConnection, code: "http_request_failed",
		message: "HTTP request failed."}
}

func isLocalResourceError(err error) bool {
	return errors.Is(err, syscall.EMFILE) || errors.Is(err, syscall.ENFILE) ||
		errors.Is(err, syscall.ENOBUFS) || errors.Is(err, syscall.ENOMEM)
}

func completedUnhealthy(
	startedAt, finishedAt time.Time, result Result, category probe.ErrorCategory, code, message string,
) probe.Result {
	return probe.Result{StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionCompleted, Assessment: probe.AssessmentUnhealthy,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message, ProbeResult: result}
}

func failed(
	startedAt, finishedAt time.Time, category probe.ErrorCategory, code, message string,
) probe.Result {
	return probe.Result{StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionFailed, Assessment: probe.AssessmentUnknown,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message}
}
