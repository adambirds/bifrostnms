package icmp

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
)

const (
	ConfigurationSchemaVersion uint32 = 1
	ResultSchemaVersion        uint32 = 1
	MaximumPacketCount                = 100
)

type AddressFamily string

const (
	AddressFamilyAuto AddressFamily = "auto"
	AddressFamilyIPv4 AddressFamily = "ipv4"
	AddressFamilyIPv6 AddressFamily = "ipv6"
)

type Configuration struct {
	SchemaVersion       int           `json:"schema_version"`
	PacketCount         int           `json:"packet_count"`
	PacketIntervalMS    int           `json:"packet_interval_ms"`
	PerPacketTimeoutMS  int           `json:"per_packet_timeout_ms,omitempty"`
	PayloadSizeBytes    int           `json:"payload_size_bytes"`
	AddressFamily       AddressFamily `json:"address_family"`
	MaximumPacketLoss   *float64      `json:"maximum_packet_loss_percent,omitempty"`
	MaximumAverageRTTMS *float64      `json:"maximum_average_rtt_ms,omitempty"`
}

func DefaultConfiguration() Configuration {
	return Configuration{
		SchemaVersion: 1, PacketCount: 20, PacketIntervalMS: 50,
		PayloadSizeBytes: 56, AddressFamily: AddressFamilyAuto,
	}
}

func DecodeConfiguration(raw json.RawMessage) (Configuration, error) {
	configuration := DefaultConfiguration()
	if err := probe.DecodeConfigurationStrictInto(raw, &configuration); err != nil {
		return Configuration{}, err
	}
	if err := configuration.Validate(); err != nil {
		return Configuration{}, err
	}
	return configuration, nil
}

func (c Configuration) Validate() error {
	if c.SchemaVersion != 1 {
		return errors.New("ICMP configuration schema version is unsupported")
	}
	if c.PacketCount < 1 || c.PacketCount > MaximumPacketCount {
		return fmt.Errorf("packet_count must be within 1..%d", MaximumPacketCount)
	}
	if c.PacketIntervalMS < 10 || c.PacketIntervalMS > 1000 {
		return errors.New("packet_interval_ms must be within 10..1000")
	}
	if c.PerPacketTimeoutMS < 0 || c.PerPacketTimeoutMS > 60_000 {
		return errors.New("per_packet_timeout_ms must be within 1..60000 when supplied")
	}
	if c.PayloadSizeBytes < 0 || c.PayloadSizeBytes > 1400 {
		return errors.New("payload_size_bytes must be within 0..1400")
	}
	if c.AddressFamily != AddressFamilyAuto && c.AddressFamily != AddressFamilyIPv4 &&
		c.AddressFamily != AddressFamilyIPv6 {
		return errors.New("address_family must be auto, ipv4 or ipv6")
	}
	for name, threshold := range map[string]*float64{
		"maximum_packet_loss_percent": c.MaximumPacketLoss,
		"maximum_average_rtt_ms":      c.MaximumAverageRTTMS,
	} {
		if threshold != nil && (math.IsNaN(*threshold) || math.IsInf(*threshold, 0) || *threshold < 0) {
			return fmt.Errorf("%s must be finite and non-negative", name)
		}
	}
	if c.MaximumPacketLoss != nil && *c.MaximumPacketLoss > 100 {
		return errors.New("maximum_packet_loss_percent cannot exceed 100")
	}
	return nil
}

func (c Configuration) Timeout(monitorTimeout time.Duration) (time.Duration, error) {
	remaining := monitorTimeout - time.Duration(c.PacketCount-1)*time.Duration(c.PacketIntervalMS)*time.Millisecond
	if remaining < time.Millisecond {
		return 0, errors.New("packet sequence does not fit within the monitor timeout")
	}
	packetTimeout := time.Duration(c.PerPacketTimeoutMS) * time.Millisecond
	if c.PerPacketTimeoutMS == 0 {
		packetTimeout = remaining
	}
	if packetTimeout > remaining {
		return 0, errors.New("packet timeout and interval sequence exceed the monitor timeout")
	}
	return packetTimeout, nil
}
