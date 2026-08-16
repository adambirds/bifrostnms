package http

import (
	"context"
	"crypto/x509"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

func TestProbeHealthyHTTP(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("X-Bifrost", "ready")
		writer.WriteHeader(http.StatusOK)
		_, _ = writer.Write([]byte("healthy response"))
	}))
	defer server.Close()

	configuration := configurationForServer(t, server.URL, map[string]any{
		"expected_status_codes": []int{200},
		"expected_header_values": []map[string]string{{"name": "X-Bifrost", "value": "ready"}},
		"expected_body_contains": []string{"healthy"},
	})
	result := New(nil).Run(context.Background(), probe.Request{
		TargetAddress: configuration.target,
		Configuration: configuration.raw,
	})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentHealthy {
		t.Fatalf("unexpected outcome: %#v", result)
	}
	typed, ok := result.ProbeResult.(Result)
	if !ok || typed.StatusCode == nil || *typed.StatusCode != 200 {
		t.Fatalf("unexpected typed result: %#v", result.ProbeResult)
	}
	if typed.AssertionsTotal != 3 || typed.AssertionsFailed != 0 || typed.TotalMS == nil {
		t.Fatalf("unexpected assertions/timing: %#v", typed)
	}
}

func TestProbeAssertionFailureIsCompletedUnhealthy(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusTeapot)
		_, _ = writer.Write([]byte("nope"))
	}))
	defer server.Close()

	configuration := configurationForServer(t, server.URL, map[string]any{
		"expected_status_codes": []int{200},
		"expected_body_contains": []string{"expected"},
	})
	result := New(nil).Run(context.Background(), probe.Request{
		TargetAddress: configuration.target,
		Configuration: configuration.raw,
	})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentUnhealthy {
		t.Fatalf("unexpected outcome: %#v", result)
	}
	if result.ErrorCode != "http_assertion_failed" || result.ErrorCategory == nil ||
		*result.ErrorCategory != probe.ErrorAssertion {
		t.Fatalf("unexpected error classification: %#v", result)
	}
	typed := result.ProbeResult.(Result)
	if typed.AssertionsTotal != 2 || typed.AssertionsFailed != 2 {
		t.Fatalf("unexpected assertion counts: %#v", typed)
	}
}

func TestProbeFollowsBoundedRedirects(t *testing.T) {
	final := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer final.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		http.Redirect(writer, request, final.URL+"/final?token=secret", http.StatusFound)
	}))
	defer redirect.Close()

	configuration := configurationForServer(t, redirect.URL, map[string]any{
		"expected_status_codes": []int{204},
		"maximum_redirects": 2,
	})
	result := New(nil).Run(context.Background(), probe.Request{
		TargetAddress: configuration.target,
		Configuration: configuration.raw,
	})
	typed := result.ProbeResult.(Result)
	if result.Assessment != probe.AssessmentHealthy || typed.RedirectCount != 1 {
		t.Fatalf("unexpected redirect result: %#v", result)
	}
	if typed.FinalURLRedacted == nil || strings.Contains(*typed.FinalURLRedacted, "secret") ||
		!strings.Contains(*typed.FinalURLRedacted, "REDACTED") {
		t.Fatalf("final URL was not redacted: %#v", typed.FinalURLRedacted)
	}
}

func TestProbeHTTPSUsesConfiguredTrustStore(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	pool := x509.NewCertPool()
	pool.AddCert(server.Certificate())
	configuration := configurationForServer(t, server.URL, map[string]any{
		"expected_status_codes": []int{200},
	})
	result := New(pool).Run(context.Background(), probe.Request{
		TargetAddress: configuration.target,
		Configuration: configuration.raw,
	})
	if result.Assessment != probe.AssessmentHealthy {
		t.Fatalf("unexpected TLS result: %#v", result)
	}
	typed := result.ProbeResult.(Result)
	if typed.TLSMS == nil {
		t.Fatalf("expected TLS timing: %#v", typed)
	}
}

func TestProbeRejectsSensitiveRequestHeaders(t *testing.T) {
	raw := json.RawMessage(`{"schema_version":1,"scheme":"https","method":"GET","path":"/","follow_redirects":true,"maximum_redirects":5,"request_headers":{"Authorization":"secret"},"expected_status_codes":[200],"maximum_response_bytes":1024,"address_family":"auto"}`)
	if err := New(nil).Validate(raw); err == nil {
		t.Fatal("expected sensitive header validation failure")
	}
}

func TestProbeHonorsCancellation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		time.Sleep(100 * time.Millisecond)
		writer.WriteHeader(http.StatusOK)
	}))
	defer server.Close()
	configuration := configurationForServer(t, server.URL, map[string]any{"expected_status_codes": []int{200}})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result := New(nil).Run(ctx, probe.Request{TargetAddress: configuration.target, Configuration: configuration.raw})
	if result.ExecutionStatus != probe.ExecutionFailed || result.ErrorCode != "http_cancelled" {
		t.Fatalf("unexpected cancelled result: %#v", result)
	}
}

type serverConfiguration struct {
	target string
	raw    json.RawMessage
}

func configurationForServer(t *testing.T, serverURL string, overrides map[string]any) serverConfiguration {
	t.Helper()
	request, err := http.NewRequest(http.MethodGet, serverURL, nil)
	if err != nil {
		t.Fatal(err)
	}
	port := 80
	if request.URL.Scheme == "https" {
		port = 443
	}
	if _, parsedPort, found := strings.Cut(request.URL.Host, ":"); found {
		if value, conversionErr := strconv.Atoi(parsedPort); conversionErr == nil {
			port = value
		}
	}
	configuration := map[string]any{
		"schema_version": 1,
		"scheme": request.URL.Scheme,
		"port": port,
		"path": "/",
		"method": "GET",
		"follow_redirects": true,
		"maximum_redirects": 5,
		"host_header": nil,
		"request_headers": map[string]string{},
		"expected_status_codes": []int{200},
		"expected_header_values": []map[string]string{},
		"expected_body_contains": []string{},
		"maximum_response_bytes": 1048576,
		"address_family": "auto",
	}
	for key, value := range overrides {
		configuration[key] = value
	}
	raw, err := json.Marshal(configuration)
	if err != nil {
		t.Fatal(err)
	}
	return serverConfiguration{target: request.URL.Hostname(), raw: raw}
}
