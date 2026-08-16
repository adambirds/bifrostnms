package tls

import (
	"context"
	"crypto/sha256"
	cryptotls "crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type Dialer interface {
	DialContext(ctx context.Context, network string, address string) (net.Conn, error)
}

type Result struct {
	Port              int        `json:"port"`
	ServerName        string     `json:"server_name"`
	ProtocolVersion   *string    `json:"protocol_version"`
	CipherSuite       *string    `json:"cipher_suite"`
	HandshakeMS       *float64   `json:"handshake_ms"`
	CertificatePresent bool      `json:"certificate_present"`
	HostnameValid     *bool      `json:"hostname_valid"`
	ChainValid        *bool      `json:"chain_valid"`
	NotBefore         *time.Time `json:"not_before"`
	NotAfter          *time.Time `json:"not_after"`
	DaysRemaining     *float64   `json:"days_remaining"`
	SubjectName       *string    `json:"subject_name"`
	IssuerName        *string    `json:"issuer_name"`
	SerialNumber      *string    `json:"serial_number"`
	FingerprintSHA256 *string    `json:"fingerprint_sha256"`
}

type Probe struct {
	dialer Dialer
	roots  *x509.CertPool
	now    func() time.Time
}

type errorClassification struct {
	category probe.ErrorCategory
	code     string
	message  string
	failed   bool
}

func New(dialer Dialer, roots *x509.CertPool) *Probe {
	if dialer == nil {
		dialer = &net.Dialer{}
	}
	return &Probe{dialer: dialer, roots: roots, now: time.Now}
}

func (*Probe) Type() probe.Type                   { return probe.TypeTLS }
func (*Probe) ConfigurationSchemaVersion() uint32 { return ConfigurationSchemaVersion }
func (*Probe) ResultSchemaVersion() uint32        { return ResultSchemaVersion }
func (*Probe) Validate(raw json.RawMessage) error { _, err := DecodeConfiguration(raw); return err }

func (p *Probe) Run(ctx context.Context, request probe.Request) probe.Result {
	startedAt := p.now()
	configuration, err := DecodeConfiguration(request.Configuration)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_tls_configuration", "TLS configuration is invalid.")
	}
	serverName, err := effectiveServerName(request.TargetAddress, configuration.ServerName)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"tls_server_name_required", "TLS server name is required for this target.")
	}

	network := networkForAddressFamily(configuration.AddressFamily)
	address := net.JoinHostPort(request.TargetAddress, strconv.Itoa(configuration.Port))
	connection, err := p.dialer.DialContext(ctx, network, address)
	if err != nil {
		finishedAt := p.now().UTC()
		classification := classifyConnectionError(ctx, err)
		if classification.failed {
			return failed(startedAt.UTC(), finishedAt, classification.category,
				classification.code, classification.message)
		}
		result := emptyResult(configuration.Port, serverName)
		return completedUnhealthy(startedAt.UTC(), finishedAt, result, classification.category,
			classification.code, classification.message)
	}
	defer func() { _ = connection.Close() }()

	tlsConnection := cryptotls.Client(connection, &cryptotls.Config{
		ServerName: serverName,
		RootCAs:    p.roots,
		MinVersion: minimumVersion(configuration.MinimumTLSVersion),
	})
	handshakeStarted := p.now()
	err = tlsConnection.HandshakeContext(ctx)
	finishedAt := p.now()
	handshakeMS := milliseconds(finishedAt.Sub(handshakeStarted))
	if err != nil {
		if verificationResult, ok := p.verificationFailureResult(
			err, configuration.Port, serverName, handshakeMS, finishedAt,
		); ok {
			return probe.Result{
				StartedAt:       startedAt.UTC(),
				FinishedAt:      finishedAt.UTC(),
				ExecutionStatus: probe.ExecutionCompleted,
				Assessment:      probe.AssessmentUnhealthy,
				ErrorCategory:   &verificationResult.category,
				ErrorCode:       verificationResult.code,
				ErrorMessage:    verificationResult.message,
				ProbeResult:     verificationResult.result,
			}
		}
		classification := classifyHandshakeError(ctx, err)
		if classification.failed {
			return failed(startedAt.UTC(), finishedAt.UTC(), classification.category,
				classification.code, classification.message)
		}
		result := emptyResult(configuration.Port, serverName)
		result.HandshakeMS = &handshakeMS
		return completedUnhealthy(startedAt.UTC(), finishedAt.UTC(), result, classification.category,
			classification.code, classification.message)
	}

	state := tlsConnection.ConnectionState()
	result := resultFromConnectionState(configuration.Port, serverName, handshakeMS, state, finishedAt)
	if result.DaysRemaining != nil && *result.DaysRemaining <= float64(configuration.ExpiryWarningDays) {
		category := probe.ErrorTLS
		return probe.Result{
			StartedAt:       startedAt.UTC(),
			FinishedAt:      finishedAt.UTC(),
			ExecutionStatus: probe.ExecutionCompleted,
			Assessment:      probe.AssessmentUnhealthy,
			ErrorCategory:   &category,
			ErrorCode:       "tls_certificate_expiring",
			ErrorMessage:    "TLS certificate is within the configured expiry warning window.",
			ProbeResult:     result,
		}
	}
	return probe.Result{
		StartedAt:       startedAt.UTC(),
		FinishedAt:      finishedAt.UTC(),
		ExecutionStatus: probe.ExecutionCompleted,
		Assessment:      probe.AssessmentHealthy,
		ProbeResult:     result,
	}
}

type verificationFailure struct {
	result   Result
	category probe.ErrorCategory
	code     string
	message  string
}

func (p *Probe) verificationFailureResult(
	err error, port int, serverName string, handshakeMS float64, now time.Time,
) (verificationFailure, bool) {
	var verificationError *cryptotls.CertificateVerificationError
	if !errors.As(err, &verificationError) {
		return verificationFailure{}, false
	}
	result := emptyResult(port, serverName)
	result.HandshakeMS = &handshakeMS
	if len(verificationError.UnverifiedCertificates) > 0 {
		leaf := verificationError.UnverifiedCertificates[0]
		populateCertificateMetadata(&result, leaf, now)
		hostnameValid := leaf.VerifyHostname(serverName) == nil
		result.HostnameValid = &hostnameValid
	}
	chainValid := false
	result.ChainValid = &chainValid

	var hostnameError x509.HostnameError
	if errors.As(verificationError.Err, &hostnameError) {
		return verificationFailure{result: result, category: probe.ErrorTLS,
			code: "tls_hostname_mismatch", message: "TLS certificate does not match the configured server name."}, true
	}
	var authorityError x509.UnknownAuthorityError
	if errors.As(verificationError.Err, &authorityError) {
		return verificationFailure{result: result, category: probe.ErrorTLS,
			code: "tls_certificate_untrusted", message: "TLS certificate chain is not trusted."}, true
	}
	var invalidError x509.CertificateInvalidError
	if errors.As(verificationError.Err, &invalidError) {
		if result.NotAfter != nil && now.After(*result.NotAfter) {
			return verificationFailure{result: result, category: probe.ErrorTLS,
				code: "tls_certificate_expired", message: "TLS certificate has expired."}, true
		}
		if result.NotBefore != nil && now.Before(*result.NotBefore) {
			return verificationFailure{result: result, category: probe.ErrorTLS,
				code: "tls_certificate_not_yet_valid", message: "TLS certificate is not yet valid."}, true
		}
	}
	return verificationFailure{result: result, category: probe.ErrorTLS,
		code: "tls_certificate_invalid", message: "TLS certificate validation failed."}, true
}

func resultFromConnectionState(
	port int, serverName string, handshakeMS float64, state cryptotls.ConnectionState, now time.Time,
) Result {
	result := emptyResult(port, serverName)
	result.HandshakeMS = &handshakeMS
	protocolVersion := cryptotls.VersionName(state.Version)
	cipherSuite := cryptotls.CipherSuiteName(state.CipherSuite)
	result.ProtocolVersion = &protocolVersion
	result.CipherSuite = &cipherSuite
	if len(state.PeerCertificates) > 0 {
		populateCertificateMetadata(&result, state.PeerCertificates[0], now)
		hostnameValid := state.PeerCertificates[0].VerifyHostname(serverName) == nil
		result.HostnameValid = &hostnameValid
		chainValid := len(state.VerifiedChains) > 0
		result.ChainValid = &chainValid
	}
	return result
}

func populateCertificateMetadata(result *Result, certificate *x509.Certificate, now time.Time) {
	result.CertificatePresent = true
	notBefore := certificate.NotBefore.UTC()
	notAfter := certificate.NotAfter.UTC()
	result.NotBefore = &notBefore
	result.NotAfter = &notAfter
	daysRemaining := notAfter.Sub(now).Hours() / 24
	result.DaysRemaining = &daysRemaining
	subjectName := truncate(certificate.Subject.String(), 500)
	issuerName := truncate(certificate.Issuer.String(), 500)
	serialNumber := truncate(certificate.SerialNumber.Text(16), 160)
	fingerprintBytes := sha256.Sum256(certificate.Raw)
	fingerprint := hex.EncodeToString(fingerprintBytes[:])
	result.SubjectName = &subjectName
	result.IssuerName = &issuerName
	result.SerialNumber = &serialNumber
	result.FingerprintSHA256 = &fingerprint
}

func emptyResult(port int, serverName string) Result {
	return Result{Port: port, ServerName: serverName}
}

func effectiveServerName(target string, configured *string) (string, error) {
	if configured != nil {
		return *configured, nil
	}
	if net.ParseIP(strings.Trim(target, "[]")) != nil {
		return "", errors.New("server name required for IP target")
	}
	serverName := strings.ToLower(strings.TrimSuffix(strings.TrimSpace(target), "."))
	if !validHostname(serverName) {
		return "", errors.New("target does not provide a valid server name")
	}
	return serverName, nil
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

func minimumVersion(version MinimumTLSVersion) uint16 {
	if version == MinimumTLS13 {
		return cryptotls.VersionTLS13
	}
	return cryptotls.VersionTLS12
}

func classifyConnectionError(ctx context.Context, err error) errorClassification {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return errorClassification{category: probe.ErrorTimeout, code: "tls_connect_timeout",
			message: "TLS target connection timed out."}
	}
	if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
		return errorClassification{category: probe.ErrorInternal, code: "tls_cancelled",
			message: "TLS probe was cancelled locally.", failed: true}
	}
	if isLocalResourceError(err) {
		return errorClassification{category: probe.ErrorResourceLimit, code: "tls_local_resource_exhausted",
			message: "TLS probe could not start because local resources are exhausted.", failed: true}
	}
	var dnsError *net.DNSError
	if errors.As(err, &dnsError) {
		return errorClassification{category: probe.ErrorResolution, code: "tls_resolution_failed",
			message: "TLS target resolution failed."}
	}
	if errors.Is(err, syscall.ECONNREFUSED) {
		return errorClassification{category: probe.ErrorConnection, code: "tls_connection_refused",
			message: "TLS target connection was refused."}
	}
	if errors.Is(err, syscall.ENETUNREACH) {
		return errorClassification{category: probe.ErrorConnection, code: "tls_network_unreachable",
			message: "TLS target network is unreachable."}
	}
	if errors.Is(err, syscall.EHOSTUNREACH) {
		return errorClassification{category: probe.ErrorConnection, code: "tls_host_unreachable",
			message: "TLS target host is unreachable."}
	}
	return errorClassification{category: probe.ErrorConnection, code: "tls_connection_failed",
		message: "TLS target connection failed."}
}

func classifyHandshakeError(ctx context.Context, err error) errorClassification {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return errorClassification{category: probe.ErrorTimeout, code: "tls_handshake_timeout",
			message: "TLS handshake timed out."}
	}
	if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
		return errorClassification{category: probe.ErrorInternal, code: "tls_cancelled",
			message: "TLS probe was cancelled locally.", failed: true}
	}
	if isLocalResourceError(err) {
		return errorClassification{category: probe.ErrorResourceLimit, code: "tls_local_resource_exhausted",
			message: "TLS handshake failed because local resources are exhausted.", failed: true}
	}
	return errorClassification{category: probe.ErrorTLS, code: "tls_handshake_failed",
		message: "TLS handshake failed."}
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

func milliseconds(duration time.Duration) float64 {
	return float64(duration) / float64(time.Millisecond)
}

func truncate(value string, maximum int) string {
	if len(value) <= maximum {
		return value
	}
	return value[:maximum]
}
