package tcp

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"strconv"
	"syscall"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

type fakeDialer struct {
	connection net.Conn
	err        error
}

func (d fakeDialer) DialContext(context.Context, string, string) (net.Conn, error) {
	return d.connection, d.err
}

func TestProbeConnectsToLocalTCPListener(t *testing.T) {
	t.Parallel()
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = listener.Close() }()
	port := listener.Addr().(*net.TCPAddr).Port
	accepted := make(chan struct{})
	go func() {
		connection, acceptErr := listener.Accept()
		if acceptErr == nil {
			_ = connection.Close()
		}
		close(accepted)
	}()
	result := New(nil).Run(context.Background(), probe.Request{
		TargetAddress: "127.0.0.1", Timeout: time.Second,
		Configuration: json.RawMessage(`{"schema_version":1,"port":` +
			strconv.Itoa(port) + `,"address_family":"ipv4"}`),
	})
	<-accepted
	if err := result.Validate(); err != nil {
		t.Fatal(err)
	}
	measurement := result.ProbeResult.(Result)
	if result.Assessment != probe.AssessmentHealthy || measurement.AddressUsed == nil ||
		*measurement.AddressUsed != "127.0.0.1" || measurement.ConnectMS == nil {
		t.Fatalf("result = %#v", result)
	}
}

func TestProbeReportsRefusedLocalConnectionAsUnhealthy(t *testing.T) {
	t.Parallel()
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	_ = listener.Close()
	result := New(nil).Run(context.Background(), probe.Request{
		TargetAddress: "127.0.0.1", Timeout: time.Second,
		Configuration: json.RawMessage(`{"schema_version":1,"port":` +
			strconv.Itoa(port) + `,"address_family":"ipv4"}`),
	})
	if result.ExecutionStatus != probe.ExecutionCompleted ||
		result.Assessment != probe.AssessmentUnhealthy ||
		result.ErrorCode != "tcp_connection_refused" {
		t.Fatalf("result = %#v", result)
	}
}

func TestProbeClassifiesExpectedNetworkFailures(t *testing.T) {
	t.Parallel()
	testCases := []struct {
		name     string
		err      error
		category probe.ErrorCategory
		code     string
	}{
		{
			name: "network unreachable", err: syscall.ENETUNREACH,
			category: probe.ErrorConnection, code: "tcp_network_unreachable",
		},
		{
			name: "host unreachable", err: syscall.EHOSTUNREACH,
			category: probe.ErrorConnection, code: "tcp_host_unreachable",
		},
		{
			name: "resolution failure", err: &net.DNSError{Err: "fixture", Name: "invalid.test"},
			category: probe.ErrorResolution, code: "tcp_resolution_failed",
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()
			result := New(fakeDialer{err: testCase.err}).Run(
				context.Background(), validRequest(),
			)
			if result.ExecutionStatus != probe.ExecutionCompleted ||
				result.Assessment != probe.AssessmentUnhealthy ||
				result.ErrorCategory == nil || *result.ErrorCategory != testCase.category ||
				result.ErrorCode != testCase.code {
				t.Fatalf("result = %#v", result)
			}
		})
	}
}

func TestProbeTreatsLocalResourceFailureAsExecutionFailure(t *testing.T) {
	t.Parallel()
	result := New(fakeDialer{err: syscall.EMFILE}).Run(context.Background(), validRequest())
	if result.ExecutionStatus != probe.ExecutionFailed ||
		result.Assessment != probe.AssessmentUnknown ||
		result.ErrorCategory == nil || *result.ErrorCategory != probe.ErrorResourceLimit ||
		result.ErrorCode != "tcp_local_resource_exhausted" || result.ProbeResult != nil {
		t.Fatalf("result = %#v", result)
	}
}

func TestProbeTreatsCancellationAsExecutionFailure(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result := New(fakeDialer{err: context.Canceled}).Run(ctx, validRequest())
	if result.ExecutionStatus != probe.ExecutionFailed ||
		result.Assessment != probe.AssessmentUnknown || result.ErrorCode != "tcp_cancelled" {
		t.Fatalf("result = %#v", result)
	}
}

func TestProbeMeasuresOnlyDialDurationForConnectMS(t *testing.T) {
	t.Parallel()
	server, client := net.Pipe()
	defer func() { _ = server.Close() }()
	defer func() { _ = client.Close() }()
	implementation := New(fakeDialer{connection: client})
	times := []time.Time{
		time.Unix(0, 0),
		time.Unix(0, int64(5*time.Millisecond)),
		time.Unix(0, int64(25*time.Millisecond)),
	}
	index := 0
	implementation.now = func() time.Time {
		value := times[index]
		index++
		return value
	}
	result := implementation.Run(context.Background(), validRequest())
	measurement := result.ProbeResult.(Result)
	if measurement.ConnectMS == nil || *measurement.ConnectMS != 20 {
		t.Fatalf("connect_ms = %#v", measurement.ConnectMS)
	}
}

func TestConfigurationRejectsUnknownFieldsAndInvalidFamily(t *testing.T) {
	t.Parallel()
	for _, raw := range []string{
		`{"schema_version":1,"port":443,"command":"nc"}`,
		`{"schema_version":1,"port":443,"address_family":"ipx"}`,
	} {
		if _, err := DecodeConfiguration(json.RawMessage(raw)); err == nil {
			t.Fatalf("configuration accepted: %s", raw)
		}
	}
}

func validRequest() probe.Request {
	return probe.Request{
		TargetAddress: "example.test",
		Timeout:       time.Second,
		Configuration: json.RawMessage(
			`{"schema_version":1,"port":443,"address_family":"auto"}`,
		),
	}
}

func TestClassifyErrorPrefersDeadlineOverWrappedConnectionError(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	classification := classifyError(ctx, errors.New("fixture connection error"))
	if classification.category != probe.ErrorTimeout || classification.code != "tcp_connect_timeout" ||
		classification.failed {
		t.Fatalf("classification = %#v", classification)
	}
}
