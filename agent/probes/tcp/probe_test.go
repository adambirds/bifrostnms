package tcp

import (
	"context"
	"encoding/json"
	"net"
	"strconv"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

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
		*measurement.AddressUsed != "127.0.0.1" ||
		measurement.ConnectMS == nil {
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
		result.Assessment != probe.AssessmentUnhealthy || result.ErrorCode != "tcp_connection_failed" {
		t.Fatalf("result = %#v", result)
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
