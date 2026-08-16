package dns

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"testing"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	"golang.org/x/net/dns/dnsmessage"
)

func TestProbeExplicitResolverReturnsTypedAnswer(t *testing.T) {
	resolverAddress, stop := startUDPResolver(t, false)
	defer stop()
	configuration := explicitConfiguration(t, resolverAddress, map[string]any{
		"expected_answers": []map[string]string{{"value": "192.0.2.10"}},
	})
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	result := New(nil).Run(ctx, probe.Request{TargetAddress: "example.com", Configuration: configuration})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentHealthy {
		t.Fatalf("unexpected outcome: %#v", result)
	}
	typed := result.ProbeResult.(Result)
	if typed.ResponseCode == nil || *typed.ResponseCode != "NOERROR" || typed.AnswerCount != 1 {
		t.Fatalf("unexpected DNS result: %#v", typed)
	}
	if typed.Answers[0].Value != "192.0.2.10" || typed.AssertionsFailed != 0 {
		t.Fatalf("unexpected DNS answer: %#v", typed)
	}
}

func TestProbeNXDomainIsCompletedUnhealthyWhenUnexpected(t *testing.T) {
	resolverAddress, stop := startUDPResolver(t, true)
	defer stop()
	configuration := explicitConfiguration(t, resolverAddress, nil)
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	result := New(nil).Run(ctx, probe.Request{TargetAddress: "missing.example", Configuration: configuration})
	if result.ExecutionStatus != probe.ExecutionCompleted || result.Assessment != probe.AssessmentUnhealthy {
		t.Fatalf("unexpected outcome: %#v", result)
	}
	if result.ErrorCode != "dns_assertion_failed" {
		t.Fatalf("unexpected error code: %#v", result)
	}
}

func TestProbeHonorsCancellation(t *testing.T) {
	configuration := json.RawMessage(`{"schema_version":1,"resolver_mode":"explicit","resolver_address":"192.0.2.1","resolver_port":53,"transport":"udp_with_tcp_fallback","query_name":"example.com","query_type":"A","recursion_desired":true,"expected_response_codes":["NOERROR"],"expected_answers":[]}`)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result := New(nil).Run(ctx, probe.Request{TargetAddress: "example.com", Configuration: configuration})
	if result.ExecutionStatus != probe.ExecutionFailed || result.ErrorCode != "dns_cancelled" {
		t.Fatalf("unexpected cancelled result: %#v", result)
	}
}

func startUDPResolver(t *testing.T, nxdomain bool) (string, func()) {
	t.Helper()
	connection, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		buffer := make([]byte, MaximumMessageBytes)
		for {
			count, remote, readErr := connection.ReadFrom(buffer)
			if readErr != nil {
				return
			}
			response, responseErr := buildTestResponse(buffer[:count], nxdomain)
			if responseErr == nil {
				_, _ = connection.WriteTo(response, remote)
			}
		}
	}()
	stop := func() {
		_ = connection.Close()
		<-stopped
	}
	return connection.LocalAddr().String(), stop
}

func buildTestResponse(query []byte, nxdomain bool) ([]byte, error) {
	var parser dnsmessage.Parser
	header, err := parser.Start(query)
	if err != nil {
		return nil, err
	}
	questions, err := parser.AllQuestions()
	if err != nil || len(questions) != 1 {
		return nil, err
	}
	rcode := dnsmessage.RCodeSuccess
	if nxdomain {
		rcode = dnsmessage.RCodeNameError
	}
	builder := dnsmessage.NewBuilder(nil, dnsmessage.Header{ID: header.ID, Response: true,
		Authoritative: true, RecursionDesired: header.RecursionDesired, RCode: rcode})
	builder.EnableCompression()
	if err := builder.StartQuestions(); err != nil {
		return nil, err
	}
	if err := builder.Question(questions[0]); err != nil {
		return nil, err
	}
	if !nxdomain {
		if err := builder.StartAnswers(); err != nil {
			return nil, err
		}
		resourceHeader := dnsmessage.ResourceHeader{Name: questions[0].Name, Type: dnsmessage.TypeA,
			Class: dnsmessage.ClassINET, TTL: 60}
		if err := builder.AResource(resourceHeader, dnsmessage.AResource{A: [4]byte{192, 0, 2, 10}}); err != nil {
			return nil, err
		}
	}
	return builder.Finish()
}

func explicitConfiguration(t *testing.T, resolverAddress string, overrides map[string]any) json.RawMessage {
	t.Helper()
	host, port, err := net.SplitHostPort(resolverAddress)
	if err != nil {
		t.Fatal(err)
	}
	configuration := map[string]any{
		"schema_version":          1,
		"resolver_mode":           "explicit",
		"resolver_address":        host,
		"resolver_port":           portNumber(t, port),
		"transport":               "udp_with_tcp_fallback",
		"query_name":              "example.com",
		"query_type":              "A",
		"recursion_desired":       true,
		"expected_response_codes": []string{"NOERROR"},
		"expected_answers":        []map[string]string{},
	}
	for key, value := range overrides {
		configuration[key] = value
	}
	content, err := json.Marshal(configuration)
	if err != nil {
		t.Fatal(err)
	}
	return content
}

func portNumber(t *testing.T, value string) int {
	t.Helper()
	var port int
	if _, err := fmt.Sscanf(value, "%d", &port); err != nil {
		t.Fatal(err)
	}
	return port
}
