package tls

import (
	"context"
	"crypto/x509"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

func TestProbeHealthyTLS(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	defer server.Close()
	configuration, target := configurationForServer(t, server, 0)
	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())
	result := New(nil, roots).Run(context.Background(), probe.Request{
		TargetAddress: target,
		Configuration: configuration,
	})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentHealthy {
		t.Fatalf("unexpected outcome: %#v", result)
	}
	typed := result.ProbeResult.(Result)
	if !typed.CertificatePresent || typed.HostnameValid == nil || !*typed.HostnameValid ||
		typed.ChainValid == nil || !*typed.ChainValid || typed.HandshakeMS == nil {
		t.Fatalf("unexpected TLS result: %#v", typed)
	}
	if typed.ProtocolVersion == nil || typed.CipherSuite == nil || typed.FingerprintSHA256 == nil {
		t.Fatalf("missing negotiated or certificate metadata: %#v", typed)
	}
}

func TestProbeCertificateExpiryWarningIsCompletedUnhealthy(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	defer server.Close()
	configuration, target := configurationForServer(t, server, 30)
	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())
	monitor := New(nil, roots)
	monitor.now = func() time.Time { return server.Certificate().NotAfter.Add(-10 * 24 * time.Hour) }
	result := monitor.Run(context.Background(), probe.Request{
		TargetAddress: target,
		Configuration: configuration,
	})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentUnhealthy {
		t.Fatalf("unexpected expiry outcome: %#v", result)
	}
	if result.ErrorCode != "tls_certificate_expiring" {
		t.Fatalf("unexpected expiry error code: %#v", result)
	}
}

func TestProbeHostnameMismatchIsCompletedUnhealthy(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	defer server.Close()
	configuration, target := configurationForServer(t, server, 0)
	var payload map[string]any
	if err := json.Unmarshal(configuration, &payload); err != nil {
		t.Fatal(err)
	}
	payload["server_name"] = "wrong.example"
	configuration, _ = json.Marshal(payload)
	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())
	result := New(nil, roots).Run(context.Background(), probe.Request{
		TargetAddress: target,
		Configuration: configuration,
	})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentUnhealthy {
		t.Fatalf("unexpected hostname outcome: %#v", result)
	}
	if result.ErrorCode != "tls_hostname_mismatch" {
		t.Fatalf("unexpected hostname error code: %#v", result)
	}
}

func TestProbeUntrustedCertificateIsCompletedUnhealthy(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	defer server.Close()
	configuration, target := configurationForServer(t, server, 0)
	result := New(nil, x509.NewCertPool()).Run(context.Background(), probe.Request{
		TargetAddress: target,
		Configuration: configuration,
	})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentUnhealthy {
		t.Fatalf("unexpected trust outcome: %#v", result)
	}
	if result.ErrorCode != "tls_certificate_untrusted" {
		t.Fatalf("unexpected trust error code: %#v", result)
	}
}

func TestProbeIPTargetRequiresServerName(t *testing.T) {
	configuration := json.RawMessage(`{"schema_version":1,"port":443,"server_name":null,"address_family":"auto","minimum_tls_version":"1.2","expiry_warning_days":30}`)
	result := New(nil, nil).Run(context.Background(), probe.Request{
		TargetAddress: "192.0.2.10",
		Configuration: configuration,
	})
	if result.ExecutionStatus != probe.ExecutionFailed || result.Assessment != probe.AssessmentUnknown {
		t.Fatalf("unexpected IP target outcome: %#v", result)
	}
	if result.ErrorCode != "tls_server_name_required" {
		t.Fatalf("unexpected IP target error code: %#v", result)
	}
}

func configurationForServer(
	t *testing.T, server *httptest.Server, expiryWarningDays int,
) (json.RawMessage, string) {
	t.Helper()
	parsed, err := url.Parse(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	port, err := strconv.Atoi(parsed.Port())
	if err != nil {
		t.Fatal(err)
	}
	certificate := server.Certificate()
	serverName := "example.com"
	if len(certificate.DNSNames) > 0 {
		serverName = certificate.DNSNames[0]
	}
	configuration := map[string]any{
		"schema_version":      1,
		"port":                port,
		"server_name":         serverName,
		"address_family":      "auto",
		"minimum_tls_version": "1.2",
		"expiry_warning_days": expiryWarningDays,
	}
	content, err := json.Marshal(configuration)
	if err != nil {
		t.Fatal(err)
	}
	return content, parsed.Hostname()
}
