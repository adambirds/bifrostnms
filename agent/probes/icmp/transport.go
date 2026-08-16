package icmp

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"time"

	xicmp "golang.org/x/net/icmp"
	"golang.org/x/net/ipv4"
	"golang.org/x/net/ipv6"
)

type NativeTransport struct {
	Resolver *net.Resolver
}

type resolvedTarget struct {
	IP        net.IP
	Network   string
	ListenAt  string
	Protocol  int
	EchoType  xicmp.Type
	ReplyType xicmp.Type
}

func (t NativeTransport) Exchange(
	ctx context.Context,
	target string,
	family AddressFamily,
	packetCount int,
	packetInterval time.Duration,
	packetTimeout time.Duration,
	payloadSize int,
) ([]float64, error) {
	resolved, err := t.resolve(ctx, target, family)
	if err != nil {
		return nil, err
	}
	connection, err := xicmp.ListenPacket(resolved.Network, resolved.ListenAt)
	if err != nil {
		return nil, fmt.Errorf("open native ICMP socket: %w", err)
	}
	defer func() { _ = connection.Close() }()
	stopCancellation := context.AfterFunc(ctx, func() { _ = connection.Close() })
	defer stopCancellation()
	destination := &net.IPAddr{IP: resolved.IP}
	payload := make([]byte, payloadSize)
	for index := range payload {
		payload[index] = byte(index)
	}
	id := os.Getpid() & 0xffff
	samplesBySequence := make(map[int]float64, packetCount)
	sentAt := make([]time.Time, packetCount)
	buffer := make([]byte, 2048)
	sequence := 0
	sequenceStartedAt := time.Now()
	finishedAt := sequenceStartedAt.Add(
		time.Duration(packetCount-1)*packetInterval + packetTimeout,
	)
	for sequence < packetCount || time.Now().Before(finishedAt) {
		if err := ctx.Err(); err != nil {
			if errors.Is(err, context.DeadlineExceeded) && sequence >= packetCount {
				break
			}
			return nil, err
		}
		now := time.Now()
		nextSendAt := sequenceStartedAt.Add(time.Duration(sequence) * packetInterval)
		if sequence < packetCount && !now.Before(nextSendAt) {
			message := xicmp.Message{
				Type: resolved.EchoType,
				Code: 0,
				Body: &xicmp.Echo{ID: id, Seq: sequence, Data: payload},
			}
			wire, marshalErr := message.Marshal(nil)
			if marshalErr != nil {
				return nil, fmt.Errorf("encode ICMP echo request: %w", marshalErr)
			}
			sentAt[sequence] = time.Now()
			if _, writeErr := connection.WriteTo(wire, destination); writeErr != nil {
				return nil, fmt.Errorf("send ICMP echo request: %w", writeErr)
			}
			sequence++
			if sequence < packetCount {
				nextSendAt = sequenceStartedAt.Add(time.Duration(sequence) * packetInterval)
			} else {
				nextSendAt = finishedAt
			}
		}
		deadline := nextSendAt
		if finishedAt.Before(deadline) {
			deadline = finishedAt
		}
		if contextDeadline, ok := ctx.Deadline(); ok && contextDeadline.Before(deadline) {
			deadline = contextDeadline
		}
		// Only bound reads. Using SetDeadline also sets the write deadline, which means
		// a read timeout at the next packet boundary leaves an already-expired write
		// deadline on the socket and causes the following echo request to fail locally.
		if err := connection.SetReadDeadline(deadline); err != nil {
			return nil, fmt.Errorf("set ICMP packet read deadline: %w", err)
		}
		read, _, readErr := connection.ReadFrom(buffer)
		if readErr != nil {
			if errors.Is(ctx.Err(), context.DeadlineExceeded) && sequence >= packetCount {
				break
			}
			var networkError net.Error
			if errors.As(readErr, &networkError) && networkError.Timeout() {
				continue
			}
			return nil, fmt.Errorf("read ICMP echo response: %w", readErr)
		}
		response, parseErr := xicmp.ParseMessage(resolved.Protocol, buffer[:read])
		if parseErr != nil || response.Type != resolved.ReplyType {
			continue
		}
		echo, ok := response.Body.(*xicmp.Echo)
		if !ok || echo.ID != id || echo.Seq < 0 || echo.Seq >= sequence {
			continue
		}
		elapsed := time.Since(sentAt[echo.Seq])
		if elapsed <= packetTimeout {
			if _, duplicate := samplesBySequence[echo.Seq]; !duplicate {
				samplesBySequence[echo.Seq] = float64(elapsed) / float64(time.Millisecond)
			}
		}
	}
	samples := make([]float64, 0, len(samplesBySequence))
	for index := 0; index < packetCount; index++ {
		if sample, ok := samplesBySequence[index]; ok {
			samples = append(samples, sample)
		}
	}
	return samples, nil
}

func (t NativeTransport) resolve(
	ctx context.Context, target string, family AddressFamily,
) (resolvedTarget, error) {
	resolver := t.Resolver
	if resolver == nil {
		resolver = net.DefaultResolver
	}
	addresses, err := resolver.LookupIPAddr(ctx, target)
	if err != nil {
		return resolvedTarget{}, fmt.Errorf("resolve ICMP target: %w", err)
	}
	for _, address := range addresses {
		isIPv4 := address.IP.To4() != nil
		if family == AddressFamilyIPv4 && !isIPv4 || family == AddressFamilyIPv6 && isIPv4 {
			continue
		}
		if isIPv4 {
			return resolvedTarget{
				IP: address.IP, Network: "ip4:icmp", ListenAt: "0.0.0.0",
				Protocol: 1, EchoType: ipv4.ICMPTypeEcho, ReplyType: ipv4.ICMPTypeEchoReply,
			}, nil
		}
		return resolvedTarget{
			IP: address.IP, Network: "ip6:ipv6-icmp", ListenAt: "::",
			Protocol: 58, EchoType: ipv6.ICMPTypeEchoRequest, ReplyType: ipv6.ICMPTypeEchoReply,
		}, nil
	}
	return resolvedTarget{}, errors.New("target has no address in the requested family")
}

func NativeSocketAvailable(ctx context.Context) bool {
	for _, candidate := range []resolvedTarget{
		{Network: "ip4:icmp", ListenAt: "0.0.0.0"},
		{Network: "ip6:ipv6-icmp", ListenAt: "::"},
	} {
		if err := ctx.Err(); err != nil {
			return false
		}
		connection, err := xicmp.ListenPacket(candidate.Network, candidate.ListenAt)
		if err == nil {
			_ = connection.Close()
			return true
		}
	}
	return false
}
